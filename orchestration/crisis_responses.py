"""
orchestration/crisis_responses.py
===================================
Crisis Response Pool — REQ-300-113 through REQ-300-118.

Implements a 5-template static response pool for Crisis Mode delivery.
All responses are static strings (REQ-300-CM3 equivalent: crisis responses
MUST NOT be LLM-generated — they must be deterministic and clinically reviewed).

Pool behaviour
--------------
REQ-300-113  The pool contains exactly 5 distinct templates.
REQ-300-114  Selection is turn-aware: the same template MUST NOT be delivered
             on consecutive crisis turns.
REQ-300-115  A 6-element rotation index prevents any template from repeating
             until all 5 have been used (Fisher-Yates conceptually; simplified
             here to a deterministic offset cycle).
REQ-300-116  From turn 3 onward, prepend a continuity-acknowledgment sentence
             that names the ongoing nature of the conversation ("You've reached
             out again — that matters.").
REQ-300-117  After the pool is exhausted (turn 6+), switch to ANCHOR_RESPONSE —
             a warm, non-repeating holding message for extended crisis contact.
REQ-300-118  The Interaction Model is fully bypassed for crisis responses.
             These strings are never passed to ADP-A or ADP-C.

Implementation note: the crisis turn counter is derived by the caller
(NikkoPipeline / main.py) from the session's conversation_history by counting
how many of the most recent assistant turns contain the Lifeline number.
This is a stateless derivation — no server-side session state required.
"""

# ── Continuity acknowledgment prefix (REQ-300-116) ────────────────────────────
# Prepended to responses from crisis turn 3 onward.
# The intent: acknowledge that the user has kept reaching out (continuity),
# without implying Nikko is a substitute for human crisis support.
_CONTINUITY_PREPEND = (
    "You've reached out again — that matters, and I'm still here with you. "
)

# ── Crisis response pool (REQ-300-113) ────────────────────────────────────────
# Five templates; each hits the same safety essentials (hotlines, safety check)
# with distinct opening framings so the user doesn't feel they're hitting a
# recorded message on their worst turn.
#
# Design constraints:
#   - Every template MUST include Lifeline (13 11 14) as the primary number.
#   - No template attempts to assess crisis severity — that's ADP-B's job.
#   - Language is direct, warm, and short. No long paragraphs in crisis context.
#   - First-person "I" framing is intentionally limited — the hotline numbers
#     are the primary actor, Nikko is secondary.

CRISIS_POOL: list[str] = [
    # Template 0 — direct + grounding
    (
        "I'm really glad you reached out, and I want to make sure you're safe right now. "
        "Please contact one of these services immediately:\n\n"
        "- **Lifeline:** 13 11 14 (24/7)\n"
        "- **Beyond Blue:** 1300 22 4636\n"
        "- **13YARN** (Aboriginal & Torres Strait Islander): 13 92 76\n"
        "- **Emergency:** 000\n\n"
        "I'm here with you. Would you like to talk about what's going on?"
    ),

    # Template 1 — safety-first, then openness
    (
        "What you're sharing sounds really serious, and your safety matters most right now. "
        "Please reach out to one of these services — they're available 24/7 and are "
        "trained for exactly this kind of moment:\n\n"
        "- **Lifeline:** 13 11 14\n"
        "- **Suicide Call Back Service:** 1300 659 467\n"
        "- **Beyond Blue:** 1300 22 4636\n"
        "- **Emergency:** 000\n\n"
        "You don't have to figure this out alone. What's been happening?"
    ),

    # Template 2 — validation-first, then safety
    (
        "It takes courage to say what you're feeling. I hear you, and I want you "
        "to be safe. Right now, please connect with someone who can truly be there "
        "with you:\n\n"
        "- **Lifeline:** 13 11 14 (24/7)\n"
        "- **Beyond Blue:** 1300 22 4636\n"
        "- **13YARN** (First Nations, 24/7): 13 92 76\n"
        "- **Emergency:** 000\n\n"
        "I'm here. Can you tell me a little more about where you're at?"
    ),

    # Template 3 — grounding language + immediacy
    (
        "Right now, the most important thing is making sure you're safe. "
        "Please call or message one of these services — they're ready for you:\n\n"
        "- **Lifeline:** 13 11 14 (call or text, 24/7)\n"
        "- **Beyond Blue:** 1300 22 4636\n"
        "- **Kids Helpline** (under 25): 1800 55 1800\n"
        "- **Emergency:** 000\n\n"
        "Would you be able to reach out to one of them? I'll be right here."
    ),

    # Template 4 — brief + warm + resource-centric
    (
        "Thank you for trusting me with this. Your safety comes first — please "
        "contact one of these services right now:\n\n"
        "- **Lifeline:** 13 11 14\n"
        "- **Suicide Call Back Service:** 1300 659 467\n"
        "- **1800RESPECT** (family violence): 1800 737 732\n"
        "- **Emergency:** 000\n\n"
        "I'm still here with you. What's been going on?"
    ),
]

# ── Anchor response — pool exhausted (REQ-300-117) ────────────────────────────
# Used from crisis turn 6 onward when the pool has cycled through once.
# Intentionally shorter and more direct — repetition fatigue is real.
ANCHOR_RESPONSE: str = (
    "I'm still here with you, and I'm glad you're still reaching out. "
    "Please stay connected with Lifeline — 13 11 14, available 24/7. "
    "They can stay on the line with you in a way I can't. "
    "Is there anything you'd like to say right now?"
)

_POOL_SIZE: int = len(CRISIS_POOL)


def select_crisis_response(
    crisis_turn_index: int,
    last_pool_index: int = -1,
) -> str:
    """
    Select the appropriate crisis response for this turn.

    Parameters
    ----------
    crisis_turn_index : int
        Zero-based count of how many crisis turns have occurred so far
        in this conversation (including the current turn).
        - 0 → first crisis turn
        - 1 → second crisis turn
        - 5+ → anchor mode

    last_pool_index : int
        The pool index used on the previous crisis turn (-1 if none).
        Used to prevent consecutive repeat (REQ-300-114).

    Returns
    -------
    str
        The complete crisis response text to deliver to the frontend.

    [CONCEPT] Pool selection algorithm:
    We cycle through the 5 templates in a deterministic offset rotation.
    The rotation index is simply (crisis_turn_index % _POOL_SIZE), which
    guarantees no template repeats until the cycle wraps at turn 5.
    If the selected index happens to match last_pool_index (turn 6+ wrap),
    we advance by 1 to avoid a consecutive repeat (REQ-300-114).
    """
    # Anchor mode: pool has been exhausted at least once (turn 5+)
    if crisis_turn_index >= _POOL_SIZE:
        return ANCHOR_RESPONSE

    # Pick index via rotation, advance by 1 on consecutive-repeat collision
    idx = crisis_turn_index % _POOL_SIZE
    if idx == last_pool_index and last_pool_index >= 0:
        idx = (idx + 1) % _POOL_SIZE

    body = CRISIS_POOL[idx]

    # Prepend continuity acknowledgment from turn 3 onward (REQ-300-116).
    # crisis_turn_index 0 = first crisis turn; index 2 = third turn.
    if crisis_turn_index >= 2:
        body = _CONTINUITY_PREPEND + body

    return body


def count_crisis_turns_from_history(conversation_history: list | None) -> int:
    """
    Derive the current crisis turn count from conversation_history.

    Inspects the tail of the assistant's prior turns to count how many
    consecutive responses contained the Lifeline number (13 11 14).
    This is the stateless derivation path — no server-side session state.

    Used by backend/main.py to compute crisis_turn_index before calling
    select_crisis_response().

    Parameters
    ----------
    conversation_history : list[{role: str, text: str}] | None
        Session conversation history forwarded from the frontend.
        Session-scoped React state — evaporates on page refresh.

    Returns
    -------
    int
        Number of consecutive crisis turns ending at the last assistant message.
        Returns 0 if no history or no prior crisis turns.
    """
    if not conversation_history:
        return 0

    # Walk backwards through history, counting consecutive assistant crisis turns.
    # Stop as soon as we see a non-crisis assistant turn or a user turn that breaks
    # the streak. This is a "consecutive" count, not a total count, because a
    # non-crisis turn in between resets the pool (the user came back from crisis).
    count = 0
    for turn in reversed(conversation_history):
        if turn.get("role") != "assistant":
            continue
        text = turn.get("text", "") or turn.get("content", "")
        if "13 11 14" in text or "Lifeline" in text:
            count += 1
        else:
            break   # non-crisis assistant turn ends the streak

    return count
