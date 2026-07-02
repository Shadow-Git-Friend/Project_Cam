"""Physical / external-load KPIs from pitch-frame player trajectories.

Replaces the GPS-vest metric set (Catapult/STATSports style) using camera
tracking only. Input is a player's pitch-plane trajectory in metres with
per-sample timestamps; output is the standard external-load family with
first-order uncertainty propagated from the tracking noise.

Speed-zone thresholds follow the common elite-football convention
(e.g. FIFA/EPL reporting): high-speed running > 19.8 km/h, sprinting
> 25.2 km/h. Acceleration events use the > 2.5 m/s^2 convention.

Metabolic power follows di Prampero / Osgnach et al. 2010 ("Energy cost and
metabolic power in elite soccer"): the energy cost of accelerated running on
flat ground equals the cost of uphill running at the "equivalent slope"
ES = a/g, scaled by the "equivalent mass" EM = sqrt(ES^2 + 1):

    EC(ES) = (155.4*ES^5 - 30.4*ES^4 - 43.3*ES^3 + 46.3*ES^2 + 19.5*ES + 3.6) * EM
    P_met  = EC * v            [W/kg]

"PlayerLoad equivalent" is a camera-derived analogue of the accelerometer
PlayerLoad (sum of acceleration-change magnitude / 100). It correlates with,
but is not identical to, the trademarked vest metric — report it as
`player_load_eq`, never as PlayerLoad.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

G = 9.81
HSR_THRESHOLD_KMH = 19.8
SPRINT_THRESHOLD_KMH = 25.2
ACCEL_THRESHOLD_MPS2 = 2.5
MPS_TO_KMH = 3.6


@dataclass
class Event:
    """One contiguous above-threshold episode (sprint, accel, decel)."""

    start_s: float
    end_s: float
    duration_s: float
    distance_m: float
    peak_value: float


@dataclass
class PhysicalLoadSummary:
    duration_s: float
    n_samples: int
    total_distance_m: float
    total_distance_sigma_m: float
    hsr_distance_m: float
    sprint_distance_m: float
    max_speed_kmh: float
    speed_sigma_kmh: float
    sprints: list[Event] = field(default_factory=list)
    accelerations: list[Event] = field(default_factory=list)
    decelerations: list[Event] = field(default_factory=list)
    mean_sprint_length_m: float = 0.0
    max_accel_mps2: float = 0.0
    max_decel_mps2: float = 0.0
    metabolic_power_mean_wkg: float = 0.0
    high_power_distance_m: float = 0.0
    player_load_eq: float = 0.0
    confidence: str = "high"

    @property
    def sprint_count(self) -> int:
        return len(self.sprints)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sprint_count"] = self.sprint_count
        return d


def _smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average per column; window <= 1 is a no-op."""
    if window <= 1 or len(x) < window:
        return x
    kernel = np.ones(window) / window
    out = np.empty_like(x, dtype=float)
    for col in range(x.shape[1]):
        out[:, col] = np.convolve(x[:, col], kernel, mode="same")
    # np.convolve 'same' underweights the edges; keep raw values there.
    half = window // 2
    out[:half] = x[:half]
    out[len(x) - half:] = x[len(x) - half:]
    return out


def _events(
    mask: np.ndarray,
    t: np.ndarray,
    step_dist: np.ndarray,
    values: np.ndarray,
    min_duration_s: float,
) -> list[Event]:
    """Contiguous True runs of `mask` lasting >= min_duration_s, as Events."""
    events: list[Event] = []
    idx = np.flatnonzero(np.diff(np.concatenate(([0], mask.astype(int), [0]))))
    for start, end in zip(idx[0::2], idx[1::2]):
        end = min(end, len(t) - 1)
        duration = float(t[end] - t[start])
        if duration < min_duration_s:
            continue
        dist = float(np.sum(step_dist[start:end]))
        peak = float(np.max(np.abs(values[start : end + 1])))
        events.append(Event(float(t[start]), float(t[end]), duration, dist, peak))
    return events


def metabolic_power_wkg(speed_mps: np.ndarray, accel_mps2: np.ndarray) -> np.ndarray:
    """Instantaneous metabolic power [W/kg], Osgnach et al. 2010."""
    es = np.asarray(accel_mps2, dtype=float) / G
    em = np.sqrt(es**2 + 1.0)
    ec = (155.4 * es**5 - 30.4 * es**4 - 43.3 * es**3 + 46.3 * es**2 + 19.5 * es + 3.6) * em
    return ec * np.asarray(speed_mps, dtype=float)


def physical_load(
    positions_m: np.ndarray,
    timestamps_s: np.ndarray,
    position_sigma_m: float = 0.30,
    smooth_window: int = 5,
    hsr_threshold_kmh: float = HSR_THRESHOLD_KMH,
    sprint_threshold_kmh: float = SPRINT_THRESHOLD_KMH,
    accel_threshold_mps2: float = ACCEL_THRESHOLD_MPS2,
    sprint_min_duration_s: float = 1.0,
    accel_min_duration_s: float = 0.4,
    high_power_threshold_wkg: float = 20.0,
) -> PhysicalLoadSummary:
    """Compute the external-load family for one player trajectory.

    positions_m: (N, 2) pitch-plane positions in metres.
    timestamps_s: (N,) monotonically increasing seconds.
    position_sigma_m: 1-sigma per-axis tracking noise; drives the reported
        uncertainty. Default 0.30 m is a conservative full-pitch camera
        figure; the calibrated arena rig measures ~0.004 m.
    """
    pos = np.asarray(positions_m, dtype=float)
    t = np.asarray(timestamps_s, dtype=float)
    if pos.ndim != 2 or pos.shape[0] != t.shape[0]:
        raise ValueError("positions_m must be (N, 2+) matching timestamps_s")
    n = len(t)
    if n < 3:
        return PhysicalLoadSummary(
            duration_s=float(t[-1] - t[0]) if n >= 2 else 0.0,
            n_samples=n,
            total_distance_m=0.0,
            total_distance_sigma_m=0.0,
            hsr_distance_m=0.0,
            sprint_distance_m=0.0,
            max_speed_kmh=0.0,
            speed_sigma_kmh=0.0,
            confidence="low",
        )

    pos = _smooth(pos, smooth_window)
    step_vec = np.diff(pos, axis=0)
    step_dt = np.diff(t)
    if np.any(step_dt <= 0):
        raise ValueError("timestamps_s must be strictly increasing")
    step_dist = np.linalg.norm(step_vec, axis=1)
    speed = step_dist / step_dt  # (N-1,) forward-difference speed
    speed_kmh = speed * MPS_TO_KMH
    accel = np.diff(speed) / step_dt[1:]  # (N-2,) signed along-path accel

    # First-order noise propagation. Smoothing by a w-sample average divides
    # the per-sample sigma by sqrt(w); a step difference multiplies by sqrt(2).
    eff_sigma = position_sigma_m / np.sqrt(max(smooth_window, 1))
    step_sigma = np.sqrt(2.0) * eff_sigma
    total_distance = float(np.sum(step_dist))
    total_distance_sigma = float(step_sigma * np.sqrt(n - 1))
    speed_sigma_kmh = float(step_sigma / np.median(step_dt) * MPS_TO_KMH)

    hsr_mask = speed_kmh > hsr_threshold_kmh
    sprint_mask = speed_kmh > sprint_threshold_kmh
    hsr_distance = float(np.sum(step_dist[hsr_mask]))
    sprint_distance = float(np.sum(step_dist[sprint_mask]))

    sprints = _events(sprint_mask, t[:-1], step_dist, speed_kmh, sprint_min_duration_s)
    acc_events = _events(
        accel > accel_threshold_mps2, t[1:-1], step_dist[1:], accel, accel_min_duration_s
    )
    dec_events = _events(
        accel < -accel_threshold_mps2, t[1:-1], step_dist[1:], accel, accel_min_duration_s
    )

    p_met = metabolic_power_wkg(speed[1:], accel)
    high_power_distance = float(np.sum(step_dist[1:][p_met > high_power_threshold_wkg]))

    # Camera PlayerLoad equivalent: accumulated jerk-like accel change / 100.
    accel_vec = np.diff(step_vec / step_dt[:, None], axis=0) / step_dt[1:, None]
    d_accel = np.diff(accel_vec, axis=0)
    player_load_eq = float(np.sum(np.linalg.norm(d_accel, axis=1)) / 100.0)

    median_fps = 1.0 / float(np.median(step_dt))
    confidence = "high" if median_fps >= 20 else ("medium" if median_fps >= 10 else "low")

    return PhysicalLoadSummary(
        duration_s=float(t[-1] - t[0]),
        n_samples=n,
        total_distance_m=total_distance,
        total_distance_sigma_m=total_distance_sigma,
        hsr_distance_m=hsr_distance,
        sprint_distance_m=sprint_distance,
        max_speed_kmh=float(np.max(speed_kmh)),
        speed_sigma_kmh=speed_sigma_kmh,
        sprints=sprints,
        accelerations=acc_events,
        decelerations=dec_events,
        mean_sprint_length_m=(
            float(np.mean([e.distance_m for e in sprints])) if sprints else 0.0
        ),
        max_accel_mps2=float(np.max(accel)) if len(accel) else 0.0,
        max_decel_mps2=float(np.min(accel)) if len(accel) else 0.0,
        metabolic_power_mean_wkg=float(np.mean(p_met)) if len(p_met) else 0.0,
        high_power_distance_m=high_power_distance,
        player_load_eq=player_load_eq,
        confidence=confidence,
    )
