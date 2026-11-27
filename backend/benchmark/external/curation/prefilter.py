"""Mechanical pre-filter for the external validation (benchmark/external/PROTOCOL.md).

An abstract is screened by hand only if it prints a number followed by a clearance unit: a
volume (L or mL) per unit time (h or min), in slash, "per", middle-dot, space or exponent
notation, optionally per kg, per 70 kg or per 1.73 m². Volumes alone (L/kg) do not match.
Fixed before screening; changing it is a protocol amendment.
"""
import re

_NUM = r"\d+(?:[.,]\d+)?"
_VOL = r"(?:m?l|litres?|liters?)"
_SEP = r"\s*(?:/|·|⋅|\bper\s+|\s)\s*"
_TIME = r"(?:hours?|hrs?|h|minutes?|min)(?![a-z])"
CLEARANCE_VALUE = re.compile(rf"{_NUM}\s*{_VOL}{_SEP}{_TIME}", re.I)


def has_clearance_value(text: str) -> bool:
    return bool(CLEARANCE_VALUE.search(text or ""))
