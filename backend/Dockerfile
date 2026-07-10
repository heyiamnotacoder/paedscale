# PaedScale backend image.
#
# The Claude Agent SDK drives the Claude Code CLI (a Node binary) as a
# subprocess, so the runtime needs BOTH Python and Node + the CLI on PATH —
# Render's plain Python runtime cannot provide that. This image installs all three.

FROM python:3.12-slim

# Node 20 + the Claude Code CLI that the Agent SDK spawns.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} (injected by the platform) is expanded at runtime.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
