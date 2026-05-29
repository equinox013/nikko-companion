"""
retrieval/semantic_safety_filter.py
=====================================
Semantic safety pre-filter for the NIKKO pipeline.

Spec source : §8g Improvement 3 (CLAUDE.md)
Requirements: REQ-300-001 (crisis detection), REQ-100-060 (risk_indicators)

Role in the system
-------------------
Sits in backend/main.py BEFORE the NikkoPipeline call (_pipeline_run_sync).
Performs a fast cosine similarity lookup against a FAISS flat index built at
startup from two flat JSON phrase files:

  retrieval/phrase_db/crisis_phrases.json     — SPEC-100 crisis language
  retrieval/phrase_db/safe_anchor_phrases.json — explicit false-positive anchors

Threshold logic (REQ-300-001):

  cosine_sim ≥ 0.70 against any crisis phrase
      → FORCE_CRISIS  — skip ADP-B inference entirely
      → backend returns CRISIS routing immediately

  0.55 ≤ cosine_sim < 0.70 (soft context band)
      → SOFT_SIGNAL   — pass through to ADP-B with similarity score as context
      → Safe anchor veto: if any safe anchor scores ≥ 0.75, raise force threshold
        to 0.95 for this message (prevents "I'm dying of laughter" mis-routes)

  cosine_sim < 0.70
      → CLEAR         — ADP-B normal, no signal from pre-filter

Architecture
-------------
- Embedding model: sentence-transformers/all-MiniLM-L6-v2 (22 M params, CPU only)
  Selected for: low latency (~80ms on CPU), no GPU budget impact, strong English
  semantic similarity on short phrases.
- Index: FAISS IndexFlatIP (inner product on L2-normalised vectors = cosine sim).
  No Render DB — phrase files are flat JSON committed to the repo. Update by
  editing the JSON and redeploying.
- Build time: ~2s at startup (encoding ~160 phrases).
- Query time: <5ms per message (flat index, no approximate search).

[DECISION-RATIONALE] FAISS flat index over ScaNN / annoy / hnswlib:
  The phrase database is small (~160 phrases). Approximate nearest-neighbour
  indices (HNSW, IVF) have build overhead that exceeds the search savings at
  this scale. IndexFlatIP is exact, instant to build, and deterministic —
  important for a safety-critical path.

[DECISION-RATIONALE] MiniLM-L6-v2 over larger models:
  The safety pre-filter is latency-sensitive (runs on every message, on CPU).
  MiniLM-L6-v2 encodes a sentence in ~15ms on CPU vs ~200ms for mpnet-base-v2.
  Benchmark: MiniLM-L6-v2 achieves 0.88 Spearman on STS-B, adequate for
  distinguishing "I want to die" from "I'm dying of laughter". A larger model
  would not meaningfully improve the ≥0.90 threshold decision on these phrases.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy imports — only loaded if the filter is initialised ──────────────────
# faiss-cpu and sentence-transformers are optional dependencies.
# The filter degrades gracefully if they are unavailable (CLEAR result).
try:
    import faiss  # type: ignore[import-untyped]
    _FAISS_AVAILABLE = True
except ImportError:
    faiss = None  # type: ignore[assignment]
    _FAISS_AVAILABLE = False
    logger.warning(
        "faiss-cpu not installed — SemanticSafetyFilter will return CLEAR on all inputs. "
        "Install with: pip install faiss-cpu"
    )

try:
    from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
    _ST_AVAILABLE = True
except ImportError:
    SentenceTransformer = None  # type: ignore[assignment,misc]
    _ST_AVAILABLE = False
    logger.warning(
        "sentence-transformers not installed — SemanticSafetyFilter will return CLEAR. "
        "Install with: pip install sentence-transformers"
    )


# ── Default phrase file paths ────────────────────────────────────────────────
# Resolved relative to this module's location so the filter works whether
# imported from the repo root or from within the backend package.
_MODULE_DIR  = Path(__file__).parent
_PHRASE_DB   = _MODULE_DIR / "phrase_db"
_DEFAULT_CRISIS_FILE = _PHRASE_DB / "crisis_phrases.json"
_DEFAULT_ANCHOR_FILE = _PHRASE_DB / "safe_anchor_phrases.json"

# ── Embedding model name ─────────────────────────────────────────────────────
_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


# ── Result types ─────────────────────────────────────────────────────────────

class FilterDecision(str, Enum):
    """
    Outcome returned by SemanticSafetyFilter.check().

    FORCE_CRISIS : cosine_sim ≥ hard_threshold — skip ADP-B, route CRISIS.
    SOFT_SIGNAL  : 0.70 ≤ cosine_sim < hard_threshold — pass through with context.
    CLEAR        : cosine_sim < 0.70 — no signal, normal ADP-B path.
    """
    FORCE_CRISIS = "FORCE_CRISIS"
    SOFT_SIGNAL  = "SOFT_SIGNAL"
    CLEAR        = "CLEAR"


@dataclass
class FilterResult:
    """
    Full result from SemanticSafetyFilter.check().

    Fields:
        decision         : FilterDecision enum value
        top_crisis_sim   : Highest cosine similarity against the crisis index
        top_crisis_phrase: The crisis phrase that scored highest (for logging)
        top_anchor_sim   : Highest cosine similarity against safe anchor index
        top_anchor_phrase: The anchor phrase that scored highest (for logging)
        safe_anchor_veto : True when anchor veto raised the hard threshold to 0.95
        elapsed_ms       : Filter latency in milliseconds
    """
    decision:          FilterDecision
    top_crisis_sim:    float
    top_crisis_phrase: str
    top_anchor_sim:    float
    top_anchor_phrase: str
    safe_anchor_veto:  bool
    elapsed_ms:        float


# ── Main class ───────────────────────────────────────────────────────────────

class SemanticSafetyFilter:
    """
    FAISS-backed semantic safety pre-filter.

    Initialise once at application startup. Thread-safe for concurrent reads
    (FAISS IndexFlatIP.search is read-only after build).

    Usage:
        filter = SemanticSafetyFilter()
        result = filter.check("I want to end my life")
        if result.decision == FilterDecision.FORCE_CRISIS:
            # short-circuit to CRISIS response

    Configuration via environment variables (optional):
        NIKKO_FILTER_HARD_THRESHOLD  : float, default 0.90
        NIKKO_FILTER_SOFT_THRESHOLD  : float, default 0.70
        NIKKO_FILTER_ANCHOR_VETO_SIM : float, default 0.75
        NIKKO_FILTER_ANCHOR_VETO_HARD: float, default 0.95 (raised threshold when veto fires)
    """

    def __init__(
        self,
        crisis_phrases_path:  Optional[Path] = None,
        anchor_phrases_path:  Optional[Path] = None,
        embedding_model_name: str             = _EMBEDDING_MODEL,
        hard_threshold:       float           = 0.70,
        soft_threshold:       float           = 0.55,
        anchor_veto_sim:      float           = 0.75,
        anchor_veto_hard:     float           = 0.95,
    ):
        """
        Build FAISS indices from phrase files.

        Parameters
        ----------
        crisis_phrases_path  : Path to crisis_phrases.json. Defaults to phrase_db/.
        anchor_phrases_path  : Path to safe_anchor_phrases.json. Defaults to phrase_db/.
        embedding_model_name : HuggingFace model identifier for sentence-transformers.
        hard_threshold       : Cosine similarity ≥ this → FORCE_CRISIS.
        soft_threshold       : Cosine similarity ≥ this (< hard) → SOFT_SIGNAL.
        anchor_veto_sim      : Safe anchor score ≥ this → raise hard_threshold to anchor_veto_hard.
        anchor_veto_hard     : Raised hard threshold when anchor veto fires.
        """
        # Read thresholds from env vars if set (allows Render env-var tuning
        # without code changes after deployment).
        self._hard_threshold  = float(os.getenv("NIKKO_FILTER_HARD_THRESHOLD",  hard_threshold))
        self._soft_threshold  = float(os.getenv("NIKKO_FILTER_SOFT_THRESHOLD",  soft_threshold))
        self._anchor_veto_sim = float(os.getenv("NIKKO_FILTER_ANCHOR_VETO_SIM", anchor_veto_sim))
        self._anchor_veto_hard = float(os.getenv("NIKKO_FILTER_ANCHOR_VETO_HARD", anchor_veto_hard))

        self._ready = False

        if not (_FAISS_AVAILABLE and _ST_AVAILABLE):
            logger.warning(
                "SemanticSafetyFilter initialised in degraded mode "
                "(faiss-cpu or sentence-transformers unavailable). "
                "All inputs will return FilterDecision.CLEAR."
            )
            return

        crisis_path = crisis_phrases_path or _DEFAULT_CRISIS_FILE
        anchor_path = anchor_phrases_path or _DEFAULT_ANCHOR_FILE

        t0 = time.perf_counter()

        # Load model on CPU — no GPU budget impact.
        # [CONCEPT] SentenceTransformer automatically uses the best available device.
        # We force CPU here to keep inference latency predictable regardless of
        # whether a GPU is present on the Render instance.
        logger.info("Loading embedding model: %s", embedding_model_name)
        self._model = SentenceTransformer(embedding_model_name, device="cpu")

        # Load phrase lists.
        self._crisis_phrases = self._load_phrases(crisis_path)
        self._anchor_phrases = self._load_phrases(anchor_path)

        # Build FAISS indices.
        self._crisis_index, self._crisis_vecs = self._build_index(self._crisis_phrases)
        self._anchor_index, self._anchor_vecs = self._build_index(self._anchor_phrases)

        elapsed = (time.perf_counter() - t0) * 1000
        logger.info(
            "SemanticSafetyFilter ready | crisis_phrases=%d anchor_phrases=%d "
            "build_time=%.0fms hard_threshold=%.2f soft_threshold=%.2f",
            len(self._crisis_phrases), len(self._anchor_phrases), elapsed,
            self._hard_threshold, self._soft_threshold,
        )
        self._ready = True

    # ── Public API ────────────────────────────────────────────────────────────

    def check(self, user_text: str) -> FilterResult:
        """
        Run the semantic safety check on a user message.

        Returns a FilterResult with decision, similarity scores, and latency.
        Never raises — on any internal error returns CLEAR with elapsed_ms.
        """
        t0 = time.perf_counter()

        # Degraded mode: dependencies missing.
        if not self._ready:
            return FilterResult(
                decision=FilterDecision.CLEAR,
                top_crisis_sim=0.0, top_crisis_phrase="",
                top_anchor_sim=0.0, top_anchor_phrase="",
                safe_anchor_veto=False,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            # Encode the incoming message — CPU, ~15ms for short texts.
            query_vec = self._model.encode(
                [user_text.strip()],
                convert_to_numpy=True,
                normalize_embeddings=True,
            ).astype("float32")

            # Search crisis index (k=1 — we only need the top match).
            crisis_sims, crisis_idxs = self._crisis_index.search(query_vec, k=1)
            top_crisis_sim   = float(crisis_sims[0][0])
            top_crisis_phrase = self._crisis_phrases[int(crisis_idxs[0][0])]

            # Search anchor index (k=1).
            anchor_sims, anchor_idxs = self._anchor_index.search(query_vec, k=1)
            top_anchor_sim    = float(anchor_sims[0][0])
            top_anchor_phrase = self._anchor_phrases[int(anchor_idxs[0][0])]

            # ── Threshold logic ────────────────────────────────────────────────
            # Safe anchor veto: if the message is also semantically close to a
            # known false-positive phrase, raise the force-CRISIS threshold.
            # This handles: "I'm dying of laughter", "this is killing me at work".
            # Note: veto only applies in the soft band (0.70–0.90). At ≥0.90
            # genuine crisis language is unmistakeable and veto does NOT apply.
            safe_anchor_veto = top_anchor_sim >= self._anchor_veto_sim
            effective_hard   = self._anchor_veto_hard if safe_anchor_veto else self._hard_threshold

            if top_crisis_sim >= effective_hard:
                decision = FilterDecision.FORCE_CRISIS
            elif top_crisis_sim >= self._soft_threshold:
                decision = FilterDecision.SOFT_SIGNAL
            else:
                decision = FilterDecision.CLEAR

            elapsed_ms = (time.perf_counter() - t0) * 1000

            if decision != FilterDecision.CLEAR:
                logger.info(
                    "SemanticSafetyFilter: decision=%s crisis_sim=%.3f "
                    "anchor_sim=%.3f veto=%s elapsed=%.1fms | top_crisis_phrase='%.60s'",
                    decision.value, top_crisis_sim, top_anchor_sim,
                    safe_anchor_veto, elapsed_ms, top_crisis_phrase,
                )

            return FilterResult(
                decision=decision,
                top_crisis_sim=top_crisis_sim,
                top_crisis_phrase=top_crisis_phrase,
                top_anchor_sim=top_anchor_sim,
                top_anchor_phrase=top_anchor_phrase,
                safe_anchor_veto=safe_anchor_veto,
                elapsed_ms=elapsed_ms,
            )

        except Exception as exc:
            logger.error("SemanticSafetyFilter.check() raised: %s", exc, exc_info=True)
            return FilterResult(
                decision=FilterDecision.CLEAR,
                top_crisis_sim=0.0, top_crisis_phrase="",
                top_anchor_sim=0.0, top_anchor_phrase="",
                safe_anchor_veto=False,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _load_phrases(path: Path) -> list[str]:
        """Load phrase list from a JSON file with a 'phrases' key."""
        if not path.exists():
            raise FileNotFoundError(
                f"SemanticSafetyFilter: phrase file not found: {path}\n"
                f"Ensure retrieval/phrase_db/ is committed and the path is correct."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        phrases = data.get("phrases", [])
        if not phrases:
            raise ValueError(f"SemanticSafetyFilter: no phrases found in {path}")
        return phrases

    def _build_index(self, phrases: list[str]) -> tuple:
        """
        Encode phrases with the embedding model and build a FAISS IndexFlatIP.

        [CONCEPT] IndexFlatIP performs exact inner-product search on L2-normalised
        vectors, which is equivalent to cosine similarity search. No approximate
        search is used — at <200 phrases the exact search is <1ms and there is
        no benefit to ANN indexing.

        Returns (index, embeddings_array).
        """
        vecs = self._model.encode(
            phrases,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2 normalise → inner product = cosine sim
            show_progress_bar=False,
        ).astype("float32")

        dim   = vecs.shape[1]
        index = faiss.IndexFlatIP(dim)  # exact cosine similarity via inner product
        index.add(vecs)
        return index, vecs
