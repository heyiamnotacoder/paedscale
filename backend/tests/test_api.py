"""API tests for the generalized /extrapolate endpoint.

The orchestrator (live multi-agent run) is monkeypatched so these tests run
without ANTHROPIC_API_KEY / network access — they pin the request contract and
the payload → ExtrapolationResponse mapping, not the model.
"""

import pytest
from fastapi.testclient import TestClient

import app.main as main_module

CANNED_PAYLOAD = {
    "drug_name": "Paracetamol",
    "covariates": {"drug_name": "paracetamol", "weight_kg": 3.1, "pma_weeks": 40.3,
                   "child_pugh_score": 7, "assumed_defaults": ["height_cm"]},
    "adult_pk": {"adult_clearance_l_per_h": 21.0, "adult_volume_l": 60.0},
    "pathways": [
        {"name": "UGT1A1", "fm": 0.5, "organ": "hepatic", "maturation_fraction": 0.4},
        {"name": "sulfation", "fm": 0.3, "organ": "hepatic"},
        {"name": "CYP2E1", "fm": 0.2, "organ": "hepatic"},
    ],
    "dosing_method": "auc",
    "source_of_dose": "mechanistic",
    "dose_recommendation": {
        "dose_mg": 28.17, "dose_mg_per_kg": 9.09, "interval_h": 6.0, "method": "auc",
        "matched_metric": "AUC over dosing interval (steady state)",
        "safety_bounds": {"min_effective_mg_per_kg": 7.5, "max_safe_mg_per_kg": 15.0, "within": True},
    },
    "evidence_grade": {"grade": "low", "rationale": "sparse neonatal PK; height assumed"},
    "citations": [{"title": "Paracetamol neonatal PK", "source": "PubMed", "identifier": "PMID:123"}],
    "concordance": {"matched": False, "verdict": "no_guideline_available"},
    "critique": {
        "objections": ["consider hepatotoxicity risk"],
        "resolution": "dose within safe bound",
        "dose_grade": "accept_with_caveats",
    },
    "safety_flags": ["hepatic impairment reduces clearance"],
    "rationale": "Paracetamol is cleared by glucuronidation, sulfation and CYP2E1...",
}


@pytest.fixture
def client():
    return TestClient(main_module.app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_extrapolate_maps_payload_to_response(client, monkeypatch):
    async def fake_run(query, on_message=None):
        return CANNED_PAYLOAD, 0.23, []

    monkeypatch.setattr(main_module, "run_orchestrator", fake_run)
    resp = client.post("/extrapolate", json={"query": "paracetamol neonate 3.1 kg Child-Pugh 7"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["drug_name"] == "Paracetamol"
    assert body["dose_recommendation"]["dose_mg_per_kg"] == 9.09
    assert body["dose_recommendation"]["safety_bounds"]["within"] is True
    assert len(body["pathways"]) == 3
    assert body["evidence_grade"]["grade"] == "low"
    assert body["citations"][0]["identifier"] == "PMID:123"
    assert body["cost_usd"] == 0.23
    assert body["source_of_dose"] == "mechanistic"
    assert body["critique"]["dose_grade"] == "accept_with_caveats"
    assert "Decision support only" in body["disclaimer"]


def test_extrapolate_missing_payload_returns_502(client, monkeypatch):
    async def fake_run(query, on_message=None):
        return None, None, []

    monkeypatch.setattr(main_module, "run_orchestrator", fake_run)
    resp = client.post("/extrapolate", json={"query": "x"})
    assert resp.status_code == 502


def test_extrapolate_requires_query(client):
    resp = client.post("/extrapolate", json={})
    assert resp.status_code == 422
