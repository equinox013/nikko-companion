"""
docs/schemas/retrieval_schemas.py
===================================
Typed I/O contracts and function signatures for all four evidence retrieval
adapter classes used by the Evidence Retrieval Agent.

Spec source : SPEC-200 §5.4
Requirements: REQ-200-070, REQ-200-071, REQ-200-ER1 through REQ-200-ER5
Gap resolved: G-EVIDENCE-02
Status      : Phase 2 — Architectural Contracts (no implementation code)
Last reviewed: 2026-05-09

v0 Retrieval stack (REQ-200-ER4)
---------------------------------
  1. PubMedAdapter          — PubMed E-utilities API (primary, peer-reviewed)
  2. HealthdirectAdapter    — Healthdirect Australia Search API (primary, grey-lit)
  3. BetterHealthAdapter    — Better Health Channel curated static cache (primary, grey-lit)
  4. WHOAdapter             — WHO articles curated static cache (primary, grey-lit)

Secondary fallbacks (NHS, CDC, Mayo Clinic) are NOT implemented in v0.
They are enumerated in REQ-200-071 for GA-phase implementation.

Naming convention
-----------------
All adapter classes are named <Source>Adapter and inherit from BaseRetrievalAdapter.
All query param models are named <Source>QueryParams.
All result models re-use EvidenceItem from acp_schemas.py.

Cache TTLs (REQ-200-ER5)
-------------------------
  PubMed        : 7 days
  Healthdirect  : 30 days + weekly HTTP HEAD check
  Better Health : 30 days + weekly HTTP HEAD check
  WHO           : 30 days + weekly HTTP HEAD check
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# Import shared types from ACP schemas.
# Phase 3 note: keep this import; do not redefine EvidenceItem locally.
from docs.schemas.acp_schemas import EvidenceItem, EvidenceTier, SourceTier


# ---------------------------------------------------------------------------
# Cache metadata
# ---------------------------------------------------------------------------

class CachePolicy(BaseModel):
    """
    Cache TTL and invalidation rules per source. (REQ-200-ER5)
    Attached to each adapter class as a class-level constant.
    """
    ttl_days:            int
    head_check_interval: Optional[timedelta] = Field(
        default=None,
        description=(
            "Interval between HTTP HEAD checks for content change detection. "
            "None for static caches with TTL-only invalidation."
        ),
    )
    invalidation_triggers: list[str] = Field(
        default_factory=lambda: ["ttl_expiry", "director_manual_purge"],
        description="Events that trigger cache invalidation. (REQ-200-ER5)",
    )


PUBMED_CACHE_POLICY = CachePolicy(
    ttl_days=7,
    head_check_interval=None,  # PubMed uses TTL-only; no HEAD check
    invalidation_triggers=["ttl_expiry", "director_manual_purge"],
)

# SUPERSEDED 2026-05-10 — Director-directed change G-RETRIEVAL-01.
# HealthdirectAdapter, BetterHealthAdapter, WHOAdapter have been replaced by
# WebSearchAdapter. These CachePolicy constants are retained for audit trail
# but are no longer referenced by any active adapter.
HEALTHDIRECT_CACHE_POLICY = CachePolicy(
    ttl_days=30,
    head_check_interval=timedelta(weeks=1),
    invalidation_triggers=["ttl_expiry", "head_check_change", "director_manual_purge"],
)

BETTER_HEALTH_CACHE_POLICY = CachePolicy(
    ttl_days=30,
    head_check_interval=timedelta(weeks=1),
    invalidation_triggers=["ttl_expiry", "head_check_change", "director_manual_purge"],
)

WHO_CACHE_POLICY = CachePolicy(
    ttl_days=30,
    head_check_interval=timedelta(weeks=1),
    invalidation_triggers=["ttl_expiry", "head_check_change", "director_manual_purge"],
)

# Active replacement policy (G-RETRIEVAL-01).
# Web search results are cached for 3 days — shorter than the old static-corpus
# TTLs because live web content changes more frequently than curated corpora.
WEB_SEARCH_CACHE_POLICY = CachePolicy(
    ttl_days=3,
    head_check_interval=None,   # DDG snippet results don't support HEAD checks
    invalidation_triggers=["ttl_expiry", "director_manual_purge"],
)


# ---------------------------------------------------------------------------
# Article type filter (PubMed-specific)
# ---------------------------------------------------------------------------

class PubMedArticleType(str, Enum):
    """
    PubMed publication type filters. These map to PubMed E-utilities
    'ptyp' values and prioritize high-quality evidence.
    Default set prioritizes systematic reviews and meta-analyses first.
    """
    META_ANALYSIS        = "Meta-Analysis"
    SYSTEMATIC_REVIEW    = "Systematic Review"
    RANDOMIZED_TRIAL     = "Randomized Controlled Trial"
    CLINICAL_TRIAL       = "Clinical Trial"
    REVIEW               = "Review"
    PRACTICE_GUIDELINE   = "Practice Guideline"


# ---------------------------------------------------------------------------
# Query parameter models
# ---------------------------------------------------------------------------

class PubMedQueryParams(BaseModel):
    """
    Input parameters for a PubMed E-utilities search query.
    Maps to the ESearch + EFetch endpoint pair.

    Rate limiting: NCBI allows 3 requests/sec without API key;
    10 requests/sec with API key. Phase 3 MUST review and document
    the key registration process before implementation. (REQ-200-ER4)
    """
    query:          str = Field(
        description="Free-text search query. Will be submitted to PubMed /esearch.fcgi.",
    )
    max_results:    int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of articles to retrieve. Capped at 20 to control latency.",
    )
    date_from:      Optional[date] = Field(
        default=None,
        description=(
            "Earliest publication date filter (inclusive). "
            "Per REQ-200-ER1, prefer sources within the last 5 years."
        ),
    )
    date_to:        Optional[date] = Field(
        default=None,
        description="Latest publication date filter (inclusive). Defaults to today.",
    )
    article_types:  list[PubMedArticleType] = Field(
        default=[
            PubMedArticleType.META_ANALYSIS,
            PubMedArticleType.SYSTEMATIC_REVIEW,
            PubMedArticleType.RANDOMIZED_TRIAL,
            PubMedArticleType.REVIEW,
        ],
        description="Publication type filter. Defaults to high-quality evidence types.",
    )
    open_access_only: bool = Field(
        default=True,
        description=(
            "When True, restricts results to PubMed Central Open Access subset. "
            "Required for full-text access without institutional subscription."
        ),
    )


class HealthdirectQueryParams(BaseModel):
    """
    Input parameters for a Healthdirect Australia Search API query.
    API documentation: https://www.healthdirect.gov.au/api-docs

    Rate limiting: subject to Healthdirect API terms. Phase 3 MUST
    review Healthdirect's API ToS before implementation. (REQ-200-ER4)
    """
    query:        str = Field(
        description="Free-text search query for Healthdirect content.",
    )
    max_results:  int = Field(
        default=5,
        ge=1,
        le=10,
    )
    content_type: Optional[str] = Field(
        default=None,
        description=(
            "Optional Healthdirect content type filter (e.g., 'health-topic', "
            "'condition'). None returns all content types."
        ),
    )


class StaticCacheQueryParams(BaseModel):
    """
    Input parameters for static-cache adapters (Better Health Channel, WHO).
    These sources do not expose a live search API in v0 — the adapter searches
    against a curated pre-loaded article index. (REQ-200-ER4)

    The curated article index must be assembled manually before Phase 3
    and stored in the format defined by StaticCacheIndex below.
    """
    query:       str = Field(
        description=(
            "Free-text query. Matched against the curated article index using "
            "keyword or semantic similarity depending on Phase 3 implementation."
        ),
    )
    max_results: int = Field(default=5, ge=1, le=10)


# ---------------------------------------------------------------------------
# Result and error models
# ---------------------------------------------------------------------------

class RetrievalResult(BaseModel):
    """
    Structured output of a single adapter query.
    Consumed by the Evidence Retrieval Agent to build EvidencePayload.
    """
    source_name:          str
    source_tier:          SourceTier
    evidence_tier:        EvidenceTier
    query_echo:           str                   # the query as submitted to the source
    items:                list[EvidenceItem]
    grey_literature_flag: bool = Field(
        default=False,
        description="True when source is grey-literature (non-peer-reviewed).",
    )
    retrieved_at:         datetime
    cache_hit:            bool = False
    cache_expires_at:     Optional[datetime] = None


class RetrievalError(BaseModel):
    """
    Structured error from an adapter, replacing raised exceptions in the
    inter-agent contract. The Evidence Retrieval Agent MUST handle these
    and attempt the next source in priority order before failing the pipeline.
    (REQ-200-160 — failure handling)
    """
    source_name:    str
    error_code:     str   # e.g., "rate_limit", "timeout", "empty_result", "parse_error"
    error_message:  str
    retryable:      bool
    occurred_at:    datetime


class StaticCacheEntry(BaseModel):
    """
    A single article entry in the pre-loaded static cache used by
    BetterHealthAdapter and WHOAdapter.
    Phase 3 implementers: the curated cache MUST be populated before
    any integration test runs against these adapters. (REQ-200-ER4)
    """
    title:            str
    url:              str
    source_name:      str
    body_markdown:    str   # article body for keyword indexing
    last_fetched:     date
    cache_expires_at: date
    keywords:         list[str] = Field(default_factory=list)


class StaticCacheIndex(BaseModel):
    """
    The complete pre-loaded article index for a static-cache source.
    Stored as a JSON file, one per source (better_health_cache.json, who_cache.json).
    """
    source_name:  str
    last_updated: date
    entries:      list[StaticCacheEntry]


# ---------------------------------------------------------------------------
# Abstract base adapter
# ---------------------------------------------------------------------------

class BaseRetrievalAdapter(ABC):
    """
    Contract all retrieval adapters must fulfil.
    Phase 3 implementers: subclass this, implement search(), and register
    the adapter in the Evidence Retrieval Agent's source priority list.
    (REQ-200-071 ordering must be respected at runtime.)

    The adapter MUST NOT interpret signals or influence routing. (REQ-200-073)
    """

    SOURCE_NAME:   str        = NotImplemented
    SOURCE_TIER:   SourceTier = NotImplemented
    EVIDENCE_TIER: EvidenceTier = NotImplemented
    CACHE_POLICY:  CachePolicy  = NotImplemented

    @abstractmethod
    def search(self, params: BaseModel) -> RetrievalResult | RetrievalError:
        """
        Execute a search against this adapter's source.

        Returns RetrievalResult on success (including empty results),
        RetrievalError on failure.

        MUST NOT raise exceptions — all errors MUST be returned as
        RetrievalError to preserve the structured pipeline contract.
        (REQ-200-037 — malformed outputs must be logged and handled)
        """
        ...

    @abstractmethod
    def is_cache_valid(self, entry: EvidenceItem) -> bool:
        """
        Return True if the cached item is still within its TTL and
        has not been invalidated by a HEAD check. (REQ-200-ER5)
        """
        ...


# ---------------------------------------------------------------------------
# Concrete adapter signatures (no implementation — contracts only)
# ---------------------------------------------------------------------------

class PubMedAdapter(BaseRetrievalAdapter):
    """
    PubMed E-utilities adapter. Primary peer-reviewed source.
    Priority: 1 (highest) in the Evidence Retrieval Agent source list.
    (REQ-200-071)

    API surface used in v0:
      ESearch: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
      EFetch:  https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi

    Phase 3 notes:
    - Register an NCBI API key to raise rate limit to 10 req/sec.
    - Prefer the PMC Open Access subset (open_access_only=True in params).
    - Parse PubMed XML into EvidenceItem. Abstract may be absent; log if so.
    - Cache TTL: 7 days (PUBMED_CACHE_POLICY).
    """

    SOURCE_NAME   = "PubMed Central Open Access"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.PEER_REVIEWED
    CACHE_POLICY  = PUBMED_CACHE_POLICY

    def search(self, params: PubMedQueryParams) -> RetrievalResult | RetrievalError: ...
    def is_cache_valid(self, entry: EvidenceItem) -> bool: ...


class HealthdirectAdapter(BaseRetrievalAdapter):
    """
    Healthdirect Australia Search API adapter. Primary grey-literature source.
    Priority: 2 in the Evidence Retrieval Agent source list. (REQ-200-071)

    Phase 3 notes:
    - Review Healthdirect API ToS before implementation. (REQ-200-ER4)
    - Content is authoritative Australian health information — not peer-reviewed.
      EvidenceTier must always be set to GREY_LITERATURE.
    - Cache TTL: 30 days + weekly HEAD check (HEALTHDIRECT_CACHE_POLICY).
    """

    SOURCE_NAME   = "Healthdirect Australia"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.GREY_LITERATURE
    CACHE_POLICY  = HEALTHDIRECT_CACHE_POLICY

    def search(self, params: HealthdirectQueryParams) -> RetrievalResult | RetrievalError: ...
    def is_cache_valid(self, entry: EvidenceItem) -> bool: ...


class BetterHealthAdapter(BaseRetrievalAdapter):
    """
    Better Health Channel (Victoria, AU) static cache adapter.
    Primary grey-literature source. Priority: 3 in the Evidence Retrieval
    Agent source list. (REQ-200-071)

    Phase 3 notes:
    - No live API in v0. Search operates against a pre-loaded StaticCacheIndex.
    - Cache index file: docs/schemas/better_health_cache.json (to be created in Phase 3).
    - Review BHC content licensing and scraping terms before building the index.
      (REQ-200-ER4)
    - Cache TTL: 30 days + weekly HEAD check (BETTER_HEALTH_CACHE_POLICY).
    """

    SOURCE_NAME   = "Better Health Channel"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.GREY_LITERATURE
    CACHE_POLICY  = BETTER_HEALTH_CACHE_POLICY

    def search(self, params: StaticCacheQueryParams) -> RetrievalResult | RetrievalError: ...
    def is_cache_valid(self, entry: EvidenceItem) -> bool: ...


# SUPERSEDED 2026-05-10 (G-RETRIEVAL-01) — replaced by WebSearchAdapter below.
class WHOAdapter(BaseRetrievalAdapter):
    """
    SUPERSEDED — Director-directed change 2026-05-10 (G-RETRIEVAL-01).
    who.int is now one of five sanctioned domains in WebSearchAdapter.
    This stub is retained for schema audit trail only.
    """
    SOURCE_NAME   = "World Health Organization"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.GREY_LITERATURE
    CACHE_POLICY  = WHO_CACHE_POLICY

    def search(self, params: StaticCacheQueryParams) -> RetrievalResult | RetrievalError: ...
    def is_cache_valid(self, entry: EvidenceItem) -> bool: ...


class WebSearchAdapter(BaseRetrievalAdapter):
    """
    General web search adapter restricted to sanctioned health domains.
    Replaces HealthdirectAdapter, BetterHealthAdapter, WHOAdapter.
    (G-RETRIEVAL-01 — Director-directed architectural change 2026-05-10)

    Priority: 2 in ADAPTER_PRIORITY_ORDER (immediately after PubMed).

    Sanctioned domains (searched first, via DuckDuckGo site: operator):
      1. healthdirect.gov.au        — Australian Government health information
      2. betterhealth.vic.gov.au    — Better Health Channel (Victoria, AU)
      3. who.int                    — World Health Organization
      4. beyondblue.org.au          — Beyond Blue (AU mental health charity)
      5. blackdoginstitute.org.au   — Black Dog Institute (AU mental health research)

    Fallback: if sanctioned results < MIN_SANCTIONED_RESULTS, broadens search
    to general web. External results are tagged SourceTier.SECONDARY and carry
    a scrutiny warning in their abstract field. (Director ruling 2026-05-10)

    Phase 3 implementation: retrieval/web_search_adapter.py
    Search backend: duckduckgo-search (PyPI, no API key required)
    Content extraction: requests + BeautifulSoup4 (sanctioned URLs only)
    Cache TTL: 3 days (WEB_SEARCH_CACHE_POLICY)
    """
    SOURCE_NAME   = "Sanctioned Web Search"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.GREY_LITERATURE
    CACHE_POLICY  = WEB_SEARCH_CACHE_POLICY

    def search(self, params: StaticCacheQueryParams) -> RetrievalResult | RetrievalError: ...
    def is_cache_valid(self, entry: EvidenceItem) -> bool: ...


# ---------------------------------------------------------------------------
# Priority-ordered adapter registry (runtime reference for Phase 3)
# ---------------------------------------------------------------------------

ADAPTER_PRIORITY_ORDER: list[type[BaseRetrievalAdapter]] = [
    PubMedAdapter,      # Priority 1 — peer-reviewed, live NCBI E-utilities API
    WebSearchAdapter,   # Priority 2 — grey-lit, sanctioned web + external fallback
    # (G-RETRIEVAL-01: HealthdirectAdapter, BetterHealthAdapter, WHOAdapter superseded)
    # NHS, CDC, Mayo Clinic — secondary fallbacks, Phase 4+ if required
]
"""
Ordered list of adapter classes for the Evidence Retrieval Agent.
Updated 2026-05-10 per Director ruling (G-RETRIEVAL-01).
The agent MUST query adapters in this order. (REQ-200-071)
"""
