"""External validation, step 2: the screening queue (PROTOCOL.md, Amendments 1-2).

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


def open_strata(decisions: list[dict]) -> set[str]:
    counts = {s: 0 for s in STRATA}
    for d in decisions:
        if d["decision"] == "include":
            for s in set(d["strata"]):
                counts[s] += 1
    return {s for s, n in counts.items() if n < STUDIES_PER_STRATUM}


def adult_open(decisions: list[dict]) -> bool:
    return sum(d["decision"] == "include" for d in decisions) < ADULT_ABSTRACTS


def replay(record: dict) -> list[dict]:
    """The observations the analysis uses, in screening order: an included study adds its
    observations in strata that were still open when it was read (Amendment 1 §1)."""
    from benchmark.external.curation.extraction import central, stratum
    counts = {s: 0 for s in STRATA}
    used = []
    for study in record["pediatric"]:
        if study["decision"] != "include":
            continue
        open_now = {s for s, n in counts.items() if n < STUDIES_PER_STRATUM}
        contributed = set()
        for o in study["observations"]:
            pna = central(o.get("pna_days"), geometric=True)
            if pna is None:                       # PMA only: postnatal age from PMA − GA
                pna = max((central(o["pma_weeks"], False) - (central(o.get("ga_weeks"), False) or 40)) * 7, 0)
            st = stratum(pna, central(o.get("ga_weeks"), geometric=False))
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


def _cli():
    """python3 -m benchmark.external.curation.screening next <pass> <drug> [n]
    Prints the next unscreened abstracts in the seeded order: pediatric while a stratum is open,
    then adult while fewer than five adult abstracts qualify."""
    import json
    import os
    import sys
    from benchmark.external.curation.search import ABSTRACT_DIR, SEARCH_DIR
    _, cmd, pass_name, drug, *rest = sys.argv
    n = int(rest[0]) if rest else 3
    snap = json.load(open(os.path.join(SEARCH_DIR, f"{drug}.json"), encoding="utf-8"))
    path = os.path.join(os.path.dirname(SEARCH_DIR), "extraction", pass_name, f"{drug}.json")
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
        print(open(os.path.join(ABSTRACT_DIR, drug, f"{p}.txt"), encoding="utf-8").read())

if __name__ == "__main__":
    _cli()
