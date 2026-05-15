"""
retrieval/web_search_adapter.py
================================
WebSearchAdapter — sanctioned-domain web search + content scraping.

Spec source  : SPEC-200 §5.4, REQ-200-071, REQ-200-ER1 through ER5
               REQ-200-160 (error handling)
Phase        : 3 — Agent Definitions (Implementation)
Priority     : 2 in ADAPTER_PRIORITY_ORDER (after PubMed)
Gap ref      : G-RETRIEVAL-01 — Director-directed change 2026-05-10

Replaces
--------
HealthdirectAdapter, BetterHealthAdapter, WHOAdapter (all superseded).
Adds Beyond Blue and Black Dog Institute (not in original spec — Director ruling).

Architecture
------------
Two-phase search per query:

  Phase 1 — Sanctioned domain search
    Uses duckduckgo-search library to query DuckDuckGo with a combined
    site: operator restriction across all five approved domains.
    For each matched URL that falls on a sanctioned domain, the adapter
    fetches and parses the full page via requests + BeautifulSoup to extract
    the main article body (not just the DDG snippet).

    Sanctioned domains:
      1. healthdirect.gov.au        — Australian Government health information
      2. betterhealth.vic.gov.au    — Better Health Channel (Victoria, AU)
      3. who.int                    — World Health Organization
      4. beyondblue.org.au          — Beyond Blue (AU mental health NGO)
      5. blackdoginstitute.org.au   — Black Dog Institute (AU mental health research)

  Phase 2 — External fallback (higher scrutiny)
    Triggered ONLY when Phase 1 returns fewer than MIN_SANCTIONED_RESULTS items.
    Performs a plain DDG search without domain restriction. External results:
      - Are NOT scraped (only DDG snippet is used as abstract)
      - Are tagged SourceTier.SECONDARY (vs PRIMARY for sanctioned)
      - Have a "[EXTERNAL — HIGHER SCRUTINY REQUIRED]" prefix injected into abstract
      - Are appended after any Phase 1 results

    The Synthesizer uses SourceTier.SECONDARY to reduce confidence per REQ-200-ER3.

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
  hammering sanctioned domains. Each search call scrapes at most
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
from datetime import datetime, timezone
from typing import Optional
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
# Constants
# ---------------------------------------------------------------------------

# Approved domains queried in Phase 1.
# These are the ONLY domains whose content is actively scraped.
SANCTIONED_DOMAINS: list[str] = [
    "healthdirect.gov.au",
    "betterhealth.vic.gov.au",
    "who.int",
    "beyondblue.org.au",
    "blackdoginstitute.org.au",
]

# Human-readable labels for each sanctioned domain (used as source_name on items).
_DOMAIN_LABELS: dict[str, str] = {
    "healthdirect.gov.au":     "Healthdirect Australia",
    "betterhealth.vic.gov.au": "Better Health Channel",
    "who.int":                 "World Health Organization",
    "beyondblue.org.au":       "Beyond Blue",
    "blackdoginstitute.org.au":"Black Dog Institute",
}

# If Phase 1 returns fewer than this many sanctioned results, trigger Phase 2.
MIN_SANCTIONED_RESULTS: int = 2

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
_USER_AGENT = "NIKKO-Research-Bot/1.0 (mental health evidence retrieval; contact: nikko-research@example.com)"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class WebSearchAdapter(CachedBaseAdapter):
    """
    Sanctioned-domain web search adapter.

    Search flow:
      1. Check disk cache (3-day TTL) — return on hit.
      2. Phase 1: DuckDuckGo search with site: restriction to SANCTIONED_DOMAINS.
         Scrape full content from matched URLs.
      3. If Phase 1 result count < MIN_SANCTIONED_RESULTS:
         Phase 2: Unrestricted DDG search. DDG snippets only (no scraping).
         External items tagged SourceTier.SECONDARY + scrutiny prefix.
      4. Merge Phase 1 + Phase 2 results, write cache, return RetrievalResult.

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

        # ---- Phase 1: Sanctioned domain search -------------------------
        phase1_result = self._phase1_sanctioned(params.query, params.max_results)
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
    # Phase 1: Sanctioned domain search
    # ------------------------------------------------------------------

    def _phase1_sanctioned(
        self, query: str, max_results: int
    ) -> list[EvidenceItem] | RetrievalError:
        """
        Search DuckDuckGo restricted to sanctioned domains via site: operator.
        Then scrape full content from each matched URL.

        DDG site: query format:
          (site:healthdirect.gov.au OR site:betterhealth.vic.gov.au OR ...) query_text

        [CONCEPT] DuckDuckGo site: operator restricts search results to pages
        hosted under a specific domain, exactly like Google's site: search.
        By OR-combining multiple domains, we get results from all sanctioned
        sites in one query. DuckDuckGo honours this without an API key.
        """
        site_clause = " OR ".join(f"site:{d}" for d in SANCTIONED_DOMAINS)
        ddg_query   = f"({site_clause}) {query}"

        raw_results = self._ddg_search(ddg_query, max_results)
        if isinstance(raw_results, RetrievalError):
            return raw_results

        # Filter: only keep results whose URL actually resolves to a sanctioned domain.
        # DDG may occasionally return a result that passed the site: filter loosely.
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

            # Skip captcha / bot-detection pages. DuckDuckGo occasionally routes
            # through Startpage's CAPTCHA endpoint (startpage.com/sp/captcha) which
            # returns HTTP 200 with a challenge page — not real content. Counting
            # these as results inflates Phase 1 counts and prevents Phase 2 fallback.
            if "/captcha" in url or "/sp/captcha" in url:
                logger.info("[WebSearch] Skipping captcha URL: %s", url)
                continue

            # Scrape content from the sanctioned URL.
            # Fall back to DDG snippet if scraping fails.
            content = self._scrape_content(url)
            abstract = content if content else raw.get("body", "")
            if not abstract:
                abstract = "(No content retrieved)"

            items.append(EvidenceItem(
                title            = raw.get("title") or url,
                abstract         = abstract[:_MAX_ABSTRACT_CHARS],
                url              = url,
                source_name      = _DOMAIN_LABELS.get(domain, domain),
                publication_date = None,   # not reliably extractable from arbitrary pages
                evidence_tier    = EvidenceTier.GREY_LITERATURE,
                source_tier      = SourceTier.PRIMARY,   # sanctioned = primary
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
        Perform an unrestricted DDG search. Uses DDG snippet only — no scraping.
        External results receive:
          - SourceTier.SECONDARY (signals Synthesizer to reduce confidence)
          - A scrutiny prefix prepended to the abstract field

        [CONCEPT] SourceTier.SECONDARY: the Synthesizer checks this field and
        SHOULD reduce its confidence score when grey-literature items come from
        secondary sources. Combined with the _EXTERNAL_SCRUTINY_PREFIX in the
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
                source_tier      = SourceTier.SECONDARY,   # ← key scrutiny signal
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
        It mimics the browser search experience programmatically. The `DDGS`
        class manages session state and handles DuckDuckGo's VQDI token
        handshake internally. We use it in a `with` block so the HTTP session
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
            # network failure, or API shape change. Catch all and wrap.
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

        Returns None on any network or parse failure (caller falls back to DDG snippet).

        Security note: only called for URLs on SANCTIONED_DOMAINS. Never called
        for external URLs (Phase 2 uses DDG snippets only). (G-RETRIEVAL-01)
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

        # Detect captcha / bot-challenge pages that return HTTP 200 but no content.
        # Startpage (used by DDG as a proxy) redirects to /sp/captcha on bot detection.
        # The final URL after redirects is the real indicator.
        final_url = resp.url if hasattr(resp, "url") else url
        if "/captcha" in str(final_url):
            logger.info("[WebSearch] Captcha page detected after redirect — discarding %s", url)
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
            # region. They're more reliable than class-based guessing.
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
        Handles both exact match and subdomains (e.g., 'content.who.int').
        """
        return any(
            domain == s or domain.endswith(f".{s}")
            for s in SANCTIONED_DOMAINS
        )

    def is_cache_valid(self, entry: EvidenceItem) -> bool:
        """Delegate to CachedBaseAdapter TTL logic. (REQ-200-ER5)"""
        return super().is_cache_valid(entry)
