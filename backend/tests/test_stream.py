"""Tests for the reasoning-trace mapper and the SSE streaming endpoint (offline)."""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.agent.stream import TraceMapper
from tests.test_api import CANNED_PAYLOAD


# --- lightweight fakes whose class names match what TraceMapper dispatches on ---
class TextBlock:
    def __init__(self, text): self.text = text


class ToolUseBlock:
    def __init__(self, name, input): self.name = name; self.input = input


class AssistantMessage:
    def __init__(self, content, parent_tool_use_id=None):
        self.content = content; self.parent_tool_use_id = parent_tool_use_id


class TaskStartedMessage:
    def __init__(self, task_type, tool_use_id, description=""):
        self.task_type = task_type; self.tool_use_id = tool_use_id; self.description = description


class ResultMessage:
    def __init__(self, total_cost_usd): self.total_cost_usd = total_cost_usd


def test_mapper_orchestrator_text_and_tool():
    m = TraceMapper()
    evs = m.events(AssistantMessage([TextBlock("Parsing covariates."),
                                     ToolUseBlock("mcp__literature__pubmed_search", {"query": "paracetamol neonate"})]))
    assert evs[0] == {"agent": "orchestrator", "kind": "thinking", "text": "Parsing covariates."}
    assert evs[1]["kind"] == "tool"
    assert "searched PubMed" in evs[1]["text"]


def test_mapper_attributes_subagent_by_parent_tool_id():
    m = TraceMapper()
    started = m.events(TaskStartedMessage("pathway-agent", tool_use_id="tid-1"))
    assert started[0]["agent"] == "pathway-agent"
    evs = m.events(AssistantMessage([TextBlock("fm split: UGT1A1 0.5")], parent_tool_use_id="tid-1"))
    assert evs[0]["agent"] == "pathway-agent"


def test_mapper_result_message_reports_cost():
    evs = TraceMapper().events(ResultMessage(total_cost_usd=0.27))
    assert evs[0]["kind"] == "status"
    assert "0.27" in evs[0]["text"]


@pytest.fixture
def client():
    return TestClient(main_module.app)


def test_stream_endpoint_emits_trace_result_and_done(client, monkeypatch):
    async def fake_run(query, on_message=None):
        # emit a couple of trace-producing messages, then return a payload
        if on_message:
            await on_message(TaskStartedMessage("pk-agent", tool_use_id="t1"))
            await on_message(AssistantMessage([TextBlock("adult CL ~21 L/h")], parent_tool_use_id="t1"))
        return CANNED_PAYLOAD, 0.24, []

    monkeypatch.setattr(main_module, "run_orchestrator", fake_run)
    resp = client.post("/extrapolate/stream", json={"query": "paracetamol neonate"})
    assert resp.status_code == 200
    body = resp.text
    assert "event: trace" in body
    assert "event: result" in body
    assert "event: done" in body
    assert "pk-agent" in body
    assert "9.09" in body  # dose_mg_per_kg carried in the result event
