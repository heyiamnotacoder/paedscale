---
title: "Adding organ maturation to allometric scaling of adult clearance for children: two pre-registered evaluations against labels and published clearance"
subtitle: "Original Article. Draft for submission to the British Journal of Clinical Pharmacology. Decision-support research, not prescribing guidance."
author: "[Author names, affiliations and ORCID iDs to be completed by the authors]"
date: "Draft of 28 November 2026"
---

**Running head:** Maturation-adjusted scaling of adult clearance for children

**Corresponding author:** [to be completed by the authors]

**Principal Investigator statement:** [To be completed by the authors: either name the Principal Investigator, or state that there is no Principal Investigator because the study used no patient data.]

**Keywords:** allometry; clearance; maturation; neonates; paediatric dosing; pharmacokinetics

**Word count:** {{word_count}} words (Introduction to Discussion). **Tables:** {{n_tables}}. **Figures:** {{n_figures}}. Supporting information: {{n_supp_tables}} and {{n_supp_figures}}.

## What is already known about this subject

- Scaling adult doses by weight, body surface area or allometry ignores organ maturation.
- Published maturation curves describe glomerular filtration and several drug-metabolising enzymes from preterm birth to adulthood.
- Whether they improve scaled predictions across many drugs has rarely been tested prospectively.

## What this study adds

- In two pre-registered evaluations, adding maturation to allometry reduced prediction error under 2 years, against labelled doses and published clearance.
- It did not outperform weight-linear scaling, which had the lowest point estimate of error against neonatal labels.
- Data, code and every result are public and reproducible.

# Abstract

**Aim.** To test whether multiplying allometric size scaling by published organ-maturation curves brings predictions from adult data closer to paediatric data than size scaling alone.

**Methods.** PaedScale is an open-source engine that scales adult clearance by (weight/70)^0.75 and by maturation curves for glomerular filtration, CYP3A4 and UGT2B7. Two protocols were committed before any prediction. In a label benchmark, five methods predicted the paediatric intravenous doses in US labels for {{n_drugs}} drugs. In a clearance validation, four methods predicted total clearance in {{ext_n_obs}} groups of children reported in PubMed abstracts ({{ext_n_drugs}} drugs), extracted by two AI-assisted passes and adjudicated. The endpoint was the ratio of typical fold errors, PaedScale to allometry, with 95% cluster-bootstrap confidence intervals over drugs.

**Results.** Against labels, the ratio (comparator: allometry with a drug-class rule) was {{H1_ratio}} in newborns and {{H2_ratio}} under 2 years, but {{H3_ratio}} across all ages. Against published clearance (comparator: allometry), it was {{ext_he1_ratio}} under 2 years ({{ext_he1_drugs}} drugs) and {{ext_he2_ratio}} at all ages. Weight-linear scaling had a lower point estimate of error than PaedScale against neonatal labels (not formally compared) and similar error against published clearance ({{ext_sec_weight_linear}}). The engine's parameter-uncertainty interval contained {{ext_coverage}} of observed clearances.

**Conclusion.** Maturation curves corrected most of allometry's overprediction in newborns and infants. They did not outperform weight-linear scaling, and their uncertainty interval is not a prediction interval.

# Introduction

Most children admitted to tertiary paediatric hospitals receive at least one drug outside the terms of its licence [1]. Potential adverse drug events are about three times as common in paediatric inpatients as in adults, incorrect dosing is the most common type, and the rate is highest in neonatal intensive care [2]. When a label gives no paediatric dose, a common shortcut is to scale the adult dose by weight, by body surface area [3] or by allometry, in which clearance scales with weight to the power 0.75 [4].

Size alone does not explain clearance in early life. Glomerular filtration and the main drug-metabolising enzymes mature over the first months to years after birth, and postmenstrual age describes this maturation better than postnatal age [4]. Published sigmoid (Hill) maturation models exist for glomerular filtration [5], for CYP3A4 as measured by midazolam clearance [6] and for UGT2B7 as measured by morphine clearance [7]. Simulation work shows that allometry with a fixed exponent of 0.75 predicts clearance less well the younger the child [8].

PaedScale is an open-source decision-support system that combines allometry with these curves. A large language model maps a drug to its elimination pathways and retrieves cited pharmacokinetic data, and a deterministic engine does all of the arithmetic. This paper does not test the language-model layer. It asks a narrower question that can be pre-registered and reproduced offline: given only adult data and a child's age and weight, does adding the maturation term bring a size-scaled prediction closer to what is known about that child?

No single reference standard answers that question, so we used two. Labelled paediatric doses are what prescribers use, but many are set by convention in mg/kg rather than to match adult exposure. Published paediatric clearance is closer to exposure, but it comes from small studies with their own designs. We pre-registered one evaluation against each, with the same engine and comparators that differ from it only by the maturation term.

# Methods

## The PaedScale engine

For each elimination pathway the engine scales adult clearance as

$$CL_{child} = CL_{adult} \times (WT/70)^{0.75} \times MF(PMA), \qquad MF(PMA) = \frac{PMA^{H}}{TM_{50}^{H} + PMA^{H}}$$

where WT is body weight (kg), PMA is postmenstrual age (weeks), TM50 is the PMA at half-maturation and H is the Hill coefficient. Clearance is split by the fraction excreted unchanged in urine (fe), which follows the renal curve, and the non-renal fraction, which follows an enzyme curve when the principal enzyme is known and size alone otherwise. The three curves are glomerular filtration (TM50 47.7 weeks, Hill 3.40) [5], CYP3A4 (73.6 weeks, 3.0) [6] and UGT2B7 (54.2 weeks, 3.92) [7] (Figure 1). The engine refuses a pathway without a published curve. It also reports a 90% parameter-uncertainty interval by sampling TM50 and Hill within their published confidence intervals; this interval describes uncertainty in the curves only.

![**Figure 1.** The three published maturation curves used by the engine, with 90% parameter-uncertainty bands.](figures/fig1_maturation_curves.png)

## Pre-registration

Each evaluation has a protocol in the public repository, committed before any prediction was computed (`backend/benchmark/PROTOCOL.md` and `backend/benchmark/external/PROTOCOL.md`). Every change is a dated amendment that states what had been seen when it was made. The label benchmark had three amendments, all before scoring. The clearance validation had 16 amendments before any prediction. Eleven were made before any abstract was screened. Amendments 12 and 13 fixed scoring details and a checker error while the passes ran. Amendment 14 set rules for questions that the screeners had decided inconsistently, after the first pass's records and reports had been read; Amendment 15 added rules during adjudication, after both passes had finished; and Amendment 16 recorded the adjudication; together they list every effect on the dataset. Two amendments after scoring corrected code and documentation, and added Figures 3 and 4; neither changed a scored number.

## Evaluation 1: label benchmark

**Reference standard.** For each candidate drug the intravenous US Structured Product Label was taken from openFDA (retrieved 27 November 2026) by a fixed rule, and its text was committed. Of {{n_candidates}} candidates chosen before scoring, {{n_drugs}} met four label criteria (L1–L4): an adult intravenous maintenance regimen as text, a paediatric intravenous regimen for a defined age band, elimination that maps onto a published curve, and linear clearance at labelled doses. They gave {{n_bands}} adult–paediatric pairs (Supporting Tables S1 and S2). The reference was the labelled daily maintenance dose in mg/kg/day, at its midpoint for a range. Every dose and fe value carries a quotation checked by a test against the label text.

**Predictions.** Each labelled band was represented by seven postnatal ages log-spaced across it, each with the sex-averaged median weight from the Fenton preterm, WHO and CDC references [9–11], and the band's prediction was their geometric mean. Every method received the same adult daily dose. The target metric followed a drug-class rule: aminoglycosides were matched on peak concentration (dose scaled by volume), β-lactams on daily exposure as a flagged proxy for time above the minimum inhibitory concentration, and all other drugs on average concentration. Five methods were compared: weight-linear, body surface area (Costeff formula [3]), allometry, allometry with the class rule (A1, the primary comparator, which differs from PaedScale only by the maturation term) and PaedScale.

**Hypotheses.** H1 (newborns, under 28 days), H2 (under 2 years) and H3 (all ages) were tested in sequence, each only if the previous one succeeded.

## Evaluation 2: clearance validation

**Drugs.** The {{ext_drugs}} drugs of the label benchmark's reference set other than morphine, the source drug of the UGT2B7 curve, with the engine inputs (fe and enzyme) frozen as recorded there. For piperacillin–tazobactam the analyte was piperacillin.

**Search.** For each drug, one paediatric and one adult PubMed query required the drug name, "clearance" and "pharmacokinetic*" in the title or abstract, a paediatric or adult term, human studies, English and an abstract. The snapshot of {{ext_ped_hits}} paediatric and {{ext_adult_hits}} adult records was saved on 27 November 2026, with a SHA-256 hash of each abstract, before screening. A regular expression fixed in advance passed only abstracts that print a numeric clearance with units ({{ext_ped_prefilter}} paediatric and {{ext_adult_prefilter}} adult abstracts). The validation therefore uses only values printed in abstracts.

**Eligibility.** A paediatric study was included if its abstract described patients under 18 years given the drug intravenously (P1); reported a numeric total clearance for a defined group, or a population typical value at a stated covariate point (P2); stated the group's age (P3); and did not restrict the population to extracorporeal support, therapeutic hypothermia, stated organ impairment, burns, cystic fibrosis or obesity (P4). Apparent clearance after oral or intramuscular dosing (CL/F) was not extracted. Critically ill groups were included and flagged. Abstracts were screened in a seeded random order per drug, and screening of a drug stopped in each ICH E11 age stratum [12] once two studies were included there. The adult reference was the median of up to the first five qualifying adult abstracts, from adults aged 18–65 years who were healthy or had normal renal function. Per-kg values and absolute values with a stated weight were converted to 70 kg; absolute values without a weight were used as reported. A drug with no qualifying adult abstract was excluded.

**Extraction and adjudication.** Each included group gave one observation: its clearance and units, central age or age range and, where stated, weight, each with a verbatim quote that a script checks against the hashed abstract. Missing weight was imputed from the growth references and missing gestational age from a fixed rule; both were flagged. Two passes screened and extracted every abstract that the stopping rule reached, each run by an AI assistant (Claude, Anthropic) from the protocol and the abstracts alone, without access to the other pass's records. The protocol records four departures from strict blinding. Before screening, one paediatric abstract was printed in full by a test of the screening queue, and a tally of unit forms over all pre-filtered abstracts showed a few unmasked words next to the units (Amendments 4 and 6). The second-pass screeners started after Amendments 13 and 14 had been committed, and one of them applied Amendment 14 while screening, which can only raise agreement on those questions (Amendment 15). The code that compares extracted values was adjusted after a first agreement output had been read, which raised exact per-abstract agreement from 76 abstracts to the {{ext_val_agree}} of {{ext_both_incl}} reported below, and the value-by-value count was added after the second pass's records had been read (Amendment 16). Neither of the last two changes touches the inclusion decisions or κ. Agreement on inclusion is reported as Cohen's κ over the abstracts both passes read. Each disagreement was resolved by re-reading the abstract against the protocol and logged with its reason. Amendments 14 and 15 then applied to both passes' records. The main one: an abstract that reports a clearance that is not CL/F and mentions no non-intravenous dosing counts as intravenous, flagged `route_unstated`; sensitivity analysis E9 removes such studies. The final dataset was committed before any prediction.

**Predictions.** Every method received the same adult clearance and the same child. For an age range, predictions were made at seven log-spaced ages and their geometric mean was used; a stated postmenstrual age was used directly. Four methods were compared: weight-linear, body surface area, allometry (the primary comparator, which differs from PaedScale only by the maturation term) and PaedScale.

**Hypotheses.** HE1: under 2 years, PaedScale has lower error than allometry. HE1 was confirmatory only if at least 8 drugs contributed. HE2 (all ages) was tested only if HE1 succeeded.

## Endpoints and statistics

In both evaluations the fold error is FE = predicted / reference. The average absolute fold error is AAFE = 10^mean(|log10 FE|) and the bias is AFE = 10^mean(log10 FE). Each was computed per drug and then averaged over drugs, so drugs with many observations do not dominate. The primary comparison was the paired difference in drug-level mean |log10 FE| between PaedScale and the primary comparator. We report it as a ratio of typical fold errors, 10 raised to that difference: below 1 favours PaedScale. Intervals are 95% bias-corrected and accelerated (BCa) intervals [13] from a cluster bootstrap that resamples drugs ({{n_boot}} replicates, seed {{seed}}). A hypothesis succeeded when the upper bound of its interval was below 1; an interval entirely above 1 would have counted as evidence against PaedScale. Secondary tests were a drug-level Wilcoxon signed-rank test and, for the clearance validation, an exact sign-flip test (the share of all sign assignments of the drug-level differences that give an absolute sum at least as large as the one observed). Comparisons with the other methods are secondary, with Holm-adjusted p-values [14], as are the shares of predictions within 0.67–1.5× and 0.5–2× of the reference. Sensitivity analyses S1–S10 and E1–E8 were pre-specified; E9 was added by Amendment 14, after the first pass's decisions were known (Table 4). The share of reference values inside PaedScale's 90% parameter-uncertainty interval was exploratory. Reporting follows TRIPOD+AI [15] where it applies to the evaluation of prediction performance.

## Use of AI tools

The authors used an AI assistant, Claude (Anthropic), to write the software and the analysis and curation code, to run both screening and extraction passes, to draft adjudication records and to draft this manuscript. The authors directed the work and are accountable for all content, and must verify the final dataset and every statement before submission.

## Software and reproducibility

`python3 -m benchmark.run` and `python3 -m benchmark.external.score` regenerate every result and figure, and each output records the engine's git commit. The outputs come from commits {{engine_commit}} (labels) and {{ext_engine_commit}} (clearance) with a clean working tree, Python {{python_version}}, NumPy {{numpy_version}} and SciPy {{scipy_version}}. This manuscript is generated from those outputs (`python3 -m paper.build`): every result in the text and tables is filled in by script.

# Results

## Label benchmark

In total, {{n_drugs}} drugs and {{n_bands}} adult–paediatric pairs were included, mostly renally cleared anti-infectives; clindamycin mapped to CYP3A4, and morphine and zidovudine to UGT2B7. PaedScale's typical fold error was lower than A1's in newborns ({{H1_ratio}}) and under 2 years ({{H2_ratio}}), so H1 and H2 were supported (Table 1). Across all ages the interval reached just above 1 ({{H3_ratio}}), so H3 was not supported. The drug-level Wilcoxon tests were not significant (H1 p = {{H1_p}}; H2 p = {{H2_p}}).

Size-only methods overpredicted newborn doses: allometry by about twofold (AFE {{newborn_allometry_afe}}) and body surface area by more (AFE {{newborn_bsa_afe}}). PaedScale tended to underpredict them (AFE {{newborn_paedscale_afe}}). Weight-linear scaling had the lowest error in newborns (AAFE {{newborn_weight_linear_aafe}} against {{newborn_paedscale_aafe}} for PaedScale) and the least bias (AFE {{newborn_weight_linear_afe}}; Table 2, Figure 2). Other secondary endpoints are in Supporting Tables S5–S7.

{{table_hypotheses}}

Table: **Table 1. Pre-specified hypotheses.** Label benchmark: PaedScale against allometry with the class rule (A1); clearance validation: PaedScale against allometry. The ratio of typical fold errors is 10 raised to the mean paired difference in drug-level |log10 FE|, with its 95% BCa cluster-bootstrap confidence interval; below 1 favours PaedScale.

{{table_label_methods}}

Table: **Table 2. Label benchmark: agreement with the labelled dose by method (drug-weighted, with 95% confidence intervals).** AAFE, average absolute fold error; AFE, average fold error (above 1 means overprediction).

![**Figure 2.** Label benchmark: fold error of each prediction against the labelled dose, by ICH E11 stratum. The shaded band is 0.67–1.5×.](figures/fig2_fold_error_by_stratum.png)

## Clearance validation: search, screening and agreement

Every one of the {{ext_ped_prefilter}} paediatric abstracts that passed the pre-filter was screened, because no drug filled all of its age strata. Of these, {{ext_ped_included}} studies were included, giving {{ext_ped_obs}} observations. The others were excluded for these reasons: {{ext_ped_reasons}}. Of {{ext_adult_prefilter}} adult abstracts, {{ext_adult_screened}} were screened until five qualified or the list ended, and {{ext_adult_included}} qualified.

The two passes both read {{ext_both_read}} abstracts and disagreed on {{ext_dec_dis}} inclusion decisions (κ = {{ext_kappa}}). Of the {{ext_both_incl}} abstracts both included, {{ext_val_agree}} had identical extractions; {{ext_num_differ}} of {{ext_num_compared}} numbers compared one by one differed.

No qualifying adult abstract was found for {{ext_n_no_adult}} drugs ({{ext_no_adult}}), which were therefore excluded, and no paediatric observation was included for {{ext_no_obs}} (Supporting Table S3). The scored set had {{ext_n_drugs}} drugs and {{ext_n_obs}} observations: {{ext_scored_drugs}}.

## Clearance validation: primary and secondary results

Under 2 years, {{ext_he1_drugs}} drugs contributed {{ext_he1_obs}} observations, so HE1 was {{ext_he1_status}}. PaedScale's typical fold error was {{ext_he1_ratio}} that of allometry, so HE1 {{ext_he1_verdict}} (Wilcoxon p = {{ext_he1_p}}; sign-flip p = {{ext_he1_signp}}; Table 1). {{ext_he2_sentence}}

Allometry overpredicted clearance under 2 years (AFE {{ext_under2_allometry_afe}}), and body surface area more (AFE {{ext_under2_bsa_afe}}). PaedScale reduced this bias (AFE {{ext_under2_paedscale_afe}}) but still overpredicted, as did weight-linear scaling (AFE {{ext_under2_weight_linear_afe}}; Table 3, Figure 3). The overprediction was concentrated in newborns. PaedScale's AFE was {{ext_st_preterm_newborn_paedscale_afe}} in preterm and {{ext_st_term_newborn_paedscale_afe}} in term newborns, against {{ext_st_preterm_newborn_allometry_afe}} and {{ext_st_term_newborn_allometry_afe}} for allometry (Supporting Table S4). By stratum, the ratio against allometry was {{ext_st_preterm_newborn_ratio}} in preterm newborns, {{ext_st_term_newborn_ratio}} in term newborns, {{ext_st_infant_toddler_ratio}} in infants and toddlers and {{ext_st_child_ratio}} in children aged 2–11 years.

Across all ages PaedScale's error was lower than that of body surface area scaling ({{ext_sec_bsa}}; Holm p = {{ext_sec_bsa_holm}}). It was not clearly lower than that of weight-linear scaling ({{ext_sec_weight_linear}}; Holm p = {{ext_sec_weight_linear_holm}}). At all ages, {{ext_n_favour}} of the {{ext_n_drugs}} drugs favoured PaedScale over allometry; {{ext_not_favour}} did not (Figure 4).

{{table_ext_methods}}

Table: **Table 3. Clearance validation: agreement with published clearance by method (drug-weighted, with 95% confidence intervals).** AAFE, average absolute fold error; AFE, average fold error (above 1 means overprediction).

![**Figure 3.** Clearance validation: fold error of each method against the central postnatal age of each study group. The shaded band is 0.67–1.5×; the dotted line marks 2 years.](figures/fig4_external_fold_error_by_age.png)

![**Figure 4.** Clearance validation: per-drug ratio of typical fold error, PaedScale ÷ allometry, under 2 years and at all ages, with the all-drug estimates and their 95% BCa confidence intervals.](figures/fig5_external_paired_difference_by_drug.png)

## Sensitivity analyses and uncertainty

In the clearance validation, the under-2 interval excluded 1 in {{ext_n_sens_excluding_1}} of the {{ext_n_sens}} sensitivity analyses that give an interval, and leaving one drug out at a time gave estimates from {{ext_e6_he1}} (Table 4). Excluding imputed weights or gestational ages (E1) left {{ext_e1_drugs}} drugs under 2 years, so that analysis is {{ext_e1_status}}. In the label benchmark, the newborn interval included 1 in {{label_n_sens_crossing_1}} of the {{label_n_sens}} sensitivity analyses that give an interval. PaedScale's 90% parameter-uncertainty interval contained {{ext_coverage}} of the observed clearances and {{coverage}} of the labelled doses.

{{table_sensitivity}}

Table: **Table 4. Pre-specified sensitivity analyses, PaedScale against the primary comparator.** Ratio of typical fold errors with its 95% BCa cluster-bootstrap confidence interval. In the label benchmark the primary population is newborns; in the clearance validation it is children under 2 years.

# Discussion

In two pre-registered evaluations with different reference standards, adding published maturation curves to allometric scaling reduced the error of predictions for children under 2 years. Against published clearance, the typical fold error under 2 years was {{ext_he1_reduction}} lower than with allometry, and the result held in the sensitivity analyses. The gain came from the youngest children: in preterm and term newborns, allometry overpredicted clearance on average {{ext_st_preterm_newborn_allometry_afe}}- and {{ext_st_term_newborn_allometry_afe}}-fold, and the maturation term removed most of that bias. Beyond 2 years PaedScale and allometry gave nearly the same predictions, as expected from curves that are mostly mature by then (Figure 1). That the two evaluations agree is the main finding, because their weaknesses differ: labels mix exposure matching with convention, while published clearance reflects small studies with their own designs.

Two findings limit the claim. First, plain weight-linear scaling did as well as PaedScale or better. Against neonatal labels it had the lowest point estimates of error and bias, although no paired test of the two methods in newborns was pre-specified. Against published clearance the two methods had similar error under 2 years, and across all ages the difference was not significant. Linear scaling gives a small child less clearance than allometry does, because WT/70 is smaller than (WT/70)^0.75, and in the first months of life this happens to offset much of the immaturity that the maturation term models. Against labels there is a second reason: many neonatal labels are written in mg/kg, which linear scaling reproduces by construction. The offset does not hold at every age; linear scaling underpredicted clearance in children aged 2–11 years. A method that is right for a mechanistic reason is preferable, but these data do not show that PaedScale predicts better than weight-linear scaling.

Second, PaedScale still overpredicted clearance in newborns, on average {{ext_st_preterm_newborn_paedscale_afe}}-fold in preterm and {{ext_st_term_newborn_paedscale_afe}}-fold in term newborns. Several explanations are possible. Many neonatal studies enrolled sick infants; the renal curve describes glomerular filtration in a mixed population [5]; and for drugs with large non-renal clearance and no mapped enzyme, the engine scales that fraction by size alone, which ignores its maturation. For a starting dose, an overprediction of clearance means a dose that is too high. A maturation-scaled starting dose for a newborn therefore needs a downward check against neonatal data or a guideline.

The parameter-uncertainty interval contained almost none of the observed clearances. This is the expected result for an interval that reflects uncertainty in two curve parameters only, and it confirms that the interval must not be read as a prediction interval for a child or a study group. A useful interval would also need between-subject and between-study variability.

The clearance validation was designed to limit the usual weaknesses of literature-based validation. The search, the screening order and the stopping rule were fixed before any abstract was read, so studies could not be picked by their results. Two passes screened with high agreement, every number is tied to a verbatim quote that a script checks, and the rules the adjudicator needed were written as dated amendments, with their effect on the dataset listed. Removing the studies most affected by those rules, whose abstracts state no route (E9), strengthened the result.

## Limitations

- **Abstracts only.** Only values printed in abstracts were used. Abstracts summarise small studies with different designs, assays and sampling, and population typical values depend on the authors' models.
- **Sample.** Only {{ext_n_drugs}} drugs were scored, mostly renally cleared anti-infectives, and only clindamycin among them maps to an enzyme curve. The results say little about drugs cleared mainly by metabolism.
- **Adult reference.** Several drugs rested on one or two adult abstracts, and {{ext_n_no_adult}} drugs had none that qualified.
- **AI-assisted curation.** Both screening passes, and the drafting of adjudication records, used the same AI assistant directed by the authors. The passes ran separately, but the same model may share systematic errors, and agreement between them is not agreement between independent human reviewers. The protocol records four departures from strict blinding (Methods). None could lower agreement, but the agreement figures should be read with them in mind. The authors must verify the final dataset before publication.
- **Rules set during screening.** Amendments 14 and 15 set inclusion and extraction rules after the first pass's records, and for Amendment 15 both passes' records, were known. They are dated, their effects are listed, and sensitivity analysis E9 removes the studies most affected.
- **Uncertainty interval.** The interval covers curve parameters only.
- **Scope.** Neither evaluation tests the retrieval and language-model layers of the application, which need separate evaluation.

## Conclusions

Published maturation curves corrected most of the large overprediction that allometric scaling gives for newborns and infants, against both labelled doses and published clearance. They did not outperform weight-linear scaling, and PaedScale still overpredicted neonatal clearance. A maturation-scaled starting dose for a young child therefore still needs checking against neonatal data, a guideline or therapeutic drug monitoring. The open protocols, data and one-command reproduction are offered as a baseline for testing paediatric dose-extrapolation tools, including language-model systems.

# Declarations

**Data availability statement.** The protocols, search snapshot (PMIDs, years and abstract hashes), extraction records of both passes, adjudication log, final dataset, label texts, analysis code, outputs and the manuscript build are openly available in the PaedScale repository at https://github.com/heyiamnotacoder/paedscale. Abstract texts are not redistributed; `python3 -m benchmark.external.curation.search restore` re-fetches them from PubMed and checks each against its committed hash.

**Acknowledgements and funding.** The use of an AI assistant is described in the Methods. [Funding to be completed by the authors.]

**Competing interests.** [To be completed by the authors; state "none" if none.]

**Ethics.** The study used only public drug labels, published abstracts and published growth references. No human participants or patient data were involved.

**Nomenclature.** Terms to be linked to the IUPHAR/BPS Guide to Pharmacology at first mention before submission: CYP3A4, UGT2B7, and the drugs aciclovir, amikacin, ampicillin, aztreonam, benzylpenicillin, cefepime, cefoxitin, ceftazidime, cefuroxime, clindamycin, daptomycin, famotidine, fluconazole, gentamicin, levetiracetam, meropenem, midazolam, morphine, piperacillin, tazobactam, tobramycin, vancomycin and zidovudine.

# References

1. Shah SS, Hall M, Goodman DM, et al. Off-label drug use in hospitalized children. Arch Pediatr Adolesc Med. 2007;161(3):282–290. doi:10.1001/archpedi.161.3.282.
2. Kaushal R, Bates DW, Landrigan C, et al. Medication errors and adverse drug events in pediatric inpatients. JAMA. 2001;285(16):2114–2120. doi:10.1001/jama.285.16.2114.
3. Costeff H. A simple empirical formula for calculating approximate surface area in children. Arch Dis Child. 1966;41(220):681–683. doi:10.1136/adc.41.220.681.
4. Anderson BJ, Holford NHG. Mechanism-based concepts of size and maturity in pharmacokinetics. Annu Rev Pharmacol Toxicol. 2008;48:303–332. doi:10.1146/annurev.pharmtox.48.113006.094708.
5. Rhodin MM, Anderson BJ, Peters AM, et al. Human renal function maturation: a quantitative description using weight and postmenstrual age. Pediatr Nephrol. 2009;24(1):67–76. doi:10.1007/s00467-008-0997-5.
6. Anderson BJ, Larsson P. A maturation model for midazolam clearance. Paediatr Anaesth. 2011;21(3):302–308. doi:10.1111/j.1460-9592.2010.03364.x.
7. Anand KJS, Anderson BJ, Holford NHG, et al. Morphine pharmacokinetics and pharmacodynamics in preterm and term neonates: secondary results from the NEOPAIN trial. Br J Anaesth. 2008;101(5):680–689. doi:10.1093/bja/aen248.
8. Calvier EAM, Krekels EHJ, Välitalo PAJ, et al. Allometric scaling of clearance in paediatric patients: when does the magic of 0.75 fade? Clin Pharmacokinet. 2017;56(3):273–285. doi:10.1007/s40262-016-0436-x.
9. Fenton TR, Kim JH. A systematic review and meta-analysis to revise the Fenton growth chart for preterm infants. BMC Pediatr. 2013;13:59. doi:10.1186/1471-2431-13-59.
10. WHO Multicentre Growth Reference Study Group. WHO Child Growth Standards: length/height-for-age, weight-for-age, weight-for-length, weight-for-height and body mass index-for-age. Methods and development. Geneva: World Health Organization; 2006.
11. Kuczmarski RJ, Ogden CL, Guo SS, et al. 2000 CDC growth charts for the United States: methods and development. Vital Health Stat 11. 2002;(246):1–190.
12. International Council for Harmonisation. E11(R1): Addendum to clinical investigation of medicinal products in the pediatric population. 2017.
13. Efron B. Better bootstrap confidence intervals. J Am Stat Assoc. 1987;82(397):171–185.
14. Holm S. A simple sequentially rejective multiple test procedure. Scand J Stat. 1979;6(2):65–70.
15. Collins GS, Moons KGM, Dhiman P, et al. TRIPOD+AI statement: updated guidance for reporting clinical prediction models that use regression or machine learning methods. BMJ. 2024;385:e078378. doi:10.1136/bmj-2023-078378.

# Supporting information

## Table S1. Label benchmark: included drugs

{{table_drugs}}

fe is the fraction excreted unchanged in urine, as stated in the selected label. The clindamycin label states no urinary fraction but names CYP3A4 as the principal route, so by protocol fe = 0.

## Table S2. Label benchmark: excluded candidates

{{table_excluded}}

L1–L4 are the label criteria in the Methods (E1–E4 in the label protocol).

## Table S3. Clearance validation: drugs, adult references and included studies

{{table_ext_drugs}}

The adult reference is the median of the qualifying adult abstracts' values. Per-kg values and absolute values with a stated weight were converted to 70 kg; absolute values without a weight were used as reported.

## Table S4. Clearance validation: results by ICH E11 stratum

{{table_ext_strata}}

Point estimates of drug-weighted AAFE, with AFE in brackets; the ratio is given with its 95% BCa confidence interval. Intervals are reported only for strata with at least 5 drugs.

## Table S5. Label benchmark: all endpoints by method, newborns

{{table_label_methods_newborn}}

## Table S6. Label benchmark: all endpoints by method, under 2 years

{{table_label_methods_under2}}

## Table S7. Label benchmark: all endpoints by method, all ages

{{table_label_methods_all}}

Drug-weighted, with 95% confidence intervals. Pair-weighted AAFE averages over age bands instead of drugs.

## Table S8. Label benchmark: AAFE by ICH E11 stratum

{{table_strata}}

Drug-weighted point estimates. Several strata contain few drugs.

## Table S9. Label benchmark: secondary all-ages comparisons

{{table_secondary}}

Ratio of typical fold errors, PaedScale ÷ comparator, with its 95% BCa confidence interval; Wilcoxon signed-rank tests on drug-level differences with Holm adjustment.

## Figure S1. Label benchmark: per-drug ratio of typical fold error, PaedScale ÷ A1

![](figures/fig3_paired_difference_by_drug.png)
