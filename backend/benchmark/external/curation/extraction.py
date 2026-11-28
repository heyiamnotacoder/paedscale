"""External validation, step 3: checks on extraction records (PROTOCOL.md, Amendments 1-11).

An extraction record lists, per drug and per screening pass, every screened abstract with its
decision and, when included, its observations. Each observation is:

    {"cl": {"value": 0.05, "unit": "L/h/kg", "summary": "mean", "quote": "..."},
     "pna_days": [3, 20] | 12 | None, "ga_weeks": [25, 32] | 30 | None, "pma_weeks": ... | None,
     "age_quote": "...", "weight_kg": 1.2 | None, "weight_quote": "..." | None,
     "bsa_m2": None, "bsa_quote": None, "height_cm": None, "height_quote": None, "flags": [...],
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
PER_KG_UNITS = {"L/h/kg", "mL/min/kg", "mL/h/kg", "L/day/kg"}
ADULT_UNITS = ABSOLUTE_UNITS | PER_KG_UNITS          # Amendment 1 §2 converts only these
# Flags a screener records, by list. weight_imputed, ga_imputed and bsa_costeff are added by the scorer.
PEDIATRIC_FLAGS = {"critically_ill", "allometric_standardized", "fixed_maturation", "fixed_allometry",
                   "with_tazobactam", "pca_as_pma",
                   "route_unstated", "birth_weight", "typical_at_cohort_median"}     # Amendment 14
ADULT_FLAGS = {"with_tazobactam", "adult_weight_missing", "adult_age_unstated", "route_unstated"}
RANGE_FIELDS = {"pna": ("pna_days", "pna_range_days"), "pma": ("pma_weeks", "pma_range_weeks"),
                "ga": ("ga_weeks", "ga_range_weeks")}
SUMMARIES = {"mean", "median", "geometric_mean", "typical"}
ADULT_AGE_YEARS = (18, 65)
DAYS_PER_MONTH = 30.4375
DAYS_PER_YEAR = 365.25


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def _is_range(x) -> bool:
    return isinstance(x, list) and len(x) == 2 and all(_is_num(v) for v in x) and x[0] <= x[1]


def _numbers(x) -> list[float]:
    return list(x) if isinstance(x, list) else [x]


def _number_in(value: float, quote: str) -> bool:
    """The value is one of the quote's numbers, compared as numbers so that "0.0340" is 0.034
    (Amendment 13 §1). A decimal comma counts as a point."""
    q = _norm(quote).replace(",", ".")
    nums = re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?!\.?\d)", q)
    return any(math.isclose(float(n), value, rel_tol=1e-9, abs_tol=1e-12) for n in nums)


def flag_problems(flags, kind: str) -> list[str]:
    allowed = PEDIATRIC_FLAGS if kind == "pediatric" else ADULT_FLAGS
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        return [f"flags {flags!r} is not a list of names"]
    bad = sorted(set(flags) - allowed)
    return [f"flag(s) {bad} are not {kind} screener flags {sorted(allowed)}"] if bad else []


def _quoted(name: str, value, quote, text: str, ranged: bool) -> list[str]:
    """A stated number (or [low, high] when ranged) with its verbatim quote."""
    if value is None:
        return []
    if not (_is_num(value) or (ranged and _is_range(value))):
        return [f"{name} {value!r} is not a non-negative number" + (" or [low, high] range" if ranged else "")]
    if not isinstance(quote, str) or not quote or _norm(quote) not in _norm(text):
        return [f"{name} quote is not in the abstract: {quote!r}"]
    grams = name == "weight" and re.search(r"\d\s*(?:g|gm|grams?)\b", _norm(quote))   # Amendment 13 §2
    return [f"{name} {v} does not appear in its quote" for v in _numbers(value)
            if not (_number_in(v, quote) or (grams and _number_in(v * 1000, quote)))]


def _cl(obs: dict) -> dict:
    return obs["cl"] if isinstance(obs.get("cl"), dict) else {}


def _common(obs: dict, abstract: str, units: set[str]) -> list[str]:
    if not isinstance(obs, dict):
        return [f"{obs!r} is not an object"]
    text = _norm(abstract)
    out = []
    cl = _cl(obs)
    if not isinstance(cl.get("unit"), str) or cl["unit"] not in units:
        out.append(f"unit {cl.get('unit')!r} is not one of {sorted(units)}")
    if cl.get("summary") not in SUMMARIES:
        out.append(f"summary {cl.get('summary')!r} is not one of {sorted(SUMMARIES)}")
    if not _is_num(cl.get("value")):
        out.append(f"clearance {cl.get('value')!r} is not a non-negative number")
    else:
        out += _quoted("clearance", cl["value"], cl.get("quote"), text, ranged=False)
    out += _quoted("weight", obs.get("weight_kg"), obs.get("weight_quote"), text, ranged=True)
    out += _quoted("BSA", obs.get("bsa_m2"), obs.get("bsa_quote"), text, ranged=False)
    out += _quoted("height", obs.get("height_cm"), obs.get("height_quote"), text, ranged=False)
    q = obs.get("age_quote")
    if q is not None and (not isinstance(q, str) or _norm(q) not in text):
        out.append(f"age quote is not in the abstract: {q!r}")
    return out


def problems(obs: dict, abstract: str, study_flags=()) -> list[str]:
    """Problems with one pediatric observation; study_flags are the study's own flags."""
    out = _common(obs, abstract, UNITS)
    if out and not isinstance(obs, dict):
        return out
    flags = obs.get("flags") or []
    bad_flags = flag_problems(flags, "pediatric")
    out += bad_flags
    flags = [] if bad_flags else flags
    if not isinstance(obs.get("preterm"), bool):
        out.append(f"preterm {obs.get('preterm')!r} is not true or false")
    if not obs.get("age_quote"):
        out.append("age quote is not in the abstract: None")
    for central_key, range_key in RANGE_FIELDS.values():
        c, r = obs.get(central_key), obs.get(range_key)
        if c is not None and not (_is_num(c) or _is_range(c)):
            out.append(f"{central_key} {c!r} is not a non-negative number or [low, high] range")
        if r is not None and c is None:            # Amendment 11 §2
            out.append(f"{range_key} is given without its main field {central_key}; a range-only age goes in {central_key}")
        if r is not None:
            if not _is_range(r):
                out.append(f"{range_key} {r!r} is not a [low, high] range")
            elif _is_num(c) and not r[0] <= c <= r[1]:
                out.append(f"{central_key} {c} is outside its stated range {r}")
    if obs.get("pna_days") is None and obs.get("pma_weeks") is None:
        out.append("no postnatal or postmenstrual age")
    if out:                                   # the age rules below need well-formed ages
        return out
    ga_msg = ga_problem(obs)
    if ga_msg:
        out.append(ga_msg)
    if _cl(obs).get("unit") == "L/h/70kg":         # Amendment 1 §3, Amendments 5 §3, 6 §2
        if "allometric_standardized" not in set(flags) | set(study_flags or []):
            out.append("a per-70 kg value needs the allometric_standardized flag")
        if not age_fixes_maturation(obs):
            out.append("a per-70 kg value needs the age it applies at: PMA, PNA with GA, or a PNA range wholly 2 years or older")
    return out


def adult_problems(value: dict, abstract: str, study_flags=()) -> list[str]:
    """Problems with one adult value (Amendment 1 §2, Amendment 2 §5)."""
    out = _common(value, abstract, ADULT_UNITS)
    if out and not isinstance(value, dict):
        return out
    own = value.get("flags") or []
    bad_flags = flag_problems(own, "adult")
    out += bad_flags
    flags = set([] if bad_flags else own) | set(study_flags or [])
    age = value.get("age_years")
    if age is None:
        if "adult_age_unstated" not in flags:
            out.append("no adult age and no adult_age_unstated flag")
    elif not (_is_num(age) or _is_range(age)):
        out.append(f"age_years {age!r} is not a number or [low, high] range")
    else:
        lo, hi = ADULT_AGE_YEARS
        if not all(lo <= a <= hi for a in _numbers(age)):
            out.append(f"adult age {age} is outside {lo}-{hi} years")
        out += _quoted("adult age", age, value.get("age_quote"), abstract, ranged=True)
    unit = _cl(value).get("unit")
    if unit in ABSOLUTE_UNITS and value.get("weight_kg") is None and "adult_weight_missing" not in flags:
        out.append("absolute clearance with no weight and no adult_weight_missing flag")
    return out


def age_fixes_maturation(obs: dict) -> bool:
    """PMA, or postnatal age with GA, or a postnatal age whose whole range is 2 years or more
    (maturation is then near-complete; Amendment 5 §3, Amendment 6 §2)."""
    if obs.get("pma_weeks") is not None:
        return True
    rng = age_range(obs, "pna")
    lowest = rng[0] if rng else central(obs.get("pna_days"), geometric=True)
    if lowest is None:
        return False
    return lowest >= 24 * DAYS_PER_MONTH or obs.get("ga_weeks") is not None


def age_range(obs: dict, age: str) -> list | None:
    """The stated range of an age ("pna", "pma" or "ga"), or None when only a central value is stated."""
    central_key, range_key = RANGE_FIELDS[age]
    if obs.get(range_key) is not None:
        return obs[range_key]
    v = obs.get(central_key)
    return v if isinstance(v, list) else None


def _bounds(obs: dict, age: str) -> tuple[float, float] | None:
    rng = age_range(obs, age)
    v = rng or obs.get(RANGE_FIELDS[age][0])
    return None if v is None else (tuple(v) if isinstance(v, list) else (v, v))


def _default_ga_cap(obs: dict) -> float | None:
    """Central PMA minus the smallest stated postnatal age, or None without a PMA. A member at
    the central PMA was born no later than this (Amendment 11 §1)."""
    pma = central(obs.get("pma_weeks"), geometric=False)
    if pma is None:
        return None
    pna = _bounds(obs, "pna")
    return pma - (pna[0] if pna else 0) / 7


def ga_problem(obs: dict) -> str | None:
    """Stated ages must allow some GA of 20-45 weeks, and a stated GA must not exceed the
    largest PMA minus the smallest postnatal age by more than half a week (Amendments 8 §2, 9 §2, 10 §2)."""
    pma, pna, ga = _bounds(obs, "pma"), _bounds(obs, "pna"), _bounds(obs, "ga")
    if pma is None:
        return None
    if pna is not None and (pma[1] - pna[0] / 7 < 20 or pma[0] - pna[1] / 7 > 45):
        return f"PMA {list(pma)} weeks and postnatal age {list(pna)} days allow no GA of 20-45 weeks"
    highest = pma[1] - (pna or (0, 0))[0] / 7
    if ga is not None and ga[0] > highest + 0.5:
        return f"stated GA {list(ga)} weeks exceeds PMA minus postnatal age ({highest:.1f} weeks)"
    return None


def gestational_weeks(obs: dict) -> float:
    """GA in weeks: as stated; else 32 weeks for a group described as preterm and 40 otherwise,
    capped at central PMA minus the smallest postnatal age (PROTOCOL.md 'Missing gestational age';
    Amendments 8 §1, 11 §1)."""
    ga = central(obs.get("ga_weeks"), geometric=False)
    if ga is not None:
        return ga
    default = 32 if obs.get("preterm") else 40
    cap = _default_ga_cap(obs)
    return default if cap is None else min(default, cap)


def ga_imputed(obs: dict) -> bool:
    """The ga_imputed flag: no stated GA, and either the preterm default or a cap below 37 weeks set it."""
    if obs.get("ga_weeks") is not None:
        return False
    return bool(obs.get("preterm")) or gestational_weeks(obs) < 37


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
