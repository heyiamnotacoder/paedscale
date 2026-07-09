"""Size scaling per the standardised '70 kg' allometric framework.

Clearance scales with weight to the 0.75 power; volume of distribution
scales roughly linearly (power 1.0). See concept doc: "Allometric scaling — size".
"""

CLEARANCE_EXPONENT = 0.75
VOLUME_EXPONENT = 1.0
REFERENCE_ADULT_WEIGHT_KG = 70.0


def scale_clearance(
    adult_clearance_l_per_h: float,
    weight_kg: float,
    reference_weight_kg: float = REFERENCE_ADULT_WEIGHT_KG,
) -> float:
    """Allometrically scale adult clearance to a child's body size (size effect only)."""
    return adult_clearance_l_per_h * (weight_kg / reference_weight_kg) ** CLEARANCE_EXPONENT


def scale_volume(
    adult_volume_l: float,
    weight_kg: float,
    reference_weight_kg: float = REFERENCE_ADULT_WEIGHT_KG,
) -> float:
    """Allometrically scale adult volume of distribution to a child's body size."""
    return adult_volume_l * (weight_kg / reference_weight_kg) ** VOLUME_EXPONENT
