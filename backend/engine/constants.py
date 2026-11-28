"""
PaedScale — pharmacometric constants (the deterministic engine's math backbone ONLY).

MATURATION holds published Anderson–Holford / Rhodin-style sigmoidal ontogeny
parameters (TM50 / Hill per elimination pathway). The engine refuses unknown pathways.

NO per-drug adult PK here — agent retrieves live or abstains.

All numbers for a standardised 70 kg adult reference. PMA in weeks.
"""

REFERENCE_WEIGHT_KG = 70.0
CL_EXPONENT = 0.75
VD_EXPONENT = 1.0
ADULT_PMA_WEEKS = 40.0 * 52.0  # ~40 years

# ---------------------------------------------------------------------------
# Maturation: MF(PMA) = PMA^H / (TM50^H + PMA^H), normalised so adult ≈ 1.
# Only TM50/Hill pairs that were read in the full text of the cited source.
# Do not invent new curves. Approximate / "Anderson–Holford style" rows
# were removed (cite-or-abstain).
#
# Per curve:
#   tm50_ci95 / hill_ci95  uncertainty printed in the same source (None when the source gives
#                          none, or the parameter was fixed). They feed the Monte Carlo
#                          interval in engine/uncertainty.py; a None is never filled in.
#   ci_basis               how that uncertainty was reported.
#   kind                   "pathway": a probe-drug curve used as the surrogate for other
#                          substrates of `enzymes` (the engine flags the surrogacy);
#                          "drug_specific": valid for `probe_drug` only (the engine refuses
#                          any other drug).
#   family                 the pathway this curve belongs to, for mechanism scoring.
#   caveats                study-design limits the engine repeats as a warning when the curve
#                          is used. Empty for the original three curves.
# ---------------------------------------------------------------------------
PATHWAY = "pathway"
DRUG_SPECIFIC = "drug_specific"

MATURATION = {
    "renal_gfr": {
        "tm50_weeks": 47.7,
        "hill": 3.40,
        "tm50_ci95": (45.1, 50.5),
        "hill_ci95": (3.03, 3.80),
        "ci_basis": "published 95% CI",
        "source": (
            "Rhodin MM et al., Pediatr Nephrol 2009;24:67-76. PMID 18846389. "
            "TM50 47.7 weeks PMA (95% CI 45.1–50.5), Hill 3.40 (95% CI 3.03–3.80)."
        ),
        "label": "Renal (glomerular filtration)",
        "kind": PATHWAY,
        "probe_drug": None,  # GFR markers, not a drug
        "enzymes": ["GFR"],
        "family": "renal_gfr",
        "caveats": "",
    },
    "cyp3a4": {
        "tm50_weeks": 73.6,
        "hill": 3.0,
        "tm50_ci95": (59.4, 80.0),
        "hill_ci95": (2.2, 4.1),
        "ci_basis": "published 95% CI",
        "source": (
            "Anderson BJ, Larsson P. Paediatr Anaesth 2011;21:302-308. PMID 20704661. "
            "Midazolam IV CL: TM50 73.6 weeks PMA (95% CI 59.4–80.0), Hill 3 (95% CI 2.2–4.1)."
        ),
        "label": "Hepatic CYP3A4",
        "kind": PATHWAY,
        "probe_drug": "midazolam",
        "enzymes": ["CYP3A4", "CYP3A5"],
        "family": "cyp3a4",
        "caveats": "",
    },
    "ugt2b7": {
        "tm50_weeks": 54.2,
        "hill": 3.92,
        "tm50_ci95": (50.3, 60.5),
        "hill_ci95": (3.25, 4.40),
        "ci_basis": "published 95% CI",
        "source": (
            "Anand KJS et al., Br J Anaesth 2008;101:680-689. PMID 18723857. "
            "Morphine (UGT2B7) CLmat50 54.2 weeks PMA (95% CI 50.3–60.5), Hill 3.92 (95% CI 3.25–4.40)."
        ),
        "label": "Hepatic UGT2B7 (glucuronidation)",
        "kind": PATHWAY,
        "probe_drug": "morphine",
        "enzymes": ["UGT2B7"],
        "family": "ugt2b7",
        "caveats": "",
    },
    "ugt1a_sult": {
        "tm50_weeks": 52.2,
        "hill": 3.43,
        "tm50_ci95": (49.8, 54.1),
        "hill_ci95": (3.19, 3.96),
        "ci_basis": "published 95% CI (1000-run non-parametric bootstrap)",
        "source": (
            "Anderson BJ, Holford NHG. Drug Metab Pharmacokinet 2009;24:25-36. PMID 19252334. "
            "Table 1, pooled paracetamol (n=509, 27 weeks PMA to 24 years; IV, oral, rectal): "
            "TM50 52.2 weeks PMA (95% CI 49.8–54.1), Hill 3.43 (95% CI 3.19–3.96)."
        ),
        "label": "Hepatic UGT1A glucuronidation + sulphation",
        "kind": PATHWAY,
        "probe_drug": "paracetamol",
        "enzymes": ["UGT1A6", "UGT1A9", "SULT1A1"],  # UGT1A1 minor: not offered as a surrogate
        "family": "ugt1a_sult",
        "caveats": (
            "Paracetamol clearance mixes UGT1A glucuronidation with sulphation, which is "
            "already active at birth; a pure-UGT1A substrate may mature later than this curve."
        ),
    },
    "cyp2d6": {
        "tm50_weeks": 39.8,
        "hill": 9.0,
        "tm50_ci95": None,
        "hill_ci95": None,
        "ci_basis": None,
        "source": (
            "Allegaert K et al., Clin Pharmacokinet 2015;54:167-178. PMID 25258277. Tramadol "
            "O-desmethyl (M1) formation clearance, CYP2D6 (n=295, 25 weeks PMA to 84.8 years): "
            "TM50 39.8 weeks PMA (abstract); Hill 9 as tabulated, fixed to the Allegaert "
            "estimates, in Healy P et al., Br J Clin Pharmacol 2025;91:283-296, Table 2. "
            "PMID 39384340. No uncertainty reported in either source."
        ),
        "label": "Hepatic CYP2D6 (O-demethylation)",
        "kind": PATHWAY,
        "probe_drug": "tramadol",
        "enzymes": ["CYP2D6"],
        "family": "cyp2d6",
        "caveats": (
            "CYP2D6 activity is genotype-driven (poor to ultrarapid metabolisers); this curve "
            "describes age only and no confidence interval was published for it."
        ),
    },
    "gsta1": {
        "tm50_weeks": 45.7,
        "hill": 2.3,
        # Wald interval from the published bootstrap RSE: point × (1 ± 1.96 × RSE).
        "tm50_ci95": (45.7 * (1 - 1.96 * 0.043), 45.7 * (1 + 1.96 * 0.043)),
        "hill_ci95": (2.3 * (1 - 1.96 * 0.097), 2.3 * (1 + 1.96 * 0.097)),
        "ci_basis": "Wald 95% CI derived from the published bootstrap RSE (4.3%, 9.7%)",
        "source": (
            "McCune JS et al., Clin Cancer Res 2014;20:754-763. PMID 24218510. IV busulfan "
            "(n=1610, 0.1–66 years), Table 2: TM50 45.7 weeks PMA (RSE 4.3%), Hill 2.3 (RSE 9.7%)."
        ),
        "label": "Hepatic glutathione S-transferase (GSTA1)",
        "kind": PATHWAY,
        "probe_drug": "busulfan",
        "enzymes": ["GSTA1"],
        "family": "gsta1",
        "caveats": (
            "Fitted with normal-fat-mass size scaling and an assumed 40-week gestation "
            "(PMA = postnatal age + 40 weeks); youngest patient 0.1 years, so preterm values "
            "are extrapolated."
        ),
    },
    "cyp1a2": {
        "tm50_weeks": 70.0,
        "hill": 3.97,
        "tm50_ci95": (52.5, 317.3),
        "hill_ci95": (2.08, 7.08),
        "ci_basis": "bootstrap 2.5th–97.5th percentiles",
        "source": (
            "Maharaj AR et al., Br J Clin Pharmacol 2021;87:542-554. PMID 32497307. Enteral "
            "olanzapine CL/F in children (0.2–19 years), Table 3: TM50 70 weeks PMA (bootstrap "
            "2.5th–97.5th 52.5–317.3), Hill 3.97 (2.08–7.08)."
        ),
        "label": "Hepatic CYP1A2 (+ UGT1A4), olanzapine probe",
        "kind": PATHWAY,
        "probe_drug": "olanzapine",
        "enzymes": ["CYP1A2"],  # UGT1A4 also clears olanzapine: see caveats
        "family": "cyp1a2",
        "caveats": (
            "Derived from apparent oral clearance (CL/F) of olanzapine, cleared by CYP1A2 and "
            "direct UGT1A4 glucuronidation; age changes in F are folded in and the TM50 "
            "upper bound is wide (317 weeks)."
        ),
    },
    "renal_secretion": {
        "tm50_weeks": 39.3,
        "hill": 5.73,
        "tm50_ci95": (32.8, 43.7),
        "hill_ci95": (3.1, 13.8),
        "ci_basis": "bootstrap 95% CI",
        "source": (
            "Commander SJ et al., J Clin Pharmacol 2021;61:368-377. PMID 33029806. Enteral "
            "hydrochlorothiazide CL/F (OAT1/OAT3 tubular secretion; n=49, 0.03–19.5 years), "
            "Table 2: TM50 39.3 weeks PMA (bootstrap 95% CI 32.8–43.7), Hill 5.73 (3.1–13.8)."
        ),
        "label": "Renal tubular secretion (OAT1/OAT3)",
        "kind": PATHWAY,
        "probe_drug": "hydrochlorothiazide",
        "enzymes": ["OAT1", "OAT3"],
        "family": "renal_secretion",
        "caveats": (
            "Derived from apparent oral clearance (CL/F) in 49 children; the authors call "
            "hydrochlorothiazide a potential surrogate for OAT1/OAT3 maturation, not a proven one."
        ),
    },
    "dexmedetomidine": {
        "tm50_weeks": 52.4,
        "hill": 1.0,
        "tm50_ci95": (43.5, 68.8),
        "hill_ci95": None,  # fixed to 1 in the final model
        "ci_basis": "bootstrap 95% CI for TM50; Hill fixed",
        "source": (
            "Morse JD, Cortinez LI, Anderson BJ. J Clin Med 2020;9:3480. PMID 33126702. IV "
            "dexmedetomidine (40.6 weeks PMA to 70.8 years), Table 1: TM50 52.4 weeks PMA "
            "(95% CI 43.5–68.8), Hill fixed to 1."
        ),
        "label": "Dexmedetomidine hepatic clearance (CYP2A6 + UGT)",
        "kind": DRUG_SPECIFIC,
        "probe_drug": "dexmedetomidine",
        "enzymes": ["CYP2A6", "UGT2B10", "UGT1A4"],
        "family": "dexmedetomidine",
        "caveats": "Fitted with fat-free-mass size scaling; Hill fixed to 1 (no Hill uncertainty).",
    },
    "clindamycin": {
        "tm50_weeks": 43.6,
        "hill": 3.1,
        "tm50_ci95": (36.1, 83.0),
        "hill_ci95": (1.2, 5.1),
        "ci_basis": "bootstrap 2.5th–97.5th percentiles",
        "source": (
            "Gonzalez D et al., Clin Pharmacol Ther 2014;96:429-437. PMID 24949994. IV "
            "clindamycin, premature infants to adolescents, Table 2: TM50 43.6 weeks PMA "
            "(bootstrap 2.5th–97.5th 36.1–83.0), Hill 3.1 (1.2–5.1)."
        ),
        "label": "Clindamycin hepatic clearance (CYP3A4)",
        "kind": DRUG_SPECIFIC,
        "probe_drug": "clindamycin",
        "enzymes": ["CYP3A4"],
        "family": "cyp3a4",
        "caveats": "",
    },
    "ibuprofen": {
        "tm50_weeks": 36.8,
        "hill": 11.5,
        "tm50_ci95": (34.7, 40.9),
        "hill_ci95": (8.1, 15.0),
        "ci_basis": "published 95% CI",
        "source": (
            "Anderson BJ, Hannam JA. Paediatr Anaesth 2019;29:1107-1113. PMID 31472084. "
            "Ibuprofen clearance, premature neonates to adults (abstract): TM50 36.8 weeks PMA "
            "(95% CI 34.7–40.9), Hill 11.5 (95% CI 8.1–15)."
        ),
        "label": "Ibuprofen hepatic clearance (CYP2C9/CYP2C8)",
        "kind": DRUG_SPECIFIC,
        "probe_drug": "ibuprofen",
        "enzymes": ["CYP2C9", "CYP2C8"],
        "family": "ibuprofen",
        "caveats": (
            "Fitted to clearance estimates pooled from 30 published studies, not to individual "
            "concentration data; it is not a general CYP2C9 curve."
        ),
    },
}
