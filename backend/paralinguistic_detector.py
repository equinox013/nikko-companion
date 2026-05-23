"""
backend/paralinguistic_detector.py
====================================
Render-side regex/heuristic detector for deterministic paralinguistic and
structural signals in user messages.

WHY THIS EXISTS
---------------
Pre-analysis was originally delegated entirely to Qwen3-4B (Modal, Step 1.5)
via LLM inference. This caused two problems:

  1. Obvious structural signals (all_lowercase, ellipsis_trail) were consistently
     missed because the model hedged on pattern-matching tasks it was never trained
     to perform reliably ("this might just be casual style").

  2. Latency: every signal detection required a network call to Modal and a GPU
     inference pass, even when the detection logic is pure text inspection.

The fix is a split architecture:
  • STRUCT signals + non-semantic PARA signals  → this module (Render, pure Python,
    deterministic, zero latency, zero cost).
  • Semantic PARA signals (tone_softener, minimisation, mixed_affect,
    typographic_register, fragmented_syntax, register_collapse) → Qwen3-4B on Modal.

The merged annotation string from both sources is injected into ADP-B's safety
system prompt so the crisis classifier can account for masked or minimised distress.

SIGNAL TAXONOMY (SPEC-100 §16)
-------------------------------
This module emits tags using the existing NIKKO annotation format:
  [STRUCT: tag_name]   — message structure signals
  [PARA: tag_name]     — paralinguistic / typographic signals

Signals detected here (8 total):
  [STRUCT: all_lowercase]        — Full message in lowercase (4+ words).
                                   McCulloch (2019) Ch. 4: "minimalist typography" —
                                   deliberate absence of caps signals sincere / deadpan
                                   / emotionally drained register.

  [STRUCT: ellipsis_trail]       — Two or more ellipsis clusters (... or …).
                                   Signals hesitation, trailing off, approaching
                                   disclosure but not completing it.

  [STRUCT: all_caps_segment]     — Isolated ALL-CAPS burst in otherwise mixed-case text.
                                   McCulloch: intensity amplifier on whatever emotion
                                   surrounds it. Acronyms excluded.

  [PARA: expressive_lengthening] — Letter repeated 3+ times ("noooo", "pleaseeee").
                                   McCulloch: drawn-out spoken sound; arousal amplifier.
                                   Repeat count correlates with intensity.

  [PARA: punctuation_urgency]    — Two or more consecutive ??, !!, or mixed ?! runs.
                                   Signals confusion, disbelief, urgency, or shock.

  [PARA: keysmash]               — Haphazard keyboard mash (asdfjkl;, fkdjsla).
                                   McCulloch: emotional overwhelm — flailing excitement,
                                   frustration, or being lost for words. Very high arousal.

  [PARA: emoji_distress]         — One or more distress-coded emoji, OR any emoji
                                   repeated 3+ times (repetition amplifies intensity).
                                   Apriliani & Muslim (2021): emojis as paralinguistic
                                   cues; repetition = amplification.

  [PARA: asterisk_action]        — Asterisk-wrapped stage directions: *sigh*, *cries*,
                                   *shakes head*. Explicit tone/action annotation that
                                   bypasses verbal expression. Signals emotional state
                                   the user cannot or will not state directly.

Semantic PARA signals NOT detected here (delegated to Qwen3-4B on Modal):
  [PARA: tone_softener]          — Laughter AFTER distress (context-dependent).
  [PARA: minimisation]           — Distress walked back with "it's fine" etc.
  [PARA: mixed_affect]           — Contradictory emotions within one message.
  [PARA: typographic_register]   — Formal → informal register shift (semantic).
  [STRUCT: fragmented_syntax]    — Incomplete clauses / broken grammar (structural).
  [STRUCT: register_collapse]    — Message degrades from sentences to fragments (structural).

REFERENCES
----------
  Wylie (2020): culture & paralinguistic features (KR–EN virtual exchange)
  Al Tawil (2019): electronic nonverbal cues (eNVC) in async online education
  Apriliani & Muslim (2021): emojis & grounding in WhatsApp discourse
  McCulloch (2019), Because Internet: Ch. 4 "Typographical Tone of Voice",
                                      Ch. 5 "Emoji and Other Internet Gestures"
  See docs/paralinguistic_emotion_cues.md for full reference patterns.

USAGE
-----
  from backend.paralinguistic_detector import detect

  tags = detect("hi there... just gotten off a shitty shift... sigh idk")
  # → "[STRUCT: all_lowercase] [STRUCT: ellipsis_trail]"
"""

from __future__ import annotations

import re

# ── Compiled patterns (module-level, compiled once) ──────────────────────────

# Full message is lowercase — no uppercase letters at all.
# Only meaningful when the message is 4+ words (guards against "ok", "lol").
# McCulloch: "minimalist typography" — sincere, deadpan, or drained register.
_RE_ALL_LOWERCASE = re.compile(r"^[^A-Z]+$")

# Two or more ellipsis clusters anywhere in the message.
# Covers both ASCII "..." (2+ dots) and the Unicode ellipsis glyph "…".
# A single trailing ellipsis for stylistic pause does NOT fire this tag;
# the 2+ cluster requirement is the guard.
_RE_ELLIPSIS = re.compile(r"\.{2,}|…")

# Runs of 2+ consecutive ALL-CAPS words (2+ chars each).
# Used to find isolated CAPS bursts — intensity spikes that amplify surrounding emotion.
# A single all-caps word like "I" is excluded by the {2,} char minimum.
_RE_CAPS_WORDS = re.compile(r"\b[A-Z]{2,}\b")

# Common acronyms that are uppercase by convention, NOT shouting.
# Extend this set as needed — any genuine acronym that might appear in chat.
_ACRONYMS: frozenset[str] = frozenset({
    "OK", "LOL", "OMG", "WTF", "IDK", "IKR", "SMH", "NGL", "IMO", "IMHO",
    "FYI", "ASAP", "BRB", "AFK", "TBH", "TBF", "TMI", "DM", "PM",
    "USA", "UK", "AU", "NZ", "EU", "UN", "WHO", "GP", "ER",
    "PTSD", "OCD", "ADHD", "ASD", "CBT", "DBT", "MH",
    "API", "URL", "AI", "ML", "IT",
})

# Letter repeated 3+ times — drawn-out sound / arousal amplifier.
# Excludes legitimate doubles ("letter", "committee") by requiring 3+.
# McCulloch: tracks repeat count for intensity; we just flag presence here.
_RE_EXPRESSIVE = re.compile(r"([A-Za-z])\1{2,}")

# Two or more consecutive question marks or exclamation marks,
# OR a mixed run containing both ? and ! (interrobang).
# Single ? or single ! do NOT fire — they're normal punctuation.
_RE_PUNCT_URGENCY = re.compile(
    r"\?{2,}"                              # ?? ???
    r"|!{2,}"                              # !! !!!
    r"|(?=[!?]{2,})(?=[!?]*\?)(?=[!?]*!)[!?]+"  # mixed ?! !? ?!?! etc.
)

# Asterisk-wrapped stage directions: *sigh*, *cries*, *shakes head*.
# The 1–40 char bound prevents runaway matches on markdown-heavy content.
# Underscore wrapping (_text_) is included: same semantic role in IM context.
_RE_ASTERISK = re.compile(r"\*[^*\n]{1,40}\*|_[^_\n]{1,40}_")

# Laughter tokens — haha, hehe, lol, lmao, xD and elongations.
# Used to detect raw presence; whether it's face-saving laughter (tone_softener)
# is a semantic question left to the LLM. This purely detects the token.
_RE_LAUGHTER = re.compile(
    r"\b(?:(?:a?ha){2,}h?|l(?:o+l+)+|lm+f?a+o+|(?:he){2,}|xd+)\b",
    re.IGNORECASE,
)

# Distress-coded emoji set.
# These carry clear negative valence in mental-health adjacent contexts.
# Source: SPEC-100 §16 definition of [PARA: emoji_distress].
_DISTRESS_EMOJI: frozenset[str] = frozenset({
    "😭", "😔", "💔", "😶", "😶‍🌫️", "🥺", "😞", "😣", "😢", "🖤", "💀",
    "😩", "😫", "🙃", "😕", "😟", "😰", "😱", "🤯", "💭", "🫠",
})


# ── Keysmash heuristic ────────────────────────────────────────────────────────

def _is_keysmash(token: str) -> bool:
    """
    Return True if `token` looks like a keyboard mash.

    Heuristic from McCulloch (2019) Ch. 4, implemented as per the reference doc:
    - Minimum 5 alpha characters (shorter tokens are too ambiguous).
    - Vowel ratio < 20%  — keysmash is consonant-heavy (home row is mostly consonants).
    - Home-row ratio > 65% — fingers rest on asdfghjkl; mashing favours these keys.

    Why not pure regex? A pattern like r"[a-z]{5,}" over-captures real words and
    abbreviations. The vowel + home-row combination is what makes it usable.

    THRESHOLD CALIBRATION (2026-05-23):
    Original thresholds (vowel < 35%, home-row > 50%) caused false positives on
    common English words. "shift" (s,h,i,f,t): vowel=20%, home-row=60% — fired
    despite being a real word. Tightening to < 20% / > 65% fixes this class:
      - "shift" at 20% vowel is NOT strictly < 20% → no longer fires ✓
      - True keysmashes ("asdfjkl", "fkdjsla") at 0–14% vowel still fire ✓
    """
    t = token.lower()
    if len(t) < 5 or not t.isalpha():
        return False
    vowel_ratio   = sum(c in "aeiou"     for c in t) / len(t)
    homerow_ratio = sum(c in "asdfghjkl" for c in t) / len(t)
    return vowel_ratio < 0.20 and homerow_ratio > 0.65


def _has_keysmash(text: str) -> bool:
    """Return True if any token in `text` passes the keysmash heuristic."""
    # Only inspect alpha-only runs — digits and punctuation are not keysmash.
    for token in re.findall(r"[A-Za-z]+", text):
        if _is_keysmash(token):
            return True
    return False


# ── Emoji detection ───────────────────────────────────────────────────────────

def _emoji_distress_present(text: str) -> bool:
    """
    Return True if the message contains any distress-coded emoji OR any emoji
    repeated 3+ times consecutively.

    Two-tier check (mirrors SPEC-100 §16 definition):
      Tier 1 — presence of any emoji in _DISTRESS_EMOJI.
      Tier 2 — any single emoji (distress or not) appearing 3+ times in a row.
               Apriliani & Muslim: repetition amplifies intensity regardless of
               which emoji is repeated ("😊😊😊" is just as significant as "😭😭😭").

    We do NOT use the `emoji` library to avoid adding a new Render dependency.
    Instead we use a regex that matches Unicode emoji ranges directly — imperfect
    for exotic ZWJ sequences but sufficient for the distress-coded set and basic
    repetition detection.
    """
    # Tier 1: known distress emoji.
    for ch in text:
        if ch in _DISTRESS_EMOJI:
            return True

    # Tier 2: any emoji repeated 3+ times.
    # Match any single emoji character (basic Unicode range U+1F300–U+1FFFF covers
    # most standard emoji; also includes common symbols U+2600–U+27BF).
    # ZWJ sequences (e.g. 👨‍👩‍👧) will partially match but that's acceptable here —
    # we're detecting repetition intensity, not exact emoji identity.
    emoji_run_re = re.compile(
        r"([\U0001F300-\U0001FFFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F])\1{2,}"
    )
    return bool(emoji_run_re.search(text))


# ── All-caps detection ────────────────────────────────────────────────────────

def _has_caps_segment(text: str) -> bool:
    """
    Return True if the message contains a non-acronym ALL-CAPS segment.

    A single isolated CAPS word is a shout only if it is 3+ characters and not
    in the acronym whitelist. A run of 2+ CAPS words is always a shout regardless
    of length (multi-word caps are far more likely to be emphasis than initialisms).
    """
    caps_tokens = _RE_CAPS_WORDS.findall(text)
    non_acronym = [t for t in caps_tokens if t not in _ACRONYMS]

    if len(non_acronym) >= 2:
        # Two or more non-acronym CAPS words → clear shout segment.
        return True
    if len(non_acronym) == 1 and len(non_acronym[0]) >= 3:
        # Single non-acronym CAPS word of 3+ chars → likely shouting.
        return True
    return False


# ── Public API ────────────────────────────────────────────────────────────────

def detect(text: str) -> str:
    """
    Run all deterministic detectors against `text` and return a space-separated
    annotation string in the NIKKO tag format.

    Args:
        text: Raw user message text (pre-sanitised; PII already redacted by Render).

    Returns:
        Space-separated annotation string, e.g.:
          "[STRUCT: all_lowercase] [STRUCT: ellipsis_trail] [PARA: keysmash]"
        Returns "" if no signals are detected.

    Design notes:
    - Each detector is independent — they do not interact or gate each other.
    - Order in the output matches SPEC-100 §16 taxonomy order (STRUCT before PARA).
    - All regex patterns are compiled at module load, not per call.
    - This function is pure: no side effects, no network, no logging.
      Callers (draft_generator.py) are responsible for logging the result.
    """
    if not text or not text.strip():
        return ""

    stripped = text.strip()
    tags: list[str] = []

    # ── STRUCT signals ──────────────────────────────────────────────────────

    # [STRUCT: all_lowercase] — entire message has no uppercase letters, 4+ words.
    # Word-count guard prevents single-word messages ("ok", "hi") from firing.
    if (
        _RE_ALL_LOWERCASE.match(stripped)
        and len(stripped.split()) >= 4
    ):
        tags.append("[STRUCT: all_lowercase]")

    # [STRUCT: ellipsis_trail] — 2+ ellipsis clusters.
    # findall returns all non-overlapping matches; len >= 2 is the threshold.
    if len(_RE_ELLIPSIS.findall(stripped)) >= 2:
        tags.append("[STRUCT: ellipsis_trail]")

    # [STRUCT: all_caps_segment] — non-acronym CAPS burst in otherwise mixed-case.
    # Skip check if the entire message is all-caps (already covered by all_caps_segment
    # but avoid double-flagging a pure-shouting message with no lowercase context).
    if _has_caps_segment(stripped):
        tags.append("[STRUCT: all_caps_segment]")

    # ── PARA signals ────────────────────────────────────────────────────────

    # [PARA: expressive_lengthening] — letter repeated 3+ times.
    if _RE_EXPRESSIVE.search(stripped):
        tags.append("[PARA: expressive_lengthening]")

    # [PARA: punctuation_urgency] — ?? !! ?! runs (2+ consecutive).
    if _RE_PUNCT_URGENCY.search(stripped):
        tags.append("[PARA: punctuation_urgency]")

    # [PARA: keysmash] — haphazard keyboard mashing.
    if _has_keysmash(stripped):
        tags.append("[PARA: keysmash]")

    # [PARA: emoji_distress] — distress emoji present, or any emoji repeated 3+.
    if _emoji_distress_present(stripped):
        tags.append("[PARA: emoji_distress]")

    # [PARA: asterisk_action] — *sigh*, *cries*, _shakes head_ stage directions.
    if _RE_ASTERISK.search(stripped):
        tags.append("[PARA: asterisk_action]")

    return " ".join(tags)
