"""Run from the repo root: python3 -m pytest -q paper/test_build.py"""
import math

import pytest

from paper import build


def test_every_placeholder_is_filled_and_an_unknown_one_stops_the_build():
    assert build.render("AAFE {{a}} and {{b}}", {"a": "1.2", "b": "x"}) == "AAFE 1.2 and x"
    with pytest.raises(KeyError, match="missing"):
        build.render("{{missing}}", {})


def test_a_log10_difference_and_its_interval_read_as_a_ratio():
    # mean log10 difference log10(0.8); CI from log10(0.5) to 0 -> ratio 0.80 (0.50-1.00)
    h = {"mean_abs_log10_diff": math.log10(0.8), "ci95": [math.log10(0.5), 0.0]}
    assert build.ratio_with_ci(h) == "0.80 (95% CI 0.50–1.00)"


def test_an_interval_that_barely_crosses_one_is_not_rounded_onto_it():
    h = {"mean_abs_log10_diff": math.log10(0.91), "ci95": [math.log10(0.80), 0.00016]}
    assert build.ratio_with_ci(h) == "0.91 (95% CI 0.80–1.0004)"


def test_a_table_cell_gives_the_interval_without_repeating_its_name():
    h = {"mean_abs_log10_diff": math.log10(0.8), "ci95": [math.log10(0.5), 0.0]}
    assert build.ratio_with_ci(h, label=False) == "0.80 (0.50–1.00)"


def test_the_manuscript_fills_from_the_committed_benchmark_outputs():
    """Every placeholder in the manuscript has a value in the committed results."""
    import json
    import os
    with open(os.path.join(build.OUTPUT, "results.json")) as f:
        results = json.load(f)
    with open(os.path.join(build.BENCH, "reference_set.json")) as f:
        refset = json.load(f)
    with open(os.path.join(build.HERE, "manuscript.md")) as f:
        text = build.render(f.read(), build.values(results, refset))
    assert "{{" not in text and "0.77 (95% CI 0.58–0.96)" in text
