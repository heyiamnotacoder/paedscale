"""Elimination pathway decomposition (the fm split) — the core reasoning moat.

Given a drug, decide which elimination pathway(s) dominate its clearance and
what fraction of clearance each accounts for. This decides which maturation
curve(s) apply (concept: "Decompose elimination pathways... the step that
decides which maturation curves apply"). Curated for the three in-scope
drugs; Claude-derived for anything else, constrained to the pathways
PaedScale has maturation data for.
"""

import json
from pathlib import Path

from app.agent.client import call_structured

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

KNOWN_PATHWAYS = ("CYP3A4", "renal_GFR", "UGT2B7")

PATHWAY_SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_pathway": {
            "type": "string",
            "enum": list(KNOWN_PATHWAYS),
            "description": "The single dominant elimination pathway PaedScale should apply maturation scaling to.",
        },
        "fm_primary": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Fraction of total clearance attributable to the primary pathway.",
        },
        "rationale": {
            "type": "string",
            "description": "Brief mechanistic justification for the pathway assignment and fm split.",
        },
        "confidence": {"type": "string", "enum": ["high", "moderate", "low"]},
    },
    "required": ["primary_pathway", "fm_primary", "rationale", "confidence"],
}


def _load_curated_drugs() -> dict:
    with open(DATA_DIR / "drugs.json") as f:
        return json.load(f)


def get_pathway_split(drug_name: str) -> dict:
    """Return the dominant elimination pathway and fm split for a drug."""
    curated = _load_curated_drugs()
    key = drug_name.strip().lower()
    if key in curated:
        entry = curated[key]
        return {
            "primary_pathway": entry["primary_pathway"],
            "fm_primary": entry["fm_primary"],
            "rationale": entry["notes"],
            "confidence": "high",
        }

    system = (
        "You are decomposing a drug's elimination into the pathway that dominates "
        "its clearance, for a pediatric dose-extrapolation tool. You may only choose "
        f"from these modelled pathways, each with its own maturation curve: {', '.join(KNOWN_PATHWAYS)}. "
        "If the drug's true elimination doesn't cleanly map to one of these, pick the "
        "closest mechanistic match, set confidence to 'low', and say so in the rationale."
    )
    user = f"Decompose the dominant elimination pathway and fm split for: {drug_name}"
    return call_structured(system, user, "pathway_split", PATHWAY_SPLIT_SCHEMA)
