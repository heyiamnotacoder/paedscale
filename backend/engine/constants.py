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
# Only pathways with published TM50/Hill that were opened and quoted.
# Do not invent new curves. Approximate / "Anderson–Holford style" rows
# were removed (cite-or-abstain).
# tm50_ci95 / hill_ci95 are the 95% CIs printed in the same source; they feed the
# Monte Carlo parameter-uncertainty interval in engine/uncertainty.py (never invented).
# ---------------------------------------------------------------------------
MATURATION = {
    "renal_gfr": {
        "tm50_weeks": 47.7,
        "hill": 3.40,
        "tm50_ci95": (45.1, 50.5),
        "hill_ci95": (3.03, 3.80),
        "citation": "Rhodin 2009",  # short form of source, for display
        "source": (
            "Rhodin MM et al., Pediatr Nephrol 2009;24:67-76. PMID 18846389. "
            "TM50 47.7 weeks PMA (95% CI 45.1–50.5), Hill 3.40 (95% CI 3.03–3.80)."
        ),
        "label": "Renal (glomerular filtration)",
    },
    "cyp3a4": {
        "tm50_weeks": 73.6,
        "hill": 3.0,
        "tm50_ci95": (59.4, 80.0),
        "hill_ci95": (2.2, 4.1),
        "citation": "Anderson & Larsson 2011",  # short form of source, for display
        "source": (
            "Anderson BJ, Larsson P. Paediatr Anaesth 2011;21:302-308. PMID 20704661. "
            "Midazolam IV CL: TM50 73.6 weeks PMA (95% CI 59.4–80.0), Hill 3 (95% CI 2.2–4.1)."
        ),
        "label": "Hepatic CYP3A4",
    },
    "ugt2b7": {
        "tm50_weeks": 54.2,
        "hill": 3.92,
        "tm50_ci95": (50.3, 60.5),
        "hill_ci95": (3.25, 4.40),
        "citation": "Anand 2008",  # short form of source, for display
        "source": (
            "Anand KJS et al., Br J Anaesth 2008;101:680-689. PMID 18723857. "
            "Morphine (UGT2B7) CLmat50 54.2 weeks PMA (95% CI 50.3–60.5), Hill 3.92 (95% CI 3.25–4.40)."
        ),
        "label": "Hepatic UGT2B7 (glucuronidation)",
    },
}
