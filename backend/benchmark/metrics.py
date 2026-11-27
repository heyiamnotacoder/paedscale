"""Benchmark endpoints and drug-clustered bootstrap (harness only).

Rows are dicts with at least {"drug": str, "fe": float} (fe = fold error, predicted / reference).
Aggregation is drug-weighted by default (each drug counts once; Amendment 1 §5).
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist
from typing import Callable


def _by_drug(rows: list[dict]) -> dict[str, list[dict]]:
    g: dict[str, list[dict]] = {}
    for r in rows:
        g.setdefault(r["drug"], []).append(r)
    return g


def _mean(xs):
    return sum(xs) / len(xs)


def _weighted(rows: list[dict], f: Callable[[dict], float], weight: str) -> float:
    if weight == "pair":
        return _mean([f(r) for r in rows])
    return _mean([_mean([f(r) for r in rs]) for rs in _by_drug(rows).values()])


def summarize(rows: list[dict], weight: str = "drug") -> dict:
    """AAFE, AFE and band shares for a set of pairs."""
    if not rows:
        return {"n_pairs": 0, "n_drugs": 0}
    lg = lambda r: math.log10(r["fe"])
    out = {
        "n_pairs": len(rows),
        "n_drugs": len(_by_drug(rows)),
        "aafe": 10 ** _weighted(rows, lambda r: abs(lg(r)), weight),
        "afe": 10 ** _weighted(rows, lg, weight),
        # concordance band as documented in CLAUDE.md / PROTOCOL.md: 0.67–1.5
        "within_1_5": _weighted(rows, lambda r: float(0.67 - 1e-12 <= r["fe"] <= 1.5 + 1e-12), weight),
        "within_2": _weighted(rows, lambda r: float(0.5 - 1e-12 <= r["fe"] <= 2.0 + 1e-12), weight),
    }
    if all("in_range" in r for r in rows):
        out["within_label_range"] = _weighted(rows, lambda r: float(r["in_range"]), weight)
    return out


def cluster_bootstrap_ci(rows: list[dict], stat: Callable[[list[dict]], float], *,
                         n_boot: int = 10000, seed: int = 20261127, level: float = 0.95) -> dict:
    """BCa CI for `stat`, resampling drugs (clusters) with replacement.

    Falls back to the percentile interval when BCa is undefined (e.g. degenerate
    bootstrap distribution or a jackknife with zero spread).
    """
    groups = list(_by_drug(rows).values())
    k = len(groups)
    theta = stat(rows)
    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [r for _ in range(k) for r in groups[rng.randrange(k)]]
        boots.append(stat(sample))
    boots.sort()
    alpha = (1 - level) / 2
    nd = NormalDist()

    def pct(p):
        i = min(n_boot - 1, max(0, int(round(p * (n_boot - 1)))))
        return boots[i]

    method = "bca"
    try:
        # ties count half, so a lumpy bootstrap distribution does not bias z0
        below = (sum(b < theta for b in boots) + 0.5 * sum(b == theta for b in boots)) / n_boot
        if below in (0.0, 1.0) or k < 3:
            raise ValueError("degenerate or too few clusters for a jackknife")
        z0 = nd.inv_cdf(below)
        jack = [stat([r for j, g in enumerate(groups) if j != i for r in g]) for i in range(k)]
        jm = _mean(jack)
        num = sum((jm - j) ** 3 for j in jack)
        den = 6.0 * (sum((jm - j) ** 2 for j in jack) ** 1.5)
        if den == 0:
            raise ValueError("no jackknife spread")
        a = num / den
        def adj(q):
            z = nd.inv_cdf(q)
            denom = 1 - a * (z0 + z)
            if denom <= 0:
                raise ValueError("BCa adjustment undefined")
            return nd.cdf(z0 + (z0 + z) / denom)
        lo, hi = pct(adj(alpha)), pct(adj(1 - alpha))
    except (ValueError, ZeroDivisionError, ArithmeticError):
        method = "percentile"
        lo, hi = pct(alpha), pct(1 - alpha)
    return {"estimate": theta, "lo": lo, "hi": hi, "level": level, "method": method,
            "n_boot": n_boot, "n_clusters": k, "seed": seed}
