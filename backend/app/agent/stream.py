"""Map the Agent SDK message stream into typed reasoning-trace events for the UI.

The right-hand sidebar shows the agents working live. Each SDK message becomes
zero or more compact events: which agent, what kind (status | thinking | tool |
tool_result), and a short human-readable line. Subagent messages are attributed
by matching their `parent_tool_use_id` to the `Task` call that started them.
"""

from __future__ import annotations

# Friendly labels for tools the user sees fly by.
_TOOL_LABELS = {
    "mcp__literature__pubmed_search": "searched PubMed",
    "mcp__literature__semantic_scholar_search": "searched Semantic Scholar",
    "WebSearch": "web search",
    "WebFetch": "fetched a source",
    "mcp__paedscale_math__list_pathways": "loaded the maturation curve library",
    "mcp__paedscale_math__extrapolate_dose": "computed the dose (allometry × maturation × organ fn)",
    "mcp__paedscale_math__check_safety_bounds": "checked the safe/effective bounds",
    "mcp__paedscale_math__find_concordance": "compared against guideline (concordance)",
    "mcp__result__submit_recommendation": "assembled the final recommendation",
    "Task": "delegated to a specialist subagent",
}

# Map an SDK Task task_type / description to a clean agent label.
_AGENT_LABELS = {
    "pathway-agent": "pathway-agent",
    "pk-agent": "pk-agent",
    "safety-agent": "safety-agent",
    "critic-agent": "critic-agent",
}


def _blocks(msg):
    c = getattr(msg, "content", None)
    return c if isinstance(c, list) else []


def _short(text: str, n: int = 220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _tool_line(name: str, tool_input) -> str:
    label = _TOOL_LABELS.get(name, name)
    if isinstance(tool_input, dict):
        q = tool_input.get("query")
        if q:
            return f"{label}: “{_short(str(q), 80)}”"
    return label


class TraceMapper:
    """Stateful mapper — tracks which Task tool_use_id belongs to which subagent."""

    def __init__(self) -> None:
        self._agent_by_tool: dict[str, str] = {}

    def _agent_of(self, msg) -> str:
        parent = getattr(msg, "parent_tool_use_id", None)
        if parent and parent in self._agent_by_tool:
            return self._agent_by_tool[parent]
        return "orchestrator"

    def events(self, msg) -> list[dict]:
        t = type(msg).__name__
        out: list[dict] = []

        if t == "TaskStartedMessage":
            raw = getattr(msg, "task_type", None) or getattr(msg, "description", "") or "subagent"
            label = _AGENT_LABELS.get(raw, raw)
            tuid = getattr(msg, "tool_use_id", None)
            if tuid:
                self._agent_by_tool[tuid] = label
            return [{"agent": label, "kind": "status", "text": f"{label} started"}]

        if t == "AssistantMessage":
            agent = self._agent_of(msg)
            for b in _blocks(msg):
                bt = type(b).__name__
                if bt == "TextBlock" and b.text.strip():
                    out.append({"agent": agent, "kind": "thinking", "text": _short(b.text)})
                elif bt == "ThinkingBlock" and (getattr(b, "thinking", "") or "").strip():
                    out.append({"agent": agent, "kind": "thinking", "text": _short(b.thinking)})
                elif bt in ("ToolUseBlock", "ServerToolUseBlock"):
                    out.append({
                        "agent": agent,
                        "kind": "tool",
                        "tool": getattr(b, "name", ""),
                        "text": _tool_line(getattr(b, "name", ""), getattr(b, "input", None)),
                    })
            return out

        if t == "UserMessage":
            agent = self._agent_of(msg)
            for b in _blocks(msg):
                if type(b).__name__ in ("ToolResultBlock", "ServerToolResultBlock"):
                    if getattr(b, "is_error", False):
                        out.append({"agent": agent, "kind": "tool_result", "text": "a tool returned an error"})
            return out

        if t == "ResultMessage":
            cost = getattr(msg, "total_cost_usd", None)
            text = "run complete" + (f" (${cost:.3f})" if cost else "")
            return [{"agent": "orchestrator", "kind": "status", "text": text}]

        return out
