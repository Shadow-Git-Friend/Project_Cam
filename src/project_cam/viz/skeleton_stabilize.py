"""Display-only skeletal rigidity for the live 3D viewers.

Human bones do not change length, but a per-joint smoothing/prediction chain
treats every COCO joint independently, so triangulation noise and per-joint
Kalman leads make the rendered bones "breathe" by tens of mm — the skeleton
reads as liquid/rubbery. This module learns each athlete's bone lengths from
confident live triangulations (robust running median, plausibility-bounded)
and softly clamps the *displayed* skeleton so limb bones stay near the
learned lengths.

Strictly display-only by construction: callers apply it to the render buffer
(``joints_display``) after all smoothing. It must never be applied to
``joints_state``, the UDP payload, or anything the drill scoring / BLM /
firing-line safety chain consumes. It does not touch any protected geometry
function.

Design rules (from the 2026-07-17 adversarial review):
- Learn only from same-tick triangulated pairs the caller pre-gates (fresh,
  slow-moving, not touched by the L/R pair split that frame); the median plus
  hard per-bone plausibility bounds keep a poisoned window from ever locking
  an absurd length.
- Clamp is SOFT (overflow beyond the tolerance band is compressed, not cut)
  so a bone riding the band never sticks to a wall, and a genuinely wrong
  joint still renders visibly wrong instead of being fabricated as healthy.
- Clamp only bones whose BOTH endpoints are fresh (caller passes the mask):
  correcting a stale, EMA-held child against a moving parent would invent a
  confident wrong-position joint — worse than breathing.
- The symmetric width clamp never reduces a pair below ``min_pair_sep_mm``
  (the L/R split's own merge threshold), so it cannot fight the split's
  effort to keep merged legs apart.
"""

from __future__ import annotations

from collections import deque

import numpy as np

# Limb chains walked root-outward: the parent end of each bone is treated as
# the anchor and only the child is moved along the current bone direction.
# Shoulders/hips are the best-conditioned joints on the rig (seen by the most
# cameras, least self-occlusion), which is what makes them safe anchors.
LIMB_CHAINS = (
    (5, 7, 9),      # left shoulder -> elbow -> wrist
    (6, 8, 10),     # right shoulder -> elbow -> wrist
    (11, 13, 15),   # left hip -> knee -> ankle
    (12, 14, 16),   # right hip -> knee -> ankle
)

# Bilateral pairs clamped symmetrically about their midpoint (both endpoints
# move, the midpoint stays) so neither side is privileged.
WIDTH_PAIRS = (
    (5, 6),         # shoulder width
    (11, 12),       # hip width
)

# Hard plausibility bounds (mm) on LEARNED lengths — samples outside never
# enter the bank, so an L/R-merge episode cannot lock e.g. a 40 mm "femur".
# Ranges are generous (youth academy athletes through large adults).
BONE_PLAUSIBLE_MM = {
    (5, 6): (220.0, 600.0),
    (11, 12): (100.0, 450.0),
    (5, 7): (150.0, 450.0),
    (6, 8): (150.0, 450.0),
    (7, 9): (130.0, 420.0),
    (8, 10): (130.0, 420.0),
    (11, 13): (220.0, 620.0),
    (12, 14): (220.0, 620.0),
    (13, 15): (220.0, 620.0),
    (14, 16): (220.0, 620.0),
}


def default_bones():
    """All bones the bank should learn: widths + limb chain segments."""
    bones = list(WIDTH_PAIRS)
    for chain in LIMB_CHAINS:
        bones.extend(zip(chain[:-1], chain[1:]))
    return tuple(bones)


class BoneLengthBank:
    """Robust per-bone length estimate (mm) for one athlete.

    Feed it caller-gated 3D states via :meth:`observe`; a bone's length
    "locks" (becomes available) once ``min_samples`` measurements are banked,
    and keeps adapting as the rolling window slides. The median is
    insensitive to the very outliers (label mixes, single-camera flings) it
    exists to fix.
    """

    def __init__(self, bones=None, window=150, min_samples=45):
        self.bones = tuple(bones) if bones is not None else default_bones()
        self.window = int(window)
        self.min_samples = max(1, int(min_samples))
        self._samples = {bone: deque(maxlen=self.window) for bone in self.bones}

    def reset(self):
        """Forget everything — call when the tracked identity changes."""
        for dq in self._samples.values():
            dq.clear()

    def observe(self, joints, conf=None, cams=None, min_conf=0.35, min_cams=2,
                exclude_joints=frozenset()):
        """Bank lengths from one 3D state (17x3 mm array, NaN = missing).

        A bone is sampled only when both endpoints are finite, outside
        ``exclude_joints`` (caller passes joints the L/R split rewrote this
        frame), pass the confidence / camera-count gates (``conf``/``cams``
        as None skips a gate), and the length lies inside its plausibility
        bounds. Returns the number of bones sampled this call.
        """
        joints = np.asarray(joints, dtype=np.float64)
        banked = 0
        for bone in self.bones:
            a, b = bone
            if a in exclude_joints or b in exclude_joints:
                continue
            pa, pb = joints[a], joints[b]
            if not (np.isfinite(pa).all() and np.isfinite(pb).all()):
                continue
            if conf is not None and (conf[a] < min_conf or conf[b] < min_conf):
                continue
            if cams is not None and (cams[a] < min_cams or cams[b] < min_cams):
                continue
            length = float(np.linalg.norm(pb - pa))
            lo, hi = BONE_PLAUSIBLE_MM.get(bone, (1e-6, float("inf")))
            if not (lo <= length <= hi):
                continue
            self._samples[bone].append(length)
            banked += 1
        return banked

    def length(self, bone):
        """Learned length in mm, or None while the bone is still unlocked."""
        dq = self._samples.get(bone)
        if dq is None or len(dq) < self.min_samples:
            return None
        return float(np.median(dq))

    def n_locked(self):
        return sum(1 for bone in self.bones if self.length(bone) is not None)


def _soft_clamp_len(length, learned, tol, soft):
    """Soft tolerance band: inside [L(1-tol), L(1+tol)] untouched; overflow
    beyond the band is compressed by ``soft`` (0 = hard clamp, 1 = no clamp).
    Keeps the display responsive at the band edge and keeps a genuinely wrong
    joint visibly wrong instead of fabricating a healthy bone."""
    lo = learned * (1.0 - tol)
    hi = learned * (1.0 + tol)
    if length > hi:
        return hi + soft * (length - hi)
    if length < lo:
        return lo - soft * (lo - length)
    return length


def _fresh(fresh_mask, j):
    return fresh_mask is None or bool(fresh_mask[j])


def _cap_restore_gain(target, length, max_gain):
    """Bound how far a COLLAPSED bone may be rescaled in one step.

    Correcting a bone's length rescales the measured direction by
    ``target/length``, which also rescales that direction's error. The
    direction of a nearly-collapsed bone is almost pure triangulation noise,
    so the unbounded form amplifies it without limit: against a learned
    440 mm tibia the gain is 2.0x at a 132 mm measurement but 11x at 20 mm and
    106x at 2 mm, turning 4 mm of transverse noise into 424 mm of rendered
    jitter. That is the opposite of the module's purpose in exactly the
    L/R-merge regime it exists to help. Capping the gain still restores the
    bone toward its band (over successive frames, as the measurement
    improves) while keeping a genuinely collapsed joint visibly collapsed.
    """
    if length <= 0.0 or target <= length:
        return target
    return min(target, length * max_gain)


def stabilize_display_skeleton(joints, bank, tol=0.13, soft=0.45,
                               fresh_mask=None, min_pair_sep_mm=100.0,
                               max_restore_gain=2.5):
    """Softly clamp displayed bone lengths toward the learned band, in place.

    ``joints`` is the 17x3 display buffer (mm, NaN = missing). Width pairs
    are clamped symmetrically first (fixing the shoulder/hip anchors), then
    each limb chain is walked outward moving only the child joint along the
    *current* bone direction — direction (pose) is always preserved, only the
    length is corrected, so a genuinely lifted leg stays lifted. Skipped:
    bones without a locked length, with a missing endpoint, or with a stale
    endpoint (``fresh_mask``, boolean per joint — a stale EMA-held child must
    not be re-fabricated at a "plausible" position).

    Returns the number of bones that were actually adjusted.
    """
    corrected = 0
    for a, b in WIDTH_PAIRS:
        learned = bank.length((a, b))
        pa, pb = joints[a], joints[b]
        if learned is None or not (np.isfinite(pa).all() and np.isfinite(pb).all()):
            continue
        if not (_fresh(fresh_mask, a) and _fresh(fresh_mask, b)):
            continue
        vec = pb.astype(np.float64) - pa.astype(np.float64)
        length = float(np.linalg.norm(vec))
        if length <= 1e-6:
            continue
        target = _cap_restore_gain(
            _soft_clamp_len(length, learned, tol, soft), length, max_restore_gain)
        # Never pull a bilateral pair closer than the L/R split's merge
        # threshold — merged-leg recovery must not be squeezed back together.
        if target < length:
            target = max(target, min_pair_sep_mm)
            if target >= length:
                continue
        if abs(target - length) < 1e-9:
            continue
        mid = 0.5 * (pa.astype(np.float64) + pb.astype(np.float64))
        half = vec / length * (0.5 * target)
        joints[a] = (mid - half).astype(joints.dtype)
        joints[b] = (mid + half).astype(joints.dtype)
        corrected += 1
    for chain in LIMB_CHAINS:
        for a, b in zip(chain[:-1], chain[1:]):
            learned = bank.length((a, b))
            pa, pb = joints[a], joints[b]
            if learned is None or not (np.isfinite(pa).all() and np.isfinite(pb).all()):
                continue
            if not (_fresh(fresh_mask, a) and _fresh(fresh_mask, b)):
                continue
            vec = pb.astype(np.float64) - pa.astype(np.float64)
            length = float(np.linalg.norm(vec))
            if length <= 1e-6:
                continue
            target = _cap_restore_gain(
                _soft_clamp_len(length, learned, tol, soft), length, max_restore_gain)
            if abs(target - length) < 1e-9:
                continue
            joints[b] = (pa.astype(np.float64) + vec / length * target).astype(joints.dtype)
            corrected += 1
    return corrected
