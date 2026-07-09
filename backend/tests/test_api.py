"""API tests for POST /extrapolate. Rationale synthesis (the live Claude call)
is monkeypatched so these tests run without ANTHROPIC_API_KEY / network access.
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module

FAKE_RATIONALE = {
    "rationale": "test rationale",
    "assumptions": ["test assumption"],
    "uncertainty_flags": [],
    "narrow_therapeutic_index_warning": "",
    "concordance_summary": "test summary",
}


@pytest.fixture(autouse=True)
def mock_rationale(monkeypatch):
    monkeypatch.setattr(main_module, "synthesize_rationale", lambda facts: FAKE_RATIONALE)


@pytest.fixture
def client():
    return TestClient(main_module.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_list_drugs(client):
    resp = client.get("/drugs")
    assert resp.status_code == 200
    assert set(resp.json()["drugs"]) == {"midazolam", "vancomycin", "morphine"}


NEONATE_CASE = {
    "weight_kg": 3.5,
    "gestational_age_weeks": 40,
    "postnatal_age_weeks": 2,
}


@pytest.mark.parametrize("drug_name", ["midazolam", "vancomycin", "morphine", "Midazolam"])
def test_extrapolate_curated_drugs_returns_full_response(client, drug_name):
    resp = client.post("/extrapolate", json={"drug_name": drug_name, **NEONATE_CASE})
    assert resp.status_code == 200
    body = resp.json()

    assert body["drug_name"].lower() == drug_name.lower()
    assert body["pma_weeks"] == 42
    assert body["dose_recommendation"]["dose_mg"] > 0
    assert body["dose_recommendation"]["dose_mg_per_kg"] > 0
    assert 0 <= body["dose_recommendation"]["maturation_fraction"] <= 1
    assert body["rationale"] == FAKE_RATIONALE
    assert "Decision support only" in body["disclaimer"]
    # concordance is matched for the neonate case since guidelines.json has a term-neonate entry
    assert body["concordance"]["matched"] is True
    assert body["concordance"]["verdict"] in ("concordant", "divergent")


def test_extrapolate_out_of_scope_drug_returns_422(client):
    resp = client.post("/extrapolate", json={"drug_name": "acetaminophen", **NEONATE_CASE})
    assert resp.status_code == 422
    assert "outside the curated demo scope" in resp.json()["detail"]


def test_extrapolate_renal_impairment_reduces_dose_for_renally_cleared_drug(client):
    baseline = client.post("/extrapolate", json={"drug_name": "vancomycin", **NEONATE_CASE}).json()
    impaired = client.post(
        "/extrapolate",
        json={"drug_name": "vancomycin", "renal_impairment": True, **NEONATE_CASE},
    ).json()
    assert impaired["dose_recommendation"]["dose_mg"] < baseline["dose_recommendation"]["dose_mg"]


def test_extrapolate_renal_impairment_does_not_affect_hepatically_cleared_drug(client):
    baseline = client.post("/extrapolate", json={"drug_name": "midazolam", **NEONATE_CASE}).json()
    impaired = client.post(
        "/extrapolate",
        json={"drug_name": "midazolam", "renal_impairment": True, **NEONATE_CASE},
    ).json()
    assert impaired["dose_recommendation"]["dose_mg"] == pytest.approx(
        baseline["dose_recommendation"]["dose_mg"]
    )


def test_extrapolate_invalid_weight_returns_422(client):
    resp = client.post(
        "/extrapolate",
        json={"drug_name": "morphine", "weight_kg": -1, "gestational_age_weeks": 40, "postnatal_age_weeks": 2},
    )
    assert resp.status_code == 422
