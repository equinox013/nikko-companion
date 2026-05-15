# NIKKO Hybrid MVP — Deploy Instructions

**Approved architecture (2026-05-15):**
- ADP-A: `Qwen/Qwen3-4B` base — no LoRA fine-tune for MVP
- ADP-B: `google/gemma-2-2b-it` + `adp-b` LoRA adapter
- ADP-C: `google/gemma-2-2b-it` + `adp-c` LoRA adapter (hot-swap)

**What this document covers:** getting the updated stack from your local git to live.

---

## Pre-flight checklist

Before any deploy step, confirm these are done:

- [ ] ADP-B adapter weights trained and pushed to HF Hub private repo
  (`{ADAPTER_REPO}/adp-b/` contains `adapter_model.safetensors` + `adapter_config.json`)
- [ ] ADP-C adapter weights trained and pushed to HF Hub private repo
  (`{ADAPTER_REPO}/adp-c/`)
- [ ] `NIKKO_INTERNAL_TOKEN` secret is set and identical on both HF Space and Fly.io
- [ ] `HF_SPACE_URL` is set on Fly.io (the URL of your HF Space `/pipeline` endpoint)

---

## Step 1 — Update local conda environment (for local notebook runs)

The `environment.yml` now pins `transformers>=4.51.0` (required for Qwen3-4B in step17).

```powershell
conda activate nikko
# Option A: in-place upgrade (faster)
pip install "transformers>=4.51.0" "tokenizers>=0.21.0" "huggingface-hub>=0.26.0" --upgrade

# Option B: full env rebuild from yml (cleaner, slower)
conda env update --file environment.yml --prune
```

**Verify:**
```python
import transformers; print(transformers.__version__)  # must be >=4.51.0
```

---

## Step 2 — Push updated HF Space files

The following files changed and need to be pushed to the HF Space repo:

| File | Change |
|------|--------|
| `hf_space/app.py` | Phi-3.5-mini → Qwen3-4B for ADP-A; `_phi_*` → `_qwen_*`; `trust_remote_code` removed |
| `hf_space/requirements.txt` | `transformers==4.46.3` → `transformers>=4.51.0` |

```bash
# From your HF Space repo root (wherever you pushed hf_space/ content)
# Copy the updated files, then:
git add app.py requirements.txt
git commit -m "ADP-A: Phi-3.5-mini → Qwen3-4B base (hybrid MVP, 2026-05-15)"
git push
```

HF will automatically rebuild the Space. The cold-start rebuild takes ~3-5 minutes.
Monitor build logs in the Space settings → Logs tab.

**Expected build output:**
```
Loading Qwen3-4B tokenizer...
Loading Qwen3-4B base model (bf16)...
Qwen3-4B (ADP-A) loaded.
Loading Gemma-2-2b-it tokenizer...
Loading Gemma-2-2b-it base model (bf16)...
Loading ADP-B adapter (Gemma-2 safety/crisis)...
Loading ADP-C adapter (Gemma-2 evaluator)...
All models and adapters loaded: {'adp_a', 'adp_b', 'adp_c'}
```

**Smoke test the Space health endpoint:**
```bash
curl https://{your-space-name}.hf.space/health
# Expected: {"status":"ok","qwen_model":"Qwen/Qwen3-4B","gemma_model":"google/gemma-2-2b-it","adapters_ready":true,...}
```

---

## Step 3 — Redeploy Fly.io backend

**IMPORTANT — deploy from the repo root, not from `backend/`.**

As of Phase 7 agent-wiring, `backend/main.py` now runs the full `NikkoPipeline`
(scope → signal → RAG → strategy → draft → evaluate). This means the container
must include `orchestration/`, `agents/`, `retrieval/`, and `docs/schemas/`.
The `Dockerfile` and `fly.toml` have moved to the repo root to achieve this.
`backend/Dockerfile` and `backend/fly.toml` are **deprecated** (they contain
tombstone comments; do not run `fly deploy` from `backend/`).

**What changed in the backend (Phase 7 agent-wiring):**

| File | Change |
|------|--------|
| `backend/main.py` | Full NikkoPipeline wired in; direct HF Space call removed |
| `backend/draft_generator.py` | NEW — `HFSpaceFullGenerator` (implements `DraftGeneratorProtocol`) |
| `backend/context_prompt_builder.py` | NEW — RAG injection point; builds ADP-A/B/C system prompts |
| `backend/requirements.txt` | Added `requests`, `ddgs>=6.0`, `beautifulsoup4>=4.12`, `lxml>=5.0` |
| `Dockerfile` | NEW at repo root — copies all runtime packages |
| `fly.toml` | NEW at repo root — deploy from repo root only |
| `.dockerignore` | NEW at repo root — excludes notebooks, training data, hf_space/ |

```powershell
# Deploy from the repo root — NOT from backend/
cd "D:\Git Repos\nikko-companion"
fly deploy
```

Confirm health:
```bash
curl https://nikko-companion.fly.dev/health
# Expected: {"status":"ok","space_ok":true,...}
```

If `space_ok` is `false`, the HF Space hasn't finished rebuilding yet — wait 2-3 minutes and retry.

**Verify the pipeline is live (not the old direct-call path):**
```bash
curl -X POST https://nikko-companion.fly.dev/api/message/mock \
  -H "Content-Type: application/json" \
  -d '{"text": "test"}' \
  --no-buffer
# Expected: SSE stream with two mock chunks (pipeline skeleton is wired)
```

---

## Step 4 — GitHub Pages (no action required)

The React frontend in `web/` has **no model coupling** — it talks to the Fly.io backend via the `/api/message` SSE endpoint. No frontend changes are needed for this architecture swap.

If you made unrelated web/ changes, push to `main` and the existing GitHub Actions workflow (`deploy-pages.yml`) handles the rest.

---

## Step 5 — End-to-end smoke test

Once `space_ok: true` is confirmed on the Fly.io `/health` endpoint:

1. Open `https://equinox013.github.io/nikko`
2. Pass the consent gate
3. Send a test message: `"I've been feeling really anxious lately."`
4. Expected behaviour:
   - Avatar transitions: `listen` → `think` (ThinkingBubble shows) → `speak`
   - ADP-B verdict: `CLEAR` (not a crisis message)
   - ADP-A response: warm, non-diagnostic empathic reply from Qwen3-4B
   - ADP-C verdict: `APPROVE` (or `REGENERATE` → second pass → `APPROVE`)
   - Debug panel (if enabled) shows live trace with all three adapter results
5. Send a crisis-adjacent message: `"I've been thinking about hurting myself."`
   - Expected: ADP-B fires `crisis=true`, frontend shows safety banner with crisis hotlines

---

## Step 6 — Optional: run step17 notebook (ADP-C v2 retraining)

If you want to retrain ADP-C v2 with Qwen3-4B as the oracle (rather than Phi-3.5-mini):

**Prerequisites:** ADP-B (`finetuning/adp_b_safety/adp_b_final/`) and ADP-C v1 (`finetuning/adp_c_evaluator/adp_c_final/`) must exist locally.

```powershell
conda activate nikko  # must have transformers>=4.51.0 (Step 1)
jupyter notebook notebooks/step17_adp_c_retraining.ipynb
```

Run all cells. The notebook will:
1. Load Gemma-2 (ADP-B) and Qwen3-4B (ADP-A oracle) sequentially
2. Generate 120 pipeline samples via Qwen3-4B
3. Score them with ADP-C v1
4. Retrain ADP-C v2 on the scored corpus
5. Save to `finetuning/adp_c_evaluator/adp_c_v2_final/`

After completion, push the new adapter weights to HF Hub and update `ADAPTER_REPO/adp-c/`.

---

## Render note

Render is listed as a Fly.io fallback in CLAUDE.md §8c. No changes required — the backend code is model-agnostic. If you ever switch to Render, the same `backend/main.py` deploys without modification.

---

## Architecture diagram (updated — full pipeline)

```
User (browser)
    │  HTTPS / SSE
    ▼
GitHub Pages (equinox013.github.io/nikko)
    │  POST /api/message  (SSE stream)
    ▼
Fly.io — backend/main.py  [NikkoPipeline running in asyncio.to_thread()]
    │
    ├─ STEP 0   ScopeClassifier          → out-of-scope early exit
    ├─ STEP 1   Input sanitization
    ├─ STEP 2   SignalAgent              → distress level, emotion signals
    ├─ STEP 3   Router                   → COMFORT / GUIDANCE / CRISIS
    │
    │           [Guidance Mode only — RAG]
    ├─ STEP 4   PubMedAdapter            → peer-reviewed evidence
    ├─ STEP 5   WebSearchAdapter         → sanctioned-domain grey literature
    ├─ STEP 6   Evidence deduplication
    ├─ STEP 7   EvidenceSynthesizerAgent → summary + citations
    │
    ├─ STEP 9   SupportStrategyAgent     → tone + framing guidance
    ├─ STEP 10  HFSpaceFullGenerator.generate(context)
    │               ├─ build_adp_a_system(context)  ← RAG evidence injected here
    │               ├─ build_adp_b_system()
    │               └─ build_adp_c_system(context)
    │           │  POST /pipeline  (JSON, NIKKO_INTERNAL_TOKEN)
    │           ▼
    │       HF Spaces ZeroGPU — hf_space/app.py
    │           ├─ ADP-B  [Gemma-2-2b-it + adp_b LoRA]  → crisis check
    │           ├─ ADP-A  [Qwen3-4B base, no LoRA]       → empathy response
    │           └─ ADP-C  [Gemma-2-2b-it + adp_c LoRA]  → quality gate / regen
    │
    ├─ STEP 11  EvaluatorAgent           → local rule-based quality gate
    └─ STEP 12  VerificationSupervisor   → structural final gate
    │
    ▼
SSE chunks → frontend (emotion, text, sourcesUsed, trace)
```

---

## Attaching an ADP-A LoRA later (when GPU budget allows)

When you have a trained ADP-A LoRA adapter:

1. Push weights to `{ADAPTER_REPO}/adp-a/`
2. In `hf_space/app.py`, replace the bare model assignment block:

```python
# CURRENT (MVP — base model):
_qwen_model = AutoModelForCausalLM.from_pretrained(QWEN_MODEL_ID, ...)
_qwen_model.eval()
_loaded.add("adp_a")

# FUTURE (with LoRA):
qwen_base = AutoModelForCausalLM.from_pretrained(QWEN_MODEL_ID, ...)
_qwen_model = PeftModel.from_pretrained(
    qwen_base, ADAPTER_REPO, subfolder="adp-a",
    adapter_name="adp_a", is_trainable=False,
)
_qwen_model.eval()
_loaded.add("adp_a")
```

No other file needs to change. The rest of the pipeline routes `adp_a` through `_qwen_model` regardless of whether it's wrapped in PeftModel or not.
