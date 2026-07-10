// Response contract — mirrors backend app/schemas.py (lenient; most fields optional).

export interface QueryRequest {
  query: string;
  overrides?: Record<string, unknown>;
}

export interface Covariates {
  drug_name?: string | null;
  indication?: string | null;
  weight_kg?: number | null;
  height_cm?: number | null;
  sex?: string | null;
  gestational_age_weeks?: number | null;
  postnatal_age_weeks?: number | null;
  pma_weeks?: number | null;
  serum_creatinine_mg_dl?: number | null;
  egfr_ml_min_1_73?: number | null;
  child_pugh_score?: number | null;
  albumin_g_dl?: number | null;
  route?: string | null;
  assumed_defaults: string[];
}

export interface Citation {
  title: string;
  authors: string;
  year?: string | number | null;
  source: string;
  identifier: string;
  url: string;
  claim_supported: string;
}

export interface PathwayOut {
  name: string;
  fm: number;
  organ: string;
  tm50_weeks?: number | null;
  hill?: number | null;
  maturation_fraction?: number | null;
}

export interface SafetyBounds {
  min_effective_mg_per_kg?: number | null;
  max_safe_mg_per_kg?: number | null;
  within: boolean;
  clamped_mg_per_kg?: number | null;
  flag?: string | null;
}

export interface DoseOut {
  dose_mg?: number | null;
  dose_mg_per_kg?: number | null;
  interval_h?: number | null;
  method: string;
  method_rationale: string;
  matched_metric: string;
  child_clearance_l_per_h?: number | null;
  child_volume_l?: number | null;
  maturation_fraction?: number | null;
  safety_bounds: SafetyBounds;
}

export interface EvidenceGrade {
  grade: string; // high | moderate | low | very-low
  rationale: string;
}

export interface Concordance {
  matched: boolean;
  guideline_age_group?: string | null;
  guideline_dose_mg_per_kg?: number | null;
  predicted_dose_mg_per_kg?: number | null;
  ratio?: number | null;
  verdict: string; // concordant | divergent | no_guideline_available
  source?: string | null;
}

export interface Critique {
  objections: string[];
  resolution: string;
  residual_risks: string[];
}

export interface ExtrapolationResponse {
  query: string;
  drug_name: string;
  covariates: Covariates;
  adult_pk: Record<string, unknown>;
  pathways: PathwayOut[];
  dosing_method: string;
  dose_recommendation: DoseOut;
  evidence_grade: EvidenceGrade;
  citations: Citation[];
  concordance: Concordance | null;
  critique: Critique;
  safety_flags: string[];
  rationale: string;
  disclaimer: string;
  cost_usd?: number | null;
}

// One reasoning-trace event from the SSE stream.
export interface TraceEvent {
  agent: string;
  kind: "status" | "thinking" | "tool" | "tool_result";
  text: string;
  tool?: string;
}

export interface ApiError {
  detail: string;
}
