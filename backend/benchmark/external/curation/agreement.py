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
    """Everything a pass extracted for one item, as strings so that items always sort."""
    cl = item.get("cl") or {}
    flags = set(item.get("flags") or []) | set(study_flags)      # a study flag applies to each item
    return tuple(json.dumps(x) for x in (_num(cl.get("value")), cl.get("unit"), cl.get("summary"),
                                         *(_num(item.get(f)) for f in fields), sorted(flags)))


def _sorted_items(study: dict, kind: str) -> list[dict]:
    fields = PED_FIELDS if kind == "pediatric" else ADULT_FIELDS
    sf = study.get("flags") or []
    return sorted(study.get(KINDS[kind]) or [], key=lambda i: _key(i, fields, sf))


def items_key(study: dict, kind: str) -> tuple:
    """Two passes extracted the same items when these keys are equal (order does not matter)."""
    fields = PED_FIELDS if kind == "pediatric" else ADULT_FIELDS
    sf = study.get("flags") or []
    return tuple(_key(i, fields, sf) for i in _sorted_items(study, kind))


NUMERIC = ("pna_days", "pna_range_days", "ga_weeks", "ga_range_weeks", "pma_weeks", "pma_range_weeks",
           "weight_kg", "bsa_m2", "height_cm", "age_years")


def _value_counts(a: dict, b: dict, kind: str) -> tuple[int, int]:
    """Numbers compared one by one (Amendment 1 §9): when both passes recorded the same number
    of items, they are paired in the sorted order of items_key; each clearance (value with its
    unit) and each number either pass recorded counts once."""
    ia, ib = _sorted_items(a, kind), _sorted_items(b, kind)
    if len(ia) != len(ib):
        return 0, 0
    compared = differ = 0
    for x, y in zip(ia, ib):
        cx, cy = x.get("cl") or {}, y.get("cl") or {}
        pairs = [((_num(cx.get("value")), cx.get("unit")), (_num(cy.get("value")), cy.get("unit")))]
        pairs += [(_num(x.get(f)), _num(y.get(f))) for f in NUMERIC if x.get(f) is not None or y.get(f) is not None]
        compared += len(pairs)
        differ += sum(p != q for p, q in pairs)
    return compared, differ


def compare(r1: dict, r2: dict) -> dict:
    pairs, dec_dis, val_dis, only1, only2, val_ok = [], [], [], [], [], 0
    n_cmp = n_diff = 0
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
                c, d = _value_counts(a[p], b[p], kind)
                n_cmp, n_diff = n_cmp + c, n_diff + d
                if items_key(a[p], kind) == items_key(b[p], kind):
                    val_ok += 1
                else:
                    val_dis.append({"kind": kind, "pmid": p})
    return {"both_read": len(pairs), "pairs": pairs, "kappa": kappa(pairs),
            "decision_disagreements": dec_dis, "value_disagreements": val_dis,
            "value_agreements": val_ok, "values_compared": n_cmp, "values_differ": n_diff,
            "only_pass1": only1, "only_pass2": only2}


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
            "n_values_compared": sum(c["values_compared"] for c in per_drug.values()),
            "n_values_differ": sum(c["values_differ"] for c in per_drug.values()),
            "drugs_missing_a_pass": sorted(set(os.listdir(d1)) ^ set(os.listdir(d2))),
            "per_drug": per_drug}


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:3]), indent=1))
