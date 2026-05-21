"""
retrieval/web_search_adapter.py
================================
WebSearchAdapter — sanctioned-domain web search + content scraping
with topic-aware domain routing.

Spec source  : SPEC-200 §5.4, REQ-200-071, REQ-200-ER1 through ER5
               REQ-200-160 (error handling)
Phase        : 3 — Agent Definitions (Implementation)
Priority     : 2 in ADAPTER_PRIORITY_ORDER (after PubMed)
Gap ref      : G-RETRIEVAL-01 — Director-directed change 2026-05-10
               G-RETRIEVAL-02 — Topic-routing expansion 2026-05-16

Replaces
--------
HealthdirectAdapter, BetterHealthAdapter, WHOAdapter (all superseded).

Architecture
------------
Two-phase search per query:

  Phase 1 — Sanctioned domain search  (topic-routed)
    The adapter first classifies the query into a set of TopicTags using
    lightweight keyword matching.  It then selects ONLY the domain subset
    relevant to those topics (see TOPIC_DOMAIN_MAP below), capped at
    MAX_DOMAINS_PER_QUERY to keep the DuckDuckGo site: clause short.

    For each matched URL that resolves to a sanctioned domain, the adapter
    fetches and parses the full page via requests + BeautifulSoup to extract
    the main article body (not just the DDG snippet).

    Sanctioned domain registry (14 domains as of 2026-05-16):
      ──── Government / clinical ────────────────────────────────────────
      1.  healthdirect.gov.au            AU Government health info
      2.  betterhealth.vic.gov.au        Better Health Channel (VIC)
      3.  who.int                        World Health Organization
      4.  medicarementalhealth.gov.au    Medicare mental health access (AU)
      ──── Broad mental health NGOs ─────────────────────────────────────
      5.  beyondblue.org.au              Beyond Blue (anxiety, depression)
      6.  blackdoginstitute.org.au       Black Dog Institute (research-led)
      7.  lifeline.org.au                Lifeline (crisis, fact-sheets, guides)
      ──── Population-specific ──────────────────────────────────────────
      8.  headspace.org.au               Youth (12–25) mental health
      9.  au.reachout.com                Youth wellbeing platform
      10. kidshelpline.com.au            Under-25 counselling / crisis
      11. mensline.org.au                Men's mental health & relationships
      ──── Specialised conditions ───────────────────────────────────────
      12. blueknot.org.au                Trauma / childhood abuse survivors
      13. griefline.org.au               Grief and bereavement support
      ──── Cultural / Indigenous ────────────────────────────────────────
      14. 13yarn.org.au                  Indigenous AU mental health & crisis

  Phase 2 — External fallback (higher scrutiny)
    Triggered ONLY when Phase 1 returns fewer than MIN_SANCTIONED_RESULTS
    items.  External results:
      - Are NOT scraped (only DDG snippet is used as abstract)
      - Are tagged SourceTier.SECONDARY (vs PRIMARY for sanctioned)
      - Have a "[EXTERNAL — HIGHER SCRUTINY REQUIRED]" prefix injected
        into the abstract field
      - Are appended after any Phase 1 results

    The Synthesizer uses SourceTier.SECONDARY to reduce confidence per
    REQ-200-ER3.

Topic routing
-------------
  Queries are classified into one or more TopicTags via keyword matching.
  Each domain carries a frozenset of TopicTags it covers.  The adapter
  builds the DDG site: clause from the union of domains matching any
  detected tag, capped at MAX_DOMAINS_PER_QUERY=6.

  If no specific topic is detected the query falls through to the
  DEFAULT_DOMAIN_KEYS fallback set (general-coverage domains only).

  This ensures the search never fans out across all 14 domains for a
  query that only a handful of them cover.

Dependencies
------------
  pip install duckduckgo-search beautifulsoup4 lxml

Cache
-----
  TTL: 3 days (WEB_SEARCH_CACHE_POLICY) — shorter than static corpus TTL
  because web content changes more frequently.
  Cache key: SHA-256(source_name + "|" + normalised_query)
  Cache path: retrieval/cache/<hex>.json

Rate limiting
-------------
  duckduckgo-search handles DuckDuckGo's informal rate limits internally.
  Content scraping adds 0.5s sleep between successive fetches to avoid
  hammering sanctioned domains.  Each search call scrapes at most
  MAX_SCRAPE_ATTEMPTS pages.

Error handling
--------------
  All failures return RetrievalError, never raised exceptions. (REQ-200-160)
  If Phase 1 returns a RetrievalError (DDG unavailable), the error is returned
  without falling back to Phase 2 — a DDG failure affects both phases equally.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import FrozenSet, Optional
from urllib.parse import urlparse

from docs.schemas.acp_schemas import EvidenceItem, EvidenceTier, SourceTier
from docs.schemas.retrieval_schemas import (
    WEB_SEARCH_CACHE_POLICY,
    StaticCacheQueryParams,
    RetrievalError,
    RetrievalResult,
)
from retrieval.base_adapter import CachedBaseAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topic taxonomy
# ---------------------------------------------------------------------------

class TopicTag(str, Enum):
    """
    Controlled vocabulary of mental-health topic areas.

    Each tag represents a distinct user-population or clinical domain.
    Domains are tagged with the set of topics they reliably cover;
    queries are classified into tags by keyword matching.  The intersection
    drives which domains the DDG site: clause targets.

    [CONCEPT] String-enum: TopicTag inherits from both str and Enum so
    instances compare equal to plain strings (e.g. TopicTag.CRISIS == "crisis")
    and can be used as dict keys without extra conversion.
    """
    GENERAL        = "general"        # broad mental health — used as fallback
    CRISIS         = "crisis"         # acute distress, suicide ideation, self-harm
    YOUTH          = "youth"          # topics specific to 12–25 year-olds
    MEN            = "men"            # men's mental health
    WOMEN          = "women"          # women's mental health (incl. perinatal)
    INDIGENOUS     = "indigenous"     # First Nations / Indigenous AU
    GRIEF          = "grief"          # grief, loss, bereavement
    TRAUMA         = "trauma"         # trauma, PTSD, childhood abuse
    CLINICAL       = "clinical"       # clinical guidelines, research, diagnosis
    SERVICES       = "services"       # service referral, Medicare, finding help
    ANXIETY        = "anxiety"        # anxiety disorders, panic, OCD
    DEPRESSION     = "depression"     # depression, mood disorders, bipolar
    RELATIONSHIPS  = "relationships"  # relationships, family, loneliness


# ---------------------------------------------------------------------------
# Domain registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DomainProfile:
    """
    Metadata record for a single sanctioned domain.

    Attributes
    ----------
    domain : str
        Bare domain (no scheme, no www.), e.g. 'beyondblue.org.au'.
    label : str
        Human-readable source name used in EvidenceItem.source_name.
    topic_tags : FrozenSet[TopicTag]
        Topics this domain reliably covers.  The router uses this set
        to decide whether to include the domain for a given query.
    path_prefixes : tuple[str, ...]
        Optional URL path prefixes that are specifically in scope.
        Used for documentation and future path-level filtering.
        An empty tuple means the whole domain is in scope.
    priority : int
        Tiebreaker when the MAX_DOMAINS_PER_QUERY cap is reached.
        Higher = included first.  Range: 1 (lowest) – 10 (highest).
    """
    domain        : str
    label         : str
    topic_tags    : FrozenSet[TopicTag]
    path_prefixes : tuple[str, ...] = field(default_factory=tuple)
    priority      : int             = 5


# [CONCEPT] frozenset: an immutable set.  We use it for topic_tags so
# DomainProfile can be hashed (required for frozen dataclasses and set
# membership checks).  frozenset({TopicTag.CRISIS, TopicTag.GENERAL})
# is equivalent to a normal set but cannot be modified after creation.

DOMAIN_REGISTRY: list[DomainProfile] = [

    # ── Government / clinical ─────────────────────────────────────────────
    DomainProfile(
        domain     = "healthdirect.gov.au",
        label      = "Healthdirect Australia",
        topic_tags = frozenset({
            TopicTag.GENERAL, TopicTag.SERVICES, TopicTag.CLINICAL,
        }),
        priority   = 9,
    ),
    DomainProfile(
        domain     = "betterhealth.vic.gov.au",
        label      = "Better Health Channel",
        topic_tags = frozenset({TopicTag.GENERAL}),
        priority   = 7,
    ),
    DomainProfile(
        domain     = "who.int",
        label      = "World Health Organization",
        topic_tags = frozenset({TopicTag.CLINICAL, TopicTag.GENERAL}),
        priority   = 6,
    ),
    DomainProfile(
        domain     = "medicarementalhealth.gov.au",
        label      = "Medicare Mental Health",
        topic_tags = frozenset({TopicTag.SERVICES, TopicTag.GENERAL}),
        priority   = 8,
    ),

    # ── Broad mental health NGOs ──────────────────────────────────────────
    DomainProfile(
        domain     = "beyondblue.org.au",
        label      = "Beyond Blue",
        topic_tags = frozenset({
            TopicTag.GENERAL, TopicTag.ANXIETY, TopicTag.DEPRESSION,
            TopicTag.WOMEN, TopicTag.CRISIS,
        }),
        # The women's mental health section is specifically in scope per
        # Director whitelist (2026-05-16).  The full domain is also in scope.
        path_prefixes = (
            "/mental-health/womens-mental-health",
        ),
        priority   = 10,
    ),
    DomainProfile(
        domain     = "blackdoginstitute.org.au",
        label      = "Black Dog Institute",
        topic_tags = frozenset({
            TopicTag.DEPRESSION, TopicTag.CLINICAL, TopicTag.GENERAL,
        }),
        priority   = 8,
    ),
    DomainProfile(
        domain     = "lifeline.org.au",
        label      = "Lifeline Australia",
        topic_tags = frozenset({
            TopicTag.CRISIS, TopicTag.GRIEF, TopicTag.GENERAL,
        }),
        # Three specific toolkit sections are in scope per Director whitelist.
        path_prefixes = (
            "/get-help/support-toolkit/fact-sheets",
            "/get-help/support-toolkit/techniques-and-guides",
            "/get-help/support-toolkit/topics",
        ),
        priority   = 9,
    ),

    # ── Population-specific ───────────────────────────────────────────────
    DomainProfile(
        domain     = "headspace.org.au",
        label      = "headspace",
        topic_tags = frozenset({
            TopicTag.YOUTH, TopicTag.ANXIETY, TopicTag.DEPRESSION,
            TopicTag.GENERAL,
        }),
        path_prefixes = (
            "/explore-topics/for-young-people/mental-ill-health/",
        ),
        priority   = 8,
    ),
    DomainProfile(
        domain     = "au.reachout.com",
        label      = "ReachOut Australia",
        topic_tags = frozenset({
            TopicTag.YOUTH, TopicTag.ANXIETY, TopicTag.RELATIONSHIPS,
            TopicTag.GENERAL,
        }),
        path_prefixes = ("/all-topics",),
        priority   = 7,
    ),
    DomainProfile(
        domain     = "kidshelpline.com.au",
        label      = "Kids Helpline",
        topic_tags = frozenset({
            TopicTag.YOUTH, TopicTag.CRISIS, TopicTag.GENERAL,
        }),
        path_prefixes = ("/young-adults",),
        priority   = 8,
    ),
    DomainProfile(
        domain     = "mensline.org.au",
        label      = "MensLine Australia",
        topic_tags = frozenset({
            TopicTag.MEN, TopicTag.RELATIONSHIPS, TopicTag.CRISIS,
            TopicTag.GENERAL,
        }),
        path_prefixes = ("/mens-mental-health/",),
        priority   = 8,
    ),

    # ── Specialised conditions ────────────────────────────────────────────
    DomainProfile(
        domain     = "blueknot.org.au",
        label      = "Blue Knot Foundation",
        topic_tags = frozenset({
            TopicTag.TRAUMA, TopicTag.RELATIONSHIPS, TopicTag.GENERAL,
        }),
        path_prefixes = ("/resources/fact-sheets/",),
        priority   = 8,
    ),
    DomainProfile(
        domain     = "griefline.org.au",
        label      = "GriefLine",
        topic_tags = frozenset({TopicTag.GRIEF, TopicTag.CRISIS}),
        path_prefixes = ("/resources/",),
        priority   = 9,
    ),

    # ── Cultural / Indigenous ─────────────────────────────────────────────
    DomainProfile(
        domain     = "13yarn.org.au",
        label      = "13YARN",
        topic_tags = frozenset({
            TopicTag.INDIGENOUS, TopicTag.CRISIS, TopicTag.GENERAL,
        }),
        path_prefixes = ("/factsheets",),
        priority   = 10,  # highest priority within its topic — no substitute
    ),
]


# ---------------------------------------------------------------------------
# Derived lookups (built once at import time from DOMAIN_REGISTRY)
# ---------------------------------------------------------------------------

# Flat list of all sanctioned domain strings — used by _is_sanctioned().
SANCTIONED_DOMAINS: list[str] = [dp.domain for dp in DOMAIN_REGISTRY]

# Map: domain string → DomainProfile (for fast lookup).
_DOMAIN_PROFILE: dict[str, DomainProfile] = {dp.domain: dp for dp in DOMAIN_REGISTRY}

# Human-readable label lookup (backward-compatible with existing call sites).
_DOMAIN_LABELS: dict[str, str] = {dp.domain: dp.label for dp in DOMAIN_REGISTRY}

# Map: TopicTag → list[DomainProfile] sorted descending by priority.
# Built automatically so adding a new DomainProfile is the only change needed.
_TOPIC_DOMAIN_MAP: dict[TopicTag, list[DomainProfile]] = {}
for _dp in DOMAIN_REGISTRY:
    for _tag in _dp.topic_tags:
        _TOPIC_DOMAIN_MAP.setdefault(_tag, []).append(_dp)
# Sort each bucket by priority descending so high-priority domains are
# picked first when the MAX_DOMAINS_PER_QUERY cap is applied.
for _tag in _TOPIC_DOMAIN_MAP:
    _TOPIC_DOMAIN_MAP[_tag].sort(key=lambda p: p.priority, reverse=True)

# Domains included when no specific topic is detected.
# These are the highest-quality general-coverage domains.
_DEFAULT_DOMAIN_KEYS: tuple[str, ...] = (
    "beyondblue.org.au",
    "healthdirect.gov.au",
    "blackdoginstitute.org.au",
    "betterhealth.vic.gov.au",
    "who.int",
)


# ---------------------------------------------------------------------------
# Keyword → TopicTag mapping
# ---------------------------------------------------------------------------

# [CONCEPT] This is a "signal dictionary" — a simple lookup table that maps
# plain-language keyword patterns to topic categories.  Each key is a TopicTag;
# each value is a list of lowercase substrings.  If any substring appears in
# the lowercased query, the corresponding tag is activated.  This avoids
# loading an NLP model just for routing — fast and deterministic.
#
# Keywords are chosen to be specific enough to avoid false positives but broad
# enough to catch natural phrasing variations.  Stemming is approximated by
# including common root forms (e.g. "griev" catches "grieving", "grieved",
# "grief").

_TOPIC_KEYWORDS: dict[TopicTag, list[str]] = {
    TopicTag.CRISIS: [
        "crisis", "suicid", "self-harm", "self harm", "overdose",
        "harm myself", "end my life", "want to die", "not want to live",
        "kill myself", "hopeless", "no reason to live", "emergency",
        "urgent help", "desperate",
    ],
    TopicTag.YOUTH: [
        "young", "teen", "teenager", "adolescent", "child", "kid",
        "school", "university", "uni", "student", "youth", "12-25",
        "under 25", "young adult", "highschool", "high school",
    ],
    TopicTag.MEN: [
        "men", "man", "male", "masculine", "father", "husband",
        "boyfriend", "masculinity", "bloke", "guy",
    ],
    TopicTag.WOMEN: [
        "women", "woman", "female", "maternal", "postnatal",
        "pregnancy", "menopause", "menstrual", "postpartum",
        "mother", "mum", "perinatal",
    ],
    TopicTag.INDIGENOUS: [
        "indigenous", "aboriginal", "torres strait", "first nations",
        "atsi", "mob", "yarn", "13yarn", "cultural safety",
    ],
    TopicTag.GRIEF: [
        "grief", "griev", "loss", "bereavement", "bereaved",
        "death", "died", "mourning", "lost someone", "passed away",
    ],
    TopicTag.TRAUMA: [
        "trauma", "traumatic", "abuse", "abused", "ptsd",
        "post-traumatic", "assault", "survivor", "childhood abuse",
        "neglect", "complex trauma", "c-ptsd",
    ],
    TopicTag.CLINICAL: [
        "clinical", "research", "evidence", "guideline", "diagnosis",
        "diagnostic", "treatment", "medication", "pharmacological",
        "cognitive behavioural", "cbt", "therapy",
    ],
    TopicTag.SERVICES: [
        "service", "referral", "gp", "doctor", "psychologist",
        "psychiatrist", "medicare", "find help", "access support",
        "treatment option", "how to get help",
    ],
    TopicTag.ANXIETY: [
        "anxiety", "anxious", "panic attack", "panic", "phobia",
        "worry", "ocd", "obsessive", "compulsive", "social anxiety",
        "agoraphobia", "generalised anxiety",
    ],
    TopicTag.DEPRESSION: [
        "depression", "depress", "bipolar", "mood disorder", "low mood",
        "persistent sadness", "anhedonia", "fatigue", "worthless",
        "dysthymia",
    ],
    TopicTag.RELATIONSHIPS: [
        "relationship", "family", "partner", "loneliness", "lonely",
        "isolation", "social connection", "friendship", "divorce",
        "separation", "domestic", "conflict",
    ],
    # GENERAL has no keywords — it is the fallback, never detected by match.
}


# ---------------------------------------------------------------------------
# Routing constants
# ---------------------------------------------------------------------------

# If Phase 1 returns fewer than this many sanctioned results, trigger Phase 2.
# Set to 0 to disable Phase 2 entirely (Director directive: block all non-sanctioned
# sources at the WebSearchAdapter layer; PubMed adapter is unaffected — it uses
# the NCBI API independently of DuckDuckGo).
# Phase 1 already validates every URL via _is_sanctioned() before returning items.
MIN_SANCTIONED_RESULTS: int = 0

# Maximum sanctioned domains included in a single DDG site: query.
# Keeping this ≤ 6 ensures the query string stays within DDG limits and
# avoids unnecessary latency from unrelated domain hits.
MAX_DOMAINS_PER_QUERY: int = 6

# Maximum pages to scrape per search call (keeps latency under control).
MAX_SCRAPE_ATTEMPTS: int = 5

# Delay between successive content scrapes (seconds).
_SCRAPE_DELAY: float = 0.5

# Maximum content length (chars) stored in abstract field.
# Enough to give the Synthesizer meaningful context without flooding the prompt.
_MAX_ABSTRACT_CHARS: int = 1500

# Scrutiny prefix injected into abstracts from external (non-sanctioned) sources.
_EXTERNAL_SCRUTINY_PREFIX = (
    "[EXTERNAL — HIGHER SCRUTINY REQUIRED: this result is from a non-sanctioned "
    "web source and has not been curated. The Synthesizer MUST apply reduced "
    "confidence when citing this item.] "
)

# User-Agent sent with scraping requests.
# Identify ourselves honestly — do not impersonate a browser.
_USER_AGENT = (
    "NIKKO-Research-Bot/1.0 "
    "(mental health evidence retrieval; contact: nikko-research@example.com)"
)


# ---------------------------------------------------------------------------
# Module-level helper (used by pipeline to populate synthesizer hints)
# ---------------------------------------------------------------------------

def get_preferred_source_labels(topic_hints: frozenset) -> frozenset[str]:
    """
    Return the set of human-readable source labels (DomainProfile.label) for
    every domain that covers at least one of the supplied topic hints.

    Used by NikkoPipeline._steps4_7_guidance_evidence() to compute the
    `preferred_sources` argument passed to EvidenceSynthesizerAgent.synthesize().
    The synthesizer uses this set to give a sub-bucket ranking boost to
    topically relevant grey-literature items (bucket 2) over generic ones.

    Parameters
    ----------
    topic_hints : frozenset
        String values from TopicTag (e.g. frozenset({"grief", "crisis"})).
        An empty frozenset returns an empty frozenset — no boost applied.

    Returns
    -------
    frozenset[str]
        E.g. frozenset({"GriefLine", "Lifeline Australia", "Beyond Blue"})
    """
    if not topic_hints:
        return frozenset()
    seen: dict[str, DomainProfile] = {}
    for tag in topic_hints:
        for dp in _TOPIC_DOMAIN_MAP.get(tag, []):
            if dp.domain not in seen:
                seen[dp.domain] = dp
    return frozenset(dp.label for dp in seen.values())


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class WebSearchAdapter(CachedBaseAdapter):
    """
    Sanctioned-domain web search adapter with topic-aware domain routing.

    Search flow:
      1. Check disk cache (3-day TTL) — return on hit.
      2. Classify query into TopicTags using keyword matching.
      3. Select the relevant domain subset for those topics (≤ MAX_DOMAINS_PER_QUERY).
      4. Phase 1: DuckDuckGo search with site: restriction to selected domains.
         Scrape full content from matched URLs.
      5. If Phase 1 result count < MIN_SANCTIONED_RESULTS:
         Phase 2: Unrestricted DDG search. DDG snippets only (no scraping).
         External items tagged SourceTier.SECONDARY + scrutiny prefix.
      6. Merge Phase 1 + Phase 2 results, write cache, return RetrievalResult.

    All exceptions are caught and returned as RetrievalError. (REQ-200-160)
    """

    SOURCE_NAME   = "Sanctioned Web Search"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.GREY_LITERATURE
    CACHE_POLICY  = WEB_SEARCH_CACHE_POLICY

    def __init__(
        self,
        max_results: int = 10,
        scrape_timeout: int = 10,
        min_sanctioned: int = MIN_SANCTIONED_RESULTS,
    ) -> None:
        """
        Parameters
        ----------
        max_results : int
            Total maximum EvidenceItems to return (Phase 1 + Phase 2 combined).
        scrape_timeout : int
            HTTP timeout in seconds for content scraping.
        min_sanctioned : int
            Minimum sanctioned results before Phase 2 fallback triggers.
        """
        self._max_results    = max_results
        self._scrape_timeout = scrape_timeout
        self._min_sanctioned = min_sanctioned

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(
        self, params: StaticCacheQueryParams
    ) -> RetrievalResult | RetrievalError:
        """
        Execute a web search for the query and return EvidenceItems.
        All errors returned as RetrievalError — never raised. (REQ-200-160)
        """
        # ---- Cache check -----------------------------------------------
        cache_result = self._load_from_cache(params.query)
        if cache_result is not None:
            items, expires_at = cache_result
            cached = [item.model_copy(update={"cache_hit": True}) for item in items]
            return RetrievalResult(
                source_name          = self.SOURCE_NAME,
                source_tier          = self.SOURCE_TIER,
                evidence_tier        = self.EVIDENCE_TIER,
                query_echo           = params.query,
                items                = cached,
                grey_literature_flag = True,
                retrieved_at         = datetime.now(timezone.utc),
                cache_hit            = True,
                cache_expires_at     = expires_at,
            )

        now = datetime.now(timezone.utc)

        # ---- Topic-aware domain selection ------------------------------
        # [CONCEPT] Topic routing: instead of querying all 14 sanctioned
        # domains every time (which wastes DDG quota and introduces noise
        # from irrelevant domains), we first classify the query into topic
        # tags, then pick only the domains that cover those tags.  This
        # narrows the site: clause to a focused, relevant subset.
        #
        # If the pipeline's Signal→Topic bridge already classified the query
        # (via _signal_to_topic_hints in pipeline.py), we use those hints
        # directly and skip the keyword scan — avoids duplicating work the
        # Signal Agent already did.  (G-RETRIEVAL-02)
        if getattr(params, "topic_hints", None):
            detected_topics = frozenset(params.topic_hints)
            logger.debug(
                "[WebSearch] Using pre-detected topic hints from pipeline: %s",
                sorted(detected_topics),
            )
        else:
            detected_topics = self._classify_query_topics(params.query)
        selected_domains = self._select_domains_for_query(detected_topics)

        logger.info(
            "[WebSearch] Query topics: %s → %d domains selected: %s",
            [t.value for t in detected_topics],
            len(selected_domains),
            selected_domains,
        )

        # ---- Phase 1: Sanctioned domain search -------------------------
        phase1_result = self._phase1_sanctioned(
            params.query, params.max_results, selected_domains
        )
        if isinstance(phase1_result, RetrievalError):
            return phase1_result  # DDG unavailable — don't attempt Phase 2

        sanctioned_items = phase1_result
        logger.info(
            "[WebSearch] Phase 1: %d sanctioned results for '%s'",
            len(sanctioned_items), params.query,
        )

        # ---- Phase 2: External fallback (if needed) --------------------
        external_items: list[EvidenceItem] = []
        if len(sanctioned_items) < self._min_sanctioned:
            remaining = params.max_results - len(sanctioned_items)
            logger.info(
                "[WebSearch] Phase 2 triggered (sanctioned=%d < min=%d) — "
                "fetching up to %d external results.",
                len(sanctioned_items), self._min_sanctioned, remaining,
            )
            ext_result = self._phase2_external(params.query, remaining, now)
            if isinstance(ext_result, RetrievalError):
                # Phase 2 failure is non-fatal — log and continue with Phase 1 only.
                logger.warning(
                    "[WebSearch] Phase 2 failed (%s) — returning Phase 1 results only.",
                    ext_result.error_message,
                )
            else:
                external_items = ext_result

        all_items = sanctioned_items + external_items
        grey_flag = True  # all web results are grey-literature (REQ-200-ER3)

        # ---- Cache write -----------------------------------------------
        # Only cache non-empty results.  If the search returned 0 items due to
        # a transient rate-limit or API failure (ddgs returning [] instead of
        # raising an exception), we MUST NOT cache the empty result — doing so
        # would serve stale 0-item responses for the full 3-day TTL and mask
        # the underlying issue.  The next request will retry the live search.
        if not all_items:
            logger.warning(
                "[WebSearch] 0 items after Phase 1+2 for query '%s' — "
                "skipping cache write so the next request retries live search.",
                params.query[:80],
            )
            expires_at = None
        else:
            expires_at = self._save_to_cache(params.query, all_items)

        return RetrievalResult(
            source_name          = self.SOURCE_NAME,
            source_tier          = self.SOURCE_TIER,
            evidence_tier        = self.EVIDENCE_TIER,
            query_echo           = params.query,
            items                = all_items,
            grey_literature_flag = grey_flag,
            retrieved_at         = now,
            cache_hit            = False,
            cache_expires_at     = expires_at,
        )

    # ------------------------------------------------------------------
    # Topic classification
    # ------------------------------------------------------------------

    def _classify_query_topics(self, query: str) -> frozenset[TopicTag]:
        """
        Classify a query string into a frozenset of TopicTags.

        Strategy: lowercase the query and scan for each tag's keyword list.
        A tag is activated if any of its keywords appears as a substring.
        Multiple tags may fire simultaneously (e.g. a query about youth
        depression activates both YOUTH and DEPRESSION).

        Returns an empty frozenset if no keywords match — the caller then
        falls back to the default domain set.

        Why keyword matching instead of an LLM or embedding model?
        - Zero latency overhead (pure string ops).
        - Deterministic — unit-testable without mocking.
        - Avoids adding a new model dependency at retrieval time.
        - Sufficient precision for routing (false positives only broaden
          the domain set, never exclude a relevant one).
        """
        q_lower = query.lower()
        activated: set[TopicTag] = set()
        for tag, keywords in _TOPIC_KEYWORDS.items():
            if any(kw in q_lower for kw in keywords):
                activated.add(tag)
        return frozenset(activated)

    # ------------------------------------------------------------------
    # Domain selection
    # ------------------------------------------------------------------

    def _select_domains_for_query(
        self, topics: frozenset[TopicTag]
    ) -> list[str]:
        """
        Return an ordered list of sanctioned domain strings to include in
        the DDG site: clause for the given topic set.

        Algorithm:
          1. Union the DomainProfile lists for each detected topic.
          2. De-duplicate while preserving priority order (highest first).
          3. Cap at MAX_DOMAINS_PER_QUERY.
          4. If no topics detected, fall back to _DEFAULT_DOMAIN_KEYS.

        Why cap at MAX_DOMAINS_PER_QUERY?
          DuckDuckGo's site: operator with many OR clauses produces longer
          queries that can hit URL-length limits, dilute relevance signals,
          and inflate scraping latency.  Six domains is the empirically
          observed sweet spot between coverage and precision.

        Why preserve priority order when capping?
          High-priority domains (e.g. beyondblue, lifeline) have broader
          and higher-quality content.  If we must drop a domain due to the
          cap, we drop the lowest-priority one, not a random one.
        """
        if not topics:
            # No specific topic detected — use the default general-coverage set.
            logger.debug("[WebSearch] No topic detected — using default domain set.")
            return list(_DEFAULT_DOMAIN_KEYS)

        # Collect candidates from each topic bucket (already sorted by priority).
        # Use a dict to de-duplicate while preserving first-seen order
        # (which corresponds to highest priority because buckets are pre-sorted).
        seen: dict[str, DomainProfile] = {}
        for tag in topics:
            for dp in _TOPIC_DOMAIN_MAP.get(tag, []):
                if dp.domain not in seen:
                    seen[dp.domain] = dp

        # Re-sort the combined dict values by priority descending, then cap.
        sorted_profiles = sorted(seen.values(), key=lambda p: p.priority, reverse=True)
        selected = [dp.domain for dp in sorted_profiles[:MAX_DOMAINS_PER_QUERY]]

        logger.debug(
            "[WebSearch] Domain selection: topics=%s → candidates=%d → selected=%s",
            [t.value for t in topics],
            len(seen),
            selected,
        )
        return selected

    # ------------------------------------------------------------------
    # Phase 1: Sanctioned domain search
    # ------------------------------------------------------------------

    def _phase1_sanctioned(
        self,
        query: str,
        max_results: int,
        selected_domains: list[str],
    ) -> list[EvidenceItem] | RetrievalError:
        """
        Search DuckDuckGo restricted to the selected sanctioned domains
        via the site: operator.  Then scrape full content from each matched URL.

        DDG site: query format:
          (site:lifeline.org.au OR site:griefline.org.au OR ...) query_text

        [CONCEPT] DuckDuckGo site: operator restricts search results to pages
        hosted under a specific domain, exactly like Google's site: search.
        By OR-combining multiple domains, we get results from all selected
        sites in one query.  DuckDuckGo honours this without an API key.
        Passing selected_domains (a subset of SANCTIONED_DOMAINS) rather
        than the full registry is the core efficiency gain of topic routing.
        """
        if not selected_domains:
            # Safety guard — should never happen given fallback in _select_domains.
            logger.warning("[WebSearch] Phase 1: no domains selected — skipping.")
            return []

        # Build the site: clause WITHOUT outer parentheses.
        # Google Lite and Bing (the backends used by ddgs>=6 and duckduckgo_search
        # respectively) handle "site:X OR site:Y query" correctly, but the
        # parenthesised form "(site:X OR site:Y) query" can cause 0-result responses
        # because parentheses are not part of standard boolean search syntax on
        # these engines.  Removing them restores reliable results.  (Phase 6 finding)
        site_clause = " OR ".join(f"site:{d}" for d in selected_domains)
        ddg_query   = f"{site_clause} {query}"

        raw_results = self._ddg_search(ddg_query, max_results)
        if isinstance(raw_results, RetrievalError):
            return raw_results

        logger.info(
            "[WebSearch] Phase 1: DDG returned %d raw results before sanctioned filter.",
            len(raw_results),
        )

        # Filter: only keep results whose URL actually resolves to ANY sanctioned
        # domain (not just the selected subset) — a mis-routing is safer to
        # include than to discard.  The site: clause should enforce this anyway,
        # but DDG occasionally leaks a non-domain-matched result.
        now = datetime.now(timezone.utc)
        items: list[EvidenceItem] = []
        scraped = 0

        for raw in raw_results:
            if scraped >= MAX_SCRAPE_ATTEMPTS:
                break

            url    = raw.get("href", "")
            domain = self._extract_domain(url)
            if not self._is_sanctioned(domain):
                logger.debug("[WebSearch] Skipping non-sanctioned URL: %s", url)
                continue

            # Skip captcha / bot-detection pages.  DuckDuckGo occasionally routes
            # through Startpage's CAPTCHA endpoint (startpage.com/sp/captcha)
            # which returns HTTP 200 with a challenge page — not real content.
            if "/captcha" in url or "/sp/captcha" in url:
                logger.info("[WebSearch] Skipping captcha URL: %s", url)
                continue

            # Scrape content from the sanctioned URL.
            # Fall back to DDG snippet if scraping fails.
            content  = self._scrape_content(url)
            abstract = content if content else raw.get("body", "")
            if not abstract:
                abstract = "(No content retrieved)"

            items.append(EvidenceItem(
                title            = raw.get("title") or url,
                abstract         = abstract[:_MAX_ABSTRACT_CHARS],
                url              = url,
                source_name      = _DOMAIN_LABELS.get(domain, domain),
                publication_date = None,
                evidence_tier    = EvidenceTier.GREY_LITERATURE,
                source_tier      = SourceTier.PRIMARY,
                cache_hit        = False,
                retrieved_at     = now,
            ))
            scraped += 1
            if scraped < len(raw_results):
                time.sleep(_SCRAPE_DELAY)  # rate-limit scraping

        return items

    # ------------------------------------------------------------------
    # Phase 2: External fallback
    # ------------------------------------------------------------------

    def _phase2_external(
        self, query: str, max_results: int, now: datetime
    ) -> list[EvidenceItem] | RetrievalError:
        """
        Perform an unrestricted DDG search.  Uses DDG snippet only — no scraping.
        External results receive:
          - SourceTier.SECONDARY (signals Synthesizer to reduce confidence)
          - A scrutiny prefix prepended to the abstract field

        [CONCEPT] SourceTier.SECONDARY: the Synthesizer checks this field and
        SHOULD reduce its confidence score when grey-literature items come from
        secondary sources.  Combined with the _EXTERNAL_SCRUTINY_PREFIX in the
        abstract, this gives the LLM two independent signals that this content
        needs more caution. (REQ-200-ER3)
        """
        raw_results = self._ddg_search(query, max_results)
        if isinstance(raw_results, RetrievalError):
            return raw_results

        items: list[EvidenceItem] = []
        for raw in raw_results:
            url    = raw.get("href", "")
            domain = self._extract_domain(url)

            # Skip any sanctioned domain results — they belong to Phase 1.
            if self._is_sanctioned(domain):
                continue

            snippet  = raw.get("body", "") or "(No snippet)"
            abstract = f"{_EXTERNAL_SCRUTINY_PREFIX}{snippet}"

            items.append(EvidenceItem(
                title            = raw.get("title") or url,
                abstract         = abstract[:_MAX_ABSTRACT_CHARS],
                url              = url,
                source_name      = domain or "External Web",
                publication_date = None,
                evidence_tier    = EvidenceTier.GREY_LITERATURE,
                source_tier      = SourceTier.SECONDARY,
                cache_hit        = False,
                retrieved_at     = now,
            ))

        logger.debug(
            "[WebSearch] Phase 2: %d external results added.", len(items)
        )
        return items

    # ------------------------------------------------------------------
    # DuckDuckGo search
    # ------------------------------------------------------------------

    def _ddg_search(
        self, query: str, max_results: int
    ) -> list[dict] | RetrievalError:
        """
        Execute a DuckDuckGo text search via the duckduckgo-search library.

        Returns a list of dicts with keys: title, href, body.
        Returns RetrievalError on any failure.

        [CONCEPT] duckduckgo-search: a Python library that interfaces with
        DuckDuckGo's undocumented search API without requiring an API key.
        It mimics the browser search experience programmatically.  The `DDGS`
        class manages session state and handles DuckDuckGo's VQDI token
        handshake internally.  We use it in a `with` block so the HTTP session
        is properly closed after each search call.
        """
        try:
            # Import here (not at module level) so the module loads even if
            # duckduckgo-search is not installed — tests can mock _ddg_search.
            from ddgs import DDGS
        except ImportError:
            return RetrievalError(
                source_name   = self.SOURCE_NAME,
                error_code    = "dependency_missing",
                error_message = (
                    "ddgs is not installed. "
                    "Run: pip install ddgs"
                ),
                retryable     = False,
                occurred_at   = datetime.now(timezone.utc),
            )

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(
                    query,
                    max_results=max_results,
                    safesearch="moderate",
                ))
            logger.debug(
                "[WebSearch] DDG returned %d raw results for: %s",
                len(results), query[:60],
            )
            return results
        except Exception as exc:  # noqa: BLE001
            # duckduckgo-search can raise various exceptions on rate-limit,
            # network failure, or API shape change.  Catch all and wrap.
            return RetrievalError(
                source_name   = self.SOURCE_NAME,
                error_code    = "search_error",
                error_message = f"DuckDuckGo search failed: {exc}",
                retryable     = True,
                occurred_at   = datetime.now(timezone.utc),
            )

    # ------------------------------------------------------------------
    # Content scraping (sanctioned URLs only)
    # ------------------------------------------------------------------

    def _scrape_content(self, url: str) -> Optional[str]:
        """
        Fetch a URL and extract the main article body text.

        Uses a generic content extraction heuristic:
          1. Find <main>, <article>, or <div role="main"> — semantic markup
          2. Fall back to <div class="content|main|article|body"> — class naming
          3. Fall back to <body> as last resort
          4. Extract all text nodes, join, truncate.

        Returns None on any network or parse failure (caller falls back to
        DDG snippet).

        Security note: only called for URLs on SANCTIONED_DOMAINS.  Never
        called for external URLs (Phase 2 uses DDG snippets only).
        (G-RETRIEVAL-01)
        """
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning(
                "[WebSearch] beautifulsoup4 or requests not installed — "
                "falling back to DDG snippet. Run: pip install beautifulsoup4 lxml"
            )
            return None

        try:
            resp = requests.get(
                url,
                timeout=self._scrape_timeout,
                headers={"User-Agent": _USER_AGENT},
                allow_redirects=True,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[WebSearch] Scrape request failed for %s: %s", url, exc)
            return None

        # Detect captcha / bot-challenge pages that return HTTP 200 but no
        # content.  The final URL after redirects is the real indicator.
        final_url = resp.url if hasattr(resp, "url") else url
        if "/captcha" in str(final_url):
            logger.info(
                "[WebSearch] Captcha page detected after redirect — discarding %s", url
            )
            return None

        try:
            soup = BeautifulSoup(resp.content, "lxml")

            # Remove boilerplate elements that add noise to extracted text.
            for tag in soup(["script", "style", "nav", "header", "footer",
                             "aside", "form", "button", "noscript"]):
                tag.decompose()

            # Attempt semantic content extraction in priority order.
            # [CONCEPT] Semantic HTML elements: <main> and <article> are HTML5
            # landmarks that page authors use to identify the primary content
            # region.  They're more reliable than class-based guessing.
            container = (
                soup.find("main") or
                soup.find("article") or
                soup.find(attrs={"role": "main"}) or
                soup.find("div", class_=re.compile(
                    r"\b(content|main|article|body|page-content)\b", re.I
                )) or
                soup.find("body")
            )

            if container is None:
                return None

            # Extract text, normalise whitespace.
            text = " ".join(container.stripped_strings)
            text = re.sub(r"\s{2,}", " ", text).strip()

            if len(text) < 50:
                # Too short — probably a JS-rendered page where content didn't load.
                logger.debug(
                    "[WebSearch] Scraped content too short (%d chars) for %s",
                    len(text), url,
                )
                return None

            return text

        except Exception as exc:  # noqa: BLE001
            logger.debug("[WebSearch] Parse failed for %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(url: str) -> str:
        """
        Extract the registered domain from a URL.
        Returns the netloc with 'www.' stripped.
        Example: 'https://www.beyondblue.org.au/...' → 'beyondblue.org.au'
        """
        try:
            netloc = urlparse(url).netloc.lower()
            return netloc.removeprefix("www.")
        except Exception:  # noqa: BLE001
            return ""

    @classmethod
    def _is_sanctioned(cls, domain: str) -> bool:
        """
        Return True if domain matches any entry in SANCTIONED_DOMAINS.
        Handles both exact match and subdomains (e.g. 'content.who.int').

        Note: this check runs against ALL sanctioned domains, not just the
        selected subset — a URL from a non-selected but valid sanctioned
        domain is still kept, just not actively searched for.
        """
        return any(
            domain == s or domain.endswith(f".{s}")
            for s in SANCTIONED_DOMAINS
        )

    def is_cache_valid(self, entry: EvidenceItem) -> bool:
        """Delegate to CachedBaseAdapter TTL logic. (REQ-200-ER5)"""
        return super().is_cache_valid(entry)
