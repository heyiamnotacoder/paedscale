"""The no-key /pk engine check reports the same 90% parameter-uncertainty interval as the agent."""

from fastapi.testclient import TestClient

from api.main import app


def test_pk_reports_interval_and_dominant_parameter_for_a_neonate():
    r = TestClient(app).post("/pk", json={
        "drug": "vancomycin", "weight_kg": 3.5, "age_years": 0.02, "pma_weeks": 42,
        "calculator_mode": "pediatric",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    pu = body["parameter_uncertainty"]
    q = pu["dose_mg_per_kg_per_day"]
    assert q["p05"] < body["recommended_dose_mg_per_kg_per_day"] < q["p95"], (q, body)
    assert pu["dominant_parameter"]["key"] == "renal_gfr.tm50_weeks", pu["dominant_parameter"]
