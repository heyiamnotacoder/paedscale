"""Adult PK retrieval: curated data first, Claude fills gaps.

For the three in-scope drugs, `data/drugs.json` is authoritative (curated
from standard pharmacology references) and used directly for the demo path.
For any other drug, Claude retrieves and annotates adult clearance, volume
of distribution, bioavailability, and protein binding from its knowledge,
with explicit confidence/citation notes — this is what lets PaedScale
generalise beyond the curated set (concept: "Coverage — the guideline set
is the minority").
"""

import json
from pathlib import Path

from app.agent.client import call_structured

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ADULT_PK_SCHEMA = {
    "type": "object",
    "properties": {
        "adult_clearance_l_per_h": {"type": "number"},
        "adult_volume_l": {"type": "number"},
        "adult_protein_binding": {"type": "number", "minimum": 0, "maximum": 1},
        "bioavailability": {"type": "number", "minimum": 0, "maximum": 1},
        "confidence": {
            "type": "string",
            "enum": ["high", "moderate", "low"],
            "description": "Confidence in these adult PK values given available literature.",
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Brief citations or reference basis for each value (label, textbook, or well-known study).",
        },
        "data_gap_notes": {
            "type": "string",
            "description": "Any gaps, assumptions, or population caveats in the adult PK estimate.",
        },
    },
    "required": [
        "adult_clearance_l_per_h",
        "adult_volume_l",
        "adult_protein_binding",
        "confidence",
        "sources",
    ],
}


def _load_curated_drugs() -> dict:
    with open(DATA_DIR / "drugs.json") as f:
        return json.load(f)


def get_adult_pk(drug_name: str) -> dict:
    """Return adult PK for a drug: curated entry if in scope, else a Claude lookup."""
    curated = _load_curated_drugs()
    key = drug_name.strip().lower()
    if key in curated:
        entry = curated[key]
        return {
            "adult_clearance_l_per_h": entry["adult_clearance_l_per_h"],
            "adult_volume_l": entry["adult_volume_l"],
            "adult_protein_binding": entry["adult_protein_binding"],
            "primary_pathway": entry["primary_pathway"],
            "fm_primary": entry["fm_primary"],
            "confidence": "high",
            "sources": ["Curated reference PK (PaedScale demo dataset)"],
            "data_gap_notes": "",
        }

    system = (
        "You are a clinical pharmacology reference assistant supporting a pediatric "
        "dose-extrapolation tool. Given a drug name, return its standard adult "
        "pharmacokinetic parameters (70 kg reference adult, IV or the most common "
        "route for the indication). Be conservative: prefer well-established "
        "literature values, and flag low confidence rather than guessing precisely."
    )
    user = f"Retrieve adult PK parameters for: {drug_name}"
    result = call_structured(system, user, "adult_pk", ADULT_PK_SCHEMA)
    result["primary_pathway"] = None
    result["fm_primary"] = None
    return result
