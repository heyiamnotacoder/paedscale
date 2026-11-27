"""Score every method against the FDA-label reference set and write all outputs.

    cd backend && python3 -m benchmark.run          # -> benchmark/output/

Implements benchmark/PROTOCOL.md (with Amendments 1–3). Deterministic: no network, no key,
fixed seeds. Harness only; product code never imports this package.
"""

from __future__ import annotations

import csv
import json
import math
import os
import subprocess
from typing import Callable, Optional

from benchmark.methods import (METHODS, NEWBORN_STRATA, STRATA, UNDER2_STRATA, ich_stratum, predict_band,
                               pathway_fractions, virtual_patients)
from benchmark.metrics import _by_drug, cluster_bootstrap_ci, summarize

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
SEED = 20261127
PRIMARY_COMPARATOR = "allometry_class"
SECONDARY_COMPARATORS = ("allometry", "bsa", "weight_linear")
CURVE_SOURCE_DRUGS = {"midazolam", "morphine"}      # S7: maturation curves fitted to these (midazolam is excluded by E1 anyway)
TITRATED_DRUGS = {"midazolam", "morphine", "famotidine"}  # S8


def load_reference_set(path: Optional[str] = None) -> dict:
    with open(path or os.path.join(HERE, "reference_set.json")) as f:
        return json.load(f)["drugs"]


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
                    "flags": sorted(_flags(d, b)),
                    "target_metric": d["target_metric"],
                    "renal_mechanism": (d.get("renal_mechanism") or {}).get("value"),
                })
    return rows


def _newborn(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["stratum"] in NEWBORN_STRATA]


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


TIE = 1e-12  # |d| below this is a tie (e.g. volume-matched cmax drugs, Amendment 1 §3)


def _drug_means(prs: list[dict]) -> list[float]:
    return [sum(p["d"] for p in ps) / len(ps) for ps in _by_drug(prs).values()]


def _drug_mean_d(prs: list[dict]) -> float:
    means = _drug_means(prs)
    return sum(means) / len(means)


def _wilcoxon_p(prs: list[dict]) -> Optional[float]:
    """Wilcoxon signed-rank on drug-level mean differences; tied drugs are dropped (and counted)."""
    diffs = [x for x in _drug_means(prs) if abs(x) > TIE]
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
        "n_tied_pairs": sum(abs(p["d"]) <= TIE for p in prs),
        "n_tied_drugs": sum(abs(x) <= TIE for x in _drug_means(prs)),
        "mean_abs_log10_diff": ci["estimate"], "ci95": [ci["lo"], ci["hi"]], "ci_method": ci["method"],
        "ci_n_boot": n_boot,
        "aafe_ratio": 10 ** ci["estimate"],  # <1 means PaedScale's typical fold error is smaller
        "wilcoxon_p_drug_level": _wilcoxon_p(prs),
        "per_drug_mean_d": {k: sum(p["d"] for p in ps) / len(ps) for k, ps in sorted(_by_drug(prs).items())},
    }


def _holm(ps: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    items = sorted(((p, k) for k, p in ps.items() if p is not None))
    m, adj, running = len(items), {}, 0.0
    for i, (p, k) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adj[k] = running
    return {k: adj.get(k) for k in ps}


SUMMARY_KEYS = ("aafe", "afe", "within_1_5", "within_2", "within_label_range")


def by_method(rows: list[dict], n_boot: int) -> dict:
    """Drug-weighted summary per method, each metric with a drug-clustered 95% CI."""
    out = {}
    for m in sorted({r["method"] for r in rows}):
        rs = [r for r in rows if r["method"] == m]
        s = summarize(rs)
        for key in SUMMARY_KEYS:
            ci = cluster_bootstrap_ci(rs, lambda x, k=key: summarize(x)[k], n_boot=n_boot, seed=SEED)
            s[key + "_ci95"] = [ci["lo"], ci["hi"]]
            s[key + "_ci_method"] = ci["method"]
        s["ci_n_boot"] = n_boot
        s["pair_weighted_aafe"] = summarize(rs, weight="pair")["aafe"]
        out[m] = s
    return out


def analyze(rows: list[dict], n_boot: int = 10000) -> dict:
    newborn = _newborn(rows)
    under2 = [r for r in rows if r["stratum"] in UNDER2_STRATA]
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
    strata = {st: by_method(rs, n_boot) for st in STRATA if (rs := [r for r in rows if r["stratum"] == st])}
    return {"hypotheses": hyp, "secondary": sec,
            "by_method": {"all": by_method(rows, n_boot), "under2": by_method(under2, n_boot),
                          "newborn": by_method(newborn, n_boot)},
            "by_stratum": strata}


def _flags(d: dict, b: dict) -> set:
    return set(b.get("flags", [])) | set(d["fe"].get("flags", [])) | set(d["adult"].get("flags", []))


S2_FLAGS = {"indication_mismatch", "fe_qualitative", "up_to", "adult_up_to"}
# Pre-specified subsets: keep(drug_name, drug, band) -> bool
SUBSETS: dict[str, Callable[[str, dict, dict], bool]] = {
    "S1_exclude_mgkg_shared": lambda n, d, b: "mgkg_shared" not in _flags(d, b),
    "S2_exclude_mismatch_qualitative_upto": lambda n, d, b: not (_flags(d, b) & S2_FLAGS),
    "S7_exclude_curve_source_drugs": lambda n, d, b: n not in CURVE_SOURCE_DRUGS,
    "S8_exclude_titrated": lambda n, d, b: n not in TITRATED_DRUGS,
    "S9_gfr_only_renal": lambda n, d, b: (d.get("renal_mechanism") or {}).get("value") == "glomerular_filtration",
}
# Pre-specified input perturbations: keyword arguments to score()
PERTURBATIONS: dict[str, dict] = {
    "S3_all_css": {"force_css": True},
    "S4_weight_minus20": {"weight_scale": 0.8},
    "S4_weight_plus20": {"weight_scale": 1.2},
    "S5_ga_minus2": {"ga_shift": -2.0},
    "S5_ga_plus2": {"ga_shift": 2.0},
    "S10_midpoint_child": {"grid": False},
}


def sensitivity(refset: dict, n_boot: int) -> dict:
    """Pre-specified S1–S10: PaedScale vs A1 on newborns (H1) and all ages (H3), plus PaedScale AAFE."""
    def run(**kw):
        rows = score(refset, methods=("paedscale", PRIMARY_COMPARATOR), **kw)
        return {"newborn": compare(_newborn(rows), "paedscale", PRIMARY_COMPARATOR, n_boot),
                "all": compare(rows, "paedscale", PRIMARY_COMPARATOR, n_boot),
                "paedscale_aafe": summarize([r for r in rows if r["method"] == "paedscale"]).get("aafe")}

    s = {name: run(keep=keep) for name, keep in SUBSETS.items()}
    s.update({name: run(**kw) for name, kw in PERTURBATIONS.items()})
    # S6: leave one drug out, range of the drug-weighted mean difference
    s6 = {"newborn": {}, "all": {}}
    for n in sorted(k for k, d in refset.items() if d.get("included")):
        rows = score({k: v for k, v in refset.items() if k != n}, methods=("paedscale", PRIMARY_COMPARATOR))
        for pop, rs in (("newborn", _newborn(rows)), ("all", rows)):
            prs = _paired(rs, "paedscale", PRIMARY_COMPARATOR)
            if prs:
                s6[pop][n] = _drug_mean_d(prs)
    s["S6_leave_one_drug_out"] = {pop: {"min": min(v.values()), "max": max(v.values()), "by_left_out_drug": v}
                                  for pop, v in s6.items() if v}
    return dict(sorted(s.items()))


def uncertainty_coverage(refset: dict) -> dict:
    """Exploratory: share of reference doses inside PaedScale's 90% parameter interval
    (arithmetic-midpoint child, maturation-parameter uncertainty only)."""
    from benchmark.methods import NOMINAL_CL_L_H, NOMINAL_VD_L
    from engine.uncertainty import dose_uncertainty_interval
    hits, n, widths = 0, 0, []
    for name, d in refset.items():
        if not d.get("included"):
            continue
        for b in d["bands"]:
            p = virtual_patients(b, grid=False)[0]
            pi = dose_uncertainty_interval(
                drug=name, weight_kg=p["weight_kg"], cl_adult_l_h=NOMINAL_CL_L_H, vd_adult_l=NOMINAL_VD_L,
                fm=pathway_fractions(d), target_metric=d["target_metric"], pma_weeks=p["pma_weeks"],
                adult_dose_mg_per_day=d["adult"]["daily"], n_draws=1000)
            q = pi["dose_mg_per_kg_per_day"]
            n += 1
            hits += q["p05"] <= b["ref_per_kg_daily"] <= q["p95"]
            widths.append(q["p95"] / q["p05"])
    widths.sort()
    return {"n_bands": n, "coverage_90": hits / n, "median_fold_width": widths[len(widths) // 2],
            "max_fold_width": widths[-1]}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=HERE, text=True).strip()


def provenance(n_boot: int) -> dict:
    """What produced an output: engine commit, whether the tree was dirty, settings, versions."""
    import platform
    from importlib.metadata import version
    return {
        "engine_commit": _git("rev-parse", "HEAD"),
        "working_tree_dirty": bool(_git("status", "--porcelain", "--", "..", ":(exclude)output")),
        "n_boot": n_boot, "seed": SEED,
        "versions": {"python": platform.python_version(),
                     **{lib: version(lib) for lib in ("scipy", "numpy", "matplotlib")}},
    }


PAIR_FIELDS = ["drug", "band", "stratum", "method", "pred", "ref", "fe", "in_range", "target_metric",
               "renal_mechanism", "flags"]


def write_pairs_csv(rows: list[dict], path: str, prov: dict) -> None:
    with open(path, "w", newline="") as f:
        f.write(f"# engine_commit={prov['engine_commit']} working_tree_dirty={prov['working_tree_dirty']}\n")
        w = csv.DictWriter(f, fieldnames=PAIR_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "flags": ";".join(r["flags"]), "pred": f"{r['pred']:.6g}", "fe": f"{r['fe']:.6g}"})


def main(n_boot: int = 10000, out: str = OUT) -> dict:
    prov = provenance(n_boot)
    refset = load_reference_set()
    rows = score(refset)
    results = {
        "provenance": prov,
        "n_included_drugs": sum(1 for d in refset.values() if d.get("included")),
        "n_bands": len({(r["drug"], r["band"]) for r in rows}),
        "excluded": {k: {"criterion": v["excluded_by"], "reason": v["reason"]}
                     for k, v in refset.items() if not v.get("included")},
        **analyze(rows, n_boot=n_boot),
        "sensitivity": sensitivity(refset, n_boot=n_boot),
        "uncertainty_coverage": uncertainty_coverage(refset),
    }
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(results, f, indent=1, sort_keys=True)
    write_pairs_csv(rows, os.path.join(out, "pairs.csv"), prov)
    from benchmark import figures
    figures.make_all(rows, results, out)
    return results


if __name__ == "__main__":
    res = main(n_boot=int(os.environ.get("BENCH_N_BOOT", "10000")))
    h = res["hypotheses"]
    for k in ("H1", "H2", "H3"):
        print(k, h[k]["population"], {x: h[k].get(x) for x in ("n_pairs", "n_clusters", "aafe_ratio", "ci95", "significant")})
