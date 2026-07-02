"""Acute:Chronic Workload Ratio (ACWR) — injury-risk banding.

ACWR = (7-day rolling mean load) / (28-day rolling mean load), the
Gabbett-style monitoring ratio. Bands follow the commonly used envelope:

    < 0.80        undertrained   (detraining risk)
    0.80 - 1.30   sweet_spot
    1.30 - 1.50   caution
    > 1.50        danger         (spike — elevated soft-tissue injury risk)

Load input is any per-day scalar (total distance, HSR distance,
player_load_eq, session-RPE if entered manually). ACWR is only meaningful
once a chronic window exists: with fewer than `min_chronic_days` observed
days the result is flagged low-confidence and should be displayed greyed out,
never as a risk verdict.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

BANDS = (
    (0.80, "undertrained"),
    (1.30, "sweet_spot"),
    (1.50, "caution"),
    (float("inf"), "danger"),
)


@dataclass
class AcwrResult:
    acute_load: float
    chronic_load: float
    ratio: float | None
    band: str
    days_observed: int
    confidence: str

    def to_dict(self) -> dict:
        return asdict(self)


def _band(ratio: float) -> str:
    for upper, name in BANDS:
        if ratio < upper:
            return name
    return BANDS[-1][1]


def acwr(
    daily_loads: list[float] | np.ndarray,
    acute_days: int = 7,
    chronic_days: int = 28,
    min_chronic_days: int = 21,
) -> AcwrResult:
    """Compute ACWR from a per-day load series (oldest first, today last).

    Missing training days must be entered as 0.0 — a gap in the list is a
    gap in time and would silently shift the windows.
    """
    loads = np.asarray(daily_loads, dtype=float)
    if loads.ndim != 1 or len(loads) == 0:
        raise ValueError("daily_loads must be a non-empty 1-D series")
    if np.any(loads < 0):
        raise ValueError("daily loads cannot be negative")

    days = len(loads)
    acute = float(np.mean(loads[-acute_days:]))
    chronic = float(np.mean(loads[-chronic_days:]))

    if chronic <= 0.0:
        return AcwrResult(acute, chronic, None, "no_data", days, "low")

    ratio = acute / chronic
    confidence = "high" if days >= min_chronic_days else "low"
    return AcwrResult(acute, chronic, float(ratio), _band(ratio), days, confidence)
