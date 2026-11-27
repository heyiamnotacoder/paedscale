"""The parameter-uncertainty interval reaches the agent's compute output and the final
recommendation (deterministic; no API key, no network)."""

from agents.agent import _build_compute, _normalize_case, attach_parameter_uncertainty


def _state(**dossier):
    base = {"cl_adult_l_h": 4.0, "vd_adult_l": 50.0, "fm": {"renal_gfr": 0.9},
            "typical_adult_dose_mg_per_day": 2000.0, "target_metric": "auc"}
    base.update(dossier)
    return {"pk_ok": True, "pk_block_reason": None, "blocked_reason": None,
            "last_compute_renal_frac": None, "last_dossier": base}


def _neonate():
    return _normalize_case({"drug": "vancomycin", "age_years": 0.02, "weight_kg": 3.4, "pma_weeks": 41})


def test_compute_output_carries_a_90pct_interval_that_brackets_the_engine_dose():
    state = _state()
    out = _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    assert not out.get("error") and not out.get("blocked"), out
    pu = out["parameter_uncertainty"]
    q = pu["dose_mg_per_kg_per_day"]
    assert pu["level"] == 0.90 and pu["kind"].startswith("parameter-uncertainty")
    assert q["p05"] < out["recommended_dose_mg_per_kg_per_day"] < q["p95"]
    assert state["last_parameter_uncertainty"] == pu


def test_failed_compute_clears_any_earlier_interval():
    state = _state()
    _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    assert state["last_parameter_uncertainty"]
    state["last_dossier"]["fm"] = {"unknown_pathway": 0.9}   # engine refuses to invent a curve
    out = _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    assert "parameter_uncertainty" not in out
    assert state["last_parameter_uncertainty"] is None


def test_recommendation_gets_the_interval_only_when_prescribable():
    state = _state()
    _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    ok = attach_parameter_uncertainty({"blocked": False, "final_dose_mg_per_kg_per_day": 30}, state)
    assert ok["parameter_uncertainty"] == state["last_parameter_uncertainty"]
    stop = attach_parameter_uncertainty({"blocked": True, "final_dose_mg_per_kg_per_day": None}, state)
    assert stop["parameter_uncertainty"] is None


def test_run_case_attaches_the_engine_interval_to_the_final_recommendation():
    """End to end through the orchestrator loop with a scripted model (no key, no network)."""
    from types import SimpleNamespace as NS
    from unittest.mock import patch

    usage = NS(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    tool = lambda i, name, inp: NS(type="tool_use", id=i, name=name, input=inp)
    script = iter([
        NS(stop_reason="tool_use", usage=usage, content=[
            tool("t1", "compute_pediatric_dose", {"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})]),
        NS(stop_reason="tool_use", usage=usage, content=[
            tool("t2", "submit_recommendation", {"drug": "vancomycin", "grade": "B", "blocked": False,
                                                 "final_dose_mg_per_kg_per_day": 30.0, "flags": []})]),
    ])
    fake = NS(messages=NS(create=lambda **kw: next(script)))
    dossier = _state()["last_dossier"]
    with patch("agents.agent.Anthropic", return_value=fake), \
         patch("agents.agent.PK_CACHE.get", return_value={"dossier": dossier}):
        from agents.agent import run_case
        out = run_case({"drug": "vancomycin", "indication": "sepsis", "age_years": 0.02,
                        "weight_kg": 3.4, "pma_weeks": 41})
    rec = out["recommendation"]
    assert rec and not rec.get("blocked"), out
    q = rec["parameter_uncertainty"]["dose_mg_per_kg_per_day"]
    assert q["p05"] < q["p50"] < q["p95"]


def test_engine_hard_stop_gets_no_interval():
    state = _state()
    _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    state["last_dossier"]["toxic_dose_mg_per_kg_per_day"] = 1.0       # engine dose is far above this
    out = _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    assert out.get("blocked") is True and "parameter_uncertainty" not in out
    assert state["last_parameter_uncertainty"] is None


def test_an_interval_failure_never_discards_a_valid_engine_dose():
    from unittest.mock import patch
    state = _state()
    with patch("agents.agent.dose_uncertainty_interval", side_effect=RuntimeError("boom")):
        out = _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    assert out.get("recommended_dose_mg_per_kg_per_day") and "error" not in out, out
    assert out["parameter_uncertainty"] is None and state["last_parameter_uncertainty"] is None


def test_no_interval_when_the_recommendation_withholds_a_dose():
    state = _state()
    _build_compute(_neonate(), state)({"drug": "vancomycin", "weight_kg": 3.4, "pma_weeks": 41})
    rec = attach_parameter_uncertainty({"blocked": False, "final_dose_mg_per_kg_per_day": None}, state)
    assert rec["parameter_uncertainty"] is None


def test_final_dose_past_a_cited_safety_bound_is_flagged_without_the_interval():
    """The final (possibly guideline-anchored) dose is checked against the dossier bounds
    in the backend, so the flag survives a missing parameter-uncertainty interval."""
    from agents.agent import apply_final_dose_safety_flags
    dossier = {"toxic_dose_mg_per_kg_per_day": 30.0, "effective_dose_mg_per_kg_per_day": 10.0}
    high = apply_final_dose_safety_flags({"final_dose_mg_per_kg_per_day": 40.0, "flags": []}, dossier)
    assert any("ABOVE TOXIC THRESHOLD" in f and "40" in f and "30" in f for f in high["flags"])
    low = apply_final_dose_safety_flags({"final_dose_mg_per_kg_per_day": 5.0, "flags": []}, dossier)
    assert any("BELOW EFFECTIVE THRESHOLD" in f for f in low["flags"])
    ok = apply_final_dose_safety_flags({"final_dose_mg_per_kg_per_day": 20.0, "flags": ["x"]}, dossier)
    assert ok["flags"] == ["x"]
    none = apply_final_dose_safety_flags({"final_dose_mg_per_kg_per_day": None, "flags": []}, dossier)
    assert none["flags"] == []


def test_a_per_day_only_final_dose_is_checked_per_kg_using_the_weight():
    """A recommendation may give only mg/day; the known weight turns it into mg/kg/day for
    the safety check (20 kg × 40 mg/kg/day = 800 mg/day is past a 30 mg/kg/day bound)."""
    from agents.agent import apply_final_dose_safety_flags
    dossier = {"toxic_dose_mg_per_kg_per_day": 30.0}
    rec = {"final_dose_mg_per_kg_per_day": None, "final_dose_mg_per_day": 800.0, "flags": []}
    out = apply_final_dose_safety_flags(rec, dossier, weight_kg=20.0)
    assert any("ABOVE TOXIC THRESHOLD" in f and "40" in f for f in out["flags"])
    no_wt = apply_final_dose_safety_flags(
        {"final_dose_mg_per_kg_per_day": None, "final_dose_mg_per_day": 800.0, "flags": []}, dossier)
    assert not any("THRESHOLD" in f for f in no_wt["flags"])


def test_both_dose_fields_are_checked_and_a_derived_value_is_labelled():
    """A per-kg value that disagrees with mg/day must not hide an unsafe mg/day dose:
    20 kg, 10 mg/kg/day stated, 2000 mg/day stated (= 100 mg/kg/day), toxic 30."""
    from agents.agent import apply_final_dose_safety_flags
    dossier = {"toxic_dose_mg_per_kg_per_day": 30.0}
    rec = {"final_dose_mg_per_kg_per_day": 10.0, "final_dose_mg_per_day": 2000.0, "flags": []}
    out = apply_final_dose_safety_flags(rec, dossier, weight_kg=20.0)
    hit = [f for f in out["flags"] if "ABOVE TOXIC THRESHOLD" in f]
    assert len(hit) == 1 and "2000 mg/day" in hit[0] and "20 kg" in hit[0]


def test_an_unusable_weight_does_not_produce_a_derived_check():
    from agents.agent import apply_final_dose_safety_flags
    dossier = {"toxic_dose_mg_per_kg_per_day": 30.0, "effective_dose_mg_per_kg_per_day": 10.0}
    for wt in (0, -5, float("inf"), True, None):
        out = apply_final_dose_safety_flags(
            {"final_dose_mg_per_kg_per_day": None, "final_dose_mg_per_day": 800.0, "flags": []},
            dossier, weight_kg=wt)
        assert not any("THRESHOLD" in f for f in out["flags"]), wt


def test_a_numeric_string_bound_is_read_and_a_bad_bound_is_ignored():
    from agents.agent import apply_final_dose_safety_flags
    out = apply_final_dose_safety_flags({"final_dose_mg_per_kg_per_day": 5.0, "flags": []},
                                        {"effective_dose_mg_per_kg_per_day": "10"})
    assert any("BELOW EFFECTIVE THRESHOLD" in f for f in out["flags"])
    for bad in ("n/a", float("nan"), True):
        out = apply_final_dose_safety_flags({"final_dose_mg_per_kg_per_day": 5.0, "flags": []},
                                            {"toxic_dose_mg_per_kg_per_day": bad})
        assert out["flags"] == [], bad


def test_a_dose_that_cannot_be_checked_against_a_cited_bound_says_so():
    """mg/day stated, no usable per-kg dose or weight, and a bound is cited: flag it."""
    from agents.agent import apply_final_dose_safety_flags
    out = apply_final_dose_safety_flags(
        {"final_dose_mg_per_kg_per_day": None, "final_dose_mg_per_day": 800.0, "flags": []},
        {"toxic_dose_mg_per_kg_per_day": 30.0}, weight_kg=None)
    assert any("NOT CHECKED AGAINST SAFETY BOUNDS" in f for f in out["flags"])
