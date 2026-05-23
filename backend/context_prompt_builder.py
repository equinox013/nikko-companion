"""
backend/context_prompt_builder.py
===================================
Converts a ResponseContextPayload into enriched system prompts for HF Space calls.

This module is the **RAG injection point** — synthesized evidence retrieved by
PubMedAdapter and WebSearchAdapter is formatted here and written into Qwen3-4B's
(ADP-A) context window so the model generates evidence-grounded responses.

Three prompt builders are exported:
  build_adp_a_system(context)  → enriched ADP-A generation prompt (RAG here)
  build_adp_b_system()         → static ADP-B safety classifier prompt
  build_adp_c_system(context)  → ADP-C evaluator prompt with mode awareness

Design notes
------------
- Evidence is capped at 5 citations to stay within the 2048-token context window.
- Abstract truncation at 300 chars prevents single evidence items from dominating
  the context budget. Full abstracts are available in the retrieval cache if needed.
- Prompts use plain language, not markdown headers — Qwen3-4B responds better to
  conversational instruction framing than structured markup.
- `build_adp_b_system()` is stateless (returns constant string) because ADP-B
  must be a deterministic binary classifier — context enrichment would risk
  nudging the safety verdict.
"""

import re

from docs.schemas.acp_schemas import DistressLevel, OperationalMode, ResponseContextPayload


# ── USM smart truncation ──────────────────────────────────────────────────────

def _smart_truncate_usm(content: str, max_chars: int = 1200) -> str:
    """
    Intelligently reduce a USM memory file to `max_chars` for injection into
    the ADP-A system prompt.

    Strategy (priority order — highest value context first):
      1. Name        — always included first; personalises every response.
      2. Mood Diary  — date-indexed entries sorted newest-first so the most
                       recent mood data fills the budget before older entries
                       are considered.  This is the highest-signal section for
                       live session context.
      3. User Preferences, Helpful Interventions, Support Notes, Emotional
                       Patterns — included in that order until the budget runs
                       out; comment-only sections are skipped silently.

    Comment lines (<!-- ... -->) are stripped from all sections before counting
    chars — they add no signal for the LLM.

    [CONCEPT] The 1200-char / ~300-token budget is intentionally tight: it
    leaves headroom in Qwen3-4B's context window for retrieved evidence
    (Guidance Mode), the strategy block, and the live conversation history.
    Exceeding it risks crowding out real-time signal with stale diary entries.
    """
    # ── Parse the file into sections (keyed by ## heading) ───────────────
    sections: dict[str, str] = {}
    current_key: str | None  = None
    current_lines: list[str] = []

    for line in content.split("\n"):
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key  = line[3:].strip()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()

    def _strip_comments(text: str) -> str:
        """Remove HTML-comment lines (<!-- ... -->) — no signal for the LLM."""
        return "\n".join(
            l for l in text.split("\n")
            if not l.strip().startswith("<!--")
        ).strip()

    budget  = max_chars
    parts: list[str] = []

    def _try_add(section_heading: str, body: str) -> bool:
        """
        Append '## {heading}\n{body}' to parts if it fits in the remaining
        budget.  Returns True if added (even partially on last call).
        """
        nonlocal budget
        block = f"## {section_heading}\n{body}"
        if len(block) <= budget:
            parts.append(block)
            budget -= len(block) + 1   # +1 for the separating newline
            return True
        elif budget > 60:
            # Partial include: truncate to budget and mark it.
            truncated = block[: budget - 15] + "\n[…truncated]"
            parts.append(truncated)
            budget = 0
        return False

    # ── 1. Name ──────────────────────────────────────────────────────────
    name_raw = _strip_comments(sections.get("Name", ""))
    if name_raw:
        _try_add("Name", name_raw)

    if budget <= 0:
        return "\n\n".join(parts)

    # ── 2. Mood Diary — newest entries first ─────────────────────────────
    diary_raw = sections.get("Mood Diary", "")
    if diary_raw:
        diary_lines = diary_raw.split("\n")
        # An entry line starts with an ISO date (YYYY-MM-DD).
        entry_lines = [
            l for l in diary_lines
            if re.match(r"\s*\d{4}-\d{2}-\d{2}", l) and l.strip()
        ]
        # Sort newest-first by the date prefix.
        entry_lines.sort(
            key=lambda l: re.match(r"\s*(\d{4}-\d{2}-\d{2})", l).group(1),
            reverse=True,
        )

        # Take as many entries as fit.
        taken: list[str] = []
        diary_budget = budget - len("## Mood Diary\n") - 1
        for entry in entry_lines:
            cost = len(entry) + 1   # +1 for newline
            if cost <= diary_budget:
                taken.append(entry)
                diary_budget -= cost
            else:
                break   # stop — remaining entries are older and won't fit

        if taken:
            _try_add("Mood Diary", "\n".join(taken))

    if budget <= 0:
        return "\n\n".join(parts)

    # ── 3. Remaining sections — fixed priority ────────────────────────────
    for section_name in (
        "User Preferences",
        "Helpful Interventions",
        "Support Notes",
        "Emotional Patterns",
    ):
        if budget <= 0:
            break
        raw = _strip_comments(sections.get(section_name, ""))
        if raw:
            _try_add(section_name, raw)

    return "\n\n".join(parts)

# ── Shared persona string ─────────────────────────────────────────────────────
# This is the base Nikko persona — replicated from backend/main.py NIKKO_SYSTEM
# but extended here with context-specific framing. Keep both in sync if edited.
_NIKKO_PERSONA = (
    "You are Nikko, a safety-aligned wellbeing companion. "
    "You are warm, empathetic, and non-diagnostic. "
    "You support users with evidence-based wellbeing strategies. "
    "You are not a therapist or medical professional. "
    "If a user is in crisis, always direct them to real human support immediately. "
    "Respond in plain, clear English. Be concise and focused on the user's needs. "
    "IMPORTANT: Never open your response with stock empathy phrases such as "
    "'I'm sorry you're feeling this way', 'I'm sorry to hear that', "
    "'I can hear that you're going through a tough time', or any variant of these. "
    "Instead, begin by directly acknowledging the specific thing the user described. "
    # [REQ-000-040] Verbatim echo prohibition.
    # ADP-A was opening responses by repeating the user's own words back to them
    # almost verbatim (e.g. user says "i feel like absolute trash" → ADP-A opens
    # "i feel like absolute trash... that sounds really heavy"). This feels robotic,
    # not empathetic. The model must respond TO what the user said, not replay it.
    "NO ECHO RULE: NEVER begin your response by repeating or closely paraphrasing "
    "the user's own words back to them. Do not open with a near-literal restatement "
    "of what they just said. Instead, respond to the meaning and feeling behind "
    "their message in your own words. REQ-000-040. "
    # [REQ-000-041] Typography / capitalisation consistency.
    # The REGISTER RULE below instructs ADP-A to match the user's energy and tone,
    # but this was being over-applied: when the user typed in all-lowercase, ADP-A
    # mirrored their capitalisation (opening responses in lowercase), then switched
    # to standard English capitalisation on the next turn — jarring inconsistency.
    # Register matching governs warmth, pace, and formality — NOT typography.
    # ADP-A must always produce grammatically correct, consistently capitalised
    # English regardless of how the user types.
    "TYPOGRAPHY RULE: Always use standard English capitalisation — begin every "
    "sentence with a capital letter, capitalise proper nouns, etc. NEVER mirror "
    "the user's typing style (e.g. do NOT write in all-lowercase because the user "
    "did). Register-matching means matching their emotional tone and warmth level, "
    "not copying their formatting. REQ-000-041. "
    # [REQ-000-070 / RISK-02 / G-SAFETY-01] Companion-substitute prohibition.
    # ADP-A was generating parasocial attachment language on loneliness prompts
    # ("I'll try to be present", "I can't always be the one to fill the silence"),
    # which violates REQ-000-070 (must not encourage exclusive reliance on Nikko),
    # REQ-000-020 (must not replace human relationships), and RISK-02 (over-reliance
    # mitigation requires periodic external-relationship encouragement).
    # This injection is the immediate inference-time guard; root fix requires
    # adding contrastive training examples (see G-SAFETY-01 in docs/GAPS.md).
    # [REQ-000-042] Social context awareness caveat.
    # When the user has EXPLICITLY stated in this conversation that they do not
    # have family or friends available to them, the generic "reach out to friends
    # and family" encouragement is not only unhelpful — it directly contradicts
    # what the user just shared and erodes trust. Context from the live conversation
    # history MUST override the default relationship encouragement.
    "SAFETY RULE — RELATIONSHIP BOUNDARY: You MUST NOT imply that you can serve "
    "as a persistent companion, constant presence, or substitute for human "
    "relationships. When a user expresses loneliness or asks you to always be "
    "there for them, validate the feeling with warmth, then gently acknowledge "
    "your limits and encourage real-world connection (friends, community, or a "
    "professional). Never say 'I'll try to be present' or 'I'm here for you' in "
    "a way that implies ongoing companionship. REQ-000-070 is binding. "
    "CRITICAL EXCEPTION (REQ-000-042): If the user has explicitly stated in this "
    "conversation that they do not have family or close friends available to them, "
    "do NOT suggest 'reaching out to friends or family' — that directly contradicts "
    "what they shared and will feel dismissive. Instead, pivot to: professional "
    "support (a GP, counsellor, or helpline), community options (support groups, "
    "community centres), or if they have expressed a preference for self-directed "
    "strategies, honour that preference and help them with it. "
    # [REQ-000-232] Epistemic language calibration — prohibited constructions.
    # Two failure modes are equally prohibited:
    #
    # OVER-CLAIMING (prohibited): asserting certainty the system cannot have.
    # These phrases make Nikko sound authoritative about clinical matters it
    # cannot know, eroding the user's agency and Nikko's epistemic integrity.
    # Prohibited patterns: 'This will help you', 'You definitely feel', 'I know
    # that what you need is', 'This is definitely anxiety', 'You need to try',
    # 'The research proves', 'This technique will work for you', 'Certainly,',
    # 'Without a doubt,', 'You clearly', 'You obviously', 'This definitely'.
    #
    # OVER-HEDGING (prohibited): so many qualifiers that the response becomes
    # useless or implies Nikko doubts the user's own experience.
    # Prohibited patterns: 'I'm just an AI so I can't really know', opening
    # every sentence with 'perhaps' or 'maybe', 'I'm not sure if this applies',
    # 'I could be wrong but', appending a disclaimer to every single sentence,
    # treating every observation as equally uncertain regardless of evidence.
    #
    # USE INSTEAD: calibrated language that reflects real confidence.
    # Peer-reviewed evidence: 'research suggests', 'studies indicate', 'evidence
    # points to', 'clinical guidance recommends'.
    # Personal inference from what user shared: 'it sounds like', 'it seems',
    # 'from what you've shared', 'that sounds really difficult'.
    # Acknowledging limits when genuinely uncertain: a single, well-placed
    # 'I'm not certain, but' is honest and appropriate; repeating it five times
    # is not. Qualify once; then trust your reading of the situation.
    "EPISTEMIC LANGUAGE RULE: "
    "DO NOT over-claim certainty — avoid 'this will help', 'you definitely', "
    "'you clearly need', 'this is definitely', 'certainly,', 'without a doubt'. "
    "DO NOT over-hedge — avoid opening every sentence with 'perhaps' or 'maybe', "
    "or adding a disclaimer to every statement. "
    "USE calibrated language: 'research suggests', 'it sounds like', "
    "'from what you've shared', 'studies indicate'. "
    "One honest qualifier per response is appropriate; five is not. REQ-000-232."
)

# ── ADP-B system prompt (static — safety classifier must be deterministic) ────
# Tightened 2026-05-15: original prompt was too loose — expressions of loneliness,
# wishing for connection, or generalised sadness were triggering crisis=true with
# suicidal_ideation flags. The classifier must require explicit, unambiguous
# self-harm language before returning crisis=true. Vague distress or existential
# statements do NOT qualify unless combined with direct self-harm intent.
_ADP_B_SYSTEM = (
    "You are a safety classifier for a mental health support app. "
    "Analyse the user message and output a JSON object with two keys:\n"
    '"crisis": true ONLY if the message contains explicit, unambiguous self-harm '
    "intent — for example: a direct statement of intent to end their life, a "
    "specific plan for self-harm or suicide, or an explicit request for means. "
    "The following do NOT qualify as crisis on their own: expressions of loneliness, "
    "sadness, grief, hopelessness about life circumstances, wishing for connection, "
    "feeling like a burden, or frustration with life. Those are distress signals, "
    "not crisis signals.\n"
    '"flags": a list of triggered safety signals such as ["suicidal_ideation", '
    '"self_harm", "plan_disclosed"] if crisis=true, otherwise an empty list.\n'
    "Output ONLY the JSON object. No explanation, no additional text."
)


# ── Public builders ───────────────────────────────────────────────────────────

def _parse_memory_prefs(usm_content: str) -> dict[str, str]:
    """
    Extract key:value pairs from the ## User Preferences section of a USM file.

    Returns a dict such as:
      { "tone": "practical", "response_length": "brief", "input_length": "verbose" }

    Keys not present in the file are absent from the dict — callers should use
    .get() with a sensible default rather than assuming all keys are present.
    """
    import re as _re
    prefs: dict[str, str] = {}
    match = _re.search(
        r"^##\s*User Preferences\s*\n([\s\S]*?)(?=\n##|$)",
        usm_content,
        _re.MULTILINE,
    )
    if not match:
        return prefs
    for line in match.group(1).split("\n"):
        pair = _re.match(r"^([\w_]+):\s*(.+)$", line.strip())
        if pair:
            prefs[pair.group(1)] = pair.group(2).strip()
    return prefs


# ── Preference → prompt text mappings ────────────────────────────────────────
# These translate the structured key:value prefs from the memory file into
# concrete instructions ADP-A can follow.  Kept here (not in the memory file)
# so the Director can tune wording without touching user data.

_TONE_INSTRUCTIONS: dict[str, str] = {
    "understanding": (
        "Tone: UNDERSTANDING — prioritise making the user feel fully heard. "
        "Lead with validation and reflection. Offer perspective or information only "
        "if the user explicitly asks or the mode requires it."
    ),
    "balanced": (
        "Tone: BALANCED — acknowledge feelings genuinely, then gently offer "
        "perspective or information where it fits naturally. Neither pure validation "
        "nor pure advice."
    ),
    "practical": (
        "Tone: PRACTICAL — keep empathy brief and direct; move toward concrete "
        "framing or next-step thinking without lingering on feelings."
    ),
}

_LENGTH_INSTRUCTIONS: dict[str, str] = {
    "brief":    "Response length: BRIEF — 2–3 sentences maximum. Be concise.",
    "standard": "Response length: STANDARD — write as much as the moment calls for.",
    "detailed": "Response length: DETAILED — unpack fully; depth is welcome here.",
}

# Note: input_length is applied client-side (word-cap on the textarea) so it
# is not injected into the system prompt — no instruction needed here.


def build_adp_a_system(context: ResponseContextPayload) -> str:
    """
    Build the ADP-A (Qwen3-4B) system prompt from the full ResponseContextPayload.

    [CONCEPT] This is where RAG becomes useful. In Guidance Mode, the pipeline
    has already retrieved and synthesized PubMed / web evidence before this
    function is called. That evidence is injected here as numbered citations in
    the system prompt, so Qwen3-4B generates responses grounded in real sources
    rather than relying on parametric knowledge alone.

    In Comfort Mode, no evidence is present — the prompt focuses on emotional
    validation framing. In Crisis Mode, this function is not called (crisis
    responses are handled by the pipeline before reaching draft generation).
    """
    parts = [_NIKKO_PERSONA]

    # ── USM memory injection (REQ-850-070) ───────────────────────────────────
    # When the user has loaded a personal memory file (usm_active=True), its
    # decrypted Markdown content is injected here so Qwen3-4B can personalise
    # the response.  The content is supplied by the frontend (client-side
    # decrypt) and never stored server-side (SPEC-800 zero-retention).
    #
    # [CONCEPT] USM = User-Scoped Memory.  It's an encrypted .md file the user
    # carries between sessions — a private diary/context note they choose to
    # share for the duration of a session.  Injecting it into the ADP-A prompt
    # lets the model reference their history without the server ever storing it.
    #
    # Safety constraints (REQ-850-073/074):
    #   - Frame memory as background context, not as clinical history.
    #   - Do NOT use memory to infer current crisis state.
    #   - Do NOT position Nikko as a continuous care provider.
    if context.usm_active and context.usm_content:
        # Smart truncation: Name first, then newest Mood Diary entries, then
        # remaining sections in priority order — all within a 1200-char budget
        # (~300 tokens).  See _smart_truncate_usm() for full strategy.
        mem_snippet = _smart_truncate_usm(context.usm_content, max_chars=1200)
        parts.append(
            "\nPERSONAL CONTEXT (from user's memory file — treat as background, "
            "not diagnosis):\n"
            "---\n"
            f"{mem_snippet}\n"
            "---\n"
            "Use this context to personalise your response where it is relevant "
            "to what the user has actually said in this conversation. "
            "If the user's name is provided above, address them by it naturally "
            "when it fits — do not force it into every message. "
            "If the memory content is not relevant to the current topic, set it "
            "aside silently — do not reference or paraphrase it unprompted. "
            "Do NOT infer clinical diagnoses, crisis state, or ongoing care needs "
            "from memory content alone.  The live conversation is your primary signal."
        )

        # ── Personalisation preferences (from ## User Preferences section) ──
        # Parse structured key:value prefs and inject concrete instructions.
        # These override the generic framing from SupportStrategyAgent when
        # the user has explicitly declared a preference.
        #
        # Safety override: in high-distress Comfort Mode, the SupportStrategy
        # agent's empathy framing takes precedence — we inject prefs as a
        # secondary modifier, not a hard override, so the model can still lead
        # with emotional acknowledgement even if the user prefers "practical".
        prefs = _parse_memory_prefs(context.usm_content)

        pref_lines: list[str] = []

        tone_key = prefs.get("tone", "")
        if tone_key in _TONE_INSTRUCTIONS:
            pref_lines.append(_TONE_INSTRUCTIONS[tone_key])

        length_key = prefs.get("response_length", "")
        if length_key in _LENGTH_INSTRUCTIONS:
            pref_lines.append(_LENGTH_INSTRUCTIONS[length_key])

        if pref_lines:
            is_high_distress_comfort = (
                context.mode == OperationalMode.COMFORT
                and context.strategy
                and getattr(context.strategy, "distress_level", DistressLevel.LOW)
                    in (DistressLevel.HIGH, DistressLevel.CRISIS)
            )
            caveat = (
                " (note: high distress detected — lead with emotional acknowledgement "
                "before applying this preference)"
                if is_high_distress_comfort else ""
            )
            parts.append(
                "\nUSER PREFERENCES (honoured from memory file):\n"
                + "\n".join(pref_lines)
                + caveat
            )

    # ── Strategy guidance (tone + framing from SupportStrategyAgent) ─────────
    # The SupportStrategyAgent has already determined the optimal tone for this
    # user's distress level and mode. Inject it so ADP-A doesn't override it.
    if context.strategy:
        s = context.strategy
        parts.append(
            f"\nRESPONSE GUIDANCE:"
            f"\n  Tone:     {s.tone_guidance}"
            f"\n  Framing:  {s.framing_strategy}"
        )
        if s.response_constraints:
            cstr = "\n".join(f"  - {c}" for c in s.response_constraints)
            parts.append(f"  Constraints:\n{cstr}")

    # ── Evidence injection (Guidance Mode RAG) ────────────────────────────────
    # synthesized_evidence is None in Comfort/Crisis Mode — only present after
    # _steps4_7_guidance_evidence() has run (Guidance Mode only).
    if context.synthesized_evidence and context.synthesized_evidence.citations:
        ev = context.synthesized_evidence
        citation_count = min(len(ev.citations), 5)  # cap to protect context window

        parts.append(
            f"\nEVIDENCE BASE ({citation_count} source(s) retrieved):"
            f"\nSummary: {ev.summary}"
        )

        for i, item in enumerate(ev.citations[:5], 1):
            # Truncate long abstracts — full text is available in retrieval cache.
            abstract = item.abstract
            if len(abstract) > 300:
                abstract = abstract[:297] + "..."

            parts.append(
                f"\n[{i}] {item.title}"
                f"\n    Source: {item.source_name} | Evidence tier: {item.evidence_tier}"
                f"\n    {abstract}"
            )

        # Grounding instruction — mandatory citation + anti-fabrication.
        # Previous wording ("when your response draws on...") was optional framing;
        # Qwen3-4B treated it as a suggestion and ignored the evidence entirely.
        # "MUST" + explicit failure condition gives the model a clear directive.
        parts.append(
            "\nYou MUST ground your response in the evidence provided above. "
            "Reference at least one source naturally in your reply "
            "(e.g. 'research suggests...', 'according to Beyond Blue...', 'studies indicate...'). "
            "Do NOT cite sources not listed above. Do NOT fabricate journal names or statistics. "
            "A response that does not reference the evidence will be rejected by the evaluator."
        )

        if ev.grey_literature_used:
            parts.append(
                "Note: some sources above are grey literature (web). "
                "Frame those findings as 'some sources suggest' rather than 'research shows'."
            )

        if ev.source_disagreement:
            note = ev.disagreement_note or "sources show conflicting findings"
            parts.append(
                f"Important: {note}. "
                "Acknowledge the uncertainty in your response rather than presenting a single view."
            )

    # ── Mode-specific framing ─────────────────────────────────────────────────
    if context.mode == OperationalMode.GUIDANCE:
        parts.append(
            "\nMode: GUIDANCE. Lead with emotional acknowledgement, then offer evidence-based "
            "information as supplementary context. Frame all information as 'things to consider' "
            "— never as diagnosis, prescription, or directive. End by reinforcing the user's autonomy."
        )
    elif context.mode == OperationalMode.COMFORT:
        parts.append(
            "\nMode: COMFORT. Focus entirely on emotional validation and supportive presence. "
            "Do not introduce information, resources, or advice unless the user explicitly asks. "
            "Reflect the SPECIFIC details the user has shared — name the situation, the person, "
            "the feeling — rather than giving a generic empathetic response. "
            "If the user mentions a specific event or person (e.g. a call from their mum, "
            "losing a job, a difficult conversation), acknowledge that specific thing directly. "
            "Make them feel genuinely heard, not just reassured with a stock phrase. "
            "Do NOT open with 'I'm sorry you're feeling this way', 'I'm sorry to hear that', "
            "or any generic apology opener. Start with the specific situation."
        )

    # ── Register-matching instruction (all modes) ─────────────────────────────
    # [REQ-700-SA7] The upstream pipeline (Qwen3 pre-analysis, ADP-B safety pass)
    # may inject signals indicating elevated arousal or distress. This is correct
    # context, but it must NOT cause ADP-A to respond with clinical weight or
    # heightened concern when the user's live message register is light, casual,
    # tentative, or humorous.
    #
    # WHY THIS MATTERS: if the user opens with "*shakes* h-hi there" in a
    # deliberately tentative/shy register, a response that mirrors back heavy
    # clinical concern would feel jarring and isolating. The user presented
    # lightly — Nikko must match that presentation, trusting the live conversation
    # tone as the primary signal. Arousal markers from upstream set the internal
    # sensitivity level; they should not dictate the surface register of the reply.
    #
    # HOW TO APPLY: scan the user's current message for register cues — word
    # choice (casual vs formal), sentence length, hedging, emoji, humour — and
    # pitch the response at that register. If the words are warm but tentative,
    # respond warmly but gently, not with urgency. If the user is self-deprecating
    # or ironic, meet them there before going deeper. The rule: words > signals
    # when determining HOW to say it; signals inform HOW MUCH weight to apply.
    parts.append(
        "\nREGISTER RULE: Match the register and energy level of the user's actual "
        "message. If the user is light, casual, tentative, shy, or gently ironic, "
        "respond in that register — do not respond with clinical weight, urgency, or "
        "heightened concern unless the verbal content of the message clearly warrants it. "
        "The pipeline may have flagged elevated arousal signals upstream; use those to "
        "inform your sensitivity level internally, but let the user's live conversation "
        "tone determine how you pitch your response on the surface. "
        "Words in the message determine HOW MUCH weight to apply; the user's register "
        "determines HOW to say it."
    )

    return "\n".join(parts)


def build_adp_b_system() -> str:
    """
    Return the static ADP-B safety classifier system prompt.
    No context enrichment — safety classification must be deterministic.
    """
    return _ADP_B_SYSTEM


def build_adp_c_system(context: ResponseContextPayload) -> str:
    """
    Build the ADP-C evaluator system prompt.

    In Guidance Mode with evidence present, the check is two-part:
      1. Absence: response MUST reference at least one retrieved source.
         A response that ignores the evidence entirely must be REGENERATE.
      2. Fabrication: response must NOT invent citations beyond the provided base.

    Previously only fabrication was checked — absence was not caught, so ADP-C
    approved responses that silently ignored injected evidence. Fixed 2026-05-21.
    """
    # Base verdict instruction — shared across all modes.
    # [REQ-000-232] Epistemic language red-lines added to evaluator:
    # ADP-C now catches BOTH over-claiming AND over-hedging failures.
    # Over-claiming example: "This will definitely help you."
    # Over-hedging example: every sentence prefixed with "perhaps" or "maybe",
    # or repeated "I'm just an AI" disclaimers throughout the response.
    base = (
        "You are a response quality evaluator for a mental health support app. "
        "Given a user message and a proposed assistant response, output a JSON object: "
        "verdict: APPROVE if the response is empathetic, safe, appropriate, and "
        "uses calibrated epistemic language. "
        "verdict: REGENERATE if the response: "
        "(1) is harmful, dismissive, or clinically inappropriate; "
        "(2) is overly advice-heavy in Comfort Mode; "
        "(3) fails to ground its response in evidence in Guidance Mode; "
        "(4) OVER-CLAIMS certainty — uses phrases like 'this will definitely help', "
        "'you clearly need', 'this is definitely [diagnosis]', 'you definitely feel' "
        "— asserting clinical certainty the system cannot have; OR "
        "(5) OVER-HEDGES excessively — prefixes every sentence with 'perhaps' or "
        "'maybe', or repeats 'I'm just an AI' type disclaimers more than once, "
        "rendering the response unhelpfully vague. "
        "reason: one sentence explanation. "
        "Output ONLY the JSON object."
    )

    # Guidance Mode: check both evidence ABSENCE and FABRICATION.
    # Previous version only caught fabrication — a response citing nothing
    # passed through undetected. Now ADP-C explicitly requires at least one
    # source to be referenced and rejects if none are. (Fixed 2026-05-21)
    if (
        context.mode == OperationalMode.GUIDANCE
        and context.synthesized_evidence
        and context.synthesized_evidence.citations
    ):
        source_names = ", ".join(
            c.source_name for c in context.synthesized_evidence.citations[:5]
        )
        base += (
            " Additionally, evidence was retrieved from: " + source_names + ". "
            "Check TWO things: "
            "(1) Does the response reference at least one of these sources naturally? "
            "If the response makes NO reference to the retrieved evidence, "
            "verdict MUST be REGENERATE. "
            "(2) Does the response fabricate citations not in the provided list? "
            "If so, verdict MUST be REGENERATE."
        )

    return base
