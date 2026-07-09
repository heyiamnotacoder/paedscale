export interface CaseRequest {
  drug_name: string;
  indication: string;
  weight_kg: number;
  gestational_age_weeks: number;
  postnatal_age_weeks: number;
  renal_impairment: boolean;
  hepatic_impairment: boolean;
  dosing_interval_h?: number;
}

export interface AdultPk {
  adult_clearance_l_per_h: number;
  adult_volume_l: number;
  adult_protein_binding: number;
  confidence: string;
  sources: string[];
  data_gap_notes?: string;
}

export interface PathwaySplit {
  primary_pathway: string;
  fm_primary: number;
  rationale: string;
  confidence: string;
  tm50_weeks: number;
  hill: number;
  maturation_source: string;
}

export interface DoseRecommendation {
  dose_mg: number;
  dose_mg_per_kg: number;
  interval_h: number;
  child_clearance_l_per_h: number;
  child_volume_l: number;
  maturation_fraction: number;
}

export interface Concordance {
  matched: boolean;
  guideline_age_group: string | null;
  guideline_dose_mg_per_kg: number | null;
  predicted_dose_mg_per_kg: number;
  ratio: number | null;
  verdict: "concordant" | "divergent" | "no_guideline_available";
  source: string | null;
}

export interface Rationale {
  rationale: string;
  assumptions: string[];
  uncertainty_flags: string[];
  narrow_therapeutic_index_warning: string;
  concordance_summary: string;
}

export interface ExtrapolationResponse {
  drug_name: string;
  pma_weeks: number;
  adult_pk: AdultPk;
  pathway_split: PathwaySplit;
  dose_recommendation: DoseRecommendation;
  concordance: Concordance | null;
  rationale: Rationale;
  disclaimer: string;
}

export interface ApiError {
  detail: string;
}
