# Maturation curves added 2026-11-28

Eight TM50/Hill pairs added to `backend/engine/constants.py` (MATURATION), on top of the
three accepted in `maturation_validate.md` (Rhodin GFR, Anderson & Larsson midazolam CYP3A4,
Anand morphine UGT2B7). Each number below was read in the place named, not filled from
memory. Engine form: `MF = PMA^H / (TM50^H + PMA^H)`, PMA in weeks.

| key | kind | TM50 (wk PMA) | Hill | uncertainty used | source | where the numbers were read |
|---|---|---:|---:|---|---|---|
| `ugt1a_sult` | pathway (probe paracetamol) | 52.2 | 3.43 | 95% CI 49.8–54.1 / 3.19–3.96 (bootstrap) | Anderson & Holford, Drug Metab Pharmacokinet 2009;24:25-36, PMID 19252334 | Table 1, J-STAGE PDF |
| `cyp2d6` | pathway (probe tramadol) | 39.8 | 9 | none published | Allegaert et al., Clin Pharmacokinet 2015;54:167-178, PMID 25258277 | TM50: PubMed abstract. Hill: Healy et al., Br J Clin Pharmacol 2025;91:283-296 (PMID 39384340, PMC11773095) Table 2, footnote "Values were fixed using the estimates from Allegaert et al." |
| `gsta1` | pathway (probe busulfan) | 45.7 | 2.3 | Wald 95% CI from bootstrap RSE 4.3% / 9.7% | McCune et al., Clin Cancer Res 2014;20:754-763, PMID 24218510 | Table 2, PMC3946385 |
| `cyp1a2` | pathway (probe olanzapine) | 70 | 3.97 | bootstrap 2.5th–97.5th 52.5–317.3 / 2.08–7.08 | Maharaj et al., Br J Clin Pharmacol 2021;87:542-554, PMID 32497307 | Table 3, PMC9008710 |
| `renal_secretion` | pathway (probe hydrochlorothiazide) | 39.3 | 5.73 | bootstrap 95% CI 32.8–43.7 / 3.1–13.8 | Commander et al., J Clin Pharmacol 2021;61:368-377, PMID 33029806 | Table 2, PMC8232568 |
| `dexmedetomidine` | drug-specific | 52.4 | 1 (fixed) | TM50 95% CI 43.5–68.8; Hill none | Morse, Cortinez & Anderson, J Clin Med 2020;9:3480, PMID 33126702 | Table 1, PMC7692360 |
| `clindamycin` | drug-specific (CYP3A4 family) | 43.6 | 3.1 | bootstrap 2.5th–97.5th 36.1–83.0 / 1.2–5.1 | Gonzalez et al., Clin Pharmacol Ther 2014;96:429-437, PMID 24949994 | Table 2, PMC4169790 |
| `ibuprofen` | drug-specific | 36.8 | 11.5 | 95% CI 34.7–40.9 / 8.1–15 | Anderson & Hannam, Paediatr Anaesth 2019;29:1107-1113, PMID 31472084 | PubMed abstract |

## Decisions

- **Pathway vs drug-specific.** A pathway curve stands in for other substrates of its
  enzymes, and the engine adds a SURROGATE warning whenever the drug is not the probe. A
  drug-specific curve describes one drug whose clearance mixes enzymes (dexmedetomidine:
  CYP2A6 + UGT) or that is not a general isoform curve (ibuprofen, clindamycin). The engine
  raises if a drug-specific curve is used for another drug.
- **CYP3A substrates mature at different ages.** Midazolam TM50 73.6 weeks, clindamycin
  43.6 weeks. `cyp3a4` stays the midazolam curve; clindamycin gets its own curve.
- **`cyp2d6` is accepted with disclosure.** The 2026-08 validator held it back because the
  Allegaert primary full text was not opened. The TM50 is in the primary abstract; the Hill is
  printed in Healy 2025 (Allegaert a co-author), which fixed both values to the Allegaert
  estimates. No uncertainty exists in either source, so the uncertainty interval holds it at
  the point value and says so.
- **`ugt1a_sult` is not offered for UGT1A1.** The validator's warning stands: paracetamol is
  mostly UGT1A6/1A9 plus sulphation, so `curves_for_enzyme("UGT1A1")` returns nothing.
- **`cyp1a2` and `renal_secretion` come from oral CL/F.** Age changes in bioavailability are
  folded into the curve. The engine repeats this caveat as a warning when the curve is used.
- **`gsta1` interval is derived.** McCune printed bootstrap RSEs, not intervals; the 95% CI
  is point × (1 ± 1.96 × RSE), labelled as derived in `ci_basis`.
- **Different size models.** Busulfan used normal fat mass, dexmedetomidine fat-free mass; the
  engine scales by total body weight^0.75. Stated in each curve's caveats.

## Still no curve

No full text read here printed a TM50/Hill pair for a general **CYP2C9, CYP2C19, CYP2B6,
CYP2A6, CYP2E1, UGT1A1, CES1 or NAT2** curve. Sirolimus (CYP3A, Emoto 2016, PMC4999604:
62.9 weeks, Hill 2.94) was read but left out: oral CL/F dominated by intestinal CYP3A and
fitted with a 0.67 size exponent. Upreti & Wahlstrom 2016 and Farhan 2024 (in-vitro
abundance curves on postnatal age) remain unread behind paywalls.

## Benchmark

None of the new curves is a benchmark input. `benchmark/reference_set.json` still maps
drugs to `renal_gfr`, `cyp3a4` and `ugt2b7`, and Figure 1 draws only those three
(`benchmark/figures.PREREGISTERED_CURVES`). Benchmark and external-validation numbers do not
change.
