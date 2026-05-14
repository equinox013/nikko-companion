"""
backend/main.py -- Nikko orchestration API (Phase 7).

Sits between the React frontend and the HF Spaces inference layer.
Implements the three-stage pipeline per SPEC-200 and SPEC-300:

  1. ADP-B  (safety/crisis check)  -- always runs first
  2. ADP-A  (empathy response)     -- runs if ADP-B clears the message
  3. ADP-C  (evaluator)            -- quality-gates the ADP-A draft;
                                      triggers one regen if it fails

Endpoints contracted in FRONTEND_INTEGRATION_SPEC.md:
  GET  /health           -- loading screen polls this (REQ-FIS-LS2)
  POST /api/message      -- primary chat, streams SSE to frontend
  POST /api/message/mock -- hardcoded fixture for frontend testing
"""

import asyncio
import json
import os
import time
import uuid
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ── Config ────────────────────────────────────────────────────────────────────

# HF Space URL -- set via: fly secrets set HF_SPACE_URL=https://...
HF_SPACE_URL = os.getenv("HF_SPACE_URL", "").rstrip("/")

# Shared secret with the HF Space -- set via: fly secrets set NIKKO_INTERNAL_TOKEN=...
INTERNAL_TOKEN = os.getenv("NIKKO_INTERNAL_TOKEN", "")

# Timeout for each /infer call to HF Space.
# ZeroGPU cold-start can take up to 30s; warm inference is ~5-10s.
INFER_TIMEOUT_S = 90

# Nikko system prompt -- sets the persona and safety framing for ADP-A.
# Kept short so it fits within the 2048-token context window after conversation history.
NIKKO_SYSTEM = (
    "You are Nikko, a safety-aligned wellbeing companion. "
    "You are warm, empathetic, and non-diagnostic. "
    "You support users with evidence-based wellbeing strategies. "
    "You are not a therapist. If a user is in crisis, always direct them to real human support. "
    "Respond in plain, clear English. Be concise."
)

# ADP-B system prompt -- instructs the safety classifier to output a structured verdict.
SAFETY_SYSTEM = (
    "You are a safety classifier for a mental health support app. "
    "Analyse the user message and output a JSON object with two keys: "
    "\"crisis\": true if the message indicates immediate risk of harm to self or others, false otherwise. "
    "\"flags\": a list of triggered safety signals (e.g. [\"suicidal_ideation\", \"self_harm\"]) or empty list. "
    "Output ONLY the JSON object. No explanation."
)

# ADP-C system prompt -- evaluates an (input, response) pair.
EVAL_SYSTEM = (
    "You are a response quality evaluator for a mental health support app. "
    "Given a user message and a proposed assistant response, output a JSON object: "
    "\"verdict\": \"APPROVE\" if the response is empathetic, safe, and appropriate, "
    "or \"REGENERATE\" if it is harmful, dismissive, or clinically inappropriate. "
    "\"reason\": one sentence explanation. "
    "Output ONLY the JSON object."
)

# Australian crisis resources -- injected when ADP-B detects a crisis signal.
CRISIS_RESPONSE = (
    "I'm really glad you reached out, and I want to make sure you're safe right now. "
    "Please contact one of these services immediately:\n\n"
    "- **Lifeline:** 13 11 14 (24/7)\n"
    "- **Beyond Blue:** 1300 22 4636\n"
    "- **13YARN** (Aboriginal & Torres Strait Islander): 13 92 76\n"
    "- **Emergency:** 000\n\n"
    "I'm here with you. Would you like to talk about what's going on?"
)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nikko Backend API",
    version="0.1.0",
    docs_url="/docs" if os.getenv("NIKKO_ENV") == "development" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://equinox013.github.io",
        "http://localhost:8000",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# ── Request / response models ─────────────────────────────────────────────────

class MoodSnapshot(BaseModel):
    selfReport:      int | None = Field(None, ge=1, le=5)
    dominantEmotion: str | None = None

class MessageRequest(BaseModel):
    text:          str           = Field(..., min_length=1, max_length=4000)
    contextId:     str | None    = None
    userId:        str | None    = None
    moodSnapshot:  MoodSnapshot | None = None

class SSEChunk(BaseModel):
    text:        str       = ""
    emotion:     str       = "calm"
    sourcesUsed: list[str] = Field(default_factory=list)
    safetyFlags: list[str] = Field(default_factory=list)

# ── HF Space client ───────────────────────────────────────────────────────────

async def _infer(adapter: str, messages: list[dict], system: str = "") -> str:
    """
    Calls POST /infer on the HF Space and returns the generated text.

    [CONCEPT] httpx.AsyncClient is used instead of requests so this coroutine
    doesn't block the FastAPI event loop while waiting for the GPU. Other
    requests (e.g. /health probes) can still be served during the wait.
    """
    if not HF_SPACE_URL:
        raise RuntimeError("HF_SPACE_URL env var not set. Run: fly secrets set HF_SPACE_URL=...")

    payload = {
        "messages": messages,
        "adapter":  adapter,
        "system":   system,
        "token":    INTERNAL_TOKEN,
    }

    async with httpx.AsyncClient(timeout=INFER_TIMEOUT_S) as client:
        resp = await client.post(f"{HF_SPACE_URL}/infer", json=payload)
        resp.raise_for_status()
        return resp.json()["text"]

# ── Pipeline ──────────────────────────────────────────────────────────────────

def _parse_json_verdict(raw: str) -> dict:
    """
    Extracts a JSON object from ADP-B or ADP-C output.
    The model occasionally wraps the JSON in markdown code fences -- strip them.
    """
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}

async def _pipeline(request: MessageRequest) -> AsyncGenerator[SSEChunk, None]:
    """
    Three-stage inference pipeline per SPEC-200 and SPEC-300.

    Stage 1 -- ADP-B safety check
    Stage 2 -- ADP-A empathy response (skipped on crisis)
    Stage 3 -- ADP-C evaluation with one regen loop

    Each _infer() call is individually wrapped so a HF Space error in any
    stage degrades gracefully: ADP-B failure -> treat as safe (no crisis);
    ADP-A failure -> emit a warm holding response; ADP-C failure -> APPROVE.
    The frontend always receives a text chunk and message_end.
    """
    user_msg = request.text.strip()
    messages = [{"role": "user", "content": user_msg}]

    # ── Stage 1: Safety / crisis check (ADP-B) ────────────────────────────────
    yield SSEChunk(emotion="think", text="")

    try:
        safety_raw = await _infer("adp_b", messages, system=SAFETY_SYSTEM)
        safety     = _parse_json_verdict(safety_raw)
        is_crisis  = safety.get("crisis", False)
        flags      = safety.get("flags", [])
    except Exception as exc:
        # ADP-B unavailable -- fail open (treat as safe) and log.
        # Never block a user from getting support because the classifier is down.
        import logging
        logging.getLogger("nikko").warning(f"ADP-B failed: {exc}")
        is_crisis, flags = False, []

    # [REQ-300-161] Crisis path: bypass ADP-A, return hard-coded resources.
    if is_crisis:
        yield SSEChunk(
            text=CRISIS_RESPONSE,
            emotion="care",
            safetyFlags=flags or ["crisis_detected"],
        )
        return

    # ── Stage 2: Empathy response (ADP-A) ─────────────────────────────────────
    yield SSEChunk(emotion="listen", text="")

    try:
        draft = await _infer("adp_a", messages, system=NIKKO_SYSTEM)
    except Exception as exc:
        import logging
        logging.getLogger("nikko").warning(f"ADP-A failed: {exc}")
        # Warm holding response -- better than silence.
        draft = (
            "I'm here with you. It sounds like there's a lot on your mind — "
            "would you like to share a bit more about what's been going on?"
        )

    # ── Stage 3: Evaluate draft (ADP-C) ───────────────────────────────────────
    eval_messages = [
        {"role": "user",      "content": f"User message: {user_msg}"},
        {"role": "assistant", "content": f"Proposed response: {draft}"},
    ]
    yield SSEChunk(emotion="think", text="")

    try:
        eval_raw = await _infer("adp_c", eval_messages, system=EVAL_SYSTEM)
        verdict  = _parse_json_verdict(eval_raw).get("verdict", "APPROVE")
    except Exception as exc:
        import logging
        logging.getLogger("nikko").warning(f"ADP-C failed: {exc}")
        verdict = "APPROVE"  # fail open -- surface the ADP-A draft as-is

    if verdict == "REGENERATE":
        regen_messages = messages + [
            {"role": "assistant", "content": draft},
            {"role": "user",      "content": "Please try a different, more empathetic approach."},
        ]
        try:
            draft = await _infer("adp_a", regen_messages, system=NIKKO_SYSTEM)
            eval2_raw = await _infer("adp_c", [
                {"role": "user",      "content": f"User message: {user_msg}"},
                {"role": "assistant", "content": f"Proposed response: {draft}"},
            ], system=EVAL_SYSTEM)
            verdict2 = _parse_json_verdict(eval2_raw).get("verdict", "APPROVE")
        except Exception:
            verdict2 = "APPROVE"

        if verdict2 == "REGENERATE":
            draft = (
                "I want to make sure I'm being as helpful as possible. "
                "Could you tell me a little more about what's on your mind?"
            )

    yield SSEChunk(text=draft, emotion="speak", safetyFlags=flags)

# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

async def _sse_stream(msg_id: str, gen: AsyncGenerator) -> AsyncGenerator[str, None]:
    yield _sse("message_start", {"id": msg_id, "emotion": "listen"})
    async for chunk in gen:
        yield _sse("chunk", chunk.model_dump())
    yield _sse("message_end", {"id": msg_id})

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """REQ-600-HL1: Fly.io platform probe + loading screen poll (REQ-FIS-LS2)."""
    space_ok = False
    if HF_SPACE_URL:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{HF_SPACE_URL}/health")
                space_ok = r.status_code == 200
        except Exception:
            pass
    return {
        "status":    "ok",
        "version":   "0.1.0",
        "space_ok":  space_ok,
        "ts":        int(time.time()),
    }

@app.post("/api/message")
async def message(body: MessageRequest):
    """REQ-FIS-001: Primary chat endpoint -- streams SSE to the frontend."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    msg_id = f"msg-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
    return StreamingResponse(
        _sse_stream(msg_id, _pipeline(body)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.post("/api/message/mock")
async def message_mock(body: MessageRequest):
    """REQ-FIS-TS1: Hardcoded fixture -- frontend testing without live agents."""
    msg_id = f"mock-{int(time.time()*1000)}"

    async def _mock():
        await asyncio.sleep(0.3)
        yield SSEChunk(text="This is a mock response. ", emotion="listen")
        await asyncio.sleep(0.2)
        yield SSEChunk(text="Pipeline is not active.", emotion="speak")

    return StreamingResponse(
        _sse_stream(msg_id, _mock()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
