"""SSE streaming endpoint — offline, with the on_event trace contract."""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from tests.test_api import CANNED_PAYLOAD


@pytest.fixture
def client():
    return TestClient(main_module.app)


def test_stream_endpoint_emits_trace_result_and_done(client, monkeypatch):
    async def fake_run(query, on_event=None, overrides=None):
        if on_event:
            await on_event({"agent": "guideline-agent", "kind": "status", "text": "searching guidelines"})
            await on_event({"agent": "orchestrator", "kind": "tool",
                            "text": "computed the dose", "tool": "extrapolate_dose"})
        return CANNED_PAYLOAD, 0.24, []

    monkeypatch.setattr(main_module, "run_orchestrator", fake_run)
    resp = client.post("/extrapolate/stream", json={"query": "paracetamol neonate"})
    assert resp.status_code == 200
    body = resp.text
    assert "event: trace" in body
    assert "event: result" in body
    assert "event: done" in body
    assert "guideline-agent" in body       # a named parallel agent shows in the trace
    assert "9.09" in body                    # dose_mg_per_kg carried in the result event
