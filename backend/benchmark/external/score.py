"""External validation, step 4: score every method against published pediatric clearance.

    cd backend && python3 -m benchmark.external.score      # -> benchmark/external/output/

Implements benchmark/external/PROTOCOL.md (Amendments 1-14). Reads only the frozen dataset
(extraction/final/<drug>.json, dataset/authors.json) and the committed search snapshot. It is
the only external-validation module that imports the engine. Deterministic: no network.
"""
from __future__ import annotations

import itertools
import json
import math
import os
import statistics
from typing import Optional

from benchmark.external.curation import extraction as ex
from benchmark.external.curation.screening import replay
from benchmark.growth import median_weight_kg
from benchmark.methods import pathway_fractions
from benchmark.metrics import by_drug, cluster_bootstrap_ci, summarize
from benchmark.run import _holm
from engine.pk_engine import compute_pediatric_dose

HERE = os.path.dirname(os.path.abspath(__file__))
FINAL_DIR = os.path.join(HERE, "extraction", "final")
AUTHORS = os.path.join(HERE, "dataset", "authors.json")
SEARCH_DIR = os.path.join(HERE, "search")
REFSET = os.path.join(os.path.dirname(HERE), "reference_set.json")
OUT = os.path.join(HERE, "output")

SEED = 20261127
REF_KG = 70.0
GRID_POINTS = 7
NOMINAL_VD_L = 50.0            # Vd does not enter clearance
METHODS = ("weight_linear", "bsa", "allometry", "paedscale")
PRIMARY = "allometry"
MIN_DRUGS_CONFIRMATORY = 8     # Amendment 1 §8
MIN_DRUGS_STRATUM_CI = 5
ADULT_ABSTRACTS = 5
UNDER2_DAYS = 24 * ex.DAYS_PER_MONTH
BSA_UNITS = {"mL/min/1.73m2", "L/h/1.73m2", "mL/h/1.73m2", "mL/min/m2", "L/h/m2"}
STRATA = ("preterm_newborn", "term_newborn", "infant_toddler", "child", "adolescent")
CURVE_AUTHORS = ("Anderson BJ", "Holford NH", "Holford NHG", "Rhodin MM", "Anand KJ", "Anand KJS", "Larsson P")


def bsa_costeff(w: float) -> float:
    return (4.0 * w + 7.0) / (w + 90.0)


# ---------------------------------------------------------------- adult reference

def adult_value_l_h(v: dict) -> float:
    """One adult value at 70 kg (Amendment 1 §2): per kg × 70; absolute × (70/WT)^0.75 with a
    stated weight; absolute as reported without one."""
    cl, unit = v["cl"]["value"], v["cl"]["unit"]
    if unit in ex.PER_KG_UNITS:
        return ex.to_l_per_h(cl, unit, weight_kg=REF_KG)
    abs_l_h = ex.to_l_per_h(cl, unit)
    w = ex.central(v.get("weight_kg"), geometric=False)
    return abs_l_h * (REF_KG / w) ** 0.75 if w else abs_l_h


def adult_reference(studies: list[dict], keep=lambda s: True) -> dict:
    """Median over the first five qualifying abstracts of each abstract's median value
    (Amendment 1 §2, Amendment 2 §5); E4 uses the first abstract alone."""
    per = [statistics.median(adult_value_l_h(v) for v in s["values"])
           for s in studies if s["decision"] == "include" and keep(s)][:ADULT_ABSTRACTS]
    if not per:
        return {"n_abstracts": 0, "median_l_h": None, "first_l_h": None, "per_abstract_l_h": []}
    return {"n_abstracts": len(per), "median_l_h": statistics.median(per), "first_l_h": per[0],
            "per_abstract_l_h": per}


# ---------------------------------------------------------------- the child

def _central_pna(o: dict) -> Optional[float]:
    return ex.central(o.get("pna_days"), geometric=True)


def central_age(o: dict) -> tuple[float, float, Optional[float]]:
    """(central postnatal age in days, GA in weeks, central PMA or None). A PMA-only group's
    postnatal age is PMA − GA, floored at 0 (Amendment 4 §4)."""
    ga = ex.gestational_weeks(o)
    pma = ex.central(o.get("pma_weeks"), geometric=False)
    pna = _central_pna(o)
    if pna is None:
        pna = max(pma - ga, 0.0) * 7
    return pna, ga, pma


def _logspace(lo: float, hi: float) -> list[float]:
    if hi - lo < 1e-9:
        return [lo]
    a, b = math.log(lo), math.log(hi)
    return [math.exp(a + (b - a) * i / (GRID_POINTS - 1)) for i in range(GRID_POINTS)]


def grid(o: dict) -> list[dict]:
    """The children a group's prediction averages over (Amendment 1 §6, Amendment 2 §7,
    Amendment 12 §2). A stated PMA is used directly, across its range when one is stated;
    otherwise the postnatal range (from max(low, 1 day)). A stated weight is used at every
    point; otherwise the growth-table weight at each point's age."""
    ga = ex.gestational_weeks(o)
    w_stated = ex.central(o.get("weight_kg"), geometric=False)
    if o.get("pma_weeks") is not None:
        rng = ex.age_range(o, "pma")
        pmas = _logspace(*rng) if rng else [ex.central(o["pma_weeks"], geometric=False)]
        pts = [(max(p - ga, 0.0) * 7, p) for p in pmas]
    else:
        rng = ex.age_range(o, "pna")
        pnas = _logspace(max(rng[0], 1.0), rng[1]) if rng else [o["pna_days"]]
        pts = [(t, ga + t / 7) for t in pnas]
    return [{"pna_days": t, "pma_weeks": p,
             "weight_kg": w_stated if w_stated else median_weight_kg(t, gestational_age_weeks=ga)}
            for t, p in pts]


def observed(o: dict, study_flags=()) -> dict:
    """Observed total clearance in L/h and the scorer's flags (PROTOCOL.md 'Extraction';
    Amendment 1 §3, §7; Amendment 9 §3)."""
    flags = set(o.get("flags") or []) | set(study_flags)
    pna, ga, _ = central_age(o)
    w = ex.central(o.get("weight_kg"), geometric=False)
    if not w:
        w = median_weight_kg(pna, gestational_age_weeks=ga)
        flags.add("weight_imputed")
    if ex.ga_imputed(o):
        flags.add("ga_imputed")
    unit = o["cl"]["unit"]
    bsa = None
    if unit in BSA_UNITS:
        bsa = o.get("bsa_m2")
        if not bsa and o.get("height_cm") and o.get("weight_kg") is not None:
            bsa = math.sqrt(o["height_cm"] * w / 3600)          # Mosteller
        if not bsa:
            bsa = bsa_costeff(w)
            flags.add("bsa_costeff")
    return {"cl_l_h": ex.to_l_per_h(o["cl"]["value"], unit, weight_kg=w, bsa_m2=bsa),
            "weight_kg": w, "pna_days": pna, "ga_weeks": ga, "flags": sorted(flags)}


# ---------------------------------------------------------------- predictions

def predict_point(method: str, cl_adult: float, drug: dict, p: dict) -> float:
    w = p["weight_kg"]
    if method == "weight_linear":
        return cl_adult * w / REF_KG
    if method == "bsa":
        return cl_adult * bsa_costeff(w) / bsa_costeff(REF_KG)
    if method == "allometry":
        return cl_adult * (w / REF_KG) ** 0.75
    if method == "paedscale":
        r = compute_pediatric_dose(drug="external", weight_kg=w, cl_adult_l_h=cl_adult,
                                   vd_adult_l=NOMINAL_VD_L, fm=pathway_fractions(drug),
                                   target_metric="css", pma_weeks=p["pma_weeks"])
        if r.blocked:
            raise ValueError(f"engine blocked an external-validation case: {r.block_reason}")
        return r.cl_child_l_h
    raise KeyError(method)


def predict(method: str, cl_adult: float, drug: dict, o: dict) -> float:
    """Geometric mean of the predicted clearance over the group's grid."""
    logs = [math.log(predict_point(method, cl_adult, drug, p)) for p in grid(o)]
    return math.exp(sum(logs) / len(logs))


# ---------------------------------------------------------------- statistics

def paired(rows: list[dict], a: str = "paedscale", b: str = PRIMARY) -> list[dict]:
    """Per observation: d = |log10 FE_a| − |log10 FE_b|. Negative favours `a`."""
    idx = {(r["drug"], r["pmid"], r["obs"], r["method"]): r for r in rows}
    out = []
    for (drug, pmid, i, m), r in idx.items():
        if m == a and (drug, pmid, i, b) in idx:
            out.append({"drug": drug, "pmid": pmid, "obs": i, "stratum": r["stratum"],
                        "d": abs(math.log10(r["fe"])) - abs(math.log10(idx[(drug, pmid, i, b)]["fe"]))})
    return out


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


def drug_means(prs: list[dict], by_study: bool = False) -> dict[str, float]:
    """Each drug's mean d over its observations, or over its studies' means (E5)."""
    out = {}
    for drug, ps in sorted(by_drug(prs).items()):
        if by_study:
            studies = {}
            for p in ps:
                studies.setdefault(p["pmid"], []).append(p["d"])
            out[drug] = _mean(_mean(v) for v in studies.values())
        else:
            out[drug] = _mean(p["d"] for p in ps)
    return out


def drug_mean_d(prs: list[dict], by_study: bool = False) -> float:
    return _mean(drug_means(prs, by_study).values())


def sign_flip_p(diffs: list[float]) -> Optional[float]:
    """Exact two-sided sign-flip permutation p on drug-level differences (Amendment 1 §8)."""
    if not diffs:
        return None
    obs = abs(sum(diffs))
    hits = sum(abs(sum(s * d for s, d in zip(signs, diffs))) >= obs - 1e-12
               for signs in itertools.product((1, -1), repeat=len(diffs)))
    return hits / 2 ** len(diffs)


def _wilcoxon(diffs: list[float]) -> Optional[float]:
    diffs = [x for x in diffs if abs(x) > 1e-12]
    if len(diffs) < 2:
        return None
    from scipy.stats import wilcoxon
    return float(wilcoxon(diffs).pvalue)


def compare(rows: list[dict], a: str, b: str, n_boot: int, by_study: bool = False) -> dict:
    prs = paired(rows, a, b)
    if not prs:
        return {"comparator": b, "n_obs": 0, "n_drugs": 0}
    means = drug_means(prs, by_study)
    ci = cluster_bootstrap_ci(prs, lambda x: drug_mean_d(x, by_study), n_boot=n_boot, seed=SEED)
    return {"comparator": b, "n_obs": len(prs), "n_drugs": len(means),
            "mean_abs_log10_diff": ci["estimate"], "ci95": [ci["lo"], ci["hi"]], "ci_method": ci["method"],
            "aafe_ratio": 10 ** ci["estimate"],
            "sign_flip_p": sign_flip_p(list(means.values()) if len(means) <= 20 else []),
            "wilcoxon_p_drug_level": _wilcoxon(list(means.values())), "per_drug_mean_d": means}


def hypothesis(rows: list[dict], n_boot: int, by_study: bool = False) -> dict:
    """PaedScale vs allometry. Success needs ≥8 drugs and an upper 95% bound below zero."""
    h = compare(rows, "paedscale", PRIMARY, n_boot, by_study)
    h["confirmatory"] = h["n_drugs"] >= MIN_DRUGS_CONFIRMATORY
    h["success"] = bool(h["confirmatory"] and h.get("ci95") and h["ci95"][1] < 0)
    h["evidence_against"] = bool(h.get("ci95") and h["ci95"][0] > 0)
    return h


SUMMARY_KEYS = ("aafe", "afe", "within_2", "within_1_5")


def by_method(rows: list[dict], n_boot: int) -> dict:
    out = {}
    for m in METHODS:
        rs = [r for r in rows if r["method"] == m]
        if not rs:
            continue
        s = summarize(rs)
        for k in SUMMARY_KEYS:
            if n_boot:
                ci = cluster_bootstrap_ci(rs, lambda x, k=k: summarize(x)[k], n_boot=n_boot, seed=SEED)
                s[k + "_ci95"] = [ci["lo"], ci["hi"]]
        out[m] = s
    return out


# ---------------------------------------------------------------- the dataset

def load_dataset(final_dir: str = FINAL_DIR) -> dict:
    with open(REFSET, encoding="utf-8") as f:
        ref = json.load(f)["drugs"]
    authors = json.load(open(AUTHORS, encoding="utf-8")) if os.path.exists(AUTHORS) else {}
    out = {}
    for fn in sorted(os.listdir(final_dir)):
        if not fn.endswith(".json"):
            continue
        drug = fn[:-5]
        rec = json.load(open(os.path.join(final_dir, fn), encoding="utf-8"))
        snap = json.load(open(os.path.join(SEARCH_DIR, fn), encoding="utf-8"))
        years = {r["pmid"]: r["year"] for k in ("pediatric", "adult") for r in snap[k]}
        out[drug] = {"record": rec, "drug": ref[drug], "years": years, "authors": authors}
    return out


def rows_for(ds: dict, *, adult: str = "median_l_h", keep=lambda u: True,
             adult_keep=lambda s: True) -> tuple[list[dict], dict]:
    """One row per (observation, method). `keep` filters used observations (sensitivities)."""
    rows, adults = [], {}
    for name, d in sorted(ds.items()):
        ref = adult_reference(d["record"]["adult"], keep=adult_keep)
        adults[name] = ref
        cl_adult = ref[adult]
        if cl_adult is None:                       # no adult reference: drug excluded
            continue
        flags_by_pmid = {s["pmid"]: s.get("flags") or [] for s in d["record"]["pediatric"]}
        for i, u in enumerate(replay(d["record"])):
            obs = observed(u["obs"], flags_by_pmid[u["pmid"]])
            u = {**u, "drug": name, "observed": obs, "year": int(d["years"].get(u["pmid"]) or 0),
                 "authors": d["authors"].get(u["pmid"], [])}
            if not keep(u):
                continue
            for m in METHODS:
                pred = predict(m, cl_adult, d["drug"], u["obs"])
                rows.append({"drug": name, "pmid": u["pmid"], "obs": i, "method": m,
                             "stratum": u["stratum"], "under2": obs["pna_days"] < UNDER2_DAYS,
                             "flags": obs["flags"], "pred_l_h": pred, "obs_l_h": obs["cl_l_h"],
                             "fe": pred / obs["cl_l_h"]})
    return rows, adults


def _is_curve_author(authors: list[str]) -> bool:
    return any(a == c or a.startswith(c + " ") or a.replace(".", "") == c for a in authors for c in CURVE_AUTHORS)


SENSITIVITY = {
    "E1_exclude_imputed_weight_or_ga": dict(keep=lambda u: not {"weight_imputed", "ga_imputed"} & set(u["observed"]["flags"])),
    "E2_exclude_critically_ill": dict(keep=lambda u: "critically_ill" not in u["observed"]["flags"]),
    "E3_exclude_standardized_or_fixed": dict(keep=lambda u: not {"allometric_standardized", "fixed_maturation", "fixed_allometry"} & set(u["observed"]["flags"])),
    "E4_first_adult_abstract": dict(adult="first_l_h"),
    "E7_exclude_curve_source_authors": dict(keep=lambda u: not _is_curve_author(u["authors"])),
    "E8_exclude_before_1995": dict(keep=lambda u: u["year"] >= 1995),
    "E9_exclude_route_unstated": dict(keep=lambda u: "route_unstated" not in u["observed"]["flags"],  # Amendment 14
                                      adult_keep=lambda s: "route_unstated" not in (s.get("flags") or [])),
}


def two_hypotheses(rows: list[dict], n_boot: int, by_study: bool = False) -> dict:
    he1 = hypothesis([r for r in rows if r["under2"]], n_boot, by_study)
    he2 = hypothesis(rows, n_boot, by_study)
    he2["tested"] = he1["success"]                 # HE2 is tested only if HE1 succeeds
    return {"HE1_under2": he1, "HE2_all_ages": he2}


def uncertainty_coverage(ds: dict, rows: list[dict]) -> dict:
    """Exploratory: share of observed clearances inside PaedScale's 90% parameter interval at
    the group's central age and weight (Amendment 12 §4). Drug-weighted."""
    from engine.uncertainty import dose_uncertainty_interval
    hits = []
    seen = {(r["drug"], r["pmid"], r["obs"]) for r in rows if r["method"] == "paedscale"}
    for name, d in sorted(ds.items()):
        ref = adult_reference(d["record"]["adult"])["median_l_h"]
        if ref is None:
            continue
        flags_by_pmid = {s["pmid"]: s.get("flags") or [] for s in d["record"]["pediatric"]}
        for i, u in enumerate(replay(d["record"])):
            if (name, u["pmid"], i) not in seen:
                continue
            obs = observed(u["obs"], flags_by_pmid[u["pmid"]])
            pna, ga, pma = central_age(u["obs"])
            pi = dose_uncertainty_interval(drug=name, weight_kg=obs["weight_kg"], cl_adult_l_h=ref,
                                           vd_adult_l=NOMINAL_VD_L, fm=pathway_fractions(d["drug"]),
                                           target_metric="css", pma_weeks=pma if pma is not None else ga + pna / 7,
                                           n_draws=1000)
            q = pi["cl_child_l_h"]
            hits.append({"drug": name, "hit": float(q["p05"] <= obs["cl_l_h"] <= q["p95"])})
    if not hits:
        return {"n_obs": 0}
    return {"n_obs": len(hits), "n_drugs": len(by_drug(hits)),
            "coverage_90_drug_weighted": _mean(_mean(h["hit"] for h in hs) for hs in by_drug(hits).values())}


def analyze(ds: dict, n_boot: int = 10000) -> dict:
    rows, adults = rows_for(ds)
    hyp = two_hypotheses(rows, n_boot)
    sec = {c: compare(rows, "paedscale", c, n_boot) for c in ("weight_linear", "bsa")}
    holm = _holm({c: s.get("wilcoxon_p_drug_level") for c, s in sec.items()})
    for c in sec:
        sec[c]["wilcoxon_p_holm"] = holm[c]
    strata = {}
    for st in STRATA:
        rs = [r for r in rows if r["stratum"] == st]
        if rs:
            enough = len(by_drug(rs)) >= MIN_DRUGS_STRATUM_CI
            strata[st] = {"by_method": by_method(rs, n_boot if enough else 0),
                          "paedscale_vs_allometry": compare(rs, "paedscale", PRIMARY, n_boot if enough else 0)
                          if enough else {"n_drugs": len(by_drug(rs)), "per_drug_mean_d": drug_means(paired(rs))}}
    sens = {}
    for name, kw in SENSITIVITY.items():
        r2, _ = rows_for(ds, **kw)
        sens[name] = two_hypotheses(r2, n_boot)
    sens["E5_study_weighted"] = two_hypotheses(rows, n_boot, by_study=True)
    loo = {"HE1_under2": {}, "HE2_all_ages": {}}
    for left in sorted({r["drug"] for r in rows}):
        rs = [r for r in rows if r["drug"] != left]
        for key, sub in (("HE1_under2", [r for r in rs if r["under2"]]), ("HE2_all_ages", rs)):
            prs = paired(sub)
            if prs:
                loo[key][left] = drug_mean_d(prs)
    sens["E6_leave_one_drug_out"] = {k: {"min": min(v.values()), "max": max(v.values()), "by_left_out_drug": v}
                                     for k, v in loo.items() if v}
    return {"hypotheses": hyp, "secondary": sec,
            "by_method": {"all": by_method(rows, n_boot), "under2": by_method([r for r in rows if r["under2"]], n_boot)},
            "by_stratum": strata, "sensitivity": sens,
            "uncertainty_coverage": uncertainty_coverage(ds, rows),
            "adult_reference": adults, "n_obs": len(rows) // len(METHODS),
            "n_drugs": len(by_drug(rows))}, rows


def main(n_boot: int = 10000, out: str = OUT) -> dict:
    import csv
    from benchmark.run import provenance
    ds = load_dataset()
    res, rows = analyze(ds, n_boot)
    res["provenance"] = provenance(n_boot)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "results.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
    with open(os.path.join(out, "observations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["drug", "pmid", "obs", "method", "stratum", "under2",
                                          "obs_l_h", "pred_l_h", "fe", "flags"])
        w.writeheader()
        for r in rows:
            w.writerow({**{k: r[k] for k in w.fieldnames if k != "flags"}, "flags": ";".join(r["flags"])})
    return res


if __name__ == "__main__":
    import sys
    main(n_boot=int(sys.argv[1]) if len(sys.argv) > 1 else 10000)
