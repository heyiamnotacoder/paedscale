"""Partial-result recovery + intake parse + orchestrator invariants (all offline)."""

from app.agent import intake
from app.agent.orchestrator import MAX_TURNS, ORCH_MODEL, SUBMIT_TOOL, SYSTEM_PROMPT
from app.agent.recovery import assemble_partial_payload

_MATH_RESULTS = {
    "extrapolate_dose": {
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
    },
    "check_safety_bounds": {
        "min_effective_mg_per_kg": 5.0,
        "max_safe_mg_per_kg": 15.0,
        "within": True,
        "clamped_mg_per_kg": 7.5,
        "flag": None,
    },
}


def test_assemble_partial_payload_builds_recommendation():
    payload = assemble_partial_payload(_MATH_RESULTS, query="amoxicillin 1 year old 6 kg")
    assert payload is not None
    assert payload["source_of_dose"] == "partial_recovery"
    assert payload["dose_recommendation"]["dose_mg"] == 45.0
    assert payload["dose_recommendation"]["dose_mg_per_kg"] == 7.5
    assert "assembled_from_partial_run" in payload["safety_flags"]
    assert payload["evidence_grade"]["grade"] == "very-low"
    assert len(payload["pathways"]) == 2
    assert payload["drug_name"] == "Amoxicillin"


def test_assemble_partial_payload_none_without_math():
    assert assemble_partial_payload({}, query="x") is None


# --- intake -----------------------------------------------------------------

def test_intake_parses_neonate_weight_and_pma():
    r = intake.parse("starting dose of vancomycin in a 2-day-old term neonate, 3.2 kg")
    cov = r["covariates"]
    assert cov["weight_kg"] == 3.2
    assert cov["drug_name"] == "vancomycin"
    assert cov["gestational_age_weeks"] == 40.0
    assert abs(cov["pma_weeks"] - 40.29) < 0.1  # 40 + 2/7
    assert r["edge_case"] is False


def test_intake_flags_organ_impairment_and_edge():
    r = intake.parse("morphine in a 6-month-old, 7 kg, with hepatic impairment (Child-Pugh 8)")
    assert r["organ_impaired"] is True
    assert r["edge_case"] is True
    assert r["covariates"]["child_pugh_score"] == 8


def test_intake_preterm_is_edge_case():
    r = intake.parse("caffeine for a 28-weeker preterm neonate 1.1 kg")
    assert r["edge_case"] is True


# --- orchestrator invariants (no subagents / Node subprocess anymore) -------

def test_orchestrator_uses_messages_api_not_agent_sdk():
    import app.agent.orchestrator as orch
    src = orch.__file__
    with open(src) as f:
        text = f.read()
    assert "ClaudeSDKClient" not in text
    assert "claude_agent_sdk" not in text
    assert "AsyncAnthropic" in text


def test_submit_tool_and_prompt_shape():
    assert SUBMIT_TOOL["name"] == "submit_recommendation"
    assert "critique" in SUBMIT_TOOL["input_schema"]["properties"]
    assert "dose_grade" in SUBMIT_TOOL["input_schema"]["properties"]["critique"]["properties"]
    # organ-impairment gate + golden rule + self-critique in the prompt
    assert "guideline short path" in SYSTEM_PROMPT
    assert "SELF-CRITIQUE" in SYSTEM_PROMPT
    assert "never invent arithmetic" in SYSTEM_PROMPT.lower()
    assert ORCH_MODEL.startswith("claude-sonnet")
    assert MAX_TURNS >= 4
