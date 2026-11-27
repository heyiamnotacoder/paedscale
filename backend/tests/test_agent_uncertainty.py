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
    assert state["last_parameter_uncertainty"] is pu


def test_blocked_compute_clears_any_earlier_interval():
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
    assert ok["parameter_uncertainty"] is state["last_parameter_uncertainty"]
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
