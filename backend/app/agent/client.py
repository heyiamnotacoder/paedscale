"""Thin Anthropic SDK wrapper. Forces structured (tool-call) output so the
agent layer returns validated JSON, never free text that needs parsing.

All judgment/reasoning happens here and in pathways.py / adult_pk.py /
rationale.py. No pharmacometric arithmetic lives in this module or its
callers — that stays in app.pk (see CLAUDE.md: "keep the LLM and the math
separate").
"""

import os

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5"

_client: Anthropic | None = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Copy backend/.env.example to "
                "backend/.env and add your key."
            )
        _client = Anthropic(api_key=api_key)
    return _client


def call_structured(
    system: str,
    user: str,
    tool_name: str,
    tool_schema: dict,
    max_tokens: int = 1536,
) -> dict:
    """Force a single structured tool-call and return its parsed input dict."""
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[
            {
                "name": tool_name,
                "description": f"Return {tool_name} as structured data matching the schema.",
                "input_schema": tool_schema,
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input
    raise RuntimeError(f"Model did not return the expected '{tool_name}' tool call.")
