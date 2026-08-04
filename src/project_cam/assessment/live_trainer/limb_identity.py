"""Left/right leg identity lock for supine leg-raise tracking.

When an athlete lies down and the legs come close or cross, a generic pose model
can swap the left/right labels frame-to-frame. That swap makes the 3D skeleton
flicker and corrupts per-side metrics. This tracker re-validates the model's
labels each frame using temporal continuity (a leg does not teleport) plus an
optional segment-length prior, with hysteresis so genuine slow motion is tracked
but transient label noise does not flip identity.

Pure geometry over 3D points; no camera stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from .limb_constraints import LegSegmentPrior, _pt, segment_length_error


@dataclass(frozen=True)
class LegPose:
    """One leg's hip/knee/ankle as 3D points (any may be None)."""

    hip: Optional[np.ndarray] = None
    knee: Optional[np.ndarray] = None
    ankle: Optional[np.ndarray] = None

    @staticmethod
    def of(hip=None, knee=None, ankle=None) -> "LegPose":
        return LegPose(_pt(hip), _pt(knee), _pt(ankle))

    def is_empty(self) -> bool:
        return self.hip is None and self.knee is None and self.ankle is None


@dataclass(frozen=True)
class IdentityResult:
    left: LegPose
    right: LegPose
    swapped: bool
    status: str  # "cold_start" | "locked" | "ambiguous"
    keep_cost: Optional[float]
    swap_cost: Optional[float]


def _continuity_cost(pose: LegPose, prev: LegPose) -> Optional[float]:
    """Mean displacement of a candidate leg from the previous frame's leg.

    Ankle dominates (it moves most in a leg raise); knee is a fallback. Returns
    None when there is nothing comparable, so a missing joint never fabricates a
    cost that would force a swap.
    """
    if pose is None or prev is None:
        return None
    terms = []
    if pose.ankle is not None and prev.ankle is not None:
        terms.append(float(np.linalg.norm(pose.ankle - prev.ankle)))
    if pose.knee is not None and prev.knee is not None:
        terms.append(float(np.linalg.norm(pose.knee - prev.knee)))
    if not terms:
        return None
    return float(np.mean(terms))


def _pair_cost(a, pa, b, pb) -> Optional[float]:
    ca = _continuity_cost(a, pa)
    cb = _continuity_cost(b, pb)
    parts = [c for c in (ca, cb) if c is not None]
    if not parts:
        return None
    return float(sum(parts))


class LimbIdentityTracker:
    """Stateful left/right leg identity lock with swap hysteresis.

    Call :meth:`resolve` each frame with the pose model's labelled left/right
    legs. The tracker corrects swaps relative to its own history, requiring the
    swapped hypothesis to beat the kept hypothesis by ``swap_margin_mm`` before
    flipping. ``lock_after`` consistent frames promote the status to ``locked``.
    """

    def __init__(
        self,
        *,
        swap_margin_mm: float = 80.0,
        lock_after: int = 5,
        prior_left: Optional[LegSegmentPrior] = None,
        prior_right: Optional[LegSegmentPrior] = None,
        segment_penalty_mm: float = 300.0,
    ):
        self.swap_margin_mm = swap_margin_mm
        self.lock_after = lock_after
        self.prior_left = prior_left
        self.prior_right = prior_right
        self.segment_penalty_mm = segment_penalty_mm
        self._prev_left: Optional[LegPose] = None
        self._prev_right: Optional[LegPose] = None
        self._stable = 0
        self._swaps = 0

    @property
    def swap_count(self) -> int:
        return self._swaps

    def reset(self) -> None:
        self._prev_left = self._prev_right = None
        self._stable = 0
        self._swaps = 0

    def _segment_penalty(self, left: LegPose, right: LegPose) -> float:
        """Penalty (mm-equivalent) for assignments inconsistent with priors."""
        pen = 0.0
        for pose, prior in ((left, self.prior_left), (right, self.prior_right)):
            if prior is None or not prior.reliable:
                continue
            err = segment_length_error(prior, pose.hip, pose.knee, pose.ankle)
            if err is not None and err > prior.tolerance:
                pen += self.segment_penalty_mm
        return pen

    def resolve(self, left_cand: LegPose, right_cand: LegPose) -> IdentityResult:
        # Cold start: trust the labels, seed history.
        if self._prev_left is None and self._prev_right is None:
            self._prev_left, self._prev_right = left_cand, right_cand
            self._stable = 1
            return IdentityResult(left_cand, right_cand, False, "cold_start", None, None)

        keep = _pair_cost(left_cand, self._prev_left, right_cand, self._prev_right)
        swap = _pair_cost(right_cand, self._prev_left, left_cand, self._prev_right)

        keep_total = keep
        swap_total = swap
        if keep is not None:
            keep_total = keep + self._segment_penalty(left_cand, right_cand)
        if swap is not None:
            swap_total = swap + self._segment_penalty(right_cand, left_cand)

        do_swap = False
        if keep_total is not None and swap_total is not None:
            do_swap = swap_total + self.swap_margin_mm < keep_total

        if do_swap:
            left, right = right_cand, left_cand
            self._swaps += 1
            self._stable = 1
            status = "ambiguous"
        else:
            left, right = left_cand, right_cand
            self._stable += 1
            status = "locked" if self._stable >= self.lock_after else "ambiguous"

        # Update history only with the joints actually present, so a one-frame
        # dropout doesn't erase the reference position.
        self._prev_left = self._merge_history(self._prev_left, left)
        self._prev_right = self._merge_history(self._prev_right, right)
        return IdentityResult(left, right, do_swap, status, keep_total, swap_total)

    @staticmethod
    def _merge_history(prev: Optional[LegPose], cur: LegPose) -> LegPose:
        if prev is None:
            return cur
        return LegPose(
            hip=cur.hip if cur.hip is not None else prev.hip,
            knee=cur.knee if cur.knee is not None else prev.knee,
            ankle=cur.ankle if cur.ankle is not None else prev.ankle,
        )
