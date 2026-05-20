"""Pure rep-counting state for the live push-up / squat trainer.

The smoothed signal angle (knee for squats, elbow for push-ups) drives a
two-state machine. A descent below ``descent_angle_deg`` opens a cycle; a
return above ``top_angle_deg`` closes it. ``top_angle_deg`` is kept strictly
above ``descent_angle_deg`` so a person resting mid-range cannot make the
machine ping-pong. A closed cycle is then classified:

* travel below ``noise_rom_deg``             -> ignored as triangulation jitter
* deep enough (depth gate + ``min_rom_deg``) -> a rep
* a real but shallow attempt                 -> an incomplete
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


_LOW_TRACKING_CUE = "Low tracking - step fully into camera view"
_SHALLOW_CUE = "Shallow rep - go deeper"
_GOOD_REP_CUE = "Good rep - keep it up"
_KNEE_VALGUS_CUE = "Knees caving in - push them out"
_TRUNK_CUE = "Trunk bent - keep body straight"
_ACQUIRE_PUSHUP_CUE = "Get into push-up position"

# The trunk-alignment cue runs through the ankles; only trust it when both
# ankles were triangulated from at least this many cameras for at least the
# streak length below. A single-frame fluke of multi-cam ankle geometry must
# not be enough to raise a form cue on a straight-trunk push-up.
_TRUNK_CUE_MIN_ANKLE_CAMS = 2
_TRUNK_CUE_ANKLE_STREAK_FRAMES = 5

# Push-up elbow-angle velocity clamp. Per-frame changes above this magnitude
# in the averaged left/right elbow signal are treated as occlusion / mislabel
# spikes and coasted on the prior value. A jump that *persists* across the
# sustained-streak length below is accepted as real fast motion. Anatomical
# elbow angular velocity in a child's push-up rarely exceeds ~500 deg/s; at
# 15 FPS that is ~33 deg/frame. 60 deg/frame leaves comfortable headroom for
# real motion while still rejecting single-frame teleports.
_PUSHUP_SIGNAL_MAX_DELTA_DEG_PER_FRAME = 60.0
_PUSHUP_SIGNAL_SUSTAINED_STREAK = 2

_WAITING_PHASE = "WAITING"

# Frames a rep verdict stays on screen before the coaching line clears
# (~1.7 s at 15 FPS) so the athlete can actually read it.
_CUE_HOLD_FRAMES = 25


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
    acquired: bool = True
    cue: str = ""


@dataclass(frozen=True)
class CounterConfig:
    exercise: str
    signal_joint: str
    descent_angle_deg: float       # signal bends past this -> a descent is underway
    bottom_angle_deg: float        # signal at/below this -> counted as full depth
    top_angle_deg: float           # signal straightens past this -> rep cycle closes
    min_rom_deg: float             # min signal travel for a valid (deep enough) rep
    noise_rom_deg: float           # cycles with less travel are ignored as jitter
    smoothing_alpha: float         # EMA factor applied to the raw signal angle
    min_pelvis_travel_mm: float    # squat: pelvis drop that also satisfies the depth gate
    max_knee_valgus_signed_ratio: float
    max_trunk_alignment_error_deg: float
    max_posture_incline_deg: float       # push-up: torso must be at least this horizontal
    acquire_min_frames: int              # consecutive clean plank frames to acquire a set
    release_min_frames: int              # consecutive lost frames to release a set
    min_cycle_frames: int                # min tracked frames for a closed cycle to count
    max_signal_asymmetry_deg: float      # max L/R signal-joint gap before a frame is held


class RepCounter:
    """Incremental hysteresis rep counter for one exercise."""

    def __init__(self, config: CounterConfig):
        self.config = config
        self.state = RepState(phase=self._up_phase())
        self._smoothed: float | None = None
        self._top_angle: float | None = None
        self._top_pelvis_z: float | None = None
        self._cycle_max_angle: float | None = None
        self._cycle_min_angle: float | None = None
        self._cycle_max_pelvis_z: float | None = None
        self._cycle_min_pelvis_z: float | None = None
        self._reached_depth = False
        self._cycle_outcome: str | None = None  # "rep" | "incomplete" this frame
        self._cue_hold = 0
        self._cycle_frames = 0          # tracked frames in the current cycle
        self._acquire_frames = 0        # consecutive clean-plank frames seen
        self._release_frames = 0        # consecutive non-plank frames seen
        # Temporal gates for push-up tracking quality. The trunk cue needs
        # several consecutive multi-cam ankle frames before it can fire; the
        # elbow signal rejects single-frame teleports above an anatomical
        # velocity threshold. Both reset when a set is abandoned.
        self._trunk_ankle_streak = 0
        self._prev_signal_raw: float | None = None
        self._signal_anomaly_streak = 0
        if config.exercise == "push_up":
            # Push-ups start un-acquired: nothing is counted until the athlete
            # is verified to be in a plank for several consecutive frames.
            self.state.acquired = False

    def update(self, metrics: dict[str, Any]) -> RepState:
        angles = metrics.get("angles_deg") or {}
        raw = self._signal_angle(angles)
        quality = self._tracking_quality(angles)
        self.state.tracking_quality = quality
        self.state.tracking_ok = (
            quality >= 0.5 and raw is not None and self._signal_stable(metrics)
        )
        self._cycle_outcome = None

        if self.config.exercise == "push_up":
            # Acquisition gate, debounced both ways: it takes several
            # consecutive verified-plank frames to acquire a set, and several
            # lost frames to release it. A standing / walking athlete sweeps
            # the elbow through the push-up range; without this gate that
            # motion would open and close phantom cycles.
            plank_ok = self.state.tracking_ok and self._pushup_posture_ok(metrics)
            self._update_acquisition(plank_ok)
            if not self.state.acquired:
                self._abandon_cycle()
                self.state.phase = _WAITING_PHASE
                self.state.cue = _ACQUIRE_PUSHUP_CUE
                self.state.current_angle = None
                self.state.depth_pct = 0.0
                return self.state
            if not plank_ok:
                # The set is still open (release debounce not yet expired) but
                # this frame is not a verified plank -- a tracking dropout or a
                # half-stood frame. Hold: never advance or close a cycle on an
                # unverified frame, otherwise standing up manufactures a rep.
                self.state.cue = _LOW_TRACKING_CUE
                return self.state
        else:
            if not self.state.tracking_ok:
                # Hold the state machine: a dropped signal must not advance or
                # close a cycle, otherwise occlusion would manufacture reps.
                self.state.acquired = False
                self.state.cue = _LOW_TRACKING_CUE
                return self.state
            self.state.acquired = True

        raw_signal = self._clamp_pushup_signal_velocity(float(raw))
        angle = self._smooth(raw_signal)
        pelvis_z = _pelvis_z(metrics)
        form_cue = self._form_cue(metrics)
        self.state.current_angle = angle
        self.state.depth_pct = self._depth_pct(angle)

        if self.state.status == "UP":
            self._track_top(angle, pelvis_z)
            self.state.phase = self._up_phase()
            if angle <= self.config.descent_angle_deg:
                self._start_cycle(angle, pelvis_z)
                self.state.status = "DOWN"
                self.state.phase = self._down_phase(angle)
        else:
            self._track_cycle(angle, pelvis_z)
            if angle >= self.config.top_angle_deg:
                self._complete_cycle()
            else:
                self.state.phase = self._down_phase(angle)

        self._apply_cue(form_cue)
        return self.state

    def _smooth(self, raw: float) -> float:
        alpha = self.config.smoothing_alpha
        if self._smoothed is None:
            self._smoothed = raw
        else:
            self._smoothed = alpha * raw + (1.0 - alpha) * self._smoothed
        return self._smoothed

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
            # Advance the ankle-reliability streak every push-up frame so a
            # single fluky ankle measurement cannot satisfy the trunk gate.
            self._update_trunk_ankle_streak(metrics)
            if not self._trunk_cue_reliable():
                # trunk_to_leg runs through the ankles; until they have been
                # reliably tracked for a sustained streak the angle is noise,
                # so the cue is suppressed rather than fired falsely on a
                # straight torso.
                return ""
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
        self._cycle_max_angle = max(seed_angle, angle)
        self._cycle_min_angle = min(seed_angle, angle)
        pelvis_values = [value for value in (self._top_pelvis_z, pelvis_z) if value is not None]
        self._cycle_max_pelvis_z = max(pelvis_values) if pelvis_values else None
        self._cycle_min_pelvis_z = min(pelvis_values) if pelvis_values else None
        self._reached_depth = angle <= self.config.bottom_angle_deg
        self._cycle_frames = 1

    def _track_cycle(self, angle: float, pelvis_z: float | None) -> None:
        self._cycle_frames += 1
        if self._cycle_max_angle is None or angle > self._cycle_max_angle:
            self._cycle_max_angle = angle
        if self._cycle_min_angle is None or angle < self._cycle_min_angle:
            self._cycle_min_angle = angle
        if pelvis_z is not None:
            if self._cycle_max_pelvis_z is None or pelvis_z > self._cycle_max_pelvis_z:
                self._cycle_max_pelvis_z = pelvis_z
            if self._cycle_min_pelvis_z is None or pelvis_z < self._cycle_min_pelvis_z:
                self._cycle_min_pelvis_z = pelvis_z
        if angle <= self.config.bottom_angle_deg:
            self._reached_depth = True

    def _complete_cycle(self) -> None:
        rom = 0.0
        if self._cycle_min_angle is not None and self._cycle_max_angle is not None:
            rom = self._cycle_max_angle - self._cycle_min_angle

        outcome = self._classify_cycle(rom)
        if outcome == "rep":
            self.state.rep_count += 1
            self._cycle_outcome = "rep"
        elif outcome == "incomplete":
            self.state.incomplete_count += 1
            self._cycle_outcome = "incomplete"
        # outcome == "ignore": triangulation jitter, not an attempt -> no count.

        self.state.status = "UP"
        self.state.phase = self._up_phase()
        self._top_angle = self.state.current_angle
        self._top_pelvis_z = self._cycle_max_pelvis_z
        self._reset_cycle()

    def _classify_cycle(self, rom: float) -> str:
        if rom < self.config.noise_rom_deg:
            return "ignore"
        if self._cycle_frames < self.config.min_cycle_frames:
            # Too few tracked frames to be a real rep: a noise-driven
            # open/close that slipped past the ROM gate. Ignoring it stops
            # the rapid double-counts seen during jittery bottom transitions.
            return "ignore"
        if rom < self.config.min_rom_deg:
            return "incomplete"
        if self._reached_depth or self._pelvis_satisfied():
            return "rep"
        return "incomplete"

    def _pelvis_satisfied(self) -> bool:
        min_travel = self.config.min_pelvis_travel_mm
        if min_travel <= 0:
            return False
        if self._cycle_min_pelvis_z is None or self._cycle_max_pelvis_z is None:
            return False
        return (self._cycle_max_pelvis_z - self._cycle_min_pelvis_z) >= min_travel

    def _apply_cue(self, form_cue: str) -> None:
        """Coaching line priority: a fresh rep verdict wins, then that verdict
        is held briefly so it stays readable, then live form feedback."""
        if self._cycle_outcome == "rep":
            self.state.cue = form_cue or _GOOD_REP_CUE
            self._cue_hold = _CUE_HOLD_FRAMES
        elif self._cycle_outcome == "incomplete":
            self.state.cue = _SHALLOW_CUE
            self._cue_hold = _CUE_HOLD_FRAMES
        elif self._cue_hold > 0:
            self._cue_hold -= 1  # keep the just-finished rep verdict readable
        elif form_cue:
            self.state.cue = form_cue
        else:
            self.state.cue = ""

    def _reset_cycle(self) -> None:
        self._cycle_max_angle = None
        self._cycle_min_angle = None
        self._cycle_max_pelvis_z = None
        self._cycle_min_pelvis_z = None
        self._reached_depth = False
        self._cycle_frames = 0

    def _pushup_posture_ok(self, metrics: dict[str, Any]) -> bool:
        """True only when the upper body is verified in a push-up plank.

        Gated on torso incline (the shoulder->hip line -- the most reliably
        tracked pair) plus both elbow angles, which together confirm
        shoulders, elbows, wrists and hips are present. Ankles are
        deliberately NOT required: in an oblique side view the legs are
        frequently mistracked, and making acquisition depend on them made the
        set flicker and the camera unlock mid-rep.
        """
        incline = _as_float((metrics.get("posture") or {}).get("torso_incline_deg"))
        if incline is None or incline > self.config.max_posture_incline_deg:
            return False
        angles = metrics.get("angles_deg") or {}
        return (
            _as_float(angles.get("left_elbow")) is not None
            and _as_float(angles.get("right_elbow")) is not None
        )

    def _update_trunk_ankle_streak(self, metrics: dict[str, Any]) -> None:
        """Advance or reset the ankle-reliability streak for this frame."""
        if self._frame_ankles_reliable(metrics):
            self._trunk_ankle_streak += 1
        else:
            self._trunk_ankle_streak = 0

    @staticmethod
    def _frame_ankles_reliable(metrics: dict[str, Any]) -> bool:
        """True only when both ankles cleared the per-frame camera-count bar."""
        cams = (metrics.get("quality") or {}).get("joint_cams") or []
        for ankle_idx in (15, 16):  # left_ankle, right_ankle
            if ankle_idx >= len(cams):
                return False
            try:
                if int(cams[ankle_idx]) < _TRUNK_CUE_MIN_ANKLE_CAMS:
                    return False
            except (TypeError, ValueError):
                return False
        return True

    def _trunk_cue_reliable(self) -> bool:
        """Whether the trunk-alignment cue can be trusted this frame.

        The cue is derived from the shoulder-hip-ankle angle, so it is only
        meaningful when both ankles have been triangulated from enough cameras
        for a sustained streak. A foot pinned to background clutter for a
        single frame must not raise a form cue.
        """
        return self._trunk_ankle_streak >= _TRUNK_CUE_ANKLE_STREAK_FRAMES

    def _clamp_pushup_signal_velocity(self, raw: float) -> float:
        """Reject single-frame teleports in the push-up signal angle.

        Per-frame deltas above ``_PUSHUP_SIGNAL_MAX_DELTA_DEG_PER_FRAME`` are
        treated as occlusion / mislabel spikes and coasted on the prior raw
        value, so the state machine does not advance or close a cycle from a
        one-frame elbow jump near a phase transition. A jump that *persists*
        across ``_PUSHUP_SIGNAL_SUSTAINED_STREAK`` consecutive frames is
        accepted as real fast motion.
        """
        if self._prev_signal_raw is None:
            self._prev_signal_raw = raw
            self._signal_anomaly_streak = 0
            return raw
        delta = abs(raw - self._prev_signal_raw)
        if delta <= _PUSHUP_SIGNAL_MAX_DELTA_DEG_PER_FRAME:
            self._prev_signal_raw = raw
            self._signal_anomaly_streak = 0
            return raw
        self._signal_anomaly_streak += 1
        if self._signal_anomaly_streak >= _PUSHUP_SIGNAL_SUSTAINED_STREAK:
            # Sustained jump -> the spike turned out to be real fast motion.
            self._prev_signal_raw = raw
            self._signal_anomaly_streak = 0
            return raw
        # Coast on the prior value: do not let the spike enter the EMA.
        return self._prev_signal_raw

    def _signal_stable(self, metrics: dict[str, Any]) -> bool:
        """Reject frames where the two signal-joint sides disagree wildly.

        A large left/right elbow (or knee) gap is the signature of a keypoint
        swap or a collapsed limb when the body is low to the floor; averaging
        the two sides would feed the state machine a corrupted angle and can
        manufacture a rep. Such a frame is held, not advanced.
        """
        asym = _as_float((metrics.get("asymmetry_deg") or {}).get(self.config.signal_joint))
        if asym is None:
            return True  # only one side seen -> nothing to cross-check
        return asym <= self.config.max_signal_asymmetry_deg

    def _update_acquisition(self, plank_ok: bool) -> None:
        """Debounced push-up set acquire / release.

        Acquisition needs ``acquire_min_frames`` consecutive clean planks so a
        transient bend cannot start counting; release needs
        ``release_min_frames`` consecutive lost frames so a brief tracking
        dropout at the bottom of a rep cannot drop the set.
        """
        if plank_ok:
            self._acquire_frames += 1
            self._release_frames = 0
        else:
            self._release_frames += 1
            self._acquire_frames = 0
        if not self.state.acquired:
            if self._acquire_frames >= self.config.acquire_min_frames:
                self.state.acquired = True
        elif self._release_frames >= self.config.release_min_frames:
            self.state.acquired = False

    def _abandon_cycle(self) -> None:
        """Drop any in-progress cycle without counting it (posture lost)."""
        self.state.status = "UP"
        self._reset_cycle()
        self._smoothed = None
        self._top_angle = None
        self._top_pelvis_z = None
        self._cycle_outcome = None
        self._cue_hold = 0
        # Reset the per-set temporal gates: a brand-new acquisition must
        # re-prove ankle reliability and re-seed the elbow velocity history.
        self._trunk_ankle_streak = 0
        self._prev_signal_raw = None
        self._signal_anomaly_streak = 0

    def _depth_pct(self, angle: float) -> float:
        span = self.config.top_angle_deg - self.config.bottom_angle_deg
        if span <= 1e-9:
            return 0.0
        pct = 100.0 * (self.config.top_angle_deg - angle) / span
        return max(0.0, min(100.0, pct))

    def _up_phase(self) -> str:
        return "TOP" if self.config.exercise == "push_up" else "STANDING"

    def _down_phase(self, angle: float) -> str:
        at_bottom = self._reached_depth and angle <= self.config.bottom_angle_deg
        if self.config.exercise == "push_up":
            if at_bottom:
                return "BOTTOM"
            return "PUSHING UP" if self._reached_depth else "LOWERING"
        if at_bottom:
            return "BOTTOM"
        return "ASCENDING" if self._reached_depth else "DESCENDING"


def make_counter(exercise: str, rules: dict[str, Any]) -> RepCounter:
    """Build a RepCounter from one exercise's config block.

    Live-trainer thresholds are read from the exercise's ``live_trainer``
    section, which is isolated from the offline screener's ``segmentation``
    keys so the two can be tuned independently.
    """
    segmentation = rules.get("segmentation") or {}
    live = rules.get("live_trainer") or {}
    thresholds = rules.get("thresholds") or {}

    if exercise == "push_up":
        signal_joint = "elbow"
    elif exercise == "squat":
        signal_joint = "knee"
    else:
        raise ValueError(f"Unsupported live trainer exercise: {exercise}")

    descent = float(live.get("descent_angle_deg", 140.0))
    top = float(live.get("top_angle_deg", 156.0))
    # Hysteresis is only well-formed when the cycle closes clearly above where
    # it opened; clamp defensively so a mis-edited config cannot ping-pong.
    top = max(top, descent + 6.0)

    config = CounterConfig(
        exercise=exercise,
        signal_joint=signal_joint,
        descent_angle_deg=descent,
        bottom_angle_deg=float(live.get("bottom_angle_deg", 112.0)),
        top_angle_deg=top,
        min_rom_deg=float(live.get("min_rom_deg", 45.0)),
        noise_rom_deg=float(live.get("noise_rom_deg", 22.0)),
        smoothing_alpha=_clamp(float(live.get("smoothing_alpha", 0.5)), 0.05, 1.0),
        min_pelvis_travel_mm=float(
            live.get("min_pelvis_travel_mm", segmentation.get("min_pelvis_travel_mm", 0.0))
        ),
        max_knee_valgus_signed_ratio=float(thresholds.get("max_knee_valgus_signed_ratio", 0.02)),
        max_trunk_alignment_error_deg=float(thresholds.get("max_trunk_alignment_error_deg", 25.0)),
        max_posture_incline_deg=float(live.get("max_posture_incline_deg", 40.0)),
        acquire_min_frames=max(1, int(live.get("acquire_min_frames", 4))),
        release_min_frames=max(1, int(live.get("release_min_frames", 8))),
        min_cycle_frames=max(0, int(live.get("min_cycle_frames", 5))),
        max_signal_asymmetry_deg=float(live.get("max_signal_asymmetry_deg", 45.0)),
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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
