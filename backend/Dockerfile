# PaedScale backend image.
#
# The orchestrator now runs entirely in-process on the Anthropic Messages API
# (anthropic Python SDK) — no Claude Code CLI, no Node subprocess. A plain
# Python runtime is all that's needed.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (injected by the platform) is expanded at runtime.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
