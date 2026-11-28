"""
Mechanistic-reasoning scorer (PRD lines 77-84).

Pure functions, NO API key — compares a model's submit_recommendation.mechanism against the
hand-reviewed answer key in mechanism_truth.json across the six PRD dimensions:
clearance pathway, hepatic-vs-renal elimination, CYP/UGT enzymes, transporters, active
metabolites, and protein binding.

Empty lists are scored as correct-negatives (e.g. "no transporter") — the model must get the
ABSENCE right too, not invent entries. Set-valued fields use synonym-normalised set equality;
protein binding is scored within an absolute tolerance.
"""

from __future__ import annotations

import json
import os
import re

from engine.constants import MATURATION

HERE = os.path.dirname(__file__)
DIMENSIONS = ["elimination", "pathways", "enzymes",
              "transporters", "active_metabolites", "protein_binding"]

# token -> canonical, applied AFTER stripping non-alphanumerics and lowercasing
_SYNONYMS = {
    # transporters
    "pglycoprotein": "pgp", "pgp": "pgp", "abcb1": "pgp", "mdr1": "pgp",
    # enzymes: collapse sub-family notation (CYP3A4/5 -> cyp3a4)
    "cyp3a45": "cyp3a4", "cyp3a5": "cyp3a4", "cyp3a": "cyp3a4",
    # active metabolites
    "morphine6glucuronide": "m6g", "m6g": "m6g",
    "morphine3glucuronide": "m3g", "m3g": "m3g",
    "1hydroxymidazolam": "1ohmidazolam", "1ohmidazolam": "1ohmidazolam",
    "alphahydroxymidazolam": "1ohmidazolam",
}


def _norm(s: str) -> str:
    t = re.sub(r"[^a-z0-9]", "", str(s).lower())
    return _SYNONYMS.get(t, t)


def _normset(xs) -> set[str]:
    return {_norm(x) for x in (xs or []) if str(x).strip()}


# A drug-specific curve (e.g. "clindamycin") names the same pathway as its family ("cyp3a4"):
# choosing the more specific curve is a dosing choice, not a different mechanism.
_PATHWAY_FAMILY = {_norm(k): _norm(c.get("family", k)) for k, c in MATURATION.items()}


def _pathwayset(xs) -> set[str]:
    return {_PATHWAY_FAMILY.get(p, p) for p in _normset(xs)}


def load_truth() -> dict:
    with open(os.path.join(HERE, "..", "eval_data", "mechanism_truth.json")) as f:
        return json.load(f)


def score_mechanism(model: dict, truth: dict, pb_tol_abs: float = 20.0) -> dict:
    """Return {dimension: bool, ...} plus 'overall' (fraction of dimensions correct)."""
    model = model or {}
    out: dict[str, object] = {}

    out["elimination"] = _norm(model.get("elimination", "")) == _norm(truth["elimination"])
    out["pathways"] = _pathwayset(model.get("pathways")) == _pathwayset(truth["pathways"])
    out["enzymes"] = _normset(model.get("enzymes")) == _normset(truth["enzymes"])
    out["transporters"] = _normset(model.get("transporters")) == _normset(truth["transporters"])

    # active metabolites: lenient — get the PRESENCE right, and if present, overlap by >=1.
    mt, tt = _normset(model.get("active_metabolites")), _normset(truth["active_metabolites"])
    out["active_metabolites"] = (not mt and not tt) or (bool(mt) and bool(tt) and bool(mt & tt))

    # protein binding: within absolute tolerance
    mpb, tpb = model.get("protein_binding_percent"), truth.get("protein_binding_percent")
    out["protein_binding"] = (
        mpb is not None and tpb is not None and abs(float(mpb) - float(tpb)) <= pb_tol_abs
    )

    out["overall"] = sum(1 for d in DIMENSIONS if out[d]) / len(DIMENSIONS)
    return out


if __name__ == "__main__":
    # Self-test: a perfect answer scores 1.0; a wrong-negative fails the right dimension.
    truth = load_truth()["drugs"]
    perfect = score_mechanism(truth["morphine"], truth["morphine"])
    assert perfect["overall"] == 1.0, perfect
    # Model that misses the active metabolite and mislabels elimination:
    wrong = score_mechanism(
        {"elimination": "renal", "pathways": ["ugt2b7"], "enzymes": ["UGT2B7"],
         "transporters": ["P-gp"], "active_metabolites": [], "protein_binding_percent": 35},
        truth["morphine"],
    )
    assert wrong["elimination"] is False and wrong["active_metabolites"] is False, wrong
    assert wrong["pathways"] is True and wrong["protein_binding"] is True, wrong
    # Synonym tolerance: "P-glycoprotein" and "CYP3A4/5" must match.
    syn = score_mechanism(
        {"elimination": "hepatic", "pathways": ["cyp3a4"], "enzymes": ["CYP3A4/5"],
         "transporters": ["P-glycoprotein"], "active_metabolites": ["1-hydroxymidazolam"],
         "protein_binding_percent": 95},
        truth["midazolam"],
    )
    assert syn["overall"] == 1.0, syn
    print("mechanism_score self-test OK — perfect=1.0, targeted misses caught, synonyms match.")
