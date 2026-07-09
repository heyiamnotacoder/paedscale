"""Pydantic request/response models for the /extrapolate endpoint."""

from pydantic import BaseModel, Field


class CaseRequest(BaseModel):
    drug_name: str = Field(..., description="e.g. midazolam, vancomycin, morphine")
    indication: str = ""
    weight_kg: float = Field(..., gt=0, le=150)
    gestational_age_weeks: float = Field(..., ge=22, le=44, description="Gestational age at birth")
    postnatal_age_weeks: float = Field(..., ge=0, le=1000, description="Age since birth, in weeks")
    renal_impairment: bool = False
    hepatic_impairment: bool = False
    dosing_interval_h: float | None = Field(
        None, gt=0, description="Override the adult reference dosing interval, if clinically indicated"
    )


class DoseRecommendationOut(BaseModel):
    dose_mg: float
    dose_mg_per_kg: float
    interval_h: float
    child_clearance_l_per_h: float
    child_volume_l: float
    maturation_fraction: float


class ConcordanceOut(BaseModel):
    matched: bool
    guideline_age_group: str | None
    guideline_dose_mg_per_kg: float | None
    predicted_dose_mg_per_kg: float
    ratio: float | None
    verdict: str
    source: str | None


class RationaleOut(BaseModel):
    rationale: str
    assumptions: list[str]
    uncertainty_flags: list[str]
    narrow_therapeutic_index_warning: str
    concordance_summary: str


class ExtrapolationResponse(BaseModel):
    drug_name: str
    pma_weeks: float
    adult_pk: dict
    pathway_split: dict
    dose_recommendation: DoseRecommendationOut
    concordance: ConcordanceOut | None
    rationale: RationaleOut
    disclaimer: str
