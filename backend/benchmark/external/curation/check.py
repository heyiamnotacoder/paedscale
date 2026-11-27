"""Validate a screening pass's records (SCREENING_GUIDE.md).

Usage (from backend/): python3 -m benchmark.external.curation.check <pass> [<drug>]
Checks that decisions follow the seeded order with no gaps, that every abstract read still has
the committed hash, and that every included study's observations pass extraction.problems.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

from benchmark.external.curation import extraction, screening
from benchmark.external.curation.search import ABSTRACT_DIR, SEARCH_DIR

EXTRACTION_DIR = os.path.join(os.path.dirname(SEARCH_DIR), "extraction")


def order_problems(screened: list[str], seeded: list[str]) -> list[str]:
    if screened != seeded[:len(screened)]:
        return [f"decisions {screened} are not the first {len(screened)} PMIDs of the seeded order"]
    return []


def study_problems(study: dict, abstract: str, kind: str) -> list[str]:
    out = []
    if study["decision"] not in ("include", "exclude"):
        out.append(f"{study['pmid']}: decision {study['decision']!r}")
    if study["decision"] == "exclude" and not study.get("reason"):
        out.append(f"{study['pmid']}: an exclusion needs a reason")
    items = study.get("observations" if kind == "pediatric" else "values") or []
    if study["decision"] == "include" and not items:
        out.append(f"{study['pmid']}: included with no {('observations' if kind == 'pediatric' else 'values')}")
    for i, o in enumerate(items):
        found = []
        if kind == "adult":
            # Adults need no age range, only the stated text or the adult_age_unstated flag.
            stated = o.get("age_quote") is not None
            if not stated and "adult_age_unstated" not in (o.get("flags") or []):
                found.append("no age quote and no adult_age_unstated flag")
            o = {**o, "pna_days": 0, "pma_weeks": None}
            found += [p for p in extraction.problems(o, abstract)
                      if stated or not p.startswith("age quote")]
        else:
            found = extraction.problems(o, abstract)
        out += [f"{study['pmid']}[{i}]: {p}" for p in found]
    return out


def check_drug(pass_name: str, drug: str) -> list[str]:
    path = os.path.join(EXTRACTION_DIR, pass_name, f"{drug}.json")
    if not os.path.exists(path):
        return []
    rec = json.load(open(path, encoding="utf-8"))
    snap = json.load(open(os.path.join(SEARCH_DIR, f"{drug}.json"), encoding="utf-8"))
    hashes = {r["pmid"]: r["sha256"] for kind in ("pediatric", "adult") for r in snap[kind]}
    out = []
    for kind in ("pediatric", "adult"):
        out += [f"{kind}: {p}" for p in order_problems([s["pmid"] for s in rec[kind]], screening.order(snap[kind]))]
        for s in rec[kind]:
            text = open(os.path.join(ABSTRACT_DIR, drug, f"{s['pmid']}.txt"), encoding="utf-8").read()
            if hashlib.sha256(text.encode()).hexdigest() != hashes.get(s["pmid"]):
                out.append(f"{kind} {s['pmid']}: abstract text differs from the committed hash")
            out += [f"{kind} {p}" for p in study_problems(s, text, kind)]
    return out


if __name__ == "__main__":
    pass_name = sys.argv[1]
    drugs = sys.argv[2:] or sorted(f[:-5] for f in os.listdir(SEARCH_DIR) if f.endswith(".json"))
    bad = 0
    for d in drugs:
        for p in check_drug(pass_name, d):
            print(d, p)
            bad += 1
    print("OK" if not bad else f"{bad} problem(s)")
    sys.exit(1 if bad else 0)
