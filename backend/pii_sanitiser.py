"""
pii_sanitiser.py — Named-entity redaction for SPEC-800 compliance.

WHY THIS EXISTS
───────────────
SPEC-800 (REQ-800-008 through REQ-800-012) prohibits user-identifiable
information from reaching server-side logs or storage. The NER pass here
redacts named entities in user input *before* any LLM sees the raw text,
replacing them with typed placeholders that preserve semantic context
without identifying individuals or places.

Design decisions:
  • REDACT not REMOVE — "[named entity - person]" tells the LLM "there is a
    person here" without exposing who. Removing the token entirely would
    collapse sentence structure and degrade signal detection quality.
  • spaCy en_core_web_sm — CPU-only, ~50 MB, fast (<10 ms on typical
    turns). Adequate NER precision for conversational English.
  • memoryContext is EXEMPT — names the user explicitly stored in their
    memory file are consented data. Sanitisation applies only to live
    message text and conversation history user turns.

ENTITY TYPE MAPPING
───────────────────
  PERSON          → [named entity - person]
  ORG             → [named entity - organisation]
  GPE (city/country) → [named entity - location]
  LOC (physical)  → [named entity - location]
  FAC (facility)  → [named entity - location]

Other entity types (DATE, TIME, MONEY, CARDINAL, etc.) are left intact —
they carry clinically relevant meaning ("I've felt this way for 3 years",
"it happened last Tuesday") and do not identify individuals.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

log = logging.getLogger(__name__)

# [CONCEPT] Lazy import pattern — spaCy is only loaded on first call to
# redact_entities(), not at module import time. This avoids a ~1s startup
# cost on every cold import and allows graceful degradation if the model
# is not installed (returns text unchanged with a warning).
_nlp = None


def _load_model() -> object | None:
    """Load spaCy model once and cache it in module-level _nlp."""
    global _nlp
    if _nlp is not None:
        return _nlp
    try:
        import spacy  # noqa: PLC0415
        _nlp = spacy.load("en_core_web_sm")
        log.info("[pii_sanitiser] spaCy en_core_web_sm loaded.")
    except Exception as exc:  # noqa: BLE001
        # Graceful degradation — if spaCy is not installed or the model is
        # missing, log a warning and return None. Callers check for None and
        # fall back to returning the original text unmodified.
        log.warning(
            "[pii_sanitiser] spaCy unavailable (%s). "
            "NER redaction disabled — text will pass through unmodified. "
            "Install spacy and run: python -m spacy download en_core_web_sm",
            exc,
        )
        _nlp = None  # stays None; we retry next call (allows hot-fix deploys)
    return _nlp


# Maps spaCy entity labels to the placeholder strings the LLM will see.
_ENTITY_PLACEHOLDERS: dict[str, str] = {
    "PERSON": "[named entity - person]",
    "ORG":    "[named entity - organisation]",
    "GPE":    "[named entity - location]",
    "LOC":    "[named entity - location]",
    "FAC":    "[named entity - location]",
}


def redact_entities(text: str) -> str:
    """
    Replace named entities (PERSON, ORG, GPE, LOC, FAC) in *text* with
    typed placeholders.  Returns the redacted string.

    If spaCy is unavailable, returns *text* unchanged (fail-open — a
    missed redaction is preferable to refusing the user's message).

    Args:
        text: Raw user message string.

    Returns:
        Redacted string with entity tokens replaced by placeholder labels.
    """
    if not text or not text.strip():
        return text

    nlp = _load_model()
    if nlp is None:
        # spaCy not available — return unchanged, warning already logged.
        return text

    doc = nlp(text)

    # [CONCEPT] spaCy represents entity spans as doc.ents — a tuple of Span
    # objects each carrying .start_char/.end_char (character offsets into
    # the original string) and .label_ (entity type string). We rebuild the
    # text by walking character offsets, substituting spans as we go.
    # Rebuilding from char offsets (rather than token indices) preserves
    # surrounding whitespace and punctuation exactly.

    result_parts: list[str] = []
    cursor = 0

    for ent in doc.ents:
        placeholder = _ENTITY_PLACEHOLDERS.get(ent.label_)
        if placeholder is None:
            # Entity type we don't redact (DATE, MONEY, etc.) — skip.
            continue

        # Append text between the previous entity end and this one's start.
        result_parts.append(text[cursor : ent.start_char])
        result_parts.append(placeholder)
        cursor = ent.end_char

    # Append any trailing text after the last entity.
    result_parts.append(text[cursor:])
    redacted = "".join(result_parts)

    # Log only that redaction occurred (no entity values) — SPEC-800-011.
    if redacted != text:
        entity_labels = [e.label_ for e in doc.ents if e.label_ in _ENTITY_PLACEHOLDERS]
        log.debug(
            "[pii_sanitiser] redacted %d entity/ies: %s",
            len(entity_labels),
            ", ".join(entity_labels),
        )

    return redacted


def redact_history(history: list[dict]) -> list[dict]:
    """
    Apply redact_entities() to the user-turn content in a conversation
    history list.  Assistant turns are left intact — they were generated
    by the model and contain no raw user PII.

    Args:
        history: List of {role, content} dicts as sent by the frontend.

    Returns:
        New list with user-turn content redacted.  Does not mutate input.
    """
    redacted: list[dict] = []
    for turn in history:
        if turn.get("role") == "user":
            redacted.append({**turn, "content": redact_entities(turn.get("content", ""))})
        else:
            redacted.append(turn)
    return redacted


# ── Log filter ────────────────────────────────────────────────────────────────

class _SanitiseExcFilter(logging.Filter):
    """
    [CONCEPT] A logging.Filter is attached to a Logger or Handler and is
    called for every log record before it is emitted. Returning False from
    filter() suppresses the record; mutating record fields (as we do here)
    lets us sanitise content before it reaches the stream.

    This filter intercepts WARNING-and-above records that carry exc_info
    (i.e. tracebacks). It removes the exc_info tuple so the raw Python
    traceback — which may include local variables containing user text —
    is never emitted to the Render log stream. A safe one-line summary
    of the exception type and message is appended to the log message
    instead, preserving debuggability without PII exposure.

    WHY: Python's exc_info=True dumps the full call stack including the
    values of local variables at every frame. In an async FastAPI handler,
    those locals often include the original request body. This is the
    primary vector by which user text reaches Render logs.
    """

    # Regex patterns that suggest a string may contain user content.
    # Used to further sanitise the exception message string itself.
    _STRIP_PATTERNS = [
        re.compile(r'\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b', re.IGNORECASE),  # email
        re.compile(r'\b\d{10,}\b'),                                       # long digit runs (phone)
    ]

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if record.exc_info:
            exc_type, exc_val, _ = record.exc_info
            # Replace full traceback with a safe type+message summary.
            safe_msg = f"{exc_type.__name__}: {str(exc_val)[:120]}" if exc_type else "unknown error"
            # Strip obvious PII patterns from the exception message itself.
            for pat in self._STRIP_PATTERNS:
                safe_msg = pat.sub("[redacted]", safe_msg)
            # Append to existing message; clear exc_info so no traceback emits.
            record.msg = f"{record.msg} | exc_summary={safe_msg}"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
        return True  # always emit the (now-sanitised) record


def attach_log_filter(logger: logging.Logger) -> None:
    """
    Attach the _SanitiseExcFilter to *logger* so all records from that
    logger (and its children) have tracebacks scrubbed before emission.

    Call once at application startup in main.py.
    """
    f = _SanitiseExcFilter()
    logger.addFilter(f)
    log.debug("[pii_sanitiser] _SanitiseExcFilter attached to logger '%s'.", logger.name)
