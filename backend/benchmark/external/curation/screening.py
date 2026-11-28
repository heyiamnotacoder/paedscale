"""External validation, step 2: the screening queue (PROTOCOL.md, Amendments 1-4).

Gives the seeded screening order of each drug's pre-filtered PMIDs and which strata, or the
adult list, are still open. The decisions themselves are made by reading abstracts and are
recorded in extraction/<pass>/<drug>.json; this module only applies the caps.
"""
from __future__ import annotations

import random

SEED = 20261127
STRATA = ("preterm_newborn", "term_newborn", "infant_toddler", "child", "adolescent")
STUDIES_PER_STRATUM = 2
ADULT_ABSTRACTS = 5


def order(rows: list[dict]) -> list[str]:
    pmids = sorted((r["pmid"] for r in rows if r["prefilter"]), key=int)
    random.Random(SEED).shuffle(pmids)
    return pmids


def adult_open(decisions: list[dict]) -> bool:
    return sum(d["decision"] == "include" for d in decisions) < ADULT_ABSTRACTS


def replay(record: dict) -> list[dict]:
    """The observations the analysis uses, in screening order: an included study adds its
    observations in strata that were still open when it was read (Amendment 1 §1)."""
    from benchmark.external.curation.extraction import central, gestational_weeks, stratum
    counts = {s: 0 for s in STRATA}
    used = []
    for study in record["pediatric"]:
        if study["decision"] != "include":
            continue
        open_now = {s for s, n in counts.items() if n < STUDIES_PER_STRATUM}
        contributed = set()
        for o in study.get("observations") or []:
            ga = gestational_weeks(o)
            pna = central(o.get("pna_days"), geometric=True)
            if pna is None and o.get("pma_weeks") is not None:   # PMA only: PNA from PMA − GA
                pna = max((central(o["pma_weeks"], False) - ga) * 7, 0)
            if pna is None:                       # no usable age: check.py reports it
                continue
            st = stratum(pna, ga)
            if st in open_now:
                used.append({"pmid": study["pmid"], "obs": o, "stratum": st})
                contributed.add(st)
        for s in contributed:
            counts[s] += 1
    return used


def full_strata(record: dict) -> set[str]:
    used = replay(record)
    return {s for s in STRATA if len({u["pmid"] for u in used if u["stratum"] == s}) >= STUDIES_PER_STRATUM}


def next_up(snap: dict, record: dict) -> tuple[str | None, list[str]]:
    """Which list to screen next and its unscreened PMIDs in seeded order: pediatric while a
    stratum is open and abstracts remain, then adult while fewer than five qualify and abstracts
    remain. (None, []) means screening for the drug is complete."""
    for kind, still_open in (("pediatric", len(full_strata(record)) < len(STRATA)),
                             ("adult", adult_open(record["adult"]))):
        done = {d["pmid"] for d in record[kind]}
        todo = [p for p in order(snap[kind]) if p not in done]
        if still_open and todo:
            return kind, todo
    return None, []


def snapshot_text(abstract_dir: str, drug: str, pmid: str, snap: dict) -> str:
    """The abstract text, only if it matches the committed snapshot hash (Literature search)."""
    import hashlib
    import os
    want = {r["pmid"]: r["sha256"] for kind in ("pediatric", "adult") for r in snap[kind]}
    with open(os.path.join(abstract_dir, drug, f"{pmid}.txt"), encoding="utf-8") as f:
        text = f.read()
    if hashlib.sha256(text.encode()).hexdigest() != want.get(pmid):
        raise SystemExit(f"abstract {pmid} differs from the snapshot: run search restore")
    return text


def _cli():
    """python3 -m benchmark.external.curation.screening next <pass> <drug> [n]
    Prints the next unscreened abstracts in the seeded order: pediatric while a stratum is open,
    then adult while fewer than five adult abstracts qualify."""
    import json
    import os
    import sys
    from benchmark.external.curation.trees import tree_of
    if len(sys.argv) < 4 or sys.argv[1] != "next":
        sys.exit("usage: python3 -m benchmark.external.curation.screening next <pass> <drug> [n]")
    _, cmd, pass_name, drug, *rest = sys.argv
    n = int(rest[0]) if rest else 3
    tree = tree_of(drug)                    # primary or extension (Amendment 19 §4)
    snap = json.load(open(os.path.join(tree.search, f"{drug}.json"), encoding="utf-8"))
    path = os.path.join(tree.extraction, pass_name, f"{drug}.json")
    rec = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {"drug": drug, "pediatric": [], "adult": []}
    kind, todo = next_up(snap, rec)
    print(f"{drug} [{pass_name}] full strata: {sorted(full_strata(rec)) or 'none'}; "
          f"adult qualifying: {sum(d['decision'] == 'include' for d in rec['adult'])}/{ADULT_ABSTRACTS}")
    if kind is None:
        print("NOTHING OPEN: screening for this drug is complete.")
        return
    print(f"-- {kind}: {len(todo)} unscreened of {len(order(snap[kind]))} pre-filtered")
    for p in todo[:n]:
        print(f"\n=== {kind} PMID {p} ===")
        print(snapshot_text(tree.abstracts, drug, p, snap))

if __name__ == "__main__":
    _cli()
