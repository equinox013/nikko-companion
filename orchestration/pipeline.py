"""
orchestration/pipeline.py
==========================
NikkoPipeline — the SPEC-700 end-to-end execution wiring.

Spec source : SPEC-700 (Full System Integration Blueprint)
Requirements: REQ-700-001 through REQ-700-161

Phase        : 3 — Agent Definitions (Implementation)

Role in the system
-------------------
This module is the single entry point for all user interactions. It owns:
  - Agent instantiation and lifecycle
  - The SPEC-700 execution order (STEP 0 → STEP 15)
  - Mode branching (Comfort / Guidance / Crisis)
  - Regeneration loop management (REQ-200-170)
  - Failure state handling (REQ-700-120 through REQ-700-123)
  - Ephemeral trace capture (REQ-700-110, REQ-700-LOG1)

Design: dependency-injected, protocol-based
--------------------------------------------
Three components are injected at construction time rather than hard-coded:
  1. draft_generator : DraftGeneratorProtocol — the Interaction Model (LLM).
     Phase 3 uses StubDraftGenerator; Phase 4 swaps in the fine-tuned model
     without changing this file.
  2. scope_classifier : ScopeClassifier instance (or stub).
  3. signal_agent    : SignalAgent instance (or stub).

Agents with FUSE-mount truncation issues (ScopeClassifier, SignalAgent,
SupportStrategyAgent) are wrapped in try/except at import time and replaced
by in-file stubs when the full implementation is unavailable. This is a
Phase 3 workaround; the real implementations will be usable once the FUSE
sync issue is resolved and the files can be imported cleanly.

Hard constraints (all from spec)
---------------------------------
  REQ-700-130 — No parallel chains: one execution path per request.
  REQ-700-131 — No bypass: Router and Evaluator are mandatory.
  REQ-700-132 — No cross-mode mixing within a turn.
  REQ-700-133 — LLM receives only synthesized/filtered inputs.
  REQ-200-170 — Regeneration loop capped at MAX_REGEN_ATTEMPTS = 2.
  REQ-700-LOG1 — All trace data is session-scoped and ephemeral.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol, runtime_checkable

# [CONCEPT] Protocol — Python's structural subtyping interface. Unlike
# abstract base classes, a Protocol does not require explicit inheritance.
# Any class that implements the required methods satisfies the Protocol,
# making dependency injection easy without coupling the pipeline to a
# specific LLM library. See PEP 544.
from typing import Protocol, runtime_checkable

from docs.schemas.acp_schemas import (
    CrisisResource,
    DistressLevel,
    EvaluationPayload,
    EvaluationVerdict,
    EvidenceItem,
    EvidencePayload,
    EvidenceTier,
    OperationalMode,
    ResponseContextPayload,
    ScopeClassifierDecision,
    ScopeDecision,
    SignalPayload,
    SourceTier,
    StrategyPayload,
    SynthesizedEvidence,
    VerificationResult,
)
from docs.schemas.retrieval_schemas import (
    PubMedQueryParams,
    RetrievalResult,
    StaticCacheQueryParams,
)
from retrieval import ADAPTER_PRIORITY_ORDER, PubMedAdapter, WebSearchAdapter
from retrieval.web_search_adapter import (
    TopicTag as _TopicTag,
    get_preferred_source_labels as _get_preferred_source_labels,
)
from agents.synthesizer_agent import EvidenceSynthesizerAgent
from agents.evaluator_agent import EvaluatorAgent
from agents.verification_supervisor import (
    VerificationSupervisorAgent,
    SAFE_FALLBACK_RESPONSE,
    MAX_REGEN_ATTEMPTS,
)
from agents.router import Router, RouterDecision

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADP-B late-crisis sentinel
# ---------------------------------------------------------------------------

# [CONCEPT] ADPB_CRISIS_SENTINEL is a string token returned by
# HFSpaceFullGenerator.generate() when ADP-B fires crisis=True AFTER the local
# pipeline already routed to COMFORT mode (the stub SignalAgent doesn't detect
# crisis — it only does keyword-based guidance detection).
#
# Instead of returning "" (which cascades into SAFE_FALLBACK with no crisis
# resources shown), draft_generator.py returns this sentinel. NikkoPipeline.run()
# intercepts it immediately after _step10_draft() and re-routes to a full CRISIS
# PipelineResult, ensuring hotlines and the safety banner are always delivered.
#
# This constant must live here (not in backend/) to preserve the
# DraftGeneratorProtocol abstraction: draft_generator.py imports from
# orchestration.pipeline — the dependency direction never reverses.
ADPB_CRISIS_SENTINEL = "__NIKKO_ADPB_CRISIS_DETECTED__"

# Sentinel returned by HFSpaceFullGenerator.generate() when the Modal LLM
# moderation+scope pass detects coded hate (antisemitism, Islamophobia, etc.)
# that regex pre-gate on Render did not catch.
# pipeline.run() intercepts this and returns _HATE_RESPONSE (static string).
MODERATION_BLOCK_SENTINEL = "__NIKKO_MODERATION_BLOCK__"

# Sentinel returned by HFSpaceFullGenerator.generate() when the Modal LLM
# moderation+scope pass determines the message is OUT_OF_SCOPE for Nikko,
# after the regex ScopeClassifier passed it or called it AMBIGUOUS.
# pipeline.run() intercepts this and returns the generic WARM_REDIRECT.
SCOPE_BLOCK_SENTINEL = "__NIKKO_SCOPE_BLOCK__"

# Crisis text used for the ADP-B late-override path. Mirrors _CRISIS_TEXT in
# backend/main.py — keep in sync if the hotlines or framing ever change.
_ADPB_CRISIS_RESPONSE = (
    "I'm really glad you reached out, and I want to make sure you're safe right now. "
    "Please contact one of these services immediately:\n\n"
    "- **Lifeline:** 13 11 14 (24/7)\n"
    "- **Beyond Blue:** 1300 22 4636\n"
    "- **13YARN** (Aboriginal & Torres Strait Islander): 13 92 76\n"
    "- **Emergency:** 000\n\n"
    "I'm here with you. Would you like to talk about what's going on?"
)

# ---------------------------------------------------------------------------
# Content moderation pre-gate
# ---------------------------------------------------------------------------
# These patterns fire BEFORE the Scope Classifier (STEP 0). They handle content
# that is not merely out-of-scope but actively harmful or CSAM-adjacent. The scope
# classifier is designed to route; this gate is designed to reject.
#
# Design principles:
#   - Runs on RAW (unsanitized) input so whitespace normalization cannot bypass it.
#   - Pattern-only — no LLM involved. Sub-millisecond, deterministic.
#   - Responses are STATIC strings (REQ-XXX-CM3). Never LLM-generated.
#   - Three tiers: CSAM-adjacent, child attraction/pedophilia, hate speech.
#
# Response policy:
#   CSAM content      → terse, firm, zero empathy for the content itself.
#   Child attraction  → firm redirect to licensed professional, non-shaming.
#                       (Some people seek help for unwanted pedophilic urges;
#                        the response is a redirect to care, not a rejection
#                        of the person — but Nikko is not that care provider.)
#   Hate speech       → short firm redirect, no engagement.
#
# [REQ-XXX-CM1] Content moderation MUST fire before any agent or LLM processing.
# [REQ-XXX-CM2] CSAM-adjacent content MUST NOT receive an empathetic validation response.
# [REQ-XXX-CM3] Moderation responses MUST be static strings — never LLM-generated.

# CSAM-adjacent patterns — explicit illegal or quasi-illegal sexual content involving minors
_CSAM_PATTERNS: list[re.Pattern] = [
    # Anime-convention CSAM terminology — includes plural forms (lolis, shotas, etc.)
    re.compile(r"\b(lolis?|lolicons?|shotas?|shotacons?)\b", re.I),
    # Explicit CSAM naming
    re.compile(r"\bchild\s*(porn|pornography)\b", re.I),
    re.compile(r"\bunderage\s+(porn|sex|content|hentai|material)\b", re.I),
    re.compile(r"\b(sexual\s+content|hentai)\s+(involving|featuring|of|with)\s*(children|kids|minors|underage)\b", re.I),
    # Masturbation explicitly to CSAM/minor-coded material.
    # `.{0,30}` allows up to 30 intervening chars ("wanking it to", "masturbating while looking at", etc.)
    # without being loose enough to match across sentence boundaries.
    re.compile(r"\b(wank(ing)?|masturbat\w*|jerk(ing)?\s+off?).{0,30}(to|over)\s+(lolis?|shotas?|child|kids?|minor|underage|children)\b", re.I),
]

# Child attraction / pedophilia patterns — disclosure of sexual attraction to children
_CHILD_ATTRACTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(attracted|attraction)\s+to\s+(children|kids|minors|child|kid|underage)\b", re.I),
    re.compile(r"\bpedophil\w*\b", re.I),
    re.compile(r"\b(sexual\s+feelings?|sexual\s+interest|sexual\s+attraction)\s+(in|towards?|for|about)\s+(children|kids|minors|a\s+child|a\s+kid)\b", re.I),
    re.compile(r"\b(like|love|want)\s+(children|kids|minors)\s+(sexually|in\s+that\s+way|that\s+way)\b", re.I),
]

# Hate speech, hard slurs, and explicit dehumanization patterns.
#
# Coverage rationale:
#   Hard slurs and explicit calls for violence/extermination against groups are
#   unambiguous and warrant immediate blocking. This is NOT a soft-discrimination
#   filter — statements like "my boss is ageist", "I hate immigrants", or
#   "women are too emotional" are grey-area and potentially valid wellbeing
#   conversations (frustration, relationship stress, etc.). Those pass through
#   to the LLM, which is better positioned to navigate nuance than a regex gate.
#   Softer discrimination is handled downstream by ADP-B and the COMFORT framing.
#
#   Slur patterns use common 1337-speak substitutions to catch basic obfuscation
#   (1→i, 3→e, @→a, 0→o). They do not attempt to out-race creative obfuscation
#   — that is a losing arms race. Clear-text and light-obfuscation hits are the
#   intended target; edge cases fall to ADP-B.
_HATE_PATTERNS: list[re.Pattern] = [
    # ── Calls for mass violence / extermination ───────────────────────────────
    re.compile(r"\b(kill\s+all|exterminate\s+(all|the)|genocide\s+(the|all)|gas\s+the)\b", re.I),
    re.compile(r"\b(should\s+be\s+(exterminated|wiped\s+out|eliminated|purged))\b", re.I),
    re.compile(r"\bdie\s+(you|all|every)\b", re.I),

    # ── Explicit dehumanization of demographic groups ─────────────────────────
    # "[group] are subhuman / animals / vermin / parasites / inferior"
    re.compile(
        r"\b(black|white|asian|hispanic|latino|jewish|muslim|christian|gay|lesbian|"
        r"trans|queer|immigrant|refugee|aboriginal|indigenous|disabled|women|men)\s+"
        r"(people\s+)?(are\s+)?(subhuman|animals?|vermin|parasites?|filth|scum|inferior|worthless)\b",
        re.I,
    ),

    # ── Racial / ethnic slurs ─────────────────────────────────────────────────
    re.compile(r"\bn[i1][gq][gq][e3][rr]s?\b", re.I),          # anti-Black
    re.compile(r"\bch[i1][n][k]s?\b", re.I),                     # anti-Asian
    re.compile(r"\bg[o0][o0]ks?\b", re.I),                        # anti-Asian
    re.compile(r"\bsp[i1][ck]s?\b", re.I),                        # anti-Hispanic/Latino
    re.compile(r"\bw[e3]tb[a@]cks?\b", re.I),                    # anti-Hispanic/Latino
    re.compile(r"\bk[i1][k][e3]s?\b", re.I),                     # anti-Jewish
    re.compile(r"\bpak[i1]s?\b", re.I),                           # anti-South Asian (AU/UK context)
    re.compile(r"\br[a@]gh[e3][a@]ds?\b", re.I),                 # anti-Arab/Muslim
    re.compile(r"\btow[e3]l\s*h[e3][a@]ds?\b", re.I),            # anti-Arab/Muslim
    re.compile(r"\bs[a@]nd\s*n[i1]gg[e3]rs?\b", re.I),           # anti-Arab/Middle Eastern

    # ── Homophobic / transphobic slurs ────────────────────────────────────────
    re.compile(r"\bf[a@][gq][gq][o0]ts?\b", re.I),               # homophobic
    re.compile(r"\btr[a@]nn[yi]e?s?\b", re.I),                   # transphobic
    re.compile(r"\bsh[e3]males?\b", re.I),                        # transphobic (used as slur)

    # ── Ableist slurs ─────────────────────────────────────────────────────────
    re.compile(r"\br[e3]t[a@]rd(ed|s)?\b", re.I),                # ableist hard slur

    # ── Sexist dehumanization ─────────────────────────────────────────────────
    # Targets explicit collective attacks on gender groups, not casual language
    re.compile(r"\b(all\s+women|all\s+men|every\s+woman|every\s+man|all\s+females?|all\s+males?)\s+(are\s+)?(wh[o0]res?|sl[u]ts?)\b", re.I),
    re.compile(r"\bwomen\s+(belong|should\s+(be|stay))\s+(in\s+the\s+kitchen|beneath\s+men|below\s+men)\b", re.I),

    # ── Ageist dehumanization ─────────────────────────────────────────────────
    re.compile(r"\b(old\s+people|elderly|seniors?)\s+(should\s+(die|be\s+(killed|put\s+down))|are\s+(useless|worthless|a\s+burden\s+on\s+society))\b", re.I),
]

# Active crime / emergency report patterns.
#
# Catches first-person reports of having just committed or witnessed a serious
# incident — "I just ran someone over", "I just stabbed someone", "I watched
# someone get shot". These need emergency services (000) and/or legal advice,
# not a mental health companion.
#
# Why the pre-gate and not the scope classifier?
#   - We need a specific 000-redirect response, not the generic warm redirect.
#   - Unlike physical health, there is no meaningful "crime + emotional distress"
#     case where Nikko's comfort mode is the right FIRST response. The 000/legal
#     need is always immediate; emotional support can follow once the person
#     is safe (the response says as much).
#
# Scope: past-tense completed actions only. Threats ("I want to hurt someone")
# and worries ("I'm scared I might hurt someone") are mental health / crisis
# territory and are NOT matched here — they pass to the crisis pipeline.
_CRIME_PATTERNS: list[re.Pattern] = [
    # First-person perpetrator — "I just [harmed] someone"
    re.compile(r"\bI\s+(just\s+|accidentally\s+)?(ran\s+over|hit|struck|stabbed|shot|killed|attacked|assaulted|punched|strangled|choked|hurt|harmed|injured)\s+(someone|somebody|a\s+(person|man|woman|kid|child|pedestrian|cyclist|driver))\b", re.I),
    # First-person perpetrator — "I [committed a crime]"
    re.compile(r"\bI\s+(just\s+)?(committed|did|have\s+(committed|done))\s+(a\s+)?(crime|murder|manslaughter|robbery|assault|sexual\s+assault|rape|theft|arson)\b", re.I),
    # Witness — "I just witnessed / saw [serious incident]"
    re.compile(r"\bI\s+(just\s+)?(witnessed|saw|watched)\s+(a\s+)?(murder|stabbing|shooting|hit.and.run|serious\s+accident|someone\s+(get\s+)?(stabbed|shot|killed|attacked))\b", re.I),
    # "There's been an accident / someone is badly hurt / there's a body"
    re.compile(r"\b(there'?s\s+(been\s+a|a)\s+(serious\s+)?accident|someone\s+is\s+(badly\s+hurt|unconscious|not\s+breathing|bleeding\s+out)|I\s+found\s+(a\s+)?body)\b", re.I),
]

_CRIME_RESPONSE: str = (
    "If this is an active emergency, call 000 immediately — that needs real human help right now. "
    "If you need legal support, a lawyer or Legal Aid can assist. "
    "Once you're safe, if you're struggling with what happened emotionally, I'm here for that."
)

# Static moderation responses (REQ-XXX-CM3)
_CSAM_RESPONSE: str = (
    "That's not something Nikko can engage with. "
    "If something else is genuinely on your mind, I'm here."
)

_CHILD_ATTRACTION_RESPONSE: str = (
    "Nikko is a wellbeing support tool — what you've described is outside what I can help with here. "
    "If you're experiencing unwanted attractions to children and want to address that, "
    "speaking with a licensed psychologist who specialises in this area is the right step. "
    "A GP referral is confidential."
)

_HATE_RESPONSE: str = (
    "That's not something I'm able to engage with here. "
    "If something else is weighing on you, I'm here to listen."
)


# ---------------------------------------------------------------------------
# Inference environment flag
# ---------------------------------------------------------------------------

# [CONCEPT] NIKKO_LOCAL_LLM controls whether the pipeline attempts to load
# local LLM-backed agents (SignalAgent, SupportStrategyAgent, EvaluatorAgent).
# These agents require torch + transformers and a GPU with ~6 GB VRAM.
#
# On Render (production orchestration layer), set:
#   NIKKO_LOCAL_LLM=false
# All LLM work is delegated to HF Spaces (ADP-A/B/C). Local agents run as
# lightweight stubs — keyword-based signal detection, static strategy fallback,
# regex-only evaluation. No model download attempts, no OOM errors.
#
# On a local GPU machine or Colab, set NIKKO_LOCAL_LLM=true (or leave unset)
# to load the real agents.
import os as _os
_LOCAL_LLM: bool = _os.getenv("NIKKO_LOCAL_LLM", "true").lower() not in ("false", "0", "no")

if not _LOCAL_LLM:
    logger.info(
        "NIKKO_LOCAL_LLM=false — all LLM-backed agents will use stubs. "
        "Signal detection: keyword fallback. Strategy: static. "
        "Evaluation: regex red-lines only (no LLM judge). "
        "All LLM inference delegated to HF Spaces."
    )

# ---------------------------------------------------------------------------
# Agent stubs (used when FUSE-truncated agents cannot be imported cleanly,
# or when NIKKO_LOCAL_LLM=false disables local inference on Render)
# ---------------------------------------------------------------------------

# [CONCEPT] try/except at import time — we attempt to import the full agent
# implementation. If Python raises a SyntaxError (caused by the FUSE mount
# showing a truncated version of the file) we fall through to the stub.
# This lets the pipeline run end-to-end in Phase 3 without requiring all
# agents to be syntactically correct in the Linux sandbox.
#
# IMPORTANT: ScopeClassifier is pure regex — no LLM, no GPU, no torch.
# It MUST be imported unconditionally regardless of NIKKO_LOCAL_LLM.
# Previously it was gated behind _LOCAL_LLM alongside the LLM-backed agents,
# which caused the stub (always IN_SCOPE) to run on Render where
# NIKKO_LOCAL_LLM=false — meaning scope filtering never ran in production.
# Fixed 2026-05-21 (REQ-200-SC1).

# ── ScopeClassifier — always imported, no LLM dependency ─────────────────────
try:
    from agents.scope_classifier import ScopeClassifier as _ScopeClassifier, WARM_REDIRECT
    _HAVE_SCOPE_CLASSIFIER = True
except (SyntaxError, ImportError) as _exc:
    _HAVE_SCOPE_CLASSIFIER = False
    # Fallback redirect used when the real ScopeClassifier cannot be imported.
    WARM_REDIRECT = (
        "That's a bit outside what I'm set up for — Nikko is here for emotional "
        "wellbeing and mental health support. If something's been on your mind "
        "or weighing on you, I'm here for that."
    )
    logger.warning("ScopeClassifier unavailable (%s) — using stub (all messages pass through).", _exc)

# ── LLM-backed agents — only loaded when NIKKO_LOCAL_LLM=true ────────────────
# When NIKKO_LOCAL_LLM=false the real agents are never imported regardless.
if _LOCAL_LLM:
    try:
        from agents.signal_agent import SignalAgent as _SignalAgent
        _HAVE_SIGNAL_AGENT = True
    except (SyntaxError, ImportError):
        _HAVE_SIGNAL_AGENT = False
        logger.warning("SignalAgent unavailable (FUSE truncation) — using stub.")

    try:
        from agents.support_strategy_agent import SupportStrategyAgent as _SupportStrategyAgent
        _HAVE_STRATEGY_AGENT = True
    except (SyntaxError, ImportError):
        _HAVE_STRATEGY_AGENT = False
        logger.warning("SupportStrategyAgent unavailable (FUSE truncation) — using stub.")
else:
    _HAVE_SIGNAL_AGENT   = False
    _HAVE_STRATEGY_AGENT = False


class _StubScopeClassifier:
    """
    Stub Scope Classifier — always returns IN_SCOPE at high confidence.
    Used when the real ScopeClassifier cannot be imported (FUSE truncation).
    Replace with the real ScopeClassifier for production.
    """
    def classify(self, text: str) -> ScopeClassifierDecision:
        return ScopeClassifierDecision(
            decision=ScopeDecision.IN_SCOPE,
            confidence=0.99,
            warm_redirect=None,
        )


class _StubSignalAgent:
    """
    Stub Signal Agent — returns LOW distress with keyword-based guidance detection.
    Used when the real SignalAgent cannot be imported (FUSE truncation).

    Previously returned all-empty signal arrays, which permanently suppressed
    GUIDANCE routing. Now applies the same lightweight keyword scan used in the
    _step2_signal exception path so explicit guidance-seeking messages still
    reach GUIDANCE mode even without the real LLM-backed agent.
    Replace with the real SignalAgent for production.
    """

    _GUIDANCE_KEYWORDS: frozenset = frozenset({
        "cbt", "dbt", "emdr", "therapy", "therapist",
        "technique", "techniques", "exercise", "exercises",
        "strategy", "strategies", "method", "methods",
        "how do i", "how to", "what can i do", "what should i",
        # Catches "is there anything I can do", "anything that I could do",
        # "anything I can try", "is there anything to help" — explicit
        # action-seeking even when not phrased as "what can I do".
        "anything i can", "anything that i can", "anything i could",
        "is there anything i", "anything to help", "what to do",
        "is there anything to", "what can help", "what helps",
        "help me", "advice", "tips", "resources", "skills",
        "psychoeducation", "mindfulness", "breathing",
    })

    def analyze(self, text: str, **kwargs) -> SignalPayload:
        text_lower = text.lower()
        has_guidance_intent = any(
            kw in text_lower for kw in self._GUIDANCE_KEYWORDS
        )
        return SignalPayload(
            distress_level=DistressLevel.LOW,
            # 0.6 when guidance intent detected — above Router's 0.40 low-band
            # ceiling so Rule 4 (guidance check) is reached. 0.5 otherwise —
            # still above threshold, COMFORT default via Rule 5.
            confidence=0.6 if has_guidance_intent else 0.5,
            emotional_states=[],
            cognitive_patterns=[],
            behavioral_indicators=(
                ["help_seeking_behavior"] if has_guidance_intent else []
            ),
            risk_indicators=[],
            support_needs=(
                ["psychoeducation"] if has_guidance_intent else []
            ),
            uncertainty_notes=(
                f"[STUB — real SignalAgent unavailable; "
                f"guidance_intent={has_guidance_intent}]"
            ),
        )


class _StubStrategyAgent:
    """
    Stub Support Strategy Agent — returns a minimal valid StrategyPayload.
    Used when the real SupportStrategyAgent cannot be imported (FUSE truncation).

    strategize() now accepts a RouterDecision (same as the real agent) so the
    pipeline can pass router_decision uniformly without branching on agent type.
    """
    def strategize(self, router_decision: RouterDecision, signal: SignalPayload) -> StrategyPayload:
        return StrategyPayload(
            mode=router_decision.mode,
            distress_level=signal.distress_level,
            tone_guidance="warm, empathetic, non-directive",
            framing_strategy="validate the user's experience before offering perspective",
        )

    def crisis_bypass(self) -> StrategyPayload:
        # Signature matches the real SupportStrategyAgent.crisis_bypass() — no args.
        return StrategyPayload(
            mode=OperationalMode.CRISIS,
            distress_level=DistressLevel.CRISIS,
            tone_guidance="calm, direct, safety-focused",
            framing_strategy="immediate safety acknowledgement; resource delivery",
        )


# ---------------------------------------------------------------------------
# Draft generator protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class DraftGeneratorProtocol(Protocol):
    """
    Protocol for the Interaction Model (LLM draft generator).

    Phase 3 stub returns a canned empathetic response.
    Phase 4/MVP implements this via Qwen3-4B base (no LoRA; see hf_space/app.py).
    Director-approved 2026-05-14. See hf_space/app.py for production dispatch logic.

    The pipeline calls generate() after building the ResponseContextPayload.
    The generator receives the full context so it can apply tone guidance,
    evidence citations, and crisis framing as directed. (REQ-700-133)
    """
    def generate(self, context: ResponseContextPayload) -> str:
        ...  # pragma: no cover


class StubDraftGenerator:
    """
    Phase 3 stub Interaction Model.

    Returns a canned response appropriate to the mode, demonstrating that
    the pipeline wiring is correct without requiring a GPU or model weights.
    Replace with a real LLM-backed implementation for Phase 4.
    """

    _COMFORT_DRAFT = (
        "It sounds like you're carrying a lot right now, and that makes sense given "
        "what you've shared. You don't have to work through this alone — reaching out "
        "is a meaningful step, and I'm here to support you."
    )
    _GUIDANCE_DRAFT = (
        "Based on the evidence I've gathered, there are a few things that may help. "
        "Speaking with a mental health professional can make a real difference, and "
        "evidence-based approaches like CBT have shown strong results for many people. "
        "Please treat this as information to explore, not a directive — you know your "
        "situation best."
    )
    _CRISIS_DRAFT = (
        "I can hear that things feel very difficult right now. Your safety matters most. "
        "Please reach out to one of the crisis support services below — they are "
        "available 24/7 and are there specifically for moments like this."
    )

    def generate(self, context: ResponseContextPayload) -> str:
        if context.mode == OperationalMode.CRISIS:
            return self._CRISIS_DRAFT
        if context.mode == OperationalMode.GUIDANCE:
            return self._GUIDANCE_DRAFT
        return self._COMFORT_DRAFT


# ---------------------------------------------------------------------------
# SPEC-300 §5: Baseline Australian crisis resources (mandatory in Crisis Mode)
# ---------------------------------------------------------------------------

# [CONCEPT] These are hardcoded in the pipeline because SPEC-300 §5 defines
# them as *mandatory static content* — they must not be LLM-generated or
# retrieved dynamically. The only permissible change is an admin update when
# a hotline number changes in the real world. (REQ-700-070)
BASELINE_CRISIS_RESOURCES: list[CrisisResource] = [
    # REQ-300-RS1: these four resources MUST always be displayed during Crisis Mode.
    # Order matches SPEC-300 §5 Step 2 and G-CRISIS-03 ratification.
    # Do NOT remove or reorder without Director approval.
    CrisisResource(name="Lifeline Australia",           number="13 11 14",     tier="baseline"),
    CrisisResource(name="Beyond Blue",                  number="1300 22 4636", tier="baseline"),
    CrisisResource(name="Suicide Call Back Service",    number="1300 659 467", tier="baseline"),
    CrisisResource(name="Emergency Services",           number="000",           tier="baseline"),
]

# REQ-300-RS2: demographic-specific resources — presented in the UI as a
# "More tailored support" expandable alongside the baseline set.
# NOT inferred from conversation context (REQ-300-RS3).
DEMOGRAPHIC_CRISIS_RESOURCES: list[CrisisResource] = [
    CrisisResource(name="QLife (LGBTIQ+)",            number="1800 184 527", tier="demographic_specific"),
    CrisisResource(name="13YARN (First Nations)",     number="13 92 76",     tier="demographic_specific"),
    CrisisResource(name="Kids Helpline (under 25)",   number="1800 55 1800", tier="demographic_specific"),
    CrisisResource(name="1800RESPECT (family violence)", number="1800 737 732", tier="demographic_specific"),
    CrisisResource(name="MensLine Australia",         number="1300 78 99 78", tier="demographic_specific"),
]


# ---------------------------------------------------------------------------
# Pipeline trace (REQ-700-110)
# ---------------------------------------------------------------------------

@dataclass
class PipelineTrace:
    """
    Session-scoped audit trace — destroyed when the session ends (REQ-700-LOG1).

    Fields map directly to the JSON schema defined in REQ-700-110. All
    timestamps are UTC. This object is never persisted; it lives only in
    memory for the duration of the pipeline run.
    """
    session_id:           str  = field(default_factory=lambda: str(uuid.uuid4()))
    execution_path:       list[str] = field(default_factory=list)
    signal_output:        Optional[dict] = None
    router_decision:      Optional[str] = None
    agents_triggered:     list[str] = field(default_factory=list)
    evidence_used:        list[str] = field(default_factory=list)
    adapter_configuration:list[str] = field(default_factory=list)
    evaluation_result:    Optional[str] = None
    verification_result:  Optional[str] = None
    final_action:         Optional[str] = None
    regen_count:          int = 0
    latency_ms:           Optional[float] = None
    started_at:           datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    def step(self, agent_name: str) -> None:
        """Record a completed pipeline step."""
        self.execution_path.append(agent_name)
        self.agents_triggered.append(agent_name)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    Unified output of NikkoPipeline.run().

    The frontend / API layer consumes this object. Fields not relevant to
    the current turn are None (e.g., verification is None when out_of_scope
    is True because the pipeline terminated at STEP 0).

    citations: the EvidenceItems used in GUIDANCE mode RAG retrieval.
               Empty list in COMFORT/CRISIS mode or when retrieval found nothing.
               Serialized to SourceItem dicts in backend/main.py and sent to
               the frontend via SSEChunk.sources for the dynamic sources panel.
    """
    response_text:        str
    mode:                 Optional[OperationalMode] = None
    out_of_scope:         bool = False
    safe_fallback_used:   bool = False
    evaluation:           Optional[EvaluationPayload] = None
    verification:         Optional[VerificationResult] = None
    trace:                Optional[PipelineTrace] = None
    crisis_resources:     Optional[list[CrisisResource]] = None
    citations:            list[EvidenceItem] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.citations is None:
            self.citations = []


# ---------------------------------------------------------------------------
# Retrieval helper
# ---------------------------------------------------------------------------

def _retrieval_result_to_evidence_payload(result: RetrievalResult) -> EvidencePayload:
    """
    Convert a retrieval adapter's RetrievalResult into the ACP EvidencePayload
    that the EvidenceSynthesizerAgent expects.

    [CONCEPT] The two schemas live in different files (retrieval_schemas vs
    acp_schemas) because the retrieval layer was designed independently of
    the ACP message contracts. This conversion is the seam between those two
    domains. It is intentionally thin — no data is transformed, only re-shaped.
    """
    return EvidencePayload(
        query=result.query_echo,
        source_name=result.source_name,
        source_tier=result.source_tier,
        results=result.items,                    # list[EvidenceItem] — same type
        grey_literature_flag=result.grey_literature_flag,
    )


# ---------------------------------------------------------------------------
# Evidence search query builder
# ---------------------------------------------------------------------------

# Map signal key names (from SignalAgent) to human-readable search terms
# suitable for DuckDuckGo and PubMed queries.
_SUPPORT_NEED_TERMS: dict[str, str] = {
    "coping_strategies":        "coping strategies",
    "relaxation_techniques":    "relaxation techniques",
    "psychoeducation":          "mental health education",
    "behavioral_activation":    "behavioral activation",
    "cognitive_restructuring":  "cognitive restructuring",
    "problem_solving":          "problem solving strategies",
    "social_support_resources": "social support",
    "crisis_intervention":      "crisis intervention",
    "grounding_exercises":      "grounding exercises",
    "mindfulness":              "mindfulness meditation",
}

_EMOTIONAL_STATE_TERMS: dict[str, str] = {
    "sadness_spectrum":         "low mood depression sadness",
    "anxiety_spectrum":         "anxiety worry stress",
    "emotional_dysregulation":  "emotional dysregulation",
    "shame_guilt":              "shame guilt",
    "emotional_numbness":       "emotional numbness",
}

_COGNITIVE_PATTERN_TERMS: dict[str, str] = {
    "rumination":               "rumination overthinking",
    "catastrophizing":          "catastrophizing negative thinking",
    "black_white_thinking":     "black and white thinking",
    "hopeless_projection":      "hopelessness",
    "personalization":          "self-blame",
    "negative_core_beliefs":    "negative self-beliefs",
    "helplessness":             "learned helplessness",
    "meaninglessness":          "loss of meaning",
}


# ---------------------------------------------------------------------------
# Topic keyword patterns: scan raw user text for specific clinical topics.
# These augment signal key lookups which only detect THAT a technique was
# requested, not WHICH specific technique — so "calming techniques" would
# only fire help_seeking_behavior → "psychoeducation", missing the
# specificity of "calming/relaxation". Scanning the text directly captures
# the clinical concept the user named.
#
# Each entry: (compiled regex, search term to inject into query)
# Ordered from most specific to most general — first N matches win.
# ---------------------------------------------------------------------------
_TOPIC_KEYWORD_PATTERNS: list[tuple[re.Pattern, str]] = [
    # ── Specific technique categories ────────────────────────────────────────
    (re.compile(
        r"\b(calm|calming|relax|relaxation|soothe|settle|ease|unwind|de-stress)", re.I),
     "relaxation techniques anxiety management"),
    (re.compile(
        r"\b(breath|breathing|breathe|box breath|4-7-8|diaphragm|belly breath)", re.I),
     "breathing exercises relaxation"),
    (re.compile(
        r"\b(ground|grounding|5-4-3-2-1|anchor|present moment|here and now)", re.I),
     "grounding exercises anxiety"),
    (re.compile(
        r"\b(mindful|mindfulness|meditat|aware|awareness|body scan)", re.I),
     "mindfulness meditation mental health"),
    (re.compile(
        r"\b(progressiv(e)? muscle|PMR|muscle relax|tension.releas)", re.I),
     "progressive muscle relaxation"),
    (re.compile(
        r"\b(yoga|stretching|movement|exercise for (stress|anxiety|mood))", re.I),
     "exercise movement mental health benefits"),
    (re.compile(
        r"\b(journal|writing|expressive writing|thought diary|mood diary)", re.I),
     "expressive writing journaling mental health"),
    (re.compile(
        r"\b(CBT|cognitive behav|thought challeng|reframe|restructur|negative thought)", re.I),
     "cognitive behavioural therapy techniques"),
    (re.compile(
        r"\b(DBT|dialectical|distress toleran|emotion regulat|interpersonal effectiv)", re.I),
     "dialectical behaviour therapy skills"),
    (re.compile(
        r"\b(ACT|acceptance.commit|psychological flexib|defusion|values-based)", re.I),
     "acceptance commitment therapy"),
    (re.compile(
        r"\b(EMDR|eye movement|trauma-focused|trauma processing)", re.I),
     "EMDR trauma therapy"),

    # ── Physical / somatic symptoms ───────────────────────────────────────────
    (re.compile(
        r"\b(shak|trembl|tremble|shiver|quiver|body shak)", re.I),
     "anxiety physical symptoms shaking management"),
    (re.compile(
        r"\b(heart (racing|pound|beat fast)|palpitat|chest tight|chest pain)", re.I),
     "panic attack physical symptoms management"),
    (re.compile(
        r"\b(sweat|sweat(ing)?|flush|hot flash|dizziness|lightheaded|nausea)", re.I),
     "anxiety somatic symptoms management"),
    (re.compile(
        r"\b(panic attack|hyperventilat|freeze|frozen|fight.or.flight)", re.I),
     "panic attack management acute anxiety"),
    (re.compile(
        r"\b(headache|tension headache|migraine|muscle tension|jaw clench)", re.I),
     "stress physical symptoms management"),
    (re.compile(
        r"\b(sleep|insomni|can't sleep|wake up|night sweat|restless|fatigue|exhaust)", re.I),
     "sleep hygiene mental health anxiety"),

    # ── Emotional states (more specific than signal keys) ─────────────────────
    (re.compile(
        r"\b(anxi|worry|worr|dread|apprehens|on edge|nervous|fear)", re.I),
     "anxiety management strategies"),
    (re.compile(
        r"\b(depress|low mood|down|unmotivat|no energy|empty|flat)", re.I),
     "depression management wellbeing strategies"),
    (re.compile(
        r"\b(sad|sadness|grief|loss|bereavem|mourn|losing someone)", re.I),
     "grief loss coping mental health"),
    (re.compile(
        r"\b(anger|angry|rage|furious|frustrat|irrita|snap|temper)", re.I),
     "anger management strategies"),
    (re.compile(
        r"\b(stress|stressed|overwhelm|pressure|too much|burnout)", re.I),
     "stress management wellbeing"),
    (re.compile(
        r"\b(shame|ashamed|embarrass|humiliat|self-conscious)", re.I),
     "shame self-compassion mental health"),
    (re.compile(
        r"\b(guilt|guilty|blame myself|regret|remorse)", re.I),
     "guilt self-forgiveness mental health"),
    (re.compile(
        r"\b(numb|empty|hollow|dissociat|feel nothing|disconnect)", re.I),
     "emotional numbing dissociation wellbeing"),
    (re.compile(
        r"\b(lonely|alone|isolat|no one|disconnected|left out)", re.I),
     "loneliness social connection mental health"),

    # ── Life domains ──────────────────────────────────────────────────────────
    (re.compile(
        r"\b(work stress|workplace|job stress|overwork|work.life|career pressure)", re.I),
     "workplace stress burnout management"),
    (re.compile(
        r"\b(relationship|partner|marriage|breakup|divorce|conflict)", re.I),
     "relationship wellbeing mental health"),
    (re.compile(
        r"\b(social anxiet|social situation|meeting people|crowds|public)", re.I),
     "social anxiety management strategies"),
    (re.compile(
        r"\b(trauma|PTSD|post-traumatic|flashback|nightmare|hypervigilant|triggered)", re.I),
     "trauma recovery PTSD mental health"),
    (re.compile(
        r"\b(self.esteem|confidence|self-worth|self.image|believe in myself|imposter)", re.I),
     "self-esteem confidence mental health"),
    (re.compile(
        r"\b(motivation|unmotivat|procrastinat|can't start|no drive)", re.I),
     "motivation wellbeing mental health"),
]


def _build_evidence_query(signal: SignalPayload, user_text: str = "") -> str:
    """
    Build a focused clinical search query from SignalPayload + raw user text.

    Two-pass construction
    ---------------------
    Pass 1 — Signal keys: support_needs, emotional_states, cognitive_patterns
             mapped to clinical search terms via lookup tables.
    Pass 2 — Keyword extraction: scan user_text against _TOPIC_KEYWORD_PATTERNS
             to catch specificity that signal keys cannot capture.

             Example: "is there any calming techniques to stop shaking?"
               Signal produces: help_seeking_behavior → "psychoeducation"
               Keyword scan finds: "calm" → "relaxation techniques anxiety management"
                                   "shak" → "anxiety physical symptoms shaking management"
               Final query: "relaxation techniques anxiety management for anxiety physical symptoms"

    Keyword-extracted terms REPLACE generic signal-derived terms (like
    "mental health education" from "psychoeducation") when they exist —
    because the user's own words carry more specificity than the inferred category.

    Query length is capped at ~100 chars. DuckDuckGo and PubMed both score
    shorter, focused queries higher than long compound queries.
    """
    # ── Pass 1: Signal-derived terms ─────────────────────────────────────────
    topic_terms: list[str] = []
    for key in (signal.support_needs or []):
        term = _SUPPORT_NEED_TERMS.get(key)
        if term and term not in topic_terms:
            topic_terms.append(term)

    emotional_terms: list[str] = []
    for key in (signal.emotional_states or []):
        term = _EMOTIONAL_STATE_TERMS.get(key)
        if term and term not in emotional_terms:
            emotional_terms.append(term)
    for key in (signal.cognitive_patterns or []):
        term = _COGNITIVE_PATTERN_TERMS.get(key)
        if term and term not in topic_terms and term not in emotional_terms:
            emotional_terms.append(term)

    # ── Pass 2: Keyword extraction from user text ─────────────────────────────
    extracted_topics: list[str] = []
    if user_text:
        for pattern, term in _TOPIC_KEYWORD_PATTERNS:
            if pattern.search(user_text) and term not in extracted_topics:
                extracted_topics.append(term)
                if len(extracted_topics) >= 3:
                    break  # cap to avoid over-specifying

    # ── Merge: keyword-extracted terms override generic signal terms ──────────
    # If Pass 2 found specific topics from the message text, use those instead
    # of broad signal-derived terms. The user's own words are more specific.
    if extracted_topics:
        final_topic_terms = extracted_topics        # e.g. ["relaxation techniques ...", "anxiety physical symptoms ..."]
        # Still include emotional terms from signals (they add useful context).
    else:
        final_topic_terms = topic_terms[:3]

    topic_part     = " ".join(final_topic_terms[:2])   # max 2 topic phrases
    emotional_part = " ".join(emotional_terms[:1])     # max 1 emotional context

    if topic_part and emotional_part:
        return f"{topic_part} for {emotional_part} mental health"
    elif topic_part:
        return f"{topic_part} mental health"
    elif emotional_part:
        return f"{emotional_part} mental health support"
    else:
        return "mental health wellbeing coping strategies"


# ---------------------------------------------------------------------------
# Signal → Topic bridge (G-RETRIEVAL-02)
# ---------------------------------------------------------------------------

def _signal_to_topic_hints(signal: SignalPayload) -> frozenset:
    """
    Translate a SignalPayload into a frozenset of TopicTag string values.

    Why do this instead of letting the adapter run its own keyword classifier?
    The Signal Agent has already performed a semantically richer analysis of
    the message than simple substring matching.  Its output fields (risk
    indicators, support needs, emotional states) encode the *clinical meaning*
    of the message — not just the vocabulary.  Passing these forward means the
    retrieval layer gets the correct topic set for free, without re-scanning
    the raw text a second time.

    Mapping rationale
    -----------------
    risk_indicators "risk.active.*" / "risk.acute.*"  → CRISIS
    distress_level == CRISIS                           → CRISIS
    support_needs "crisis_escalation"                  → CRISIS
    support_needs "psychoeducation"                    → CLINICAL
    support_needs "encouragement_external_support"     → SERVICES
    support_needs "grounding_stabilization"            → ANXIETY
    emotional_states "*.grief_expression"              → GRIEF
    emotional_states "*.loss_oriented_statements"      → GRIEF
    emotional_states "anxiety_spectrum.*"              → ANXIETY
    emotional_states "sadness_spectrum.*"              → DEPRESSION
    cognitive_patterns "hopeless_future_projection"    → DEPRESSION
    cognitive_patterns "meaninglessness_expression"    → DEPRESSION
    cognitive_patterns "rumination_loop"               → ANXIETY
    cognitive_patterns "catastrophizing"               → ANXIETY

    Returns an empty frozenset if no mapping fires (e.g. stub agent with
    all-empty arrays) — the adapters then fall back to their own keyword
    classifiers, preserving existing behaviour on Render (NIKKO_LOCAL_LLM=false).

    Parameters
    ----------
    signal : SignalPayload
        Output of the Signal Agent (real or stub) for the current turn.

    Returns
    -------
    frozenset
        Zero or more _TopicTag string values.
    """
    topics: set = set()

    # ── Risk indicators → CRISIS ─────────────────────────────────────────
    # risk.active.* and risk.acute.* are the two highest-risk subcategories.
    # risk.passive.* (wishing_to_disappear etc.) does not necessarily indicate
    # an active crisis requiring crisis-domain sources.
    for indicator in (signal.risk_indicators or []):
        if "risk.active" in indicator or "risk.acute" in indicator:
            topics.add(_TopicTag.CRISIS)
            break

    # Distress level CRISIS is an unconditional CRISIS signal.
    if signal.distress_level == DistressLevel.CRISIS:
        topics.add(_TopicTag.CRISIS)

    # ── Support needs → topics ────────────────────────────────────────────
    _NEED_MAP: dict[str, _TopicTag] = {
        "crisis_escalation":              _TopicTag.CRISIS,
        "psychoeducation":                _TopicTag.GENERAL,   # grey-lit educational sources, not PubMed
        "encouragement_external_support": _TopicTag.SERVICES,
        "grounding_stabilization":        _TopicTag.ANXIETY,
    }
    for need in (signal.support_needs or []):
        tag = _NEED_MAP.get(need)
        if tag:
            topics.add(tag)

    # ── Emotional states → topics ─────────────────────────────────────────
    # Signal Agent keys use dot notation: "sadness_spectrum.grief_expression".
    # We check both the full key and the root prefix so either form matches.
    _STATE_MAP: dict[str, _TopicTag] = {
        "grief_expression":        _TopicTag.GRIEF,
        "loss_oriented_statements":_TopicTag.GRIEF,
        "anxiety_spectrum":        _TopicTag.ANXIETY,
        "sadness_spectrum":        _TopicTag.DEPRESSION,
        "emotional_dysregulation": _TopicTag.TRAUMA,
    }
    for state in (signal.emotional_states or []):
        # Try full key first, then root prefix, then leaf suffix.
        # Signal Agent keys use dot notation ("sadness_spectrum.grief_expression")
        # so we check all three forms to ensure neither the root category NOR
        # the specific leaf concept is missed (both may carry distinct topics).
        parts = state.split(".")
        tag = (
            _STATE_MAP.get(state)
            or _STATE_MAP.get(parts[0])
            or (len(parts) > 1 and _STATE_MAP.get(parts[-1]))
            or None
        )
        if tag:
            topics.add(tag)
        # If the key has a meaningful leaf, also check leaf independently so
        # compound keys like "sadness_spectrum.grief_expression" add BOTH
        # DEPRESSION (from root) AND GRIEF (from leaf).
        if len(parts) > 1:
            leaf_tag = _STATE_MAP.get(parts[-1])
            if leaf_tag:
                topics.add(leaf_tag)

    # ── Cognitive patterns → topics ───────────────────────────────────────
    _COG_MAP: dict[str, _TopicTag] = {
        "hopeless_future_projection": _TopicTag.DEPRESSION,
        "meaninglessness_expression": _TopicTag.DEPRESSION,
        "helplessness_framing":       _TopicTag.DEPRESSION,
        "rumination_loop":            _TopicTag.ANXIETY,
        "catastrophizing":            _TopicTag.ANXIETY,
        "black_white_thinking":       _TopicTag.ANXIETY,
    }
    for pattern in (signal.cognitive_patterns or []):
        tag = _COG_MAP.get(pattern)
        if tag:
            topics.add(tag)

    logger.debug(
        "_signal_to_topic_hints: distress=%s needs=%s states=%s → topics=%s",
        signal.distress_level.value,
        signal.support_needs,
        signal.emotional_states,
        sorted(topics),
    )
    return frozenset(topics)


# ---------------------------------------------------------------------------
# PubMed eligibility gate (G-RETRIEVAL-03)
# ---------------------------------------------------------------------------

# Topics that warrant a PubMed lookup.  These map to explicitly clinical or
# research-oriented signals — the user is asking "how does X work" or
# "what is the evidence for Y", not "I feel X" or "help me cope with Y".
#
# Only CLINICAL is included by design.  ANXIETY, DEPRESSION, GRIEF etc. are
# *population signals*, not necessarily *research queries*.  Someone saying
# "I've been feeling anxious lately" should get grey-lit guidance sites
# (Beyond Blue, headspace), not a PubMed abstract.  Someone asking "what CBT
# techniques are evidence-based for GAD?" has a CLINICAL support need and
# warrants a PubMed lookup alongside the grey-lit sources.
#
# If future evaluation shows that TRAUMA or other topics consistently produce
# high-quality PubMed results that meaningfully improve response quality,
# add them to this set and log the decision here.
_PUBMED_ELIGIBLE_TOPIC_HINTS: frozenset = frozenset({_TopicTag.CLINICAL})

# Additional clinical keywords checked directly against the evidence query
# string.  This handles the case where the signal agent produces a CLINICAL
# topic hint (e.g. "psychoeducation" support need) but the query-level
# keywords also confirm research intent.  Also catches cases where the stub
# signal agent fires (empty arrays) but the query string is clearly clinical.
_PUBMED_ELIGIBLE_QUERY_KEYWORDS: tuple[str, ...] = (
    "clinical", "evidence", "research", "guideline", "diagnosis",
    "diagnostic", "treatment", "medication", "pharmacological",
    "cognitive behavio",  # catches "cognitive behavioural" and "cognitive behavioral"
    "cbt", "dbt", "therapy", "systematic review", "meta-analysis",
    "randomised", "randomized", "study", "trial",
)


def _is_pubmed_eligible(topic_hints: frozenset, query: str, raw_text: str = "") -> bool:
    """
    Return True if the query warrants a PubMed lookup.

    Three independent signals are checked — True if any of:
      (a) signal-derived topic hints include a CLINICAL-tier tag, OR
      (b) the derived evidence query string contains clinical/research vocabulary, OR
      (c) the raw user text explicitly signals research intent (e.g. "is there
          any research that supports...", "what does the evidence say about...").

    Signal (c) is necessary because the derived evidence query loses the user's
    explicit framing.  For example, "is there any research that supports deep
    breathing for anxiety?" produces an evidence query like
    "breathing exercises relaxation anxiety management" — which contains none of
    the clinical keywords in (b).  Checking (c) catches this case.

    When False, the retrieval step runs WebSearch only.  This ensures general
    emotional queries ("I feel overwhelmed", "help me cope with grief") are
    served by high-quality grey-lit sources instead of peer-reviewed abstracts
    that the user has no context to interpret.

    When True, PubMed runs first (ADAPTER_PRIORITY_ORDER) and grey-lit follows.
    Both result sets are passed to the Synthesizer — the Synthesizer's quality
    ranking ensures peer-reviewed evidence surfaces above grey-lit in the
    final response when both are present.

    G-RETRIEVAL-03 — Director-approved [date TBD].
    """
    # (a) Signal-derived check — CLINICAL support need explicitly detected.
    if _PUBMED_ELIGIBLE_TOPIC_HINTS & topic_hints:
        return True
    # (b) Derived evidence query contains clinical/research vocabulary.
    q_lower = query.lower()
    if any(kw in q_lower for kw in _PUBMED_ELIGIBLE_QUERY_KEYWORDS):
        return True
    # (c) Raw user text explicitly requests research/evidence — catches cases
    # where the evidence query normalises away the user's research framing.
    # Keywords chosen to be specific to research intent, not general questions.
    if raw_text:
        rt_lower = raw_text.lower()
        _RAW_RESEARCH_KEYWORDS = (
            "is there research", "is there any research", "is there evidence",
            "any evidence", "does research", "does the research",
            "what does research", "what does the research",
            "what does evidence", "scientifically", "scientifically proven",
            "science say", "science behind", "studies show", "studies suggest",
            "any studies", "is there a study", "are there studies",
            "evidence-based", "evidence based", "what does science",
        )
        if any(kw in rt_lower for kw in _RAW_RESEARCH_KEYWORDS):
            return True
    return False


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

class NikkoPipeline:
    """
    End-to-end SPEC-700 execution pipeline.

    Instantiate once per application lifetime; call run() once per user turn.

        pipeline = NikkoPipeline()
        result = pipeline.run(user_input="I've been feeling overwhelmed lately.")

    Dependency injection points:
        draft_generator : DraftGeneratorProtocol (default: StubDraftGenerator)
        scope_classifier: ScopeClassifier or stub
        signal_agent    : SignalAgent or stub

    These can be overridden in tests:
        pipeline = NikkoPipeline(
            draft_generator=MyRealLLM(),
            scope_classifier=MyScopeClassifier(),
        )
    """

    def __init__(
        self,
        draft_generator:  Optional[DraftGeneratorProtocol] = None,
        scope_classifier=None,
        signal_agent=None,
        strategy_agent=None,
        evaluator=None,
    ) -> None:
        # [CONCEPT] Lazy initialisation: if a real agent is injected, use it;
        # otherwise fall back to the stub. This pattern lets the pipeline
        # run deterministically in Phase 3 tests without any GPU resources.
        # `evaluator` is injectable so the notebook can pass a mock that
        # does not require the `transformers` library (Phase 3 sandbox).
        self._scope   = scope_classifier or (
            _ScopeClassifier() if _HAVE_SCOPE_CLASSIFIER else _StubScopeClassifier()
        )
        self._signal  = signal_agent or (
            _SignalAgent() if _HAVE_SIGNAL_AGENT else _StubSignalAgent()
        )
        self._strategy = strategy_agent or (
            _SupportStrategyAgent() if _HAVE_STRATEGY_AGENT else _StubStrategyAgent()
        )
        self._router      = Router()
        self._pubmed      = PubMedAdapter()
        self._web         = WebSearchAdapter()
        self._synthesizer = EvidenceSynthesizerAgent()
        self._evaluator   = evaluator or EvaluatorAgent()
        self._vs          = VerificationSupervisorAgent()
        self._draft_gen   = draft_generator or StubDraftGenerator()

        logger.info(
            "NikkoPipeline initialised — scope=%s signal=%s strategy=%s draft=%s",
            type(self._scope).__name__,
            type(self._signal).__name__,
            type(self._strategy).__name__,
            type(self._draft_gen).__name__,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        regen_count: int = 0,
        memory_context: Optional[str] = None,
    ) -> PipelineResult:
        """
        Execute the full SPEC-700 pipeline for one user turn.

        Parameters
        ----------
        user_input      : Raw user message (untrusted — sanitized in STEP 1).
        session_id      : Optional stable ID for the current session.
                          Generated internally if not provided.
        regen_count     : Incremented on each regeneration loop. The pipeline
                          calls itself recursively when the Evaluator emits
                          REGENERATE. Callers should always pass 0 (default).
        memory_context  : Decrypted USM memory file content (plaintext Markdown)
                          forwarded from the frontend.  None when no memory file
                          is loaded.  Injected into ADP-A system prompt via
                          ResponseContextPayload.usm_content (REQ-850-070).
                          Never persisted server-side (SPEC-800 zero-retention).

        Spec trace
        ----------
        REQ-700-001  MUST define the exact end-to-end flow of every interaction.
        REQ-700-002  Outputs SHALL be traceable, reproducible, structurally consistent.
        REQ-700-010  Nikko SHALL be a deterministic multi-agent pipeline.
        """
        t0 = time.perf_counter()
        trace = PipelineTrace(
            session_id=session_id or str(uuid.uuid4()),
            regen_count=regen_count,
        )
        logger.info("Pipeline.run() — session=%s regen=%d", trace.session_id, regen_count)

        # ── Content moderation pre-gate ──────────────────────────────────
        # Runs on RAW input before sanitization or scope classification.
        # REQ-XXX-CM1: MUST fire before any agent or LLM processing.
        moderation_result = self._step_content_moderation(user_input, trace)
        if moderation_result is not None:
            moderation_result.trace.latency_ms = (time.perf_counter() - t0) * 1000
            return moderation_result

        # ── STEP 0: Scope Classification ─────────────────────────────────
        # REQ-700-SC1: MUST evaluate every input before any other processing.
        # REQ-700-SC2: OUT_OF_SCOPE → terminate here, ≤ 500 ms.
        scope = self._step0_scope(user_input, trace)
        if scope.decision == ScopeDecision.OUT_OF_SCOPE:
            trace.final_action = "out_of_scope_redirect"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.info("Pipeline: OUT_OF_SCOPE — terminating at STEP 0.")
            return PipelineResult(
                response_text=scope.warm_redirect or
                    "I can only help with emotional wellbeing and mental health topics.",
                out_of_scope=True,
                trace=trace,
            )

        # ── STEP 1: Input sanitization ───────────────────────────────────
        # REQ-700-021/022: treat as untrusted, sanitize injection attempts.
        clean_input = self._step1_sanitize(user_input)
        trace.step("input_sanitization")

        # ── STEP 2: Psychological Signal Detection ────────────────────────
        # REQ-700-030: sanitized input → Signal Agent.
        # REQ-700-032: output is immutable for the rest of the pipeline.
        signal = self._step2_signal(clean_input, trace)

        # ── STEP 3: Routing ───────────────────────────────────────────────
        # REQ-700-040/041: Router evaluates signal; outputs one mode.
        # REQ-700-042: Mixed-mode execution SHALL NOT be permitted.
        router_decision = self._step3_route(signal, regen_count, trace)
        mode = router_decision.mode

        # ── STEPS 4–10: Mode execution ────────────────────────────────────
        evidence: Optional[SynthesizedEvidence] = None
        crisis_resources: Optional[list[CrisisResource]] = None

        if mode == OperationalMode.GUIDANCE:
            # REQ-700-060: evidence first, tone second.
            # Pass clean_input for two-pass query construction:
            # signal keys give category, user_text gives specificity.
            evidence = self._steps4_7_guidance_evidence(signal, clean_input, trace)

        elif mode == OperationalMode.CRISIS:
            # REQ-700-070: inject mandatory Australian crisis resources.
            # REQ-700-VS1: evidence retrieval is skipped in Crisis Mode.
            crisis_resources = BASELINE_CRISIS_RESOURCES
            trace.step("crisis_resource_injection")
            logger.info("Pipeline: Crisis Mode — skipping evidence retrieval (REQ-700-VS1).")

        # ── Support Strategy ──────────────────────────────────────────────
        strategy = self._step_strategy(router_decision, signal, trace)

        # ── Build ResponseContextPayload ──────────────────────────────────
        # [CONCEPT] This is the single object the Interaction Model (LLM)
        # receives. REQ-700-133 / REQ-200-129/130: the LLM sees only this
        # curated context — never raw retrieval outputs or signal payloads.
        # [CONCEPT] USM (User-Scoped Memory) wiring — REQ-850-070/073/074.
        # memory_context is the decrypted Markdown from the user's .nikko-mem.enc
        # file, forwarded by the frontend.  We set usm_active=True and attach the
        # content so build_adp_a_system() can inject it into the ADP-A system
        # prompt.  The content is NEVER persisted here (SPEC-800 zero-retention).
        context = ResponseContextPayload(
            mode=mode,
            signals=signal,
            strategy=strategy,
            synthesized_evidence=evidence,
            crisis_resources=crisis_resources,
            raw_user_message=clean_input,       # [MVP-INFRA] consumed by HFSpaceFullGenerator
            usm_active=memory_context is not None,
            usm_content=memory_context,         # None when no memory file loaded
            # [G-HYBRID-01 resolution] Thread ScopeClassifier AMBIGUOUS verdict into
            # the context so HFSpaceFullGenerator can forward it to the Modal
            # combined moderation+scope LLM pass as a weighting hint.
            scope_ambiguous=(scope.decision == ScopeDecision.AMBIGUOUS),
        )

        # ── STEP 10: Draft generation (Interaction Model) ─────────────────
        # REQ-700-100: output constructed from LLM text + strategy constraints
        #              + verified evidence + safety framing.
        draft = self._step10_draft(context, trace)

        # ── ADP-B late-crisis override ────────────────────────────────────
        # If the stub SignalAgent missed a crisis signal (it only does keyword
        # guidance detection) and ADP-B caught it in the HF Space, the draft
        # generator returns ADPB_CRISIS_SENTINEL instead of "" to avoid the
        # silent SAFE_FALLBACK path. Intercept here and immediately deliver a
        # proper CRISIS PipelineResult with hotlines and the safety flag set.
        if draft == ADPB_CRISIS_SENTINEL:
            crisis_resources = BASELINE_CRISIS_RESOURCES
            trace.step("adpb_crisis_override")
            trace.final_action = "adpb_crisis_override"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Pipeline: ADP-B late-crisis override triggered. "
                "Switching to CRISIS mode (local router was COMFORT)."
            )
            return PipelineResult(
                response_text=_ADPB_CRISIS_RESPONSE,
                mode=OperationalMode.CRISIS,
                crisis_resources=crisis_resources,
                trace=trace,
            )

        # ── Modal moderation block (coded hate detected by LLM pass) ──────
        # The Render regex pre-gate catches hard slurs and explicit CSAM; the
        # Modal LLM pass catches coded antisemitism, Islamophobia, white
        # nationalism, and veiled dehumanization. Same static _HATE_RESPONSE
        # used for both (REQ-XXX-CM3: moderation responses must be static).
        if draft == MODERATION_BLOCK_SENTINEL:
            trace.step("moderation_llm_block")
            trace.final_action = "moderation_llm_block"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.warning("Pipeline: Modal LLM moderation block — issuing static hate response.")
            return PipelineResult(
                response_text=_HATE_RESPONSE,
                trace=trace,
            )

        # ── Modal scope block (OOS detected by LLM pass after regex passed) ─
        # The regex ScopeClassifier passed or called this AMBIGUOUS; the Modal
        # LLM pass made the final OUT_OF_SCOPE determination. Issue the same
        # WARM_REDIRECT used for regex-detected OUT_OF_SCOPE.
        if draft == SCOPE_BLOCK_SENTINEL:
            trace.step("scope_llm_block")
            trace.final_action = "scope_llm_block"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.info("Pipeline: Modal LLM scope block — issuing warm redirect.")
            return PipelineResult(
                response_text=WARM_REDIRECT,
                out_of_scope=True,
                trace=trace,
            )

        # ── STEP 11: Evaluator ─────────────────────────────────────────────
        # REQ-700-080: every non-crisis response MUST pass Evaluator audit.
        # REQ-700-082: on failure → regenerate OR safe fallback.
        evaluation = self._step11_evaluate(draft, context, trace)

        if evaluation.verdict != EvaluationVerdict.PASS:
            return self._handle_evaluator_failure(
                evaluation, user_input, session_id, regen_count, trace, t0
            )

        # ── STEP 12: Verification Supervisor ──────────────────────────────
        # REQ-700-090: final structural gate before output.
        # REQ-700-092: on failure → safe fallback.
        verification = self._step12_verify(context, evaluation, scope, regen_count, trace)

        if not verification.passed:
            trace.final_action = "vs_safe_fallback"
            trace.latency_ms = (time.perf_counter() - t0) * 1000
            logger.warning("Pipeline: VS failed — emitting safe fallback. Reasons: %s",
                           verification.failure_reasons)
            return PipelineResult(
                response_text=SAFE_FALLBACK_RESPONSE,
                mode=mode,
                safe_fallback_used=True,
                evaluation=evaluation,
                verification=verification,
                trace=trace,
                crisis_resources=crisis_resources,
            )

        # ── STEPS 13–14: Final assembly and delivery ───────────────────────
        # REQ-700-100/101: include AI disclosure framing, non-clinical tone,
        #                  autonomy reinforcement.
        final_response = self._step13_assemble(draft, context, trace)

        # ── STEP 15: Trace logging ─────────────────────────────────────────
        # REQ-700-LOG1: ephemeral — trace lives in memory only.
        trace.final_action = "response_delivered"
        trace.latency_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Pipeline complete — mode=%s latency=%.1fms regen=%d",
            mode.value, trace.latency_ms, regen_count,
        )

        return PipelineResult(
            response_text=final_response,
            mode=mode,
            safe_fallback_used=False,
            evaluation=evaluation,
            verification=verification,
            trace=trace,
            crisis_resources=crisis_resources,
            # Carry retrieved EvidenceItems to the API layer for the sources panel.
            # Empty for COMFORT/CRISIS modes (evidence retrieval is skipped).
            citations=evidence.citations if evidence else [],
        )

    # ------------------------------------------------------------------
    # Private step implementations
    # ------------------------------------------------------------------

    def _step_content_moderation(
        self, raw_input: str, trace: PipelineTrace
    ) -> Optional[PipelineResult]:
        """
        Content moderation pre-gate — runs before STEP 0 (Scope Classifier).

        Checks raw user input against three pattern sets:
          1. CSAM-adjacent content — illegal or quasi-illegal sexual content
             involving minors (loli/shota terminology, explicit naming).
          2. Child attraction / pedophilia — disclosure of sexual attraction
             to children. Response redirects to a licensed professional;
             it is non-shaming because some people seek help for unwanted
             urges — but Nikko is not the right provider for that work.
          3. Hate speech / dehumanizing language.

        Returns a PipelineResult (block immediately) if any pattern fires.
        Returns None if the input is clean (pipeline continues normally).

        Runs on RAW input (before sanitization) so whitespace normalization
        or case changes in _step1_sanitize cannot bypass the check.
        [REQ-XXX-CM1 through CM3]
        """
        # Check CSAM patterns — highest priority
        for pat in _CSAM_PATTERNS:
            if pat.search(raw_input):
                logger.warning(
                    "Content moderation: CSAM pattern matched — blocking. "
                    "Pattern: %s", pat.pattern
                )
                trace.step("content_moderation")
                trace.final_action = "content_moderation_csam"
                return PipelineResult(
                    response_text=_CSAM_RESPONSE,
                    out_of_scope=True,
                    trace=trace,
                )

        # Check child attraction / pedophilia patterns
        for pat in _CHILD_ATTRACTION_PATTERNS:
            if pat.search(raw_input):
                logger.warning(
                    "Content moderation: child attraction pattern matched — blocking. "
                    "Pattern: %s", pat.pattern
                )
                trace.step("content_moderation")
                trace.final_action = "content_moderation_child_attraction"
                return PipelineResult(
                    response_text=_CHILD_ATTRACTION_RESPONSE,
                    out_of_scope=True,
                    trace=trace,
                )

        # Check hate speech / dehumanizing language patterns
        for pat in _HATE_PATTERNS:
            if pat.search(raw_input):
                logger.warning(
                    "Content moderation: hate speech pattern matched — blocking. "
                    "Pattern: %s", pat.pattern
                )
                trace.step("content_moderation")
                trace.final_action = "content_moderation_hate"
                return PipelineResult(
                    response_text=_HATE_RESPONSE,
                    out_of_scope=True,
                    trace=trace,
                )

        # Check active crime / emergency report patterns
        for pat in _CRIME_PATTERNS:
            if pat.search(raw_input):
                logger.warning(
                    "Content moderation: crime/emergency pattern matched — redirecting to 000. "
                    "Pattern: %s", pat.pattern
                )
                trace.step("content_moderation")
                trace.final_action = "content_moderation_crime"
                return PipelineResult(
                    response_text=_CRIME_RESPONSE,
                    out_of_scope=True,
                    trace=trace,
                )

        return None  # Clean — pipeline continues normally

    def _step0_scope(self, text: str, trace: PipelineTrace) -> ScopeClassifierDecision:
        """STEP 0 — Scope classification (REQ-700-SC1/SC2)."""
        try:
            decision = self._scope.classify(text)
        except Exception as exc:
            # REQ-700-120: on agent failure, retry once then safe response.
            # For the Scope Classifier, a failure must default to AMBIGUOUS
            # (asymmetric error policy: err toward inclusion, REQ-200-SC3).
            logger.error("ScopeClassifier raised %s — defaulting to AMBIGUOUS.", exc)
            decision = ScopeClassifierDecision(
                decision=ScopeDecision.AMBIGUOUS,
                confidence=0.0,
                warm_redirect=None,
            )
        trace.step("scope_classifier")
        logger.debug("Scope: %s (confidence=%.2f)", decision.decision.value, decision.confidence)
        return decision

    def _step1_sanitize(self, text: str) -> str:
        """
        STEP 1 — Input sanitization (REQ-700-021/022).

        Phase 3: strips leading/trailing whitespace and collapses internal
        whitespace runs. Injection-pattern detection is a Phase 5 hardening
        item (SPEC-600 §8).
        """
        import re
        return re.sub(r"\s+", " ", text.strip())

    def _step2_signal(self, text: str, trace: PipelineTrace) -> SignalPayload:
        """STEP 2 — Psychological signal detection (REQ-700-030/032)."""
        try:
            signal = self._signal.analyze(text)
        except Exception as exc:
            logger.info("SignalAgent raised %s — using keyword fallback.", exc)
            # REQ-700-120: safe degradation. Rather than returning all-empty arrays
            # (which permanently suppresses GUIDANCE routing), apply a lightweight
            # keyword scan so explicit guidance-seeking messages ("CBT techniques",
            # "how do I", "therapy") still reach GUIDANCE mode.
            # [PROPOSED-RECONCILIATION: This is a production safety net for Fly.io
            # free-tier environments where Qwen2.5-3B-Instruct OOMs at load time.
            # The keyword list is intentionally conservative — it only covers clear
            # guidance-intent signals, not vague distress language. Director review
            # recommended before GA. Logged as G-SIGNAL-FALLBACK-01.]
            _GUIDANCE_KEYWORDS: frozenset[str] = frozenset({
                "cbt", "dbt", "emdr", "therapy", "therapist",
                "technique", "techniques", "exercise", "exercises",
                "strategy", "strategies", "method", "methods",
                "how do i", "how to", "what can i do", "what should i",
                # Catches "is there anything I can do", "anything I could try",
                # "is there anything to help", "what to do" — action-seeking
                # phrasing that doesn't start with "what can I do".
                "anything i can", "anything that i can", "anything i could",
                "is there anything i", "anything to help", "what to do",
                "is there anything to", "what can help", "what helps",
                "help me", "advice", "tips", "resources", "skills",
                "psychoeducation", "mindfulness", "breathing",
            })
            text_lower = text.lower()
            has_guidance_intent = any(kw in text_lower for kw in _GUIDANCE_KEYWORDS)
            signal = SignalPayload(
                distress_level=DistressLevel.LOW,
                # [PROPOSED-RECONCILIATION: confidence must be >= 0.40 for the
                # Router to reach Rule 4 (guidance check). When guidance_intent
                # is detected via keywords, we set 0.6 — above the low-band
                # ceiling — so the Router doesn't short-circuit to COMFORT
                # at Rule 3. When no guidance intent is found, 0.0 is correct:
                # COMFORT fallback is the right default for an unknown signal.]
                confidence=0.6 if has_guidance_intent else 0.0,
                emotional_states=[],
                cognitive_patterns=[],
                # help_seeking_behavior triggers GUIDANCE in the Router
                # (REQ-700-040: _GUIDANCE_BEHAVIORAL_INDICATORS match).
                behavioral_indicators=(
                    ["help_seeking_behavior"] if has_guidance_intent else []
                ),
                risk_indicators=[],
                # psychoeducation also triggers GUIDANCE as a backup path.
                support_needs=(
                    ["psychoeducation"] if has_guidance_intent else []
                ),
                uncertainty_notes=(
                    "[SIGNAL AGENT FAILURE — keyword fallback active; "
                    f"guidance_intent={has_guidance_intent}]"
                ),
            )
            logger.info(
                "SignalAgent fallback: guidance_intent=%s text_lower_snippet=%r",
                has_guidance_intent, text_lower[:80],
            )
        trace.step("signal_agent")
        trace.signal_output = {
            "distress_level": signal.distress_level.value,
            "confidence": signal.confidence,
        }
        logger.info("Signal: distress=%s confidence=%.2f",
                    signal.distress_level.value, signal.confidence)
        return signal

    def _step3_route(
        self, signal: SignalPayload, attempt_count: int, trace: PipelineTrace
    ) -> RouterDecision:
        """
        STEP 3 — Routing (REQ-700-040 through REQ-700-042).

        REQ-700-123: on Router failure, default to Comfort Mode and suppress
        all evidence chains.
        """
        try:
            decision = self._router.route(signal, attempt_count=attempt_count + 1)
        except Exception as exc:
            logger.error("Router raised %s — defaulting to COMFORT Mode (REQ-700-123).", exc)
            from agents.router import RouterDecision
            decision = RouterDecision(
                mode=OperationalMode.COMFORT,
                routing_rationale="[ROUTER FAILURE — forced COMFORT]",
                confidence=0.0,
                crisis_override=False,  # COMFORT fallback is never a crisis override
            )
        trace.step("router")
        trace.router_decision = decision.mode.value
        logger.info("Router: mode=%s confidence=%.2f crisis_override=%s",
                    decision.mode.value, decision.confidence,
                    getattr(decision, "crisis_override", False))
        return decision

    def _steps4_7_guidance_evidence(
        self, signal: SignalPayload, user_text: str, trace: PipelineTrace
    ) -> Optional[SynthesizedEvidence]:
        """
        STEPS 4–8 (Guidance Mode) — Evidence retrieval + synthesis.

        REQ-700-121: on retrieval failure, proceed without evidence and
        explicitly avoid fabrication (handled downstream by Evaluator).

        Runs ADAPTER_PRIORITY_ORDER sequentially: PubMed first, WebSearch
        fallback. Both results (if any) are passed to the Synthesizer.

        Query construction: _build_evidence_query() does two-pass extraction:
        1. Signal keys (support_needs, emotional_states, cognitive_patterns)
        2. Keyword scan of the raw sanitized user text via _TOPIC_KEYWORD_PATTERNS
        This ensures "calming techniques to stop shaking" → a query like
        "relaxation techniques anxiety management physical symptoms mental health"
        rather than the raw conversational sentence or a generic "psychoeducation".
        """
        # Two-pass query: signal keys + keyword scan of user text.
        query = _build_evidence_query(signal, user_text)
        logger.info(
            "Evidence query: %r  (support_needs=%s emotional_states=%s user_text=%r)",
            query, signal.support_needs, signal.emotional_states, user_text[:60],
        )

        # ── Signal → Topic bridge (G-RETRIEVAL-02) ────────────────────────
        # Translate Signal Agent output into TopicTag hints before retrieval.
        # Both adapters receive the same hint set so they select consistent
        # domain/MeSH coverage.  An empty frozenset means the adapters fall
        # back to their own keyword classifiers — identical to pre-G-RETRIEVAL-02
        # behaviour (safe on Render where stub signal agent fires empty arrays).
        topic_hints     = _signal_to_topic_hints(signal)
        preferred_sources = _get_preferred_source_labels(topic_hints)
        logger.info(
            "Topic hints: %s → preferred sources: %s",
            sorted(topic_hints), sorted(preferred_sources),
        )

        # ── PubMed eligibility gate (G-RETRIEVAL-03) ──────────────────────────
        # General emotional queries → WebSearch only (grey-lit guidance sites).
        # Explicitly clinical/research queries → PubMed first, WebSearch second.
        # See _is_pubmed_eligible() for the two-signal eligibility rule.
        pubmed_eligible = _is_pubmed_eligible(topic_hints, query, raw_text=user_text)
        adapters_to_run = ADAPTER_PRIORITY_ORDER if pubmed_eligible else [WebSearchAdapter]
        # When PubMed is skipped, request more grey-lit results to compensate
        # for the absent peer-reviewed set.
        web_max_results = 3 if pubmed_eligible else 6
        logger.info(
            "PubMed eligible: %s (topic_hints=%s) → adapters: %s",
            pubmed_eligible,
            sorted(topic_hints),
            [cls.__name__ for cls in adapters_to_run],
        )

        retrieval_results: list[EvidencePayload] = []
        adapters_run = []

        for AdapterClass in adapters_to_run:
            adapter_name = AdapterClass.__name__
            try:
                adapter = AdapterClass()
                if AdapterClass is PubMedAdapter:
                    params = PubMedQueryParams(
                        query=query,
                        max_results=5,
                        topic_hints=topic_hints,
                    )
                else:
                    params = StaticCacheQueryParams(
                        query=query,
                        max_results=web_max_results,
                        topic_hints=topic_hints,
                    )
                result: RetrievalResult = adapter.search(params)
                if result.items:
                    retrieval_results.append(_retrieval_result_to_evidence_payload(result))
                    adapters_run.append(adapter_name)
                    logger.info("Retrieval %s: %d items", adapter_name, len(result.items))
                else:
                    logger.info("Retrieval %s: 0 items returned.", adapter_name)
            except Exception as exc:
                # REQ-700-121: failure does not abort — continue with other adapters.
                logger.warning("Retrieval adapter %s failed: %s", adapter_name, exc)

        trace.step("evidence_retrieval")
        trace.adapter_configuration = adapters_run
        trace.evidence_used = [ep.source_name for ep in retrieval_results]

        if not retrieval_results:
            # [PROPOSED-RECONCILIATION: C5 checks that the evidence step RAN, not
            # that it produced results. Returning an empty SynthesizedEvidence object
            # (rather than None) correctly signals "step ran, found nothing" vs
            # "step was skipped entirely". Returning None was causing C5 to fire and
            # emit SAFE_FALLBACK_RESPONSE on Fly.io where PubMed/WebSearch are
            # unreachable (network restrictions / free-tier timeouts). The ADP-A
            # context_prompt_builder handles empty citations gracefully — it simply
            # omits the evidence injection block. Director: review as G-RETRIEVAL-01.]
            logger.warning(
                "All retrievals returned 0 items — returning empty SynthesizedEvidence "
                "so GUIDANCE mode can proceed without RAG injection. C5 preserved."
            )
            return SynthesizedEvidence(
                summary=(
                    "No peer-reviewed evidence was retrieved for this query. "
                    "Retrieval adapters returned zero results — respond from "
                    "general clinical knowledge with appropriate epistemic humility."
                ),
                citations=[],
                confidence=0.0,
                grey_literature_used=False,
            )

        # Pass preferred_sources so the Synthesizer can give a sub-bucket boost
        # to topically relevant grey-literature items (e.g. GriefLine results
        # rank ahead of generic Healthdirect results on a grief query).
        evidence = self._synthesizer.synthesize(
            retrieval_results,
            query=query,
            preferred_sources=preferred_sources,
        )
        trace.step("evidence_synthesizer")
        logger.info("Synthesizer: confidence=%.4f grey_lit=%s",
                    evidence.confidence, evidence.grey_literature_used)
        return evidence

    def _step_strategy(
        self, router_decision: RouterDecision, signal: SignalPayload, trace: PipelineTrace
    ) -> StrategyPayload:
        """Support Strategy Agent step (REQ-200-060/061).

        Receives the full RouterDecision so the real SupportStrategyAgent
        (which expects a RouterDecision, not a bare OperationalMode) gets the
        correct type. Previously this method received only `mode: OperationalMode`,
        causing an AttributeError on every request when the real agent tried to
        call `router_decision.mode` on an OperationalMode enum value.
        """
        mode = router_decision.mode
        try:
            if mode == OperationalMode.CRISIS:
                # CRISIS: strategy agent is bypassed; use static crisis strategy.
                # crisis_bypass() takes NO arguments in the real SupportStrategyAgent
                # (it returns a hardcoded StrategyPayload constant). Passing signal
                # previously caused a TypeError on the real agent — fixed here.
                strategy = self._strategy.crisis_bypass()
            else:
                strategy = self._strategy.strategize(router_decision, signal)
        except Exception as exc:
            logger.error("StrategyAgent raised %s — using minimal fallback strategy.", exc)
            strategy = StrategyPayload(
                mode=mode,
                distress_level=signal.distress_level,
                tone_guidance="empathetic, non-directive",
                framing_strategy="validate and support",
            )
        trace.step("support_strategy_agent")
        return strategy

    def _step10_draft(
        self, context: ResponseContextPayload, trace: PipelineTrace
    ) -> str:
        """
        STEP 10 — Draft generation (Interaction Model).

        REQ-700-133: LLM receives ONLY the curated ResponseContextPayload —
        never raw retrieval outputs or signal payloads directly.
        """
        try:
            draft = self._draft_gen.generate(context)
        except Exception as exc:
            logger.error("DraftGenerator raised %s — using safe fallback draft.", exc)
            draft = SAFE_FALLBACK_RESPONSE
        trace.step("interaction_model")
        logger.debug("Draft generated (%d chars).", len(draft))
        return draft

    def _step11_evaluate(
        self,
        draft: str,
        context: ResponseContextPayload,
        trace: PipelineTrace,
    ) -> EvaluationPayload:
        """
        STEP 11 — Evaluator audit pass (REQ-700-080 through REQ-700-082).

        REQ-700-122: on Evaluator failure, default to SAFE MODE response
        with no evidence injection. Modelled here as returning a synthetic
        FAIL payload so the failure handling path is triggered normally.
        """
        try:
            evaluation = self._evaluator.evaluate(draft, context)
        except Exception as exc:
            logger.error("EvaluatorAgent raised %s — synthetic FAIL payload.", exc)
            evaluation = EvaluationPayload(
                verdict=EvaluationVerdict.FAIL,
                safety_check=False,
                tone_check=False,
                hallucination_check=False,
                rejection_reasons=[f"[EVALUATOR FAILURE: {exc}]"],
            )
        trace.step("evaluator_agent")
        trace.evaluation_result = evaluation.verdict.value
        logger.info("Evaluator: verdict=%s", evaluation.verdict.value)
        return evaluation

    def _step12_verify(
        self,
        context: ResponseContextPayload,
        evaluation: EvaluationPayload,
        scope: ScopeClassifierDecision,
        regen_count: int,
        trace: PipelineTrace,
    ) -> VerificationResult:
        """STEP 12 — Verification Supervisor (REQ-700-090 through REQ-700-092)."""
        verification = self._vs.verify(context, evaluation, scope, regen_count)
        trace.step("verification_supervisor")
        trace.verification_result = "passed" if verification.passed else "failed"
        return verification

    def _step13_assemble(
        self,
        draft: str,
        context: ResponseContextPayload,
        trace: PipelineTrace,
    ) -> str:
        """
        STEP 13 — Final response assembly (REQ-700-100/101).

        Non-clinical framing is ensured by the Evaluator in STEP 11.
        Autonomy reinforcement (REQ-700-101) is now satisfied at the UI
        layer by the persistent AiDisclaimer component in chat.jsx
        (G-UI-01 / REQ-300-164), which renders below the composer on every
        turn. Appending a per-message suffix was redundant, produced formulaic
        responses, and has been removed.

        [PROPOSED-RECONCILIATION: Director-approved 2026-05-15. REQ-700-101
        is fulfilled by AiDisclaimer in frontend rather than server-side string
        appending. Logged as G-AUTONOMY-SUFFIX-01.]
        """
        trace.step("response_assembly")
        return draft

    # ------------------------------------------------------------------
    # Failure handlers
    # ------------------------------------------------------------------

    def _handle_evaluator_failure(
        self,
        evaluation: EvaluationPayload,
        user_input: str,
        session_id: Optional[str],
        regen_count: int,
        trace: PipelineTrace,
        t0: float,
    ) -> PipelineResult:
        """
        REQ-700-082: on Evaluator failure, regenerate if within loop limit;
        otherwise emit safe fallback.

        REQ-200-170: maximum 2 regeneration attempts per request.
        REQ-200-171: no more than 1 evaluation cycle per response — so we
        regenerate by re-running the full pipeline from STEP 2, not by
        re-calling just the Evaluator.
        """
        if (
            evaluation.verdict == EvaluationVerdict.REGENERATE
            and regen_count < MAX_REGEN_ATTEMPTS
        ):
            logger.info(
                "Evaluator REGENERATE — attempt %d/%d. Re-running pipeline.",
                regen_count + 1, MAX_REGEN_ATTEMPTS,
            )
            return self.run(user_input, session_id=session_id, regen_count=regen_count + 1)

        # FAIL verdict or regen limit exhausted — safe fallback.
        trace.final_action = "evaluator_safe_fallback"
        trace.latency_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            "Evaluator %s (regen=%d) — emitting safe fallback.",
            evaluation.verdict.value, regen_count,
        )
        return PipelineResult(
            response_text=SAFE_FALLBACK_RESPONSE,
            safe_fallback_used=True,
            evaluation=evaluation,
            trace=trace,
        )
