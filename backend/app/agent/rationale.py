"""Synthesis: cited rationale, uncertainty/data-gap flags, NTI warnings, and
concordance narrative (concept: "Explain, flag, and self-check").

All numbers (dose, clearance, maturation fraction, concordance ratio) are
computed upstream in app.pk and passed in here as facts. This step only
writes the auditable explanation around those facts — it never invents or
adjusts a number.
"""

from app.agent.client import call_structured

RATIONALE_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {
            "type": "string",
            "description": (
                "Full auditable explanation: adult PK used, elimination pathway and fm "
                "split, maturation fraction applied, and how the recommended dose was "
                "derived. Written for a prescribing clinician."
            ),
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Explicit list of assumptions made in this estimate.",
        },
        "uncertainty_flags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific reasons for caution: sparse adult PK, low pathway-assignment confidence, extreme prematurity, etc.",
        },
        "narrow_therapeutic_index_warning": {
            "type": "string",
            "description": "If applicable, a warning recommending therapeutic drug monitoring instead of standalone dosing. Empty string if not applicable.",
        },
        "concordance_summary": {
            "type": "string",
            "description": "One or two sentences on how the estimate compares to any known guideline dose, and — if divergent — why.",
        },
    },
    "required": [
        "rationale",
        "assumptions",
        "uncertainty_flags",
        "narrow_therapeutic_index_warning",
        "concordance_summary",
    ],
}


def synthesize_rationale(facts: dict) -> dict:
    """Generate the cited rationale + flags from precomputed pipeline facts.

    `facts` should include: drug name, indication, child covariates, adult PK
    (with sources/confidence), pathway split (with rationale/confidence),
    maturation fraction, recommended dose, and — if available — the
    guideline comparison (guideline dose, ratio, source).
    """
    system = (
        "You write the auditable clinical rationale for a pediatric dose-extrapolation "
        "tool (PaedScale). You are given the already-computed pharmacometric facts — do "
        "not recompute or alter any numeric value. Explain the derivation clearly for a "
        "prescribing clinician, state assumptions and uncertainty explicitly, flag "
        "narrow-therapeutic-index drugs for therapeutic drug monitoring, and summarize "
        "concordance with any known guideline dose. This is decision support, not an "
        "autonomous prescribing order — never imply otherwise."
    )
    user = f"Pipeline facts (JSON):\n{facts}"
    result = call_structured(system, user, "rationale", RATIONALE_SCHEMA)

    # The Anthropic tool-use "required" list is advisory, not enforced: the model
    # can still omit a field. Fill in safe defaults rather than let a schema
    # validation error surface as a 500 to the caller.
    result.setdefault("assumptions", [])
    result.setdefault("uncertainty_flags", [])
    result.setdefault("narrow_therapeutic_index_warning", "")
    result.setdefault("concordance_summary", "")
    return result
