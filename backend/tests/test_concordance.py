"""Concordance tests: the deterministic PK pipeline vs. known guideline doses.

Per the concept doc (§02, §06): where a guideline exists, PaedScale's mechanistic
estimate should land in the neighbourhood of the established dose. This is a
directional sanity check, not an exact regulatory match — the allometry x
maturation model is a simplified top-down engine (concept §03), and honest
uncertainty is preferred over false precision. We assert the predicted mg/kg
dose falls within CONCORDANCE_TOLERANCE_FACTOR of the guideline mg/kg dose for
each of the three in-scope elimination archetypes (CYP3A4, renal GFR, UGT2B7).
"""

import json
from pathlib import Path

import pytest

from app.pk.pipeline import ChildCovariates, DrugProfile, PathwayMaturation, extrapolate

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
CONCORDANCE_TOLERANCE_FACTOR = 2.5


def _load_json(name: str) -> dict:
    with open(DATA_DIR / name) as f:
        return json.load(f)


DRUGS = _load_json("drugs.json")
MATURATION = _load_json("maturation.json")
GUIDELINES = _load_json("guidelines.json")


def _drug_profile(key: str) -> DrugProfile:
    d = DRUGS[key]
    return DrugProfile(
        name=d["name"],
        adult_clearance_l_per_h=d["adult_clearance_l_per_h"],
        adult_volume_l=d["adult_volume_l"],
        adult_protein_binding=d["adult_protein_binding"],
        primary_pathway=d["primary_pathway"],
        fm_primary=d["fm_primary"],
        adult_reference_dose_mg=d["adult_reference_dose_mg"],
        dosing_interval_h=d["dosing_interval_h"],
    )


def _pathway(key: str) -> PathwayMaturation:
    d = DRUGS[key]
    m = MATURATION[d["primary_pathway"]]
    return PathwayMaturation(tm50_weeks=m["tm50_weeks"], hill=m["hill"])


CASES = [
    (drug_key, case)
    for drug_key, cases in GUIDELINES.items()
    for case in cases
]


@pytest.mark.parametrize(
    "drug_key,case",
    CASES,
    ids=[f"{k}:{c['age_group']}" for k, c in CASES],
)
def test_predicted_dose_concordant_with_guideline(drug_key, case):
    drug = _drug_profile(drug_key)
    pathway = _pathway(drug_key)
    child = ChildCovariates(weight_kg=case["weight_kg"], pma_weeks=case["pma_weeks"])

    rec = extrapolate(drug, pathway, child)

    guideline_mg_per_kg = case["guideline_dose_mg_per_kg"]
    ratio = rec.dose_mg_per_kg / guideline_mg_per_kg

    assert 1 / CONCORDANCE_TOLERANCE_FACTOR <= ratio <= CONCORDANCE_TOLERANCE_FACTOR, (
        f"{drug.name} ({case['age_group']}): predicted {rec.dose_mg_per_kg:.4f} mg/kg "
        f"vs guideline {guideline_mg_per_kg:.4f} mg/kg (ratio {ratio:.2f}) "
        f"exceeds tolerance factor {CONCORDANCE_TOLERANCE_FACTOR}"
    )


def test_neonate_dose_never_exceeds_child_dose_for_maturing_pathway():
    """Sanity check: for a maturing elimination pathway, a term neonate's
    weight-normalised dose should not exceed an older child's, since clearance
    per kg only increases (or stays flat) as the pathway matures.
    """
    for drug_key in ("midazolam", "vancomycin", "morphine"):
        drug = _drug_profile(drug_key)
        pathway = _pathway(drug_key)

        neonate = ChildCovariates(weight_kg=3.5, pma_weeks=40)
        older_child = ChildCovariates(weight_kg=12.0, pma_weeks=160)

        neonate_rec = extrapolate(drug, pathway, neonate)
        child_rec = extrapolate(drug, pathway, older_child)

        assert neonate_rec.dose_mg_per_kg <= child_rec.dose_mg_per_kg, (
            f"{drug.name}: neonate mg/kg dose ({neonate_rec.dose_mg_per_kg:.4f}) "
            f"should not exceed older child's ({child_rec.dose_mg_per_kg:.4f})"
        )
