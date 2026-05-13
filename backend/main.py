"""
backend/main.py -- Nikko orchestration API (Phase 7 skeleton).

Exposes the three endpoints contracted in FRONTEND_INTEGRATION_SPEC.md:
  GET  /health          -- Fly.io health probe; loading screen polls this.
  POST /api/message     -- Primary chat endpoint; streams SSE chunks.
  POST /api/message/mock -- Hardcoded streaming fixture for frontend testing.

All agent logic (LangGraph orchestration, ADP adapters, evidence retrieval)
slots in through the _pipeline() placeholder in this file. Nothing else in
web/ or the test harness needs to change when the pipeline is wired up.

[CONCEPT] Server-Sent Events (SSE): a one-way HTTP streaming protocol where
the server pushes newline-delimited "event: ...\ndata: ...\n\n" frames over
a single persistent connection. The browser's EventSource API (or a fetch
reader) consumes them. FastAPI's StreamingResponse + an async generator
makes this straightforward -- see _sse_stream() below.
"""

import asyncio
import json
import os
import time
import uuid
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ── App initialisation ────────────────────────────────────────────────────────

app = FastAPI(
    title="Nikko Backend API",
    version="0.1.0",
    description="Orchestration layer for the Nikko wellbeing assistant (research preview).",
    # Disable auto-generated /docs in production; re-enable for local dev.
    docs_url="/docs" if os.getenv("NIKKO_ENV", "production") == "development" else None,
    redoc_url=None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# [CONCEPT] CORS (Cross-Origin Resource Sharing): browsers block JS from
# calling APIs on a different origin unless the server explicitly allows it.
# The GitHub Pages origin must be in this list, or every /api/message call
# from the frontend will be rejected before it even reaches FastAPI.
_ALLOWED_ORIGINS = [
    "https://equinox013.github.io",   # production -- GitHub Pages
    "http://localhost:8000",          # local dev (serve.bat equivalent)
    "http://localhost:3000",          # alternative local dev port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)

# ── Request / response models ─────────────────────────────────────────────────
# These mirror the shapes defined in FRONTEND_INTEGRATION_SPEC.md §2.

class MoodSnapshot(BaseModel):
    """Optional mood data captured by the frontend mood diary (SPEC-800)."""
    selfReport: int | None = Field(None, ge=1, le=5)
    dominantEmotion: str | None = None

class MessageRequest(BaseModel):
    """
    POST /api/message request body.
    See FRONTEND_INTEGRATION_SPEC.md §2 -- Request.
    """
    text: str = Field(..., min_length=1, max_length=4000)
    contextId: str | None = Field(None, description="Session context ID for multi-turn memory.")
    userId: str | None = Field(None, description="Opaque client-side ID; never a real identity.")
    moodSnapshot: MoodSnapshot | None = None

class SSEChunk(BaseModel):
    """
    A single SSE data payload.
    See FRONTEND_INTEGRATION_SPEC.md §2 -- Response.
    """
    text: str = ""
    # [CONCEPT] Emotion states drive the avatar glyph in avatar.jsx.
    # The full set is defined in docs/GLOSSARY.md. The backend selects the
    # appropriate state based on what the agent pipeline is currently doing.
    emotion: str = "calm"   # calm | listen | search | speak | care | think
    sourcesUsed: list[str] = Field(default_factory=list)
    safetyFlags: list[str] = Field(default_factory=list)

# ── SSE helpers ───────────────────────────────────────────────────────────────

def _sse_event(event: str, data: dict) -> str:
    """
    Formats a single SSE frame.
    The double newline at the end is required by the SSE spec -- it signals
    the end of one event so the browser knows to dispatch it.
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

async def _sse_stream(msg_id: str, gen: AsyncGenerator) -> AsyncGenerator[str, None]:
    """
    Wraps an async chunk generator with the required message_start /
    message_end envelope defined in FRONTEND_INTEGRATION_SPEC.md §2.
    """
    # Opening frame -- frontend uses msg_id to deduplicate streamed messages.
    yield _sse_event("message_start", {"id": msg_id, "emotion": "listen"})

    async for chunk in gen:
        yield _sse_event("chunk", chunk.model_dump())

    # Closing frame -- frontend stops the spinner and locks the message.
    yield _sse_event("message_end", {"id": msg_id})

# ── Agent pipeline placeholder ────────────────────────────────────────────────

async def _pipeline(request: MessageRequest) -> AsyncGenerator[SSEChunk, None]:
    """
    PLACEHOLDER -- replace with LangGraph orchestration in Phase 5.

    In production this function:
      1. Forwards `request.text` to the Crisis Detection Agent (ADP-B).
      2. Routes through the SPEC-200 Router.
      3. Calls the CBT Support Agent (ADP-A) or Crisis Response flow (SPEC-300).
      4. Streams annotated chunks back with emotion + sourcesUsed.

    For now it yields a single holding response so the frontend can be tested
    end-to-end against a real HTTP connection without live agents.
    """
    # Simulate agent think time so the loading avatar state is visible.
    await asyncio.sleep(0.4)

    # [CONCEPT] `yield` inside an async def turns this into an async generator.
    # Each yield sends one SSE chunk downstream without blocking the event loop.
    yield SSEChunk(
        text="Hey, I'm here. The full agent pipeline isn't wired up yet -- "
             "this is the Phase 7 infrastructure skeleton talking.",
        emotion="speak",
    )

# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """
    REQ-600-HL1: Health probe consumed by the Fly.io platform and the
    Nikko loading screen (REQ-FIS-LS2). Must return 200 with a JSON body.
    The loading screen polls this at 3-second intervals until it gets a 200,
    then transitions into the Gate component (REQ-FIS-LS9).
    """
    return {"status": "ok", "version": "0.1.0", "ts": int(time.time())}


@app.post("/api/message")
async def message(body: MessageRequest):
    """
    REQ-FIS-001 (FRONTEND_INTEGRATION_SPEC §2): Primary chat endpoint.
    Accepts a user message and streams a Server-Sent Events response.

    The frontend sends here on every user submission; the loading screen
    must have already cleared (backend gate passed) before this is called.
    """
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    msg_id = f"msg-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"

    return StreamingResponse(
        # [CONCEPT] _sse_stream() wraps the pipeline generator with the
        # message_start / message_end envelope the frontend expects.
        _sse_stream(msg_id, _pipeline(body)),
        media_type="text/event-stream",
        headers={
            # Prevents proxies / CDNs from buffering the stream.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/message/mock")
async def message_mock(body: MessageRequest):
    """
    REQ-FIS-TS1 (FRONTEND_INTEGRATION_SPEC §9): Hardcoded fixture endpoint
    for frontend integration testing. Returns the same SSE shape as the live
    endpoint but with deterministic content -- no agents, no LLM calls.

    Useful when iterating on the frontend without a running model.
    """
    msg_id = f"mock-{int(time.time() * 1000)}"

    async def _mock_gen():
        await asyncio.sleep(0.3)
        yield SSEChunk(text="This is a mock response from Nikko. ", emotion="listen")
        await asyncio.sleep(0.2)
        yield SSEChunk(text="The agent pipeline is not active.", emotion="speak")
        await asyncio.sleep(0.1)
        yield SSEChunk(
            text=" Here is a cited chunk.",
            emotion="search",
            sourcesUsed=["s_sleep"],
        )

    return StreamingResponse(
        _sse_stream(msg_id, _mock_gen()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
