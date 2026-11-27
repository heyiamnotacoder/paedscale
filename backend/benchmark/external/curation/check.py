"""Validate a screening pass's records (SCREENING_GUIDE.md; PROTOCOL.md, Amendments 3-5).

Usage (from backend/): python3 -m benchmark.external.curation.check <pass> [<drug> ...]
Checks that decisions follow the seeded order with no gaps and stop where the queue stops, that
every abstract read still has the committed hash, and that every included study's observations
pass extraction.problems. Problems are reported, never raised.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

from benchmark.external.curation import extraction, screening
from benchmark.external.curation.search import ABSTRACT_DIR, SEARCH_DIR

EXTRACTION_DIR = os.path.join(os.path.dirname(SEARCH_DIR), "extraction")
ITEMS = {"pediatric": "observations", "adult": "values"}


def order_problems(screened: list[str], seeded: list[str]) -> list[str]:
    if screened != seeded[:len(screened)]:
        return [f"decisions {screened} are not the first {len(screened)} PMIDs of the seeded order"]
    return []


def stop_problems(record: dict, snap: dict) -> list[str]:
    """Screening ran no further than the queue (screening.next_up) would have shown."""
    out = []
    ped, adult = record["pediatric"], record["adult"]
    for j in range(len(ped)):
        if screening.next_up(snap, {"pediatric": ped[:j], "adult": []})[0] != "pediatric":
            out.append(f"pediatric {ped[j]['pmid']}: screened after every stratum was full")
            break
    if adult and screening.next_up(snap, {"pediatric": ped, "adult": []})[0] == "pediatric":
        out.append("adult screening began while a pediatric stratum was open and abstracts remained")
    for j in range(len(adult)):
        if not screening.adult_open(adult[:j]):
            out.append(f"adult {adult[j]['pmid']}: screened after five adult abstracts qualified")
            break
    return out


def study_problems(study: dict, abstract: str, kind: str) -> list[str]:
    pmid = study.get("pmid")
    decision = study.get("decision")
    if decision not in ("include", "exclude"):
        return [f"{pmid}: decision {decision!r} is not include or exclude"]
    out = []
    if decision == "exclude" and not study.get("reason"):
        out.append(f"{pmid}: an exclusion needs a reason")
    out += [f"{pmid}: study {p}" for p in extraction.flag_problems(study.get("flags") or [], kind)]
    items = study.get(ITEMS[kind]) or []
    if decision == "include" and not items:
        out.append(f"{pmid}: included with no {ITEMS[kind]}")
    for i, o in enumerate(items):
        check_one = extraction.adult_problems if kind == "adult" else extraction.problems
        found = check_one(o, abstract, study.get("flags") or [])
        out += [f"{pmid}[{i}]: {p}" for p in found]
    return out


def check_drug(pass_name: str, drug: str) -> list[str]:
    path = os.path.join(EXTRACTION_DIR, pass_name, f"{drug}.json")
    if not os.path.exists(path):
        return [f"no record file {path}"]
    with open(path, encoding="utf-8") as f:
        rec = json.load(f)
    with open(os.path.join(SEARCH_DIR, f"{drug}.json"), encoding="utf-8") as f:
        snap = json.load(f)
    hashes = {r["pmid"]: r["sha256"] for kind in ITEMS for r in snap[kind]}
    out = []
    for kind in ITEMS:
        rec.setdefault(kind, [])
        out += [f"{kind}: {p}" for p in order_problems([s.get("pmid") for s in rec[kind]],
                                                        screening.order(snap[kind]))]
        for s in rec[kind]:
            if s.get("pmid") not in hashes:
                out.append(f"{kind} {s.get('pmid')}: not in the search snapshot")
                continue
            with open(os.path.join(ABSTRACT_DIR, drug, f"{s['pmid']}.txt"), encoding="utf-8") as f:
                text = f.read()
            if hashlib.sha256(text.encode()).hexdigest() != hashes[s["pmid"]]:
                out.append(f"{kind} {s['pmid']}: abstract text differs from the committed hash")
            out += [f"{kind} {p}" for p in study_problems(s, text, kind)]
    if not out:                       # the queue replays only well-formed records
        out += stop_problems(rec, snap)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python3 -m benchmark.external.curation.check <pass> [<drug> ...]")
    pass_name = sys.argv[1]
    drugs = sys.argv[2:] or sorted(f[:-5] for f in os.listdir(SEARCH_DIR) if f.endswith(".json"))
    bad = 0
    for d in drugs:
        for p in check_drug(pass_name, d):
            print(d, p)
            bad += 1
    print("OK" if not bad else f"{bad} problem(s)")
    sys.exit(1 if bad else 0)
