"""Curator script: writes backend/benchmark/reference_set.json. Every number has a verbatim quote."""
import json
import os
HERE = os.path.dirname(os.path.abspath(__file__))
M = 30.4375          # days per month
Y = 365.25           # days per year
OPEN_UPPER = 16 * Y  # protocol: open upper bound = 16 years

def band(id, label, pna, dose, rng=None, quote="", ga=None, flags=()):
    return {"id": id, "label": label, "pna_days": [round(pna[0], 2), round(pna[1], 2)],
            "ga_weeks": ga, "ref_per_kg_daily": dose, "range_per_kg_daily": rng or [dose, dose],
            "quote": quote, "flags": list(flags)}

def drug(label, cls, metric, fe, fe_quote, adult, adult_rng, adult_ind, adult_quote, bands,
         enzyme=None, enzyme_evidence=None, fe_flags=(), unit="mg", notes="", adult_flags=()):
    return {"included": True, "label": label, "class": cls, "target_metric": metric,
            "unit": unit,
            "fe": {"value": fe, "quote": fe_quote, "flags": list(fe_flags)},
            "nonrenal_enzyme": enzyme, "enzyme_evidence": enzyme_evidence,
            "adult": {"indication": adult_ind, "daily": adult, "range_daily": adult_rng,
                      "quote": adult_quote, "flags": list(adult_flags)},
            "bands": bands, "notes": notes}

D = {}
D["vancomycin"] = drug("vancomycin.json", "glycopeptide", "css",
    0.75, "In the first 24 hours, about 75% of an administered dose of vancomycin is excreted in urine by glomerular filtration.",
    2000, [2000, 2000], "usual adult IV dose (normal renal function)",
    "The usual daily intravenous dose is 2 g divided either as 500 mg every 6 hours or 1 g every 12 hours.",
    [band("child", "Pediatric patients (>1 month)", [M, OPEN_UPPER], 40,
          quote="The usual intravenous dosage of vancomycin is 10 mg/kg per dose given every 6 hours."),
     band("neo_wk1", "Neonates, 1st week of life", [0, 7], 20,
          quote="followed by 10 mg/kg every 12 hours for neonates in the 1st week of life and every 8 hours thereafter up to the age of 1 month"),
     band("neo_wk1_4", "Neonates, 1 week to 1 month", [7, M], 30,
          quote="followed by 10 mg/kg every 12 hours for neonates in the 1st week of life and every 8 hours thereafter up to the age of 1 month")])

D["gentamicin"] = drug("gentamicin.json", "aminoglycoside", "cmax",
    0.70, "ally 70% or more of the gentamicin dose is recoverable in the urine in 24 hours",
    280, [210, 350], "serious to life-threatening infections (union of tiers 3–5 mg/kg/day × 70 kg)",
    "The recommended dosage of gentamicin injection for patients with serious infections and normal renal function is 3 mg/kg/day, administered in three equal doses every eight hours ( Table 3 ). For patients with life-threatening infections, dosages up to 5 mg/kg/day may be ad",
    [band("child", "Children (1–16 y)", [Y, OPEN_UPPER], 6.75, [6, 7.5],
          quote="Children 6 to 7.5 mg/kg/day (2 to 2.5 mg/kg administered every eight hours)."),
     band("infant", "Infants and neonates (>1 week to <1 y)", [7, Y], 7.5,
          quote="Infants and Neonates 7.5 mg/kg/day (2.5 mg/kg administered every eight hours)."),
     band("neo_wk1", "Premature or full-term neonates ≤1 week", [0, 7], 5,
          quote="Premature or Full-Term Neonates One Week of Age or Less 5 mg/kg/day (2.5 mg/kg administered every 12 hours).")])

D["tobramycin"] = drug("tobramycin.json", "aminoglycoside", "cmax",
    0.93, "up to 84% of the dose is recoverable from the urine in 8 hours and up to 93% in 24 hours",
    280, [210, 350], "serious to life-threatening infections (union of tiers 3–5 mg/kg/day × 70 kg)",
    "Adults with Serious Infections: 3 mg/kg/day in 3 equal doses every 8 hours (see Table 1). Adults with Life-Threatening Infections: Up to 5 mg/kg/day may be administered",
    [band("child", "Pediatric patients >1 week of age", [7, OPEN_UPPER], 6.75, [6, 7.5],
          quote="Pediatric Patients (Greater Than 1 Week of Age): 6 to 7.5 mg/kg/day in 3 or 4 equally divided doses"),
     band("neo_wk1", "Premature or full-term neonates ≤1 week", [0, 7], 4, [0, 4],
          quote="Premature or Full-Term Neonates 1 Week of Age or Less: Up to 4 mg/kg/day", flags=["up_to", "mgkg_shared"])])

D["amikacin"] = drug("amikacin.json", "aminoglycoside", "cmax",
    0.94, "about 94% within 24 hours",
    1050, [1050, 1050], "normal renal function (15 mg/kg/day × 70 kg)",
    "The recommended dosage for adults, children and older infants (see WARNINGS box) with normal renal function is 15 mg/kg/day",
    [band("child", "Children and older infants (1 month–16 y)", [M, OPEN_UPPER], 15,
          quote="The recommended dosage for adults, children and older infants (see WARNINGS box) with normal renal function is 15 mg/kg/day",
          flags=["mgkg_shared"]),
     band("neo", "Newborns (0–28 days)", [0, 28], 15,
          quote="it is recommended that a loading dose of 10 mg/kg be administered initially to be followed with 7.5 mg/kg every 12 hours",
          flags=["mgkg_shared"])])

D["ampicillin"] = drug("ampicillin.json", "beta-lactam", "time_mic",
    0.90, "Ampicillin is excreted largely unchanged in the urine",
    12250, [10500, 14000], "septicemia (150–200 mg/kg/day × 70 kg)",
    "Septicemia Adults and children: 150 to 200 mg/kg/day.",
    [band("child", "Children (>28 days)", [28, OPEN_UPPER], 175, [150, 200],
          quote="Septicemia Adults and children: 150 to 200 mg/kg/day.", flags=["mgkg_shared"]),
     band("neo_term", "Neonates GA >34 wk, PNA ≤28 days", [0, 28], 150, ga=37,
          quote="greater than 34 less than or equal to 28 150 mg/kg/day in equally divided doses every 8 hours"),
     band("neo_pre_wk1", "Neonates GA ≤34 wk, PNA ≤7 days", [0, 7], 100, ga=32,
          quote="less than or equal to 34 less than or equal to 7 100 mg/kg/day in equally divided doses every 12 hours"),
     band("neo_pre_wk1_4", "Neonates GA ≤34 wk, PNA 8–<28 days", [8, 28], 150, ga=32,
          quote="less than or equal to 34 greater than or equal to 8 and less than 28 150 mg/kg/day in equally divided doses every 12 hours")],
    fe_flags=["fe_qualitative"])

D["ceftazidime"] = drug("ceftazidime.json", "beta-lactam", "time_mic",
    0.85, "Approximately 80% to 90% of an IM or IV dose of ceftazidime is excreted unchanged by the kidneys over a 24-hour period.",
    2500, [2000, 3000], "usual recommended adult dosage (1 g q8–12h)",
    "Usual recommended dosage 1 gram intravenous or intramuscular every 8 to 12 hours",
    [band("child", "Infants and children (1 month–12 y)", [M, 12 * Y], 90, [90, 150],
          quote="Infants and children (1 month to 12 years) 30 to 50 mg/kg intravenous to a maximum of 6 grams per day** every 8 hours"),
     band("neo", "Neonates (0–4 weeks)", [0, 28], 60,
          quote="Neonates (0 to 4 weeks) 30 mg/kg intravenous every 12 hours")],
    notes="Child scored at the usual 30 mg/kg q8h to match the adult 'usual' regimen; label: the higher dose should be reserved for immunocompromised pediatric patients or pediatric patients with cystic fibrosis or meningitis.")

D["cefepime"] = drug("cefepime.json", "beta-lactam", "time_mic",
    0.85, "Urinary recovery of unchanged cefepime accounts for approximately 85% of the administered dose.",
    6000, [6000, 6000], "empiric therapy for febrile neutropenia (most severe indication with a pediatric row)",
    "Empiric therapy for febrile neutropenic patients 2 g IV Every 8 hours",
    [band("child", "Pediatric patients 2 months–16 y (febrile neutropenia)", [2 * M, OPEN_UPPER], 150,
          quote="50 mg per kg per dose, every 8 hours for febrile neutropenic patients.")])

D["meropenem"] = drug("meropenem.json", "beta-lactam", "time_mic",
    0.625, "Approximately 70% (50% - 75%) of the dose is excreted unchanged within 12 hours.",
    3000, [3000, 3000], "complicated intra-abdominal infection (1 g q8h)",
    "1 gram every 8 hours by intravenous infusion over 15 minutes to 30 minutes for intra-abdominal infections for adult patients.",
    [band("child", "Pediatric patients ≥3 months (intra-abdominal)", [3 * M, OPEN_UPPER], 60,
          quote="Intra-abdominal 20 1 gram Every 8 hours"),
     band("neo_lt32_lt2w", "GA <32 wk, PNA <2 weeks", [0, 14], 40, ga=30,
          quote="Infants less than 32 weeks GA and PNA less than 2 weeks 20 Every 12 hours"),
     band("neo_lt32_ge2w", "GA <32 wk, PNA ≥2 weeks (to 3 months)", [14, 3 * M], 60, ga=30,
          quote="Infants less than 32 weeks GA and PNA 2 weeks and older 20 Every 8 hours"),
     band("neo_ge32_lt2w", "GA ≥32 wk, PNA <2 weeks", [0, 14], 60, ga=36,
          quote="Infants 32 weeks and older GA and PNA less than 2 weeks 20 Every 8 hours"),
     band("neo_ge32_ge2w", "GA ≥32 wk, PNA ≥2 weeks (to 3 months)", [14, 3 * M], 90, ga=36,
          quote="Infants 32 weeks and older GA and PNA 2 weeks and older 30 Every 8 hours")])

D["piperacillin_tazobactam"] = drug("piperacillin_and_tazobactam.json", "beta-lactam", "time_mic",
    0.68, "Piperacillin is excreted rapidly as unchanged drug with 68% of the administered dose excreted in the urine.",
    16000, [16000, 16000], "nosocomial pneumonia (piperacillin component; most severe indication with pediatric rows)",
    "should start with piperacillin and tazobactam for injection at a dosage of 4.5 g every six hours plus an aminoglycoside, [totaling 18 g (16 g piperacillin and 2 g tazobactam)]",
    [band("infant", "2–9 months (nosocomial pneumonia)", [2 * M, 9 * M], 320,
          quote="90 mg/kg (80 mg piperacillin and 10 mg tazobactam) every 6 ( six ) hours"),
     band("child", ">9 months (nosocomial pneumonia)", [9 * M, OPEN_UPPER], 400,
          quote="112.5 mg/kg (100 mg piperacillin and 12.5 mg tazobactam) every 6 ( six) hours")],
    notes="Doses scored as the piperacillin component. The label's 40 kg weight cap is not applied (Amendment 1 §15).")

D["acyclovir"] = drug("acyclovir.json", "antiviral", "css",
    0.765, "Renal excretion of unchanged drug is the major route of acyclovir elimination accounting for 62% to 91% of the dose.",
    2100, [2100, 2100], "herpes simplex encephalitis (10 mg/kg q8h × 70 kg)",
    "HERPES SIMPLEX ENCEPHALITIS Adults and Adolescents (12 years of age and older) 10 mg/kg infused at a constant rate over 1 hour, every 8 hours for 10 days.",
    [band("child", "Pediatrics 3 months–12 y (HSV encephalitis)", [3 * M, 12 * Y], 60,
          quote="Pediatrics (3 months to 12 years of age) 20 mg/kg infused at a constant rate over 1 hour, every 8 hours for 10 days ."),
     band("neo", "Neonatal HSV (birth–3 months)", [0, 3 * M], 30,
          quote="Neonatal Herpes Simplex Virus Infections (Birth to 3 months) 10 mg/kg infused at a constant rate over 1 hour, every 8 hours for 10 days.",
          flags=["indication_mismatch", "mgkg_shared"])])

D["fluconazole"] = drug("fluconazole.json", "azole", "css",
    0.80, "with approximately 80% of the administered dose appearing in the urine as unchanged drug.",
    400, [400, 400], "systemic Candida infections (adults: doses of up to 400 mg daily)",
    "doses of up to 400 mg daily have been used",
    [band("child", "3 months and older (systemic Candida)", [3 * M, OPEN_UPPER], 12,
          quote="3 months and older A loading dose of 25-mg/kg on the first day (not to exceed 800 mg), followed by 12-mg/kg once daily (not to exceed 400 mg)."),
     band("neo_ge30", "Birth to 3 months, GA ≥30 weeks", [0, 3 * M], 12, ga=35,
          quote="Birth to 3 months postnatal age and gestational age 30 weeks and above 25-mg/kg on the first day, followed by 12- mg/kg once daily"),
     band("neo_lt30", "Birth to 3 months, GA <30 weeks", [0, 3 * M], 9, ga=28,
          quote="Birth to 3 months postnatal age and gestational age less than 30 weeks 25-mg/kg on the first day, followed by 9- mg/kg once daily")],
    adult_flags=["adult_up_to"],
    notes="Indication with the most pediatric bands (systemic Candida; label: pediatric regimens chosen to match adult AUC). Adult reference is the label's 'up to 400 mg daily'.")

D["levetiracetam"] = drug("levetiracetam.json", "anticonvulsant", "css",
    0.66, "Sixty-six percent (66%) of the dose is renally excreted unchanged.",
    3000, [3000, 3000], "partial-onset seizures, recommended dose (1500 mg twice daily)",
    "Adults 16 Years and Older: 500 mg twice daily; increase by 500 mg twice daily every 2 weeks to a recommended dose of 1500 mg twice daily",
    [band("infant_1_6m", "1 to <6 months", [M, 6 * M], 42,
          quote="1 Month to < 6 Months: 7 mg/kg twice daily; increase by 7 mg/kg twice daily every 2 weeks to recommended dose of 21 mg/kg twice daily"),
     band("infant_6m_4y", "6 months to <4 years", [6 * M, 4 * Y], 50,
          quote="6 Months to < 4 Years: 10 mg/kg twice daily; increase by 10 mg/kg twice daily every 2 weeks to recommended dose of 25 mg/kg twice daily"),
     band("child_4_16", "4 to <16 years", [4 * Y, 16 * Y], 60,
          quote="every 2 weeks to recommended dose of 30 mg/kg twice daily")],
    notes="Non-renal fraction is enzymatic hydrolysis (not CYP) and stays unattributed.")

D["famotidine"] = drug("famotidine.json", "H2 antagonist", "css",
    0.675, "Sixty-five to 70% of an intravenous dose are recovered in the urine as unchanged compound.",
    40, [40, 40], "adults: 20 mg every 12 hours",
    "Adults: 20 mg every 12 hours.",
    [band("child", "Pediatric patients 1–16 y (0.25 q12h titrated to 0.5 q12h)", [Y, OPEN_UPPER], 0.75, [0.5, 1.0],
          quote="Pediatric Patients 1 year of age and older: 0.25 mg/kg every 12 hours; titrate to a maximum of 0.5 mg/kg every 12 hours")])

D["daptomycin"] = drug("daptomycin.json", "lipopeptide", "css",
    0.52, "approximately 78% of the administered dose was recovered from urine based on total radioactivity (approximately 52% of the dose based on micro",
    280, [280, 280], "cSSSI, CLcr ≥30 mL/min (4 mg/kg q24h × 70 kg)",
    "≥30 mL/min 4 mg/kg once every 24 hours 6 mg/kg once every 24 hours",
    [band("adol", "12–17 years", [12 * Y, 18 * Y], 5,
          quote="12 to 17 years 5 mg/kg once every 24 hours infused over 30 minutes Up to 14 days"),
     band("child_7_11", "7–11 years", [7 * Y, 12 * Y], 7,
          quote="7 to 11 years 7 mg/kg once every 24 hours infused over 30 minutes"),
     band("child_2_6", "2–6 years", [2 * Y, 7 * Y], 9,
          quote="2 to 6 years 9 mg/kg once every 24 hours infused over 60 minutes"),
     band("infant_1_2", "1 to <2 years", [Y, 2 * Y], 10,
          quote="1 to less than 2 years 10 mg/kg once every 24 hours infused over 60 minutes")],
    notes="fe = microbiologically active (unchanged) fraction, not total radioactivity. Label age bands are whole years (7–11 y means through the 12th birthday).")

D["cefoxitin"] = drug("cefoxitin.json", "beta-lactam", "time_mic",
    0.85, "Approximately 85 percent of cefoxitin is excreted unchanged by the kidneys over a 6-hour period",
    5500, [3000, 8000], "usual adult dosage range (1–2 g q6–8h)",
    "The usual adult dosage range is 1 gram to 2 grams every 6 to 8 hours.",
    [band("child", "Pediatric patients ≥3 months", [3 * M, OPEN_UPPER], 120, [80, 160],
          quote="The recommended dosage in pediatric patients 3 months of age and older is 80 to 160 mg/kg of body weight per day")])

D["aztreonam"] = drug("aztreonam.json", "beta-lactam", "time_mic",
    0.65, "Approximately 60% to 70% of an intravenous or intramuscular dose was recovered in the urine by 8 hours.",
    5000, [2000, 8000], "moderately severe to severe systemic infections (union of tiers 1 g q12h–2 g q6h)",
    "Moderately severe systemic infections 1 g or 2 g 8 or 12 Severe systemic or life-threatening infections 2 g 6 or 8",
    [band("child", "Pediatric patients 9 months–16 y (moderate to severe)", [9 * M, 16 * Y], 105, [90, 120],
          quote="Moderate to severe infections 30 mg/kg 6 or 8")],
    notes="Age band from Pediatric Use: established in the age groups 9 months to 16 years.")

D["penicillin_g"] = drug("penicillin_g_potassium.json", "beta-lactam", "time_mic",
    0.60, "Approximately 60 percent of the total dose of 300,000 units is excreted in the urine within this 5-hour period.",
    24_000_000, [24_000_000, 24_000_000], "meningococcal meningitis (most severe indication with a pediatric row)",
    "Meningococcal meningitis and/or septicemia 24 million units/day as 2 million units every 2 hours",
    [band("child", "Pediatric patients, pneumococcal/meningococcal meningitis", [28, OPEN_UPPER], 250_000,
          quote="Meningitis caused by susceptible strains of pneumococcus and meningococcus 250,000 units/kg/day divided in equal doses every 4 hours")],
    unit="units", notes="Urinary fraction is the label's 5-hour collection (the only quantitative value).")

D["cefuroxime"] = drug("cefuroxime.json", "beta-lactam", "time_mic",
    0.89, "Approximately 89% of a dose of cefuroxime is excreted by the kidneys over an 8-hour period",
    3375, [2250, 4500], "usual adult dosage range (750 mg–1.5 g q8h)",
    "The usual adult dosage range for Cefuroxime for Injection is 750 mg to 1.5 grams every 8 hours",
    [band("child", "Pediatric patients above 3 months", [3 * M, OPEN_UPPER], 75, [50, 100],
          quote="Administration of 50 to 100 mg/kg/day in equally divided doses every 6 to 8 hours")])

D["clindamycin"] = drug("clindamycin.json", "lincosamide", "css",
    0.0, "predominantly metabolized by Cytochrome P450 3A4 (CYP3A4)",
    1650, [600, 2700], "serious to more severe infections (union of tiers 600–2700 mg/day)",
    "600–1200 mg/day in 2, 3 or 4 equal doses.",
    [band("child", "1 month–16 years", [M, 16 * Y], 30, [20, 40],
          quote="Pediatric Patients 1 month of age to 16 years Parenteral (IM or IV) Administration 20 to 40 mg/kg/day in 3 or 4 equal doses."),
     band("neo", "Pediatric patients less than 1 month", [0, M], 17.5, [15, 20],
          quote="Pediatric Patients less than 1 month The recommended dosage is 15 to 20 mg/kg/day in 3 to 4 equal doses.")],
    enzyme="cyp3a4", enzyme_evidence="label", fe_flags=["fe_not_in_label"],
    notes="Label Table 3 (PMA-based neonatal regimens) is not machine-readable text, so those bands are not scored (E1/E2 text rule). Adult tier quote continues with 1200–2700 mg/day for more severe infections.")

D["morphine"] = drug("morphine.json", "opioid", "css",
    0.07, "Morphine is also eliminated by the kidneys, 2 to 12% being excreted unchang",
    100.8, [33.6, 168.0], "continuous IV infusion, initiation 0.02–0.1 mg/kg/hour × 70 kg",
    "Adults: Initiate treatment in a dosing range of 0.02 mg/kg/hour to 0.1 mg/kg/hour as needed.",
    [band("child", "1 to <17 years, <50 kg (initiation)", [Y, 17 * Y], 0.6, [0.48, 0.72],
          quote="Less than 50 kg body weight: 20 mcg/kg/hour to 30 mcg/kg/hour (0.02 mg/kg/hour to 0.03 mg/kg/hour)"),
     band("infant", "<1 year including neonates (initiation)", [0, Y], 0.18, [0.12, 0.24],
          quote="Initiate treatment in a dosing range of 0.005 mg/kg/hour to 0.01 mg/kg/hour.")],
    enzyme="ugt2b7", enzyme_evidence="literature: UGT2B7 forms M3G/M6G (Coffman et al., Drug Metab Dispos 1997;25:1-4)",
    notes="Label states hepatic glucuronidation is the major clearance pathway; enzyme identity from literature.")

D["zidovudine"] = drug("zidovudine.json", "NRTI", "css",
    0.29, "After IV dosing, about 29% of the dose was excreted in the urine unchanged",
    420, [420, 420], "adult IV dosing (1 mg/kg q4h × 70 kg)",
    "The recommended intravenous dose is 1 mg per kg infused at a constant rate over 1 hour every 4 hours.",
    [band("neo", "Neonates, birth to 6 weeks (IV)", [0, 42], 6,
          quote="Intravenous 6 mg/kg/day 1.5 mg/kg infused over 30 minutes, every 6 hours", flags=["mgkg_shared", "indication_mismatch"])],
    enzyme="ugt2b7", enzyme_evidence="literature: zidovudine glucuronidation by UGT2B7 (Barbier et al., Drug Metab Dispos 2000;28:497-502)",
    notes="Label: major route is metabolism to GZDV (the glucuronide).")

EXCLUDED = {
    "midazolam": ("E1", "Selected label (rule: pediatric mention, latest effective_time) has no continuous-infusion or other maintenance regimen in its machine-readable Dosage and Administration text."),
    "cefazolin": ("E1", "Adult treatment dosage table is an image in the selected label; only the perioperative prophylaxis regimen is text, so no adult regimen can be paired to the pediatric 25–100 mg/kg/day treatment text."),
    "digoxin": ("E2", "Selected label defers pediatric dosing under 10 years to a separate pediatric product label (not available from this manufacturer). It also fails E1: the adult and over-10-year maintenance doses are in image tables (Tables 2–3)."),
    "fentanyl": ("E1", "Label gives only induction/premedication bolus doses (adult 50–100 mcg; children 2–3 mcg/kg), not a maintenance regimen."),
}
for k, (crit, why) in EXCLUDED.items():
    D[k] = {"included": False, "label": f"{k}.json", "excluded_by": crit, "reason": why}

import re
LAB = os.path.join(HERE, "..", "labels") + os.sep
for k, v in D.items():
    if not v["included"]:
        continue
    lab = json.load(open(LAB + v["label"]))
    cp = " ".join(lab["sections"].get(s, "") for s in ("clinical_pharmacology", "pharmacokinetics"))
    sec = re.search(r"tubular (secretion|excretion)", cp, re.I)
    gfr = re.search(r"glomerular filtration", cp, re.I)
    if v["target_metric"] != "cmax" and v["fe"]["value"] < 0.5:
        mech, ev = "not_renal_predominant", None
    elif sec:
        mech, ev = "secretion", sec.group(0)
    elif gfr:
        mech, ev = "glomerular_filtration", gfr.group(0)
    else:
        mech, ev = "unspecified", None
    v["renal_mechanism"] = {"value": mech, "matched": ev,
                            "rule": "regex on label clinical pharmacology: 'tubular (secretion|excretion)' -> secretion; else 'glomerular filtration' -> glomerular_filtration; else unspecified"}

out = {"_about": ("PaedScale label benchmark reference set. Curated from FDA SPL text snapshots in "
                  "benchmark/labels/ under benchmark/PROTOCOL.md. Every number carries a verbatim quote "
                  "checked by tests/test_benchmark.py. Harness only: never read by the product path."),
       "drugs": dict(sorted(D.items()))}
json.dump(out, open(os.path.join(HERE, "..", "reference_set.json"), "w"), indent=1, ensure_ascii=False)
print(sum(1 for v in D.values() if v["included"]), "included;", sum(len(v["bands"]) for v in D.values() if v["included"]), "bands")
