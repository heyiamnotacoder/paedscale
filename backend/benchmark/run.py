"""Score every method against the FDA-label reference set and write all outputs.

    cd backend && python3 -m benchmark.run          # -> benchmark/output/

Implements benchmark/PROTOCOL.md (with Amendment 1). Deterministic: no network, no key,
fixed seeds. Harness only; product code never imports this package.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
import sys
from typing import Callable, Optional

from benchmark.methods import METHODS, predict_band, virtual_patients
from benchmark.metrics import cluster_bootstrap_ci, summarize

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
SEED = 20261127
PRIMARY_COMPARATOR = "allometry_class"
SECONDARY_COMPARATORS = ("allometry", "bsa", "weight_linear")
STRATA = ("preterm_newborn", "term_newborn", "infant_toddler", "child", "adolescent")
CURVE_SOURCE_DRUGS = {"midazolam", "morphine"}      # S7: maturation curves fitted to these (midazolam is excluded by E1 anyway)
TITRATED_DRUGS = {"midazolam", "morphine", "famotidine"}  # S8


def load_reference_set(path: Optional[str] = None) -> dict:
    with open(path or os.path.join(HERE, "reference_set.json")) as f:
        return json.load(f)["drugs"]


def ich_stratum(band: dict) -> str:
    """ICH E11 category from the band's arithmetic-midpoint patient."""
    pna = sum(band["pna_days"]) / 2.0
    ga = band.get("ga_weeks") or 40.0
    if pna < 28:
        return "preterm_newborn" if ga < 37 else "term_newborn"
    if pna < 2 * 365.25:
        return "infant_toddler"
    if pna < 12 * 365.25:
        return "child"
    return "adolescent"


def score(refset: dict, methods=METHODS, *, weight_scale: float = 1.0, ga_shift: float = 0.0,
          grid: bool = True, force_css: bool = False,
          keep: Callable[[str, dict, dict], bool] = lambda d, drug, band: True) -> list[dict]:
    rows = []
    for name, d in sorted(refset.items()):
        if not d.get("included"):
            continue
        for b in d["bands"]:
            if not keep(name, d, b):
                continue
            lo, hi = b["range_per_kg_daily"]
            for m in methods:
                pred = predict_band(m, d, b, weight_scale=weight_scale, ga_shift=ga_shift,
                                    grid=grid, force_css=force_css)
                rows.append({
                    "drug": name, "band": b["id"], "stratum": ich_stratum(b), "method": m,
                    "pred": pred, "ref": b["ref_per_kg_daily"], "fe": pred / b["ref_per_kg_daily"],
                    "in_range": lo - 1e-9 <= pred <= hi + 1e-9,
                    "flags": sorted(set(b.get("flags", [])) | set(d["fe"].get("flags", []))
                                    | set(d["adult"].get("flags", []))),
                    "target_metric": d["target_metric"],
                    "renal_mechanism": (d.get("renal_mechanism") or {}).get("value"),
                })
    return rows


def _paired(rows: list[dict], a: str, b: str) -> list[dict]:
    """Per (drug, band): d = |log10 FE_a| - |log10 FE_b|. Negative favours `a`."""
    idx = {(r["drug"], r["band"], r["method"]): r for r in rows}
    out = []
    for (drug, band, m), r in idx.items():
        if m != a or (drug, band, b) not in idx:
            continue
        out.append({"drug": drug, "band": band, "stratum": r["stratum"],
                    "d": abs(math.log10(r["fe"])) - abs(math.log10(idx[(drug, band, b)]["fe"]))})
    return out


def _drug_mean_d(prs: list[dict]) -> float:
    g: dict[str, list[float]] = {}
    for p in prs:
        g.setdefault(p["drug"], []).append(p["d"])
    return sum(sum(v) / len(v) for v in g.values()) / len(g)


def _wilcoxon_p(prs: list[dict]) -> Optional[float]:
    g: dict[str, list[float]] = {}
    for p in prs:
        g.setdefault(p["drug"], []).append(p["d"])
    diffs = [sum(v) / len(v) for v in g.values()]
    diffs = [x for x in diffs if abs(x) > 1e-12]
    if len(diffs) < 2:
        return None
    from scipy.stats import wilcoxon
    return float(wilcoxon(diffs).pvalue)


def compare(rows: list[dict], a: str, b: str, n_boot: int) -> dict:
    prs = _paired(rows, a, b)
    if not prs:
        return {"comparator": b, "n_pairs": 0, "n_clusters": 0}
    ci = cluster_bootstrap_ci(prs, _drug_mean_d, n_boot=n_boot, seed=SEED)
    return {
        "comparator": b, "n_pairs": len(prs), "n_clusters": ci["n_clusters"],
        "mean_abs_log10_diff": ci["estimate"], "ci95": [ci["lo"], ci["hi"]], "ci_method": ci["method"],
        "aafe_ratio": 10 ** ci["estimate"],  # <1 means PaedScale's typical fold error is smaller
        "wilcoxon_p_drug_level": _wilcoxon_p(prs),
    }


def _holm(ps: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    items = sorted(((p, k) for k, p in ps.items() if p is not None))
    m, adj, running = len(items), {}, 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return {k: adj.get(k) for k in ps}


def by_method(rows: list[dict], n_boot: int = 0) -> dict:
    out = {}
    for m in sorted({r["method"] for r in rows}):
        rs = [r for r in rows if r["method"] == m]
        s = summarize(rs)
        if n_boot and s["n_pairs"]:
            for key in ("aafe", "afe", "within_1_5", "within_2"):
                ci = cluster_bootstrap_ci(rs, lambda x, k=key: summarize(x)[k], n_boot=n_boot, seed=SEED)
                s[key + "_ci95"] = [ci["lo"], ci["hi"]]
        s["pair_weighted_aafe"] = summarize(rs, weight="pair")["aafe"]
        out[m] = s
    return out


def analyze(rows: list[dict], n_boot: int = 10000) -> dict:
    newborn = [r for r in rows if r["stratum"] in ("preterm_newborn", "term_newborn")]
    under2 = [r for r in rows if r["stratum"] in ("preterm_newborn", "term_newborn", "infant_toddler")]
    hyp = {}
    for name, subset in (("H1", newborn), ("H2", under2), ("H3", rows)):
        hyp[name] = compare(subset, "paedscale", PRIMARY_COMPARATOR, n_boot)
        hyp[name]["population"] = {"H1": "newborns (<28 d)", "H2": "<2 years", "H3": "all ages"}[name]
    gate = True
    for name in ("H1", "H2", "H3"):
        h = hyp[name]
        lo_hi = h.get("ci95")
        h["tested"] = gate
        h["significant"] = bool(gate and lo_hi and lo_hi[1] < 0)
        gate = h["significant"]
    sec = {c: compare(rows, "paedscale", c, n_boot) for c in SECONDARY_COMPARATORS}
    holm = _holm({c: s.get("wilcoxon_p_drug_level") for c, s in sec.items()})
    for c in sec:
        sec[c]["wilcoxon_p_holm"] = holm[c]
    strata = {}
    for st in STRATA:
        rs = [r for r in rows if r["stratum"] == st]
        if rs:
            strata[st] = by_method(rs)
    return {"hypotheses": hyp, "secondary": sec,
            "by_method": {"all": by_method(rows, n_boot=n_boot // 5 if n_boot >= 1000 else 0),
                          "under2": by_method(under2), "newborn": by_method(newborn)},
            "by_stratum": strata}


def sensitivity(refset: dict, n_boot: int) -> dict:
    """Pre-specified S1–S10: H3-style PaedScale vs A1 difference, plus PaedScale AAFE."""
    def run(**kw):
        rows = score(refset, methods=("paedscale", PRIMARY_COMPARATOR), **kw)
        c = compare(rows, "paedscale", PRIMARY_COMPARATOR, n_boot)
        nb = [r for r in rows if r["stratum"] in ("preterm_newborn", "term_newborn")]
        return {"all": c, "newborn": compare(nb, "paedscale", PRIMARY_COMPARATOR, n_boot),
                "paedscale_aafe": summarize([r for r in rows if r["method"] == "paedscale"])["aafe"]}

    flags = lambda d, b: (set(b.get("flags", [])) | set(d["fe"].get("flags", []))
                          | set(d["adult"].get("flags", [])))
    s = {
        "S1_exclude_mgkg_shared": run(keep=lambda n, d, b: "mgkg_shared" not in flags(d, b)),
        "S2_exclude_mismatch_qualitative_upto": run(keep=lambda n, d, b: not (
            flags(d, b) & {"indication_mismatch", "fe_qualitative", "up_to", "adult_up_to", "fe_not_in_label"})),
        "S3_all_css": run(force_css=True),
        "S4_weight_minus20": run(weight_scale=0.8),
        "S4_weight_plus20": run(weight_scale=1.2),
        "S5_ga_minus2": run(ga_shift=-2.0),
        "S5_ga_plus2": run(ga_shift=2.0),
        "S7_exclude_curve_source_drugs": run(keep=lambda n, d, b: n not in CURVE_SOURCE_DRUGS),
        "S8_exclude_titrated": run(keep=lambda n, d, b: n not in TITRATED_DRUGS),
        "S9_gfr_only_renal": run(keep=lambda n, d, b: (d.get("renal_mechanism") or {}).get("value")
                                 in ("glomerular_filtration", "not_renal_predominant")),
        "S10_midpoint_child": run(grid=False),
    }
    # S6 leave-one-drug-out on the all-ages difference
    names = [n for n, d in refset.items() if d.get("included")]
    lodo = {}
    for n in names:
        rows = score({k: v for k, v in refset.items() if k != n}, methods=("paedscale", PRIMARY_COMPARATOR))
        lodo[n] = _drug_mean_d(_paired(rows, "paedscale", PRIMARY_COMPARATOR))
    s["S6_leave_one_drug_out"] = {"min": min(lodo.values()), "max": max(lodo.values()),
                                  "by_left_out_drug": lodo}
    return s


def uncertainty_coverage(refset: dict) -> dict:
    """Exploratory: share of reference doses inside PaedScale's 90% parameter interval
    (arithmetic-midpoint child, maturation-parameter uncertainty only)."""
    from benchmark.methods import NOMINAL_CL_L_H, NOMINAL_VD_L, _fm
    from engine.uncertainty import dose_uncertainty_interval
    hits, n, widths = 0, 0, []
    for name, d in refset.items():
        if not d.get("included"):
            continue
        for b in d["bands"]:
            p = virtual_patients(b, grid=False)[0]
            pi = dose_uncertainty_interval(
                drug=name, weight_kg=p["weight_kg"], cl_adult_l_h=NOMINAL_CL_L_H, vd_adult_l=NOMINAL_VD_L,
                fm=_fm(d), target_metric=d["target_metric"], pma_weeks=p["pma_weeks"],
                adult_dose_mg_per_day=d["adult"]["daily"], n_draws=1000)
            q = pi["dose_mg_per_kg_per_day"]
            n += 1
            hits += q["p05"] <= b["ref_per_kg_daily"] <= q["p95"]
            widths.append(q["p95"] / q["p05"])
    widths.sort()
    return {"n_bands": n, "coverage_90": hits / n, "median_fold_width": widths[len(widths) // 2],
            "max_fold_width": widths[-1]}


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return "unknown"


def main(n_boot: int = 10000) -> dict:
    refset = load_reference_set()
    rows = score(refset)
    results = {
        "engine_commit": _git_commit(),
        "n_included_drugs": sum(1 for d in refset.values() if d.get("included")),
        "n_bands": len({(r["drug"], r["band"]) for r in rows}),
        "excluded": {k: {"criterion": v["excluded_by"], "reason": v["reason"]}
                     for k, v in refset.items() if not v.get("included")},
        **analyze(rows, n_boot=n_boot),
        "sensitivity": sensitivity(refset, n_boot=max(1000, n_boot // 10)),
        "uncertainty_coverage": uncertainty_coverage(refset),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(results, f, indent=1, sort_keys=True)
    with open(os.path.join(OUT, "pairs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["drug", "band", "stratum", "method", "pred", "ref", "fe",
                                          "in_range", "target_metric", "renal_mechanism", "flags"])
        w.writeheader()
        for r in rows:
            w.writerow({**r, "flags": ";".join(r["flags"]), "pred": f"{r['pred']:.6g}",
                        "fe": f"{r['fe']:.6g}"})
    try:
        from benchmark import figures
        figures.make_all(rows, results, refset, OUT)
    except ImportError as e:  # matplotlib optional for the numeric pipeline
        print(f"figures skipped: {e}", file=sys.stderr)
    return results


if __name__ == "__main__":
    res = main(n_boot=int(os.environ.get("BENCH_N_BOOT", "10000")))
    h = res["hypotheses"]
    for k in ("H1", "H2", "H3"):
        print(k, h[k]["population"], {x: h[k].get(x) for x in ("n_pairs", "n_clusters", "aafe_ratio", "ci95", "significant")})
