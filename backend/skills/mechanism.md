# Mechanism selection

Map drug → engine `fm` keys only when a maturation curve exists.

**Keys:** the curves listed in the `compute_pediatric_dose` tool description — each a TM50/Hill pair read in its cited source (see `engine/constants.py`).
- **Drug-specific key** (`clindamycin`, `dexmedetomidine`, `ibuprofen`): use it for that drug; the engine refuses it for any other drug.
- **Pathway key**: a probe-drug curve. For another substrate it is a surrogate; the engine flags this, so say it in the rationale.
- **No key for the enzyme** (CYP2C9, CYP2C19, CYP2B6, CYP2A6, UGT1A1, CES1, ...): never borrow a neighbouring isoform's curve; leave that fraction out (engine flags it) and grade down.

**Rules**
- `fm` fractions ≈ 1.0 for the cleared share; unmapped fraction → leave out (engine flags it).
- Empty lists for transporters/metabolites when none — never invent.
- **target_metric:** `auc` (vanco), `cmax` (aminoglycosides), `time_mic` (β-lactams), else `css`.
- Unknown pathway with no key → do not invent TM50; data-gap / grade C–D.
- **cmax AG:** engine may underdose vs pediatric practice → guideline-anchor + TDM flag.
- **time_mic:** daily dose is proxy only → frequent/extended dosing + grade ≤ B.
- **MM kinetics / null CL:** no linear invent → guideline or grade D.
