"""Biomechanics KPIs from 3D pose sequences (world frame, metres).

Builds on the same signal the assessment coach uses (triangulated COCO-17
joints); joint-angle conventions are shared with
`project_cam.assessment.kinematics.angle_degrees`, do not redefine them.

At the current 15-18 FPS rig, per-stride timing quantisation is ~±33 ms, so
ground-contact time is reported with that floor and stride cadence should be
averaged over >= 4 strides. At the planned 60 FPS global-shutter rig the same
code yields ±8 ms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class StrideMetrics:
    stride_count: int
    stride_length_m: float
    stride_length_cv: float
    cadence_hz: float
    ground_contact_time_s: float | None
    timing_resolution_s: float
    confidence: str

    def to_dict(self) -> dict:
        return asdict(self)


def asymmetry_index(left: float, right: float) -> float | None:
    """Symmetry index [%]: |L-R| / mean(L,R) * 100. 0 = perfectly symmetric.

    >10-15% on stride or force proxies is the conventional flag threshold.
    Returns None when the mean is ~0 (metric undefined).
    """
    mean = 0.5 * (left + right)
    if abs(mean) < 1e-9:
        return None
    return abs(left - right) / abs(mean) * 100.0


def _foot_strikes(
    ankle_z_m: np.ndarray, timestamps_s: np.ndarray, contact_band_m: float
) -> np.ndarray:
    """Indices where the ankle enters the contact band above its session minimum."""
    z = np.asarray(ankle_z_m, dtype=float)
    in_contact = z < (np.min(z) + contact_band_m)
    edges = np.flatnonzero(np.diff(in_contact.astype(int)) == 1) + 1
    if in_contact[0]:
        edges = np.concatenate(([0], edges))
    return edges


def stride_metrics(
    ankle_pos_m: np.ndarray,
    timestamps_s: np.ndarray,
    contact_band_m: float = 0.05,
    min_stride_interval_s: float = 0.35,
) -> StrideMetrics:
    """Stride length / cadence / ground-contact estimate for ONE foot.

    ankle_pos_m: (N, 3) world positions of one ankle, Z up, metres.
    A stride = same-foot strike to same-foot strike. Ground contact is the
    dwell time inside the contact band (a proxy, not a force plate).
    """
    pos = np.asarray(ankle_pos_m, dtype=float)
    t = np.asarray(timestamps_s, dtype=float)
    if pos.ndim != 2 or pos.shape[1] < 3 or len(pos) != len(t):
        raise ValueError("ankle_pos_m must be (N, 3) matching timestamps_s")
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.0

    strikes = _foot_strikes(pos[:, 2], t, contact_band_m)
    # Debounce: merge strikes closer than a physiological stride interval.
    kept: list[int] = []
    for idx in strikes:
        if not kept or (t[idx] - t[kept[-1]]) >= min_stride_interval_s:
            kept.append(int(idx))
    strikes = np.asarray(kept, dtype=int)

    if len(strikes) < 2:
        return StrideMetrics(0, 0.0, 0.0, 0.0, None, dt, "low")

    stride_vecs = pos[strikes[1:], :2] - pos[strikes[:-1], :2]
    lengths = np.linalg.norm(stride_vecs, axis=1)
    intervals = np.diff(t[strikes])
    mean_len = float(np.mean(lengths))
    cv = float(np.std(lengths) / mean_len) if mean_len > 1e-9 else 0.0

    # Ground contact: dwell inside the band after each kept strike.
    z = pos[:, 2]
    band = np.min(z) + contact_band_m
    contacts: list[float] = []
    for idx in strikes:
        j = idx
        while j + 1 < len(z) and z[j + 1] < band:
            j += 1
        contacts.append(float(t[j] - t[idx]))
    gct = float(np.mean(contacts)) if contacts else None

    confidence = "high" if len(strikes) >= 5 and dt <= 0.04 else "medium"
    return StrideMetrics(
        stride_count=len(strikes) - 1,
        stride_length_m=mean_len,
        stride_length_cv=cv,
        cadence_hz=float(1.0 / np.mean(intervals)),
        ground_contact_time_s=gct,
        timing_resolution_s=dt,
        confidence=confidence,
    )


def kick_foot_speed(
    foot_pos_m: np.ndarray,
    timestamps_s: np.ndarray,
    contact_time_s: float | None = None,
    window_s: float = 0.25,
) -> dict:
    """Peak foot speed [m/s] around ball contact, plus approach direction.

    If contact_time_s is None, the global speed peak is used (valid for an
    isolated kick clip). Approach angle is the foot-velocity heading at peak,
    in degrees, in the pitch XY plane.
    """
    pos = np.asarray(foot_pos_m, dtype=float)
    t = np.asarray(timestamps_s, dtype=float)
    vel = np.diff(pos, axis=0) / np.diff(t)[:, None]
    speed = np.linalg.norm(vel, axis=1)
    tv = t[:-1]

    if contact_time_s is not None:
        sel = np.abs(tv - contact_time_s) <= window_s
        if not np.any(sel):
            return {"peak_speed_mps": None, "approach_angle_deg": None, "confidence": "low"}
        idx = int(np.flatnonzero(sel)[np.argmax(speed[sel])])
    else:
        idx = int(np.argmax(speed))

    heading = float(np.degrees(np.arctan2(vel[idx, 1], vel[idx, 0])))
    dt = float(np.median(np.diff(t)))
    return {
        "peak_speed_mps": float(speed[idx]),
        "peak_time_s": float(tv[idx]),
        "approach_angle_deg": heading,
        # One-frame speed at peak is blur/undersampling-sensitive below 60 FPS.
        "confidence": "high" if dt <= 0.02 else "medium",
    }
