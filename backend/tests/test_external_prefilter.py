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
])
def test_a_clearance_with_units_passes(text):
    assert has_clearance_value(text)


@pytest.mark.parametrize("text", [
    "Clearance increased with postmenstrual age.",          # no number
    "Creatinine 0.5 mg/dL; doses of 15 mg/kg every 8 h.",   # numbers, no clearance unit
    "volume of distribution was 0.58 L/kg",                 # L/kg is a volume, not a clearance
    "trough 10 mg/L at 12 h",
])
def test_text_without_a_clearance_value_is_screened_out(text):
    assert not has_clearance_value(text)
