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
