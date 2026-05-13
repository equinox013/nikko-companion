# Nikko backend -- Docker image for Fly.io deployment.
# Base: python:3.11-slim (small footprint, no CUDA -- inference is on HF Spaces).
# [CONCEPT] Multi-stage builds keep the final image lean by separating the
# "install deps" stage from the "run app" stage. We use a single stage here
# because the dep set is small; revisit if the image exceeds ~500 MB.

FROM python:3.11-slim

# Prevent .pyc files and enable unbuffered stdout (essential for Fly.io log streaming).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NIKKO_ENV=production

WORKDIR /app

# Install deps first (separate layer -- cached by Docker unless requirements.txt changes).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source.
COPY . .

# Fly.io expects the app to listen on 0.0.0.0:8080 by default.
EXPOSE 8080

# [CONCEPT] uvicorn is the ASGI server that runs the FastAPI app.
# --workers 1: single worker is fine for a stateless API on a 256 MB Fly micro-VM.
# --loop uvloop: faster async event loop (included via uvicorn[standard]).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--loop", "uvloop"]
