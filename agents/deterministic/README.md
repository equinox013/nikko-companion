# agents/deterministic/ — Archived Deterministic Agents

**Archived:** 2026-05-21  
**Archived by:** NIKKO Engineering Collective (Lead Architect)  
**Reason:** Superseded by hybrid LLM-backed implementations in `agents/`. The files in this directory are the **sole-rule-engine versions** — retained as the canonical reference for the deterministic backbone that the hybrid agents are built on top of.

---

## What is in this folder

| File | Agent | Phase |
|------|-------|-------|
| `scope_classifier.py` | Scope Classifier (Step 0) | Phase 3 impl + Phase 6 bug fixes |
| `signal_agent.py` | Signal Agent (Step 2) | Phase 3 impl |
| `support_strategy_agent.py` | Support Strategy Agent (Step 4) | Phase 3 impl |

---

## Why these were archived (not deleted)

The deterministic rule engines are **not replaced** — they are the non-overridable safety backbone of the hybrid architecture. The new `agents/` implementations wrap these rule engines with an LLM enrichment pass, but the rule results take strict priority in all safety-critical decisions.

Archiving rather than deleting preserves:
- Rollback path if the hybrid approach introduces regression
- Diff surface to audit exactly what the hybrid versions change
- Historical record for spec traceability (REQ-IDs in inline comments remain accurate)

---

## Deterministic architecture (what was here)

### Scope Classifier (`scope_classifier.py`)
Pure regex-based gate. Assigns `IN_SCOPE`, `OUT_OF_SCOPE`, or `AMBIGUOUS` before any LLM is involved.

**Key design decisions preserved in hybrid:**
- Weighted regex scoring: `_blend_confidence(dominant, competing) = dominant * (1 - 0.5 * competing)`
- Asymmetric error policy (REQ-200-SC3): ambiguous messages pass through to the pipeline rather than being silently dropped — a distress-coded message being wrongly blocked is a safety failure
- Thresholds: `IN_SCOPE ≥ 0.40`, `OUT_OF_SCOPE > 0.60`, else `AMBIGUOUS`
- `can you help me` alone = weight 0.30 → AMBIGUOUS (not IN_SCOPE); only passes if emotional context raises total above 0.40

**Bug fixes applied before archival (2026-05-21):**
- `what(?:'s| is) the capital of` — contraction handling for "what's" (REQ-200-SC2)
- Extended coding verb/object list to catch `code|build|create|develop|make` + `website|web app|application|dashboard` etc.
- Added compound pattern: `\b(help me|could you|can you)\s+(code|build|create|...)\s+(a\s+)?(website|...)\b` at weight 0.85

### Signal Agent (`signal_agent.py`)
Extracts psychological signals from user text using four pattern tables:
- Emotional indicators (distress vocabulary)
- Cognitive indicators (thought patterns)
- Behavioral indicators (action cues)
- Risk indicators (active/acute/passive risk keys)

**Non-overridable safety anchors preserved in hybrid:**
- Active/acute risk keys (`risk.active.*`, `risk.acute.*`) force `distress_level=CRISIS` regardless of LLM output
- Passive risk keys (`risk.passive.*`) set `passive_risk_flag=True` for the L2 escalation rule (REQ-100-PR1)
- Confidence formula: `0.50 + (match_count * 0.06)` capped at 0.82; crisis=0.92; passive=0.85

**What the LLM adds on top (hybrid only):**
- Tone note: one sentence capturing emotional register the regex cannot express (e.g. "user sounds exhausted and resigned, not acutely distressed")
- Distress level can be nudged up if LLM reads higher severity than regex sum implies — but LLM can NEVER downgrade a CRISIS ruling from the rule engine

### Support Strategy Agent (`support_strategy_agent.py`)
Maps `(OperationalMode, DistressLevel)` → `{tone_guidance, framing_strategy, response_constraints}` via a static 8-cell `_STRATEGY_TABLE`.

**Non-overridable rules preserved in hybrid:**
- `crisis_bypass()` always returns `_CRISIS_STRATEGY` — no LLM ever touches Crisis Mode strategy
- Mode and distress_level are always taken from the Router and Signal Agent respectively — LLM cannot change them
- LLM enrichment is additive only: a `tone_note` field and optional constraint refinements are appended, not substituted

---

## Hybrid architecture (what replaced these)

The production agents in `agents/` implement the following fork:

```
Render (no GPU):
  NIKKO_LOCAL_LLM=false → deterministic rule engine only (same as these archived files)

Modal pipeline (GPU available):
  NIKKO_LOCAL_LLM=true (default) → rule engine runs first, then:
    - Signal: Qwen3-4B adds tone_note + optional distress nudge (max_new_tokens=256)
    - Strategy: Qwen3-4B enriches tone/framing from base table (max_new_tokens=128)
    - Scope: Qwen3-4B resolves AMBIGUOUS cases only (max_new_tokens=64)
  LLM output is merged into rule output — rule anchors are never overridden
```

Modal hosts the LLM enrichment as a preamble within the existing `run_pipeline()` GPU session, using the already-loaded Qwen3-4B model. Zero additional cold start cost.

---

## Do not import from this folder in production code

These files are an archive, not a library. They are not on `sys.path` and should not be imported. If you need to reference deterministic logic, import from `agents/` directly.
