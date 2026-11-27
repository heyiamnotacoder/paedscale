"""Representative body weight for a virtual patient (benchmark harness only).

Term infants and children: sex-averaged median weight-for-age, WHO Child Growth Standards
(2006) for 0–1856 days and CDC 2000 growth charts above that (data/weight_median.csv).

Preterm infants (gestational age < 37 wk) whose postmenstrual age is still below 40 wk:
APPROXIMATE sex-averaged 50th centile of the Fenton 2013 preterm growth chart, read from the
published charts at 2-week steps (Fenton & Kim, BMC Pediatr 2013;13:59). Precision is about
±10%; the benchmark's weight sensitivity analysis (±20%) covers it. Fenton's charts join the
WHO standard at 50 wk PMA; between 40 and 50 wk we interpolate linearly from the Fenton
40-wk value to the WHO median at 10 weeks corrected age (avoiding the WHO first-days
weight dip, which belongs to term newborns). From 50 wk PMA on: WHO at corrected age.
"""

from __future__ import annotations

import bisect
import csv
import os
from functools import lru_cache

HERE = os.path.dirname(__file__)

# PMA (weeks) -> approximate Fenton 2013 50th centile, sex-averaged (kg)
FENTON_2013_P50_APPROX = {
    22: 0.50, 24: 0.65, 26: 0.88, 28: 1.13, 30: 1.45, 32: 1.80,
    34: 2.25, 36: 2.70, 38: 3.10, 40: 3.45,
}


@lru_cache(maxsize=1)
def _table() -> tuple[list[float], list[float]]:
    days, kg = [], []
    with open(os.path.join(HERE, "data", "weight_median.csv")) as f:
        for row in csv.DictReader(line for line in f if not line.startswith("#")):
            days.append(float(row["age_days"]))
            kg.append(float(row["weight_kg"]))
    return days, kg


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect.bisect_right(xs, x)
    x0, x1, y0, y1 = xs[i - 1], xs[i], ys[i - 1], ys[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def median_weight_kg(age_days: float, gestational_age_weeks: float = 40.0) -> float:
    """Median weight (kg) at a postnatal age, for an infant born at a gestational age."""
    days, kg = _table()
    if gestational_age_weeks < 37:
        pma = gestational_age_weeks + age_days / 7.0
        if pma < 40:
            xs = sorted(FENTON_2013_P50_APPROX)
            return _interp([float(x) for x in xs], [FENTON_2013_P50_APPROX[x] for x in xs], pma)
        if pma < 50:
            w40, w50 = FENTON_2013_P50_APPROX[40], _interp(days, kg, 70.0)
            return w40 + (w50 - w40) * (pma - 40.0) / 10.0
        age_days = (pma - 40.0) * 7.0  # corrected age on the term reference
    return _interp(days, kg, age_days)
