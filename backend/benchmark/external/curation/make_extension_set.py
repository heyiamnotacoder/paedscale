"""Write extension/extension_set.json: the extension candidates of PROTOCOL.md Amendment 19 §2
and their engine inputs (§3), each with a verbatim quote from its FDA label snapshot.

    cd backend && python3 -m benchmark.external.curation.make_extension_set

fe follows the label benchmark's model-input rules (longest collection; a range at its
midpoint). The non-renal fraction goes to CYP3A4 only where the cited source names it as the
principal route; otherwise it stays unattributed. Written once, before any extension search.
"""
from __future__ import annotations

import json
import os

from benchmark.external.curation.trees import EXTENSION

CANDIDATES = ("cefazolin", "digoxin", "fentanyl", "alfentanil", "sufentanil", "ganciclovir",
              "cefotaxime", "levofloxacin", "milrinone", "ceftriaxone", "linezolid", "metronidazole")
TATEISHI = ("literature: CYP3A4 N-dealkylation of fentanyl and sufentanil (Tateishi et al., "
            "Anesth Analg 1996;82:167-72, PMID 8712396)")
LABROO = ("literature: fentanyl metabolism by hepatic CYP3A4 (Labroo et al., Drug Metab Dispos "
          "1997;25:1072-80, PMID 9311623)")


def inc(label, fe, quote, enzyme=None, evidence=None, flags=(), notes=""):
    return {"included": True, "label": label, "fe": {"value": fe, "quote": quote, "flags": list(flags)},
            "nonrenal_enzyme": enzyme, "enzyme_evidence": evidence, "notes": notes}


def exc(by, reason, label=None, quote=None):
    return {"included": False, "label": label, "excluded_by": by, "reason": reason, "quote": quote}


D = {
    "cefazolin": inc("labels/cefazolin.json", 0.75,
        "In the first 6 hours approximately 60% of the drug is excreted in the urine and this increases to 70% to 80% within 24 hours",
        notes="Label: 'excreted unchanged in the urine'. Longest collection (24 h), range midpoint."),
    "digoxin": inc("labels/digoxin.json", 0.60,
        "Following intravenous administration to healthy volunteers, 50-70% of a digoxin dose is excreted unchanged in the urine",
        notes="Non-renal fraction: label says metabolism is not CYP-dependent, so it stays unattributed."),
    "fentanyl": inc("labels/fentanyl.json", 0.05,
        "mostly as metabolites with less than 10% representing the unchanged drug",
        enzyme="cyp3a4", evidence=LABROO, flags=["fe_upper_bound"],
        notes="fe stated only as an upper bound (<10%); scored at the midpoint of [0, 10%]."),
    "alfentanil": exc("label", "No openFDA label has openfda.generic_name alfentanil with an intravenous route, so the selection rule returns no label and E3 cannot be assessed."),
    "sufentanil": inc("external/extension/labels/sufentanil.json", 0.02,
        "only 2% of the dose is eliminated as unchanged drug",
        enzyme="cyp3a4", evidence=TATEISHI),
    "ganciclovir": inc("external/extension/labels/ganciclovir.json", 0.913,
        "91.3 ± 5.0% (n = 4) of intravenously administered ganciclovir was recovered unmetabolized in the urine"),
    "cefotaxime": inc("external/extension/labels/cefotaxime.json", 0.28,
        "Approximately 20-36% of an intravenously administered dose of 14 C-cefotaxime is excreted by the kidney as unchanged cefotaxime",
        notes="Non-renal fraction (desacetylation) is not CYP3A4 or UGT2B7, so it stays unattributed."),
    "levofloxacin": inc("external/extension/labels/levofloxacin.json", 0.87,
        "approximately 87% of an administered dose was recovered as unchanged drug in urine within 48 hours",
        flags=["fe_after_oral"], notes="The label's only quantitative fe follows oral dosing."),
    "milrinone": inc("external/extension/labels/milrinone.json", 0.83,
        "The major urinary excretions of orally administered milrinone in man are milrinone (83%) and its 0-glucuronide metabolite (12%)",
        flags=["fe_after_oral"], notes="The label's only quantitative fe follows oral dosing."),
    "ceftriaxone": inc("external/extension/labels/ceftriaxone.json", 0.50,
        "Thirty-three percent to 67% of a ceftriaxone dose was excreted in the urine as unchanged drug and the remainder was secreted in the bile",
        notes="Non-renal fraction is biliary, not enzymatic, so it stays unattributed."),
    "linezolid": exc("E4", "The label states that clearance is nonlinear with dose.",
        label="external/extension/labels/linezolid.json",
        quote="A small degree of nonlinearity in clearance was observed with increasing doses of linezolid"),
    "metronidazole": inc("external/extension/labels/metronidazole.json", 0.14,
        "unchanged metronidazole accounting for approximately 20% of the total",
        flags=["fe_derived"],
        notes="Unchanged drug is about 20% of urinary recovery, which is 60 to 80% of the dose "
              "(quote_2): fe = 0.20 × 0.70. Oxidation and glucuronidation are not attributed to a curve."),
}
D["metronidazole"]["fe"]["quote_2"] = ("The major route of elimination of metronidazole and its metabolites is via "
                                       "the urine (60 to 80% of the dose)")

ABOUT = ("PaedScale external validation, extension set (PROTOCOL.md Amendment 19). Engine inputs from "
         "FDA label snapshots (paths relative to backend/benchmark/); every quote is checked by "
         "tests/test_external_extension.py. Harness only: never read by the product path.")


def main() -> None:
    assert set(D) == set(CANDIDATES)
    os.makedirs(os.path.dirname(EXTENSION.inputs), exist_ok=True)
    with open(EXTENSION.inputs, "w", encoding="utf-8") as f:
        json.dump({"_about": ABOUT, "drugs": {k: D[k] for k in CANDIDATES}}, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
