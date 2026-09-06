"""Compulsory HI gate + calculator toggle (issue #4). No API key."""

from __future__ import annotations

from engine.child_pugh import (
    CHILD_PUGH_ON_CHILD_FLAG,
    HI_GATE_INCOMPLETE,
    hi_gate_error,
    hi_resolution_required,
    resolve_calculator_mode,
    resolve_child_pugh,
)


def _base(**kw):
    case = {
        "drug": "vancomycin",
        "age_years": 6,
        "weight_kg": 20,
        "calculator_mode": "pediatric",
        "hepatic_impairment": False,
    }
    case.update(kw)
    return case


def test_pediatric_healthy_liver_still_submits():
    assert hi_gate_error(_base()) is None
    assert hi_resolution_required(_base()) is False
    print("  hi gate: pediatric + hepatic off  OK")


def test_pediatric_hepatic_requires_class_or_complete_labs():
    assert hi_gate_error(_base(hepatic_impairment=True)) == HI_GATE_INCOMPLETE
    assert hi_gate_error(_base(hepatic_impairment=True, child_pugh="B")) is None
    incomplete_labs = _base(
        hepatic_impairment=True,
        bilirubin_mg_dl=1.2, albumin_g_dl=3.8, inr=1.1,
    )
    assert hi_gate_error(incomplete_labs) == HI_GATE_INCOMPLETE
    complete = _base(
        hepatic_impairment=True,
        bilirubin_mg_dl=1.2, albumin_g_dl=3.8, inr=1.1,
        ascites="none", encephalopathy="none",
    )
    assert hi_gate_error(complete) is None
    print("  hi gate: pediatric + hepatic on  OK")


def test_pbpk_mode_does_not_trip_the_generic_hi_gate():
    """PBPK owns CP-B/C and HI-without-class; the 400 must not fire first."""
    incomplete = _base(calculator_mode="pbpk", hepatic_impairment=True)
    assert hi_gate_error(incomplete) is None
    assert hi_resolution_required(incomplete) is False
    print("  hi gate: pbpk skips generic incomplete-HI 400  OK")


def test_adult_hi_requires_class_even_if_hepatic_box_off():
    assert hi_gate_error(_base(calculator_mode="adult_hi")) == HI_GATE_INCOMPLETE
    assert hi_resolution_required(_base(calculator_mode="adult_hi", hepatic_impairment=False)) is True
    assert hi_gate_error(_base(calculator_mode="adult_hi", child_pugh="A")) is None
    print("  hi gate: adult_hi implies hepatic on  OK")


def test_empty_ascites_is_not_implicit_none():
    case = _base(
        hepatic_impairment=True,
        bilirubin_mg_dl=1.0, albumin_g_dl=4.0, inr=1.0,
        ascites="", encephalopathy="none",
    )
    assert hi_gate_error(case) == HI_GATE_INCOMPLETE
    missing = _base(
        hepatic_impairment=True,
        bilirubin_mg_dl=1.0, albumin_g_dl=4.0, inr=1.0,
        encephalopathy="none",
    )
    assert hi_gate_error(missing) == HI_GATE_INCOMPLETE
    print("  hi gate: no implicit none  OK")


def test_age_does_not_switch_facades():
    child_adult_mode = _base(calculator_mode="adult_hi", age_years=5, child_pugh="B")
    adult_ped_mode = _base(calculator_mode="pediatric", age_years=40, hepatic_impairment=False)
    assert resolve_calculator_mode(child_adult_mode) == "adult_hi"
    assert resolve_calculator_mode(adult_ped_mode) == "pediatric"
    assert hi_gate_error(child_adult_mode) is None
    assert hi_gate_error(adult_ped_mode) is None
    print("  hi gate: age does not switch facades  OK")


def test_normalize_adult_hi_sets_hepatic_and_flags_child_pugh_on_child():
    from agents.agent import _normalize_case, _organ_function_flags

    n = _normalize_case(_base(calculator_mode="adult_hi", child_pugh="B", age_years=10))
    assert n["hepatic_impairment"] is True
    assert n["calculator_mode"] == "adult_hi"
    flags = _organ_function_flags(n)
    assert any(CHILD_PUGH_ON_CHILD_FLAG in f for f in flags), flags
    adult = _normalize_case(_base(calculator_mode="adult_hi", child_pugh="B", age_years=45))
    adult_flags = _organ_function_flags(adult)
    assert not any(CHILD_PUGH_ON_CHILD_FLAG in f for f in adult_flags), adult_flags
    print("  hi gate: Child-Pugh-on-child flag  OK")


def test_resolve_does_not_default_missing_signs():
    entered = resolve_child_pugh({
        "bilirubin_mg_dl": 1.0, "albumin_g_dl": 4.0, "inr": 1.0, "child_pugh": "B",
    })
    assert entered["child_pugh"] == "B" and entered["child_pugh_source"] == "entered"
    calc = resolve_child_pugh({
        "bilirubin_mg_dl": 1.0, "albumin_g_dl": 4.0, "inr": 1.0,
        "ascites": "none", "encephalopathy": "none",
    })
    assert calc["child_pugh"] == "A" and calc["child_pugh_source"] == "calculated"
    print("  hi gate: resolve requires explicit signs  OK")


def test_server_rejects_incomplete_hi():
    from fastapi.testclient import TestClient
    from api.main import app

    c = TestClient(app)
    body = {
        "drug": "vancomycin", "age_years": 6, "weight_kg": 20,
        "hepatic_impairment": True, "calculator_mode": "pediatric",
    }
    r = c.post("/pk", json=body)
    assert r.status_code == 400, r.text
    assert "Child-Pugh" in r.json()["detail"]

    ok_healthy = c.post("/pk", json={
        "drug": "vancomycin", "age_years": 6, "weight_kg": 20,
        "calculator_mode": "pediatric",
    })
    assert ok_healthy.status_code == 200, ok_healthy.text

    adult_incomplete = c.post("/pk", json={
        "drug": "vancomycin", "age_years": 40, "weight_kg": 70,
        "calculator_mode": "adult_hi",
    })
    assert adult_incomplete.status_code == 400, adult_incomplete.text

    adult_ok = c.post("/pk", json={
        "drug": "vancomycin", "age_years": 6, "weight_kg": 20,
        "calculator_mode": "adult_hi", "child_pugh": "B",
    })
    assert adult_ok.status_code == 200, adult_ok.text
    print("  hi gate: server rejects incomplete HI  OK")


if __name__ == "__main__":
    print("HI gate + calculator toggle (issue #4):")
    test_pediatric_healthy_liver_still_submits()
    test_pediatric_hepatic_requires_class_or_complete_labs()
    test_pbpk_mode_does_not_trip_the_generic_hi_gate()
    test_adult_hi_requires_class_even_if_hepatic_box_off()
    test_empty_ascites_is_not_implicit_none()
    test_age_does_not_switch_facades()
    test_normalize_adult_hi_sets_hepatic_and_flags_child_pugh_on_child()
    test_resolve_does_not_default_missing_signs()
    test_server_rejects_incomplete_hi()
    print("All HI-gate tests passed.")
