"""External validation, step 3: checks on extraction records (PROTOCOL.md, Amendments 1-2).

An extraction record lists, per drug and per screening pass, every screened abstract with its
decision and, when included, its observations. Each observation is:

    {"cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "..."},
     "pna_days": [3, 20] | 12 | None, "ga_weeks": [25, 32] | 30 | None, "pma_weeks": ... | None,
     "age_quote": "...", "weight_kg": 1.2 | None, "weight_quote": "..." | None,
     "bsa_m2": None, "height_cm": None, "flags": [...]}

Ages are converted to days or weeks by fixed factors (year = 365.25 d, month = 30.4375 d,
week = 7 d); the as-reported text is in age_quote. This module never imports the engine.
"""
from __future__ import annotations

import math
import re

UNITS = {"L/h", "mL/min", "L/h/kg", "mL/min/kg", "mL/h/kg", "L/h/70kg", "mL/min/1.73m2",
         "L/h/1.73m2", "L/day"}
SUMMARIES = {"mean", "median", "geometric_mean", "typical"}
DAYS_PER_MONTH = 30.4375
DAYS_PER_YEAR = 365.25


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _number_in(value: float, quote: str) -> bool:
    forms = {f"{value:g}", str(value), f"{value:.1f}", f"{value:.2f}", f"{value:.3f}"}
    q = _norm(quote).replace(",", ".")
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", q) for f in forms)


def problems(obs: dict, abstract: str) -> list[str]:
    text = _norm(abstract)
    out = []
    cl = obs.get("cl") or {}
    if cl.get("unit") not in UNITS:
        out.append(f"unit {cl.get('unit')!r} is not one of {sorted(UNITS)}")
    if cl.get("summary") not in SUMMARIES:
        out.append(f"summary {cl.get('summary')!r} is not one of {sorted(SUMMARIES)}")
    quotes = [("cl quote", cl.get("quote")), ("age quote", obs.get("age_quote"))]
    if obs.get("weight_kg") is not None:
        quotes.append(("weight quote", obs.get("weight_quote")))
    for name, q in quotes:
        if not q or _norm(q) not in text:
            out.append(f"{name} is not in the abstract: {q!r}")
    if isinstance(cl.get("value"), (int, float)) and cl.get("quote") and not _number_in(cl["value"], cl["quote"]):
        out.append(f"clearance {cl['value']} does not appear in its quote")
    if obs.get("weight_kg") is not None and obs.get("weight_quote") and not _number_in(obs["weight_kg"], obs["weight_quote"]):
        out.append(f"weight {obs['weight_kg']} does not appear in its quote")
    if obs.get("pna_days") is None and obs.get("pma_weeks") is None:
        out.append("no postnatal or postmenstrual age")
    return out


def central(x, geometric: bool):
    """A stated value as is; a [low, high] range at its midpoint. Postnatal age uses the
    geometric midpoint with the lower bound floored at 1 day (Amendment 1 §6)."""
    if x is None or isinstance(x, (int, float)):
        return x
    lo, hi = x
    return math.sqrt(max(lo, 1.0) * hi) if geometric else (lo + hi) / 2


def stratum(pna_days: float, ga_weeks: float | None) -> str:
    """ICH E11 category from the central postnatal age (days) and gestational age (weeks)."""
    if pna_days < 28:
        return "preterm_newborn" if (ga_weeks or 40) < 37 else "term_newborn"
    if pna_days < 24 * DAYS_PER_MONTH:
        return "infant_toddler"
    if pna_days < 12 * DAYS_PER_YEAR:
        return "child"
    return "adolescent"


def to_l_per_h(value: float, unit: str, weight_kg: float | None = None, bsa_m2: float | None = None) -> float:
    """Total clearance in L/h (PROTOCOL.md 'Extraction'; Amendment 1 §3, §7)."""
    if unit == "L/h":
        return value
    if unit == "mL/min":
        return value * 0.06
    if unit == "L/day":
        return value / 24
    if unit == "L/h/kg":
        return value * weight_kg
    if unit == "mL/min/kg":
        return value * 0.06 * weight_kg
    if unit == "mL/h/kg":
        return value / 1000 * weight_kg
    if unit == "L/h/70kg":
        return value * (weight_kg / 70) ** 0.75
    if unit == "mL/min/1.73m2":
        return value * 0.06 * bsa_m2 / 1.73
    if unit == "L/h/1.73m2":
        return value * bsa_m2 / 1.73
    raise ValueError(f"unknown clearance unit {unit!r}")
