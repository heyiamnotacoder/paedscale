"""Pydantic request/response models for the generalized /extrapolate endpoint.

Input is now a free-text clinical query. Output is the orchestrator's assembled,
cited, self-critiqued recommendation. Every output sub-model is lenient (wide
defaults) because the fields are populated by an LLM's structured tool call —
a missing field should degrade gracefully, never 500 the request.

Nested objects/arrays sometimes arrive as JSON *strings* from tool-use (double-
encoded). Before-validators coerce those so validation does not 502 a good run.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator


def parse_jsonish(value: Any) -> Any:
    """If *value* is a JSON object/array encoded as a string, parse it; else return as-is."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return value
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return value
    return value


_NESTED_SUBMIT_KEYS = (
    "covariates",
    "adult_pk",
    "pathways",
    "dose_recommendation",
    "evidence_grade",
    "citations",
    "concordance",
    "critique",
    "safety_flags",
)


def normalize_submit_payload(payload: dict[str, Any] | Any) -> dict[str, Any] | Any:
    """Coerce JSON-string nested fields from LLM submit_recommendation args.

    Used at tool-capture time and safe to re-run before model_validate.
    """
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for key in _NESTED_SUBMIT_KEYS:
        if key in out:
            out[key] = parse_jsonish(out[key])
    dr = out.get("dose_recommendation")
    if isinstance(dr, dict) and "safety_bounds" in dr:
        dr = dict(dr)
        dr["safety_bounds"] = parse_jsonish(dr["safety_bounds"])
        out["dose_recommendation"] = dr
    cr = out.get("critique")
    if isinstance(cr, dict):
        cr = dict(cr)
        for k in ("objections", "residual_risks"):
            if k in cr:
                cr[k] = parse_jsonish(cr[k])
        out["critique"] = cr
    return out


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

    @field_validator("assumed_defaults", mode="before")
    @classmethod
    def _coerce_assumed_defaults(cls, v: Any) -> Any:
        return parse_jsonish(v)


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

    @field_validator("safety_bounds", mode="before")
    @classmethod
    def _coerce_safety_bounds(cls, v: Any) -> Any:
        return parse_jsonish(v)


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
    dose_grade: str | None = None  # accept | accept_with_caveats | revise

    @field_validator("objections", "residual_risks", mode="before")
    @classmethod
    def _coerce_string_lists(cls, v: Any) -> Any:
        return parse_jsonish(v)


class ExtrapolationResponse(BaseModel):
    query: str
    drug_name: str = ""
    covariates: Covariates = Covariates()
    adult_pk: dict = {}
    pathways: list[PathwayOut] = []
    dosing_method: str = ""
    # guideline = published regimen short path; mechanistic = allometry×maturation;
    # partial_recovery = assembled after submit_recommendation never ran.
    source_of_dose: str = "mechanistic"
    dose_recommendation: DoseOut = DoseOut()
    evidence_grade: EvidenceGradeOut = EvidenceGradeOut()
    citations: list[Citation] = []
    concordance: ConcordanceOut | None = None
    critique: CritiqueOut = CritiqueOut()
    safety_flags: list[str] = []
    rationale: str = ""
    disclaimer: str = ""
    cost_usd: float | None = None  # measured inference cost for this query (observability)

    @field_validator(
        "covariates",
        "adult_pk",
        "pathways",
        "dose_recommendation",
        "evidence_grade",
        "citations",
        "concordance",
        "critique",
        "safety_flags",
        mode="before",
    )
    @classmethod
    def _coerce_json_strings(cls, v: Any) -> Any:
        return parse_jsonish(v)
