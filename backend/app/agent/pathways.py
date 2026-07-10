"""Elimination pathway decomposition (the fm split) — the core reasoning moat.

Given a drug, decide which elimination pathway(s) dominate its clearance and
what fraction of clearance each accounts for. This decides which maturation
curve(s) apply (concept: "Decompose elimination pathways... the step that
decides which maturation curves apply").

The set of modelled pathways is read dynamically from `data/maturation.json`,
so expanding the maturation curve library automatically widens what the model
may choose from — no hardcoded pathway list. In the multi-agent build (Phase 2)
this is superseded by the `pathway-agent` subagent, which returns a *multi*-
pathway split (a list of fm fractions, not a single dominant pathway) grounded
in a literature search. This module is retained as the single-call fallback.
"""

import json
from pathlib import Path

from app.agent.client import call_structured

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def known_pathways() -> list[str]:
    """Modelled elimination pathways, from the maturation curve library."""
    with open(DATA_DIR / "maturation.json") as f:
        return sorted(json.load(f).keys())


def _pathway_split_schema() -> dict:
    pathways = known_pathways()
    return {
        "type": "object",
        "properties": {
            "primary_pathway": {
                "type": "string",
                "enum": pathways,
                "description": "The dominant elimination pathway to apply maturation scaling to.",
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


def get_pathway_split(drug_name: str) -> dict:
    """Return the dominant elimination pathway and fm split for a drug via Claude."""
    pathways = known_pathways()
    system = (
        "You are decomposing a drug's elimination into the pathway that dominates "
        "its clearance, for a pediatric dose-extrapolation tool. You may only choose "
        f"from these modelled pathways, each with its own maturation curve: {', '.join(pathways)}. "
        "If the drug's true elimination doesn't cleanly map to one of these, pick the "
        "closest mechanistic match, set confidence to 'low', and say so in the rationale."
    )
    user = f"Decompose the dominant elimination pathway and fm split for: {drug_name}"
    return call_structured(system, user, "pathway_split", _pathway_split_schema())
