# Lightning.ai Setup Guide — NIKKO Phase 4.1 Cloud Retraining

**Audience:** Nicholas (Director), setting up Lightning.ai to run steps 20–25.  
**Prerequisite:** GitHub repo connected to Lightning.ai (you confirmed this is done).  
**Platform:** Lightning.ai Studio, A10G GPU (24 GB VRAM), background job execution.

---

## Overview

Six notebooks run in pairs — data prep first, then training:

| Pair | Data prep | Training | Adapter output |
|------|-----------|----------|---------------|
| ADP-A (Qwen3-4B) | Step 20 | Step 21 | `equinox013/nikko-adp-a` on HF Hub |
| ADP-B (Gemma-2-2b-it) | Step 22 | Step 23 | `equinox013/nikko-adp-b` on HF Hub |
| ADP-C (Gemma-2-2b-it) | Step 24 | Step 25 | `equinox013/nikko-adp-c` on HF Hub |

Each pair is independent — ADP-B and ADP-C can run concurrently, but ADP-A
must complete Step 20 before Step 21 runs, and so on.

**Recommended run order for a single A10G Studio:**
1. Step 24 (ADP-C data prep) → Step 25 (ADP-C training) — fastest, verify setup
2. Step 22 (ADP-B data prep) → Step 23 (ADP-B training)
3. Step 20 (ADP-A data prep) → Step 21 (ADP-A training) — longest

---

## Step 1 — Create a Lightning.ai Studio

1. Log into [lightning.ai](https://lightning.ai).
2. Click **New Studio** → choose **Jupyter Notebook** as the environment.
3. Under **Compute**, select **A10G** (24 GB GPU). This is the correct tier — do not
   select T4 (16 GB) or V100; the A10G is required for the batch sizes configured in
   the training notebooks.
4. Under **Storage**, set at least **50 GB** to accommodate model weights and checkpoints.
5. Name the Studio (e.g. `nikko-retraining`).

---

## Step 2 — Clone the Repo

Since your GitHub is already connected to Lightning.ai:

1. In the Studio terminal (or a notebook cell), run:
   ```bash
   git clone https://github.com/equinox013/nikko-companion.git \
       /teamspace/studios/this_studio/nikko-companion
   ```
2. Verify the clone:
   ```bash
   ls /teamspace/studios/this_studio/nikko-companion/notebooks/step20*.ipynb
   ```
   You should see `step20_adp_a_cloud_data_preparation.ipynb`.

**Why this path?** All six notebooks are hardcoded to `BASE_DIR = Path("/teamspace/studios/this_studio/nikko-companion")`. If you clone somewhere else, update `BASE_DIR` in Cell 1 of each notebook.

---

## Step 3 — Set Your HF Hub Token as a Secret

The training notebooks push adapter weights to your private HF Hub repos after
training. They read the token from the `HF_TOKEN` environment variable.

1. In Lightning.ai, go to **Settings → Secrets**.
2. Add a secret named `HF_TOKEN` with your HuggingFace write token.
   - Get your token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens).
   - The token needs **write** access to the target repos.
3. Lightning.ai automatically injects secrets as environment variables when the
   Studio starts — no code change required.

**What if you skip this?** The notebooks still train and save adapters locally to
`finetuning/*/cloud_final/`. They just won't push to HF Hub, so you'd need to
download the adapters manually and upload to your HF repos.

---

## Step 4 — Create Target HF Hub Repos (if not already existing)

Each training notebook pushes to a specific repo. The default repo names in the
notebooks are:

| Adapter | `HF_OUTPUT_REPO` variable | Where to update |
|---------|--------------------------|----------------|
| ADP-A | `equinox013/nikko-adp-a` | Cell 1 of Step 21 |
| ADP-B | `equinox013/nikko-adp-b` | Cell 1 of Step 23 |
| ADP-C | `equinox013/nikko-adp-c` | Cell 1 of Step 25 |

If these repos don't exist:
1. Go to [huggingface.co/new](https://huggingface.co/new).
2. Create each as a **private** model repo.
3. Update the `HF_OUTPUT_REPO` variable in the relevant training notebook if your
   username differs from `equinox013`.

---

## Step 5 — Install Dependencies

Run this in a terminal or the first cell of any notebook before running the full
notebook. Lightning.ai's Jupyter environment has PyTorch pre-installed, but the
ML training libraries need to be added:

```bash
pip install \
    transformers==4.46.3 \
    accelerate==1.1.0 \
    peft==0.13.2 \
    trl==0.11.4 \
    datasets==3.1.0 \
    bitsandbytes \
    sentencepiece \
    protobuf \
    huggingface_hub \
    --quiet
```

**Important notes:**
- `bitsandbytes` is safe to install on Lightning.ai — the persistent CUDA context
  means it won't crash at import time. This is the opposite of HF ZeroGPU.
- You do NOT need `--break-system-packages` on Lightning.ai (that flag is
  Windows/conda specific).
- Pin the transformers/peft/trl versions above — they match the production stack.
  Newer versions of `trl` changed the `SFTConfig` API in ways that break the
  training configs in the notebooks.

---

## Step 6 — Run the Notebooks

### Option A: Interactive (manual cell-by-cell)

Open the notebook in Jupyter, run cells one at a time. Good for the first run
to verify each section works before committing to the full training loop.

### Option B: Background Job (recommended for training runs)

Lightning.ai supports running notebooks as background jobs so the Studio can be
closed mid-run without interrupting training.

1. In the Studio, navigate to the notebook file.
2. Click **Run as job** (top-right menu or the ⚡ icon).
3. Lightning.ai executes all cells top-to-bottom and streams logs to the job dashboard.
4. The adapters are saved to `finetuning/*/cloud_final/` and pushed to HF Hub
   when the push cell runs.

**Why background jobs matter:** The training notebooks take 20–60 minutes each.
Background execution means you can close your laptop and check results later — the
A10G container keeps running without your browser session.

### Option C: Run from terminal

```bash
cd /teamspace/studios/this_studio/nikko-companion
jupyter nbconvert --to notebook --execute \
    notebooks/step24_adp_c_cloud_data_preparation.ipynb \
    --output notebooks/step24_adp_c_cloud_data_preparation_executed.ipynb
```

---

## Step 7 — Recommended Run Order and Expected Times

| Step | Notebook | Expected time (A10G) | VRAM peak |
|------|----------|---------------------|-----------|
| 24 | ADP-C data prep | 5–10 min (no GPU needed) | <1 GB |
| 25 | ADP-C training | **15–25 min** | ~8–10 GB |
| 22 | ADP-B data prep | 5 min (no GPU) | <1 GB |
| 23 | ADP-B training | **20–35 min** | ~8–10 GB |
| 20 | ADP-A data prep | 30–50 min (ADP-C oracle scoring) | ~6–8 GB |
| 21 | ADP-A training | **25–45 min** | ~10–14 GB |

**Total estimated time:** ~2–3 hours for all six notebooks run sequentially.

Note that the data prep notebooks (20, 22, 24) can run on CPU — you can use a
cheaper CPU Studio tier for those and only spin up the A10G for training notebooks
(21, 23, 25). This reduces cost by ~40%.

---

## Step 8 — Verify Adapter Availability on HF Hub

After each training notebook completes:

1. Go to `huggingface.co/equinox013/nikko-adp-[a/b/c]`.
2. Verify that `adapter_model.safetensors` and `adapter_config.json` are present.
3. Check that `adapter_config.json` shows the correct `base_model_name_or_path`:
   - ADP-A: `Qwen/Qwen3-4B`
   - ADP-B: `google/gemma-2-2b-it`
   - ADP-C: `google/gemma-2-2b-it`

---

## Step 9 — Update HF Space to Use Cloud Adapters

Once all three adapters are on HF Hub, update `hf_space/app.py` to load from
the new cloud adapter repos rather than the local paths or previous adapter IDs.

In `hf_space/app.py`, find the adapter load calls and update the repo strings:
```python
# ADP-A (Qwen3-4B) — update to cloud adapter
ADP_A_ADAPTER = "equinox013/nikko-adp-a"   # was bare base or previous path

# ADP-B / ADP-C (Gemma-2-2b-it)
ADP_B_ADAPTER = "equinox013/nikko-adp-b"
ADP_C_ADAPTER = "equinox013/nikko-adp-c"
```

**This is the production integration step** — do not make this change until the
smoke tests in steps 21, 23, and 25 all pass.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: bitsandbytes` | Not installed | Run the `pip install` command in Step 5 |
| `AssertionError: Repo not found at /teamspace/studios/this_studio/nikko-companion` | Wrong clone path | Update `BASE_DIR` in Cell 1 of the failing notebook |
| `HF_TOKEN not set` warning | Secret not configured | Follow Step 3 |
| Training loss stuck at 3.5+ after 10 steps | Dataset too small or wrong format | Check that the data prep notebook ran cleanly and the JSONL has > 50 records |
| CUDA OOM during training | A10G not selected | Verify Studio compute is A10G, not T4 |
| `load_best_model_at_end` error about eval_steps | Eval/save step mismatch | This is already fixed in the notebooks; if it fires, check you're running the Step 23/25 versions not the older Step 16/12 |
| Push to HF Hub 403 | Token missing write scope | Generate a new token with write access at HF settings |

---

## What the notebooks do NOT do (manual steps required)

1. **Create HF Hub repos** — you need to create them once manually (Step 4 above).
2. **Update `hf_space/app.py` adapter paths** — manual update required after all
   three adapters are pushed and smoke-tested (Step 9 above).
3. **Run Phase 6 evaluation harness** — after new adapters are deployed, re-run
   the evaluation suite against the live stack.
