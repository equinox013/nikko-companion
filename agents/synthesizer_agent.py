"""
agents/synthesizer_agent.py
============================
Evidence Synthesizer Agent — Phase 3, Step 7.

Spec source : SPEC-200 §5.5
Requirements: REQ-200-080, REQ-200-081, REQ-200-ER3, REQ-200-126/127/128/129,
              G-EVIDENCE-01 tiebreak rule (peer-review preferred within 5 years;
              fall back to grey-literature with confidence penalty + flag).

Role in the pipeline (SPEC-700 STEP 4)
---------------------------------------
  Evidence Retrieval Agent
       │  List[EvidencePayload]       ← one payload per adapter that ran
       ▼
  Evidence Synthesizer Agent (this module)
       │  SynthesizedEvidence          ← consolidated, ranked, scored
       ▼
  [embedded in ResponseContextPayload → Interaction Model]

Hard constraints
-----------------
  REQ-200-081 — MUST NOT interpret user emotion.
  REQ-200-081 — MUST NOT generate advice.
  REQ-200-081 — MUST NOT determine response strategy.
  REQ-200-126 — Evidence is immutable once retrieved; this agent only RANKS and SCORES.
  REQ-200-127 — Only this agent may transform retrieved evidence.

Design note: deterministic, no LLM
------------------------------------
AGENT_DEFINITIONS.md §5 says the Synthesizer is "likely an LLM call". We chose
deterministic aggregation instead for three reasons:
  1. Auditability — every ranking and confidence delta maps to a named REQ ID.
  2. Latency — no extra LLM round-trip on the Guidance Mode path.
  3. Testability — outputs are reproducible from fixed inputs.
If the Director wants an LLM synthesis pass (e.g., to write a prose summary),
it can be added as a post-processing step without changing the ranking/scoring
logic here. This file owns ranking + scoring; prose generation belongs to the
Interaction Model.
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone, timedelta
from functools import partial
from typing import Optional

# [CONCEPT] We import the shared Pydantic schemas from acp_schemas.py. These
# are the single source of truth for all inter-agent data shapes. The
# Synthesizer never defines its own data classes — it consumes and produces
# types already ratified in SPEC-200 §5.4/5.5.
from docs.schemas.acp_schemas import (
    EvidenceItem,
    EvidencePayload,
    EvidenceTier,
    SourceTier,
    SynthesizedEvidence,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (all values traceable to ratified gap rulings)
# ---------------------------------------------------------------------------

# G-EVIDENCE-01: prefer peer-reviewed sources published within the last N years.
# Director ratified: 5 years.
_PEER_REVIEW_RECENCY_YEARS: int = 5

# Maximum citations to include in SynthesizedEvidence.citations.
_MAX_CITATIONS: int = 5

# Confidence formula constants — each maps to a requirement.
_BASE_PEER_REVIEWED: float = 0.90    # REQ-200-080: primary tier, peer-reviewed present
_BASE_GREY_LIT_ONLY: float = 0.65    # REQ-200-ER3: grey-literature fallback base
_PENALTY_GREY_LIT_DOMINANT: float = 0.15   # REQ-200-ER3: extra penalty — no peer-reviewed
_PENALTY_DISAGREEMENT: float = 0.10  # REQ-200-080: source disagreement detected

# Disagreement detection: two abstracts are "divergent" when shared keyword
# overlap falls below this fraction. Heuristic for v0.
_DISAGREEMENT_OVERLAP_THRESHOLD: float = 0.25

# Minimum token count for an abstract to participate in disagreement detection.
# Short snippets (scraped descriptions, truncated fields) produce false positives.
_MIN_ABSTRACT_TOKENS: int = 15

# Relevance filtering: minimum fraction of query tokens that must appear in
# an item's combined title + abstract text for it to pass the relevance gate.
#
# Rationale: a broad PubMed query like "relaxation techniques anxiety management
# mental health" may return papers about CBT for menopausal symptoms. Those papers
# discuss CBT and stress management but don't contain "relaxation", "calm", etc.
# A 0.20 threshold means at least 1-in-5 non-trivial query terms must appear.
# Too high (>0.40) risks filtering genuinely relevant papers with sparse abstracts.
_MIN_RELEVANCE_SCORE: float = 0.20

# Stop words excluded from relevance scoring — too generic to be discriminating.
_RELEVANCE_STOP: frozenset[str] = frozenset({
    "a", "an", "the", "of", "in", "on", "and", "or", "for", "to",
    "with", "by", "from", "at", "is", "are", "was", "were",
    # Domain-level stop words: every mental health paper contains these.
    "mental", "health", "management", "support", "strategies", "wellbeing",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> set[str]:
    """
    Reduce a citation title to a set of lowercase alphabetical tokens.
    Used for deduplication — two titles are duplicates when Jaccard >= 0.90.

    Stop words are stripped to prevent them inflating overlap scores.
    """
    _STOP = {"a", "an", "the", "of", "in", "on", "and", "or", "for", "to",
              "with", "by", "from", "at", "is", "are", "was", "were"}
    tokens = re.sub(r"[^a-z0-9\s]", "", title.lower()).split()
    return set(t for t in tokens if t not in _STOP)


def _jaccard_overlap(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity: |A ∩ B| / |A ∪ B|. Returns 0.0 for empty sets."""
    if not set_a and not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _parse_publication_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO-8601 date string (YYYY-MM-DD or YYYY) into UTC-aware datetime.
    Returns None on failure — items with no date rank last within their tier.
    """
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y"):
        try:
            return datetime.strptime(date_str[:len(fmt.replace("%Y", "XXXX").replace("%m", "XX").replace("%d", "XX"))], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    # Fallback: try the raw string up to 10 characters
    for attempt, length in [("%Y-%m-%d", 10), ("%Y", 4)]:
        try:
            return datetime.strptime(date_str[:length], attempt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.warning("Unparseable publication_date: %r — will rank last.", date_str)
    return None


def _is_recent_peer_reviewed(item: EvidenceItem) -> bool:
    """
    True if item is PEER_REVIEWED and published within _PEER_REVIEW_RECENCY_YEARS.
    This is the top-priority bucket in the G-EVIDENCE-01 tiebreak sort.
    """
    if item.evidence_tier != EvidenceTier.PEER_REVIEWED:
        return False
    pub_date = _parse_publication_date(item.publication_date)
    if pub_date is None:
        return False
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=365 * _PEER_REVIEW_RECENCY_YEARS)
    return pub_date >= cutoff


def _sort_key(
    item: EvidenceItem,
    preferred_sources: frozenset = frozenset(),
) -> tuple:
    """
    Sort key implementing the G-EVIDENCE-01 tiebreak rule.
    Lower tuple = higher priority (ascending sort).

    Bucket order:
      0 — PEER_REVIEWED, published within last 5 years           (best)
      1 — PEER_REVIEWED, older than 5 years or no date
      2a — GREY_LITERATURE, PRIMARY, source is topically preferred
      2b — GREY_LITERATURE, PRIMARY, generic source              (G-RETRIEVAL-02)
      3 — GREY_LITERATURE, SECONDARY source tier (fallback)      (worst)

    The 2a/2b split is the G-RETRIEVAL-02 addition: when the pipeline has
    detected a specific topic (e.g. GRIEF), grey-lit results from topically
    specialised sources (e.g. GriefLine, Lifeline) are ranked before results
    from general-coverage sources (e.g. Healthdirect).  This does not change
    the overall tier order — peer-reviewed always wins.

    Within each sub-bucket, most recent publication date wins (negated epoch).

    [CONCEPT] functools.partial: this function is called as a sort key via
    partial(_sort_key, preferred_sources=ps), which pre-binds the
    preferred_sources argument.  The result is a one-argument callable
    suitable for list.sort(key=...) — Python's sort protocol.

    Parameters
    ----------
    item : EvidenceItem
        The evidence item being ranked.
    preferred_sources : frozenset[str]
        Human-readable source labels (DomainProfile.label) for domains that
        cover the current query's detected topics.  Empty frozenset → no
        sub-bucket split (identical to pre-G-RETRIEVAL-02 behaviour).
    """
    if _is_recent_peer_reviewed(item):
        bucket = 0
        sub    = 0
    elif item.evidence_tier == EvidenceTier.PEER_REVIEWED:
        bucket = 1
        sub    = 0
    elif item.source_tier == SourceTier.PRIMARY:
        bucket = 2
        # Sub-bucket: 0 if source is topically preferred, 1 otherwise.
        # An empty preferred_sources set means all PRIMARY items tie at sub=1
        # — identical ranking to the pre-G-RETRIEVAL-02 behaviour.
        sub = 0 if (preferred_sources and item.source_name in preferred_sources) else 1
    else:
        bucket = 3
        sub    = 0

    pub_date = _parse_publication_date(item.publication_date)
    recency  = -(pub_date.timestamp() if pub_date else 0)
    return (bucket, sub, recency)


def _deduplicate(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """
    Remove near-duplicate citations using Jaccard title-token similarity.
    When two items share >= 90% title tokens, the later (lower-priority) one
    is dropped. Items must be pre-sorted so the better item comes first.

    O(n²) — acceptable for n <= 20 (typical retrieval batch size).
    """
    kept: list[EvidenceItem] = []
    for candidate in items:
        c_tokens = _normalize_title(candidate.title)
        is_dup = any(
            _jaccard_overlap(c_tokens, _normalize_title(existing.title)) >= 0.90
            for existing in kept
        )
        if not is_dup:
            kept.append(candidate)
    return kept


def _abstract_tokens(text: str) -> set[str]:
    """Tokenize an abstract into a set of lowercase alphanumeric tokens."""
    return set(re.sub(r"[^a-z0-9\s]", "", text.lower()).split())


def _detect_disagreement(items: list[EvidenceItem]) -> tuple[bool, Optional[str]]:
    """
    Heuristic source-disagreement detector. (REQ-200-072, REQ-200-080)

    Flags disagreement when two items share a similar title (same topic,
    Jaccard >= 0.50) but their abstract keyword sets overlap below
    _DISAGREEMENT_OVERLAP_THRESHOLD.

    Abstracts with fewer than _MIN_ABSTRACT_TOKENS tokens are skipped —
    short snippets produce false positives due to sparse vocabulary.

    An LLM-backed contradiction detector can replace this in Phase 6.
    (SPEC-500 §4 — evaluation criteria include factual grounding checks.)
    """
    if len(items) < 2:
        return False, None

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            a_tok = _abstract_tokens(a.abstract)
            b_tok = _abstract_tokens(b.abstract)

            # Skip pairs where either abstract is too short to be reliable.
            if len(a_tok) < _MIN_ABSTRACT_TOKENS or len(b_tok) < _MIN_ABSTRACT_TOKENS:
                logger.debug(
                    "Skipping disagreement check '%s' vs '%s' — "
                    "abstracts too short (%d, %d tokens).",
                    a.source_name, b.source_name, len(a_tok), len(b_tok),
                )
                continue

            # Only compare items on the same topic.
            title_overlap = _jaccard_overlap(
                _normalize_title(a.title), _normalize_title(b.title)
            )
            if title_overlap < 0.50:
                continue

            # Same topic: check if abstracts diverge.
            abstract_overlap = _jaccard_overlap(a_tok, b_tok)
            if abstract_overlap < _DISAGREEMENT_OVERLAP_THRESHOLD:
                note = (
                    f"Potential disagreement between '{a.source_name}' and "
                    f"'{b.source_name}' on '{a.title[:60]}'. "
                    f"Abstract keyword overlap: {abstract_overlap:.2f} "
                    f"(threshold: {_DISAGREEMENT_OVERLAP_THRESHOLD}). "
                    "Confidence reduced. (REQ-200-080)"
                )
                logger.warning(note)
                return True, note

    return False, None


def _relevance_score(item: EvidenceItem, query: str) -> float:
    """
    Compute a relevance score: fraction of meaningful query tokens that appear
    anywhere in the item's title + abstract text.

    Metric: matched_tokens / total_query_tokens (coverage ratio).
    Domain stop words and tokens shorter than 3 characters are excluded so that
    "mental health management" doesn't inflate scores via near-universal terms.

    Returns 1.0 when the query has no meaningful tokens — i.e. nothing to filter on.
    Examples (query="relaxation techniques anxiety calm"):
      "CBT for anxiety and depression" → matched {"anxiety"} / 3 unique terms = 0.33 ✓
      "CBT for (peri)menopausal symptoms" → matched {} / 3 unique terms = 0.0  ✗
    """
    query_tokens = set(
        t for t in re.sub(r"[^a-z0-9\s]", "", query.lower()).split()
        if t not in _RELEVANCE_STOP and len(t) > 2
    )
    if not query_tokens:
        # No discriminating terms in the query — accept everything.
        return 1.0

    item_text = (item.title + " " + item.abstract).lower()
    item_text_clean = re.sub(r"[^a-z0-9\s]", "", item_text)
    item_word_set = set(item_text_clean.split())

    matched = len(query_tokens & item_word_set)
    return matched / len(query_tokens)


def _compute_confidence(
    citations: list[EvidenceItem],
    grey_literature_used: bool,
    source_disagreement: bool,
) -> float:
    """
    Confidence scoring formula. All deltas trace to ratified requirements.

    Base (REQ-200-080 / REQ-200-ER3):
      Any PEER_REVIEWED citation present → 0.90
      Grey-literature only              → 0.65

    Penalties:
      No peer-reviewed at all           → −0.15  (REQ-200-ER3)
      Source disagreement detected      → −0.10  (REQ-200-080)

    Floor: 0.0 (empty input). Ceiling: 0.90 (no upward bonus in v0).
    """
    if not citations:
        return 0.0

    has_peer = any(c.evidence_tier == EvidenceTier.PEER_REVIEWED for c in citations)
    score = _BASE_PEER_REVIEWED if has_peer else _BASE_GREY_LIT_ONLY

    if grey_literature_used and not has_peer:
        score -= _PENALTY_GREY_LIT_DOMINANT   # REQ-200-ER3

    if source_disagreement:
        score -= _PENALTY_DISAGREEMENT         # REQ-200-080

    return round(max(0.0, min(1.0, score)), 4)


def _build_summary(citations: list[EvidenceItem], grey_literature_used: bool) -> str:
    """
    Build a structured summary string for SynthesizedEvidence.summary.

    Intentionally plain — not a prose paragraph. The Interaction Model uses
    the raw citations and the strategy payload to compose the user-facing text.
    This summary tells the Interaction Model what was found and from where,
    plus any hedging obligations (REQ-200-ER3).
    """
    if not citations:
        return "No relevant evidence retrieved for this query."

    labels = [f"{c.title[:60]}… ({c.source_name})" for c in citations[:3]]
    tail = "" if len(citations) <= 3 else f"; and {len(citations) - 3} more."
    summary = f"{len(citations)} source(s) retrieved: {'; '.join(labels)}{tail}"

    has_peer = any(c.evidence_tier == EvidenceTier.PEER_REVIEWED for c in citations)
    if grey_literature_used and not has_peer:
        # REQ-200-ER3: Synthesizer MUST flag grey-lit fallback so the
        # Interaction Model can qualify factual claims appropriately.
        summary += (
            " Note: all sources are grey-literature (no peer-reviewed evidence "
            "found). Interaction Model SHOULD hedge factual claims. (REQ-200-ER3)"
        )

    return summary


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

class EvidenceSynthesizerAgent:
    """
    Deterministic evidence consolidator.

    Receives EvidencePayload objects from the retrieval layer, ranks and
    deduplicates items by the G-EVIDENCE-01 tiebreak rule, scores overall
    confidence, and emits a single SynthesizedEvidence bundle.

    Usage (within the pipeline orchestrator):
        synthesizer = EvidenceSynthesizerAgent()
        result = synthesizer.synthesize(evidence_payloads, query=user_query)
    """

    def synthesize(
        self,
        evidence_payloads: list[EvidencePayload],
        query: str = "",
        preferred_sources: frozenset = frozenset(),
    ) -> SynthesizedEvidence:
        """
        Consolidate EvidencePayload objects into a SynthesizedEvidence.

        Parameters
        ----------
        evidence_payloads : list[EvidencePayload]
            Raw retrieval outputs — one per adapter. May be empty (e.g.,
            Crisis Mode where retrieval is skipped per REQ-200-124).
        query : str
            Original search query; used for relevance filtering and logging.
        preferred_sources : frozenset[str]
            Human-readable source labels for topically relevant domains,
            computed by get_preferred_source_labels() in web_search_adapter.py
            from the pipeline's Signal→Topic hints (G-RETRIEVAL-02).
            When non-empty, grey-literature PRIMARY items from preferred sources
            are ranked before generic PRIMARY items (sub-bucket split in
            _sort_key).  An empty frozenset means no sub-bucket boost is applied
            — identical to pre-G-RETRIEVAL-02 behaviour.

        Spec trace
        ----------
            REQ-200-080  consolidate, dedupe, normalise, score confidence
            REQ-200-081  MUST NOT generate advice / interpret emotion
            G-EVIDENCE-01 tiebreak: PEER_REVIEWED(<=5y) > PEER_REVIEWED(older)
                          > GREY_LIT PRIMARY (preferred) > GREY_LIT PRIMARY
                          > GREY_LIT SECONDARY
        """
        logger.info(
            "EvidenceSynthesizerAgent.synthesize() — payloads: %d, query: %r, "
            "preferred_sources: %s",
            len(evidence_payloads),
            query[:80] if query else "",
            sorted(preferred_sources) if preferred_sources else "(none)",
        )

        # 1. Collect all EvidenceItems across payloads.
        all_items: list[EvidenceItem] = []
        grey_literature_used = False
        for ep in evidence_payloads:
            all_items.extend(ep.results)
            if ep.grey_literature_flag:
                grey_literature_used = True
        # Also flag from individual item tiers (catches mis-flagged payloads).
        if any(i.evidence_tier == EvidenceTier.GREY_LITERATURE for i in all_items):
            grey_literature_used = True

        # 2. Sort by G-EVIDENCE-01 tiebreak BEFORE dedup so that when two
        #    near-duplicates exist, the higher-quality item is retained.
        #
        # [CONCEPT] functools.partial: we pre-bind the preferred_sources
        # argument so the resulting one-argument callable satisfies
        # list.sort(key=...).  When preferred_sources is empty we use the
        # bare _sort_key function (no partial overhead, same behaviour).
        sort_fn = (
            partial(_sort_key, preferred_sources=preferred_sources)
            if preferred_sources
            else _sort_key
        )
        all_items.sort(key=sort_fn)

        # 2b. Relevance filter — discard items whose title + abstract share too
        # few tokens with the query. This prevents broad PubMed queries from
        # surfacing topically off-target papers (e.g. a CBT/menopausal-symptoms
        # paper returned for a "relaxation anxiety calm" query). Only applied
        # when a non-empty query is provided; skipped in Crisis Mode (no query).
        if query:
            pre_count = len(all_items)
            all_items = [
                item for item in all_items
                if _relevance_score(item, query) >= _MIN_RELEVANCE_SCORE
            ]
            filtered_count = pre_count - len(all_items)
            if filtered_count:
                logger.info(
                    "Relevance filter removed %d item(s) below threshold=%.2f "
                    "(query=%r).", filtered_count, _MIN_RELEVANCE_SCORE, query[:60],
                )

        # 3. Deduplicate.
        deduped = _deduplicate(all_items)
        logger.debug("Items: %d raw → %d after dedup", len(all_items), len(deduped))

        # 4. Cap to MAX_CITATIONS (ranking already applied in step 2).
        citations = deduped[:_MAX_CITATIONS]

        # 5. Detect source disagreement across full deduped set.
        source_disagreement, disagreement_note = _detect_disagreement(deduped)

        # 6. Compute confidence score.
        confidence = _compute_confidence(citations, grey_literature_used, source_disagreement)
        logger.info(
            "Synthesis: cits=%d grey=%s disagree=%s confidence=%.4f",
            len(citations), grey_literature_used, source_disagreement, confidence,
        )

        # 7. Build summary.
        summary = _build_summary(citations, grey_literature_used)

        # 8. Return consolidated bundle.
        # REQ-200-127: only this agent may transform retrieved evidence.
        # REQ-200-129: Interaction Model receives ONLY this object.
        return SynthesizedEvidence(
            summary=summary,
            citations=citations,
            confidence=confidence,
            grey_literature_used=grey_literature_used,
            source_disagreement=source_disagreement,
            disagreement_note=disagreement_note,
        )
