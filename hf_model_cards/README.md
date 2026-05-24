# hf_model_cards/

Source files for the three NIKKO adapter model cards on HuggingFace Hub.
These are **not** deployed automatically — each README.md must be uploaded manually to its respective HF Hub repo.

## Adapter repos

| Adapter | HF Hub repo | Local source |
|---------|-------------|--------------|
| ADP-A (Empathy Response) | [equinox013/nikko-adp-a](https://huggingface.co/equinox013/nikko-adp-a) | `nikko-adp-a/README.md` |
| ADP-B (Safety Classifier) | [equinox013/nikko-adp-b](https://huggingface.co/equinox013/nikko-adp-b) | `nikko-adp-b/README.md` |
| ADP-C (Response Evaluator) | [equinox013/nikko-adp-c](https://huggingface.co/equinox013/nikko-adp-c) | `nikko-adp-c/README.md` |

## Upload procedure

1. Go to the adapter repo on HF Hub (links above).
2. Click **Files** → **README.md** → **Edit**.
3. Paste the contents of the corresponding local README.md.
4. Commit directly to `main`.

The YAML frontmatter block at the top of each README is parsed by HF Hub to populate the model card metadata (license, base model, tags, pipeline tag). It must be present and valid.

## When to update

Update the model card here first, then re-upload to HF Hub whenever:
- A new training phase is completed (e.g., Phase 4.2 DPO)
- Smoke test results change
- The adapter's intended use or limitations change
- The HF Hub repo structure changes (e.g., subfolder layout for shared-base adapters)
