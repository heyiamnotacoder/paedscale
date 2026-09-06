"""Trial PBPK-translation facade: vancomycin IV starting regimen (testing only).

Whole-branch trial on `muse-spark-pbpk` (Q3/Q13): if axed, delete this file plus
the `pbpk` wiring and the tab — the allometry path is untouched.

What this is: a DETERMINISTIC, cited simplification of published vancomycin PBPK
knowledge into a starting regimen (dose + interval + infusion + first-TDM timing).
It is NOT PK-Sim/Simcyp execution — no compartmental ODEs run here. Every number
below names its source; anything without a source abstains instead of inventing.

Composite source of truth (Q10):
- OSP Vancomycin model table (PK-Sim, open): fu 0.67 (albumin), GFR fraction 1,
  i.e. elimination is filtration-driven with a small non-renal arm.
- Emoto et al., CPT PSP 2018 (PMCID:PMC5915605): developmental-renal description
  of vancomycin disposition in children.
- Cao et al., J Clin Pharmacol 2024 (doi:10.1002/jcph.6126): validated envelope
  PMA 25-45 wk in 230 neonates; PMA < 36 wk unsolved -> ABSTAIN here.
- Rybak et al. 2020 ASHP/IDSA/PIDS/SIDP guideline: AUC24 target 400-600
  mg*h/L, pediatric per-dose 15 mg/kg q6h at normal renal function, steady-state
  trough before the 4th dose as the first TDM checkpoint.

Trial simplifications, stated openly (NOT hidden):
- CL = fu (0.67, OSP) x absolute GFR + nonrenal 1.05 L/h/70kg allometrically
  scaled (Emoto Table 1); the OSP partition model itself is not executed.
  Nonrenal ontogeny (Emoto fast-ontogeny Age50 0.02 y) not modelled — stated
  assumption, envelope PMA >= 36 wk only.
- Vss = 0.37 L/kg (Emoto Table 1 predicted; observed 0.30-0.43).
- Interval snap is a trial heuristic (half-life-anchored II >= t1/2 onto the
  standard set), checkpoint-gated, grade deferred (Q12).
"""

from __future__ import annotations

import math
from typing import Any, Optional

from engine.pk_engine import estimate_gfr_bedside_schwartz

# --------------------------------------------------------------------------
# Cited constants (Q10/Q11/Q14). [INFERENCE] marks conventional bands, never
# paper-stated claims. Cao full text + Rybak full text inaccessible (paywalled);
# their quant gates are marked ABSTAINED, never reconstructed.
# --------------------------------------------------------------------------

DRUG = "vancomycin"
ROUTE = "iv"

AUC_TARGET_LO = 400.0  # mg*h/L — Rybak 2020 via Brunetti 2022 (R1)
AUC_TARGET_MID = 500.0  # regimen solved at band midpoint
AUC_TARGET_HI = 600.0  # mg*h/L — Rybak 2020 via Brunetti 2022 (R1)

PER_DOSE_MG_PER_KG = 15.0  # Emoto-cited regimens: 15 mg/kg IV over 1 h
FU_OSP = 0.67  # OSP table (albumin-only); Emoto serum fu 0.45 — free-AUC moves here (E8)
CL_NONRENAL_L_PER_H_70KG = 1.05  # Emoto Table 1 (total 6.78, renal 5.73, urine 84.6%)
VD_L_PER_KG = 0.37  # Emoto Table 1 predicted Vss (observed 0.30-0.43)

PMA_MIN_WEEKS = 36.0  # Cao 2024 abstract caveat (C2): PMA < 36 wk unsolved -> abstain
# Pediatric analogue of Emoto E3's adult CCr >= 15 mL/min: bedside-Schwartz
# INDEXED eGFR (mL/min/1.73 m²). Adult absolute CCr 15 applied to a neonate
# would empty the Cao PMA>=36 envelope (1.2 kg term abs GFR is ~2–3 mL/min).
EGFR_FLOOR = 15.0

MAX_INFUSION_RATE_MG_PER_HR = 1000.0  # standard rate cap (Rybak full text inaccessible — marked unverified)
MIN_INFUSION_MIN = 60.0  # Emoto-cited regimens run 15 mg/kg over 1 h

STANDARD_INTERVALS_H = (6, 8, 12, 24, 36, 48)  # renal-driven steps per Emoto Fig S1 design

TRIAL_BANNER = (
    "TRIAL PBPK-translation tab (branch muse-spark-pbpk): cited simplification of "
    "published vancomycin PBPK knowledge, NOT simulator execution. Starting-regimen "
    "decision support only — confirm with TDM. No A-D grade on this facade."
)

NON_RENAL_MINOR_FLAG = (
    "Nonrenal arm carried as 1.05 L/h/70kg scaled by (WT/70)^0.75 (Emoto Table 1); "
    "its ontogeny is not modelled — PMA >= 36 wk envelope only."
)
HEPATIC_CP_A_FLAG = (
    "Hepatic coverage is Child-Pugh A only (visual overlay, no numeric band); "
    "CP-B/C abstain. No auto dose reduction applied."
)
ICU_STARTING_POINT_FLAG = (
    "Critical-illness / ICU / sepsis physiology (altered cardiac output, volume of "
    "distribution) is outside this translation — starting point only, intensify TDM."
)

CITATIONS = [
    {
        "claim": "AUC24 target 400-600 mg*h/L; pediatric 15 mg/kg q6h starting "
        "regimen; first steady-state trough before the 4th dose",
        "source": "Rybak et al. 2020 ASHP/IDSA/PIDS/SIDP vancomycin guideline",
    },
    {
        "claim": "Vancomycin compound table: fu 0.67 (albumin), GFR fraction 1 "
        "(filtration-driven elimination)",
        "source": "OSP Vancomycin PBPK Model Library (open PK-Sim table)",
    },
    {
        "claim": "Developmental-renal description of vancomycin disposition in children",
        "source": "Emoto et al., CPT Pharmacometrics Syst Pharmacol 2018 (PMC5915605)",
    },
    {
        "claim": "Pediatric PBPK-vs-PopPK head-to-head in 230 neonates PMA 25-45 wk; "
        "PMA < 36 wk unsolved; PBPK suited to initial-dose optimisation",
        "source": "Cao et al., J Clin Pharmacol 2024 (doi:10.1002/jcph.6126)",
    },
]
# --------------------------------------------------------------------------
# Pinned validation checkpoints (Q14A). Paper-stated bands are quoted; 2-fold
# gates not stated in a paper are marked [INFERENCE] (conventional, not source
# claims). Paywalled/inaccessible quant is marked ABSTAINED, never reconstructed.
# Trial verdict: E4 is the only paper-explicit peds gate; O1/E1-E3/E5 are
# backbone-fidelity gates at the conventional 2-fold band; C1-quant abstained.
# --------------------------------------------------------------------------
CHECKPOINTS = [
    {"id": "O1", "source": "OSP eval report v2.0-OSP12.3 Table 3-1",
     "population": "Healthy adults, IV 500-1000 mg (Boeckh 1988 + Healy 1987)",
     "metric": "GMFE predicted vs observed = 1.11; trial gate GMFE <= 2.0 [INFERENCE]",
     "scope": "backbone fidelity; adult-only, zero pediatric license"},
    {"id": "E1", "source": "Emoto 2018 Fig 2a-g + Suppl Table S5",
     "population": "Healthy adults (Nakashima/Boeckh/Healy/Lodise arms)",
     "metric": "pred/obs Cmax,AUC 0.79-1.23 (means 0.96/1.08); trial gate 0.5-2.0x [INFERENCE]",
     "scope": "backbone fidelity"},
    {"id": "E2", "source": "Emoto 2018 Fig 3a-b (Takenaka 1993 Japanese arms)",
     "population": "Healthy Japanese adults",
     "metric": "pred/obs 0.62-0.94; trial gate 0.5-2.0x [INFERENCE]; documents lower-bound bias",
     "scope": "backbone fidelity; anti-cherry-picking"},
    {"id": "E3", "source": "Emoto 2018 Fig 3c-d (FDA renal bins)",
     "population": "CCr >= 30-<70 and >= 15-<30 mL/min",
     "metric": "pred/obs 0.73-1.36 (means 1.05/1.05); trial gate 0.5-2.0x [INFERENCE]",
     "scope": "renal envelope floor CCr >= 15; below abstains"},
    {"id": "E4", "source": "Emoto 2018 Fig 4g-h + Suppl Table S8",
     "population": "Japanese peds 1.0 y and 2.8 y, multiple dosing",
     "metric": "pred/obs Cmax AND AUC WITHIN TWOFOLD, paper-explicit (means 1.10/1.01)",
     "scope": "strongest falsifiable peds gate"},
    {"id": "E5", "source": "Emoto 2018 Fig 4a-f + Fig 5 (Schaad 1980 US peds 2.6 d-7.6 y)",
     "population": "US peds 2.6 days-7.6 y single dose",
     "metric": "pred/obs Cmax 0.85-1.69, AUC 0.54-1.52; trial gate 0.5-2.0x [INFERENCE]",
     "scope": "peds range; youngest is postnatal age, NOT PMA<36 wk validation"},
    {"id": "C1-quant", "source": "Cao 2024 full text (Wiley, paywalled — INACCESSIBLE)",
     "population": "230 neonates PMA 25-45 wk",
     "metric": "ABSTAINED — no numeric band set from the abstract; never reconstructed",
     "scope": "envelope reference only"},
    {"id": "C2", "source": "Cao 2024 abstract caveat, paper-explicit",
     "population": "Early neonates PMA < 36 wk",
     "metric": "OUT OF ENVELOPE — facade abstains; any PMA<36 number without flag = trial FAIL",
     "scope": "hard envelope rule"},
    {"id": "R1", "source": "Rybak 2020 via Brunetti 2022 (OUP full text 403 — via accessible paraphrase)",
     "population": "Adult serious-MRSA guideline scope",
     "metric": "TDM comparator is AUC24 400-600 (MIC 1 assumed); trough-only success claims = FAIL",
     "scope": "target definition; neonatal use is extrapolation, flagged"},
    {"id": "R2", "source": "Rybak 2020 via Brunetti 2022 Sec 4",
     "population": "Same",
     "metric": "Bayesian AUC from first interval allowed; trough/equation path needs steady state",
     "scope": "first-TDM timing rule"},
]


# Keys of the regimen block, shared by the success return, the abstain return and
# the submit-shaped `pbpk` object so the three cannot drift apart.
PBPK_DETAIL_KEYS = (
    "per_dose_mg", "per_dose_mg_per_kg", "interval_h", "doses_per_day",
    "daily_dose_mg", "daily_dose_mg_per_kg", "infusion_min", "auc_predicted",
    "auc_target", "first_tdm", "cl_l_per_h", "vd_l", "half_life_h",
    "egfr_indexed", "gfr_absolute_ml_min", "pma_weeks",
)


def _round_step_mg(dose_mg: float) -> float:
    """Rounding granularity, NTI-aware.

    A flat 10 mg step is ~28% of a neonatal vancomycin dose — far outside any
    therapeutic tolerance for an NTI drug. Step scales with the dose instead.
    """
    if dose_mg < 50.0:
        return 1.0
    if dose_mg < 250.0:
        return 5.0
    return 10.0


def _pma_or_abstain(case: dict) -> tuple[Optional[float], Optional[str]]:
    """Strict PMA for under-2s (Q11): supplied PMA wins, else GA+PNA, else ABSTAIN.

    The base engine assumes term here; this facade refuses to (NTI drug).
    Over-2s do not need PMA for a GFR-driven translation.
    """
    try:
        age = float(case.get("age_years"))
    except (TypeError, ValueError):
        return None, (
            "ABSTAIN — a numeric age in years is required on the PBPK trial facade "
            "(it selects the PMA rule). Missing age must not fall through to the "
            "neonatal branch for an NTI drug."
        )
    if age < 0:
        return None, "ABSTAIN — age in years must not be negative."
    if age >= 2.0:
        return None, None
    try:
        pma = case.get("pma_weeks")
        if pma not in (None, ""):
            return float(pma), None
        ga = case.get("gestational_age_weeks")
        pna = case.get("postnatal_age_weeks")
        if ga not in (None, "") and pna not in (None, ""):
            return float(ga) + float(pna), None
    except (TypeError, ValueError):
        return None, "ABSTAIN — PMA / gestational + postnatal age must be numeric."
    return None, (
        "ABSTAIN — PMA required for age < 2 yr on the PBPK trial facade "
        "(supply pma_weeks or gestational + postnatal age). No assumed-term fill-in "
        "for an NTI drug."
    )


def _absolute_gfr_ml_min(case: dict) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Bedside-Schwartz eGFR (indexed) -> absolute GFR via Mosteller BSA.

    SCr + height are REQUIRED inputs (Q11) — never defaulted.
    """
    scr = case.get("serum_creatinine_mg_dl")
    ht = case.get("height_cm")
    if scr in (None, "") or ht in (None, ""):
        return None, None, (
            "ABSTAIN — serum creatinine + height required on the PBPK trial facade "
            "(renal inputs drive a vancomycin dose; no defaulted-normal kidney)."
        )
    try:
        egfr = estimate_gfr_bedside_schwartz(float(ht), float(scr))
    except (TypeError, ValueError):
        egfr = None
    if egfr is None:
        return None, None, "ABSTAIN — eGFR not estimable from supplied SCr/height."
    wt = float(case.get("weight_kg") or 0.0)
    if wt <= 0:
        return None, None, "ABSTAIN — weight must be positive."
    bsa = math.sqrt(float(ht) * wt / 3600.0)  # Mosteller
    return egfr * bsa / 1.73, egfr, None


def _snap_interval(t_half_h: float, nominal_doses_per_day: int) -> int:
    """TRIAL heuristic: nominal interval from the AUC-matched daily dose, floored
    at the half-life onto the standard set (trough protection)."""
    nominal = 24.0 / max(1, nominal_doses_per_day)
    for ii in STANDARD_INTERVALS_H:
        if ii >= nominal and ii >= t_half_h:
            return ii
    return STANDARD_INTERVALS_H[-1]


def run_pbpk_vancomycin(case: dict) -> dict[str, Any]:
    """Deterministic vancomycin starting regimen. Pure compute, no I/O, no LLM."""
    flags: list[str] = [TRIAL_BANNER]
    assumptions: list[str] = [
        "CL = fu 0.67 (OSP) x absolute GFR + nonrenal 1.05 L/h/70kg scaled by "
        "(WT/70)^0.75 (Emoto Table 1) — cited simplification, not OSP/PK-Sim execution. "
        "Nonrenal ontogeny not modelled.",
        "Vss = 0.37 L/kg (Emoto Table 1 predicted; observed 0.30-0.43).",
        "Regimen solved at AUC24 band midpoint (500 mg*h/L); band 400-600 is an "
        "adult-serious-MRSA target applied by extrapolation (R1) — neonatal use flagged.",
        "fu pinned at 0.67 (OSP albumin-only); Emoto serum fu 0.45 — free-AUC/MIC "
        "moves with this choice (E8).",
        "Interval snap is a TRIAL heuristic (half-life-anchored onto renal-driven "
        "steps); checkpoint-gated, no grade.",
    ]
    drug = str(case.get("drug") or "").strip().lower()
    if drug != DRUG:
        return _abstain(
            f"ABSTAIN — trial facade bundles vancomycin only, not {case.get('drug')!r}.",
            flags, assumptions,
        )
    if str(case.get("route") or "iv").strip().lower() != ROUTE:
        return _abstain(
            "ABSTAIN — trial facade is IV vancomycin only (oral F not modelled).",
            flags, assumptions,
        )
    wt = case.get("weight_kg")
    try:
        wt = float(wt)
    except (TypeError, ValueError):
        return _abstain("ABSTAIN — weight must be positive.", flags, assumptions)
    if wt <= 0:
        return _abstain("ABSTAIN — weight must be positive.", flags, assumptions)

    # Allergy hard stop (same token-overlap contract as the product path).
    from engine.child_pugh import allergy_tokens_overlap

    hits = allergy_tokens_overlap(case.get("allergies"), "vancomycin")
    if hits:
        return _abstain(
            f"SAFETY STOP — allergy overlap with vancomycin ({', '.join(hits)}).",
            flags, assumptions,
        )

    pma, err = _pma_or_abstain(case)
    if err:
        return _abstain(err, flags, assumptions)
    if pma is not None and pma < PMA_MIN_WEEKS:
        return _abstain(
            f"ABSTAIN — PMA {pma:g} wk below the validated envelope "
            f"(Cao 2024: PMA < 36 wk unsolved).",
            flags, assumptions,
        )

    gfr_abs, egfr, err = _absolute_gfr_ml_min(case)
    if err:
        return _abstain(err, flags, assumptions)
    if gfr_abs is None or egfr is None:
        return _abstain(
            "ABSTAIN — renal inputs did not resolve to an eGFR.", flags, assumptions,
        )
    if egfr < EGFR_FLOOR:
        return _abstain(
            f"ABSTAIN — indexed eGFR {egfr:.0f} mL/min/1.73 m² below the "
            f"validated envelope (pediatric analogue of Emoto E3 adult CCr "
            f">= {EGFR_FLOOR:.0f} mL/min; absolute adult CCr is not applied "
            "to a child — that would empty the Cao PMA>=36 envelope).",
            flags, assumptions,
        )
    # Gate on the CLASS, not on a separate boolean: a case carrying child_pugh="C"
    # must abstain whether or not a `hepatic_impairment` flag rode along with it.
    cp = str(case.get("child_pugh") or "").strip().upper()
    if cp in ("B", "C"):
        return _abstain(
            "ABSTAIN — Child-Pugh B/C outside the validated envelope "
            "(hepatic coverage is CP-A only, visual overlay, no numeric band).",
            flags, assumptions,
        )
    if bool(case.get("hepatic_impairment")) and cp != "A":
        return _abstain(
            "ABSTAIN — hepatic impairment declared without a Child-Pugh class. "
            "Coverage is CP-A only, so the class cannot be assumed for an NTI drug.",
            flags, assumptions,
        )

    # --- core translation -------------------------------------------------
    gfr_l_per_h = gfr_abs * 60.0 / 1000.0
    cl_l_per_h = FU_OSP * gfr_l_per_h + CL_NONRENAL_L_PER_H_70KG * (wt / 70.0) ** 0.75
    vd_l = VD_L_PER_KG * wt
    t_half_h = math.log(2) * vd_l / cl_l_per_h if cl_l_per_h > 0 else float("inf")

    daily_dose_mg = cl_l_per_h * AUC_TARGET_MID  # AUC24 = 24-h dose / CL
    per_dose_nominal = PER_DOSE_MG_PER_KG * wt
    nominal_doses_per_day = max(1, min(4, round(daily_dose_mg / per_dose_nominal)))
    interval_h = _snap_interval(t_half_h, nominal_doses_per_day)
    # Re-solve per-dose FROM the snapped interval so AUC stays on target. q36h and
    # q48h do not divide the day, so the doses-per-day term must stay fractional:
    # round()ing it to 1 hands the whole 24-h dose out once per 36-48 h, i.e. a
    # 33-50% under-dose in exactly the renally-impaired band that snaps there —
    # and it would feed the same wrong number to the AUC check, disabling it.
    doses_per_day = 24.0 / interval_h
    per_dose_mg = daily_dose_mg / doses_per_day
    step_mg = _round_step_mg(per_dose_mg)
    per_dose_mg_rounded = round(per_dose_mg / step_mg) * step_mg  # vial-practical
    if per_dose_mg_rounded <= 0:
        return _abstain(
            f"ABSTAIN — solved per-dose {per_dose_mg:.2f} mg is below any deliverable "
            "vancomycin dose. No regimen is issued rather than rounding to zero.",
            flags, assumptions,
        )
    daily_equivalent_mg = per_dose_mg_rounded * doses_per_day
    auc_predicted = daily_equivalent_mg / cl_l_per_h if cl_l_per_h > 0 else float("nan")

    infusion_min = max(MIN_INFUSION_MIN, per_dose_mg_rounded / MAX_INFUSION_RATE_MG_PER_HR * 60.0)

    if interval_h > 24:
        flags.append(
            f"Extended interval q{interval_h}h — the mg/day figures below are 24-hour "
            f"EQUIVALENTS for AUC comparison, not an amount given every day. The order "
            f"is {per_dose_mg_rounded:g} mg once every {interval_h} h."
        )
    if not (AUC_TARGET_LO <= auc_predicted <= AUC_TARGET_HI):
        flags.append(
            "AUC discordance — rounded regimen predicts AUC24 "
            f"{auc_predicted:.0f} outside 400-600; pharmacist review before use."
        )
    flags.append(NON_RENAL_MINOR_FLAG)
    if cp == "A" or bool(case.get("hepatic_impairment")):
        flags.append(HEPATIC_CP_A_FLAG)
    # The tab's own indication placeholder is "e.g. MRSA sepsis", so the indication
    # is scanned alongside conditions — otherwise the obvious user path loses the flag.
    condition_text = " ".join(
        str(c) for c in [*(case.get("conditions") or []), case.get("indication") or ""]
    ).lower()
    if any(k in condition_text for k in ("sepsis", "septic", "icu", "critical", "shock")):
        flags.append(ICU_STARTING_POINT_FLAG)

    tdm_dose_number = 4
    tdm_timing = (
        f"Trough 30 min before dose #{tdm_dose_number} "
        f"(~{interval_h * (tdm_dose_number - 1):g} h after start); "
        "target AUC24 400-600 by trough/equation path at steady state — "
        "Bayesian AUC may be estimated from the first interval (R2). "
        "Neonatal AUC use is adult-target extrapolation (R1)."
    )

    return {
        "blocked": False,
        "block_reason": None,
        "drug": DRUG,
        "weight_kg": wt,
        "pma_weeks": pma,
        "egfr_indexed": round(egfr, 1),
        "gfr_absolute_ml_min": round(gfr_abs, 1),
        "cl_l_per_h": round(cl_l_per_h, 3),
        "vd_l": round(vd_l, 2),
        "half_life_h": round(t_half_h, 2) if math.isfinite(t_half_h) else None,
        "per_dose_mg": per_dose_mg_rounded,
        "per_dose_mg_per_kg": round(per_dose_mg_rounded / wt, 2),
        "interval_h": interval_h,
        "doses_per_day": round(doses_per_day, 2),
        # 24-h EQUIVALENT when the interval exceeds a day (flagged above).
        "daily_dose_mg": round(daily_equivalent_mg, 1),
        "daily_dose_mg_per_kg": round(daily_equivalent_mg / wt, 2),
        "infusion_min": round(infusion_min),
        "auc_predicted": round(auc_predicted, 0),
        "auc_target": [AUC_TARGET_LO, AUC_TARGET_HI],
        "first_tdm": tdm_timing,
        "grade": None,
        "flags": flags,
        "assumptions": assumptions,
        "citations": CITATIONS,
        "checkpoints": CHECKPOINTS,
    }


def _abstain(reason: str, flags: list[str], assumptions: list[str]) -> dict[str, Any]:
    return {
        **{k: None for k in PBPK_DETAIL_KEYS},
        "blocked": True,
        "block_reason": reason,
        "drug": DRUG,
        "auc_target": [AUC_TARGET_LO, AUC_TARGET_HI],
        "flags": [reason, *flags],
        "assumptions": assumptions,
        "citations": CITATIONS,
        "checkpoints": CHECKPOINTS,
    }


def recommendation_from_pbpk(case: dict, result: dict) -> dict[str, Any]:
    """Submit-shaped rec reusing the renderResult envelope. No A-D grade."""
    blocked = bool(result.get("blocked"))
    wt = case.get("weight_kg")
    try:
        wtf = float(wt)
    except (TypeError, ValueError):
        wtf = None
    rec: dict[str, Any] = {
        "final_dose_mg_per_day": None if blocked else result.get("daily_dose_mg"),
        "final_dose_mg_per_kg_per_day": None if blocked else result.get("daily_dose_mg_per_kg"),
        "grade": None,
        "grade_rationale": (
            "Trial PBPK-translation facade: no A-D grade (Q12 — grade deferred to "
            "post-trial). Confidence is provenance + checkpoints, not a letter."
        ),
        "blocked": blocked,
        "block_reason": result.get("block_reason"),
        "flags": list(result.get("flags") or []),
        "rationale": (
            f"GFR-proportional vancomycin translation: CL {result.get('cl_l_per_h')} L/h "
            f"(0.67 x absolute GFR {result.get('gfr_absolute_ml_min')} mL/min + nonrenal), "
            f"Vss {result.get('vd_l')} L, t1/2 {result.get('half_life_h')} h; "
            f"solved at AUC24 midpoint 500 (band 400-600, adult-target extrapolation). "
            f"First TDM: {result.get('first_tdm')}"
            if not blocked else (result.get("block_reason") or "Abstained.")
        ),
        "assumptions": list(result.get("assumptions") or []),
        "uncertainty": (
            "Cited simplification, not simulator execution; interval snap is a trial "
            "heuristic. Starting regimen only — TDM mandatory (NTI drug)."
        ),
        "citations": list(result.get("citations") or []),
        "pbpk_checkpoints": list(result.get("checkpoints") or []),
        "contraindications_avoid": [],
        "calculator_mode": "pbpk",
        "allometry_applied": False,
        "route": "iv",
        "interval": (
            f"every {result.get('interval_h')} hours"
            if not blocked and result.get("interval_h") else None
        ),
        "pbpk": {k: result.get(k) for k in PBPK_DETAIL_KEYS},
    }
    if wtf:
        rec["pbpk"]["weight_kg"] = wtf
    return rec


def run_pbpk_case(case: dict, on_step=None) -> dict[str, Any]:
    """Product path for the PBPK trial calculator: deterministic, no key, no A-D."""
    from engine.formulation import attach_administration

    trace: list[str] = ["pbpk facade — cited vancomycin translation, no allometry"]
    if on_step:
        on_step("→ pbpk_facade — cited vancomycin translation (trial, no grade)")
    result = run_pbpk_vancomycin(case)
    rec = recommendation_from_pbpk(case, result)
    attach_administration(rec, case)
    if on_step:
        on_step("→ pbpk done — starting regimen + first-TDM timing" if not result.get("blocked") else "→ pbpk abstained")
    trace.append("abstained" if result.get("blocked") else "regimen computed")
    return {
        "recommendation": rec,
        "trace": trace,
        "usage": {
            "retrieval_input_tokens": 0,
            "retrieval_output_tokens": 0,
            "orchestrator_input_tokens": 0,
            "orchestrator_output_tokens": 0,
            "retrieval_model": None,
            "model": "pbpk_facade",
            "source_mode": "bundled-cited-trial",
        },
    }
