"""
PaedScale — parameter-uncertainty layer (deterministic, seeded; no I/O, no LLM).

The point estimate from compute_pediatric_dose uses the published TM50 / Hill of each
maturation curve. Those same papers publish 95% confidence intervals. This module
propagates them by Monte Carlo into a prediction interval for the child's clearance,
half-life and dose, and attributes the variance to each maturing pathway.

Assumptions (stated, not hidden):
  * TM50 and Hill are sampled independently, each log-normal with median = the published
    point estimate and log-SD = (ln hi − ln lo) / (2 × 1.96). Their covariance is not
    published, so independence is an assumption (it widens, not narrows, the interval
    when the true correlation is negative).
  * The allometric exponent stays fixed at 0.75 (theory-based; Anderson & Holford 2008).
  * The interval covers PARAMETER uncertainty in the maturation curves only. It is not a
    between-subject variability interval and says nothing about errors in the retrieved
    adult PK, the pathway split (fm) or the reference dose.
"""

from __future__ import annotations

import math
import random
from typing import Optional

from engine.constants import MATURATION
from engine.pk_engine import compute_pediatric_dose

Z_95 = 1.959963984540054
DEFAULT_DRAWS = 2000
DEFAULT_SEED = 20261127


def _log_sd(ci: tuple[float, float]) -> float:
    lo, hi = ci
    return (math.log(hi) - math.log(lo)) / (2.0 * Z_95)


def _sample_curve(params: dict, rng: random.Random) -> dict:
    """One draw of a maturation curve from its published 95% CIs."""
    out = dict(params)
    if params.get("tm50_ci95"):
        out["tm50_weeks"] = params["tm50_weeks"] * math.exp(rng.gauss(0.0, _log_sd(params["tm50_ci95"])))
    if params.get("hill_ci95"):
        out["hill"] = params["hill"] * math.exp(rng.gauss(0.0, _log_sd(params["hill_ci95"])))
    return out


def _quantiles(xs: list[float]) -> dict:
    s = sorted(xs)
    n = len(s)

    def q(p: float) -> float:
        # linear interpolation between order statistics (type-7, as numpy default)
        h = (n - 1) * p
        lo = math.floor(h)
        hi = min(lo + 1, n - 1)
        return s[lo] + (h - lo) * (s[hi] - s[lo])

    return {"p05": q(0.05), "p50": q(0.50), "p95": q(0.95)}


def _var(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / max(1, len(xs) - 1)


def dose_prediction_interval(
    *,
    n_draws: int = DEFAULT_DRAWS,
    seed: int = DEFAULT_SEED,
    **case,
) -> Optional[dict]:
    """90% prediction interval for a compute_pediatric_dose case.

    `case` takes the same keyword arguments as compute_pediatric_dose. Returns None when
    the point estimate is blocked (no interval around a withheld dose). Pathways in `fm`
    with no published CI contribute no spread (their curve is held at the point value).
    """
    case = dict(case)
    case.pop("maturation", None)
    point = compute_pediatric_dose(**case)
    if point.blocked:
        return None
    fm = case.get("fm") or {}
    maturing = [p for p in fm if p in MATURATION]

    def run(vary: set[str], rng: random.Random):
        curves = {
            k: (_sample_curve(v, rng) if k in vary else v) for k, v in MATURATION.items()
        }
        return compute_pediatric_dose(maturation=curves, **case)

    rng = random.Random(seed)
    doses: list[float] = []
    cls: list[float] = []
    hls: list[float] = []
    for _ in range(n_draws):
        r = run(set(maturing), rng)
        cls.append(r.cl_child_l_h)
        hls.append(r.half_life_h)
        if r.recommended_dose_mg_per_kg_per_day is not None:
            doses.append(r.recommended_dose_mg_per_kg_per_day)

    # One-at-a-time variance attribution on log(CL_child) — the quantity every dose
    # metric and the half-life depend on.
    raw: dict[str, float] = {}
    for i, pw in enumerate(maturing):
        sub = random.Random(seed + 1 + i)
        raw[pw] = _var([math.log(run({pw}, sub).cl_child_l_h) for _ in range(max(200, n_draws // 4))])
    total = sum(raw.values())
    share = {k: (v / total if total > 0 else 1.0 / len(raw)) for k, v in raw.items()}

    dose_q = _quantiles(doses) if doses else None
    out = {
        "method": (
            f"Monte Carlo, {n_draws} draws (seed {seed}); TM50 and Hill sampled log-normally "
            "and independently from the published 95% CIs; allometric exponent fixed at 0.75. "
            "Covers maturation-parameter uncertainty only."
        ),
        "level": 0.90,
        "n_draws": n_draws,
        "seed": seed,
        "dose_mg_per_kg_per_day": dose_q,
        "cl_child_l_h": _quantiles(cls),
        "half_life_h": _quantiles(hls),
        "fold_width_90": (dose_q["p95"] / dose_q["p05"]) if dose_q and dose_q["p05"] > 0 else None,
        "variance_share": share,
    }
    return out


def interval_to_dict(pi: Optional[dict], ndigits: int = 3) -> Optional[dict]:
    """Round an interval for JSON / tool return (keeps structure)."""
    if pi is None:
        return None

    def rnd(x):
        if isinstance(x, float):
            return round(x, ndigits)
        if isinstance(x, dict):
            return {k: rnd(v) for k, v in x.items()}
        return x

    return rnd(pi)
