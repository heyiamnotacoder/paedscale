"""Masked tally of the clearance-unit forms the pre-filter matches (Amendment 4 §1, Amendment 5 §5).

Usage (from backend/): python3 -m benchmark.external.curation.unit_tally
Writes benchmark/external/unit_tally.json: each matched form with every number replaced
by '#' and bracketed text emptied, and how often it occurs across all pre-filtered abstracts.
No other abstract text is shown, so the tally reveals units, not results.
"""
from __future__ import annotations

import collections
import json
import os
import re

from benchmark.external.curation.prefilter import CLEARANCE_VALUE
from benchmark.external.curation.search import ABSTRACT_DIR, SEARCH_DIR

OUT = os.path.join(os.path.dirname(SEARCH_DIR), "unit_tally.json")


def masked_forms(text: str) -> list[str]:
    forms = []
    for m in CLEARANCE_VALUE.finditer(re.sub(r"\s+", " ", text or "")):
        u = re.sub(r"\d+(?:[.,]\d+)?", "#", m.group(0)).lower()
        forms.append((re.sub(r"\(.*?\)", "()", u) if u.startswith("#") else u).strip())
    return forms


def tally() -> dict[str, int]:
    c = collections.Counter()
    for f in sorted(os.listdir(SEARCH_DIR)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(SEARCH_DIR, f), encoding="utf-8") as fh:
            snap = json.load(fh)
        for kind in ("pediatric", "adult"):
            for r in snap[kind]:
                if r["prefilter"]:
                    with open(os.path.join(ABSTRACT_DIR, snap["drug"], f"{r['pmid']}.txt"), encoding="utf-8") as fh:
                        c.update(masked_forms(fh.read()))
    return dict(c.most_common())


if __name__ == "__main__":
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(tally(), f, indent=1, ensure_ascii=False)
    print(OUT)
