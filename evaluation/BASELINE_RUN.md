# Phase 6 Baseline — Execution Guide

Run this once to establish the Improvement 1 baseline before any model changes.
All nine metrics are written to `evaluation/baseline_results.json`.

---

## Prerequisites

1. **nikko conda environment active**
   ```powershell
   conda activate nikko
   ```

2. **HF_TOKEN set** — needed for Empathy Score (ES) via HF Inference API free tier.
   ```powershell
   $env:HF_TOKEN = "hf_..."   # your HuggingFace token
   ```

3. **Render backend reachable** — confirm it's not sleeping:
   ```powershell
   curl https://nikko-companion.onrender.com/health
   ```
   Expected: `{"status":"ok","space_ok":true,...}`.
   If `space_ok=false`, wait 60-90s for Modal/HF Space to warm up, then retry.

---

## Run

```powershell
cd "D:\Git Repos\nikko-companion"
python evaluation/harness.py
```

The harness will:
1. Probe `/health` — aborts if backend unreachable.
2. Fetch ADP-A/B/C commit hashes from HF Hub.
3. POST each of 100 test cases to `/api/message` (with retry-backoff).
4. Score SCS, ASIS, EGS, CRC, routing accuracy, regen rate deterministically.
5. Call HF Inference API (Llama-3.1-8B-Instruct) for Empathy Score on each case.
6. Write results.

**Expected runtime**: 30–60 min depending on Render warm/cold state and HF API rate limits.

---

## Expected output

```
evaluation/baseline_results.json   ← nine-metric aggregate summary
evaluation/baseline_cases.jsonl    ← per-case detail (one JSON line each)
```

---

## Interpreting the summary

| Metric | Key in JSON | Notes |
|--------|-------------|-------|
| ES | `empathy_score_mean` | 1–5 scale. Null count reported separately. |
| SCS | `safety_compliance_rate` | Proportion with 0 red-line violations. 1.0 = all clean. |
| EGS | `evidence_grounding_mean` | GUIDANCE cases only. 1.0 = sources returned. |
| CRC | `crisis_response_correctness` | Crisis cases only. 1.0 = bridging + resources + no delay. |
| ASIS | `agent_system_integrity_mean` | 0–1. <1.0 indicates pipeline structural failures. |
| Regen rate | `regen_rate` | % of responses that triggered ≥1 regen pass. |
| FP regen rate | `false_positive_regen_rate` | Regens on DPO cases with a known-good anchor. Requires human review. |
| Routing accuracy | `routing_accuracy` | ADP-B routing vs ground truth labels. |
| Latency | `latency_p50_s`, `latency_p95_s` | Wall-clock seconds. Cold-start cases inflate p95. |

---

## If ES is all null

HF Inference API free tier may gate the model behind a queue or require model
warm-up. If all ES scores are null:
1. Check `es_error` in `baseline_cases.jsonl` — look for `"HTTP 503"` (model loading) or `"HTTP 429"` (rate limit).
2. For 503: re-run with `NIKKO_BACKEND_URL` pointing to mock to avoid re-running backend, or wait 5 min for model to load.
3. Alternative judge: set `ES_JUDGE_MODEL` in harness.py to `"HuggingFaceH4/zephyr-7b-beta"` (smaller, usually warm on free tier).

---

## No model changes during baseline

Per §9.4: the baseline MUST be recorded before any model is changed. Do not
retrain, swap adapters, or push to HF Hub until `baseline_results.json` is
committed. This is the comparison state for Improvements 2, 3, and 4.

After the run, commit:
```powershell
git add evaluation/baseline_results.json evaluation/baseline_cases.jsonl
git add evaluation/test_set.json evaluation/build_test_set.py evaluation/harness.py
git commit -m "Phase 6: add evaluation baseline harness and test set (100 cases)"
```
