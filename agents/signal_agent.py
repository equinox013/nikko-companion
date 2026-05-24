"""
agents/signal_agent.py
======================
Psychological Signal Agent — Step 2 of the NIKKO pipeline (first LLM call).

Spec source  : SPEC-100, SPEC-200 §5.2
               REQ-200-050 through REQ-200-053
               REQ-100-090 through REQ-100-093
               REQ-700-032 (output immutability)
Phase        : 3 — Agent Definitions (Implementation)
Authority    : LOW — emits SignalPayload to Router only. No other downstream
               communication is permitted. (REQ-200-052/053)

Role
----
Receives a sanitized user message (and optional in-session conversation
history) and returns a structured SignalPayload describing detected
psychological signals. The Router consumes this payload and assigns a mode.

Output immutability
-------------------
Once a SignalPayload is returned from `analyze()`, no downstream agent may
alter it. (REQ-700-032) Enforcement is by convention in Phase 3; a frozen
model config can be added when the Phase 2 schema is next revised.

Model strategy
--------------
Phase 3 uses Qwen2.5-3B-Instruct in zero-shot mode with the system prompt
from agent_prompts.md §3.1. It produces well-structured JSON and fits in
8GB VRAM without quantization. Fine-tuned adapters (Empathy + Safety) are
a Phase 4 deliverable and will be swapped in via PEFT's `load_adapter()`
without changing this class interface.

Production target (Phase 4+, Director-approved 2026-05-14):
  ADP-A (empathy/response): Qwen3-4B base (Qwen/Qwen3-4B) — no LoRA for MVP
  ADP-B (safety/crisis):    Gemma-2-2b-it          (google/gemma-2-2b-it)
  ADP-C (evaluation):       Gemma-2-2b-it          (google/gemma-2-2b-it)
Mistral-7B-Instruct-v0.3 was the previous target but was infeasible on RTX 3070
8GB VRAM (14GB fp16 requirement; training exceeded 14h with no convergence).
bitsandbytes / NF4 quantization is no longer used. See hf_space/app.py for the
dual-model deployment architecture and SPEC-400 for updated model selection.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Optional

# [CONCEPT] Lazy imports for heavy dependencies
# torch and transformers are only imported inside _load_model(), not at module
# level. This means `from agents.signal_agent import SignalAgent` is fast and
# won't crash if transformers isn't installed — it only fails when you actually
# try to call analyze() without the model. The notebook mock-mode cells rely
# on this: they can import the class and test parse/validate logic without
# triggering a model download.

from schemas.acp_schemas import (
    DistressLevel,
    SignalPayload,
)
from schemas.validate import (
    VALID_SIGNAL_KEYS,
    get_confidence_band,
    validate_signal_payload,
)

# ---------------------------------------------------------------------------
# Deployment mode flag
# ---------------------------------------------------------------------------
# [CONCEPT] NIKKO_LOCAL_LLM controls whether transformer models are loaded.
# On Render free tier (no GPU, ~512 MB RAM), this must be "false" — set via
# Render Dashboard → Environment. When false, analyze() uses _rule_analyze()
# (deterministic weighted-regex) as the primary path instead of calling a
# transformer model. On HF Spaces / local GPU, the LLM path runs first and
# falls back to _rule_analyze() only on model load failure.
_LOCAL_LLM: bool = os.getenv("NIKKO_LOCAL_LLM", "true").lower() not in ("false", "0", "no")

# ---------------------------------------------------------------------------
# Rule-based signal detection patterns (SPEC-100)
# ---------------------------------------------------------------------------
# Each tuple: (signal_key, compiled_regex, weight)
# weight: 1.0 = definitive indicator (risk language), 0.8 = strong,
#         0.7 = clear, 0.6 = moderate, 0.5 = weak/ambiguous, 0.4 = minimal.
#
# Design notes:
#   - Patterns are deliberately conservative on lower signals (avoid false
#     positives that escalate distress level).
#   - Risk patterns use weight=1.0 and are checked first (early exit logic
#     for crisis distress assignment mirrors REQ-100-060).
#   - All keys resolve to SPEC-100 / signal_enum.json entries.
#   - Word-boundary anchors (\b) prevent substring collisions.
#   - re.IGNORECASE applied at compile time to every pattern.
#
_I = re.IGNORECASE  # shorthand

# ── Emotional states ───────────────────────────────────────────────────────
_EMOTIONAL_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # sadness_spectrum.low_mood_language
    ("sadness_spectrum.low_mood_language", re.compile(
        r"\b(feel(ing)? (sad|down|blue|low|unhappy|miserable)|"
        r"(pretty|really|so|pretty) (sad|down|low|unhappy)|"
        r"not (happy|okay|doing (well|great|good))|"
        r"(things|life) (have been|has been|is|are) (hard|tough|difficult|rough|not great))\b", _I), 0.6),

    # sadness_spectrum.emotional_heaviness
    ("sadness_spectrum.emotional_heaviness", re.compile(
        r"\b(feel(ing)? (heavy|weighed down|burdened|crushed|drained emotionally)|"
        r"everything (feels?|seems?) (heavy|hard|too much|like a weight)|"
        r"carry(ing)? (so much|a lot|this weight)|"
        r"can'?t (shake|get rid of) (this|the) (feeling|sadness|heaviness))\b", _I), 0.7),

    # sadness_spectrum.grief_expression
    ("sadness_spectrum.grief_expression", re.compile(
        r"\b(griev(ing|e)|lost (my|a|someone|him|her|them|a friend)|"
        r"(he|she|they) (passed away|died|is gone)|death of|"
        r"miss(ing)? (him|her|them|you|my \w+) (so much|terribly|every day|still)|"
        r"mourning|bereavement|funeral)\b", _I), 0.8),

    # sadness_spectrum.loss_oriented_statements
    ("sadness_spectrum.loss_oriented_statements", re.compile(
        r"\b(lost (my job|my relationship|my partner|my home|everything|hope|interest|purpose|direction)|"
        r"(nothing|it) (matters?|means anything) anymore|"
        r"everything (I had|that mattered|I cared about)|"
        r"(feel(ing)? like I'?ve lost|lost a part of) (myself|who I was|everything))\b", _I), 0.7),

    # anxiety_spectrum.worry_language
    ("anxiety_spectrum.worry_language", re.compile(
        r"\b(worried|worrying|worry(ing)?|anxious|anxiety|"
        r"can'?t stop (thinking about|worrying)|"
        r"keep (thinking|wondering|worrying) about|"
        r"(so|really|always|constantly) (nervous|anxious|stressed|on edge))\b", _I), 0.6),

    # anxiety_spectrum.anticipatory_fear
    ("anxiety_spectrum.anticipatory_fear", re.compile(
        r"\b(scared (of|about|that)|afraid (of|about|that)|"
        r"dreading|fear(ing)? (the worst|what|that)|"
        r"(what if|what happens if|what (will|would) happen)|"
        r"terrified (of|about|that)|"
        r"(panic(king)?|panicked) (about|at|when))\b", _I), 0.7),

    # anxiety_spectrum.hypervigilance
    ("anxiety_spectrum.hypervigilance", re.compile(
        r"\b(always (on edge|watching|checking|alert|scanning)|"
        r"can'?t (relax|switch off|unwind|let my guard down)|"
        r"constantly (on guard|alert|checking|watching)|"
        r"(jumpy|startle|startled) (at|by) (everything|every|the slightest)|"
        r"(feel(ing)?|felt) (unsafe|like something bad is|like I'?m in danger))\b", _I), 0.7),

    # anxiety_spectrum.overwhelm_signals
    ("anxiety_spectrum.overwhelm_signals", re.compile(
        r"\b(overwhelm(ed|ing|s me)|too much (to handle|going on|at once|for me)|"
        r"can'?t (cope|deal|manage|handle) (with )?(everything|this|it all)|"
        r"(it'?s|everything'?s|things are) (too much|getting to me|piling up|building up)|"
        r"(swamp(ed|ing)|drown(ing|ed) in|bury(ing|ied) under))\b", _I), 0.7),

    # emotional_dysregulation.rapid_emotional_shifts
    ("emotional_dysregulation.rapid_emotional_shifts", re.compile(
        r"\b(one minute I('?m| was|am) .{0,30} (then|next)|"
        r"go(ing|es)? from (happy|fine|okay) to|"
        r"feel(ing)? (up and down|all over the place|all kinds of (emotions|ways)|"
        r"emotions? (all over|swinging|fluctuating|unstable|unpredictable)))\b", _I), 0.7),

    # emotional_dysregulation.intensity_escalation
    ("emotional_dysregulation.intensity_escalation", re.compile(
        r"\b(feel(ing)? (out of control|like I'?m (losing it|going to (snap|explode|break))|"
        r"too intense|(everything is )?(spiral(l?ing)|falling apart|breaking down))|"
        r"can'?t (control|stop|contain) (my|these|the) (emotions?|feelings?|reactions?))\b", _I), 0.8),

    # emotional_dysregulation.inability_to_self_soothe
    ("emotional_dysregulation.inability_to_self_soothe", re.compile(
        r"\b(nothing (helps?|works?|calms? me|makes? (it|me) (better|okay))|"
        r"can'?t (calm (down|myself)|soothe (myself)?|settle|get it together)|"
        r"tried (everything|so many things|lots of things) (and|but) nothing (helps?|works?)|"
        r"(no matter what I try|whatever I do) (nothing|it) (helps?|works?|changes?))\b", _I), 0.7),

    # shame_self_worth.self_criticism
    ("shame_self_worth.self_criticism", re.compile(
        r"\b(I'?m (so stupid|such a failure|worthless|useless|pathetic|a mess|terrible|awful|a joke)|"
        r"hate (myself|who I am|everything about me)|"
        r"I (always|never) (mess up|get it right|fail|do things wrong)|"
        r"(it'?s|that'?s) (all my fault|always my fault)|"
        r"(should (have known|be better|do better|know better)|blame myself))\b", _I), 0.8),

    # shame_self_worth.perceived_burden_language
    ("shame_self_worth.perceived_burden_language", re.compile(
        r"\b((everyone|they|people) (would be|are) better off (without me|if I wasn'?t here)|"
        r"(I'?m|feel(ing)? like I'?m) (a burden|holding (everyone|them|him|her|people) (back|down))|"
        r"(they|he|she|everyone) (shouldn'?t|doesn'?t|won'?t) (have to|need to) (deal with|worry about) me|"
        r"(I just|only) (cause|bring) (pain|trouble|stress|problems?) to (everyone|others|people))\b", _I), 0.9),

    # shame_self_worth.worthlessness_framing
    ("shame_self_worth.worthlessness_framing", re.compile(
        r"\b(feel(ing)? (worthless|like nothing|like I don'?t matter|invisible|irrelevant)|"
        r"(don'?t|doesn'?t) (deserve|matter|belong|count)|"
        r"(no one|nobody) (would (miss|care)|cares|notices|needs me)|"
        r"(I|my (life|existence)) (mean(s)?|matter(s)?) (nothing|to no one))\b", _I), 0.9),

    # emotional_numbness.detachment_language
    ("emotional_numbness.detachment_language", re.compile(
        r"\b(feel(ing)? (numb|disconnected|detached|empty inside|like I'?m not really here)|"
        r"(just|just) (going through the motions|existing|getting through (the )?days?)|"
        r"(don'?t|can'?t) feel (anything|much) (anymore|at all)|"
        r"like I'?m (watching|outside of) (myself|my own life))\b", _I), 0.7),

    # emotional_numbness.emptiness_statements
    ("emotional_numbness.emptiness_statements", re.compile(
        r"\b(feel(ing)? (empty|hollow|like a void|like there'?s nothing inside)|"
        r"(inside|there'?s) (nothing|just emptiness|a void|a hollow)|"
        r"(complete|total|just) (emptiness|numbness|blankness|hollowness))\b", _I), 0.7),

    # emotional_numbness.reduced_emotional_vocabulary
    ("emotional_numbness.reduced_emotional_vocabulary", re.compile(
        r"\b(I don'?t know (how I feel|what I feel|what to call it)|"
        r"(hard|difficult) to (describe|explain|put into words) (how I feel|it)|"
        r"(just|I'?m just) (fine|okay|alright|meh|here|existing|getting by))\b", _I), 0.4),
]

# ── Cognitive patterns ─────────────────────────────────────────────────────
_COGNITIVE_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # rumination_loop
    ("rumination_loop", re.compile(
        r"\b(keep (thinking|going over|replaying|dwelling on|obsessing over)|"
        r"can'?t stop (thinking about|going over|replaying)|"
        r"(it|this|that) keeps? (coming back|haunting|replaying in my (head|mind))|"
        r"(stuck|spinning|looping) (on|around|over) (this|it|the same thought)|"
        r"(over and over|again and again|on my mind (all the time|constantly)))\b", _I), 0.7),

    # catastrophizing
    ("catastrophizing", re.compile(
        r"\b(everything (will|is going to) (fall apart|go wrong|be ruined|collapse)|"
        r"(the worst|terrible|awful|horrible) (thing|outcome|case) (possible|is going to happen|is coming)|"
        r"(it'?s|this is|that'?s|i know it'?s) (the end|over|all falling apart|ruined|doomed)|"
        r"(nothing will ever|it'?ll never) (get better|change|work out|be okay)|"
        r"(something (terrible|awful|bad) is going to happen|this (is|will) (destroy|ruin|end)))\b", _I), 0.7),

    # black_white_thinking
    ("black_white_thinking", re.compile(
        r"\b(always (fail|mess up|get it wrong|ruin things|ruin everything)|"
        r"never (get it right|succeed|good enough|works? out for me|do anything right)|"
        r"(everything|nothing) (is|was) (good|bad|right|wrong|perfect|a disaster)|"
        r"(either .{0,30} or .{0,30}|no middle ground|no in.between|all or nothing))\b", _I), 0.6),

    # hopeless_future_projection
    ("hopeless_future_projection", re.compile(
        r"\b((things|nothing|it) will (ever|never) (change|get better|improve|be different)|"
        r"(no point|no use|pointless|useless) (trying|hoping|anyway|anymore)|"
        r"(future|tomorrow|my life) (look(s)?|seems?) (bleak|hopeless|dark|pointless|empty)|"
        r"(there'?s|I see|I have) (no future|nothing (to look forward to|ahead|left)|no hope)|"
        r"(I|things) (will (always|never)|am (never|always) going to) (be (like this|this way)|feel this way))\b", _I), 0.8),

    # personalization_bias
    ("personalization_bias", re.compile(
        r"\b((it'?s|that'?s) (all my fault|because of me|my doing|on me)|"
        r"I (caused|made|brought|created) (this|it|that) (on|upon|to) (myself|them|us)|"
        r"(blame myself|take the blame|my fault|responsibility (is|falls on) me) (for|when)|"
        r"(if only I (hadn'?t|had|were|wasn'?t)))\b", _I), 0.6),

    # negative_core_beliefs
    ("negative_core_beliefs", re.compile(
        r"\b(I'?m (fundamentally|inherently|just|basically) (broken|bad|unlovable|defective|wrong|flawed)|"
        r"(always been|always will be|I'?ve always been) (this way|like this|broken|the problem|not enough)|"
        r"(deep down|I know|I'?ve always known) (I'?m not|that I'?m) (good enough|worthy|lovable|capable)|"
        r"(I'?m) (just (not|never) (good|smart|strong|worthy|capable) enough))\b", _I), 0.8),

    # helplessness_framing
    ("helplessness_framing", re.compile(
        r"\b((can'?t|couldn'?t) (do anything|change anything|make it better|help (myself|anything))|"
        r"(no matter what I do|whatever I try|I'?ve tried (everything|so much))|"
        r"(nothing (I do|I try|can|ever)) (matters?|works?|helps?|makes (a )?(difference|change))|"
        r"(feel(ing)?|felt) (powerless|helpless|stuck|trapped) (with no|and (no|with no)) way (out|forward|to change))\b", _I), 0.7),

    # meaninglessness_expression
    ("meaninglessness_expression", re.compile(
        r"\b((no (point|purpose|meaning|reason) (to|in|for) (anything|going on|living|trying|it all))|"
        r"(what'?s the point|why (bother|try|keep (going|on)|does it even matter))|"
        r"(nothing (matters?|means anything|has meaning))|"
        r"(life|living|everything) (feels?|seems?|is) (pointless|meaningless|empty|futile|without purpose))\b", _I), 0.8),
]

# ── Behavioral indicators ──────────────────────────────────────────────────
_BEHAVIORAL_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # withdrawal_isolation
    ("withdrawal_isolation", re.compile(
        r"\b((stopped|avoiding|don'?t want to) (seeing|talking to|going out with|being around|spending time with) (people|friends|family|anyone|others)|"
        r"(isolat(ed|ing|e myself)|withdrawn|cut(ting)? (myself |myself )?off from)|"
        r"(haven'?t (left|seen|talked to)|not (going out|talking|seeing anyone))|"
        r"(spend(ing)? (more )?time alone|stay(ing)? (home|inside|in) (all|mostly|almost all)))\b", _I), 0.7),

    # avoidance_behavior
    ("avoidance_behavior", re.compile(
        r"\b((avoid(ing)?|putting off|can'?t (face|make myself (do|go to))) .{0,40}(work|tasks?|things?|chores?|responsibilities|commitments|places?|situations?|people)|"
        r"(procrastinat(ing|ion)|keep putting (it|things) off)|"
        r"(make excuses|find reasons) (not to|to avoid))\b", _I), 0.6),

    # sleep_disruption
    ("sleep_disruption", re.compile(
        r"\b((can'?t (sleep|fall asleep|stay asleep|get to sleep))|"
        r"(sleep(ing)? (too much|all the time|way too much|for hours and hours))|"
        r"(insomnia|wak(ing|e) up (at night|early|too early|in the middle of the night|several times))|"
        r"(sleep (deprivation|problems?|issues?|trouble))|"
        r"(exhausted (all the time|constantly|even after sleeping|no matter how much I sleep)))\b", _I), 0.6),

    # appetite_change
    ("appetite_change", re.compile(
        r"\b((not (eating|hungry|able to eat)|lost (my )?appetite)|"
        r"(forget(ting)? to eat|barely eating|skipping meals?|not eating much)|"
        r"(eating (too much|constantly|all the time|when (bored|stressed|sad)|for comfort))|"
        r"(stress.eating|overeating|binge(ing)?)|"
        r"(food (doesn'?t|no longer) (interest|appeal|taste (good|right)) (to me|anymore)))\b", _I), 0.6),

    # loss_of_motivation
    ("loss_of_motivation", re.compile(
        r"\b((can'?t (be bothered|make myself (do|start|get up)|get motivated|find the energy))|"
        r"(lost|no|zero|little) (motivation|drive|interest|energy|desire)|"
        r"(things I used to (enjoy|love|care about)|don'?t (enjoy|care about|want to do)) (anymore|at all)|"
        r"(hard|difficult|impossible) to (get (started|going|up|out of bed)|do (anything|the simplest things|basic things)))\b", _I), 0.7),

    # coping_attempt
    ("coping_attempt", re.compile(
        r"\b((tried|trying|been (trying|using|doing)) (to cope|to (manage|deal|get through|handle it))|"
        r"(exercise|meditation|breathing|journaling|talking to (a friend|someone)) (helps?|has been helping|I (use|try))|"
        r"(coping|getting by|managing (somehow|okay))|"
        r"(things that (help|have helped)|what (helps?|works?) for me))\b", _I), 0.5),

    # help_seeking_behavior
    # [CONCEPT] Specificity requirement
    # This pattern must only fire on INFORMATION-SEEKING intent, not on generic
    # "help me" phrases ("could you help me?", "I need help" on their own).
    # Generic help requests in emotional contexts are COMFORT not GUIDANCE.
    # The pattern requires: named techniques/resources OR specific how-to questions
    # OR explicit requests for advice/tips/strategies/resources — not bare "help".
    ("help_seeking_behavior", re.compile(
        r"\b((looking for|need|want|seeking|asking for|could use) (advice|tips?|resources?|strategies?|techniques?|information|guidance on)|"
        r"(how (do|can|should) I (cope|manage|deal|handle|treat|reduce|stop|overcome|practice|use|try))|"
        r"(what (can|should) I do (about|with|to (help|manage|cope|reduce)))|"
        r"(any (advice|suggestions?|tips?|resources?|techniques?|exercises?))|"
        r"(CBT|DBT|EMDR|ACT|therapy|therapist|technique|techniques|skill|skills|strategy|strategies|"
        r"mindfulness|breathing exercise|grounding technique|grounding exercises?|what works?))\b", _I), 0.7),

    # self_reflection_capacity
    ("self_reflection_capacity", re.compile(
        r"\b((I think|I feel|I notice|I realize|I'?ve (been thinking|noticed|realized|been reflecting))|"
        r"(reflecting on|trying to understand|making sense of|working through)|"
        r"(it'?s (possible|maybe) that I|I wonder if I)|"
        r"(introspect(ing|ion)|self.aware(ness)?|self.insight))\b", _I), 0.4),
]

# ── Risk indicators ────────────────────────────────────────────────────────
# NOTE: These are intentionally aggressive. A false positive on risk is always
# preferable to a false negative. All risk patterns use weight >= 0.9.
_RISK_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # risk.passive.wishing_to_disappear
    ("risk.passive.wishing_to_disappear", re.compile(
        r"\b((wish(ed)? (I could|I would|I can) (disappear|not exist|not be here|just vanish|cease to exist))|"
        r"(want(ed)? to (disappear|not exist|just not be here|be invisible forever))|"
        r"(world|everyone|they|people) would be better off (without me|if I wasn'?t (here|around|alive))|"
        r"(tired of (existing|being here)|just want it (to stop|to end|all to stop)))\b", _I), 0.9),

    # risk.passive.fatigue_with_living
    ("risk.passive.fatigue_with_living", re.compile(
        r"\b((tired of (living|fighting|being alive|life itself|it all)|"
        r"don'?t (want|see the point) (to|of|in) (living|being here|going on|continuing)|"
        r"(so|really|completely) (exhausted by|tired of|done with|finished with) (life|everything|it all)|"
        r"can'?t (do this|keep going|take it|carry on) (anymore|much longer|any longer|for much longer)))\b", _I), 0.9),

    # risk.passive.indirect_death_reference
    ("risk.passive.indirect_death_reference", re.compile(
        r"\b((think(ing)? about (death|dying|not being (here|alive|around)))|"
        r"(death|dying) (seems?|sounds?|feels?|is) (appealing|like relief|like an escape|peaceful|easier|better)|"
        r"(imagine(d)?|think about) (not being here|being dead|not existing|dying)|"
        r"(if I (weren'?t|wasn'?t|wasn'?t) (here|alive|around|born)))\b", _I), 0.9),

    # risk.active.suicidal_ideation
    ("risk.active.suicidal_ideation", re.compile(
        r"\b((think(ing)? about (killing|ending) (myself|my life)|"
        r"suicidal (thoughts?|ideation|feelings?)|"
        r"(want(ed)?|thought(s)? about|have been (thinking|considering|contemplating)) (killing|ending|taking) (my (life|own life)|myself)|"
        r"(don'?t want to (be alive|live|exist|go on)|wish I was dead|wish I (were|am|could be) dead)|"
        r"(thoughts? of suicide|I'?ve been suicidal|feeling suicidal)))\b", _I), 1.0),

    # risk.active.self_harm_reference
    ("risk.active.self_harm_reference", re.compile(
        r"\b((hurt(ing)? myself|self.harm(ing|ed)?|"
        r"cut(ting)? (myself|my (skin|arms?|wrists?|legs?))|"
        r"(burning|hitting|injur(ing|ed)|scratch(ing)?) myself|"
        r"(scars?|marks?|wounds?|cuts?) (on|from) (hurting|harming|cutting|burning) myself|"
        r"(think(ing)? about|have been|been) (hurting|harming|cutting) myself))\b", _I), 1.0),

    # risk.active.preparation_statement
    ("risk.active.preparation_statement", re.compile(
        r"\b((been (thinking about|planning|researching|looking up) (how to|ways? to|methods? (to|of)))|"
        r"(looking up|researching|found out|know) (how|ways?) to (end|die|kill|harm) (myself|my life)?|"
        r"(putting? (my|things|affairs?) in order|giving? (things|stuff|belongings|possessions) away|"
        r"given(ing)? (things) (to|away))|"
        r"(said|writing?|wrote|leaving?) (my )?(goodbyes?|farewell|final messages?|final note))\b", _I), 1.0),

    # risk.active.farewell_framing
    ("risk.active.farewell_framing", re.compile(
        r"\b((this (might|may|could) be (my|the) last (time|chance|message)|"
        r"(wanted to|just wanted to|need to) (say goodbye|thank you for everything|let you know I care)|"
        r"(goodbye|farewell|take care) .{0,30}(for everything|always|forever|I love you)|"
        r"(won'?t|don'?t think I'?ll|might not) (see you|be (around|here|alive) (much longer|anymore|after this))))\b", _I), 1.0),

    # risk.acute.intent_language
    ("risk.acute.intent_language", re.compile(
        r"\b((I (am going to|will|'?m going to|have decided to) (kill|end|harm|hurt) (myself|my life|my own life)|"
        r"I (have a|'?ve got a|made a) plan( to (kill|end|harm|hurt) myself)?|"
        r"I'?ve (made up my mind|decided( to (do it|end it|kill myself))?)|"
        r"(tonight|soon|later today|this (afternoon|evening|week|weekend)) I (plan|will|'?m going to) (do it|end it|kill myself)))\b", _I), 1.0),

    # risk.acute.immediacy_statement
    ("risk.acute.immediacy_statement", re.compile(
        r"\b(right now (I|it|this|I'?m)|this (very )?moment|"
        r"I'?m (about to|going to) (do it|hurt myself|end it|die)|"
        r"I (can'?t|won'?t) (wait (any longer|anymore)|hold on (much longer|anymore)|stop myself)|"
        r"(happening|doing it|it'?s) (right now|tonight|happening soon|going to happen))\b", _I), 0.9),

    # risk.acute.loss_of_safety_framing
    ("risk.acute.loss_of_safety_framing", re.compile(
        r"\b((not safe|I'?m not safe|don'?t feel safe (right now)?|"
        r"(afraid|scared|worried|not sure) (I'?ll|I will|I might|I could) (hurt|harm|do something to|kill) (myself)|"
        r"(can'?t|don'?t know if I can) (keep (myself )?safe|control myself|stop myself|guarantee I won'?t)))\b", _I), 1.0),
]

# ── Support needs: inferred from signal combinations (not matched directly) ─
# The following table maps signal keys → support needs they imply.
# This is applied after pattern matching to derive the support_needs list.
_SUPPORT_NEED_RULES: list[tuple[set[str], str]] = [
    # Any risk signal → crisis_escalation + external support
    ({"risk.active.suicidal_ideation", "risk.active.self_harm_reference",
      "risk.active.preparation_statement", "risk.active.farewell_framing",
      "risk.acute.intent_language", "risk.acute.immediacy_statement",
      "risk.acute.loss_of_safety_framing"}, "crisis_escalation"),
    ({"risk.passive.wishing_to_disappear", "risk.passive.fatigue_with_living",
      "risk.passive.indirect_death_reference", "risk.active.suicidal_ideation",
      "risk.active.self_harm_reference"}, "encouragement_external_support"),
    # Grounding for dysregulation, overwhelm, high distress
    ({"emotional_dysregulation.intensity_escalation",
      "emotional_dysregulation.inability_to_self_soothe",
      "anxiety_spectrum.overwhelm_signals",
      "risk.acute.loss_of_safety_framing"}, "grounding_stabilization"),
    # Psychoeducation when user explicitly seeks information
    ({"help_seeking_behavior"}, "psychoeducation"),
    # Normalization for common distress patterns
    ({"rumination_loop", "catastrophizing", "hopeless_future_projection",
      "black_white_thinking", "anxiety_spectrum.worry_language"}, "normalization"),
    # Reflective exploration when user shows insight
    ({"self_reflection_capacity", "sadness_spectrum.grief_expression",
      "sadness_spectrum.loss_oriented_statements"}, "reflective_exploration"),
    # Emotional validation for any sadness/shame/numbness
    ({"sadness_spectrum.low_mood_language", "sadness_spectrum.emotional_heaviness",
      "sadness_spectrum.grief_expression", "sadness_spectrum.loss_oriented_statements",
      "shame_self_worth.self_criticism", "shame_self_worth.worthlessness_framing",
      "shame_self_worth.perceived_burden_language",
      "emotional_numbness.emptiness_statements",
      "emotional_numbness.detachment_language",
      "helplessness_framing", "meaninglessness_expression"}, "emotional_validation"),
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default base model — Apache 2.0 licence, primary choice per G-MODEL-01.
# Override at instantiation for testing with a smaller model (e.g. phi-3-mini).
# Phase 3 development model — Qwen2.5-3B fits in 8GB VRAM without quantization.
# Production target (Phase 4+, Director-approved 2026-05-14):
#   ADP-A (empathy): Qwen3-4B (base, no LoRA for MVP)    ADP-B/C: Gemma-2-2b-it
# See hf_space/app.py for the dual-model loading and adapter dispatch logic.
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default base model — Apache 2.0 licence, primary choice per G-MODEL-01.
# Override at instantiation for testing with a smaller model (e.g. phi-3-mini).
# Phase 3 development model — Qwen2.5-3B fits in 8GB VRAM without quantization.
# Production target (Phase 4+, Director-approved 2026-05-14):
#   ADP-A (empathy): Qwen3-4B (base, no LoRA for MVP)    ADP-B/C: Gemma-2-2b-it
# See hf_space/app.py for the dual-model loading and adapter dispatch logic.
DEFAULT_MODEL_ID: str = "Qwen/Qwen2.5-3B-Instruct"

# Max new tokens for signal output. The JSON schema is compact; 512 is generous.
_MAX_NEW_TOKENS: int = 512

# Temperature: low but non-zero. We want near-deterministic signal detection
# while allowing the model to express genuine uncertainty. (not 0.0 -- that
# enables greedy decoding which can cause repetition loops in some models)
_TEMPERATURE: float = 0.1

# Timeout for a single generate() call, in seconds.
_GENERATE_TIMEOUT_S: float = 30.0

# System prompt -- verbatim from agent_prompts.md 3.1.
# REQ-ID comments are stripped before the prompt is passed to the model
# (per agent_prompts.md traceability rule). They are preserved here for
# maintainability -- a diff against agent_prompts.md will show any drift.
_SYSTEM_PROMPT: str = """You are the Psychological Signal Agent for Nikko. You detect observable linguistic patterns in user language that are associated with emotional states, cognitive patterns, behavioural indicators, and risk.

WHAT YOU DETECT
You detect patterns of expression -- not conditions, not diagnoses, not identities.
You observe what the user says, not what they are.

THE FOUR SIGNAL LAYERS
1. Emotional states -- expressed affect (sadness spectrum, anxiety spectrum, emotional dysregulation, shame/self-worth, emotional numbness)
2. Cognitive patterns -- thinking styles (rumination, catastrophizing, black-white thinking, hopeless projection, personalization bias, negative core beliefs, helplessness, meaninglessness)
3. Behavioural indicators -- described actions (withdrawal, avoidance, sleep disruption, appetite change, loss of motivation, coping attempts, help-seeking, self-reflection)
4. Risk indicators -- passive (wishing to disappear, fatigue with living, indirect death reference) | active (suicidal ideation, self-harm reference, preparation statements, farewell framing) | acute (intent language, immediacy, loss of safety framing)

DISTRESS LEVEL SCALE
low -- general conversation, minimal affect markers
moderate -- identifiable emotional distress
high -- pronounced distress, multiple signals
crisis -- any active or acute risk indicator present

CONFIDENCE AND UNCERTAINTY
Your confidence reflects the strength of linguistic evidence -- not psychological certainty.
Absence of signal is NOT absence of distress.
When cultural, neurodivergent, or indirect expression patterns are detected, reduce confidence and explain in uncertainty_notes.
If confidence < 0.40, the router will trigger fallback handling. Be accurate, not generous.

TEMPORAL AWARENESS
Consider conversational history. A single passive risk indicator in isolation is different from the same indicator repeated across three turns alongside high distress.

ABSOLUTE PROHIBITIONS
You MUST NOT: diagnose, infer mental disorders, label users clinically, output disorder names, communicate with any agent other than the Router, or produce user-facing text.
All values in your output arrays MUST resolve to keys in signal_enum.json. Do not invent new signal strings.

VALID SIGNAL KEYS (use these exact strings -- no others):

DISTRESS LEVELS: low, moderate, high, crisis

EMOTIONAL STATES: sadness_spectrum.low_mood_language, sadness_spectrum.emotional_heaviness, sadness_spectrum.grief_expression, sadness_spectrum.loss_oriented_statements, anxiety_spectrum.worry_language, anxiety_spectrum.anticipatory_fear, anxiety_spectrum.hypervigilance, anxiety_spectrum.overwhelm_signals, emotional_dysregulation.rapid_emotional_shifts, emotional_dysregulation.intensity_escalation, emotional_dysregulation.inability_to_self_soothe, shame_self_worth.self_criticism, shame_self_worth.perceived_burden_language, shame_self_worth.worthlessness_framing, emotional_numbness.detachment_language, emotional_numbness.emptiness_statements, emotional_numbness.reduced_emotional_vocabulary

COGNITIVE PATTERNS: rumination_loop, catastrophizing, black_white_thinking, hopeless_future_projection, personalization_bias, negative_core_beliefs, helplessness_framing, meaninglessness_expression

BEHAVIORAL INDICATORS: withdrawal_isolation, avoidance_behavior, sleep_disruption, appetite_change, loss_of_motivation, coping_attempt, help_seeking_behavior, self_reflection_capacity

RISK INDICATORS: risk.passive.wishing_to_disappear, risk.passive.fatigue_with_living, risk.passive.indirect_death_reference, risk.active.suicidal_ideation, risk.active.self_harm_reference, risk.active.preparation_statement, risk.active.farewell_framing, risk.acute.intent_language, risk.acute.immediacy_statement, risk.acute.loss_of_safety_framing

SUPPORT NEEDS: emotional_validation, grounding_stabilization, psychoeducation, normalization, reflective_exploration, encouragement_external_support, crisis_escalation

OUTPUT FORMAT
Respond with ONLY a JSON object. No preamble. No explanation. No markdown fences.
{
  "distress_level": "low | moderate | high | crisis",
  "emotional_states": [],
  "cognitive_patterns": [],
  "behavioral_indicators": [],
  "risk_indicators": [],
  "support_needs": [],
  "confidence": 0.0,
  "uncertainty_notes": ""
}"""


# ---------------------------------------------------------------------------
# Public helper — passive risk scan for multi-turn tracking
# ---------------------------------------------------------------------------

def has_passive_risk(text: str) -> bool:
    """
    Return True if the text contains at least one passive risk signal.

    [REQ-100-PR2] Used by NikkoPipeline to scan the last N user turns for
    sustained passive risk patterns without running a full signal analysis.
    Reuses the same _RISK_PATTERNS table as _rule_analyze() — any key that
    starts with "risk.passive." counts as a passive risk hit.

    Passive risk indicators (SPEC-100 §4, risk.passive.*):
      wishing_to_disappear, burden_ideation, hopelessness_passive,
      escapism_ideation, anhedonia_severe, and related patterns.

    Intentionally conservative: only named passive risk keys count.
    General distress language (e.g. "nothing ever gets better") does NOT
    trigger this function — that goes through the full _rule_analyze() path
    so its distress weight is properly accounted for.
    """
    for key, pattern, _weight in _RISK_PATTERNS:
        if key.startswith("risk.passive.") and pattern.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Signal Agent
# ---------------------------------------------------------------------------

class SignalAgent:
    """
    Psychological Signal Agent -- first LLM-backed component in the pipeline.

    When NIKKO_LOCAL_LLM=false (Render / no GPU), analyze() calls the
    deterministic _rule_analyze() engine directly -- no model load attempted.
    When NIKKO_LOCAL_LLM=true (HF Spaces / local GPU), the LLM path runs
    first and falls back to _rule_analyze() on any load or parse failure.

    Usage:
        agent = SignalAgent()
        payload = agent.analyze("I've been struggling a lot lately.")

    For testing without a GPU / model download, use mock_analyze() instead.
    See the Step 3 notebook for examples.
    """

    def __init__(
        self,
        model_id:      str  = DEFAULT_MODEL_ID,
        quantize_4bit: bool = False,
        device_map:    str  = "auto",
    ) -> None:
        self._model_id      = model_id
        self._quantize_4bit = quantize_4bit
        self._device_map    = device_map
        self._model     = None
        self._tokenizer = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(
        self,
        sanitized_input:       str,
        conversation_history:  list[str] | None = None,
    ) -> SignalPayload:
        """
        Analyze a sanitized user message and return a validated SignalPayload.

        The payload is constructed and returned as the authoritative signal for
        this turn. No downstream agent may modify it. (REQ-700-032)

        Rule-based path:
            When NIKKO_LOCAL_LLM=false (Render / no GPU), _rule_analyze() is
            called directly -- no model load attempt. This produces a
            deterministic SignalPayload from weighted regex patterns covering
            all SPEC-100 signal keys with correct distress/confidence scoring.
        """
        # [CONCEPT] Deployment-mode fork
        # When NIKKO_LOCAL_LLM=false (Render free tier), we skip the transformer
        # path entirely and go directly to the rule-based engine. This avoids
        # ~512 MB RAM spike and the ModuleNotFoundError cascade that previously
        # produced SAFE_FALLBACK_RESPONSE on every request.
        if not _LOCAL_LLM:
            return self._rule_analyze(sanitized_input)

        # LLM path -- GPU / local dev. Falls back to rule engine on any failure.
        try:
            self._ensure_model_loaded()
            prompt = self._build_prompt(sanitized_input, conversation_history or [])
            raw_output = self._generate(prompt)
        except Exception as exc:
            print(f"[SignalAgent] LLM path failed ({exc}), falling back to rule engine.")
            return self._rule_analyze(sanitized_input)

        try:
            parsed = self._extract_json(raw_output)
        except ValueError as exc:
            print(f"[SignalAgent] JSON parse failed ({exc}), falling back to rule engine.")
            return self._rule_analyze(sanitized_input)

        return self._build_payload(parsed)

    def mock_analyze(self, mock_response: dict) -> SignalPayload:
        """
        Inject a pre-built dict as if the model returned it, bypassing LLM call.
        Used exclusively in tests and notebooks. Passes through full validation.
        """
        return self._build_payload(mock_response)

    # ------------------------------------------------------------------
    # Rule-based signal analysis (primary path on Render / no-GPU deploys)
    # ------------------------------------------------------------------

    def _rule_analyze(self, text: str) -> SignalPayload:
        """
        Deterministic weighted-regex signal engine.

        Matches all SPEC-100 pattern tables against the input text, computes
        distress level and confidence from match density, then derives
        support_needs from the signal combination. Produces a fully valid
        SignalPayload without any model calls.

        Algorithm:
          1. Run all emotional / cognitive / behavioral / risk pattern tables.
          2. Enforce REQ-100-060 crisis override: any active/acute risk key
             forces distress_level = CRISIS regardless of other scores.
          3. Estimate distress from summed signal weights when no risk keys.
          4. Compute confidence from total match count and weight sum.
          5. Derive support_needs from the _SUPPORT_NEED_RULES intersection.
          6. Construct and return a validated SignalPayload.
        """
        matched_emotional:   list[str] = []
        matched_cognitive:   list[str] = []
        matched_behavioral:  list[str] = []
        matched_risk:        list[str] = []

        # Weight accumulators for distress scoring
        emotional_weight_sum: float = 0.0
        cognitive_weight_sum: float = 0.0
        total_match_count:    int   = 0

        for key, pattern, weight in _EMOTIONAL_PATTERNS:
            if pattern.search(text):
                matched_emotional.append(key)
                emotional_weight_sum += weight
                total_match_count    += 1

        for key, pattern, weight in _COGNITIVE_PATTERNS:
            if pattern.search(text):
                matched_cognitive.append(key)
                cognitive_weight_sum += weight
                total_match_count    += 1

        for key, pattern, _weight in _BEHAVIORAL_PATTERNS:
            if pattern.search(text):
                matched_behavioral.append(key)
                total_match_count += 1

        for key, pattern, _weight in _RISK_PATTERNS:
            if pattern.search(text):
                matched_risk.append(key)
                total_match_count += 1

        # -- Distress level --------------------------------------------------
        # REQ-100-060: active/acute risk forces crisis, no override permitted.
        has_active_acute = any(
            k.startswith("risk.active.") or k.startswith("risk.acute.")
            for k in matched_risk
        )
        has_passive = any(k.startswith("risk.passive.") for k in matched_risk)

        if has_active_acute:
            distress_level = DistressLevel.CRISIS
        elif has_passive:
            distress_level = DistressLevel.HIGH
        else:
            # Scale from emotional + cognitive weight sums.
            # Caps: emotional at 3.0 (4+ signals), cognitive at 2.4 (3+ signals).
            combined = (min(emotional_weight_sum, 3.0) / 3.0) * 0.6 + \
                       (min(cognitive_weight_sum, 2.4) / 2.4) * 0.4
            if combined >= 0.65:
                distress_level = DistressLevel.HIGH
            elif combined >= 0.35:
                distress_level = DistressLevel.MODERATE
            else:
                distress_level = DistressLevel.LOW

        # -- Confidence ------------------------------------------------------
        if has_active_acute:
            confidence = 0.92
        elif has_passive:
            confidence = 0.85
        elif "help_seeking_behavior" in matched_behavioral and distress_level == DistressLevel.LOW:
            # [CONCEPT] Guidance-intent boost
            # Router Rule 4 (guidance mode) fires only when confidence >= 0.40
            # AND behavioral_indicators includes help_seeking_behavior.
            # Set to 0.65 so Rule 3 (confidence < 0.40 -> COMFORT) is bypassed.
            confidence = 0.65
        elif total_match_count == 0:
            confidence = 0.45
        else:
            confidence = min(0.50 + (total_match_count * 0.06), 0.82)

        # -- Support needs (inferred from matched signal set) ----------------
        matched_all = set(matched_emotional + matched_cognitive +
                          matched_behavioral + matched_risk)
        support_needs: list[str] = []
        seen: set[str] = set()
        for trigger_keys, need in _SUPPORT_NEED_RULES:
            if matched_all & trigger_keys and need not in seen:
                support_needs.append(need)
                seen.add(need)
        if not support_needs:
            support_needs = ["emotional_validation"]

        notes = (
            "[RULE-ENGINE] Weighted regex signal analysis -- no LLM call. "
            f"Matched: {total_match_count} pattern(s). "
            f"emotional_w={emotional_weight_sum:.2f} cognitive_w={cognitive_weight_sum:.2f}."
        )

        return SignalPayload(
            distress_level=distress_level,
            emotional_states=matched_emotional,
            cognitive_patterns=matched_cognitive,
            behavioral_indicators=matched_behavioral,
            risk_indicators=matched_risk,
            support_needs=support_needs,
            confidence=round(confidence, 4),
            uncertainty_notes=notes,
        )

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Load model and tokenizer on first call; no-op on subsequent calls."""
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> None:
        """Load the causal LM with optional 4-bit quantization."""
        import torch
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
        )

        print(f"[SignalAgent] Loading model: {self._model_id}")
        print(f"[SignalAgent] 4-bit quantization: {self._quantize_4bit}")
        t0 = time.perf_counter()

        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_id,
            use_fast=True,
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        bnb_config = None
        if self._quantize_4bit:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )

        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_id,
            quantization_config=bnb_config,
            device_map=self._device_map,
            torch_dtype=torch.float16 if not self._quantize_4bit else None,
        )
        self._model.eval()

        elapsed = time.perf_counter() - t0
        print(f"[SignalAgent] Model loaded in {elapsed:.1f}s.")

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        sanitized_input:      str,
        conversation_history: list[str],
    ) -> str:
        """Build the full prompt using the instruction template from agent_prompts.md 3.2."""
        history_section = ""
        if conversation_history:
            history_lines = "\n".join(
                f"  Turn {i+1}: {turn}"
                for i, turn in enumerate(conversation_history[-6:])
            )
            history_section = f"\nCONVERSATION HISTORY (this session, newest last):\n{history_lines}\n"

        user_content = (
            f"USER INPUT (sanitized):\n{sanitized_input}"
            f"{history_section}\n"
            "Emit a signal object conforming to the SPEC-100 9 schema.\n"
            "All array values MUST be keys from the valid signal key list above.\n"
            "Respond with ONLY the JSON object -- no markdown, no explanation."
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]
        return self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate(self, prompt: str) -> str:
        """Run the model and return the raw text completion."""
        import torch

        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=4096,
        ).to(self._model.device)

        input_len = inputs["input_ids"].shape[1]

        with torch.inference_mode():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=_MAX_NEW_TOKENS,
                temperature=_TEMPERATURE,
                do_sample=True,
                pad_token_id=self._tokenizer.pad_token_id,
                eos_token_id=self._tokenizer.eos_token_id,
            )

        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def _extract_json(self, raw_output: str) -> dict:
        """Extract the JSON object from the model's raw text output."""
        text = raw_output.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
        text = text.strip()

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(
                f"No JSON object found in model output. Raw output: {text[:200]!r}"
            )

        try:
            return json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON parse error: {exc}. Extracted text: {match.group()[:200]!r}"
            ) from exc

    # ------------------------------------------------------------------
    # Payload construction and validation
    # ------------------------------------------------------------------

    def _build_payload(self, parsed: dict) -> SignalPayload:
        """
        Validate the parsed dict and construct a SignalPayload.

        Validation steps:
        1. Extract each field with a safe default (never raise on missing keys).
        2. Run validate_signal_payload() to find invalid enum keys.
        3. Scrub any invalid keys from the arrays (log them, don't crash).
        4. Clamp confidence to [0.0, 1.0].
        5. Enforce the distress_level / risk_indicator consistency rule:
           any active or acute risk key forces distress_level = "crisis".
        6. Construct and return the SignalPayload.
        """
        raw_distress    = str(parsed.get("distress_level", "low")).lower()
        emotional       = list(parsed.get("emotional_states",      []))
        cognitive       = list(parsed.get("cognitive_patterns",     []))
        behavioral      = list(parsed.get("behavioral_indicators",  []))
        risk            = list(parsed.get("risk_indicators",        []))
        support         = list(parsed.get("support_needs",          []))
        raw_confidence  = float(parsed.get("confidence", 0.20))
        uncertainty     = str(parsed.get("uncertainty_notes", ""))

        result = validate_signal_payload(
            emotional_states=emotional,
            cognitive_patterns=cognitive,
            behavioral_indicators=behavioral,
            risk_indicators=risk,
            support_needs=support,
        )

        scrub_notes: list[str] = []
        if not result.valid:
            bad_field_keys: set[str] = set(result.invalid_keys)

            def scrub(field_name: str, items: list[str]) -> list[str]:
                clean, removed = [], []
                for item in items:
                    tag = f"{field_name}:{item}"
                    if tag in bad_field_keys:
                        removed.append(item)
                    else:
                        clean.append(item)
                if removed:
                    scrub_notes.append(
                        f"[SignalAgent] Scrubbed invalid keys from {field_name}: {removed}. "
                        f"(REQ-100-093)"
                    )
                return clean

            emotional  = scrub("emotional_states",      emotional)
            cognitive  = scrub("cognitive_patterns",     cognitive)
            behavioral = scrub("behavioral_indicators",  behavioral)
            risk       = scrub("risk_indicators",        risk)
            support    = scrub("support_needs",          support)

        confidence = max(0.0, min(1.0, raw_confidence))

        has_active_or_acute = any(
            k.startswith("risk.active.") or k.startswith("risk.acute.")
            for k in risk
        )
        if has_active_or_acute:
            if raw_distress != "crisis":
                scrub_notes.append(
                    "[SignalAgent] distress_level forced to 'crisis': active/acute risk "
                    f"indicators present but model emitted '{raw_distress}'. (REQ-100-060)"
                )
            raw_distress = "crisis"

        distress_map = {
            "low":      DistressLevel.LOW,
            "moderate": DistressLevel.MODERATE,
            "high":     DistressLevel.HIGH,
            "crisis":   DistressLevel.CRISIS,
        }
        distress_level = distress_map.get(raw_distress, DistressLevel.LOW)

        # [Issue 5, Director-approved 2026-05-23] LLM path CRISIS confidence cap.
        #
        # The rule-engine path is safe: has_active_or_acute always forces
        # ra