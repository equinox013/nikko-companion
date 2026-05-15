# DEPRECATED — do not use this Dockerfile directly.
#
# As of Phase 7 agent-wiring, the active Dockerfile lives at the repo root:
#   D:\Git Repos\nikko-companion\Dockerfile
#
# Why: backend/main.py now imports from orchestration/, agents/, retrieval/,
# and docs/schemas/ — packages that live outside backend/. The build context
# must be the repo root so Docker can reach them.
#
# Deploy command (from repo root):
#   cd "D:\Git Repos\nikko-companion"
#   fly deploy
#
# Do NOT run `fly deploy` from the backend/ directory — it will use this
# file as context and the container will fail to start with ImportError.
