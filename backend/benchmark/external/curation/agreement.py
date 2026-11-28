"""External validation, step 3b: agreement between the two blinded passes (PROTOCOL.md,
Amendment 1 §9, Amendment 2 §8).

    cd backend && python3 -m benchmark.external.curation.agreement pass1 pass2

Inclusion agreement is Cohen's κ over the abstracts both passes read. For abstracts both
included, the extracted numbers are compared value by value. This module never imports the
engine and computes no prediction.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

KINDS = {"pediatric": "observations", "adult": "values"}
# The numbers a pass extracts from an observation or adult value (Amendment 1 §9).
PED_FIELDS = ("pna_days", "pna_range_days", "ga_weeks", "ga_range_weeks", "pma_weeks",
              "pma_range_weeks", "weight_kg", "bsa_m2", "height_cm", "preterm")
ADULT_FIELDS = ("weight_kg", "age_years")


def kappa(pairs: list[tuple[str, str]]) -> Optional[float]:
    """Cohen's κ for include/exclude pairs; None when undefined (no pairs, or chance agreement 1)."""
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    p1 = sum(a == "include" for a, _ in pairs) / n
    p2 = sum(b == "include" for _, b in pairs) / n
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    return None if pe >= 1 else (po - pe) / (1 - pe)


def _num(v):
    """30 and 30.0 are the same number; lists element-wise."""
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, list):
        return [_num(x) for x in v]
    return v


def _key(item: dict, fields: tuple[str, ...], study_flags=()) -> tuple:
    cl = item.get("cl") or {}
    flags = set(item.get("flags") or []) | set(study_flags)      # a study flag applies to each item
    return (_num(cl.get("value")), cl.get("unit"), cl.get("summary"),
            *(json.dumps(_num(item.get(f))) for f in fields), tuple(sorted(flags)))


def _items_key(study: dict, kind: str) -> tuple:
    fields = PED_FIELDS if kind == "pediatric" else ADULT_FIELDS
    sf = study.get("flags") or []
    return tuple(sorted(_key(i, fields, sf) for i in study.get(KINDS[kind]) or []))


def compare(r1: dict, r2: dict) -> dict:
    pairs, dec_dis, val_dis, only1, only2, val_ok = [], [], [], [], [], 0
    for kind in KINDS:
        a = {s["pmid"]: s for s in r1.get(kind, [])}
        b = {s["pmid"]: s for s in r2.get(kind, [])}
        only1 += [f"{kind} {p}" for p in a if p not in b]
        only2 += [f"{kind} {p}" for p in b if p not in a]
        for p in a:
            if p not in b:
                continue
            pairs.append((a[p]["decision"], b[p]["decision"]))
            if a[p]["decision"] != b[p]["decision"]:
                dec_dis.append(f"{kind} {p}")
            elif a[p]["decision"] == "include":
                if _items_key(a[p], kind) == _items_key(b[p], kind):
                    val_ok += 1
                else:
                    val_dis.append({"kind": kind, "pmid": p})
    return {"both_read": len(pairs), "pairs": pairs, "kappa": kappa(pairs),
            "decision_disagreements": dec_dis, "value_disagreements": val_dis,
            "value_agreements": val_ok, "only_pass1": only1, "only_pass2": only2}


def main(p1: str, p2: str) -> dict:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d1, d2 = (os.path.join(here, "extraction", p) for p in (p1, p2))
    per_drug, all_pairs = {}, []
    for fn in sorted(set(os.listdir(d1)) & set(os.listdir(d2))):
        if not fn.endswith(".json"):
            continue
        c = compare(json.load(open(os.path.join(d1, fn), encoding="utf-8")),
                    json.load(open(os.path.join(d2, fn), encoding="utf-8")))
        all_pairs += c.pop("pairs")
        per_drug[fn[:-5]] = c
    return {"kappa_overall": kappa(all_pairs), "both_read": len(all_pairs),
            "n_decision_disagreements": sum(len(c["decision_disagreements"]) for c in per_drug.values()),
            "n_value_disagreements": sum(len(c["value_disagreements"]) for c in per_drug.values()),
            "n_value_agreements": sum(c["value_agreements"] for c in per_drug.values()),
            "per_drug": per_drug}


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:3]), indent=1))
