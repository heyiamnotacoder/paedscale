"""Partial-result recovery when submit_recommendation never ran."""

import json

from app.agent.orchestrator import BUDGET_USD, DISALLOWED_TOOLS, ORCHESTRATOR_SYSTEM, SUBAGENTS
from app.agent.recovery import assemble_partial_payload, extract_math_results


class ToolUseBlock:
    def __init__(self, id, name, input=None):
        self.id = id
        self.name = name
        self.input = input or {}


class ToolResultBlock:
    def __init__(self, tool_use_id, content, is_error=False, name=None):
        self.tool_use_id = tool_use_id
        self.content = content
        self.is_error = is_error
        self.name = name


class AssistantMessage:
    def __init__(self, content):
        self.content = content


class UserMessage:
    def __init__(self, content):
        self.content = content


def _math_result_messages():
    dose_payload = {
        "child_clearance_l_per_h": 0.42,
        "child_volume_l": 1.8,
        "maturation_fraction": 0.55,
        "resolved_pathways": [
            {"name": "renal_GFR", "fm": 0.7, "organ": "renal", "tm50_weeks": 48, "hill": 3.3},
            {"name": "hepatic_other", "fm": 0.3, "organ": "hepatic", "tm50_weeks": 40, "hill": 1.0},
        ],
        "dose": {
            "dose_mg": 45.0,
            "dose_mg_per_kg": 7.5,
            "interval_h": 8.0,
            "method": "auc",
            "matched_metric": "AUC over dosing interval (steady state)",
        },
    }
    safety_payload = {
        "min_effective_mg_per_kg": 5.0,
        "max_safe_mg_per_kg": 15.0,
        "within": True,
        "clamped_mg_per_kg": 7.5,
        "flag": None,
    }
    return [
        AssistantMessage([
            ToolUseBlock("u1", "mcp__paedscale_math__extrapolate_dose", {}),
        ]),
        UserMessage([
            ToolResultBlock("u1", json.dumps(dose_payload)),
        ]),
        AssistantMessage([
            ToolUseBlock("u2", "mcp__paedscale_math__check_safety_bounds", {}),
        ]),
        UserMessage([
            ToolResultBlock("u2", json.dumps(safety_payload)),
        ]),
    ]


def test_extract_math_results_pairs_tool_use_and_result():
    msgs = _math_result_messages()
    last = extract_math_results(msgs)
    assert "extrapolate_dose" in last
    assert last["extrapolate_dose"]["dose"]["dose_mg_per_kg"] == 7.5
    assert last["check_safety_bounds"]["within"] is True


def test_assemble_partial_payload_builds_recommendation():
    payload = assemble_partial_payload(_math_result_messages(), query="amoxicillin 1 year old 6 kg")
    assert payload is not None
    assert payload["source_of_dose"] == "partial_recovery"
    assert payload["dose_recommendation"]["dose_mg"] == 45.0
    assert payload["dose_recommendation"]["dose_mg_per_kg"] == 7.5
    assert "assembled_from_partial_run" in payload["safety_flags"]
    assert payload["evidence_grade"]["grade"] == "very-low"
    assert len(payload["pathways"]) == 2
    assert payload["drug_name"].lower().startswith("amoxicillin") or payload["drug_name"] == "Amoxicillin"


def test_assemble_partial_payload_none_without_math():
    assert assemble_partial_payload([], query="x") is None


def test_budget_default_is_two_dollars():
    assert BUDGET_USD >= 2.0


def test_subagents_are_synchronous_research_and_critic():
    assert set(SUBAGENTS.keys()) == {"research-agent", "critic-agent"}
    for ag in SUBAGENTS.values():
        assert ag.background is False
    assert SUBAGENTS["critic-agent"].tools == []
    assert SUBAGENTS["critic-agent"].maxTurns == 1


def test_async_team_tools_disallowed():
    for name in ("ScheduleWakeup", "TaskOutput", "SendMessage", "ToolSearch"):
        assert name in DISALLOWED_TOOLS


def test_prompt_blocks_guideline_when_organ_impaired():
    assert "NEVER use the guideline short path" in ORCHESTRATOR_SYSTEM or \
        "Never use the guideline short path" in ORCHESTRATOR_SYSTEM
    assert "organ_impaired" in ORCHESTRATOR_SYSTEM or "ORGAN IMPAIRMENT" in ORCHESTRATOR_SYSTEM
    assert "critic-agent" in ORCHESTRATOR_SYSTEM
    assert "research-agent" in ORCHESTRATOR_SYSTEM
    assert "ToolSearch" in ORCHESTRATOR_SYSTEM  # instructed not to use


def test_prompt_requires_critic_before_submit():
    assert "CRITIC (mandatory" in ORCHESTRATOR_SYSTEM or "mandatory critic" in ORCHESTRATOR_SYSTEM.lower()
    assert "dose_grade" in ORCHESTRATOR_SYSTEM
