"""Mechanical pre-filter for the external validation (benchmark/external/PROTOCOL.md).

An abstract is screened by hand only if it prints a clearance value: a number and a unit of
volume (L or mL) per time (h, min or day), in slash, "per", dot, "x", space or exponent notation.
A body-size unit (kg, m², 1.73 m², 70 kg) may sit before or after the time unit, brackets may
wrap the denominator, up to 40 characters of bracketed text (a CI, an SD) may sit between the
number and the unit, and the unit may come first in brackets ("CL (L/h) was 3.2"). A volume
alone (L/kg) does not match. Fixed before screening (Amendment 1); a change is an amendment.
"""
import re

_NUM = r"\d+(?:[.,]\d+)?"
_BRACKETED = r"(?:[\(\[][^\)\]]{0,40}[\)\]]\s*)?"
_VOL = r"(?:m?l|millilit(?:er|re)s?|lit(?:er|re)s?)"
_EXP = r"(?:\s*(?:\(\s*[-−]\s*1\s*\)|[-−]\s*1|⁻¹|\^\s*[-−]?1))?"
_SEP = r"\s*(?:/|·|⋅|\.|\*|×|\bx\b|\bper\b|\s)\s*\(?\s*"
_SIZE = r"(?:1\.73\s*m(?:2|²|\^2)?|70\s*kg|kg|m2|m²|m\^2)"
_TIME = r"(?:hours?|hrs?|h|minutes?|min|days?)(?![a-z])"
_UNIT = rf"{_VOL}{_EXP}{_SEP}(?:{_SIZE}{_EXP}{_SEP})?{_TIME}"
CLEARANCE_VALUE = re.compile(
    rf"{_NUM}\s*{_BRACKETED}{_UNIT}"          # 3.2 (95% CI 2.9-3.5) L/h
    rf"|\(\s*{_UNIT}[^)]{{0,20}}\)[^.;]{{0,30}}?{_NUM}",   # CL (L/h) was 3.2
    re.I)


def has_clearance_value(text: str) -> bool:
    return bool(CLEARANCE_VALUE.search(text or ""))
