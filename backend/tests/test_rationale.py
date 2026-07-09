"""synthesize_rationale must tolerate the model omitting a 'required' tool
field — Anthropic's tool-use schema 'required' is advisory, not enforced, and
a live run surfaced exactly this: Claude returned a dict missing
uncertainty_flags/narrow_therapeutic_index_warning/concordance_summary, which
crashed pydantic validation downstream in main.py before this fix.
"""

from unittest.mock import patch

from app.agent.rationale import synthesize_rationale


def test_synthesize_rationale_fills_missing_optional_fields():
    with patch("app.agent.rationale.call_structured", return_value={"rationale": "some text"}):
        result = synthesize_rationale({"drug": "vancomycin"})

    assert result["rationale"] == "some text"
    assert result["assumptions"] == []
    assert result["uncertainty_flags"] == []
    assert result["narrow_therapeutic_index_warning"] == ""
    assert result["concordance_summary"] == ""


def test_synthesize_rationale_fills_missing_rationale_field():
    # 'rationale' is a required RationaleOut field too; if the model omits it,
    # we must still return a valid dict rather than let main.py 500.
    with patch("app.agent.rationale.call_structured", return_value={"assumptions": ["a1"]}):
        result = synthesize_rationale({"drug": "vancomycin"})

    assert result["rationale"] == ""
    assert result["assumptions"] == ["a1"]
    assert result["uncertainty_flags"] == []
    assert result["narrow_therapeutic_index_warning"] == ""
    assert result["concordance_summary"] == ""


def test_synthesize_rationale_preserves_all_present_fields():
    full_response = {
        "rationale": "text",
        "assumptions": ["a1"],
        "uncertainty_flags": ["u1"],
        "narrow_therapeutic_index_warning": "confirm with TDM",
        "concordance_summary": "concordant",
    }
    with patch("app.agent.rationale.call_structured", return_value=dict(full_response)):
        result = synthesize_rationale({"drug": "morphine"})

    assert result == full_response
