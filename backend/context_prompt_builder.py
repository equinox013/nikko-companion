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

from docs.schemas.acp_schemas import OperationalMode, ResponseContextPayload

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
    "Instead, begin by directly acknowledging the specific thing the user described."
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
        # Truncate to protect context window — 1200 chars is ≈ 300 tokens,
        # enough for a rich diary entry while leaving headroom for evidence.
        mem_snippet = context.usm_content[:1200]
        if len(context.usm_content) > 1200:
            mem_snippet += "\n[Memory file truncated — remaining content not shown]"
        parts.append(
            "\nPERSONAL CONTEXT (from user's memory file — treat as background, "
            "not diagnosis):\n"
            "---\n"
            f"{mem_snippet}\n"
            "---\n"
            "Use this context to personalise your response. "
            "Do NOT infer clinical diagnoses, crisis state, or ongoing care needs "
            "from memory content alone.  The live conversation is your primary signal."
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
    base = (
        "You are a response quality evaluator for a mental health support app. "
        "Given a user message and a proposed assistant response, output a JSON object: "
        "verdict: APPROVE if the response is empathetic, safe, and appropriate. "
        "verdict: REGENERATE if the response is harmful, dismissive, clinically "
        "inappropriate, overly advice-heavy in Comfort Mode, or fails to ground "
        "its response in evidence in Guidance Mode. "
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
