"""
PaedScale — Claude orchestration layer.

Maps drug → pathways, retrieves adult PK (subagent), runs deterministic engine,
concordance + grade. Decision support, not prescribing.

Requires ANTHROPIC_API_KEY. Engine (pk_engine.py) needs no key.
Detail lives in lean skills (backend/skills/) via load_skill — keep SYSTEM short.
"""

from __future__ import annotations

import json
import os

from anthropic import Anthropic

import retrieval
from engine.formulation import attach_administration
from engine.pk_cache import CACHE as PK_CACHE
from engine.pk_engine import (
    compute_pediatric_dose,
    estimate_gfr_bedside_schwartz,
    renal_function_fraction_from_labs,
    result_to_dict,
)
from skills import load_skill, list_skills

ORCHESTRATOR_MODEL = os.environ.get("ORCHESTRATOR_MODEL", "claude-opus-4-8")
MAX_TOKENS = int(os.environ.get("PAEDSCALE_MAX_TOKENS", "4000"))

SYSTEM = """You are PaedScale: pediatric STARTING dose from adult PK via allometry × maturation.
Decision support for a clinician — NOT a prescriber.

Pipeline (lean):
1. load_skill('mechanism') if needed → map elimination / fm / target_metric / mechanism fields.
   Empty lists for absent transporters/metabolites. Cite-or-abstain.
2. retrieve_drug_data FIRST — only PK source (live or shared cache). Skip this call if the
   user message already includes a cached dossier with CL+Vd. Null/unavailable → grade D, no invented numbers.
3. CONTRAINDICATIONS (before or with dosing): from the label/dossier + clinical knowledge, list
   situations where this drug should be AVOIDED in contraindications_avoid (allergy/class
   cross-reactivity, absolute contraindications, major condition warnings). Compare to case
   allergies[] and conditions[]. If the patient MATCHES a true contraindication (e.g. allergy
   to this drug or class, absolute contraindication present), HARD STOP: final_dose_* = null,
   grade = D, blocked=true, block_reason = "SAFETY STOP — CONTRAINDICATED: …", and put that
   string as the FIRST flag. Never invent a dose for a contraindicated patient. Always still
   fill contraindications_avoid so the clinician sees the full avoid-list.
4. compute_pediatric_dose with retrieved PK + child covariates (use case renal fraction;
   hepatic_function_fraction stays 1.0). Pediatric + hepatic on + hepatic fm ≥ 0.3: HI
   rewrites the adult reference dose from the cited table, then allometry — do not invent an
   OF. No cited applicable row → blocked/abstain, grade D. Adult HI label × allometry is
   grade ceiling B; renal+HI stacked is ceiling C.
   Adult HI calculator (calculator_mode=adult_hi) is NOT this pipeline: it is a deterministic
   cited-label lookup with no allometry, no maturation, and no A–D grade.
   Pass oral_bioavailability from the dossier; if a route is clinically non-viable (e.g. an oral
   route for a drug not systemically absorbed orally, F=0), pass routes_allowed (e.g. ["iv"]).
   If compute returns blocked=true the case is NOT prescribable: submit_recommendation with
   final_dose_mg_per_kg_per_day AND final_dose_mg_per_day = null, grade = D, and block_reason
   verbatim as the FIRST flag. Never fabricate or carry forward a dose for a blocked case.
5. load_skill('edge_cases') + assess_edge_cases when relevant; merge flags.
6. web_search pediatric guideline → concordance 0.67×–1.5× (none → grade B).
7. Grade A/B/C/D; flag NTI→TDM, metabolites, oral-F, assumed-term, exposure-matching PD assumption.
8. submit_recommendation once, last. Lean reasoning. Flag toxic/sub-therapeutic doses.

Engine vs guideline (validated limits — act on them):
- Cmax aminoglycosides: allometry×adult-Vd often UNDERdoses children; if engine ≪ published
  pediatric peak/extended-interval dose, prefer the guideline STARTING dose, flag exposure-target
  mismatch + TDM, grade ceiling B.
- time_mic β-lactams: daily-dose match is a PROXY for fT>MIC — guideline-anchor interval/infusion;
  flag proxy; grade ceiling B.
- Michaelis–Menten / null adult CL (e.g. phenytoin): do NOT invent linear CL; guideline-only or D.
- Titration drugs with no adult mg/day: no false precision; guideline/titrate language, not fake CSS."""

TOOLS = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 2,
    },
    {
        "name": "load_skill",
        "description": f"Load a lean skill. Names: {', '.join(list_skills())}.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "retrieve_drug_data",
        "description": "LIVE retrieval subagent (PubMed + openFDA). ONLY source of drug PK. "
                       "Returns source_mode live|cache|unavailable.",
        "input_schema": {
            "type": "object",
            "properties": {"drug": {"type": "string"}, "indication": {"type": "string"}},
            "required": ["drug"],
        },
    },
    {
        "name": "compute_pediatric_dose",
        "description": "Deterministic allometry × maturation engine. fm keys must exist in MATURATION.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drug": {"type": "string"},
                "weight_kg": {"type": "number"},
                "cl_adult_l_h": {"type": "number"},
                "vd_adult_l": {"type": "number"},
                "fm": {
                    "type": "object",
                    "description": "pathway -> fraction, e.g. {\"renal_gfr\": 0.9}",
                    "additionalProperties": {"type": "number"},
                },
                "target_metric": {"type": "string", "enum": ["css", "auc", "cmax", "time_mic"]},
                "age_years": {"type": "number"},
                "pma_weeks": {"type": "number"},
                "gestational_age_weeks": {"type": "number"},
                "postnatal_age_weeks": {"type": "number"},
                "adult_dose_mg_per_day": {"type": "number"},
                "adult_interval_h": {"type": "number"},
                "renal_function_fraction": {"type": "number"},
                "hepatic_function_fraction": {"type": "number"},
                "toxic_dose_mg_per_kg_per_day": {"type": "number"},
                "effective_dose_mg_per_kg_per_day": {"type": "number"},
                "route": {"type": "string", "enum": ["iv", "oral"]},
                "oral_bioavailability": {"type": "number"},
                "routes_allowed": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional clinically viable routes, e.g. [\"iv\"] for a drug "
                                   "not systemically absorbed orally. Non-viable route → hard stop.",
                },
            },
            "required": ["drug", "weight_kg", "cl_adult_l_h", "vd_adult_l", "fm"],
        },
    },
    {
        "name": "assess_edge_cases",
        "description": "Deterministic flags for prodrug/obesity/protein-binding/illness. "
                       "Call after retrieve (and after compute if dose set). Merge flags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case": {"type": "object"},
                "dossier": {"type": "object"},
                "engine_result": {"type": "object"},
            },
            "required": ["case"],
        },
    },
    {
        "name": "submit_recommendation",
        "description": "Final structured recommendation. Call exactly once, last.",
        "input_schema": {
            "type": "object",
            "properties": {
                "final_dose_mg_per_kg_per_day": {"type": ["number", "null"]},
                "final_dose_mg_per_day": {"type": ["number", "null"]},
                "route": {"type": "string"},
                "interval": {"type": "string"},
                "mechanism": {
                    "type": "object",
                    "properties": {
                        "elimination": {"type": "string", "enum": ["renal", "hepatic", "mixed"]},
                        "pathways": {"type": "array", "items": {"type": "string"}},
                        "enzymes": {"type": "array", "items": {"type": "string"}},
                        "transporters": {"type": "array", "items": {"type": "string"}},
                        "active_metabolites": {"type": "array", "items": {"type": "string"}},
                        "protein_binding_percent": {"type": ["number", "null"]},
                    },
                    "required": ["elimination", "pathways", "enzymes",
                                 "transporters", "active_metabolites"],
                },
                "grade": {"type": "string", "enum": ["A", "B", "C", "D"]},
                "grade_rationale": {"type": "string"},
                "concordance": {
                    "type": "object",
                    "properties": {
                        "guideline_dose_mg_per_kg_per_day": {"type": ["number", "null"]},
                        "ratio": {"type": ["number", "null"]},
                        "verdict": {"type": "string"},
                        "source": {"type": "string"},
                    },
                },
                "rationale": {"type": "string"},
                "assumptions": {"type": "array", "items": {"type": "string"}},
                "uncertainty": {"type": "string"},
                "flags": {"type": "array", "items": {"type": "string"}},
                "contraindications_avoid": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Conditions / situations where this drug should be avoided "
                                   "(allergy class, absolute CIs, major warnings). Always fill.",
                },
                "contraindication_matched": {
                    "type": ["string", "null"],
                    "description": "If patient allergies/conditions match a true CI, the "
                                   "matched reason; else null.",
                },
                "blocked": {
                    "type": "boolean",
                    "description": "true when not prescribable (contraindication, route, toxic).",
                },
                "block_reason": {
                    "type": ["string", "null"],
                    "description": "SAFETY STOP reason when blocked.",
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"claim": {"type": "string"}, "source": {"type": "string"}},
                    },
                },
            },
            "required": ["mechanism", "grade", "grade_rationale", "rationale", "flags",
                         "contraindications_avoid"],
        },
    },
]


# Keyword args accepted by compute_pediatric_dose (filter model junk).
_COMPUTE_KEYS = frozenset({
    "drug", "weight_kg", "cl_adult_l_h", "vd_adult_l", "fm", "target_metric",
    "age_years", "pma_weeks", "gestational_age_weeks", "postnatal_age_weeks",
    "adult_dose_mg_per_day", "adult_interval_h", "renal_function_fraction",
    "hepatic_function_fraction", "toxic_dose_mg_per_kg_per_day",
    "effective_dose_mg_per_kg_per_day", "route", "oral_bioavailability",
    "routes_allowed", "assume_term",
})


def _assess_edge_cases(args: dict) -> dict:
    try:
        from engine.edge_cases import assess_edge_cases
        return assess_edge_cases(
            args.get("case") or {},
            args.get("dossier"),
            args.get("engine_result"),
        )
    except Exception as e:
        return {"flags": [], "adjustments": {}, "notes": [], "error": str(e)}


def _dossier_core_pk_ok(dossier: dict | None) -> bool:
    """True when both adult CL and Vd are present (usable for the engine)."""
    if not dossier:
        return False
    return dossier.get("cl_adult_l_h") is not None and dossier.get("vd_adult_l") is not None


def _force_safety_block(rec: dict, reason: str, *, flag_token: str = "SAFETY STOP") -> None:
    """Null doses, grade D, blocked — deterministic submit override."""
    rec["final_dose_mg_per_kg_per_day"] = None
    rec["final_dose_mg_per_day"] = None
    rec["grade"] = "D"
    rec["blocked"] = True
    rec["block_reason"] = reason
    flags = list(rec.get("flags") or [])
    if not any(flag_token in str(f).upper() or reason in str(f) for f in flags):
        flags.insert(0, reason if reason.upper().startswith("SAFETY") else f"SAFETY STOP: {reason}")
    rec["flags"] = flags


def _adult_hi_compute_payload(adult_hi: dict, case: dict) -> dict:
    """Tool-return for adult HI: label dose, never pathways / allometry."""
    blocked = bool(adult_hi.get("blocked"))
    dose = adult_hi.get("adult_dose_mg_per_day")
    dpk = None
    wt = case.get("weight_kg")
    if not blocked and dose is not None and wt not in (None, ""):
        try:
            dpk = round(float(dose) / float(wt), 3)
        except (TypeError, ValueError, ZeroDivisionError):
            dpk = None
    payload = {
        "blocked": blocked,
        "block_reason": adult_hi.get("block_reason"),
        "recommended_dose_mg_per_day": (
            None if blocked or dose is None else round(float(dose), 2)
        ),
        "recommended_dose_mg_per_kg_per_day": None if blocked else dpk,
        "hi_outcome": adult_hi.get("outcome"),
        "hi_outcome_label": adult_hi.get("outcome_label"),
        "allometry_applied": False,
        "grade": None,
    }
    if blocked:
        payload["recommended_dose_mg_per_day"] = None
        payload["recommended_dose_mg_per_kg_per_day"] = None
    return payload


def _load_adult_hi_dossier(case: dict, on_step=None) -> tuple[dict, str, dict]:
    """Cited HI table for adult facade: cache hi_table, else live openFDA extract.

    Does not write a PK-null dossier into the cache (would poison pediatric runs).
    """
    drug = case.get("drug") or ""
    indication = case.get("indication")
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_hit": False, "model": None}
    cached = PK_CACHE.get(drug, indication)
    cached_dossier = (cached or {}).get("dossier") if cached else None
    if cached_dossier:
        usage["cache_hit"] = True
        if on_step:
            on_step("pk_cache hit — reused cited HI table")
        return cached_dossier, "cache", usage
    if on_step:
        on_step("→ retrieve_drug_data — openFDA label lookup (adult HI, no allometry)")
    from engine.hi_table import maybe_extract_hi_table
    from retrieval.retrieval_tools import openfda_label

    label = openfda_label(drug, max_field_chars=8000)
    table = maybe_extract_hi_table(
        label if label.get("found") else {},
        drug=drug,
        indication=indication,
    )
    typical = (table or {}).get("typical_adult_dose_mg_per_day")
    dossier = {
        "hi_table": table,
        "hi_table_pediatric": None,
        "typical_adult_dose_mg_per_day": typical,
        "oral_bioavailability": None,
        "citations": (
            [{"claim": "openFDA hepatic-impairment dosing", "source": table["citation"]}]
            if table and table.get("citation") else []
        ),
    }
    mode = "openfda" if label.get("found") else "unavailable"
    return dossier, mode, usage


def _run_adult_hi_case(case: dict, on_step=None) -> dict:
    """Product path for Adult HI calculator: label lookup, no orchestrator, no A–D."""
    from engine.adult_hi import (
        merge_adult_hi_into_recommendation,
        recommendation_from_adult_hi,
        run_adult_hi_facade,
    )
    from engine.formulation import attach_administration

    trace: list[str] = []
    dossier, source_mode, usage = _load_adult_hi_dossier(case, on_step=on_step)
    if on_step:
        on_step("→ adult_hi_facade — cited label lookup, no allometry")
    result = run_adult_hi_facade(case, dossier, route=case.get("route"))
    rec = recommendation_from_adult_hi(case, result, dossier)
    _apply_organ_function_flags(rec, case, applied_renal_frac=None)
    merge_adult_hi_into_recommendation(rec, result)
    attach_administration(rec, case)
    if on_step:
        label = rec.get("hi_outcome_label") or rec.get("hi_outcome") or "done"
        on_step(f"→ adult HI outcome: {label}")
    return {
        "recommendation": rec,
        "trace": trace,
        "usage": {
            "input_tokens": usage.get("input_tokens") or 0,
            "output_tokens": usage.get("output_tokens") or 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "retrieval_input_tokens": 0,
            "retrieval_output_tokens": 0,
            "retrieval_model": None,
            "model": "adult_hi_facade",
            "source_mode": source_mode,
        },
    }


def _build_compute(case: dict, state: dict):
    """Return a compute_pediatric_dose tool handler closed over case + retrieval state.

    Injects authoritative organ fractions / route / safety bounds from the case and
    last dossier so the model cannot omit renal OF or invent PK after abstention.
    Dossier CL/Vd/fm/F/toxic/effective always win when present (not fill-if-omitted).
    """
    def _compute(args: dict) -> dict:
        # Live-or-abstain: refuse pediatric compute without core PK. Adult HI is
        # label lookup and does not need CL/Vd.
        try:
            from engine.child_pugh import resolve_calculator_mode as _mode
            try:
                _facade = _mode(case)
            except ValueError:
                _facade = "pediatric"
            if _facade != "adult_hi" and (state.get("pk_block_reason") or not state.get("pk_ok")):
                reason = state.get("pk_block_reason") or (
                    "SAFETY STOP — no cited adult PK retrieved; call retrieve_drug_data "
                    "successfully before compute (cite-or-abstain)."
                )
                return {
                    "error": reason,
                    "blocked": True,
                    "block_reason": reason,
                    "recommended_dose_mg_per_day": None,
                    "recommended_dose_mg_per_kg_per_day": None,
                }
            # Keep explicit nulls for oral_bioavailability (unknown F must reach the engine).
            merged: dict = {}
            for k, v in (args or {}).items():
                if k not in _COMPUTE_KEYS:
                    continue
                if v is None and k != "oral_bioavailability":
                    continue
                merged[k] = v
            # Authoritative organ function from normalized case (not model defaults).
            if case.get("renal_function_fraction") is not None:
                merged["renal_function_fraction"] = case["renal_function_fraction"]
            if case.get("hepatic_function_fraction") is not None:
                merged["hepatic_function_fraction"] = case["hepatic_function_fraction"]
            # Prefer case route when model omits it.
            if "route" not in merged and case.get("route"):
                merged["route"] = case["route"]
            # Child covariates from case if model omitted them.
            for k in ("weight_kg", "age_years", "pma_weeks", "gestational_age_weeks",
                      "postnatal_age_weeks"):
                if k not in merged and case.get(k) is not None:
                    merged[k] = case[k]
            if "drug" not in merged and case.get("drug"):
                merged["drug"] = case["drug"]
            dossier = state.get("last_dossier") or {}
            # Prefer retrieved adult dose when model omits it.
            if "adult_dose_mg_per_day" not in merged and dossier.get("typical_adult_dose_mg_per_day") is not None:
                merged["adult_dose_mg_per_day"] = dossier["typical_adult_dose_mg_per_day"]
            # Authoritative dossier fields — always override model invention when present.
            if dossier.get("cl_adult_l_h") is not None:
                merged["cl_adult_l_h"] = dossier["cl_adult_l_h"]
            if dossier.get("vd_adult_l") is not None:
                merged["vd_adult_l"] = dossier["vd_adult_l"]
            if dossier.get("fm"):
                merged["fm"] = dossier["fm"]
            if dossier.get("target_metric"):
                merged["target_metric"] = dossier["target_metric"]
            for k in ("toxic_dose_mg_per_kg_per_day", "effective_dose_mg_per_kg_per_day",
                      "oral_bioavailability"):
                if k in dossier and dossier[k] is not None:
                    merged[k] = dossier[k]
            # Pediatric HI facade (#5): bake cited HI into adult dose, then allometry.
            # Adult HI facade (#6): label lookup only — never call the engine.
            from engine.child_pugh import resolve_calculator_mode
            from engine.adult_hi import run_adult_hi_facade
            from engine.pediatric_hi import run_pediatric_hi_facade

            try:
                mode = resolve_calculator_mode(case)
            except ValueError:
                mode = "pediatric"
            if mode == "adult_hi":
                adult_hi = run_adult_hi_facade(
                    case,
                    dossier,
                    route=merged.get("route") or case.get("route"),
                )
                state["last_adult_hi"] = adult_hi
                state["last_hi_resolution"] = adult_hi.get("resolution")
                return _adult_hi_compute_payload(adult_hi, case)

            ped_hi = run_pediatric_hi_facade(
                case,
                dossier,
                fm=merged.get("fm") or dossier.get("fm") or {},
                route=merged.get("route") or case.get("route"),
            )
            state["last_pediatric_hi"] = ped_hi
            if ped_hi.get("entered"):
                merged["hepatic_function_fraction"] = 1.0
                state["last_hi_resolution"] = ped_hi.get("resolution")
                if ped_hi.get("blocked"):
                    reason = ped_hi.get("block_reason") or (
                        "SAFETY STOP — no cited applicable hepatic-impairment adjustment; abstain."
                    )
                    state["blocked_reason"] = reason
                    return {
                        "blocked": True,
                        "block_reason": reason,
                        "recommended_dose_mg_per_day": None,
                        "recommended_dose_mg_per_kg_per_day": None,
                    }
                if ped_hi.get("adult_dose_mg_per_day") is not None:
                    merged["adult_dose_mg_per_day"] = ped_hi["adult_dose_mg_per_day"]
            # Oral + unknown F: pass None so the engine hard-stops (do not invent F=1.0).
            route = (merged.get("route") or case.get("route") or "iv").lower()
            if route == "oral" and "oral_bioavailability" not in merged:
                merged["oral_bioavailability"] = None

            state["last_compute_renal_frac"] = merged.get(
                "renal_function_fraction", case.get("renal_function_fraction", 1.0)
            )
            r = compute_pediatric_dose(**merged)
            out = result_to_dict(r)
            if out.get("blocked"):
                state["blocked_reason"] = out.get("block_reason") or "not prescribable"
            else:
                # Successful non-blocked compute clears a prior engine latch only if
                # this run is prescribable (PK-not-ready never latched blocked_reason).
                state["blocked_reason"] = None
            return out
        except Exception as e:
            return {"error": str(e)}

    return _compute


def _normalize_case(case: dict) -> dict:
    """Map UI inputs to engine organ fractions; copy so we do not mutate caller.

    Renal: derive the organ-function modifier from labs (bedside Schwartz eGFR from
    serum creatinine + height). If labs are absent we apply NO reduction (fraction
    1.0) and rely on a data-gap flag — never a silent flat 0.5.
    Hepatic: no automatic clearance reduction; adjustment is drug-specific and is
    surfaced as a note (see _organ_function_flags). Child-Pugh class may be entered
    or calculated from labs (bilirubin, albumin, INR ± ascites/encephalopathy).
    """
    c = dict(case)
    from engine.child_pugh import resolve_calculator_mode

    try:
        c["calculator_mode"] = resolve_calculator_mode(c)
    except ValueError:
        c["calculator_mode"] = str(c.get("calculator_mode") or "").strip().lower() or "pediatric"
    if c["calculator_mode"] == "adult_hi":
        c["hepatic_impairment"] = True
    if "renal_function_fraction" not in c:
        frac = None
        if c.get("renal_impairment"):
            frac = renal_function_fraction_from_labs(
                c.get("height_cm"), c.get("serum_creatinine_mg_dl")
            )
            c["estimated_gfr_ml_min_1_73m2"] = estimate_gfr_bedside_schwartz(
                c.get("height_cm"), c.get("serum_creatinine_mg_dl")
            )
        c["renal_function_fraction"] = frac if frac is not None else 1.0
    if "hepatic_function_fraction" not in c:
        c["hepatic_function_fraction"] = 1.0  # drug-specific; note instead of flat modifier
    # Child-Pugh: calculate from labs when present, else keep entered A/B/C
    try:
        from engine.child_pugh import resolve_child_pugh
        cp_patch = resolve_child_pugh(c)
        c.update(cp_patch)
    except Exception:
        pass
    # Normalize allergies/conditions to clean string lists
    for key in ("allergies", "conditions"):
        raw = c.get(key)
        if raw is None:
            c[key] = []
        elif isinstance(raw, str):
            c[key] = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        elif isinstance(raw, list):
            c[key] = [str(x).strip() for x in raw if str(x).strip()]
        else:
            c[key] = []
    # Same-drug allergy token overlap → deterministic submit hard-stop (not model-optional).
    try:
        from engine.child_pugh import allergy_tokens_overlap
        hits = allergy_tokens_overlap(c.get("allergies"), c.get("drug") or "")
        if hits:
            c["allergy_name_overlap_hint"] = hits
    except Exception:
        pass
    # postnatal days → weeks for engine if provided
    if c.get("postnatal_age_days") is not None and c.get("postnatal_age_weeks") is None:
        try:
            c["postnatal_age_weeks"] = float(c["postnatal_age_days"]) / 7.0
        except (TypeError, ValueError):
            pass
    return c


def _organ_function_flags(case: dict, applied_renal_frac: float | None = None) -> list[str]:
    """Deterministic renal/hepatic-impairment flags built from the normalized case.

    Authoritative and model-independent: run_case injects these at submit time so the
    graded output always reflects what the engine actually did with organ function.
    `applied_renal_frac` is the fraction actually passed into the last compute (if any).
    """
    flags: list[str] = []
    if case.get("renal_impairment"):
        egfr = case.get("estimated_gfr_ml_min_1_73m2")
        frac = applied_renal_frac if applied_renal_frac is not None else case.get("renal_function_fraction")
        if egfr is not None and frac is not None:
            flags.append(
                f"RENAL impairment: estimated GFR ~{egfr:.0f} mL/min/1.73m^2 (bedside Schwartz "
                f"from serum creatinine + height) → renal clearance scaled to ~{float(frac):.2f}x normal. "
                "NOTE: Schwartz is the pediatric standard; Cockcroft-Gault (adult) is not used. "
                "Reassess interval and TDM for renally-cleared / narrow-TI drugs."
            )
        else:
            flags.append(
                "RENAL impairment flagged but serum creatinine and/or height were not provided — "
                "GFR was NOT estimated and NO clearance reduction was applied. Provide height + "
                "serum creatinine for a Schwartz-based estimate; reassess interval and TDM."
            )
    if case.get("hepatic_impairment"):
        cp = case.get("child_pugh")
        src = case.get("child_pugh_source")
        score = case.get("child_pugh_score")
        if cp:
            src_txt = ""
            if src == "calculated" and score is not None:
                src_txt = f" (calculated score {score})"
            elif src == "entered":
                src_txt = " (entered)"
            cp_txt = f"Child-Pugh {str(cp).upper()}{src_txt} noted; "
        else:
            cp_txt = ""
        flags.append(
            f"HEPATIC impairment: {cp_txt}dose adjustment is DRUG-SPECIFIC (depends on the drug's "
            "hepatic extraction ratio and metabolic pathway). No automatic clearance reduction was "
            "applied — consult a drug-specific hepatic-impairment reference; further research required."
        )
        age = case.get("age_years")
        try:
            if cp and age is not None and float(age) < 18:
                from engine.child_pugh import CHILD_PUGH_ON_CHILD_FLAG
                flags.append(CHILD_PUGH_ON_CHILD_FLAG)
        except (TypeError, ValueError):
            pass
    return flags


def _apply_organ_function_flags(
    rec: dict, case: dict, applied_renal_frac: float | None = None,
) -> None:
    """Replace any renal/hepatic-impairment flags with the authoritative deterministic ones."""
    kept = [
        f for f in (rec.get("flags") or [])
        if not str(f).startswith(("RENAL impairment", "HEPATIC impairment"))
    ]
    kept.extend(_organ_function_flags(case, applied_renal_frac=applied_renal_frac))
    rec["flags"] = kept


def run_case(case: dict, on_step=None, max_turns: int = 12) -> dict:
    """Run one dosing case end-to-end."""
    case = _normalize_case(case)
    from engine.child_pugh import hi_gate_error, resolve_calculator_mode

    gate = hi_gate_error(case)
    if gate:
        if on_step:
            on_step(gate)
        return {"error": gate, "recommendation": None}
    try:
        mode = resolve_calculator_mode(case)
    except ValueError:
        mode = "pediatric"
    if mode == "adult_hi":
        return _run_adult_hi_case(case, on_step=on_step)
    if mode == "pbpk":
        # Trial PBPK-translation facade (branch muse-spark-pbpk): deterministic,
        # no orchestrator, no key, no A-D. Axe with the branch.
        from engine.pbpk_vancomycin import run_pbpk_case
        return run_pbpk_case(case, on_step=on_step)
    client = Anthropic()
    user_msg = (
        "Dose this case. Follow your pipeline and finish with submit_recommendation.\n\n"
        f"Case: {json.dumps(case)}"
    )
    trace: list[str] = []
    in_tok = out_tok = cache_read = cache_write = 0
    retr_in = retr_out = 0
    # Deterministic safety state shared with tool handlers (not model-trust).
    state: dict = {
        "blocked_reason": None,   # engine / route / toxic hard-stop
        "pk_ok": False,           # True after live/cache dossier with CL+Vd
        "pk_block_reason": None,  # sticky when retrieval unavailable / null PK
        "last_dossier": None,
        "last_compute_renal_frac": case.get("renal_function_fraction"),
    }
    # Prefetch shared PK cache so a repeat drug skips the retrieval subagent.
    cached = PK_CACHE.get(case.get("drug") or "", case.get("indication"))
    cached_dossier = (cached or {}).get("dossier") if cached else None
    if cached_dossier and _dossier_core_pk_ok(cached_dossier):
        state["pk_ok"] = True
        state["pk_block_reason"] = None
        state["last_dossier"] = cached_dossier
        user_msg += (
            "\n\nPK dossier already retrieved (source_mode=cache). "
            "Do NOT call retrieve_drug_data unless this dossier is missing CL or Vd. "
            "Use it for compute_pediatric_dose.\n"
            + json.dumps(cached_dossier, default=str)[:4000]
        )
        if on_step:
            on_step("pk_cache hit — skipped live retrieval")
        trace.append("pk_cache hit — skipped live retrieval")
    messages = [{"role": "user", "content": user_msg}]
    local_tools = {
        "compute_pediatric_dose": _build_compute(case, state),
        "load_skill": lambda a: load_skill(a.get("name", "")),
        "assess_edge_cases": _assess_edge_cases,
    }

    for _ in range(max_turns):
        resp = client.messages.create(
            model=ORCHESTRATOR_MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
            cache_control={"type": "ephemeral"},
        )
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens
        cache_read += getattr(resp.usage, "cache_read_input_tokens", 0) or 0
        cache_write += getattr(resp.usage, "cache_creation_input_tokens", 0) or 0

        tool_uses = []
        for block in resp.content:
            if block.type == "text" and block.text.strip():
                trace.append(block.text.strip())
                if on_step:
                    on_step(block.text.strip())
            elif block.type == "tool_use":
                tool_uses.append(block)
            elif block.type == "server_tool_use" and getattr(block, "name", "") == "web_search":
                q = ""
                if isinstance(getattr(block, "input", None), dict):
                    q = block.input.get("query", "")
                if on_step:
                    on_step(f"→ web_search — finding pediatric guideline{(': ' + q) if q else ' …'}")

        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            break

        tool_results = []
        for tu in tool_uses:
            if tu.name == "submit_recommendation":
                rec = dict(tu.input) if tu.input else {}
                from engine.child_pugh import resolve_calculator_mode as _rmode_early
                try:
                    _facade_early = _rmode_early(case)
                except ValueError:
                    _facade_early = "pediatric"
                # 1) PK cite-or-abstain: never allow a pediatric dose without retrieval.
                # Adult HI is a label lookup and does not need CL/Vd.
                if _facade_early != "adult_hi" and (
                    state.get("pk_block_reason") or not state.get("pk_ok")
                ):
                    reason = state.get("pk_block_reason") or (
                        "SAFETY STOP — adult PK was not retrieved (or was null); "
                        "abstain, do not invent numbers (grade D)."
                    )
                    _force_safety_block(rec, reason)
                # 2) Engine hard stop (route / toxic / empty fm / …).
                if state.get("blocked_reason"):
                    _force_safety_block(rec, state["blocked_reason"])
                # 3) Deterministic same-drug allergy hard-stop (token overlap).
                allergy_hits = case.get("allergy_name_overlap_hint") or []
                if allergy_hits:
                    hits_txt = ", ".join(str(h) for h in allergy_hits)
                    reason = (
                        f"SAFETY STOP — CONTRAINDICATED: allergy matches drug name "
                        f"({hits_txt})."
                    )
                    _force_safety_block(rec, reason, flag_token="CONTRAINDICATED")
                    rec["contraindication_matched"] = rec.get("contraindication_matched") or hits_txt
                # 4) Model-reported contraindication hard-stop.
                matched = rec.get("contraindication_matched")
                matched_s = str(matched).strip() if matched is not None else ""
                br = str(rec.get("block_reason") or "")
                ci_hit = bool(matched_s) or "CONTRAINDICATED" in br.upper()
                if ci_hit:
                    reason = br if "CONTRAINDICATED" in br.upper() else (
                        f"SAFETY STOP — CONTRAINDICATED: {matched_s or br or 'patient matches a listed contraindication'}"
                    )
                    if not reason.upper().startswith("SAFETY"):
                        reason = f"SAFETY STOP — CONTRAINDICATED: {reason}"
                    _force_safety_block(rec, reason, flag_token="CONTRAINDICATED")
                # Ensure avoid-list is always a list (even if model omitted)
                avoid = rec.get("contraindications_avoid")
                if not isinstance(avoid, list):
                    rec["contraindications_avoid"] = []
                # Authoritative renal/hepatic-impairment flags (model-independent).
                _apply_organ_function_flags(
                    rec, case, applied_renal_frac=state.get("last_compute_renal_frac"),
                )
                from engine.adult_hi import (
                    merge_adult_hi_into_recommendation,
                    run_adult_hi_facade,
                )
                from engine.pediatric_hi import (
                    merge_pediatric_hi_into_recommendation,
                    run_pediatric_hi_facade,
                )
                from engine.child_pugh import resolve_calculator_mode as _rmode
                try:
                    _facade = _rmode(case)
                except ValueError:
                    _facade = "pediatric"
                if _facade == "adult_hi":
                    adult_hi = state.get("last_adult_hi")
                    if adult_hi is None:
                        dossier = state.get("last_dossier") or {}
                        adult_hi = run_adult_hi_facade(
                            case, dossier, route=case.get("route"),
                        )
                        state["last_adult_hi"] = adult_hi
                    if adult_hi.get("blocked"):
                        rec["final_dose_mg_per_kg_per_day"] = None
                        rec["final_dose_mg_per_day"] = None
                        rec["blocked"] = True
                        rec["block_reason"] = adult_hi.get("block_reason")
                    merge_adult_hi_into_recommendation(rec, adult_hi)
                else:
                    ped_hi = state.get("last_pediatric_hi")
                    if ped_hi is None:
                        dossier = state.get("last_dossier") or {}
                        ped_hi = run_pediatric_hi_facade(
                            case, dossier, fm=dossier.get("fm") or {},
                        )
                        state["last_pediatric_hi"] = ped_hi
                    if ped_hi.get("blocked"):
                        _force_safety_block(
                            rec,
                            ped_hi.get("block_reason")
                            or "SAFETY STOP — no cited applicable hepatic-impairment adjustment; abstain.",
                        )
                    merge_pediatric_hi_into_recommendation(rec, ped_hi)
                attach_administration(rec, case)
                return {
                    "recommendation": rec,
                    "trace": trace,
                    "usage": {"input_tokens": in_tok, "output_tokens": out_tok,
                              "cache_read_input_tokens": cache_read,
                              "cache_creation_input_tokens": cache_write,
                              "retrieval_input_tokens": retr_in,
                              "retrieval_output_tokens": retr_out,
                              "retrieval_model": retrieval.RETRIEVAL_MODEL,
                              "model": ORCHESTRATOR_MODEL},
                }
            if tu.name == "retrieve_drug_data":
                if on_step:
                    on_step(f"→ retrieve_drug_data({tu.input.get('drug')}) …")
                rout = retrieval.fetch(tu.input["drug"], tu.input.get("indication"))
                retr_in += rout["usage"].get("input_tokens", 0)
                retr_out += rout["usage"].get("output_tokens", 0)
                dossier = rout.get("dossier") or {}
                mode = rout.get("source_mode") or "unavailable"
                if on_step:
                    if mode == "cache":
                        on_step("→ pk_cache hit — skipped live PubMed/openFDA")
                    elif mode == "live":
                        on_step("→ retrieve_drug_data — live PubMed/openFDA")
                # Latch retrieval outcome — product path never invents PK after fail/null.
                if mode == "unavailable" or not _dossier_core_pk_ok(dossier):
                    state["pk_ok"] = False
                    state["last_dossier"] = dossier
                    conf = (dossier.get("confidence") or "").strip()
                    state["pk_block_reason"] = (
                        "SAFETY STOP — PK retrieval unavailable or core adult PK (CL/Vd) "
                        f"null (source_mode={mode}"
                        + (f"; {conf}" if conf else "")
                        + "). Abstain — do not invent numbers (grade D)."
                    )
                    if on_step:
                        on_step(f"→ retrieval {mode} — PK abstain latched")
                else:
                    state["pk_ok"] = True
                    state["pk_block_reason"] = None
                    state["last_dossier"] = dossier
                payload = {
                    "source_mode": mode,
                    "dossier": dossier,
                }
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": json.dumps(payload),
                })
            elif tu.name in local_tools:
                if on_step:
                    on_step(f"→ {tu.name} …")
                out = local_tools[tu.name](tu.input)
                if tu.name == "compute_pediatric_dose" and isinstance(out, dict) and out.get("blocked"):
                    state["blocked_reason"] = out.get("block_reason") or state.get("blocked_reason") or "not prescribable"
                    if on_step:
                        on_step(f"→ SAFETY STOP — {state['blocked_reason']}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(out),
                })
        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return {
        "recommendation": None,
        "trace": trace,
        "error": "Agent did not submit a recommendation within the turn budget.",
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok,
                  "cache_read_input_tokens": cache_read,
                  "cache_creation_input_tokens": cache_write,
                  "retrieval_input_tokens": retr_in,
                  "retrieval_output_tokens": retr_out,
                  "retrieval_model": retrieval.RETRIEVAL_MODEL,
                  "model": ORCHESTRATOR_MODEL},
    }


if __name__ == "__main__":
    import sys
    demo = {"drug": "vancomycin", "indication": "sepsis", "age_years": 6,
            "weight_kg": 20, "renal_impairment": False, "hepatic_impairment": False}
    if len(sys.argv) > 1:
        demo["drug"] = sys.argv[1]
    out = run_case(demo, on_step=lambda s: print("  ·", s[:120]))
    print("\n=== RECOMMENDATION ===")
    print(json.dumps(out["recommendation"], indent=2))
    print("usage:", out["usage"])
