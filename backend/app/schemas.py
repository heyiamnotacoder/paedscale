"""Pydantic request/response models for the generalized /extrapolate endpoint.

Input is now a free-text clinical query. Output is the orchestrator's assembled,
cited, self-critiqued recommendation. Every output sub-model is lenient (wide
defaults) because the fields are populated by an LLM's structured tool call —
a missing field should degrade gracefully, never 500 the request.
"""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., description="Free-text clinical question, e.g. 'starting dose of "
                       "paracetamol in a 2-day-old neonate, 3.1 kg, Child-Pugh 7'.")
    overrides: dict | None = Field(None, description="Optional structured covariate overrides.")


# --- legacy shape kept so the transitional endpoint / older clients still parse ---
class CaseRequest(BaseModel):
    drug_name: str
    indication: str = ""
    weight_kg: float = Field(..., gt=0, le=150)
    gestational_age_weeks: float = Field(..., ge=22, le=44)
    postnatal_age_weeks: float = Field(..., ge=0, le=1000)
    renal_impairment: bool = False
    hepatic_impairment: bool = False
    dosing_interval_h: float | None = Field(None, gt=0)


class Covariates(BaseModel):
    drug_name: str | None = None
    indication: str | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    sex: str | None = None
    gestational_age_weeks: float | None = None
    postnatal_age_weeks: float | None = None
    pma_weeks: float | None = None
    serum_creatinine_mg_dl: float | None = None
    egfr_ml_min_1_73: float | None = None
    child_pugh_score: int | None = None
    albumin_g_dl: float | None = None
    route: str | None = None
    assumed_defaults: list[str] = []  # covariates not given, filled with population defaults


class Citation(BaseModel):
    title: str = ""
    authors: str = ""
    year: str | int | None = None
    source: str = ""  # PubMed | Semantic Scholar | web | label/guideline
    identifier: str = ""  # PMID / DOI
    url: str = ""
    claim_supported: str = ""


class PathwayOut(BaseModel):
    name: str
    fm: float
    organ: str = "other"
    tm50_weeks: float | None = None
    hill: float | None = None
    maturation_fraction: float | None = None


class SafetyBoundsOut(BaseModel):
    min_effective_mg_per_kg: float | None = None
    max_safe_mg_per_kg: float | None = None
    within: bool = True
    clamped_mg_per_kg: float | None = None
    flag: str | None = None


class DoseOut(BaseModel):
    dose_mg: float | None = None
    dose_mg_per_kg: float | None = None
    interval_h: float | None = None
    method: str = ""
    method_rationale: str = ""
    matched_metric: str = ""
    child_clearance_l_per_h: float | None = None
    child_volume_l: float | None = None
    maturation_fraction: float | None = None
    safety_bounds: SafetyBoundsOut = SafetyBoundsOut()


class EvidenceGradeOut(BaseModel):
    grade: str = "very-low"  # high | moderate | low | very-low
    rationale: str = ""


class ConcordanceOut(BaseModel):
    matched: bool = False
    guideline_age_group: str | None = None
    guideline_dose_mg_per_kg: float | None = None
    predicted_dose_mg_per_kg: float | None = None
    ratio: float | None = None
    verdict: str = "no_guideline_available"
    source: str | None = None


class CritiqueOut(BaseModel):
    objections: list[str] = []
    resolution: str = ""
    residual_risks: list[str] = []


class ExtrapolationResponse(BaseModel):
    query: str
    drug_name: str = ""
    covariates: Covariates = Covariates()
    adult_pk: dict = {}
    pathways: list[PathwayOut] = []
    dosing_method: str = ""
    dose_recommendation: DoseOut = DoseOut()
    evidence_grade: EvidenceGradeOut = EvidenceGradeOut()
    citations: list[Citation] = []
    concordance: ConcordanceOut | None = None
    critique: CritiqueOut = CritiqueOut()
    safety_flags: list[str] = []
    rationale: str = ""
    disclaimer: str = ""
    cost_usd: float | None = None  # measured inference cost for this query (observability)
