# retrieval/

This directory contains the evidence retrieval subsystem. It is active only in Guidance Mode. When the Router assigns GUIDANCE, the pipeline runs two retrieval adapters in priority order, caches their results to disk, and passes the combined output to the Evidence Synthesizer in `agents/`.

Evidence retrieval exists because Nikko's LLM is deliberately not trained on medical content. All health information is externalized here — the model never "knows" it; it is always fetched, cited, and passed through the Synthesizer's confidence scoring before reaching the user.

---

## Executive Summary

| Component | Role |
|-----------|------|
| `base_adapter.py` | Shared cache I/O logic for all adapters (SHA-256 keying, TTL, JSON serialisation) |
| `pubmed_adapter.py` | Queries NCBI PubMed E-utilities for peer-reviewed abstracts; priority 1 |
| `web_search_adapter.py` | DuckDuckGo search across five sanctioned domains + external fallback; priority 2 |
| `__init__.py` | Exports adapters and `ADAPTER_PRIORITY_ORDER` |
| `cache/` | Disk cache directory (auto-created; files are SHA-256-keyed JSON) |
| `static/` | Static reference content (pre-seeded cache for offline/test use) |

---

## Component Breakdown

### `base_adapter.py` — CachedBaseAdapter

**Overview:** A concrete intermediate base class that all retrieval adapters inherit from. It provides the shared cache implementation — SHA-256 keying, JSON read/write, TTL checking, and HEAD-check scheduling — so each concrete adapter only has to implement its own HTTP or corpus-search logic.

**Technical breakdown:**

- **Cache key:** `SHA-256(source_name + "|" + normalised_query)` — normalisation strips whitespace and lowercases. Different adapters querying the same topic produce different keys because the source name is part of the input.
- **Cache file layout:**
  ```json
  {
    "retrieved_at": "2026-05-10T03:00:00+00:00",
    "expires_at":   "2026-05-17T03:00:00+00:00",
    "last_head_check": "2026-05-10T03:00:00+00:00",
    "items": [ ...EvidenceItem dicts... ]
  }
  ```
- **Cache directory:** resolved relative to `retrieval/base_adapter.py` at import time, so the path is stable regardless of the working directory the pipeline is launched from.
- **TTL policy:** each adapter subclass defines its own TTL via a `CachePolicy` object (e.g., 7 days for PubMed, 3 days for WebSearch). TTLs are shorter for web content because it changes more frequently.
- **HEAD-check scheduling:** for long-TTL entries, the adapter periodically issues an HTTP HEAD request to check whether the source URL has changed without downloading the full content again. The interval is defined in the `CachePolicy`.
- **Error propagation:** cache I/O errors are not caught here — they propagate to the concrete adapter, which wraps them in a `RetrievalError`. The pipeline then logs the error and continues with the remaining adapters.
- **Spec refs:** SPEC-200 §5.4, REQ-200-ER5, REQ-200-160.

---

### `pubmed_adapter.py` — PubMedAdapter (Priority 1)

**Overview:** Queries NCBI PubMed via the E-utilities REST API to retrieve peer-reviewed abstracts relevant to the user's query. This is the highest-priority evidence source. Peer-reviewed content from PubMed contributes to `EvidenceTier.PEER_REVIEWED` items, which the Synthesizer scores at the highest confidence tier.

**Technical breakdown:**

- **API surface:**
  - `ESearch` (`esearch.fcgi`) — returns a list of PubMed IDs (PMIDs) matching the query.
  - `EFetch` (`efetch.fcgi`) — returns PubMed XML for a given set of PMIDs. JSON mode is used for ESearch; XML is used for EFetch because the JSON EFetch endpoint omits structured abstract text.
- **Rate limiting:** NCBI enforces 3 requests/second without an API key, 10/second with one. The adapter enforces a 340 ms inter-request delay (≈ 2.9 req/s, safely under the unauthenticated cap). Set `NCBI_API_KEY` as an environment variable to raise the cap.
- **Parsed fields:** PMID, title, abstract text, publication year, journal name. Each becomes an `EvidenceItem` with `evidence_tier=EvidenceTier.PEER_REVIEWED` and `source_tier=SourceTier.PRIMARY`.
- **PubMed URL format:** `https://pubmed.ncbi.nlm.nih.gov/{pmid}/` — constructed and stored in `EvidenceItem.url` for citation rendering.
- **Cache TTL:** 7 days (`PUBMED_CACHE_POLICY`). PubMed content is stable; a week-long TTL avoids hammering the API on repeated similar queries.
- **Query params:** accepts a `PubMedQueryParams` object controlling `max_results`, `article_types`, and `min_year`.
- **Spec refs:** SPEC-200 §5.4, REQ-200-070, REQ-200-071, REQ-200-ER1 through ER5, REQ-200-160.

---

### `web_search_adapter.py` — WebSearchAdapter (Priority 2)

**Overview:** Searches five sanctioned health authority domains via DuckDuckGo, scrapes the full article body from matched URLs, and falls back to unsanitised external results when sanctioned results are insufficient. This is the secondary evidence source — active when PubMed returns too few items for the query.

**Technical breakdown:**

- **Two-phase search:**

  **Phase 1 — Sanctioned domain search:** DuckDuckGo is queried with a combined `site:` restriction across five approved domains:
  1. `healthdirect.gov.au` — Australian Government health information
  2. `betterhealth.vic.gov.au` — Better Health Channel (Victoria)
  3. `who.int` — World Health Organization
  4. `beyondblue.org.au` — Beyond Blue (AU mental health NGO)
  5. `blackdoginstitute.org.au` — Black Dog Institute (AU mental health research)

  For each matched URL, the adapter fetches the full page with `requests` + `BeautifulSoup` and extracts the main article body. Sanctioned results are tagged `SourceTier.PRIMARY`.

  **Phase 2 — External fallback:** Triggered only when Phase 1 returns fewer than `MIN_SANCTIONED_RESULTS` items. Performs a plain DuckDuckGo search without domain restriction. External results are **not scraped** — only the DDG snippet is used as the abstract. They are tagged `SourceTier.SECONDARY`, which causes the Synthesizer to reduce overall confidence per REQ-200-ER3. A `[EXTERNAL — HIGHER SCRUTINY REQUIRED]` prefix is injected into the abstract text.

- **Dependencies:** `duckduckgo-search`, `beautifulsoup4`, `lxml`.
- **Rate limiting:** 0.5 s sleep between successive page scrapes to avoid hammering sanctioned domains.
- **Cache TTL:** 3 days (`WEB_SEARCH_CACHE_POLICY`) — shorter than PubMed because web content changes more frequently.
- **Gap ref:** `G-RETRIEVAL-01` — Beyond Blue and Black Dog Institute were added by Director ruling on 2026-05-10 (not in the original NIKKO-spec.docx).
- **Spec refs:** SPEC-200 §5.4, REQ-200-071, REQ-200-ER1 through ER5, REQ-200-160.

---

### `__init__.py`

Exports the two concrete adapters and `ADAPTER_PRIORITY_ORDER` — the list that tells the pipeline orchestrator which adapters to run and in what sequence.

```python
from retrieval import PubMedAdapter, WebSearchAdapter, ADAPTER_PRIORITY_ORDER
# ADAPTER_PRIORITY_ORDER = [PubMedAdapter, WebSearchAdapter]
```

The pipeline iterates this list in order. PubMed always runs first. If PubMed fails or returns 0 items, WebSearch runs. If all adapters fail, the pipeline logs a warning and continues with `synthesized_evidence = None` (the Verification Supervisor's C5 check will catch this in Guidance Mode and trigger a safe fallback).

---

### `cache/` — Disk Cache

Auto-created directory. Contains JSON files named by SHA-256 hash. Safe to delete — the adapters will re-populate on the next query. Do not commit cache files to version control (`.gitignore` excludes `*.json` in this directory).

---

### `static/` — Static Reference Content

Pre-seeded content for offline use and testing. The pipeline can be pointed at static content to validate the Synthesizer and pipeline logic without live network calls. Structure mirrors the cache format.

---

## Forking Notes

To add a new evidence source:

1. Create a new file in `retrieval/` that subclasses `CachedBaseAdapter`.
2. Implement `search(query: str, params: ...) -> RetrievalResult`.
3. Define a `CachePolicy` with appropriate TTL.
4. Add your adapter class to `ADAPTER_PRIORITY_ORDER` in `retrieval/__init__.py` at the priority position you want.
5. The pipeline orchestrator will pick it up automatically.

The only constraint is that your adapter must return a `RetrievalResult` containing a list of `EvidenceItem` objects matching the schema in `docs/schemas/acp_schemas.py`. The Synthesizer and pipeline do not care what source the items came from.
