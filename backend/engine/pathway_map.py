"""
PaedScale — drug / enzyme -> maturation-curve lookup (deterministic; no I/O, no LLM).

Helps the agent pick an `fm` key; it does not decide the clearance split. The agent still
judges which pathways clear a drug and in what fractions. These lookups only say which
published curve, if any, describes a named drug or enzyme:

  * curve_for_drug: a drug-specific curve for that drug, else the pathway curve whose
    probe it is, else None.
  * curves_for_enzyme: the pathway curves that cover an enzyme or transporter. A
    drug-specific curve is never offered for another drug's enzyme, and an enzyme with no
    curve returns [] (abstain; never borrow a neighbouring isoform's curve).
"""

from __future__ import annotations

import re
from typing import Optional

from engine.constants import DRUG_SPECIFIC, MATURATION, PATHWAY
from engine.pk_engine import is_probe_drug


def _norm_enzyme(name: str) -> str:
    t = re.sub(r"[^a-z0-9]", "", str(name).lower())
    # CYP3A4/5, CYP3A5, CYP3A -> cyp3a4 (the curve covers the CYP3A sub-family)
    return "cyp3a4" if t in ("cyp3a45", "cyp3a5", "cyp3a") else t


def curve_for_drug(drug: str) -> Optional[str]:
    """Key of the curve estimated from this drug itself, or None."""
    for kind in (DRUG_SPECIFIC, PATHWAY):
        for key, c in MATURATION.items():
            if c.get("kind") == kind and is_probe_drug(drug, c.get("probe_drug")):
                return key
    return None


def curves_for_enzyme(enzyme: str) -> list[str]:
    """Pathway-curve keys that cover this enzyme/transporter; [] when none is published."""
    e = _norm_enzyme(enzyme)
    return [k for k, c in MATURATION.items()
            if c.get("kind") == PATHWAY and e in {_norm_enzyme(x) for x in c.get("enzymes", [])}]


def curve_catalogue() -> str:
    """One line per curve, for the agent's tool description and prompts."""
    lines = []
    for key, c in MATURATION.items():
        scope = (f"{c['probe_drug']} only" if c.get("kind") == DRUG_SPECIFIC
                 else f"covers {'/'.join(c['enzymes'])}"
                 + (f"; probe {c['probe_drug']}" if c.get("probe_drug") else ""))
        unc = "" if (c.get("tm50_ci95") or c.get("hill_ci95")) else "; no published uncertainty"
        lines.append(f"{key}: {c['label']} — {scope}; TM50 {c['tm50_weeks']:g} wk, "
                     f"Hill {c['hill']:g}{unc}")
    return "\n".join(lines)
