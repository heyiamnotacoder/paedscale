"""FastAPI app wiring the full PaedScale pipeline behind POST /extrapolate.

Pipeline (concept doc §04): case input -> adult PK -> pathway split ->
allometry x maturation -> dose solve -> rationale + concordance.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent.adult_pk import get_adult_pk
from app.agent.pathways import get_pathway_split
from app.agent.rationale import synthesize_rationale
from app.pk.concordance import find_concordance
from app.pk.pipeline import ChildCovariates, DrugProfile, PathwayMaturation, extrapolate
from app.schemas import CaseRequest, ExtrapolationResponse

DATA_DIR = Path(__file__).resolve().parent / "data"
with open(DATA_DIR / "maturation.json") as f:
    MATURATION = json.load(f)
with open(DATA_DIR / "guidelines.json") as f:
    GUIDELINES = json.load(f)
with open(DATA_DIR / "drugs.json") as f:
    DRUGS = json.load(f)

DISCLAIMER = (
    "Decision support only, not an autonomous prescribing order. This is a defensible "
    "starting estimate for a qualified clinician to review. Narrow-therapeutic-index "
    "drugs must be confirmed with therapeutic drug monitoring."
)

# Renal impairment reduces GFR-dependent clearance; hepatic impairment reduces
# CYP/UGT-dependent clearance. Simplified fixed modifier for the MVP — a real
# system would take a graded renal/hepatic function input (e.g. CrCl, Child-Pugh).
IMPAIRMENT_ORGAN_FUNCTION_MODIFIER = 0.5

app = FastAPI(title="PaedScale", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/drugs")
def list_drugs():
    return {"drugs": sorted(DRUGS.keys())}


@app.post("/extrapolate", response_model=ExtrapolationResponse)
def extrapolate_case(case: CaseRequest) -> ExtrapolationResponse:
    pma_weeks = case.gestational_age_weeks + case.postnatal_age_weeks
    drug_key = case.drug_name.strip().lower()
    curated = drug_key in DRUGS

    if not curated:
        # MVP limitation: the exposure-matching dose solve needs an adult reference
        # dose/interval, which only exists for the curated drugs in this scope.
        # Short-circuit before any live Claude call for a clear, fast error.
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{case.drug_name}' is outside the curated demo scope "
                "(midazolam, vancomycin, morphine). This MVP needs an adult "
                "reference dose to solve against, which only the curated drugs have."
            ),
        )

    try:
        adult_pk = get_adult_pk(case.drug_name)
        pathway = get_pathway_split(case.drug_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    primary_pathway = pathway.get("primary_pathway")
    if primary_pathway not in MATURATION:
        raise HTTPException(
            status_code=422,
            detail=f"No maturation model available for pathway '{primary_pathway}'.",
        )

    drug_entry = DRUGS[drug_key]
    organ_function_modifier = 1.0
    if case.renal_impairment and primary_pathway == "renal_GFR":
        organ_function_modifier = IMPAIRMENT_ORGAN_FUNCTION_MODIFIER
    if case.hepatic_impairment and primary_pathway in ("CYP3A4", "UGT2B7"):
        organ_function_modifier = IMPAIRMENT_ORGAN_FUNCTION_MODIFIER

    drug_profile = DrugProfile(
        name=drug_entry["name"],
        adult_clearance_l_per_h=adult_pk["adult_clearance_l_per_h"],
        adult_volume_l=adult_pk["adult_volume_l"],
        adult_protein_binding=adult_pk["adult_protein_binding"],
        primary_pathway=primary_pathway,
        fm_primary=pathway["fm_primary"],
        adult_reference_dose_mg=drug_entry["adult_reference_dose_mg"],
        dosing_interval_h=drug_entry["dosing_interval_h"],
    )
    child = ChildCovariates(weight_kg=case.weight_kg, pma_weeks=pma_weeks)
    pathway_maturation = PathwayMaturation(
        tm50_weeks=MATURATION[primary_pathway]["tm50_weeks"],
        hill=MATURATION[primary_pathway]["hill"],
    )

    rec = extrapolate(
        drug_profile,
        pathway_maturation,
        child,
        child_interval_h=case.dosing_interval_h,
        organ_function_modifier=organ_function_modifier,
    )

    concordance = None
    if drug_key in GUIDELINES:
        concordance = find_concordance(pma_weeks, rec.dose_mg_per_kg, GUIDELINES[drug_key])

    facts = {
        "drug": drug_entry["name"],
        "indication": case.indication or drug_entry["indication"],
        "child": {
            "weight_kg": case.weight_kg,
            "pma_weeks": pma_weeks,
            "renal_impairment": case.renal_impairment,
            "hepatic_impairment": case.hepatic_impairment,
        },
        "adult_pk": adult_pk,
        "pathway_split": pathway,
        "organ_function_modifier": organ_function_modifier,
        "maturation_fraction_applied": rec.maturation_fraction,
        "dose_recommendation_mg": rec.dose_mg,
        "dose_recommendation_mg_per_kg": rec.dose_mg_per_kg,
        "interval_h": rec.interval_h,
        "narrow_therapeutic_index": drug_entry.get("narrow_therapeutic_index", False),
        "guideline_concordance": concordance.__dict__ if concordance else None,
    }
    try:
        rationale = synthesize_rationale(facts)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ExtrapolationResponse(
        drug_name=drug_entry["name"],
        pma_weeks=pma_weeks,
        adult_pk=adult_pk,
        pathway_split=pathway,
        dose_recommendation=rec.__dict__,
        concordance=concordance.__dict__ if concordance else None,
        rationale=rationale,
        disclaimer=DISCLAIMER,
    )
