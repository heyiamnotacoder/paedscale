"""Case intake: deterministic first-pass parse of a free-text clinical query.

Matches the whiteboard's first box (USER → DRUG + AGE + WT + EDGE_CASE). Python does a cheap,
deterministic extraction of the obvious covariates, a best-guess drug name, and the organ-impaired /
edge-case flags. The orchestrator (LLM) refines and fills gaps — this seed keeps the prompt small
and lets the happy path skip the agentic web loop.
"""

import re

# Kept for the (trimmed) orchestrator prompt / covariate contract.
COVARIATE_SPEC = """\
Covariates: drug_name, indication, route, weight_kg, height_cm, sex,
gestational_age_weeks, postnatal_age_weeks, pma_weeks (= GA + postnatal),
serum_creatinine_mg_dl / egfr_ml_min_1_73, child_pugh_score, albumin_g_dl.
Leave unknowns null; record anything you defaulted in assumed_defaults.
"""

INTAKE_INSTRUCTIONS = """\
A deterministic parse of the query is provided as `parsed`. Trust it for the numbers it found;
correct it only where clearly wrong, and fill gaps with age-typical population defaults (flagging
each in assumed_defaults). Never block on a missing covariate.
"""

_EDGE_KEYWORDS = (
    "preterm", "premature", "prematurity", "ecmo", "dialysis", "crrt", "haemofiltration",
    "hemofiltration", "aki", "acute kidney", "renal impair", "renal failure", "hepatic impair",
    "liver disease", "liver failure", "cirrhosis", "obes", "transplant", "rare", "unlicensed",
    "off-label", "off label", "no guideline", "cystic fibrosis", "burn", "elbw", "vlbw",
    "extremely low birth weight", "very low birth weight", "metabolic", "interaction",
)
_ORGAN_KEYWORDS = (
    "renal impair", "renal failure", "hepatic impair", "liver disease", "liver failure",
    "cirrhosis", "aki", "acute kidney", "dialysis", "crrt",
)


def _num(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else None


def _age_to_weeks(text: str) -> float | None:
    """Postnatal age in weeks from phrases like '2 days old', '3-week-old', '5 months', '2 yo'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[- ]?(day|week|wk|month|mo|year|yr|yo)s?[- ]?old", text)
    if not m:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(day|week|wk|month|mo|year|yr|yo)s?\b", text)
    if not m:
        return None
    val, unit = float(m.group(1)), m.group(2)
    if unit in ("day",):
        return val / 7.0
    if unit in ("week", "wk"):
        return val
    if unit in ("month", "mo"):
        return val * 4.345
    return val * 52.14  # year/yr/yo


def _gestational_age(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+\d+)?\s*(?:week|wk)s?\s*(?:ga|gestation|gestational|corrected)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"\bga\s*(?:of\s*)?(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"born\s+at\s+(\d+(?:\.\d+)?)\s*(?:week|wk)", text)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)[- ]?week(?:er)\b", text)
    if m:
        return float(m.group(1))
    return None


_LEADINS = (
    "starting dose of", "loading dose of", "maintenance dose of", "dose of", "dosing for",
    "dosing of", "what is the", "what's the", "calculate", "how much", "recommend", "give",
)
_STOP = {"a", "an", "the", "for", "in", "of", "to", "iv", "im", "po", "oral", "dose", "starting"}


def _guess_drug(text: str) -> str | None:
    low = text.strip().lower()
    for lead in _LEADINS:
        if lead in low:
            low = low.split(lead, 1)[1]
            break
    for tok in re.split(r"[\s,;:()]+", low.strip()):
        tok = tok.strip()
        if len(tok) >= 4 and tok.isalpha() and tok not in _STOP:
            return tok
    return None


def parse(query: str) -> dict:
    """Free-text → covariates + organ_impaired + edge_case + drug_name (best effort)."""
    text = (query or "").lower()
    assumed: list[str] = []

    weight = _num(r"(\d+(?:\.\d+)?)\s*kg", text)
    height = _num(r"(\d+(?:\.\d+)?)\s*cm", text)
    scr = None
    if "creatinine" in text or "scr" in text:
        scr = _num(r"(\d+(?:\.\d+)?)\s*mg\s*/\s*dl", text)
    egfr = _num(r"egfr\s*(?:of\s*)?(\d+(?:\.\d+)?)", text) or _num(r"crcl\s*(?:of\s*)?(\d+(?:\.\d+)?)", text)
    child_pugh = _num(r"child[- ]?pugh\s*(?:score\s*)?(\d+)", text)
    albumin = _num(r"albumin\s*(?:of\s*)?(\d+(?:\.\d+)?)", text)

    postnatal = _age_to_weeks(text)
    ga = _gestational_age(text)
    if ga is None and postnatal is not None:
        ga = 40.0  # term default
        assumed.append("gestational_age_weeks=40 (term default)")
    pma = (ga + postnatal) if (ga is not None and postnatal is not None) else None

    organ_impaired = any(k in text for k in _ORGAN_KEYWORDS)
    if child_pugh is not None and child_pugh >= 7:
        organ_impaired = True
    edge_case = organ_impaired or any(k in text for k in _EDGE_KEYWORDS)

    covariates = {
        "drug_name": _guess_drug(text),
        "weight_kg": weight,
        "height_cm": height,
        "gestational_age_weeks": ga,
        "postnatal_age_weeks": postnatal,
        "pma_weeks": pma,
        "serum_creatinine_mg_dl": scr,
        "egfr_ml_min_1_73": egfr,
        "child_pugh_score": int(child_pugh) if child_pugh is not None else None,
        "albumin_g_dl": albumin,
        "assumed_defaults": assumed,
    }
    return {
        "covariates": covariates,
        "drug_name": covariates["drug_name"],
        "organ_impaired": organ_impaired,
        "edge_case": edge_case,
    }


def merge_overrides(covariates: dict, overrides: dict | None) -> dict:
    """Structured overrides from the request win over the parsed covariates."""
    if not overrides:
        return covariates
    merged = dict(covariates)
    merged.update({k: v for k, v in overrides.items() if v is not None})
    return merged
