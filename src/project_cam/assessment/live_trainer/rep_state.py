"""Pure rep-counting state for the live push-up / squat trainer."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


_LOW_TRACKING_CUE = "Low tracking - step fully into camera view"
_SHALLOW_CUE = "Shallow rep - go deeper"
_KNEE_VALGUS_CUE = "Knees caving in - push them out"
_TRUNK_CUE = "Trunk bent - keep body straight"


@dataclass
class RepState:
    rep_count: int = 0
    incomplete_count: int = 0
    status: str = "UP"
    phase: str = "STANDING"
    current_angle: float | None = None
    depth_pct: float = 0.0
    tracking_quality: float = 0.0
    tracking_ok: bool = False
    cue: str = ""


@dataclass(frozen=True)
class CounterConfig:
    exercise: str
    signal_joint: str
    descent_angle_deg: float
    enter_angle_deg: float
    exit_angle_deg: float
    min_rom_deg: float
    min_pelvis_travel_mm: float
    max_knee_valgus_signed_ratio: float
    max_trunk_alignment_error_deg: float


class RepCounter:
    """Incremental three-threshold hysteresis counter for one exercise."""

    def __init__(self, config: CounterConfig):
        self.config = config
        self.state = RepState(phase=self._up_phase())
        self._top_angle: float | None = None
        self._top_pelvis_z: float | None = None
        self._cycle_max_angle: float | None = None
        self._cycle_min_angle: float | None = None
        self._cycle_max_pelvis_z: float | None = None
        self._cycle_min_pelvis_z: float | None = None
        self._reached_depth = False

    def update(self, metrics: dict[str, Any]) -> RepState:
        angles = metrics.get("angles_deg") or {}
        signal = self._signal_angle(angles)
        quality = self._tracking_quality(angles)
        self.state.tracking_quality = quality
        self.state.tracking_ok = quality >= 0.5 and signal is not None

        if not self.state.tracking_ok:
            self.state.current_angle = signal
            self.state.cue = _LOW_TRACKING_CUE
            return self.state

        angle = float(signal)
        pelvis_z = _pelvis_z(metrics)
        form_cue = self._form_cue(metrics)
        self.state.current_angle = angle
        self.state.depth_pct = self._depth_pct(angle)
        self.state.cue = form_cue

        if self.state.status == "UP":
            self._track_top(angle, pelvis_z)
            self.state.phase = self._up_phase()
            if angle <= self.config.descent_angle_deg:
                self._start_cycle(angle, pelvis_z)
                self.state.status = "DOWN"
                self.state.phase = self._down_phase(angle)
        else:
            self._track_cycle(angle, pelvis_z)
            if angle >= self.config.exit_angle_deg:
                self._complete_cycle(form_cue)
            else:
                self.state.phase = self._down_phase(angle)

        return self.state

    def _signal_angle(self, angles: dict[str, Any]) -> float | None:
        values = [
            _as_float(angles.get(f"left_{self.config.signal_joint}")),
            _as_float(angles.get(f"right_{self.config.signal_joint}")),
        ]
        present = [value for value in values if value is not None]
        if not present:
            return None
        return sum(present) / len(present)

    def _tracking_quality(self, angles: dict[str, Any]) -> float:
        required = (
            ("left_elbow", "right_elbow", "left_trunk_to_leg", "right_trunk_to_leg")
            if self.config.exercise == "push_up"
            else ("left_knee", "right_knee", "left_hip", "right_hip")
        )
        present = sum(1 for key in required if _as_float(angles.get(key)) is not None)
        return present / float(len(required))

    def _form_cue(self, metrics: dict[str, Any]) -> str:
        if self.config.exercise == "push_up":
            trunk_angle = _mean_metric(metrics.get("angles_deg") or {}, "trunk_to_leg")
            if trunk_angle is not None:
                error = abs(180.0 - trunk_angle)
                if error > self.config.max_trunk_alignment_error_deg:
                    return _TRUNK_CUE
            return ""

        valgus = metrics.get("knee_valgus_signed_ratio") or {}
        for side in ("left", "right"):
            value = _as_float(valgus.get(side))
            if value is not None and value > self.config.max_knee_valgus_signed_ratio:
                return _KNEE_VALGUS_CUE
        return ""

    def _track_top(self, angle: float, pelvis_z: float | None) -> None:
        if self._top_angle is None or angle > self._top_angle:
            self._top_angle = angle
        if pelvis_z is not None and (self._top_pelvis_z is None or pelvis_z > self._top_pelvis_z):
            self._top_pelvis_z = pelvis_z

    def _start_cycle(self, angle: float, pelvis_z: float | None) -> None:
        seed_angle = self._top_angle if self._top_angle is not None else angle
        angle_values = [seed_angle, angle]
        self._cycle_max_angle = max(angle_values)
        self._cycle_min_angle = min(angle_values)
        pelvis_values = [value for value in (self._top_pelvis_z, pelvis_z) if value is not None]
        self._cycle_max_pelvis_z = max(pelvis_values) if pelvis_values else None
        self._cycle_min_pelvis_z = min(pelvis_values) if pelvis_values else None
        self._reached_depth = angle <= self.config.enter_angle_deg

    def _track_cycle(self, angle: float, pelvis_z: float | None) -> None:
        if self._cycle_max_angle is None or angle > self._cycle_max_angle:
            self._cycle_max_angle = angle
        if self._cycle_min_angle is None or angle < self._cycle_min_angle:
            self._cycle_min_angle = angle
        if pelvis_z is not None:
            if self._cycle_max_pelvis_z is None or pelvis_z > self._cycle_max_pelvis_z:
                self._cycle_max_pelvis_z = pelvis_z
            if self._cycle_min_pelvis_z is None or pelvis_z < self._cycle_min_pelvis_z:
                self._cycle_min_pelvis_z = pelvis_z
        if angle <= self.config.enter_angle_deg:
            self._reached_depth = True

    def _complete_cycle(self, form_cue: str) -> None:
        valid = self._valid_cycle()
        if valid:
            self.state.rep_count += 1
            self.state.cue = form_cue
        else:
            self.state.incomplete_count += 1
            self.state.cue = _SHALLOW_CUE

        self.state.status = "UP"
        self.state.phase = self._up_phase()
        self._top_angle = self.state.current_angle
        self._top_pelvis_z = self._cycle_max_pelvis_z
        self._reset_cycle()

    def _valid_cycle(self) -> bool:
        if self._cycle_min_angle is None or self._cycle_max_angle is None:
            return False
        rom = self._cycle_max_angle - self._cycle_min_angle
        if not self._reached_depth:
            return False
        if rom < self.config.min_rom_deg:
            return False
        min_travel = self.config.min_pelvis_travel_mm
        if min_travel > 0:
            if self._cycle_min_pelvis_z is None or self._cycle_max_pelvis_z is None:
                return False
            if (self._cycle_max_pelvis_z - self._cycle_min_pelvis_z) < min_travel:
                return False
        return True

    def _reset_cycle(self) -> None:
        self._cycle_max_angle = None
        self._cycle_min_angle = None
        self._cycle_max_pelvis_z = None
        self._cycle_min_pelvis_z = None
        self._reached_depth = False

    def _depth_pct(self, angle: float) -> float:
        span = self.config.descent_angle_deg - self.config.enter_angle_deg
        if span <= 1e-9:
            return 0.0
        pct = 100.0 * (self.config.descent_angle_deg - angle) / span
        return max(0.0, min(100.0, pct))

    def _up_phase(self) -> str:
        return "TOP" if self.config.exercise == "push_up" else "STANDING"

    def _down_phase(self, angle: float) -> str:
        if self.config.exercise == "push_up":
            if self._reached_depth and angle <= self.config.enter_angle_deg:
                return "BOTTOM"
            return "PUSHING UP" if self._reached_depth else "LOWERING"
        if self._reached_depth and angle <= self.config.enter_angle_deg:
            return "BOTTOM"
        return "ASCENDING" if self._reached_depth else "DESCENDING"


def make_counter(exercise: str, rules: dict[str, Any]) -> RepCounter:
    seg_rules = rules.get("segmentation") or {}
    protocol = rules.get("protocol") or {}
    thresholds = rules.get("thresholds") or {}

    if exercise == "push_up":
        signal_joint = "elbow"
    elif exercise == "squat":
        signal_joint = "knee"
    else:
        raise ValueError(f"Unsupported live trainer exercise: {exercise}")

    config = CounterConfig(
        exercise=exercise,
        signal_joint=signal_joint,
        descent_angle_deg=float(seg_rules.get("descent_angle_deg", 150.0)),
        enter_angle_deg=float(seg_rules.get("enter_angle_deg", 100.0 if exercise == "push_up" else 90.0)),
        exit_angle_deg=float(seg_rules.get("exit_angle_deg", 150.0 if exercise == "push_up" else 120.0)),
        min_rom_deg=float(seg_rules.get("min_rom_deg", protocol.get("min_rom_deg", 25.0))),
        min_pelvis_travel_mm=float(seg_rules.get("min_pelvis_travel_mm", 0.0)),
        max_knee_valgus_signed_ratio=float(thresholds.get("max_knee_valgus_signed_ratio", 0.02)),
        max_trunk_alignment_error_deg=float(thresholds.get("max_trunk_alignment_error_deg", 25.0)),
    )
    return RepCounter(config)


def _mean_metric(values: dict[str, Any], name: str) -> float | None:
    side_values = [_as_float(values.get(f"left_{name}")), _as_float(values.get(f"right_{name}"))]
    present = [value for value in side_values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _pelvis_z(metrics: dict[str, Any]) -> float | None:
    return _as_float((metrics.get("distances") or {}).get("pelvis_center_z_mm"))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number
