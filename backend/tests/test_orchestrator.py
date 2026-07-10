"""Offline orchestrator-loop test with a fake AsyncAnthropic client + seed cache hit."""

import asyncio
import json

import app.agent.orchestrator as orch
from app.agent.research_tools import clear_research_cache, run_research_tool


# --- fake Anthropic client -------------------------------------------------
class _Blk:
    def __init__(self, type, name=None, input=None, id=None, text=None):
        self.type = type
        self.name = name
        self.input = input or {}
        self.id = id
        self.text = text


class _Msg:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = None


class _Stream:
    def __init__(self, msg):
        self._msg = msg

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def get_final_message(self):
        return self._msg


class _Messages:
    def __init__(self, script, guideline_text):
        self._script = list(script)
        self._i = 0
        self._g = guideline_text

    def stream(self, **kw):
        msg = self._script[self._i]
        self._i += 1
        return _Stream(msg)

    async def create(self, **kw):
        return _Msg([_Blk("text", text=self._g)], "end_turn")


class _Client:
    def __init__(self, script, guideline_text):
        self.messages = _Messages(script, guideline_text)
        self.beta = self  # beta.messages.stream unused (no MCP in this test)


def test_fetch_drug_pk_seed_cache_no_network():
    clear_research_cache()
    r = asyncio.run(run_research_tool("fetch_drug_pk", {"drug_name": "Vancomycin"}))
    assert r["found"] is True
    assert r["source"] == "seed_cache"
    assert r["structured_pk"]["adult_clearance_l_per_h"] == 4.5


def test_orchestrator_loop_submits_with_self_critique(monkeypatch):
    extrapolate = _Blk(
        "tool_use", name="extrapolate_dose", id="t1",
        input={
            "adult_clearance_l_per_h": 4.5, "adult_volume_l": 49.0, "adult_protein_binding": 0.5,
            "weight_kg": 3.2, "pma_weeks": 40.3,
            "pathways": [{"name": "renal_GFR", "fm": 0.85}, {"name": "hepatic_other", "fm": 0.15}],
            "method": "css", "method_params": {"css_target_mg_per_l": 15, "interval_h": 12},
        },
    )
    submit = _Blk(
        "tool_use", name="submit_recommendation", id="t2",
        input={
            "drug_name": "Vancomycin",
            "dose_recommendation": {"dose_mg": 40.0, "dose_mg_per_kg": 12.5, "method": "css"},
            "rationale": "Renally cleared; GFR immature at 40 wk PMA so clearance is reduced.",
            "evidence_grade": {"grade": "low", "rationale": "sparse neonatal PK"},
            "critique": {"objections": ["NTI drug — needs TDM"], "dose_grade": "accept_with_caveats",
                         "residual_risks": ["nephrotoxicity"]},
            "source_of_dose": "mechanistic",
        },
    )
    script = [_Msg([extrapolate], "tool_use"), _Msg([submit], "tool_use")]
    fake = _Client(script, guideline_text=json.dumps({"guideline_cases": [], "note": "none"}))
    monkeypatch.setattr(orch, "_get_client", lambda: fake)
    clear_research_cache()

    events = []
    payload, cost, msgs = asyncio.run(orch.run_orchestrator(
        "vancomycin in a 2-day-old term neonate 3.2 kg", on_event=lambda ev: events.append(ev)))

    assert payload is not None
    assert payload["drug_name"] == "Vancomycin"
    assert payload["critique"]["dose_grade"] == "accept_with_caveats"
    assert payload["source_of_dose"] == "mechanistic"
    # the real PK math ran (a dose tool_result was emitted) and named agents show in the trace
    kinds = {e["kind"] for e in events}
    assert "tool" in kinds and "status" in kinds
    assert any("mg" in (e.get("text") or "") for e in events)
    assert any(e["agent"] == "guideline-agent" for e in events)
