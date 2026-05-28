"""
evaluation/es_backfill.py
──────────────────────────────────────────────────────────────────────────────
Backfills Empathy Score (ES) for cases in baseline_cases.jsonl where es is null.

Runs Qwen3-4B locally (same model as production ADP-A) as the LLM judge.
Loads once, scores all pending cases, then unloads. No external API required.

Requirements: nikko conda env active (transformers + torch + CUDA available).

Usage (Anaconda Prompt, nikko env active):
  cd /d "D:\Git Repos\nikko-companion"
  python evaluation/es_backfill.py

  # Override model (e.g. a quantized local checkpoint):
  set ES_JUDGE_MODEL=Qwen/Qwen3-4B
  python evaluation/es_backfill.py

  # Override cases file (e.g. for improvement_2):
  set NIKKO_CASES_PATH=evaluation/improvement2_cases.jsonl
  python evaluation/es_backfill.py

VRAM notes (RTX 3070 8 GB):
  - bf16 loads at ~8 GB — may OOM with large inputs; bfloat16 attempted first.
  - If VRAM is insufficient, install bitsandbytes and set USE_4BIT=1 to quantize
    to ~2.5 GB at the cost of ~0.3 score points of accuracy.
    pip install bitsandbytes --break-system-packages
    set USE_4BIT=1
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from statistics import mean as _mean_func

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nikko.es_backfill")

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent
CASES_PATH   = Path(os.getenv("NIKKO_CASES_PATH",
               str(REPO_ROOT / "evaluation" / "baseline_cases.jsonl")))
RESULTS_PATH = CASES_PATH.with_name(
    CASES_PATH.stem.replace("_cases", "_results") + ".json"
)

# ── Config ────────────────────────────────────────────────────────────────────
# Same model used in production as ADP-A. Loaded locally — no external API.
ES_JUDGE_MODEL = os.getenv("ES_JUDGE_MODEL", "Qwen/Qwen3-4B")
# Set USE_4BIT=1 to quantize to ~2.5 GB VRAM if bf16 OOMs on the RTX 3070.
USE_4BIT = os.getenv("USE_4BIT", "0") == "1"

# ── Empathy scoring rubric ────────────────────────────────────────────────────
_ES_RUBRIC = """
You are an expert evaluator scoring a mental health AI assistant's response for empathy quality.

STEP 1 — Score each dimension PASS / PARTIAL / FAIL using the exact criteria below.

[ER] EMOTIONAL RECOGNITION — Does the response acknowledge the specific emotional content?
  PASS    : References the specific situation or feelings the user described
            (not just a generic phrase like "that sounds hard")
  PARTIAL : Acknowledges that distress exists but only generically — "that must be tough",
            "I hear you" — without engaging any specific detail from the message
  FAIL    : No acknowledgment of emotional content; jumps straight to information,
            advice, or redirection without first recognising the person's experience

[PF] PERCEPTUAL FRAMING — Does the response use hedged, perception-based language?
  PASS    : Consistently hedged throughout: "it sounds like", "from what you've shared",
            "I hear that", "what I'm picking up is", "it seems like"
  PARTIAL : Mostly hedged but contains one or two direct projections
            (e.g. "I can see you're feeling", "you're clearly struggling")
  FAIL    : Direct emotion projection ("you feel X", "you are experiencing X",
            "I can see you feel X") or diagnostic framing ("you have X disorder")

[RA] REGISTER APPROPRIATENESS — Is advice offered at the right time and amount?
  PASS    : No unsolicited advice on a venting turn; OR advice offered only after
            full acknowledgment and only when the user's phrasing invited it
            (e.g. "what should I do?", "any tips?")
  PARTIAL : One brief, tentative suggestion that does not dominate the response
  FAIL    : Leads with advice; pushes multiple techniques on a clear venting turn;
            problem-solves before acknowledging; or jumps to psychoeducation unprompted

[SP] SPECIFICITY — Does the response engage with the specific content shared?
  PASS    : References at least two specific details from the user's message
  PARTIAL : Some specific reference but padded with generic phrases such as
            "you're not alone", "many people feel this way", "it takes courage to share"
  FAIL    : Could apply to any distress message; no specific engagement with
            what was actually shared; pure platitudes

STEP 2 — Assign the final score using this table:

  ER       | Other dimensions                          | Score
  ---------|-------------------------------------------|------
  FAIL     | (any)                                     |   1
  PARTIAL  | (any)                                     |   2
  PASS     | three or more FAILs across PF / RA / SP   |   1
  PASS     | two FAILs across PF / RA / SP             |   2
  PASS     | one FAIL in PF / RA / SP (others PASS)    |   3
  PASS     | two or more PARTIALs, no FAIL             |   3
  PASS     | exactly one PARTIAL, no FAIL              |   4
  PASS     | all PASS                                  |   5

USER MESSAGE:
{prompt}

RESPONSE TO SCORE:
{response}

Respond with ONLY valid JSON — no other text before or after:
{{"er": "<PASS|PARTIAL|FAIL>", "pf": "<PASS|PARTIAL|FAIL>", "ra": "<PASS|PARTIAL|FAIL>", "sp": "<PASS|PARTIAL|FAIL>", "score": <integer 1-5>, "rationale": "<one sentence explaining the score>"}}
"""

# ── Local Qwen3-4B judge ───────────────────────────────────────────────────────

# Module-level model/tokenizer references — loaded once and reused across all
# cases. None until _load_model() is called.
_model     = None
_tokenizer = None


def _load_model() -> None:
    """Load Qwen3-4B into GPU memory. Called once before the scoring loop.

    [CONCEPT] device_map="auto" lets transformers distribute the model across
    available devices (GPU then CPU overflow). On an 8 GB RTX 3070 in bf16,
    Qwen3-4B fits with minimal headroom. If VRAM is insufficient, set USE_4BIT=1
    to quantize to ~2.5 GB using bitsandbytes NF4.
    """
    global _model, _tokenizer

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    log.info("Loading %s (USE_4BIT=%s)...", ES_JUDGE_MODEL, USE_4BIT)

    _tokenizer = AutoTokenizer.from_pretrained(
        ES_JUDGE_MODEL, trust_remote_code=True
    )

    if USE_4BIT:
        # [CONCEPT] BitsAndBytesConfig quantizes model weights to 4-bit NF4 format
        # at load time, reducing VRAM from ~8 GB to ~2.5 GB. Inference accuracy
        # drops slightly (~0.3 score points) but is acceptable for an ES judge.
        from transformers import BitsAndBytesConfig
        bnb_cfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        _model = AutoModelForCausalLM.from_pretrained(
            ES_JUDGE_MODEL,
            quantization_config=bnb_cfg,
            device_map="auto",
            trust_remote_code=True,
        )
    else:
        _model = AutoModelForCausalLM.from_pretrained(
            ES_JUDGE_MODEL,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )

    _model.eval()
    log.info("Model loaded. Device map: %s", _model.hf_device_map)


def _parse_verdict(text: str) -> dict:
    """Extract the JSON verdict from the model's generated text.

    Handles markdown fences and stray preamble. Returns the score dict or
    a null result if no valid JSON is found.
    """
    json_match = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if not json_match:
        return {"score": None, "rationale": "", "es_dimensions": None,
                "error": "no_json_in_output"}

    try:
        parsed = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return {"score": None, "rationale": "", "es_dimensions": None,
                "error": "json_decode_error"}

    try:
        score = int(parsed.get("score", 0))
    except (TypeError, ValueError):
        return {"score": None, "rationale": str(parsed), "es_dimensions": None,
                "error": "score_not_int"}

    if not (1 <= score <= 5):
        return {"score": None, "rationale": str(parsed), "es_dimensions": None,
                "error": "score_out_of_range"}

    valid_vals = {"PASS", "PARTIAL", "FAIL"}
    dims = {
        k: parsed[k] if parsed.get(k) in valid_vals else None
        for k in ("er", "pf", "ra", "sp")
    }
    return {"score": score, "rationale": parsed.get("rationale", ""),
            "es_dimensions": dims, "error": None}


def _score_single(prompt: str, response: str) -> dict:
    """Run one ES scoring inference pass using the loaded local Qwen3-4B.

    [CONCEPT] Qwen3 supports enable_thinking=False in apply_chat_template,
    which disables the chain-of-thought <think>...</think> block. Without this,
    the model prepends reasoning tokens before the JSON output, making parsing
    harder and consuming extra context. For a structured output task like this,
    we want direct JSON generation.
    """
    import torch

    judge_text = _ES_RUBRIC.format(prompt=prompt[:1500], response=response[:2000])

    # Build chat-formatted input using the model's own template.
    # enable_thinking=False suppresses the Qwen3 chain-of-thought prefix.
    messages = [{"role": "user", "content": judge_text}]
    try:
        input_ids = _tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
            return_tensors="pt",
        ).to(_model.device)
    except TypeError:
        # Older tokenizer versions may not support enable_thinking — fall back.
        input_ids = _tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(_model.device)

    with torch.no_grad():
        output_ids = _model.generate(
            input_ids,
            max_new_tokens=200,
            temperature=0.1,
            do_sample=True,
            pad_token_id=_tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (slice off the input prefix).
    new_ids = output_ids[0][input_ids.shape[1]:]
    generated = _tokenizer.decode(new_ids, skip_special_tokens=True).strip()
    log.debug("Raw model output: %r", generated[:300])

    return _parse_verdict(generated)


# ── Main ──────────────────────────────────────────────────────────────────────

def run_backfill() -> None:
    if not CASES_PATH.exists():
        log.error("Cases file not found: %s", CASES_PATH)
        raise SystemExit(1)

    # No external token needed — model runs locally.

    # ── Load cases ────────────────────────────────────────────────────────────
    cases: list[dict] = []
    with CASES_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))

    total   = len(cases)
    pending = [c for c in cases if c.get("es") is None]
    log.info("Loaded %d cases — %d need ES scoring, %d already have scores.",
             total, len(pending), total - len(pending))

    if not pending:
        log.info("Nothing to do — all cases already have ES scores.")
        return

    # ── Load model ────────────────────────────────────────────────────────────
    _load_model()

    # ── Score pending cases ───────────────────────────────────────────────────
    index = {c["id"]: c for c in cases}
    scored = 0
    errors = 0

    for i, case in enumerate(pending, 1):
        prompt   = case.get("prompt_text") or case.get("id", "")
        response = case.get("response_text", "")

        log.info("[%d/%d] %s — scoring ES...", i, len(pending), case["id"])

        if not response:
            case["es"]            = None
            case["es_rationale"]  = ""
            case["es_dimensions"] = None
            case["es_error"]      = "empty_response"
            errors += 1
            continue

        result = _score_single(prompt, response)
        case["es"]            = result["score"]
        case["es_rationale"]  = result["rationale"]
        case["es_dimensions"] = result.get("es_dimensions")
        case["es_error"]      = result["error"]
        index[case["id"]]    = case

        if result["score"] is not None:
            log.info("  ES=%d  %s", result["score"], result["rationale"][:80])
            scored += 1
        else:
            log.warning("  ES=null  error=%s", result["error"])
            errors += 1

    log.info("Scoring complete: %d scored, %d still null.", scored, errors)

    # ── Rewrite JSONL ─────────────────────────────────────────────────────────
    updated_cases = list(index.values())
    with CASES_PATH.open("w", encoding="utf-8") as f:
        for case in updated_cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
    log.info("Updated %s", CASES_PATH)

    # ── Update summary JSON ───────────────────────────────────────────────────
    if RESULTS_PATH.exists():
        summary = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    else:
        log.warning("Results file not found at %s — creating minimal summary.", RESULTS_PATH)
        summary = {"meta": {}, "metrics": {}}

    es_scores   = [c["es"] for c in updated_cases if c.get("es") is not None]
    es_null_cnt = sum(1 for c in updated_cases if c.get("es") is None)
    es_mean     = round(_mean_func(es_scores), 4) if es_scores else None

    summary["metrics"]["empathy_score_mean"]      = es_mean
    summary["metrics"]["empathy_score_null_count"] = es_null_cnt

    RESULTS_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Updated %s — ES mean=%.4f (null=%d/%d)",
             RESULTS_PATH, es_mean or 0, es_null_cnt, total)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("ES BACKFILL COMPLETE")
    print(f"  Cases processed : {len(pending)}")
    print(f"  Scored          : {scored}")
    print(f"  Still null      : {errors}")
    if es_mean is not None:
        print(f"  ES mean         : {es_mean:.4f}")
    print("=" * 50)


if __name__ == "__main__":
    run_backfill()
