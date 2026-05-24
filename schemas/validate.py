"""
schemas/validate.py
========================
Runtime signal validation utilities for Phase 3 agent implementations.

Spec source  : SPEC-100, REQ-100-093
Phase        : 3 — Agent Definitions (Implementation)
Status       : Active

Purpose
-------
Every agent that emits or consumes a SignalPayload MUST validate all
signal key arrays against the canonical enum in signal_enum.json before
emitting any ACP-Message. This module loads the enum once at import
time and provides fast O(1) set-based lookups.

Design choice — why a separate module?
---------------------------------------
We could embed validation inside each agent class, but that would
scatter the source-of-truth check across nine files. Instead, the enum
is loaded *once here* and agents call these helpers. If signal_enum.json
is ever updated, every agent picks up the change automatically on the
next import — no multi-file edits required.

CRITICAL: New signal keys MUST NOT be added by implementation code.
Any new key requires a SPEC-100 revision. (REQ-100-093)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# [CONCEPT] Path(__file__).parent
# ---------------------------------------------------------------------------
# __file__ is the absolute path to *this* file at runtime. .parent gives us
# the directory it lives in (schemas/). We resolve signal_enum.json
# relative to that directory so the import works regardless of which
# directory the caller is running from. This pattern appears again in every
# retrieval adapter when loading local cache indexes.
# ---------------------------------------------------------------------------
_ENUM_PATH = Path(__file__).parent / "signal_enum.json"


# ---------------------------------------------------------------------------
# Private: load and flatten the enum on first import
# ---------------------------------------------------------------------------

def _load_valid_keys(path: Path) -> frozenset[str]:
    """
    Parse signal_enum.json and return every valid signal key as a frozenset.

    Why frozenset?
    - O(1) membership test (vs O(n) list scan).
    - Immutable — no agent can accidentally mutate the set at runtime.

    The risk_indicators category is nested differently from the others:
    its values live under ["risk_indicators"]["tiers"][tier]["values"]
    instead of ["category"]["values"]. We handle both shapes here so the
    rest of the codebase never needs to know about the structural quirk.
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    keys: set[str] = set()

    # Flat categories: distress_levels, emotional_states, cognitive_patterns,
    # behavioral_indicators, support_needs all expose a top-level "values" list.
    flat_categories = [
        "distress_levels",
        "emotional_states",
        "cognitive_patterns",
        "behavioral_indicators",
        "support_needs",
    ]
    for cat in flat_categories:
        keys.update(raw[cat]["values"])

    # Nested category: risk_indicators is split across three severity tiers
    # (passive / active / acute). We flatten all three into the same set.
    # The tier prefix (e.g. "risk.active.") is part of the key string itself,
    # so routing logic can inspect it with a simple .startswith() check.
    for tier_data in raw["risk_indicators"]["tiers"].values():
        keys.update(tier_data["values"])

    return frozenset(keys)


# Module-level constant — loaded once, never mutated.
_VALID_KEYS: frozenset[str] = _load_valid_keys(_ENUM_PATH)

# Expose the full set for introspection in notebooks / tests.
VALID_SIGNAL_KEYS: frozenset[str] = _VALID_KEYS


# ---------------------------------------------------------------------------
# Confidence band classification
# ---------------------------------------------------------------------------

class ConfidenceBand(NamedTuple):
    """
    Named result of a confidence band classification.

    label   : "low" | "moderate" | "high"  (REQ-100-CB1)
    fallback: True when the band is "low" — agents MUST suspend
              confidence-dependent routing. (REQ-100-CB2)
    """
    label: str
    fallback: bool


def get_confidence_band(score: float) -> ConfidenceBand:
    """
    Classify a raw confidence float into the three SPEC-100 bands.

    Thresholds (REQ-100-CB1):
      low      : [0.0, 0.40)   → fallback routing MUST be applied
      moderate : [0.40, 0.70]  → standard processing
      high     : (0.70, 1.0]   → full confidence-dependent routing

    Args:
        score: Confidence float in [0.0, 1.0].

    Returns:
        ConfidenceBand named tuple with label and fallback flag.

    Raises:
        ValueError: If score is outside [0.0, 1.0].
    """
    if not (0.0 <= score <= 1.0):
        raise ValueError(
            f"Confidence score {score!r} is outside the valid range [0.0, 1.0]. "
            "All confidence values must be produced by the Signal Agent's "
            "softmax output and clamped before this call. (REQ-200-035)"
        )

    if score < 0.40:
        return ConfidenceBand(label="low", fallback=True)
    elif score <= 0.70:
        return ConfidenceBand(label="moderate", fallback=False)
    else:
        return ConfidenceBand(label="high", fallback=False)


# ---------------------------------------------------------------------------
# Key-level validation
# ---------------------------------------------------------------------------

def validate_signal_key(key: str) -> bool:
    """
    Return True if `key` is a registered signal key in signal_enum.json.

    Usage in agents:
        if not validate_signal_key(k):
            raise ValueError(f"Unknown signal key: {k!r}. (REQ-100-093)")

    Args:
        key: The signal key string to check (e.g. "risk.active.suicidal_ideation").

    Returns:
        bool — True if valid, False if not registered.
    """
    return key in _VALID_KEYS


# ---------------------------------------------------------------------------
# Payload-level validation
# ---------------------------------------------------------------------------

class PayloadValidationResult(NamedTuple):
    """
    Structured result from validate_signal_payload().

    valid         : True only if *all* arrays contain only registered keys.
    invalid_keys  : Flat list of every unregistered key found, with the
                    field name prefixed (e.g. "risk_indicators:unknown.key").
                    Empty when valid=True.
    """
    valid: bool
    invalid_keys: list[str]


def validate_signal_payload(
    emotional_states:       list[str],
    cognitive_patterns:     list[str],
    behavioral_indicators:  list[str],
    risk_indicators:        list[str],
    support_needs:          list[str],
) -> PayloadValidationResult:
    """
    Sweep all five signal arrays and return a structured validation result.

    Called by the Signal Agent immediately before emitting a SignalPayload.
    Any invalid keys MUST cause the agent to either correct the output or
    emit a fallback — never silently pass garbage downstream. (REQ-100-093)

    Args:
        emotional_states       : From SignalPayload.emotional_states
        cognitive_patterns     : From SignalPayload.cognitive_patterns
        behavioral_indicators  : From SignalPayload.behavioral_indicators
        risk_indicators        : From SignalPayload.risk_indicators
        support_needs          : From SignalPayload.support_needs

    Returns:
        PayloadValidationResult with valid flag and list of offending keys.

    Example:
        result = validate_signal_payload(
            emotional_states=["sadness_spectrum.low_mood_language"],
            cognitive_patterns=["rumination_loop"],
            behavioral_indicators=[],
            risk_indicators=["risk.active.suicidal_ideation"],
            support_needs=["emotional_validation"],
        )
        assert result.valid is True
    """
    # [CONCEPT] zip() over parallel sequences
    # We pair each field name with its list so we can produce human-readable
    # error messages like "risk_indicators:unknown.key" rather than a raw
    # key string with no context. This pattern repeats in the pipeline's
    # execution trace builder (pipeline.py).
    fields = {
        "emotional_states":      emotional_states,
        "cognitive_patterns":    cognitive_patterns,
        "behavioral_indicators": behavioral_indicators,
        "risk_indicators":       risk_indicators,
        "support_needs":         support_needs,
    }

    invalid: list[str] = []
    for field_name, keys in fields.items():
        for key in keys:
            if key not in _VALID_KEYS:
                invalid.append(f"{field_name}:{key}")

    return PayloadValidationResult(valid=len(invalid) == 0, invalid_keys=invalid)


# ---------------------------------------------------------------------------
# Pydantic smoke test — call once on startup to verify the environment
# ---------------------------------------------------------------------------

def run_pydantic_smoke_test() -> None:
    """
    Verify that Pydantic v2 and the ACP schemas import and validate correctly.

    This catches missing dependencies (Pydantic not installed, wrong version)
    and schema regressions (someone edited acp_schemas.py and broke a model).

    Raises:
        ImportError   : If Pydantic or the schemas can't be imported.
        AssertionError: If a known-good payload fails validation.
        RuntimeError  : If Pydantic's version is not v2.

    Call this in your environment setup script or CI entrypoint — not in
    the hot path of every request.
    """
    import pydantic

    # Ensure we're on Pydantic v2 — v1 has a different API and will silently
    # produce wrong behaviour if someone installs the wrong version.
    major = int(pydantic.VERSION.split(".")[0])
    if major < 2:
        raise RuntimeError(
            f"Pydantic v2 required; found v{pydantic.VERSION}. "
            "Run: pip install 'pydantic>=2.0' --break-system-packages"
        )

    # Import the Phase 2 schema contracts.
    from schemas.acp_schemas import (
        DistressLevel,
        OperationalMode,
        SignalPayload,
        StrategyPayload,
    )

    # Build a minimal known-good SignalPayload. If this fails, a schema field
    # has been changed without a corresponding REQ-ID update.
    test_signal = SignalPayload(
        distress_level=DistressLevel.MODERATE,
        emotional_states=["sadness_spectrum.low_mood_language"],
        cognitive_patterns=["rumination_loop"],
        behavioral_indicators=[],
        risk_indicators=[],
        support_needs=["emotional_validation"],
        confidence=0.65,
    )
    assert test_signal.distress_level == DistressLevel.MODERATE, (
        "SignalPayload distress_level round-trip failed."
    )

    # Build a minimal StrategyPayload.
    test_strategy = StrategyPayload(
        mode=OperationalMode.COMFORT,
        distress_level=DistressLevel.MODERATE,
        tone_guidance="Warm, non-directive.",
        framing_strategy="Validate before exploring.",
        response_constraints=[],
    )
    assert test_strategy.mode == OperationalMode.COMFORT, (
        "StrategyPayload mode round-trip failed."
    )

    print(
        f"[validate.py] Pydantic smoke test PASSED "
        f"(Pydantic v{pydantic.VERSION}, {len(_VALID_KEYS)} signal keys loaded)."
    )
