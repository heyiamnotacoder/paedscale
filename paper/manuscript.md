---
title: "Adding organ maturation to size scaling of adult doses for children: a pre-registered benchmark against FDA labels"
subtitle: "Preprint draft. Not peer reviewed. Decision support research, not prescribing guidance."
author: "[Author names, affiliations and ORCID iDs to be completed by the authors]"
date: "Draft of 27 November 2026"
---

# Abstract

**Background.** Many drugs given to children have no pediatric dose on their label, and prescribers often scale the adult dose by body size. Scaling by weight or by allometry ignores the maturation of the organs that clear the drug, which matters most in newborns and infants. PaedScale is an open-source decision-support system that multiplies allometric size scaling by published maturation curves for the drug's elimination pathways. We tested whether this maturation term brings size-scaled doses closer to the doses in FDA labels.

**Methods.** We wrote and committed an analysis protocol before scoring any prediction. Three amendments, all made before scoring, are dated in the repository. The reference standard was the pediatric intravenous maintenance dose in public FDA Structured Product Labels, with one label selected per drug by a fixed rule. Of {{n_candidates}} candidate drugs, {{n_drugs}} met the eligibility criteria and gave {{n_bands}} pairs of an adult regimen and a labeled pediatric age band. Five methods received identical inputs: weight-linear scaling, body surface area, allometry, allometry with a drug-class rule for the target metric (A1, the primary comparator), and PaedScale. A1 differs from PaedScale only by the maturation term. The endpoint was the absolute fold error against the labeled dose, averaged first within each drug. Three hypotheses were tested in a fixed sequence: newborns (H1), children under 2 years (H2) and all ages (H3). Each used a 95% BCa cluster-bootstrap interval that resampled drugs ({{n_boot}} replicates).

**Results.** In newborns, PaedScale's typical fold error was {{H1_ratio}} times that of A1 ({{H1_drugs}} drugs, {{H1_pairs}} pairs). Under 2 years the ratio was {{H2_ratio}}. Across all ages it was {{H3_ratio}}, so H3 was not supported. The secondary drug-level Wilcoxon tests did not reach significance (H1 p = {{H1_p}}; H2 p = {{H2_p}}). In newborns, plain weight-linear scaling agreed with the labels at least as closely as PaedScale did (AAFE {{newborn_weight_linear_aafe}} against {{newborn_paedscale_aafe}}). PaedScale's 90% parameter-uncertainty interval contained the labeled dose in {{coverage}} of drugs.

**Conclusions.** Adding published maturation curves to allometric scaling moved predictions closer to FDA-labeled doses in newborns and children under 2 years. It did not do so across all ages. The benchmark is small and measures agreement with labels, not drug exposure. The close agreement of weight-linear scaling with neonatal labels suggests that many of those labels are themselves written in mg/kg. Any clinical use needs prospective, exposure-based evaluation.

# Introduction

Most children admitted to tertiary pediatric hospitals receive at least one drug outside the terms of its license [1]. In one prospective study of pediatric inpatients, potential adverse drug events were three times as common as in a comparable adult study. Incorrect dosing was the most common type, and the rate was highest in the neonatal intensive care unit [2]. When a label gives no pediatric dose, a common shortcut is to scale the adult dose by weight, by body surface area [3] or by allometry, in which clearance scales with weight to the power 0.75 [4].

Size alone does not explain clearance in early life. Glomerular filtration and the main drug-metabolizing enzymes mature over the first months to years after birth. Postmenstrual age describes this maturation better than postnatal age [4]. Published sigmoid (Hill) maturation models exist for glomerular filtration [5], for CYP3A4 as measured by midazolam clearance [6] and for UGT2B7 as measured by morphine clearance [7]. Simulation work shows that allometry with a fixed exponent of 0.75 predicts clearance less well the younger the child [8].

PaedScale combines allometry with these published maturation curves. It is a decision-support system: a large language model maps a drug to its elimination pathways and retrieves cited pharmacokinetic data, and a deterministic engine does all of the arithmetic. This paper does not test the language-model layer. It asks a narrower question that can be pre-registered and reproduced offline. Given only an adult regimen and a child's age and weight, does adding the maturation term bring a size-scaled dose closer to the dose that the FDA label gives that child?

# Methods

## The PaedScale engine

For each elimination pathway, the engine scales adult clearance as

$$CL_{child} = CL_{adult} \times (WT/70)^{0.75} \times MF(PMA) \times OF$$

$$MF(PMA) = \frac{PMA^{H}}{TM_{50}^{H} + PMA^{H}}$$

Here WT is body weight in kg and PMA is postmenstrual age in weeks. TM50 is the PMA at which clearance reaches half its mature value, H is the Hill coefficient, and OF is an organ-function modifier, which equals 1 in this benchmark. The curve is normalized so that an adult has MF of 1. Volume of distribution scales with WT^1.0.

Clearance is split between pathways by the fraction excreted unchanged in urine (fe), which uses the renal curve, and the non-renal fraction. The non-renal fraction uses an enzyme curve when the principal enzyme is known, and is scaled by size alone otherwise. The engine refuses any pathway without a published curve. The curves and their published 95% confidence intervals are:

| Pathway | TM50, weeks PMA (95% CI) | Hill (95% CI) | Source |
|---|---|---|---|
| Glomerular filtration | 47.7 (45.1–50.5) | 3.40 (3.03–3.80) | Rhodin et al. 2009 [5] |
| CYP3A4 (midazolam) | 73.6 (59.4–80.0) | 3.0 (2.2–4.1) | Anderson and Larsson 2011 [6] |
| UGT2B7 (morphine) | 54.2 (50.3–60.5) | 3.92 (3.25–4.40) | Anand et al. 2008 [7] |

![Figure 1. The three published maturation curves used by the engine, with their parameter-uncertainty bands.](figures/fig1_maturation_curves.png)

The dose solve depends on the metric that drives the drug's effect:

- For average concentration (css) or area under the curve, the daily dose scales by the ratio CL_child / CL_adult.
- For peak concentration (cmax), the dose scales by the volume ratio.
- For β-lactams, efficacy depends on the time above the minimum inhibitory concentration. The engine matches daily exposure as for css, flags this as a proxy, and caps the recommendation grade.

When the cited evidence gives toxic or effective dose thresholds, the engine flags any dose past them. The application checks the final recommended dose against the same thresholds again. The engine also reports a 90% parameter-uncertainty interval by Monte Carlo sampling of TM50 and Hill within their published confidence intervals (split log-normal, fixed seed). This interval describes uncertainty in the maturation parameters only. It is not a prediction interval for an individual child.

In the full application, a retrieval agent queries PubMed and openFDA live and returns a cited dossier, or returns no data. An orchestrating agent records the drug's mechanism, calls the engine, checks the result against a guideline, and grades the recommendation from A to D. When the pharmacokinetic data cannot be retrieved, the grade is D and no dose is given. None of this layer is used in the benchmark.

## Benchmark design and pre-registration

The protocol (`backend/benchmark/PROTOCOL.md`) was committed before any prediction was scored. It was amended three times before scoring, each time after an internal methodological, standards or data review. Amendment 1 replaced the co-primary endpoints with a hypothesis sequence and added the primary comparator. Amendment 2 corrected the label-selection code and the curation. Amendment 3 made label selection deterministic and fixed the reporting. Each amendment is dated, states that it preceded scoring, and gives its reason. A scoring record in the protocol states the commit at which scoring first ran. Every later change is a post-scoring amendment.

## Reference standard and eligibility

For each candidate drug, the label was taken from openFDA (`/drug/label.json`, retrieved 27 November 2026) by a fixed rule. The search returned labels whose generic name matched and whose route included intravenous. Combination products were removed: the label's active ingredients had to be exactly the candidate's. The rule then preferred labels whose Dosage and Administration text matched `pediatric|neonat`, then the latest effective date, then the highest SPL version, then the highest set ID. The selected labels' text is committed, so the benchmark reruns offline. Every adult dose, pediatric dose and urinary-excretion value used carries a quotation that a test checks against the stored label text.

There were {{n_candidates}} candidate drugs, chosen by the authors before scoring. They were the PaedScale demonstration drugs plus commonly used intravenous anti-infectives, anticonvulsants, acid suppressants, a cardiac glycoside, sedatives and opioids. A drug was included if its label gave an adult intravenous maintenance regimen as text (E1), gave a pediatric intravenous maintenance regimen for a defined age band (E2), had elimination that mapped onto a published curve (E3), and had linear clearance at labeled doses (E4). {{n_excluded}} candidates were excluded ({{excluded_list}}; Table S1).

The reference dose was the labeled daily maintenance dose in mg/kg/day. A labeled range was scored at its midpoint. Adult and pediatric regimens were paired on the same indication and severity, using rules fixed in the protocol, and the choices and quotations were recorded before scoring. Pairs were flagged when:

- the label gave the adult and the child the same mg/kg (`mgkg_shared`);
- the neonatal indication differed from the adult one;
- the fe was qualitative;
- the dose was an "up to" value.

## Virtual patients and inputs

Each labeled band was scored at seven postnatal ages, spaced evenly on a log scale across the band. The band's prediction was the geometric mean over these ages. Gestational age was 40 weeks unless the band was defined by gestational or postmenstrual age. Weight was the sex-averaged median from three references:

- the Fenton 2013 preterm chart [9], bridged linearly to the WHO standard between 40 and 50 weeks PMA;
- the WHO Child Growth Standards up to 5 years [10];
- the CDC 2000 charts above 5 years [11].

Every method received the same adult daily dose and the same virtual patients. fe came from the label. The non-renal enzyme came from the label, or from fixed literature sources: morphine and zidovudine to UGT2B7 [12, 13]. The target metric followed a class rule, never a per-drug choice:

- aminoglycosides used cmax;
- β-lactams used time above the minimum inhibitory concentration;
- all other drugs used css.

Each pair was assigned to an ICH E11 age stratum [14].

## Methods compared

| Method | Child daily dose |
|---|---|
| Weight-linear | adult × WT/70 |
| Body surface area | adult × BSA(WT)/BSA(70), with Costeff's weight-only formula [3] |
| Allometry only | adult × (WT/70)^0.75 |
| Allometry + class rule (A1) | adult × WT/70 for cmax drugs, otherwise adult × (WT/70)^0.75 |
| PaedScale | the engine with the inputs above |

A1 is the primary comparator because it differs from PaedScale only by the maturation term. For aminoglycosides, PaedScale, A1 and weight-linear scaling give identical predictions by construction. These pairs are reported as ties.

## Endpoints and statistics

The fold error is FE = predicted / labeled dose. The average absolute fold error is AAFE = 10^mean(|log10 FE|) and the bias is AFE = 10^mean(log10 FE). Each metric was computed per drug, as the mean over that drug's bands, and then averaged over drugs, so drugs with many bands do not dominate.

The primary comparison was the paired difference in drug-level mean |log10 FE| between PaedScale and A1. We report it as a ratio of typical fold errors: below 1 favors PaedScale. The 95% confidence intervals came from a cluster bootstrap that resampled drugs ({{n_boot}} replicates, seed {{seed}}). The BCa method [15] was used, with a fallback to the percentile method where BCa is undefined. A drug drawn twice in one replicate counted twice.

The hypotheses were tested in a fixed sequence, each only if the previous one succeeded. Success meant a 95% interval for the difference that excluded zero:

- H1: newborns, under 28 days;
- H2: under 2 years;
- H3: all ages.

A Wilcoxon signed-rank test on drug-level differences is reported as a secondary test. The three all-ages comparisons against the other comparators are secondary, with Holm-adjusted p-values [16]. Eleven sensitivity analyses (S1 to S10, with S4 and S5 run in both directions) were pre-specified.

The exploratory calibration endpoint was the share of labeled doses inside PaedScale's 90% parameter-uncertainty interval.

## Software and reproducibility

One command, `python3 -m benchmark.run`, regenerates every number, table and figure. Each output records the engine's git commit. The committed outputs come from commit {{engine_commit}} with a clean working tree, Python {{python_version}}, NumPy {{numpy_version}} and SciPy {{scipy_version}}. This manuscript is generated from those outputs (`python3 -m paper.build`). Every number in the text and tables is filled in from `results.json`, and none is typed by hand. Continuous integration runs the test suite and a short benchmark run on every push.

# Results

## Included drugs

{{n_drugs}} drugs and {{n_bands}} adult–pediatric pairs were included (Table 1). Most were renally cleared anti-infectives. Three drugs mapped to an enzyme curve: clindamycin to CYP3A4, and morphine and zidovudine to UGT2B7.

{{table_drugs}}

Table: **Table 1. Included drugs.** fe is the fraction excreted unchanged in urine, as stated in the selected label. The clindamycin label states no urinary fraction but names CYP3A4 as the principal route, so by protocol fe = 0 and all clearance uses the CYP3A4 curve.

## Primary hypotheses

PaedScale's typical fold error was lower than A1's in newborns and in children under 2 years. It was not lower across all ages (Table 2). The H3 interval reaches just above 1. The secondary Wilcoxon tests did not reach significance for any hypothesis. Three of the nine newborn drugs are aminoglycosides, which tie by construction.

{{table_hypotheses}}

Table: **Table 2. Pre-specified hypotheses, PaedScale against allometry + class rule (A1).** The ratio is 10 raised to the mean paired difference in |log10 FE|; below 1 favors PaedScale.

![Figure 2. Fold error of each prediction against the labeled dose, by ICH E11 stratum. The shaded band is 0.67–1.5×.](figures/fig2_fold_error_by_stratum.png)

## Agreement with the label, by method and age

{{table_methods_newborn}}

Table: **Table 3. Agreement with the labeled dose in newborns (drug-weighted, 95% CI).**

{{table_methods_under2}}

Table: **Table 4. Agreement with the labeled dose under 2 years.**

{{table_methods_all}}

Table: **Table 5. Agreement with the labeled dose across all ages.**

Size-only methods without a maturation term overpredicted newborn doses on average: allometry by about twofold (AFE {{newborn_allometry_afe}}) and body surface area more (AFE {{newborn_bsa_afe}}). PaedScale slightly underpredicted (AFE {{newborn_paedscale_afe}}). Weight-linear scaling was nearly unbiased in newborns (AFE {{newborn_weight_linear_afe}}). Its absolute error there was the lowest of all methods (AAFE {{newborn_weight_linear_aafe}}).

{{table_strata}}

Table: **Table 6. AAFE by ICH E11 stratum (drug-weighted, point estimates).** Several strata contain few drugs.

## Secondary comparisons

Across all ages, PaedScale's typical fold error was lower than that of body surface area scaling and of allometry alone. The intervals for both excluded 1, but no Holm-adjusted Wilcoxon p-value was below 0.05 (Table 7). Against weight-linear scaling, the interval included 1.

{{table_secondary}}

Table: **Table 7. Secondary all-ages comparisons.**

![Figure 3. Per-drug ratio of typical fold error, PaedScale ÷ A1, all ages. The diamond and bar show the all-drug estimate and its 95% BCa interval, {{H3_ratio}}, which includes 1.](figures/fig3_paired_difference_by_drug.png)

## Sensitivity analyses

The newborn result kept the same direction in every sensitivity analysis (Table 8). Its interval excluded 1 in most of them, but not in three: S2, which leaves 6 drugs; weight +20%; and S9, which leaves 5 drugs. When one drug at a time was left out, the newborn point estimate ranged from {{s6_newborn}} and the all-ages estimate from {{s6_all}}.

{{table_sensitivity}}

Table: **Table 8. Sensitivity analyses, PaedScale against A1.**

## Parameter-uncertainty interval

PaedScale's 90% parameter-uncertainty interval contained the labeled dose in {{coverage}} of drugs. No band was blocked ({{cov_blocked}} blocked). The median interval width was {{cov_median_width}}-fold, and the widest was {{cov_max_width}}-fold. For most children beyond infancy the maturation factor is close to 1, so the interval is very narrow. The interval does not describe how far a label may sit from a size-based prediction, and low coverage is the expected result.

# Discussion

In this pre-registered benchmark, adding published maturation curves to allometric scaling brought predicted doses closer to FDA-labeled doses in newborns and in children under 2 years. Across all ages there was no clear difference. This pattern fits the mechanism. Glomerular filtration and the enzymes modeled here are mostly mature by about 2 years (Figure 1), so beyond infancy PaedScale and A1 give nearly the same doses. Their differences there mostly reflect drugs whose labels depart from allometry for other reasons.

The comparison isolates the maturation term because A1 shares everything else with PaedScale. Allometry and body surface area scaling without maturation overpredicted newborn doses about two- to threefold. This matches the core concern that motivates maturation models [4, 8].

Two findings limit what can be claimed.

First, weight-linear scaling agreed with neonatal labels at least as well as PaedScale. A likely reason is that many neonatal and pediatric labels are written in mg/kg, and some give the adult the same mg/kg (the `mgkg_shared` pairs). For those pairs, weight-linear scaling matches the label by construction. More broadly, where a labeled pediatric dose was set by mg/kg convention rather than to match adult exposure, agreement with the label, the reference standard here, is not the same as matching exposure. A method that matches exposure better could then look worse against labels. This benchmark cannot tell these cases apart.

Second, the effect estimates are imprecise and depend on few drugs. H1 rests on nine drugs, three of which tie. The secondary Wilcoxon tests were not significant. The pre-specified sequence makes H1 and H2 confirmatory, but their size is uncertain.

The drugs where PaedScale did worse than A1 were mainly β-lactams and fluconazole (Figure 3). For β-lactams, matching daily exposure is only a proxy for time above the inhibitory concentration, and the engine flags it as such. The fluconazole label states that its pediatric regimens were chosen to match adult exposure, and they are higher than allometry predicts. The application flags this kind of discordance between engine and guideline.

## Limitations

- **Reference standard.** Labeled doses are a clinical reference, not measured exposure. Some come from pediatric pharmacokinetic studies, and some from convention.
- **Sample.** The sample is small (21 drugs, 46 pairs). The candidates were chosen by the authors, not by systematic search, and most are renally cleared anti-infectives. Only three drugs used an enzyme curve, and morphine is the source drug for the UGT2B7 curve. Sensitivity analysis S7 removes it.
- **Who did the work.** Curation, pairing and the analysis code were done by the study team with AI assistance (see the AI-use statement). They were not done by independent curators, though every value carries a verbatim quotation checked by a test.
- **Patients.** Each band was represented by median-weight virtual patients. There was no individual variability, obesity, critical illness or organ impairment.
- **Inputs.** The benchmark gives the engine label-derived inputs. It does not test the live retrieval and language-model layers, which need a separate evaluation.
- **Uncertainty interval.** The interval reflects maturation-parameter uncertainty only. Its 13% coverage shows it must not be read as a dose range.
- **Labels.** Only US FDA labels were used.

## Conclusions

Published maturation curves improved the agreement of size-scaled doses with FDA labels in newborns and children under 2 years, and not across all ages. Weight-linear scaling agreed with neonatal labels about as well. The open, pre-registered benchmark and its one-command reproduction are offered as a baseline for testing pediatric dose-extrapolation tools, including language-model systems. Clinical use of any such tool needs prospective evaluation against measured exposure.

# Declarations

**Code and data availability.** The source code, protocol, label snapshots, reference set, outputs and the manuscript build are in the PaedScale repository (https://github.com/heyiamnotacoder/paedscale), at commit {{engine_commit}} for the scored outputs.

**Use of AI tools.** The authors used an AI coding assistant, Claude (Anthropic), for software development, the benchmark code, label curation support and drafting this manuscript. The authors directed the work and are responsible for the content. The authors must check every statement, number and reference before submission. Every number in this manuscript is generated from the committed outputs by script.

**Funding.** [To be completed by the authors.]

**Competing interests.** [To be completed by the authors.]

**Ethics.** The study used only public drug labels and published growth references. No human participants or patient data were involved.

# References

1. Shah SS, Hall M, Goodman DM, et al. Off-label drug use in hospitalized children. Arch Pediatr Adolesc Med. 2007;161(3):282–290. doi:10.1001/archpedi.161.3.282. PMID 17339510.
2. Kaushal R, Bates DW, Landrigan C, et al. Medication errors and adverse drug events in pediatric inpatients. JAMA. 2001;285(16):2114–2120. doi:10.1001/jama.285.16.2114. PMID 11311101.
3. Costeff H. A simple empirical formula for calculating approximate surface area in children. Arch Dis Child. 1966;41(220):681–683. doi:10.1136/adc.41.220.681. PMID 5927924.
4. Anderson BJ, Holford NHG. Mechanism-based concepts of size and maturity in pharmacokinetics. Annu Rev Pharmacol Toxicol. 2008;48:303–332. doi:10.1146/annurev.pharmtox.48.113006.094708. PMID 17914927.
5. Rhodin MM, Anderson BJ, Peters AM, et al. Human renal function maturation: a quantitative description using weight and postmenstrual age. Pediatr Nephrol. 2009;24(1):67–76. doi:10.1007/s00467-008-0997-5. PMID 18846389.
6. Anderson BJ, Larsson P. A maturation model for midazolam clearance. Paediatr Anaesth. 2011;21(3):302–308. doi:10.1111/j.1460-9592.2010.03364.x. PMID 20704661.
7. Anand KJS, Anderson BJ, Holford NHG, et al. Morphine pharmacokinetics and pharmacodynamics in preterm and term neonates: secondary results from the NEOPAIN trial. Br J Anaesth. 2008;101(5):680–689. doi:10.1093/bja/aen248. PMID 18723857.
8. Calvier EAM, Krekels EHJ, Välitalo PAJ, et al. Allometric scaling of clearance in paediatric patients: when does the magic of 0.75 fade? Clin Pharmacokinet. 2017;56(3):273–285. doi:10.1007/s40262-016-0436-x. PMID 27510367.
9. Fenton TR, Kim JH. A systematic review and meta-analysis to revise the Fenton growth chart for preterm infants. BMC Pediatr. 2013;13:59. doi:10.1186/1471-2431-13-59. PMID 23601190.
10. WHO Multicentre Growth Reference Study Group. WHO Child Growth Standards: length/height-for-age, weight-for-age, weight-for-length, weight-for-height and body mass index-for-age. Methods and development. Geneva: World Health Organization; 2006.
11. Kuczmarski RJ, Ogden CL, Guo SS, et al. 2000 CDC growth charts for the United States: methods and development. Vital Health Stat 11. 2002;(246):1–190. PMID 12043359.
12. Coffman BL, Rios GR, King CD, Tephly TR. Human UGT2B7 catalyzes morphine glucuronidation. Drug Metab Dispos. 1997;25(1):1–4. PMID 9010622.
13. Barbier O, Turgeon D, Girard C, et al. 3'-azido-3'-deoxythimidine (AZT) is glucuronidated by human UDP-glucuronosyltransferase 2B7 (UGT2B7). Drug Metab Dispos. 2000;28(5):497–502. PMID 10772627.
14. International Council for Harmonisation. E11(R1): Addendum to clinical investigation of medicinal products in the pediatric population. 2017.
15. Efron B. Better bootstrap confidence intervals. J Am Stat Assoc. 1987;82(397):171–185.
16. Holm S. A simple sequentially rejective multiple test procedure. Scand J Stat. 1979;6(2):65–70.

# Supplementary Table S1. Excluded candidates

{{table_excluded}}
