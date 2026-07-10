"""Volume-of-distribution correction for neonatal body composition and protein binding.

Neonates have a higher total body water fraction and lower plasma protein
binding than adults, which shifts Vd beyond what size-only allometry predicts.
This applies a simplified unbound-fraction correction (Oie-Benet style) on
top of the allometrically size-scaled volume.
"""

from app.pk.allometry import scale_volume

# Reference adult serum albumin (g/dL) for scaling protein binding.
REFERENCE_ADULT_ALBUMIN_G_DL = 4.0


def protein_binding_from_albumin(
    adult_protein_binding: float,
    child_albumin_g_dl: float,
    adult_albumin_g_dl: float = REFERENCE_ADULT_ALBUMIN_G_DL,
) -> float:
    """Estimate a child's bound fraction from albumin (for albumin-bound drugs).

    Neonates have lower albumin, so the *bound* fraction falls roughly in
    proportion to the albumin ratio: bound_child ≈ bound_adult · (alb_c/alb_a),
    capped in [0, 1). The unbound (active) fraction rises accordingly. This is a
    first-order approximation for a starting estimate, not a binding model.
    """
    if child_albumin_g_dl <= 0 or adult_albumin_g_dl <= 0:
        raise ValueError("albumin values must be positive")
    bound = adult_protein_binding * (child_albumin_g_dl / adult_albumin_g_dl)
    return max(0.0, min(bound, 0.999))


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
