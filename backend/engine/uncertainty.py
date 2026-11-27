"""
PaedScale — parameter-uncertainty layer (deterministic, seeded; no I/O, no LLM).

The point estimate from compute_pediatric_dose uses the published TM50 / Hill of each
maturation curve. Those same papers publish 95% confidence intervals. This module
propagates them by Monte Carlo into a 90% *parameter-uncertainty interval* for the
child's clearance, half-life and dose, and attributes the variance to each pathway.

Assumptions (stated, not hidden):
  * TM50 and Hill are each sampled from a split (two-piece) log-normal whose median is the
    published point estimate and whose 2.5th / 97.5th percentiles are the published CI
    bounds exactly — published CIs are often asymmetric on the log scale.
  * TM50 and Hill are sampled independently. Their covariance is not published. Below
    TM50 a negative correlation would make the true spread narrower than shown; above
    TM50 it would make it wider. The direction of the error is therefore age-dependent.
  * The allometric exponent stays fixed at 0.75 (theory-based; Anderson & Holford 2008).
  * The interval covers PARAMETER uncertainty in the maturation curves only. It is not a
    between-subject variability (prediction) interval and says nothing about errors in the
    retrieved adult PK, the pathway split (fm) or the reference dose.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from engine.constants import MATURATION
from engine.pk_engine import compute_pediatric_dose

Z_975 = 1.959963984540054
DEFAULT_DRAWS = 2000
DEFAULT_SEED = 20261127
# Below this, log-CL variance is numerical noise (e.g. an adult on the plateau).
_NO_SPREAD = 1e-12


def _split_lognormal(point: float, ci: tuple[float, float], rng: random.Random) -> float:
    lo, hi = ci
    z = rng.gauss(0.0, 1.0)
    sd = (math.log(point) - math.log(lo)) / Z_975 if z < 0 else (math.log(hi) - math.log(point)) / Z_975
    return point * math.exp(z * sd)


def sample_curve(params: dict, rng: random.Random) -> dict:
    """One draw of a maturation curve whose TM50 / Hill reproduce the published 95% CIs."""
    out = dict(params)
    if params.get("tm50_ci95"):
        out["tm50_weeks"] = _split_lognormal(params["tm50_weeks"], params["tm50_ci95"], rng)
    if params.get("hill_ci95"):
        out["hill"] = _split_lognormal(params["hill"], params["hill_ci95"], rng)
    return out


def _quantiles(xs: list[float]) -> Optional[dict]:
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)

    def q(p: float) -> float:
        # linear interpolation between order statistics (type 7, the numpy default)
        h = (n - 1) * p
        lo = math.floor(h)
        hi = min(lo + 1, n - 1)
        return s[lo] + (h - lo) * (s[hi] - s[lo])

    return {"p05": q(0.05), "p50": q(0.50), "p95": q(0.95)}


def _var(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)


def dose_uncertainty_interval(
    *,
    n_draws: int = DEFAULT_DRAWS,
    seed: int = DEFAULT_SEED,
    **case,
) -> Optional[dict]:
    """90% parameter-uncertainty interval for a compute_pediatric_dose case.

    `case` takes the same keyword arguments as compute_pediatric_dose, except `maturation`
    (the published curves are not caller-overridable here). Returns None when the point
    estimate is blocked: there is no interval around a withheld dose.
    """
    if "maturation" in case:
        raise TypeError("dose_uncertainty_interval samples the published MATURATION curves only")
    point = compute_pediatric_dose(**case)
    if point.blocked:
        return None
    maturing = [p for p in (case.get("fm") or {}) if p in MATURATION]
    # Draws describe the engine dose, so safety bounds must not truncate them: they are
    # removed for sampling and reported as the share of draws past each bound instead.
    toxic = case.get("toxic_dose_mg_per_kg_per_day")
    effective = case.get("effective_dose_mg_per_kg_per_day")
    unbounded = {k: v for k, v in case.items()
                 if k not in ("toxic_dose_mg_per_kg_per_day", "effective_dose_mg_per_kg_per_day")}

    def run(vary: set[str], rng: random.Random):
        curves = {k: (sample_curve(v, rng) if k in vary else v) for k, v in MATURATION.items()}
        return compute_pediatric_dose(maturation=curves, **unbounded)

    rng = random.Random(seed)
    dose_kg: list[float] = []
    dose_day: list[float] = []
    cls: list[float] = []
    hls: list[float] = []
    for _ in range(n_draws):
        r = run(set(maturing), rng)
        cls.append(r.cl_child_l_h)
        hls.append(r.half_life_h)
        if r.recommended_dose_mg_per_kg_per_day is not None:
            dose_kg.append(r.recommended_dose_mg_per_kg_per_day)
            dose_day.append(r.recommended_dose_mg_per_day)

    # One-at-a-time variance attribution on log(CL_child): every dose metric and the
    # half-life depend on it, so the attribution is meaningful even for Cmax drugs.
    raw: dict[str, float] = {}
    for i, pw in enumerate(maturing):
        sub = random.Random(seed + 1 + i)
        raw[pw] = _var([math.log(run({pw}, sub).cl_child_l_h) for _ in range(max(200, n_draws // 4))])
    total = sum(raw.values())
    share = {k: v / total for k, v in raw.items()} if total > _NO_SPREAD else None

    dq = _quantiles(dose_kg)
    share_past = lambda bound, past: (sum(past(x, bound) for x in dose_kg) / len(dose_kg)
                                      if bound is not None and dose_kg else None)
    return {
        "kind": "parameter-uncertainty interval around the engine dose (maturation TM50/Hill only)",
        "engine_dose_mg_per_kg_per_day": point.recommended_dose_mg_per_kg_per_day,
        "method": (
            f"Monte Carlo, {n_draws} draws (seed {seed}); TM50 and Hill sampled independently "
            "from split log-normals matching the published 95% CIs; allometric exponent fixed "
            "at 0.75. Not a between-subject variability interval."
        ),
        "level": 0.90,
        "n_draws": n_draws,
        "n_valid": len(dose_kg),
        "seed": seed,
        "dose_mg_per_kg_per_day": dq,
        "dose_mg_per_day": _quantiles(dose_day),
        "cl_child_l_h": _quantiles(cls),
        "half_life_h": _quantiles(hls),
        "fold_width_90": (dq["p95"] / dq["p05"]) if dq and dq["p05"] > 0 else None,
        "variance_share": share,
        "share_above_toxic": share_past(toxic, lambda x, t: x > t),
        "share_below_effective": share_past(effective, lambda x, e: x < e),
    }
