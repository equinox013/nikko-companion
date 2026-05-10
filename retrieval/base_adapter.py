"""
retrieval/base_adapter.py
=========================
CachedBaseAdapter — concrete intermediate base for all four retrieval adapters.

Spec source  : SPEC-200 §5.4, REQ-200-ER5, REQ-200-160
Phase        : 3 — Agent Definitions (Implementation)
Inherits from: docs.schemas.retrieval_schemas.BaseRetrievalAdapter (abstract)

Why this file exists
--------------------
BaseRetrievalAdapter (in retrieval_schemas.py) is a pure abstract contract —
it defines what each adapter MUST do (search + is_cache_valid) but provides
no shared implementation. All four adapters share identical cache I/O logic:
SHA-256 keying, JSON serialisation, TTL comparison, and HEAD-check scheduling.
Putting that logic here avoids repeating it in every adapter and keeps each
concrete file focused purely on its source-specific HTTP or corpus-search code.

Cache file layout
-----------------
  retrieval/cache/<sha256_hex>.json
  {
    "retrieved_at": "2026-05-10T03:00:00+00:00",
    "expires_at":   "2026-05-17T03:00:00+00:00",
    "last_head_check": "2026-05-10T03:00:00+00:00",   # null if never
    "items": [ ...EvidenceItem dicts... ]
  }

The cache directory path is resolved relative to this file at import time so
it works regardless of the working directory.

Usage
-----
All four adapters subclass CachedBaseAdapter and call:
  - _load_from_cache(query)  → (items, expires_at) or None
  - _save_to_cache(query, items)  → expires_at
  - is_cache_valid(entry)    → bool (TTL check on a single item)
  - _should_head_check(entry) → bool (HEAD-check interval check)

Adapters must NOT catch exceptions here — CachedBaseAdapter propagates I/O
errors to the caller, which wraps them in a RetrievalError. (REQ-200-160)
"""

from __future__ import annotations

import hashlib
import json
import logging
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from docs.schemas.acp_schemas import EvidenceItem
from docs.schemas.retrieval_schemas import BaseRetrievalAdapter, RetrievalError

logger = logging.getLogger(__name__)

# Cache directory is resolved relative to this file, not the cwd.
# This guarantees the path is stable regardless of where Python is invoked from.
_CACHE_DIR: Path = Path(__file__).parent / "cache"


class CachedBaseAdapter(BaseRetrievalAdapter):
    """
    Concrete intermediate base providing shared disk-cache logic for all
    four retrieval adapters. Subclasses must implement search() only;
    is_cache_valid() and _should_head_check() are provided here.

    Cache is keyed by SHA-256 of (SOURCE_NAME + "|" + normalised_query).
    Collision resistance: SHA-256 hex → 2^256 space; practically zero collision
    risk for a bounded set of mental-health search queries.

    Thread safety: not guaranteed. Phase 3 runs single-threaded; add file locks
    if parallel adapter calls are introduced in later phases.
    """

    # ------------------------------------------------------------------
    # Cache key / path helpers
    # ------------------------------------------------------------------

    def _cache_key(self, query: str) -> str:
        """
        Produce a stable, filesystem-safe cache key for (source, query).
        Normalise: strip whitespace + lowercase the query before hashing.
        This ensures "Anxiety" and "anxiety " hit the same cache entry.
        """
        normalised = f"{self.SOURCE_NAME}|{query.strip().lower()}"
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    def _cache_path(self, query: str) -> Path:
        """Return the full path to the cache JSON file for a given query."""
        return _CACHE_DIR / f"{self._cache_key(query)}.json"

    # ------------------------------------------------------------------
    # Cache read
    # ------------------------------------------------------------------

    def _load_from_cache(
        self, query: str
    ) -> Optional[tuple[list[EvidenceItem], datetime]]:
        """
        Attempt to load cached EvidenceItems for this query.

        Returns (items, expires_at) if the cache file exists AND is within TTL.
        Returns None on:
          - cache miss (file not found)
          - TTL expiry (expires_at < now)
          - JSON parse error (logged; treated as a miss so we re-fetch)

        [CONCEPT] Cache-aside pattern: the adapter first checks the local cache.
        Only if the cache is missing or stale does it make an outbound HTTP call.
        This reduces PubMed API calls (rate limit: 3/s without key) and protects
        against Healthdirect availability blips.
        """
        path = self._cache_path(query)

        if not path.exists():
            logger.debug("[%s] cache miss: %s", self.SOURCE_NAME, path.name)
            return None

        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[%s] cache file unreadable (%s) — treating as miss: %s",
                self.SOURCE_NAME, exc, path.name,
            )
            return None

        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now(timezone.utc) >= expires_at:
            logger.debug("[%s] cache expired: %s", self.SOURCE_NAME, path.name)
            return None

        # Deserialise the list of EvidenceItem dicts back to Pydantic models.
        try:
            items = [EvidenceItem(**item) for item in data["items"]]
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[%s] cache item deserialisation failed (%s) — miss: %s",
                self.SOURCE_NAME, exc, path.name,
            )
            return None

        logger.debug(
            "[%s] cache hit — %d items, expires %s",
            self.SOURCE_NAME, len(items), expires_at.isoformat(),
        )
        return items, expires_at

    # ------------------------------------------------------------------
    # Cache write
    # ------------------------------------------------------------------

    def _save_to_cache(self, query: str, items: list[EvidenceItem]) -> datetime:
        """
        Serialise EvidenceItems to disk using the CACHE_POLICY TTL.
        Returns the computed expires_at so the caller can populate
        RetrievalResult.cache_expires_at.

        Non-fatal: if the write fails, log the error and return the expiry time
        anyway — the in-memory result is still usable. (REQ-200-160)
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=self.CACHE_POLICY.ttl_days)

        payload = {
            "retrieved_at":    now.isoformat(),
            "expires_at":      expires_at.isoformat(),
            # Record the time of this write as the initial HEAD-check baseline.
            "last_head_check": now.isoformat(),
            # model_dump(mode="json") converts datetime → ISO string so json.dumps works.
            "items": [item.model_dump(mode="json") for item in items],
        }

        path = self._cache_path(query)
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, default=str)
            logger.debug(
                "[%s] cached %d items → %s (expires %s)",
                self.SOURCE_NAME, len(items), path.name, expires_at.isoformat(),
            )
        except OSError as exc:
            logger.error(
                "[%s] cache write failed (%s) — result still returned in-memory",
                self.SOURCE_NAME, exc,
            )

        return expires_at

    # ------------------------------------------------------------------
    # Validity helpers
    # ------------------------------------------------------------------

    def is_cache_valid(self, entry: EvidenceItem) -> bool:
        """
        Return True if a single EvidenceItem is still within this adapter's
        CACHE_POLICY TTL. Uses entry.retrieved_at as the age baseline.

        Note: this method checks one item in isolation. For batch cache reads,
        use _load_from_cache(), which checks the file-level expires_at instead.
        (REQ-200-ER5)
        """
        expires_at = entry.retrieved_at + timedelta(days=self.CACHE_POLICY.ttl_days)
        return datetime.now(timezone.utc) < expires_at

    def _should_head_check(self, entry: EvidenceItem) -> bool:
        """
        Return True if the HEAD-check interval has elapsed since the item was
        last retrieved, indicating we should send a HEAD request to the source
        URL to detect content changes. (REQ-200-ER5)

        For PubMed (head_check_interval=None) this always returns False —
        PubMed uses TTL-only invalidation.
        For grey-lit adapters (30-day TTL + weekly HEAD), this returns True
        once 7 days have passed since entry.retrieved_at.

        [CONCEPT] HTTP HEAD check: a HEAD request retrieves only response headers
        (no body). We use it to check ETag or Last-Modified headers against the
        cached value. If the header changed, we invalidate the cache and re-fetch
        the full content with a GET. This lets us detect source updates without
        paying the bandwidth cost of a full re-download on every check.
        """
        if self.CACHE_POLICY.head_check_interval is None:
            return False
        check_due_at = entry.retrieved_at + self.CACHE_POLICY.head_check_interval
        return datetime.now(timezone.utc) >= check_due_at

    # ------------------------------------------------------------------
    # Abstract method — concrete adapters MUST implement this
    # ------------------------------------------------------------------

    @abstractmethod
    def search(self, params: BaseModel):  # type: ignore[override]
        """
        Execute a search against this adapter's data source.
        Must return RetrievalResult on success, RetrievalError on any failure.
        MUST NOT raise exceptions. (REQ-200-160)
        """
        ...
