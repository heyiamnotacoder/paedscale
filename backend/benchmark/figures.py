"""Manuscript figures for the label benchmark (harness only; matplotlib, static PNG + PDF).

Palette: the dataviz reference categorical slots 1–3 (validated all-pairs, light surface),
with gray for context series. Every figure also has marker-shape encoding and a legend,
and the numbers behind each figure are in output/results.json and output/pairs.csv.
"""

from __future__ import annotations

import os
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from benchmark.metrics import CONCORDANCE_BAND  # noqa: E402
from benchmark.methods import STRATA  # noqa: E402

BLUE, ORANGE, AQUA, GRAY, INK, INK2 = "#257de0", "#f47230", "#00b894", "#9a9a9a", "#191919", "#666666"
STRATUM_LABEL = {"preterm_newborn": "Preterm\nnewborn", "term_newborn": "Term\nnewborn",
                 "infant_toddler": "Infant/\ntoddler", "child": "Child\n2–11 y", "adolescent": "Adolescent\n12–16 y"}
SHOWN = [("weight_linear", "Weight-linear", GRAY, "s"),
         ("allometry_class", "Allometry + class rule", ORANGE, "^"),
         ("paedscale", "PaedScale (allometry × maturation)", BLUE, "o")]


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
        ax.spines[s].set_linewidth(0.8)
    ax.tick_params(colors=INK2, labelcolor=INK, width=0.8)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.6)
    ax.set_axisbelow(True)


def _save(fig, out, name, prov=None):
    note = f"PaedScale label benchmark; engine_commit={(prov or {}).get('engine_commit', 'n/a')}"
    for ext, meta in (("png", {"Description": note}), ("pdf", {"Subject": note})):
        fig.savefig(os.path.join(out, f"{name}.{ext}"), dpi=300, bbox_inches="tight", metadata=meta)
    plt.close(fig)


def fold_error_by_stratum(rows, out, prov=None):
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _style(ax)
    lo, hi = CONCORDANCE_BAND
    ax.axhspan(lo, hi, color="#eef4fc", zorder=0, label=f"Concordance band {lo:g}–{hi:g}×")
    ax.axhline(1.0, color=INK2, linewidth=0.8)
    rng = random.Random(0)
    for j, (m, lab, col, mk) in enumerate(SHOWN):
        xs, ys = [], []
        for i, st in enumerate(STRATA):
            for r in rows:
                if r["method"] == m and r["stratum"] == st:
                    xs.append(i + (j - 1) * 0.24 + rng.uniform(-0.06, 0.06))
                    ys.append(r["fe"])
        ax.scatter(xs, ys, s=22, marker=mk, color=col, edgecolors="white", linewidths=0.6,
                   label=lab, zorder=3)
    ax.set_yscale("log")
    ticks = [0.25, 0.5, 0.67, 1, 1.5, 2, 4]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:g}×" for t in ticks])
    ax.set_xticks(range(len(STRATA)))
    ax.set_xticklabels([STRATUM_LABEL[s] for s in STRATA])
    ax.set_ylabel("Fold error (predicted ÷ labeled dose)", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="upper left", ncol=2)
    _save(fig, out, "fig2_fold_error_by_stratum", prov)


def paired_difference_forest(results, out, prov=None):
    """Per drug: 10^mean(d), the ratio of typical fold errors, PaedScale / A1 (all ages)."""
    h3 = results["hypotheses"]["H3"]
    if not h3.get("n_pairs"):
        return
    items = sorted((d, k) for k, d in h3["per_drug_mean_d"].items())
    fig, ax = plt.subplots(figsize=(6.4, 0.26 * len(items) + 1.4))
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#e6e6e6", linewidth=0.6)
    ys = list(range(len(items)))
    ax.scatter([10 ** d for d, _ in items], ys, s=26, color=BLUE, edgecolors="white", linewidths=0.6, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels([k.replace("_", " ") for _, k in items], fontsize=8)
    est, (lo, hi) = 10 ** h3["mean_abs_log10_diff"], [10 ** x for x in h3["ci95"]]
    y0 = -1.2
    # Interval and estimate drawn separately: a BCa interval need not contain its estimate.
    ax.hlines(y0, lo, hi, color=INK, linewidth=1.2)
    ax.vlines([lo, hi], y0 - 0.25, y0 + 0.25, color=INK, linewidth=1.2)
    ax.scatter([est], [y0], marker="D", s=36, color=INK, zorder=3)
    ax.text(max(hi, est), y0, "  all drugs, 95% CI", va="center", fontsize=8, color=INK)
    ax.axvline(1.0, color=INK2, linewidth=0.8)
    ax.set_xscale("log")
    ax.set_xlabel("Ratio of typical fold error, PaedScale ÷ allometry + class rule\n(<1 favours PaedScale)", color=INK)
    ax.set_ylim(-2, len(items))
    _save(fig, out, "fig3_paired_difference_by_drug", prov)


def maturation_curves(out, prov=None):
    from engine.constants import MATURATION
    from engine.pk_engine import maturation_factor
    from engine.uncertainty import sample_curve
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    _style(ax)
    pma = [24 * (1.02 ** i) for i in range(0, 175)]  # 24 wk -> ~ 25 y, log-spaced
    pma = [p for p in pma if p <= 52 * 18 + 40]
    rng = random.Random(1)
    colours = {"renal_gfr": BLUE, "cyp3a4": ORANGE, "ugt2b7": AQUA}
    for key, params in MATURATION.items():
        draws = [sample_curve(params, rng) for _ in range(400)]
        lo, hi, mid = [], [], []
        for p in pma:
            v = sorted(maturation_factor(p, d["tm50_weeks"], d["hill"]) for d in draws)
            lo.append(v[round(0.05 * (len(v) - 1))])   # symmetric 5th/95th order statistics
            hi.append(v[round(0.95 * (len(v) - 1))])
            mid.append(maturation_factor(p, params["tm50_weeks"], params["hill"]))
        ax.fill_between(pma, lo, hi, color=colours[key], alpha=0.18, linewidth=0)
        ax.plot(pma, mid, color=colours[key], linewidth=2, label=f"{params['label']} (TM50 {params['tm50_weeks']} wk, Hill {params['hill']})")
    ax.set_xscale("log")
    xt = [(24, "24 wk"), (40, "Term"), (40 + 26, "6 mo"), (40 + 52, "1 y"), (40 + 104, "2 y"), (40 + 52 * 5, "5 y"), (40 + 52 * 12, "12 y")]
    ax.set_xticks([x for x, _ in xt])
    ax.set_xticklabels([t for _, t in xt])
    ax.minorticks_off()
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Fraction of adult clearance\n(maturation factor)", color=INK)
    ax.set_xlabel("Postmenstrual age (log scale)", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _save(fig, out, "fig1_maturation_curves", prov)


def make_all(rows, results, out):
    os.makedirs(out, exist_ok=True)
    prov = results.get("provenance")
    maturation_curves(out, prov)
    fold_error_by_stratum(rows, out, prov)
    paired_difference_forest(results, out, prov)
