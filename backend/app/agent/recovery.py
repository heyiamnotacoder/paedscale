"""Best-effort assembly of a recommendation when submit_recommendation never ran.

The orchestrator captures each successful math-tool result during its loop; if the model exits
without submitting, we build a minimal, honest payload from those results so the UI is never blank
after a paid run.
"""

from __future__ import annotations

import re
from typing import Any


def assemble_partial_payload(math_results: dict, query: str = "") -> dict[str, Any] | None:
    """Build a minimal ExtrapolationResponse-shaped dict from captured math results, or None."""
    extrap = math_results.get("extrapolate_dose")
    if not extrap or not isinstance(extrap.get("dose"), dict):
        return None

    dose = extrap["dose"]
    safety = math_results.get("check_safety_bounds") or {}
    concordance = math_results.get("find_concordance")

    safety_bounds = {
        "min_effective_mg_per_kg": safety.get("min_effective_mg_per_kg"),
        "max_safe_mg_per_kg": safety.get("max_safe_mg_per_kg"),
        "within": safety.get("within", True),
        "clamped_mg_per_kg": safety.get("clamped_mg_per_kg"),
        "flag": safety.get("flag"),
    }

    pathways = [
        {
            "name": p.get("name", "unknown"),
            "fm": p.get("fm", 0),
            "organ": p.get("organ", "other"),
            "tm50_weeks": p.get("tm50_weeks"),
            "hill": p.get("hill"),
        }
        for p in (extrap.get("resolved_pathways") or [])
    ]

    return {
        "drug_name": _guess_drug_name(query),
        "covariates": {},
        "adult_pk": {},
        "pathways": pathways,
        "dosing_method": dose.get("method") or "",
        "dose_recommendation": {
            "dose_mg": dose.get("dose_mg"),
            "dose_mg_per_kg": dose.get("dose_mg_per_kg"),
            "interval_h": dose.get("interval_h"),
            "method": dose.get("method") or "",
            "matched_metric": dose.get("matched_metric") or "",
            "child_clearance_l_per_h": extrap.get("child_clearance_l_per_h"),
            "child_volume_l": extrap.get("child_volume_l"),
            "maturation_fraction": extrap.get("maturation_fraction"),
            "safety_bounds": safety_bounds,
        },
        "evidence_grade": {
            "grade": "very-low",
            "rationale": "Assembled from partial run; submit_recommendation was not called.",
        },
        "citations": [],
        "concordance": concordance,
        "critique": {
            "objections": ["Run ended before full critique/submit; numbers recovered from math tools only."],
            "resolution": "Partial recovery — review carefully.",
            "residual_risks": ["Missing structured rationale and critic dose_grade."],
            "dose_grade": "accept_with_caveats",
        },
        "safety_flags": ["assembled_from_partial_run"],
        "rationale": (
            "This recommendation was recovered from deterministic math-tool outputs after the agent "
            "run ended without calling submit_recommendation. Treat as incomplete; re-run if clinical "
            "use is intended."
        ),
        "source_of_dose": "partial_recovery",
    }


_LEADINS = ("starting dose of ", "dose of ", "oral ", "iv ", "i.v. ")


def _guess_drug_name(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "Unknown"
    low = q.lower()
    for prefix in _LEADINS:
        if low.startswith(prefix):
            q = q[len(prefix):]
            break
    token = re.split(r"[\s,;]+", q.strip())[0]
    return token.capitalize() if token and token.isalpha() else "Unknown"
