"""Manual smoke test for the Claude agent layer.

Runs the curated adult-PK + pathway-split lookups (no API call), then a live
rationale synthesis call (requires ANTHROPIC_API_KEY) for each in-scope drug.

Usage:
    cd backend && python -m scripts.smoke_agent
"""

from app.agent.adult_pk import get_adult_pk
from app.agent.pathways import get_pathway_split
from app.agent.rationale import synthesize_rationale
from app.pk.pipeline import ChildCovariates, DrugProfile, PathwayMaturation, extrapolate

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
MATURATION = json.load(open(DATA_DIR / "maturation.json"))
DRUGS = json.load(open(DATA_DIR / "drugs.json"))

CASES = {
    "midazolam": {"weight_kg": 3.5, "pma_weeks": 42, "indication": "Procedural sedation"},
    "vancomycin": {"weight_kg": 3.5, "pma_weeks": 42, "indication": "Suspected sepsis"},
    "morphine": {"weight_kg": 3.5, "pma_weeks": 42, "indication": "Postoperative analgesia"},
}


def run_one(drug_name: str, case: dict) -> None:
    print(f"\n=== {drug_name} ===")

    adult_pk = get_adult_pk(drug_name)
    pathway = get_pathway_split(drug_name)
    print("adult_pk:", adult_pk)
    print("pathway_split:", pathway)

    drug_entry = DRUGS[drug_name]
    drug = DrugProfile(
        name=drug_name,
        adult_clearance_l_per_h=adult_pk["adult_clearance_l_per_h"],
        adult_volume_l=adult_pk["adult_volume_l"],
        adult_protein_binding=adult_pk["adult_protein_binding"],
        primary_pathway=pathway["primary_pathway"],
        fm_primary=pathway["fm_primary"],
        adult_reference_dose_mg=drug_entry["adult_reference_dose_mg"],
        dosing_interval_h=drug_entry["dosing_interval_h"],
    )
    mat = MATURATION[pathway["primary_pathway"]]
    child = ChildCovariates(weight_kg=case["weight_kg"], pma_weeks=case["pma_weeks"])
    rec = extrapolate(drug, PathwayMaturation(tm50_weeks=mat["tm50_weeks"], hill=mat["hill"]), child)
    print("dose_recommendation:", rec)

    facts = {
        "drug": drug_name,
        "indication": case["indication"],
        "child": case,
        "adult_pk": adult_pk,
        "pathway_split": pathway,
        "dose_recommendation_mg_per_kg": rec.dose_mg_per_kg,
        "dose_recommendation_mg": rec.dose_mg,
        "interval_h": rec.interval_h,
    }
    rationale = synthesize_rationale(facts)
    print("rationale:", rationale)


if __name__ == "__main__":
    for drug_name, case in CASES.items():
        run_one(drug_name, case)
