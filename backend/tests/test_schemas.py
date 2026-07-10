"""Unit tests for lenient ExtrapolationResponse parsing (LLM tool-arg shape quirks)."""

import json

from app.schemas import (
    ExtrapolationResponse,
    assemble_lenient_response,
    coerce_critique,
    normalize_submit_payload,
    parse_jsonish,
)


def test_parse_jsonish_object_and_array():
    assert parse_jsonish('{"a": 1}') == {"a": 1}
    assert parse_jsonish("[1, 2]") == [1, 2]
    assert parse_jsonish("plain text") == "plain text"
    assert parse_jsonish({"already": "dict"}) == {"already": "dict"}


def test_parse_jsonish_python_style_single_quotes():
    assert parse_jsonish("{'objections': ['x'], 'dose_grade': 'accept'}") == {
        "objections": ["x"],
        "dose_grade": "accept",
    }


def test_normalize_submit_payload_coerces_critique_string():
    raw = {
        "drug_name": "Paracetamol",
        "critique": json.dumps({
            "objections": ["Guideline may not fit"],
            "dose_grade": "accept_with_caveats",
            "resolution": "effective dose needed.",
        }),
        "dose_recommendation": json.dumps({"dose_mg": 120.0, "dose_mg_per_kg": 15.0}),
    }
    out = normalize_submit_payload(raw)
    assert isinstance(out["critique"], dict)
    assert out["critique"]["dose_grade"] == "accept_with_caveats"
    assert out["dose_recommendation"]["dose_mg"] == 120.0


def test_extrapolation_response_accepts_stringified_nested_fields():
    """Mirrors production 502: critique arrived as str, not CritiqueOut dict."""
    data = {
        "query": "Paracetamol dosage for 2 year old with weight of 8 kg",
        "drug_name": "Paracetamol",
        "dose_recommendation": {
            "dose_mg": 120.0,
            "dose_mg_per_kg": 15.0,
            "interval_h": 6.0,
            "method": "guideline",
        },
        "evidence_grade": {"grade": "moderate", "rationale": "BNFC-style oral dose"},
        "rationale": "Published pediatric paracetamol dosing for age/weight.",
        "critique": (
            '{"objections": ["Guideline band may not match exact weight"], '
            '"dose_grade": "accept_with_caveats", '
            '"resolution": "Converted published mg/kg; effective dose needed.", '
            '"residual_risks": []}'
        ),
        "disclaimer": "Decision support only",
    }
    resp = ExtrapolationResponse.model_validate(data)
    assert resp.critique.dose_grade == "accept_with_caveats"
    assert "Guideline" in resp.critique.objections[0]
    assert resp.dose_recommendation.dose_mg == 120.0


def test_coerce_critique_garbage_string_preserves_text():
    out = coerce_critique("not a dict at all — monitoring protocol.")
    assert isinstance(out, dict)
    assert "monitoring protocol" in out["resolution"]
    assert out["dose_grade"] == "accept_with_caveats"


def test_assemble_lenient_response_single_quoted_critique():
    data = {
        "query": "gentamicin 2yo 7kg",
        "drug_name": "Gentamicin",
        "dose_recommendation": {
            "dose_mg": 14.0,
            "dose_mg_per_kg": 2.0,
            "interval_h": 8.0,
            "method": "auc",
        },
        "rationale": "Mechanistic dose with TDM flag.",
        "critique": (
            "{'objections': ['Guideline vs mechanistic discrepancy'], "
            "'dose_grade': 'accept_with_caveats', "
            "'resolution': 'TDM monitoring protocol.'}"
        ),
        "disclaimer": "Decision support only",
    }
    resp = assemble_lenient_response(data)
    assert resp.dose_recommendation.dose_mg == 14.0
    assert resp.critique.dose_grade == "accept_with_caveats"
    assert any("discrepancy" in o for o in resp.critique.objections)


def test_assemble_lenient_response_garbage_critique_still_returns_dose():
    data = {
        "query": "paracetamol 2yo 8kg",
        "drug_name": "Paracetamol",
        "dose_recommendation": {
            "dose_mg": 120.0,
            "dose_mg_per_kg": 15.0,
            "interval_h": 6.0,
            "method": "guideline",
        },
        "rationale": "Guideline path.",
        "critique": "<<<totally broken>>>",
        "disclaimer": "x",
    }
    resp = assemble_lenient_response(data)
    assert resp.dose_recommendation.dose_mg == 120.0
    assert "broken" in resp.critique.resolution
