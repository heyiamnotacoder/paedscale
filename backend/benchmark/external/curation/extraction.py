"""External validation, step 3: checks on extraction records (PROTOCOL.md, Amendments 1-4).

An extraction record lists, per drug and per screening pass, every screened abstract with its
decision and, when included, its observations. Each observation is:

    {"cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "..."},
     "pna_days": [3, 20] | 12 | None, "ga_weeks": [25, 32] | 30 | None, "pma_weeks": ... | None,
     "age_quote": "...", "weight_kg": 1.2 | None, "weight_quote": "..." | None,
     "bsa_m2": None, "height_cm": None, "flags": [...],
     "preterm": False, "pna_range_days": [lo, hi] | None, "pma_range_weeks": [lo, hi] | None}

An age field holds the central value when one is stated, else the range; when both are stated
the range goes in the *_range_* field (Amendment 4 §2).

Ages are converted to days or weeks by fixed factors (year = 365.25 d, month = 30.4375 d,
week = 7 d); the as-reported text is in age_quote. This module never imports the engine.
"""
from __future__ import annotations

import math
import re

UNITS = {"L/h", "mL/min", "mL/h", "L/min", "L/day", "L/h/kg", "mL/min/kg", "mL/h/kg", "L/day/kg",
         "L/h/70kg", "mL/min/1.73m2", "L/h/1.73m2", "mL/h/1.73m2", "mL/min/m2", "L/h/m2"}
ABSOLUTE_UNITS = {"L/h", "mL/min", "mL/h", "L/min", "L/day"}
# Flags a screener records. weight_imputed, ga_imputed and bsa_costeff are added by the scorer.
FLAGS = {"critically_ill", "allometric_standardized", "fixed_maturation", "fixed_allometry",
         "with_tazobactam", "pca_as_pma", "adult_weight_missing", "adult_age_unstated"}
RANGE_FIELDS = {"pna": ("pna_days", "pna_range_days"), "pma": ("pma_weeks", "pma_range_weeks"),
                "ga": ("ga_weeks", "ga_range_weeks")}
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
    bad_flags = sorted(set(obs.get("flags") or []) - FLAGS)
    if bad_flags:
        out.append(f"flag(s) {bad_flags} are not screener flags {sorted(FLAGS)}")
    for central_key, range_key in RANGE_FIELDS.values():
        for key in (central_key, range_key):
            v = obs.get(key)
            if isinstance(v, list) and not (len(v) == 2 and all(isinstance(x, (int, float)) for x in v)
                                            and 0 <= v[0] <= v[1]):
                out.append(f"{key} {v!r} is not a [low, high] range")
    return out


def age_range(obs: dict, age: str) -> list | None:
    """The stated range of an age ("pna", "pma" or "ga"), or None when only a central value is stated."""
    central_key, range_key = RANGE_FIELDS[age]
    if obs.get(range_key) is not None:
        return obs[range_key]
    v = obs.get(central_key)
    return v if isinstance(v, list) else None


def gestational_weeks(obs: dict) -> float:
    """Central GA; else 32 weeks for a group described as preterm, 40 otherwise (PROTOCOL.md 'Missing gestational age')."""
    ga = central(obs.get("ga_weeks"), geometric=False)
    if ga is not None:
        return ga
    return 32 if obs.get("preterm") else 40


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
    """Total clearance in L/h (PROTOCOL.md 'Extraction'; Amendment 1 §3, §7; Amendments 3 §1, 4 §1)."""
    if unit == "L/h":
        return value
    if unit == "mL/min":
        return value * 0.06
    if unit == "L/day":
        return value / 24
    if unit == "mL/h":                        # Amendment 4 §1
        return value / 1000
    if unit == "L/min":
        return value * 60
    if unit == "L/day/kg":
        return value / 24 * weight_kg
    if unit == "mL/h/1.73m2":
        return value / 1000 * bsa_m2 / 1.73
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
    if unit == "mL/min/m2":                   # Amendment 3 §1
        return value * 0.06 * bsa_m2
    if unit == "L/h/m2":
        return value * bsa_m2
    raise ValueError(f"unknown clearance unit {unit!r}")
