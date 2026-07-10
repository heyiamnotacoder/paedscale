"""Deterministic pharmacometric tools for the Messages-API orchestrator (box ② PK MATHS).

This is how the golden rule is enforced at runtime: the LLM never does arithmetic. To
get a number it must call one of these tools, each a thin wrapper over the pinned, tested
functions in `app.pk`. The model supplies judgment (which pathways, which method, which
targets); Python returns the math.

Exposed as plain Anthropic tool-definition dicts + an async dispatcher (no MCP server, no
Node subprocess). `run_math_tool(name, args)` returns a JSON-serialisable dict.
"""

import json
from pathlib import Path

from app.pk.concordance import find_concordance as _find_concordance
from app.pk.distribution import protein_binding_from_albumin
from app.pk.maturation import Pathway
from app.pk.methods import METHODS
from app.pk.organ_function import organ_modifiers as _organ_modifiers
from app.pk.organ_function import schwartz_egfr
from app.pk.pipeline import ChildCovariates, extrapolate_generalized
from app.pk.safety import check_bounds

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_MATURATION_LIBRARY: dict | None = None


def _load_maturation_library() -> dict:
    """Load maturation curves once per process (read-only library)."""
    global _MATURATION_LIBRARY
    if _MATURATION_LIBRARY is None:
        with open(DATA_DIR / "maturation.json") as f:
            _MATURATION_LIBRARY = json.load(f)
    return _MATURATION_LIBRARY


# --------------------------------------------------------------------------- #
# Tool implementations (plain async functions returning JSON-able dicts).      #
# --------------------------------------------------------------------------- #


async def _list_pathways(args: dict) -> dict:
    return {"pathways": _load_maturation_library()}


async def _extrapolate_dose(args: dict) -> dict:
    library = _load_maturation_library()

    pathways: list[Pathway] = []
    resolved = []
    for p in args["pathways"]:
        name = p["name"]
        curve = library.get(name, {})
        tm50 = p.get("tm50_weeks", curve.get("tm50_weeks"))
        hill = p.get("hill", curve.get("hill"))
        organ = p.get("organ", curve.get("organ", "other"))
        if tm50 is None or hill is None:
            return {
                "error": f"No maturation curve for pathway '{name}'. "
                "Call list_pathways or supply tm50_weeks and hill explicitly."
            }
        pathways.append(
            Pathway(fm=float(p["fm"]), tm50_weeks=float(tm50), hill=float(hill), name=name, organ=organ)
        )
        resolved.append({"name": name, "fm": p["fm"], "tm50_weeks": tm50, "hill": hill, "organ": organ})

    # Organ function: prefer an explicit eGFR, else derive from height + SCr.
    egfr = args.get("egfr_ml_min_1_73")
    if egfr is None and args.get("height_cm") and args.get("serum_creatinine_mg_dl"):
        egfr = schwartz_egfr(args["height_cm"], args["serum_creatinine_mg_dl"])
    mods = _organ_modifiers(egfr_ml_min_1_73=egfr, child_pugh_score=args.get("child_pugh_score"))

    adult_pb = args.get("adult_protein_binding", 0.5)
    child_pb = None
    if args.get("child_albumin_g_dl"):
        child_pb = protein_binding_from_albumin(adult_pb, args["child_albumin_g_dl"])

    result = extrapolate_generalized(
        adult_clearance_l_per_h=args["adult_clearance_l_per_h"],
        adult_volume_l=args["adult_volume_l"],
        adult_protein_binding=adult_pb,
        pathways=pathways,
        child=ChildCovariates(
            weight_kg=args["weight_kg"], pma_weeks=args["pma_weeks"], protein_binding=child_pb
        ),
        method=args["method"],
        method_params=args.get("method_params") or {},
        organ_modifiers=mods,
    )
    return {
        "child_clearance_l_per_h": round(result.child_clearance_l_per_h, 4),
        "child_volume_l": round(result.child_volume_l, 4),
        "maturation_fraction": round(result.maturation_fraction, 4),
        "effective_clearance_fraction": round(result.effective_clearance_fraction, 4),
        "organ_modifiers_applied": mods,
        "resolved_pathways": resolved,
        "estimated_egfr_ml_min_1_73": round(egfr, 2) if egfr is not None else None,
        "dose": {
            "dose_mg": round(result.dose.dose_mg, 4),
            "dose_mg_per_kg": round(result.dose.dose_mg_per_kg, 5),
            "interval_h": result.dose.interval_h,
            "method": result.dose.method,
            "matched_metric": result.dose.matched_metric,
        },
    }


async def _check_safety_bounds(args: dict) -> dict:
    r = check_bounds(
        args["dose_mg_per_kg"],
        args.get("min_effective_mg_per_kg"),
        args.get("max_safe_mg_per_kg"),
    )
    return dict(r.__dict__)


async def _find_concordance(args: dict) -> dict:
    cases = args["guideline_cases"]
    for c in cases:
        c.setdefault("age_group", "unspecified")
        c.setdefault("source", "literature")
    r = _find_concordance(args["pma_weeks"], args["predicted_dose_mg_per_kg"], cases)
    return dict(r.__dict__)


# --------------------------------------------------------------------------- #
# Anthropic tool definitions (name / description / input_schema).              #
# --------------------------------------------------------------------------- #

_EXTRAPOLATE_SCHEMA = {
    "type": "object",
    "properties": {
        "adult_clearance_l_per_h": {"type": "number"},
        "adult_volume_l": {"type": "number"},
        "adult_protein_binding": {"type": "number", "default": 0.5},
        "weight_kg": {"type": "number"},
        "pma_weeks": {"type": "number", "description": "Postmenstrual age = gestational + postnatal, in weeks."},
        "pathways": {
            "type": "array",
            "description": "Every elimination route with its fraction of clearance (fm). fm's are "
            "normalised. Omit tm50_weeks/hill/organ to use the curated library curve for that name.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "fm": {"type": "number"},
                    "tm50_weeks": {"type": "number"},
                    "hill": {"type": "number"},
                    "organ": {"type": "string", "enum": ["hepatic", "renal", "other"]},
                },
                "required": ["name", "fm"],
            },
        },
        "method": {"type": "string", "enum": list(METHODS)},
        "method_params": {
            "type": "object",
            "description": "Method-specific inputs, e.g. {adult_reference_dose_mg, adult_interval_h} "
            "for 'auc'; {css_target_mg_per_l, interval_h} for 'css'; {cmax_target_mg_per_l} for "
            "'cmax'; {c_target_mg_per_l} for 'loading'; {ctrough_target_mg_per_l, interval_h} for "
            "'trough'; {adult_reference_dose_mg, adult_weight_kg} for 'mgkg_linear'.",
        },
        "egfr_ml_min_1_73": {"type": "number", "description": "Measured/estimated GFR or CrCl, if known."},
        "height_cm": {"type": "number", "description": "Used with serum_creatinine to derive eGFR (Schwartz)."},
        "serum_creatinine_mg_dl": {"type": "number"},
        "child_pugh_score": {"type": "integer", "description": "5-15; drives the hepatic modifier."},
        "child_albumin_g_dl": {"type": "number", "description": "If known, refines the free-fraction Vd correction."},
    },
    "required": ["adult_clearance_l_per_h", "adult_volume_l", "weight_kg", "pma_weeks", "pathways", "method"],
}

MATH_TOOLS = [
    {
        "name": "list_pathways",
        "description": "List the modelled elimination pathways and their maturation curves "
        "(tm50 in weeks PMA, Hill coefficient, dependent organ). Use these curated curves; do not "
        "invent tm50/hill values.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "extrapolate_dose",
        "description": "Compute the pediatric dose deterministically: allometric size scaling × "
        "multi-pathway maturation × per-organ function, then solve by the chosen method. Returns "
        "child clearance, volume, maturation fraction, organ modifiers, and the dose. This is the "
        "ONLY way to obtain a mechanistic dose.",
        "input_schema": _EXTRAPOLATE_SCHEMA,
    },
    {
        "name": "check_safety_bounds",
        "description": "Verify a mg/kg dose sits within [min_effective, max_safe]. Clamps to the "
        "nearest bound and flags if outside. Either bound may be omitted if unknown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dose_mg_per_kg": {"type": "number"},
                "min_effective_mg_per_kg": {"type": "number"},
                "max_safe_mg_per_kg": {"type": "number"},
            },
            "required": ["dose_mg_per_kg"],
        },
    },
    {
        "name": "find_concordance",
        "description": "Compare the predicted mg/kg dose against published pediatric guideline cases "
        "(supplied from the literature) at the nearest matching PMA.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pma_weeks": {"type": "number"},
                "predicted_dose_mg_per_kg": {"type": "number"},
                "guideline_cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "age_group": {"type": "string"},
                            "pma_weeks": {"type": "number"},
                            "guideline_dose_mg_per_kg": {"type": "number"},
                            "source": {"type": "string"},
                        },
                        "required": ["pma_weeks", "guideline_dose_mg_per_kg"],
                    },
                },
            },
            "required": ["pma_weeks", "predicted_dose_mg_per_kg", "guideline_cases"],
        },
    },
]

_DISPATCH = {
    "list_pathways": _list_pathways,
    "extrapolate_dose": _extrapolate_dose,
    "check_safety_bounds": _check_safety_bounds,
    "find_concordance": _find_concordance,
}

MATH_TOOL_NAMES = list(_DISPATCH)


def is_math_tool(name: str) -> bool:
    return name in _DISPATCH


async def run_math_tool(name: str, args: dict) -> dict:
    """Dispatch a PK-maths tool call. Raises KeyError for an unknown tool."""
    return await _DISPATCH[name](args or {})
