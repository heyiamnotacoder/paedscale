"""API tests for the transitional PaedScale app (Phase 0).

The prefill drug set and the curated exposure-match endpoint have been removed.
Until the generalized multi-agent pipeline lands (Phase 2), /extrapolate returns
503. Request-shape validation (pydantic) still applies before the handler runs.
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module

VALID_CASE = {
    "drug_name": "paracetamol",
    "weight_kg": 3.1,
    "gestational_age_weeks": 40,
    "postnatal_age_weeks": 0,
}


@pytest.fixture
def client():
    return TestClient(main_module.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_extrapolate_is_under_construction(client):
    resp = client.post("/extrapolate", json=VALID_CASE)
    assert resp.status_code == 503
    assert "under construction" in resp.json()["detail"]


def test_extrapolate_invalid_weight_still_422(client):
    resp = client.post(
        "/extrapolate",
        json={**VALID_CASE, "weight_kg": -1},
    )
    assert resp.status_code == 422
