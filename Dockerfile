# Nikko backend — Dockerfile (repo-root build context, Phase 7 MVP).
#
# Build context MUST be the repo root so Docker can reach the agent packages.
# Deploy command: `fly deploy` from D:\Git Repos\nikko-companion\
#
# [CONCEPT] The inference models (Qwen3-4B, Gemma-2-2b-it) live on HF Spaces
# ZeroGPU. This container has NO GPU and NO model weights — it only runs the
# orchestration layer (NikkoPipeline agents + RAG retrieval) and bridges to
# HF Space via HTTP. This keeps the Fly.io image lean (~200 MB vs ~10+ GB).
#
# Runtime module graph (everything below must land in /app):
#   backend/      ← FastAPI app, HFSpaceFullGenerator, context_prompt_builder
#   orchestration/← NikkoPipeline + all SPEC-700 step logic
#   agents/       ← SignalAgent, Router, Synthesizer, Evaluator, VS, etc.
#   retrieval/    ← PubMedAdapter, WebSearchAdapter, base adapters
#   docs/schemas/ ← ACP schemas (acp_schemas.py, retrieval_schemas.py, validate.py)
#
# [CONCEPT] Multi-stage builds are skipped here — dep set is small and the
# app is CPU-only. Revisit if the image exceeds 500 MB.

FROM python:3.11-slim

# Prevent .pyc files; unbuffered stdout is required for Fly.io log streaming.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NIKKO_ENV=production

WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────────────
# Copied first as a separate layer — Docker cache invalidates only if
# requirements.txt changes, not on every source edit.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy runtime packages ─────────────────────────────────────────────────────
# Only the packages actually imported at runtime are copied. Training notebooks,
# finetuning data, hf_space/, web/, docs/specs/ etc. are excluded via
# .dockerignore to keep the image small and the build context fast.
COPY backend/       ./backend/
COPY orchestration/ ./orchestration/
COPY agents/        ./agents/
COPY retrieval/     ./retrieval/
COPY docs/schemas/  ./docs/schemas/

# ── Runtime ───────────────────────────────────────────────────────────────────
# Fly.io expects the app on 0.0.0.0:8080.
# [CONCEPT] Module path is `backend.main:app` (not `main:app`) because WORKDIR
# is the repo root — `backend` is a sub-package, not the working directory.
# --workers 1: stateless API on a 256 MB Fly micro-VM; single worker is fine.
# --loop uvloop: faster async event loop (bundled with uvicorn[standard]).
EXPOSE 8080
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--loop", "uvloop"]
