"""Volume-of-distribution correction for neonatal body composition and protein binding.

Neonates have a higher total body water fraction and lower plasma protein
binding than adults, which shifts Vd beyond what size-only allometry predicts.
This applies a simplified unbound-fraction correction (Oie-Benet style) on
top of the allometrically size-scaled volume.
"""

from app.pk.allometry import scale_volume


def corrected_volume(
    adult_volume_l: float,
    weight_kg: float,
    adult_protein_binding: float,
    child_protein_binding: float,
) -> float:
    """Size-scale Vd, then correct for the child's altered free (unbound) fraction.

    Lower protein binding in the child (higher free fraction) increases the
    apparent volume of distribution relative to the size-only prediction.
    """
    size_scaled_vd = scale_volume(adult_volume_l, weight_kg)
    fu_adult = 1 - adult_protein_binding
    fu_child = 1 - child_protein_binding
    return size_scaled_vd * (fu_child / fu_adult)
