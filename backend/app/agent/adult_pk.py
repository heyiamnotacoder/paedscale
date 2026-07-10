"""Adult PK retrieval via Claude.

PaedScale no longer prefills a curated drug set — it generalises to any drug
with adult PK (concept: "Coverage — the guideline set is the minority"). Given a
drug name, Claude retrieves and annotates adult clearance, volume of distribution,
bioavailability, and protein binding, with explicit confidence and citation notes.

In the multi-agent build (Phase 2) this is superseded by the `pk-agent` subagent,
which grounds each value in a literature search (PubMed / Semantic Scholar / web)
rather than model recall alone. This module is retained as the single-call
fallback and to keep the schema in one place.
"""

from app.agent.client import call_structured

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


def get_adult_pk(drug_name: str) -> dict:
    """Return standard adult PK parameters for a drug via a structured Claude call."""
    system = (
        "You are a clinical pharmacology reference assistant supporting a pediatric "
        "dose-extrapolation tool. Given a drug name, return its standard adult "
        "pharmacokinetic parameters (70 kg reference adult, IV or the most common "
        "route for the indication). Be conservative: prefer well-established "
        "literature values, and flag low confidence rather than guessing precisely."
    )
    user = f"Retrieve adult PK parameters for: {drug_name}"
    result = call_structured(system, user, "adult_pk", ADULT_PK_SCHEMA)
    result.setdefault("primary_pathway", None)
    result.setdefault("fm_primary", None)
    return result
