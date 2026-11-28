"""Figures for the external validation (PROTOCOL.md; harness only, matplotlib PNG + PDF).

Same palette and styling as the label benchmark's figures. The numbers behind each figure are in
output/results.json and output/observations.csv.
"""
from __future__ import annotations

import os

from benchmark.figures import BLUE, GRAY, INK, INK2, ORANGE, _style, plt
from benchmark.metrics import CONCORDANCE_BAND
from matplotlib.ticker import NullFormatter

SHOWN = [("weight_linear", "Weight-linear", GRAY, "s"),
         ("allometry", "Allometry (primary comparator)", ORANGE, "^"),
         ("paedscale", "PaedScale (allometry × maturation)", BLUE, "o")]
AGE_TICKS = [(1, "1 d"), (7, "1 wk"), (30.4, "1 mo"), (182.6, "6 mo"), (365.25, "1 y"), (730.5, "2 y"),
             (1826, "5 y"), (4383, "12 y")]


def _save(fig, out, name, prov=None):
    note = f"PaedScale external validation; engine_commit={(prov or {}).get('engine_commit', 'n/a')}"
    for ext, meta in (("png", {"Description": note}), ("pdf", {"Subject": note})):
        fig.savefig(os.path.join(out, f"{name}.{ext}"), dpi=300, bbox_inches="tight", metadata=meta)
    plt.close(fig)


def _fold_ticks(ax, values, axis="y"):
    lo, hi = min([0.25] + values) / 1.15, max([4.0] + values) * 1.15
    ticks = [t for t in (0.0625, 0.125, 0.25, 0.5, 0.67, 1, 1.5, 2, 4, 8, 16, 32) if lo <= t <= hi]
    if axis == "y":
        ax.set_ylim(lo, hi)
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"{t:g}×" for t in ticks])
        ax.yaxis.set_minor_formatter(NullFormatter())


def fold_error_by_age(rows, out, prov=None):
    """Each observation's fold error against its central postnatal age, by method."""
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    _style(ax)
    lo, hi = CONCORDANCE_BAND
    ax.axhspan(lo, hi, color="#eef4fc", zorder=0, label=f"Within {lo:g}–{hi:g}×")
    ax.axhline(1.0, color=INK2, linewidth=0.8)
    ax.axvline(730.5, color=INK2, linewidth=0.8, linestyle=":")
    shift = {"weight_linear": 0.94, "allometry": 1.0, "paedscale": 1.06}   # small offsets keep points apart
    fes = []
    for m, lab, col, mk in SHOWN:
        pts = [(max(r["pna_days"], 1.0) * shift[m], r["fe"]) for r in rows if r["method"] == m]
        fes += [y for _, y in pts]
        ax.scatter([x for x, _ in pts], [y for _, y in pts], s=20, marker=mk, color=col,
                   edgecolors="white", linewidths=0.6, label=lab, zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    _fold_ticks(ax, fes)
    ax.set_xticks([x for x, _ in AGE_TICKS])
    ax.set_xticklabels([t for _, t in AGE_TICKS])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Central postnatal age of the study group (log scale; dotted line at 2 years)", color=INK)
    ax.set_ylabel("Fold error (predicted ÷ observed clearance)", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    _save(fig, out, "fig4_external_fold_error_by_age", prov)


def paired_difference_forest(results, out, prov=None):
    """Per drug, under 2 years and at all ages: the ratio of typical fold errors, PaedScale ÷ allometry."""
    hyps = [("HE2_all_ages", "All ages", BLUE, "o"), ("HE1_under2", "Under 2 years", ORANGE, "^")]
    drugs = sorted(results["hypotheses"]["HE2_all_ages"]["per_drug_mean_d"])
    if not drugs:
        return
    fig, ax = plt.subplots(figsize=(6.4, 0.3 * len(drugs) + 1.8))
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#e6e6e6", linewidth=0.6)
    xs = []
    for j, (k, lab, col, mk) in enumerate(hyps):
        per = results["hypotheses"][k]["per_drug_mean_d"]
        pts = [(10 ** per[d], i + (0.15 if j else -0.15)) for i, d in enumerate(drugs) if d in per]
        xs += [x for x, _ in pts]
        ax.scatter([x for x, _ in pts], [y for _, y in pts], s=24, marker=mk, color=col,
                   edgecolors="white", linewidths=0.6, zorder=3, label=lab)
        h = results["hypotheses"][k]
        est, (lo, hi) = 10 ** h["mean_abs_log10_diff"], [10 ** v for v in h["ci95"]]
        y0 = -1.0 - 0.8 * j
        # Interval and estimate drawn separately: a BCa interval need not contain its estimate.
        ax.hlines(y0, lo, hi, color=col, linewidth=1.2)
        ax.vlines([lo, hi], y0 - 0.2, y0 + 0.2, color=col, linewidth=1.2)
        ax.scatter([est], [y0], marker="D", s=32, color=col, zorder=3)
        xs += [lo, hi, est]
    ax.axvline(1.0, color=INK2, linewidth=0.8)
    names = [d.replace("_", " ").replace("piperacillin tazobactam", "piperacillin") for d in drugs]
    ax.set_yticks([-1.8, -1.0] + list(range(len(drugs))))
    ax.set_yticklabels(["All drugs, under 2 y (95% CI)", "All drugs, all ages (95% CI)"] + names, fontsize=8)
    ax.set_xscale("log")
    ticks = [t for t in (0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3, 4) if min(xs) / 1.1 <= t <= max(xs) * 1.1]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks])
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Ratio of typical fold error, PaedScale ÷ allometry\n(<1 favours PaedScale)", color=INK)
    ax.set_ylim(-2.4, len(drugs))
    ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2, markerscale=1.4)
    _save(fig, out, "fig5_external_paired_difference_by_drug", prov)


def make_all(rows, results, out):
    os.makedirs(out, exist_ok=True)
    prov = results.get("provenance")
    fold_error_by_age(rows, out, prov)
    paired_difference_forest(results, out, prov)
