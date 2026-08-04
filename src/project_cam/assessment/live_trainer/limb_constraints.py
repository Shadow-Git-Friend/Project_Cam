"""Segment-length priors for supine leg-raise tracking.

Generic RGB pose models are weaker on lying poses: a knee or ankle can flicker,
jump to the other leg, or be visible in only one camera. A simple, strong prior
helps -- a person's thigh and shin lengths are (near) constant within a session.
This module estimates those lengths from a short calibration hold and then scores
each frame's hip/knee/ankle triple against them, so an anatomically impossible
reconstruction can be rejected before it pollutes the angle estimate.

Pure geometry over 3D points (mm). No camera stack, no model weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import List, Optional, Sequence

import numpy as np


def _pt(value) -> Optional[np.ndarray]:
    if value is None:
        return None
    try:
        p = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if p.shape[0] < 3 or not np.isfinite(p[:3]).all():
        return None
    return p[:3]


def segment_length(a, b) -> Optional[float]:
    """Euclidean distance between two 3D points, or None if either is missing."""
    pa, pb = _pt(a), _pt(b)
    if pa is None or pb is None:
        return None
    return float(np.linalg.norm(pa - pb))


@dataclass(frozen=True)
class LegSegmentPrior:
    """Per-leg thigh (hip->knee) and shin (knee->ankle) length priors, in mm.

    ``tolerance`` is the fractional deviation allowed before a frame's geometry is
    rejected (0.25 = +/-25 %). ``samples`` records how many calibration frames the
    estimate came from -- a prior built from too few frames is flagged unreliable.
    """

    thigh_mm: float
    shin_mm: float
    tolerance: float = 0.25
    samples: int = 0

    @property
    def reliable(self) -> bool:
        return self.samples >= 5 and self.thigh_mm > 0 and self.shin_mm > 0


def calibrate_segment_lengths(
    triples: Sequence[tuple],
    *,
    tolerance: float = 0.25,
) -> Optional[LegSegmentPrior]:
    """Estimate thigh/shin length from ``(hip, knee, ankle)`` triples.

    Uses the median over the calibration hold so a few bad frames don't skew the
    prior. Returns None if no triple yields both segments.
    """
    thighs: List[float] = []
    shins: List[float] = []
    for hip, knee, ankle in triples:
        t = segment_length(hip, knee)
        s = segment_length(knee, ankle)
        if t is not None and s is not None and t > 0 and s > 0:
            thighs.append(t)
            shins.append(s)
    if not thighs:
        return None
    return LegSegmentPrior(
        thigh_mm=float(median(thighs)),
        shin_mm=float(median(shins)),
        tolerance=tolerance,
        samples=len(thighs),
    )


def segment_length_error(
    prior: LegSegmentPrior, hip, knee, ankle
) -> Optional[float]:
    """Max fractional deviation of this frame's segments from the prior.

    Returns the larger of the thigh and shin relative errors, or None if either
    segment can't be measured this frame.
    """
    t = segment_length(hip, knee)
    s = segment_length(knee, ankle)
    if t is None or s is None:
        return None
    if prior.thigh_mm <= 0 or prior.shin_mm <= 0:
        return None
    thigh_err = abs(t - prior.thigh_mm) / prior.thigh_mm
    shin_err = abs(s - prior.shin_mm) / prior.shin_mm
    return float(max(thigh_err, shin_err))


def accept_by_segment_prior(
    prior: Optional[LegSegmentPrior], hip, knee, ankle
) -> bool:
    """True if the frame's leg geometry is consistent with the prior.

    With no (or unreliable) prior we do not reject -- the prior is a guard, not a
    gate, so a missing calibration never silently blanks the track. With a prior,
    geometry beyond ``tolerance`` is rejected.
    """
    if prior is None or not prior.reliable:
        return True
    err = segment_length_error(prior, hip, knee, ankle)
    if err is None:
        return True
    return err <= prior.tolerance
