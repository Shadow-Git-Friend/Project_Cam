"""Biological maturity context for youth sport assessment reports."""

from __future__ import annotations

from typing import Any


def calculate_maturity_offset(
    sex: str,
    age_years: float,
    standing_height_cm: float,
    sitting_height_cm: float,
    body_mass_kg: float,
) -> dict[str, Any]:
    """Estimate years from peak height velocity using Mirwald-style equations.

    Inputs use centimetres, kilograms, and decimal chronological age.
    The result is context for youth sport screening, not a diagnosis.
    """
    sex_norm = str(sex).lower()
    if sex_norm not in {"male", "female"}:
        raise ValueError("Mirwald maturity offset requires sex='male' or sex='female'")
    for name, value in {
        "age_years": age_years,
        "standing_height_cm": standing_height_cm,
        "sitting_height_cm": sitting_height_cm,
        "body_mass_kg": body_mass_kg,
    }.items():
        if value is None or float(value) <= 0:
            raise ValueError(f"{name} must be positive")

    age = float(age_years)
    standing = float(standing_height_cm)
    sitting = float(sitting_height_cm)
    mass = float(body_mass_kg)
    leg_length = standing - sitting
    if leg_length <= 0:
        raise ValueError("standing_height_cm must be greater than sitting_height_cm")

    weight_height_ratio = (mass / standing) * 100.0
    if sex_norm == "male":
        offset = (
            -9.236
            + 0.0002708 * (leg_length * sitting)
            - 0.001663 * (age * leg_length)
            + 0.007216 * (age * sitting)
            + 0.02292 * weight_height_ratio
        )
    else:
        offset = (
            -9.376
            + 0.0001882 * (leg_length * sitting)
            + 0.0022 * (age * leg_length)
            + 0.005841 * (age * sitting)
            - 0.002658 * (age * mass)
            + 0.07693 * weight_height_ratio
        )

    if offset < -0.5:
        status = "pre_phv"
    elif offset > 0.5:
        status = "post_phv"
    else:
        status = "circa_phv"

    return {
        "method": "Mirwald et al. 2002 maturity offset estimate",
        "sex": sex_norm,
        "age_years": round(age, 4),
        "standing_height_cm": round(standing, 4),
        "sitting_height_cm": round(sitting, 4),
        "leg_length_cm": round(leg_length, 4),
        "body_mass_kg": round(mass, 4),
        "maturity_offset_years": round(offset, 4),
        "age_at_phv_years": round(age - offset, 4),
        "maturity_status": status,
        "interpretation": _interpretation(offset),
    }


def maybe_calculate_maturity(
    sex: str | None,
    age_years: float | None,
    standing_height_cm: float | None,
    sitting_height_cm: float | None,
    body_mass_kg: float | None,
) -> dict[str, Any] | None:
    if not all(v is not None for v in (sex, age_years, standing_height_cm, sitting_height_cm, body_mass_kg)):
        return None
    if str(sex).lower() not in {"male", "female"}:
        return None
    return calculate_maturity_offset(
        sex=str(sex),
        age_years=float(age_years),
        standing_height_cm=float(standing_height_cm),
        sitting_height_cm=float(sitting_height_cm),
        body_mass_kg=float(body_mass_kg),
    )


def _interpretation(offset: float) -> str:
    if offset < -1.0:
        return "Athlete is estimated to be more than one year before peak height velocity; compare primarily against their own baseline."
    if offset < -0.5:
        return "Athlete is estimated to be before peak height velocity; maturity context should temper age-group comparisons."
    if offset <= 0.5:
        return "Athlete is estimated to be near peak height velocity; coordination and limb proportions may change quickly."
    return "Athlete is estimated to be after peak height velocity; continue using individual baseline trends."

