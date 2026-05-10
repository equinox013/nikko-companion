"""
retrieval/pubmed_adapter.py
===========================
PubMed E-utilities adapter — primary peer-reviewed evidence source.

Spec source  : SPEC-200 §5.4, REQ-200-070, REQ-200-071, REQ-200-ER1 through ER5,
               REQ-200-160
Phase        : 3 — Agent Definitions (Implementation)
Priority     : 1 (highest) in ADAPTER_PRIORITY_ORDER (REQ-200-071)

API surface used in v0
----------------------
  ESearch : GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
            → returns list of PubMed IDs (PMIDs) matching the query
  EFetch  : GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
            → returns PubMed XML for a list of PMIDs

Both calls use `retmode=json` for ESearch and `rettype=abstract&retmode=xml`
for EFetch. The XML route is chosen for EFetch because the JSON efetch endpoint
does not include structured abstract text.

Rate limits (NCBI policy — REQ-200-ER4)
-----------------------------------------
Without API key : 3 requests / second
With API key    : 10 requests / second
The adapter enforces a 340 ms inter-request delay (≈ 2.9 req/s, safely under
the unauthenticated cap). Set NCBI_API_KEY in your environment or pass it to
__init__ to raise the cap. Register at: https://www.ncbi.nlm.nih.gov/account/

PubMed URL format: https://pubmed.ncbi.nlm.nih.gov/{pmid}/
"""

from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import requests

from docs.schemas.acp_schemas import EvidenceItem, EvidenceTier, SourceTier
from docs.schemas.retrieval_schemas import (
    PUBMED_CACHE_POLICY,
    PubMedArticleType,
    PubMedQueryParams,
    RetrievalError,
    RetrievalResult,
)
from retrieval.base_adapter import CachedBaseAdapter

logger = logging.getLogger(__name__)

# NCBI E-utilities base URL.
_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Minimum delay between consecutive NCBI API calls (seconds).
# 0.34 s → ~2.94 req/s, safely under the 3/s unauthenticated limit.
_MIN_REQUEST_INTERVAL = 0.34

# PubMed publication type → PubMed ptyp filter string mapping.
# These are the [Publication Type] MeSH filter values recognised by NCBI.
_ARTICLE_TYPE_FILTERS: dict[PubMedArticleType, str] = {
    PubMedArticleType.META_ANALYSIS:      "Meta-Analysis[ptyp]",
    PubMedArticleType.SYSTEMATIC_REVIEW:  "Systematic Review[ptyp]",
    PubMedArticleType.RANDOMIZED_TRIAL:   "Randomized Controlled Trial[ptyp]",
    PubMedArticleType.CLINICAL_TRIAL:     "Clinical Trial[ptyp]",
    PubMedArticleType.REVIEW:             "Review[ptyp]",
    PubMedArticleType.PRACTICE_GUIDELINE: "Practice Guideline[ptyp]",
}

# Open-access filter clause for PMC Full Text.
_OA_FILTER = "free full text[filter]"


class PubMedAdapter(CachedBaseAdapter):
    """
    Retrieves peer-reviewed evidence from PubMed E-utilities.

    Two-call sequence per search:
      1. ESearch → list of PMIDs matching the query + filters
      2. EFetch  → PubMed XML for those PMIDs → parsed into EvidenceItem list

    The result is cached to disk for 7 days (PUBMED_CACHE_POLICY). On cache
    hit the ESearch + EFetch calls are skipped entirely.

    All errors are returned as RetrievalError — this adapter never raises.
    (REQ-200-160)
    """

    SOURCE_NAME   = "PubMed Central Open Access"
    SOURCE_TIER   = SourceTier.PRIMARY
    EVIDENCE_TIER = EvidenceTier.PEER_REVIEWED
    CACHE_POLICY  = PUBMED_CACHE_POLICY

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 10,
    ) -> None:
        """
        Parameters
        ----------
        api_key : str, optional
            NCBI API key. If None, falls back to the NCBI_API_KEY env var,
            then to unauthenticated (3 req/s limit). Register at
            https://www.ncbi.nlm.nih.gov/account/
        timeout : int
            HTTP request timeout in seconds.
        """
        self._api_key = api_key or os.getenv("NCBI_API_KEY")
        self._timeout = timeout
        # Track time of last NCBI call for rate limiting.
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(self, params: PubMedQueryParams) -> RetrievalResult | RetrievalError:
        """
        Execute a PubMed search and return structured evidence items.

        Steps:
          1. Check disk cache → return cached items if valid
          2. Build ESearch query string with date/type/OA filters
          3. ESearch → get PMIDs
          4. EFetch   → get PubMed XML for those PMIDs
          5. Parse XML → EvidenceItem list
          6. Write result to cache
          7. Return RetrievalResult

        All HTTP or parse failures produce a RetrievalError, not an exception.
        (REQ-200-160)
        """
        # ---- 1. Cache check -------------------------------------------
        cache_result = self._load_from_cache(params.query)
        if cache_result is not None:
            items, expires_at = cache_result
            # Mark all items as cache hits.
            cached_items = [item.model_copy(update={"cache_hit": True}) for item in items]
            return RetrievalResult(
                source_name          = self.SOURCE_NAME,
                source_tier          = self.SOURCE_TIER,
                evidence_tier        = self.EVIDENCE_TIER,
                query_echo           = params.query,
                items                = cached_items,
                grey_literature_flag = False,
                retrieved_at         = datetime.now(timezone.utc),
                cache_hit            = True,
                cache_expires_at     = expires_at,
            )

        # ---- 2. Build search query ------------------------------------
        esearch_query = self._build_query(params)

        # ---- 3. ESearch → PMIDs ----------------------------------------
        pmid_result = self._esearch(esearch_query, params.max_results)
        if isinstance(pmid_result, RetrievalError):
            return pmid_result

        pmids = pmid_result
        if not pmids:
            # ESearch returned no results — valid empty response, not an error.
            logger.info("[PubMed] ESearch returned 0 results for: %s", params.query)
            return RetrievalResult(
                source_name          = self.SOURCE_NAME,
                source_tier          = self.SOURCE_TIER,
                evidence_tier        = self.EVIDENCE_TIER,
                query_echo           = params.query,
                items                = [],
                grey_literature_flag = False,
                retrieved_at         = datetime.now(timezone.utc),
                cache_hit            = False,
            )

        # ---- 4. EFetch → XML -------------------------------------------
        xml_result = self._efetch(pmids)
        if isinstance(xml_result, RetrievalError):
            return xml_result

        # ---- 5. Parse XML → EvidenceItem list --------------------------
        now = datetime.now(timezone.utc)
        try:
            items = self._parse_pubmed_xml(xml_result, now)
        except Exception as exc:  # noqa: BLE001
            return RetrievalError(
                source_name   = self.SOURCE_NAME,
                error_code    = "parse_error",
                error_message = f"PubMed XML parse failed: {exc}",
                retryable     = False,
                occurred_at   = datetime.now(timezone.utc),
            )

        # ---- 6. Write cache -------------------------------------------
        expires_at = self._save_to_cache(params.query, items)

        # ---- 7. Return result -----------------------------------------
        return RetrievalResult(
            source_name          = self.SOURCE_NAME,
            source_tier          = self.SOURCE_TIER,
            evidence_tier        = self.EVIDENCE_TIER,
            query_echo           = params.query,
            items                = items,
            grey_literature_flag = False,
            retrieved_at         = now,
            cache_hit            = False,
            cache_expires_at     = expires_at,
        )

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------

    def _build_query(self, params: PubMedQueryParams) -> str:
        """
        Construct the full PubMed query string from PubMedQueryParams.

        Anatomy of the query:
          ({user_terms}) AND ({ptyp filters OR'd together}) [AND date range] [AND OA filter]

        Publication types are OR'd so results include any of the requested
        high-evidence types (e.g., meta-analysis OR systematic review).
        """
        parts: list[str] = [f"({params.query})"]

        # Publication type filter — OR all requested types.
        if params.article_types:
            ptyp_clause = " OR ".join(
                _ARTICLE_TYPE_FILTERS[at]
                for at in params.article_types
                if at in _ARTICLE_TYPE_FILTERS
            )
            if ptyp_clause:
                parts.append(f"({ptyp_clause})")

        # Date range filter. REQ-200-ER1: prefer sources within the last 5 years.
        # Represented as PubMed's PDAT (publication date) field.
        if params.date_from:
            parts.append(f"{params.date_from.strftime('%Y/%m/%d')}:{params.date_to.strftime('%Y/%m/%d') if params.date_to else '3000'}[PDAT]")

        # Open-access filter restricts to PMC Open Access subset.
        if params.open_access_only:
            parts.append(_OA_FILTER)

        return " AND ".join(parts)

    # ------------------------------------------------------------------
    # HTTP calls
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """
        Enforce the NCBI inter-request delay.
        Sleep for the remaining time since the last call if needed.

        [CONCEPT] Rate limiting via time.sleep: we record the timestamp of the
        last outbound request, then before each new call compute how much of the
        minimum interval has already elapsed and sleep the remainder. This is a
        simple leaky-bucket approach — adequate for single-threaded Phase 3 use.
        """
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    def _common_params(self) -> dict:
        """Base params shared by ESearch and EFetch calls."""
        base = {"db": "pubmed"}
        if self._api_key:
            base["api_key"] = self._api_key
        return base

    def _esearch(self, query: str, max_results: int) -> list[str] | RetrievalError:
        """
        Call ESearch to get a list of PMIDs for the query.
        Returns a list of PMID strings on success, RetrievalError on failure.

        ESearch JSON response shape (relevant fields only):
          {"esearchresult": {"idlist": ["12345678", "23456789", ...]}}
        """
        self._rate_limit()
        params = {
            **self._common_params(),
            "term":    query,
            "retmax":  max_results,
            "retmode": "json",
        }
        try:
            resp = requests.get(_ESEARCH_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()
            pmids: list[str] = data.get("esearchresult", {}).get("idlist", [])
            logger.debug("[PubMed] ESearch returned %d PMIDs", len(pmids))
            return pmids
        except requests.exceptions.Timeout:
            return RetrievalError(
                source_name="PubMed",
                error_code="timeout",
                error_message="ESearch request timed out.",
                retryable=True,
                occurred_at=datetime.now(timezone.utc),
            )
        except requests.exceptions.RequestException as exc:
            return RetrievalError(
                source_name="PubMed",
                error_code="http_error",
                error_message=f"ESearch HTTP error: {exc}",
                retryable=True,
                occurred_at=datetime.now(timezone.utc),
            )
        except (KeyError, ValueError) as exc:
            return RetrievalError(
                source_name="PubMed",
                error_code="parse_error",
                error_message=f"ESearch JSON parse error: {exc}",
                retryable=False,
                occurred_at=datetime.now(timezone.utc),
            )

    def _efetch(self, pmids: list[str]) -> str | RetrievalError:
        """
        Call EFetch to retrieve PubMed XML for a list of PMIDs.
        Returns raw XML string on success, RetrievalError on failure.

        rettype=abstract gives us: ArticleTitle, Abstract, PubDate, PMID,
        AuthorList. retmode=xml is required — the JSON efetch endpoint does
        not expose structured abstract text.
        """
        self._rate_limit()
        params = {
            **self._common_params(),
            "id":      ",".join(pmids),
            "rettype": "abstract",
            "retmode": "xml",
        }
        try:
            resp = requests.get(_EFETCH_URL, params=params, timeout=self._timeout)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.Timeout:
            return RetrievalError(
                source_name="PubMed",
                error_code="timeout",
                error_message="EFetch request timed out.",
                retryable=True,
                occurred_at=datetime.now(timezone.utc),
            )
        except requests.exceptions.RequestException as exc:
            return RetrievalError(
                source_name="PubMed",
                error_code="http_error",
                error_message=f"EFetch HTTP error: {exc}",
                retryable=True,
                occurred_at=datetime.now(timezone.utc),
            )

    # ------------------------------------------------------------------
    # XML parser
    # ------------------------------------------------------------------

    def _parse_pubmed_xml(
        self, xml_text: str, retrieved_at: datetime
    ) -> list[EvidenceItem]:
        """
        Parse PubMed EFetch XML into a list of EvidenceItems.

        PubMed XML structure (simplified):
          <PubmedArticleSet>
            <PubmedArticle>
              <MedlineCitation>
                <PMID>12345678</PMID>
                <Article>
                  <ArticleTitle>...</ArticleTitle>
                  <Abstract>
                    <AbstractText>...</AbstractText>
                    <!-- or multiple labelled sections: -->
                    <AbstractText Label="BACKGROUND">...</AbstractText>
                    <AbstractText Label="CONCLUSIONS">...</AbstractText>
                  </Abstract>
                  <Journal>
                    <JournalIssue>
                      <PubDate>
                        <Year>2023</Year>
                        <Month>05</Month>
                      </PubDate>
                    </JournalIssue>
                  </Journal>
                </Article>
              </MedlineCitation>
            </PubmedArticle>
          </PubmedArticleSet>

        Notes:
        - Abstract may be absent (some articles only have titles in PubMed).
          We log a warning and use an empty string rather than dropping the article.
        - Abstract may be structured (multiple <AbstractText Label="..."> elements).
          We concatenate them with the label as a prefix: "BACKGROUND: ... CONCLUSIONS: ..."
        - PubDate may be partial (year only, or year + month).
          We store whatever is present as a string.
        - PMID is used to construct the canonical PubMed URL.
        """
        root = ET.fromstring(xml_text)
        items: list[EvidenceItem] = []

        for article_el in root.findall(".//PubmedArticle"):
            pmid      = self._extract_pmid(article_el)
            title     = self._extract_title(article_el)
            abstract  = self._extract_abstract(article_el, pmid)
            pub_date  = self._extract_pubdate(article_el)
            url       = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

            items.append(EvidenceItem(
                title            = title,
                abstract         = abstract,
                url              = url,
                source_name      = self.SOURCE_NAME,
                publication_date = pub_date,
                evidence_tier    = self.EVIDENCE_TIER,
                source_tier      = self.SOURCE_TIER,
                cache_hit        = False,
                retrieved_at     = retrieved_at,
            ))

        return items

    # ------------------------------------------------------------------
    # XML extraction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_pmid(article_el: ET.Element) -> str:
        """Extract PMID text from a PubmedArticle element."""
        pmid_el = article_el.find(".//PMID")
        return pmid_el.text.strip() if pmid_el is not None and pmid_el.text else ""

    @staticmethod
    def _extract_title(article_el: ET.Element) -> str:
        """Extract ArticleTitle text, stripping inner XML tags (e.g., <i>, <sub>)."""
        title_el = article_el.find(".//ArticleTitle")
        if title_el is None:
            return "(No title)"
        # itertext() walks all text nodes inside the element, including subelements.
        return "".join(title_el.itertext()).strip()

    @classmethod
    def _extract_abstract(cls, article_el: ET.Element, pmid: str) -> str:
        """
        Extract abstract text. Handles both plain and structured abstracts.
        Returns empty string if no abstract element is found (with a log warning).
        """
        abstract_texts = article_el.findall(".//Abstract/AbstractText")
        if not abstract_texts:
            logger.debug("[PubMed] PMID %s has no abstract in EFetch response.", pmid)
            return ""

        if len(abstract_texts) == 1:
            # Plain abstract — no section labels.
            return "".join(abstract_texts[0].itertext()).strip()

        # Structured abstract — concatenate sections with label prefixes.
        parts: list[str] = []
        for el in abstract_texts:
            label = el.get("Label", "")
            text  = "".join(el.itertext()).strip()
            if label:
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)
        return " ".join(parts)

    @staticmethod
    def _extract_pubdate(article_el: ET.Element) -> Optional[str]:
        """
        Extract publication date from the JournalIssue/PubDate element.
        PubDate may contain Year only, Year+Month, or Year+Month+Day.
        Returns a partial ISO-ish string such as "2023", "2023-05", "2023-05-12".
        Returns None if no date can be extracted.
        """
        pubdate_el = article_el.find(".//JournalIssue/PubDate")
        if pubdate_el is None:
            return None
        year  = pubdate_el.findtext("Year")
        month = pubdate_el.findtext("Month")
        day   = pubdate_el.findtext("Day")
        if not year:
            return None
        # Month may be a 3-letter abbreviation (e.g., "Jan"). Convert if numeric.
        parts = [year]
        if month:
            # Pad numeric months; leave alpha months as-is.
            parts.append(month.zfill(2) if month.isdigit() else month)
        if day:
            parts.append(day.zfill(2))
        return "-".join(parts)
