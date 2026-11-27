"""The mechanical pre-filter of the external validation (benchmark/external/PROTOCOL.md)."""
import pytest

from benchmark.external.curation.prefilter import has_clearance_value


@pytest.mark.parametrize("text", [
    "Clearance was 0.103 L/h/kg in neonates.",
    "CL increased from 0.897 l h(-1) 70 kg(-1) at 24 weeks PMA",
    "mean clearance of 2.4 mL/min/kg",
    "CL = 1.2 L/hr",
    "clearance 105 ml/min/1.73 m2",
    "total body clearance was 0.12 L·h−1·kg−1",
    "clearance (CL) 3.79 l h-1 70 kg-1",
    "clearance was 4.5 mL min-1 kg-1",
    "CL 0.25 L per h per kg",
    "clearance of 1.1 L/h per 70 kg",
    # Amendment 1: weight or area before time, brackets, text between number and unit,
    # unit before number, other separators and spelled-out units.
    "CL was 0.1 L/kg/h",
    "clearance 2.1 ml/kg/h",
    "clearance 3 mL/kg/min",
    "CL 0.2 L·kg⁻¹·h⁻¹",
    "clearance 4 ml kg-1 min-1",
    "CL 0.1 L/(h·kg)",
    "CL 2 mL/(min*kg)",
    "CL was 3.2 (95% CI 2.9-3.5) L/h",
    "clearance 3.2 (SD 0.4) L/h",
    "clearance 3.2 [2.9, 3.5] L/h",
    "CL (L/h) was 3.2",
    "clearance 1.2 L.h-1",
    "clearance 1.2 l x h-1",
    "clearance was 95 milliliters per minute",
    "clearance of 30 L/day",
])
def test_a_clearance_with_units_passes(text):
    assert has_clearance_value(text)


@pytest.mark.parametrize("text", [
    "Clearance increased with postmenstrual age.",          # no number
    "Creatinine 0.5 mg/dL; doses of 15 mg/kg every 8 h.",   # numbers, no clearance unit
    "volume of distribution was 0.58 L/kg",                 # L/kg is a volume, not a clearance
    "trough 10 mg/L at 12 h",
    "Vd 0.6 (0.5-0.7) L/kg in 30 infants aged 2 (1-6) months",   # bracketed text, still a volume
])
def test_text_without_a_clearance_value_is_screened_out(text):
    assert not has_clearance_value(text)


@pytest.mark.parametrize("text", [
    "clearance 4 ml kg–1 min–1",       # en dash exponent
    "CL 0.5 L/kg/d",
    "clearance 30 dL/h",
])
def test_amendment_2_units_pass(text):
    assert has_clearance_value(text)


def test_long_runs_of_whitespace_do_not_stall_the_filter():
    import time
    t = time.perf_counter()
    has_clearance_value("1 l" + " " * 5000 + "x")
    assert time.perf_counter() - t < 0.5
