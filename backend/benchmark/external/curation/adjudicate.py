"""External validation, step 3c: the final record from the two passes and the adjudication log
(PROTOCOL.md, Amendment 12 §9, Amendment 14).

    cd backend && python3 -m benchmark.external.curation.adjudicate     # -> extraction/final/

The final record follows the seeded order and stops where its own queue stops. An abstract
both passes decided the same way, with the same values, keeps that decision. Every other
abstract needs an entry in extraction/adjudication.json:

    {"<drug>": {"pediatric": {"<pmid>": {"use": "pass1" | "pass2", "reason": "..."}
                                       | {"record": {...study record...}, "reason": "..."}},
                "adult": {...}}}

An entry also overrides an agreed decision (for example to apply Amendment 14). This module
never imports the engine and computes no prediction.
"""
from __future__ import annotations

import json
import os
import sys

from benchmark.external.curation import screening
from benchmark.external.curation.agreement import items_key

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTRACTION = os.path.join(HERE, "extraction")
LOG = os.path.join(EXTRACTION, "adjudication.json")


def _choose(kind: str, pmid: str, a: dict | None, b: dict | None, entry: dict | None):
    """(study record or None, problem or None)."""
    if entry:
        if not str(entry.get("reason") or "").strip():
            return a or b, "log entry has no reason"
        if "record" in entry:
            rec = entry["record"]
            if not isinstance(rec, dict) or rec.get("pmid") != pmid:
                return a or b, f"log record is for PMID {rec.get('pmid') if isinstance(rec, dict) else None!r}"
            return rec, None
        src = a if entry.get("use") == "pass1" else b if entry.get("use") == "pass2" else None
        return (src, None) if src else (None, f"log entry uses {entry.get('use')!r}, which did not read it")
    if a and b:
        if a["decision"] != b["decision"]:
            return a, "decisions differ"
        if a["decision"] == "include" and items_key(a, kind) != items_key(b, kind):
            return a, "values differ"
        return a, None
    if a or b:
        return (a or b), f"read by {'pass1' if a else 'pass2'} only"
    return None, "read by neither pass"


def build(p1: dict, p2: dict, log: dict, ped_order: list[str], adult_order: list[str], stop):
    """The final record and the unresolved (kind, pmid, why) items. Past an unresolved item the
    record continues on a provisional choice (pass 1's where it has one), so every open question
    is listed in one run; the record is final only when nothing is unresolved."""
    rec = {"pediatric": [], "adult": []}
    unresolved = []
    for kind, order in (("pediatric", ped_order), ("adult", adult_order)):
        a = {s["pmid"]: s for s in p1.get(kind, [])}
        b = {s["pmid"]: s for s in p2.get(kind, [])}
        for pmid in order:
            if stop(rec, kind):
                break
            study, why = _choose(kind, pmid, a.get(pmid), b.get(pmid), (log.get(kind) or {}).get(pmid))
            if why:
                unresolved.append((kind, pmid, why))
            if study is None:
                break
            rec[kind].append(study)
    return rec, unresolved


def queue_stop(snap: dict):
    """Stop rule of the final record: the screening queue's own (screening.next_up)."""
    return lambda rec, kind: screening.next_up(snap, rec)[0] != kind


def write_final(passes: dict, snaps: dict, out_dir: str) -> list[str]:
    """Build every drug's final record from {drug: (pass1, pass2, log)} and {drug: snapshot}.
    The records are written to out_dir only when nothing is unresolved; returns the open items."""
    recs, open_items = {}, []
    for drug in sorted(passes):
        p1, p2, log = passes[drug]
        snap = snaps[drug]
        rec, unresolved = build(p1, p2, log, screening.order(snap["pediatric"]),
                                screening.order(snap["adult"]), queue_stop(snap))
        open_items += [f"{drug} {kind} {pmid}: {why}" for kind, pmid, why in unresolved]
        recs[drug] = rec
    if open_items:
        return open_items
    os.makedirs(out_dir, exist_ok=True)
    for drug, rec in recs.items():
        with open(os.path.join(out_dir, f"{drug}.json"), "w", encoding="utf-8") as f:
            json.dump({"drug": drug, "pass": "final", **rec}, f, indent=1)
    return []


def main() -> int:
    from benchmark.external.curation import check
    from benchmark.external.curation.search import SEARCH_DIR
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    d1, d2 = (sorted(os.listdir(os.path.join(EXTRACTION, p))) for p in ("pass1", "pass2"))
    if d1 != d2:
        print(f"the passes cover different drugs: {sorted(set(d1) ^ set(d2))}")
        return 1
    passes, snaps = {}, {}
    for fn in d1:
        drug = fn[:-5]
        p1, p2 = (json.load(open(os.path.join(EXTRACTION, p, fn), encoding="utf-8")) for p in ("pass1", "pass2"))
        passes[drug] = (p1, p2, log.get(drug, {}))
        snaps[drug] = json.load(open(os.path.join(SEARCH_DIR, fn), encoding="utf-8"))
    open_items = write_final(passes, snaps, os.path.join(EXTRACTION, "final"))
    for item in open_items:
        print(item)
    if open_items:
        print(f"{len(open_items)} unresolved; extraction/final/ was not written")
        return 1
    problems = [f"{d} {p}" for d in sorted(passes) for p in check.check_drug("final", d)]
    for p in problems:
        print(p)
    print("OK" if not problems else f"{len(problems)} check problem(s) in extraction/final/")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
