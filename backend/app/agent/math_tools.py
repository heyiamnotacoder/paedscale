"""Deterministic pharmacometric tools, exposed to the orchestrator as an
in-process MCP server.

This module is how the golden rule is *enforced* at runtime: the LLM never does
arithmetic. To get a number it must call one of these tools, each a thin wrapper
over the pinned, tested functions in `app.pk`. The model supplies judgment
(which pathways, which method, which targets); Python returns the math.
"""

import json
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from app.pk.concordance import find_concordance as _find_concordance
from app.pk.maturation import Pathway, maturation_fraction
from app.pk.methods import METHODS
from app.pk.organ_function import organ_modifiers as _organ_modifiers
from app.pk.organ_function import schwartz_egfr
from app.pk.pipeline import ChildCovariates, extrapolate_generalized
from app.pk.safety import check_bounds
from app.pk.distribution import protein_binding_from_albumin

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_maturation_library() -> dict:
    with open(DATA_DIR / "maturation.json") as f:
        return json.load(f)


def _text(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


@tool(
    "list_pathways",
    "List the modelled elimination pathways and their maturation curves "
    "(tm50 in weeks PMA, Hill coefficient, dependent organ). Use these curated "
    "curves; do not invent tm50/hill values.",
    {"type": "object", "properties": {}},
)
async def list_pathways(args):
    return _text({"pathways": _load_maturation_library()})


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
            "description": "Every elimination route with its fraction of clearance (fm). "
            "fm's should sum to ~1 (they are normalised). Omit tm50_weeks/hill/organ to "
            "use the curated library curve for that pathway name.",
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


@tool(
    "extrapolate_dose",
    "Compute the pediatric dose deterministically: allometric size scaling × "
    "multi-pathway maturation × per-organ function, then solve by the chosen "
    "method. Returns child clearance, volume, maturation fraction, the organ "
    "modifiers applied, and the dose. This is the only way to obtain a dose.",
    _EXTRAPOLATE_SCHEMA,
)
async def extrapolate_dose(args):
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
            return _text({"error": f"No maturation curve for pathway '{name}'. "
                          "Call list_pathways or supply tm50_weeks and hill explicitly."})
        pathways.append(Pathway(fm=float(p["fm"]), tm50_weeks=float(tm50), hill=float(hill), name=name, organ=organ))
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
        child=ChildCovariates(weight_kg=args["weight_kg"], pma_weeks=args["pma_weeks"], protein_binding=child_pb),
        method=args["method"],
        method_params=args.get("method_params") or {},
        organ_modifiers=mods,
    )
    return _text({
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
    })


@tool(
    "check_safety_bounds",
    "Verify a mg/kg dose sits within [min_effective, max_safe]. Clamps to the "
    "nearest bound and flags if outside. Either bound may be omitted if unknown.",
    {
        "type": "object",
        "properties": {
            "dose_mg_per_kg": {"type": "number"},
            "min_effective_mg_per_kg": {"type": "number"},
            "max_safe_mg_per_kg": {"type": "number"},
        },
        "required": ["dose_mg_per_kg"],
    },
)
async def check_safety_bounds(args):
    r = check_bounds(
        args["dose_mg_per_kg"],
        args.get("min_effective_mg_per_kg"),
        args.get("max_safe_mg_per_kg"),
    )
    return _text(r.__dict__)


@tool(
    "find_concordance",
    "Compare the predicted mg/kg dose against published pediatric guideline "
    "cases (supplied from the literature search) at the nearest matching PMA.",
    {
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
)
async def find_concordance(args):
    cases = args["guideline_cases"]
    for c in cases:
        c.setdefault("age_group", "unspecified")
        c.setdefault("source", "literature")
    r = _find_concordance(args["pma_weeks"], args["predicted_dose_mg_per_kg"], cases)
    return _text(r.__dict__)


def build_math_server():
    """The 'paedscale_math' in-process MCP server."""
    return create_sdk_mcp_server(
        "paedscale_math",
        tools=[list_pathways, extrapolate_dose, check_safety_bounds, find_concordance],
    )


MATH_TOOL_NAMES = [
    "mcp__paedscale_math__list_pathways",
    "mcp__paedscale_math__extrapolate_dose",
    "mcp__paedscale_math__check_safety_bounds",
    "mcp__paedscale_math__find_concordance",
]
