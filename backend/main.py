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

# Timeout for the /pipeline call to HF Space.
# Cold start (first call after Space rebuild): ~120s model load + inference.
# Warm (subsequent calls, GPU context warm): ~30-60s for 3 adapter passes.
# Regen pass adds another ~20-30s. 360s gives comfortable headroom.
PIPELINE_TIMEOUT_S = 360

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
    text:        str        = ""
    emotion:     str        = "calm"
    sourcesUsed: list[str]  = Field(default_factory=list)
    safetyFlags: list[str]  = Field(default_factory=list)
    trace:       dict | None = None   # pipeline trace for debug panel

# ── HF Space client ───────────────────────────────────────────────────────────

async def _call_pipeline(messages: list[dict]) -> dict:
    """
    Calls POST /pipeline on the HF Space -- runs ADP-B → ADP-A → ADP-C in
    a single ZeroGPU GPU session, returning the full pipeline result.

    [CONCEPT] httpx.AsyncClient doesn't block the FastAPI event loop while
    waiting for the GPU. /health probes and other requests are served normally
    during the (potentially long) pipeline wait.
    """
    if not HF_SPACE_URL:
        raise RuntimeError("HF_SPACE_URL env var not set. Run: fly secrets set HF_SPACE_URL=...")

    payload = {
        "messages":      messages,
        "system":        NIKKO_SYSTEM,
        "safety_system": SAFETY_SYSTEM,
        "eval_system":   EVAL_SYSTEM,
        "token":         INTERNAL_TOKEN,
    }

    async with httpx.AsyncClient(timeout=PIPELINE_TIMEOUT_S) as client:
        resp = await client.post(f"{HF_SPACE_URL}/pipeline", json=payload)
        resp.raise_for_status()
        return resp.json()

# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _pipeline(request: MessageRequest) -> AsyncGenerator[SSEChunk, None]:
    """
    Single-call pipeline per SPEC-200 and SPEC-300.

    Sends one POST /pipeline to the HF Space which runs ADP-B → ADP-A → ADP-C
    (+ optional regen) inside a single @spaces.GPU context. This eliminates
    the 80-110s CPU→VRAM overhead that was incurred per adapter when using
    three separate /infer calls.

    Graceful degradation: if the HF Space call fails entirely, a warm holding
    response is emitted so the frontend always receives text.
    """
    user_msg = request.text.strip()
    messages = [{"role": "user", "content": user_msg}]

    # Signal "thinking" while the pipeline runs (~30-120s depending on warm/cold).
    yield SSEChunk(emotion="think", text="")

    try:
        result    = await _call_pipeline(messages)
        is_crisis = result.get("is_crisis", False)
        flags     = result.get("flags", [])
        text      = result.get("text", "")
    except Exception as exc:
        import logging
        logging.getLogger("nikko").warning(f"Pipeline failed: {exc}")
        # Full pipeline down -- emit a warm holding response.
        yield SSEChunk(
            text=(
                "I'm here with you. It sounds like there's a lot on your mind — "
                "would you like to share a bit more about what's been going on?"
            ),
            emotion="speak",
        )
        return

    # [REQ-300-161] Crisis path -- pipeline sets is_crisis=True, text is empty.
    if is_crisis:
        yield SSEChunk(
            text=CRISIS_RESPONSE,
            emotion="care",
            safetyFlags=flags or ["crisis_detected"],
        )
        return

    if not text:
        text = (
            "I want to make sure I'm being as helpful as possible. "
            "Could you tell me a little more about what's on your mind?"
        )

    # Build a trace payload for the debug panel so the user can see
    # adapter activity without checking HF/Render logs.
    trace = {
        "is_crisis": is_crisis,
        "flags":     flags,
        "verdict":   result.get("verdict", "APPROVE"),
        "regen":     result.get("regen", False),
        "elapsed":   result.get("elapsed", 0),
        "adp_b": {
            "label":   "Safety / crisis check",
            "verdict": "CRISIS" if is_crisis else "CLEAR",
            "flags":   flags,
        },
        "adp_a": {
            "label": "Empathy response draft",
            "chars": len(text),
        },
        "adp_c": {
            "label":   "Quality gate (evaluator)",
            "verdict": result.get("verdict", "APPROVE"),
            "regen":   result.get("regen", False),
        },
    }

    yield SSEChunk(text=text, emotion="speak", safetyFlags=flags, trace=trace)

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
