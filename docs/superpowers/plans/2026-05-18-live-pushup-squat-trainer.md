# 4-Cam Live Push-Up and Squat Trainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a LinkedIn-style real-time OpenCV pose trainer for the garage 4-camera rig that counts push-up/squat reps and coaches form, driven by the existing Project_Cam UDP 3D joint stream.

**Architecture:** A standalone `project_cam.assessment.live_trainer` package binds the same UDP port the assessment recorder uses (5015), converts each `joints` packet into a normalized frame with the existing `io.normalize_frame`, computes 3D kinematics with the existing `kinematics.frame_kinematics`, feeds metrics into a new incremental `RepCounter` state machine (one config-driven class for both exercises), and renders an OpenCV dashboard every loop. No frozen calibration/triangulation code is touched — the live tracker remains the unchanged sender.

**Tech Stack:** Python 3.10, NumPy, OpenCV (`cv2`), Python stdlib `socket`/`argparse`, `unittest`, YAML exercise config.

---

## Background / Context for the Engineer

You are extending a thesis project that tracks people with 4 cameras and produces 3D joint coordinates in millimetres (COCO-17 layout). A separate already-working program (`apps/athlete_assessment/run_live_tracking_for_assessment.sh`) broadcasts 3D joints over UDP. Your job is to build a *consumer* of that stream: a live coaching dashboard for push-ups and squats.

Key facts you must not re-derive:

- **UDP packet format** (sent by the live tracker, one per frame):
  ```json
  {"type": "joints", "ts": 1747573200.12, "frame": 813,
   "joints": {"left_knee": {"x_mm": 120.0, "y_mm": 50.0, "z_mm": 805.0, "conf": 0.91, "cams": 3}, ...}}
  ```
  The `joints` value is a dict keyed by COCO-17 joint name. Not every joint is present every frame (occluded / low-confidence joints are dropped by the sender).
- **Coordinate frame:** millimetres. `z_mm` is vertical (up). A person standing tall has a high pelvis `z`; squatting lowers it.
- `io.normalize_frame(packet, index, default_fps, source)` already converts that packet into a frame dict with a 17-element `joints` list. Reuse it — do not parse joints yourself.
- `kinematics.frame_kinematics(frame)` already computes all joint angles, `distances.pelvis_center_z_mm`, `knee_valgus_signed_ratio`, and `quality`. Reuse it.
- COCO-17 angle keys produced in `metrics["angles_deg"]` include `left_knee`/`right_knee` (hip-knee-ankle), `left_elbow`/`right_elbow` (shoulder-elbow-wrist), `left_hip`/`right_hip`, and `left_trunk_to_leg`/`right_trunk_to_leg` (shoulder-hip-ankle). A perfectly straight push-up plank has `trunk_to_leg` ≈ 180°.
- **Do NOT modify** `triangulate_multi`, `transform_world_point_y`, `ema_update`, the live tracker's UDP sender, or any extrinsics/firmware files. This plan never touches them.

**Rep-counting model used throughout this plan (3-threshold hysteresis):**
- `descent_angle_deg` — the signal angle (knee for squat, elbow for push-up) drops below this ⇒ a descent has started, the state machine enters `down`.
- `enter_angle_deg` — the angle must reach at or below this for the rep to count as "full depth".
- `exit_angle_deg` — the angle must return at or above this to complete the cycle.
- On cycle completion: a rep is **valid** if it reached full depth AND its angle range-of-motion ≥ `min_rom_deg` AND (squat only) pelvis vertical travel ≥ `min_pelvis_travel_mm`. Otherwise it is counted as **incomplete** (shallow).

---

## File Structure

**Create:**
- `src/project_cam/assessment/live_trainer/__init__.py` — package marker, re-exports `RepCounter`, `RepState`, `make_counter`.
- `src/project_cam/assessment/live_trainer/rep_state.py` — `RepState` dataclass, `CounterConfig` dataclass, `RepCounter` incremental state machine, `make_counter` factory. Pure logic, no I/O, no OpenCV. Unit-tested.
- `src/project_cam/assessment/live_trainer/dashboard.py` — `render_dashboard()` OpenCV renderer. Pure rendering (input state → BGR image).
- `src/project_cam/assessment/live_trainer/__main__.py` — CLI + UDP receive loop + `cv2` window. Wires the three pieces together.
- `apps/athlete_assessment/run_live_trainer.sh` — convenience wrapper.
- `tests/test_live_trainer.py` — unit tests for `RepCounter` and `render_dashboard`.

**Modify:**
- `configs/exercises/football_academy_u10.yaml` — add `push_up` as an active exercise, add `descent_angle_deg` to `squat`, remove `push_up` from `deferred_exercises`, and **move `single_leg_squat` out of the active set into `deferred_exercises`** (it is dropped from the screen — single-leg balance is hard to perform reliably for the demo athlete; deferring rather than deleting keeps its tuned thresholds for future use).
- `src/project_cam/assessment/segmentation.py:8-11` — add `push_up` to `SIGNAL_BY_EXERCISE` so the offline path uses the elbow signal (defensive; offline push-up is not a v1 deliverable but the config now exposes it).
- `tests/test_assessment_kairat_hardening.py:9-16` — the existing test asserts the config exposes *only* squat + single-leg squat; update it to expect the active set `{squat, push_up}`.

---

### Task 1: Set the screen to squat + push-up in the exercise config

**Files:**
- Modify: `configs/exercises/football_academy_u10.yaml`
- Modify: `src/project_cam/assessment/segmentation.py:8-11`
- Modify: `tests/test_assessment_kairat_hardening.py:9-16`

- [ ] **Step 1: Update the failing config test first**

In `tests/test_assessment_kairat_hardening.py`, replace lines 9-16 (the method `test_demo_config_exposes_only_squat_and_single_leg_squat` and its body) with:

```python
    def test_demo_config_exposes_squat_and_push_up(self):
        from project_cam.assessment.rules import load_rules

        config = load_rules("configs/exercises/football_academy_u10.yaml")

        self.assertEqual(
            set(config["exercises"].keys()),
            {"squat", "push_up"},
        )
        self.assertIn("deferred_exercises", config)
        self.assertNotIn("push_up", config["deferred_exercises"])
        self.assertIn("single_leg_squat", config["deferred_exercises"])
        self.assertIn("plank", config["deferred_exercises"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/test_assessment_kairat_hardening.py::KairatHardeningTests::test_demo_config_exposes_squat_and_push_up -v`
Expected: FAIL — `push_up` is still under `deferred_exercises` and `single_leg_squat` is still active, so `config["exercises"].keys()` is `{"squat", "single_leg_squat"}`.

- [ ] **Step 3: Add `descent_angle_deg` to the squat segmentation block**

In `configs/exercises/football_academy_u10.yaml`, inside `exercises.squat.segmentation`, add one line after `exit_angle_deg: 120`:

```yaml
      enter_angle_deg: 90
      exit_angle_deg: 120
      descent_angle_deg: 150
      min_rep_duration_s: 0.3
```

(The offline pipeline ignores unknown segmentation keys; only the live `RepCounter` reads `descent_angle_deg`.)

- [ ] **Step 4: Add the `push_up` active exercise**

In `configs/exercises/football_academy_u10.yaml`, add a new exercise block under `exercises:`, immediately after the `squat:` exercise block (so the active exercises read `squat`, `push_up`):

```yaml
  push_up:
    <<: *defaults
    description: "Bilateral push-up rep count and trunk-alignment screen."
    segmentation:
      descent_angle_deg: 150
      enter_angle_deg: 100
      exit_angle_deg: 150
      min_rom_deg: 50
      min_rep_duration_s: 0.3
      max_rep_duration_s: 8.0
      max_missing_frame_ratio: 0.30
    protocol:
      min_fps: 15
      min_reps: 5
      min_rom_deg: 50
      min_valid_frame_ratio: 0.60
    thresholds:
      min_confidence_score: 45
      max_left_right_angle_asymmetry_deg: 25
      max_knee_line_deviation_ratio: 0.20
      max_knee_valgus_signed_ratio: 0.020
      bottom_elbow_angle_max_deg: 100
      max_trunk_alignment_error_deg: 20
```

- [ ] **Step 5: Reconcile the exercise roster — drop `single_leg_squat`, swap deferred entries**

In `configs/exercises/football_academy_u10.yaml`:

(a) Delete the entire `single_leg_squat:` exercise block from under `exercises:` (the block beginning `  single_leg_squat:` and running through its `thresholds:` sub-block, ending at the `bottom_knee_angle_max_deg:` line). After this and Step 4, `exercises:` contains exactly `squat` and `push_up`.

(b) Delete these two lines from the `deferred_exercises:` block (push-up is now active):

```yaml
  push_up:
    reason: "Deferred until squat/single-leg squat repeatability is proven in garage tests."
```

(c) Add a `single_leg_squat` entry to the `deferred_exercises:` block (it is dropped from the active screen, not deleted — the block is preserved in version control history and can be reactivated later):

```yaml
  single_leg_squat:
    reason: "Removed from the active screen - single-leg balance is hard to perform reliably for the demo athlete."
```

Leave `plank`, `countermovement_jump`, `drop_landing`, `lateral_shuffle`, `cutting`, `slalom_dribble`, and `wall_volley` in `deferred_exercises` untouched.

- [ ] **Step 6: Add the push-up signal to the offline segmenter**

In `src/project_cam/assessment/segmentation.py`, replace the `SIGNAL_BY_EXERCISE` dict (lines 8-11) with:

```python
SIGNAL_BY_EXERCISE = {
    "squat": ("angles_deg", "knee"),
    "single_leg_squat": ("angles_deg", "knee"),
    "push_up": ("angles_deg", "elbow"),
}
```

- [ ] **Step 7: Run the config test to verify it passes**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/test_assessment_kairat_hardening.py -v`
Expected: PASS — all tests in the file pass, including `test_demo_config_exposes_squat_and_push_up`.

- [ ] **Step 8: Run the full assessment test suite to confirm no regressions**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/ -v`
Expected: PASS — no test regressions. The remaining `KairatHardeningTests` use `exercise="squat"`, which stays active, so dropping `single_leg_squat` does not break them.

- [ ] **Step 9: Commit**

```bash
git add configs/exercises/football_academy_u10.yaml src/project_cam/assessment/segmentation.py tests/test_assessment_kairat_hardening.py
git commit -m "feat: swap U10 screen to squat + push_up, defer single-leg squat"
```

---

### Task 2: `RepCounter` incremental rep state machine

**Files:**
- Create: `src/project_cam/assessment/live_trainer/__init__.py`
- Create: `src/project_cam/assessment/live_trainer/rep_state.py`
- Test: `tests/test_live_trainer.py`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_live_trainer.py` with these synthetic-frame tests. The helpers build COCO-17 joint lists; `_metrics` runs the real kinematics so the counter is tested against genuine angle math.

```python
import math
import unittest


def _metrics(joints):
    from project_cam.assessment.kinematics import frame_kinematics

    conf = [0.95 if p is not None else 0.0 for p in joints]
    cams = [3 if p is not None else 0 for p in joints]
    return frame_kinematics({"joints": joints, "joint_conf": conf, "joint_cams": cams})


def _squat_joints(knee_angle_deg, hip_z):
    """COCO-17 body in a squat pose; hip-knee-ankle angle == knee_angle_deg."""
    joints = [None] * 17
    theta = math.radians(knee_angle_deg)

    def side(x):
        hip = [x, 0, hip_z]
        knee = [x, 0, hip_z - 450]
        ankle = [x + 450 * math.sin(theta), 0, hip_z - 450 + 450 * math.cos(theta)]
        shoulder = [x, 0, hip_z + 550]
        elbow = [x + 80, 0, hip_z + 250]
        wrist = [x + 120, 0, hip_z + 50]
        return shoulder, elbow, wrist, hip, knee, ankle

    for idx, point in zip([5, 7, 9, 11, 13, 15], side(-180)):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 14, 16], side(180)):
        joints[idx] = point
    joints[0] = [0, 0, hip_z + 700]
    return joints


def _pushup_joints(elbow_angle_deg, hip_drop_mm=0.0):
    """COCO-17 body in a push-up pose; shoulder-elbow-wrist angle == elbow_angle_deg.

    hip_drop_mm lowers the pelvis below the shoulder-ankle line, bending the
    shoulder-hip-ankle (trunk_to_leg) angle away from 180 degrees.
    """
    joints = [None] * 17
    t = math.radians(elbow_angle_deg)

    def side(y):
        shoulder = [0.0, y, 500.0]
        elbow = [0.0, y, 300.0]
        wrist = [200.0 * math.sin(t), y, 300.0 + 200.0 * math.cos(t)]
        hip = [600.0, y, 500.0 - hip_drop_mm]
        ankle = [1300.0, y, 500.0]
        return shoulder, elbow, wrist, hip, ankle

    for idx, point in zip([5, 7, 9, 11, 15], side(-180.0)):
        joints[idx] = point
    for idx, point in zip([6, 8, 10, 12, 16], side(180.0)):
        joints[idx] = point
    joints[0] = [0.0, 0.0, 560.0]
    return joints


def _make(exercise):
    from project_cam.assessment.live_trainer.rep_state import make_counter
    from project_cam.assessment.rules import exercise_rules, load_rules

    config = load_rules("configs/exercises/football_academy_u10.yaml")
    return make_counter(exercise, exercise_rules(config, exercise))


_SQUAT_REP = [(165, 1000), (132, 930), (102, 850), (88, 805), (105, 850), (135, 930), (165, 1000)]
_SHALLOW_SQUAT_REP = [(165, 1000), (150, 990), (140, 980), (135, 975), (140, 980), (150, 990), (165, 1000)]
_PUSHUP_REP = [165, 120, 95, 80, 95, 120, 165]
_SHALLOW_PUSHUP_REP = [165, 150, 138, 132, 138, 150, 165]


class RepCounterSquatTests(unittest.TestCase):
    def test_counts_five_clean_squats(self):
        counter = _make("squat")
        for _ in range(5):
            for knee, hip_z in _SQUAT_REP:
                counter.update(_metrics(_squat_joints(knee, hip_z)))
        self.assertEqual(counter.state.rep_count, 5)
        self.assertEqual(counter.state.incomplete_count, 0)
        self.assertEqual(counter.state.status, "UP")

    def test_shallow_squats_flagged_incomplete_not_counted(self):
        counter = _make("squat")
        for _ in range(5):
            for knee, hip_z in _SHALLOW_SQUAT_REP:
                counter.update(_metrics(_squat_joints(knee, hip_z)))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertGreaterEqual(counter.state.incomplete_count, 1)
        self.assertIn("shallow", counter.state.cue.lower())


class RepCounterPushUpTests(unittest.TestCase):
    def test_counts_five_clean_push_ups(self):
        counter = _make("push_up")
        for _ in range(5):
            for elbow in _PUSHUP_REP:
                counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 5)
        self.assertEqual(counter.state.incomplete_count, 0)

    def test_shallow_push_ups_flagged_incomplete(self):
        counter = _make("push_up")
        for _ in range(5):
            for elbow in _SHALLOW_PUSHUP_REP:
                counter.update(_metrics(_pushup_joints(elbow)))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertGreaterEqual(counter.state.incomplete_count, 1)

    def test_trunk_misalignment_triggers_cue(self):
        counter = _make("push_up")
        for elbow in _PUSHUP_REP:
            counter.update(_metrics(_pushup_joints(elbow, hip_drop_mm=200.0)))
        cue = counter.state.cue.lower()
        self.assertTrue("trunk" in cue or "body" in cue)


class RepCounterTrackingTests(unittest.TestCase):
    def test_missing_leg_joints_show_low_tracking_no_false_reps(self):
        counter = _make("squat")
        for _ in range(5):
            for knee, hip_z in _SQUAT_REP:
                joints = _squat_joints(knee, hip_z)
                for idx in (13, 14, 15, 16):  # drop both knees and ankles
                    joints[idx] = None
                counter.update(_metrics(joints))
        self.assertEqual(counter.state.rep_count, 0)
        self.assertFalse(counter.state.tracking_ok)
        self.assertLess(counter.state.tracking_quality, 0.5)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/test_live_trainer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'project_cam.assessment.live_trainer'`.

- [ ] **Step 3: Create the package marker**

Create `src/project_cam/assessment/live_trainer/__init__.py`:

```python
"""Live push-up / squat trainer: UDP-driven OpenCV coaching dashboard."""

from .rep_state import CounterConfig, RepCounter, RepState, make_counter

__all__ = ["CounterConfig", "RepCounter", "RepState", "make_counter"]
```

- [ ] **Step 4: Implement `rep_state.py`**

Create `src/project_cam/assessment/live_trainer/rep_state.py`:

```python
"""Incremental rep state machine for the live push-up / squat trainer.

Pure logic: consumes per-frame metrics from `kinematics.frame_kinematics`
and exposes a `RepState`. No I/O, no OpenCV — fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Display phase labels per exercise: (top, descending, bottom, ascending).
_PHASE_LABELS = {
    "squat": ("STANDING", "DESCENDING", "BOTTOM", "ASCENDING"),
    "push_up": ("TOP", "LOWERING", "BOTTOM", "PUSHING UP"),
}
_DEFAULT_PHASE_LABELS = ("UP", "DESCENDING", "BOTTOM", "ASCENDING")

# Which joint-angle drives rep segmentation for each exercise.
_SIGNAL_JOINT = {"squat": "knee", "single_leg_squat": "knee", "push_up": "elbow"}

# Joint-angle keys used to gauge tracking quality per exercise.
_QUALITY_KEYS = {
    "push_up": ["left_elbow", "right_elbow", "left_trunk_to_leg", "right_trunk_to_leg"],
    "_default": ["left_knee", "right_knee", "left_hip", "right_hip"],
}


@dataclass
class RepState:
    """Snapshot of trainer state, consumed by the dashboard renderer."""

    rep_count: int = 0
    incomplete_count: int = 0
    status: str = "UP"  # "UP" or "DOWN"
    phase: str = "STANDING"  # display phase label
    current_angle: float | None = None
    depth_pct: float = 0.0  # 0..100, how deep into the current rep
    tracking_quality: float = 0.0  # 0..1
    tracking_ok: bool = False
    cue: str = "Waiting for athlete..."


@dataclass
class CounterConfig:
    exercise: str
    signal_joint: str  # "knee" or "elbow"
    descent_angle_deg: float
    enter_angle_deg: float
    exit_angle_deg: float
    min_rom_deg: float
    min_pelvis_travel_mm: float | None  # None disables the pelvis-travel gate
    max_knee_valgus_signed_ratio: float
    max_trunk_alignment_error_deg: float


def make_counter(exercise: str, rules: dict[str, Any]) -> "RepCounter":
    """Build a RepCounter from a single exercise's rules block."""
    seg = rules.get("segmentation", {}) or {}
    thr = rules.get("thresholds", {}) or {}
    proto = rules.get("protocol", {}) or {}
    config = CounterConfig(
        exercise=exercise,
        signal_joint=_SIGNAL_JOINT.get(exercise, "knee"),
        descent_angle_deg=float(seg.get("descent_angle_deg", 150.0)),
        enter_angle_deg=float(seg.get("enter_angle_deg", 95.0)),
        exit_angle_deg=float(seg.get("exit_angle_deg", 150.0)),
        min_rom_deg=float(proto.get("min_rom_deg", seg.get("min_rom_deg", 45.0))),
        min_pelvis_travel_mm=(
            float(seg["min_pelvis_travel_mm"]) if "min_pelvis_travel_mm" in seg else None
        ),
        max_knee_valgus_signed_ratio=float(thr.get("max_knee_valgus_signed_ratio", 0.02)),
        max_trunk_alignment_error_deg=float(thr.get("max_trunk_alignment_error_deg", 20.0)),
    )
    return RepCounter(config)


class RepCounter:
    """Streaming 3-threshold hysteresis rep counter for one exercise."""

    def __init__(self, config: CounterConfig):
        self.config = config
        labels = _PHASE_LABELS.get(config.exercise, _DEFAULT_PHASE_LABELS)
        self._label_top, self._label_desc, self._label_bottom, self._label_asc = labels
        self.state = RepState(phase=self._label_top, status="UP")
        self._machine = "up"  # "up" | "down"
        self._prev_angle: float | None = None
        self._rep_top_angle: float | None = None
        self._rep_min_angle: float | None = None
        self._rep_min_pelvis_z: float | None = None
        self._rep_max_pelvis_z: float | None = None
        self._standing_pelvis_z: float | None = None
        self._rep_worst_cue: str = ""

    def update(self, metrics: dict[str, Any]) -> RepState:
        cfg = self.config
        angle = self._signal_angle(metrics)
        quality = self._tracking_quality(metrics)
        self.state.tracking_quality = quality
        tracking_ok = quality >= 0.5 and angle is not None
        self.state.tracking_ok = tracking_ok
        if not tracking_ok:
            self.state.cue = "Low tracking - step fully into camera view"
            return self.state

        self.state.current_angle = angle
        pelvis_z = self._pelvis_z(metrics)
        frame_cue = self._form_cue(metrics)
        rep_msg = ""

        if self._machine == "up":
            self._rep_top_angle = (
                angle if self._rep_top_angle is None else max(self._rep_top_angle, angle)
            )
            if pelvis_z is not None:
                self._standing_pelvis_z = pelvis_z
            if angle <= cfg.descent_angle_deg:
                self._machine = "down"
                self._rep_min_angle = angle
                seed = self._standing_pelvis_z if self._standing_pelvis_z is not None else pelvis_z
                self._rep_min_pelvis_z = seed
                self._rep_max_pelvis_z = seed
                self._rep_worst_cue = frame_cue
        else:  # "down"
            self._rep_min_angle = min(self._rep_min_angle, angle)
            if pelvis_z is not None:
                if self._rep_min_pelvis_z is None:
                    self._rep_min_pelvis_z = pelvis_z
                    self._rep_max_pelvis_z = pelvis_z
                else:
                    self._rep_min_pelvis_z = min(self._rep_min_pelvis_z, pelvis_z)
                    self._rep_max_pelvis_z = max(self._rep_max_pelvis_z, pelvis_z)
            if frame_cue:
                self._rep_worst_cue = frame_cue
            if angle >= cfg.exit_angle_deg:
                rep_msg = self._finish_rep()
                self._machine = "up"
                self._rep_top_angle = angle

        self._update_phase(angle)
        self._update_cue(frame_cue, rep_msg)
        self._prev_angle = angle
        return self.state

    def _finish_rep(self) -> str:
        cfg = self.config
        top = self._rep_top_angle if self._rep_top_angle is not None else cfg.exit_angle_deg
        bottom = self._rep_min_angle if self._rep_min_angle is not None else top
        rom = top - bottom
        reached_depth = bottom <= cfg.enter_angle_deg
        deep_enough = rom >= cfg.min_rom_deg
        pelvis_ok = True
        if cfg.min_pelvis_travel_mm is not None:
            if self._rep_min_pelvis_z is None or self._rep_max_pelvis_z is None:
                pelvis_ok = False
            else:
                travel = self._rep_max_pelvis_z - self._rep_min_pelvis_z
                pelvis_ok = travel >= cfg.min_pelvis_travel_mm
        worst = self._rep_worst_cue
        self._rep_min_angle = None
        self._rep_min_pelvis_z = None
        self._rep_max_pelvis_z = None
        self._rep_worst_cue = ""
        if reached_depth and deep_enough and pelvis_ok:
            self.state.rep_count += 1
            return worst if worst else f"Rep {self.state.rep_count} - good form"
        self.state.incomplete_count += 1
        return "Shallow rep - go deeper"

    def _update_phase(self, angle: float) -> None:
        cfg = self.config
        if self._machine == "up":
            self.state.status = "UP"
            self.state.phase = self._label_top
            self.state.depth_pct = 0.0
            return
        self.state.status = "DOWN"
        span = max(1e-6, cfg.descent_angle_deg - cfg.enter_angle_deg)
        self.state.depth_pct = max(0.0, min(100.0, (cfg.descent_angle_deg - angle) / span * 100.0))
        if angle <= cfg.enter_angle_deg:
            self.state.phase = self._label_bottom
        elif self._prev_angle is not None and angle > self._prev_angle + 1.0:
            self.state.phase = self._label_asc
        else:
            self.state.phase = self._label_desc

    def _update_cue(self, frame_cue: str, rep_msg: str) -> None:
        if frame_cue:
            self.state.cue = frame_cue
        elif rep_msg:
            self.state.cue = rep_msg
        elif self.state.cue.startswith(("Low tracking", "Waiting")):
            self.state.cue = "Good form - keep going"

    def _signal_angle(self, metrics: dict[str, Any]) -> float | None:
        angles = metrics.get("angles_deg", {}) or {}
        joint = self.config.signal_joint
        vals = [angles.get(f"left_{joint}"), angles.get(f"right_{joint}")]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def _pelvis_z(self, metrics: dict[str, Any]) -> float | None:
        return (metrics.get("distances") or {}).get("pelvis_center_z_mm")

    def _tracking_quality(self, metrics: dict[str, Any]) -> float:
        angles = metrics.get("angles_deg", {}) or {}
        keys = _QUALITY_KEYS.get(self.config.exercise, _QUALITY_KEYS["_default"])
        present = sum(1 for k in keys if angles.get(k) is not None)
        return present / len(keys)

    def _form_cue(self, metrics: dict[str, Any]) -> str:
        if self.config.exercise == "push_up":
            return self._trunk_cue(metrics)
        return self._valgus_cue(metrics)

    def _valgus_cue(self, metrics: dict[str, Any]) -> str:
        ratios = metrics.get("knee_valgus_signed_ratio", {}) or {}
        for side in ("left", "right"):
            r = ratios.get(side)
            if r is not None and r > self.config.max_knee_valgus_signed_ratio:
                return "Knees caving in - push them out"
        return ""

    def _trunk_cue(self, metrics: dict[str, Any]) -> str:
        angles = metrics.get("angles_deg", {}) or {}
        vals = [angles.get("left_trunk_to_leg"), angles.get("right_trunk_to_leg")]
        vals = [v for v in vals if v is not None]
        if not vals:
            return ""
        trunk = sum(vals) / len(vals)
        dev = abs(180.0 - trunk)
        if dev > self.config.max_trunk_alignment_error_deg:
            return f"Trunk bent {dev:.0f} deg - keep body straight"
        return ""
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/test_live_trainer.py -v`
Expected: PASS — all six `RepCounter` tests pass (the dashboard test is added in Task 3).

- [ ] **Step 6: Commit**

```bash
git add src/project_cam/assessment/live_trainer/__init__.py src/project_cam/assessment/live_trainer/rep_state.py tests/test_live_trainer.py
git commit -m "feat: add incremental RepCounter for live push-up/squat trainer"
```

---

### Task 3: OpenCV dashboard renderer

**Files:**
- Create: `src/project_cam/assessment/live_trainer/dashboard.py`
- Test: `tests/test_live_trainer.py` (append one test)

- [ ] **Step 1: Add the failing dashboard test**

Append this class to `tests/test_live_trainer.py`, before the `if __name__ == "__main__":` line:

```python
class DashboardTests(unittest.TestCase):
    def test_render_dashboard_returns_bgr_canvas(self):
        import numpy as np

        from project_cam.assessment.live_trainer.dashboard import render_dashboard
        from project_cam.assessment.live_trainer.rep_state import RepState

        state = RepState(rep_count=3, status="DOWN", phase="BOTTOM",
                         current_angle=92.0, depth_pct=80.0,
                         tracking_quality=0.9, tracking_ok=True, cue="Good form")
        joints = _squat_joints(92.0, 850.0)
        canvas = render_dashboard("squat", state, joints, width=900, height=720)

        self.assertEqual(canvas.shape, (720, 900, 3))
        self.assertEqual(canvas.dtype, np.uint8)

    def test_render_dashboard_handles_missing_joints(self):
        from project_cam.assessment.live_trainer.dashboard import render_dashboard
        from project_cam.assessment.live_trainer.rep_state import RepState

        canvas = render_dashboard("push_up", RepState(), [None] * 17)
        self.assertEqual(canvas.shape[2], 3)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/test_live_trainer.py::DashboardTests -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'project_cam.assessment.live_trainer.dashboard'`.

- [ ] **Step 3: Implement `dashboard.py`**

Create `src/project_cam/assessment/live_trainer/dashboard.py`:

```python
"""OpenCV dashboard renderer for the live push-up / squat trainer.

LinkedIn-style 'AI FITNESS ANALYTICS' layout: a large skeleton stage on the
left with a vertical depth gauge, and an analytics column on the right with
status, rep count, an angle dial, movement phase, tracking quality, a
coaching ribbon, and a phase timeline. Pure rendering: state in, BGR out.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .rep_state import RepState

# --- palette (BGR) ---
_BG = (26, 26, 30)
_STAGE = (18, 18, 22)
_PANEL = (42, 42, 48)
_PANEL_HI = (54, 54, 62)
_TEXT = (240, 240, 240)
_MUTE = (140, 140, 148)
_GREEN = (96, 208, 116)
_BLUE = (224, 168, 72)
_AMBER = (64, 184, 240)
_RED = (84, 92, 232)
_YELLOW = (90, 220, 232)

_PHASE_COLOR = {
    "STANDING": _GREEN, "TOP": _GREEN,
    "DESCENDING": _AMBER, "LOWERING": _AMBER,
    "BOTTOM": _RED,
    "ASCENDING": _BLUE, "PUSHING UP": _BLUE,
}

_PHASE_DESC = {
    "STANDING": "Tall, ready position",
    "DESCENDING": "Lowering hips under control",
    "BOTTOM": "Hips at depth",
    "ASCENDING": "Driving back up",
    "TOP": "Arms fully extended",
    "LOWERING": "Chest toward the floor",
    "PUSHING UP": "Driving the body up",
}

# Ordered phase sequence per exercise, for the timeline strip.
_PHASE_ORDER = {
    "squat": ["STANDING", "DESCENDING", "BOTTOM", "ASCENDING"],
    "push_up": ["TOP", "LOWERING", "BOTTOM", "PUSHING UP"],
}

# COCO-17 skeleton edges (limbs + torso + head links).
_SKELETON_EDGES = [
    (5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6),
]

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def render_dashboard(
    exercise: str,
    state: RepState,
    joints: list[Any],
    width: int = 1180,
    height: int = 680,
) -> np.ndarray:
    """Render the trainer dashboard as a BGR uint8 image."""
    canvas = np.full((height, width, 3), _BG, dtype=np.uint8)
    phases = _PHASE_ORDER.get(exercise, ["UP", "DESCENDING", "BOTTOM", "ASCENDING"])
    phase_color = _PHASE_COLOR.get(state.phase, _MUTE)

    # ===== left: skeleton stage with vertical depth gauge =====
    stage_x, stage_y, stage_w, stage_h = 20, 20, 620, height - 40
    _round_rect(canvas, stage_x, stage_y, stage_w, stage_h, 14, _STAGE)
    _chip(canvas, stage_x + 16, stage_y + 16, "SKELETON VIEW", _MUTE)
    gauge_w = 26
    _draw_skeleton(canvas, stage_x + 16, stage_y + 52,
                   stage_w - 48 - gauge_w, stage_h - 96, joints, phase_color)
    _depth_gauge(canvas, stage_x + stage_w - gauge_w - 16, stage_y + 52,
                 gauge_w, stage_h - 96, state.depth_pct, phase_color)

    # ===== right: analytics column =====
    col_x = stage_x + stage_w + 20
    col_w = width - col_x - 20

    cv2.putText(canvas, "AI FITNESS ANALYTICS", (col_x, stage_y + 30),
                _FONT, 0.9, _TEXT, 2, cv2.LINE_AA)
    cv2.line(canvas, (col_x, stage_y + 42), (col_x + 200, stage_y + 42),
             _GREEN, 3, cv2.LINE_AA)
    _chip(canvas, col_x + col_w - 150, stage_y + 12,
          exercise.replace("_", " ").upper(), _YELLOW, filled=True)

    y = stage_y + 60

    # status panel
    status_color = _GREEN if state.status == "UP" else _RED
    _round_rect(canvas, col_x, y, col_w, 62, 10, _PANEL)
    cv2.rectangle(canvas, (col_x, y), (col_x + 6, y + 62), status_color, -1)
    cv2.putText(canvas, "CURRENT STATUS", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, state.status, (col_x + 20, y + 50),
                _FONT, 0.92, status_color, 2, cv2.LINE_AA)
    y += 76

    # count tile + angle dial tile
    tile_w = (col_w - 14) // 2
    _round_rect(canvas, col_x, y, tile_w, 128, 10, _PANEL)
    cv2.putText(canvas, "COUNT", (col_x + 20, y + 26), _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, str(state.rep_count), (col_x + 18, y + 94),
                _FONT, 2.0, _TEXT, 4, cv2.LINE_AA)
    cv2.putText(canvas, f"incomplete  {state.incomplete_count}", (col_x + 20, y + 116),
                _FONT, 0.44, _MUTE, 1, cv2.LINE_AA)

    dial_x = col_x + tile_w + 14
    _round_rect(canvas, dial_x, y, tile_w, 128, 10, _PANEL)
    cv2.putText(canvas, "ANGLE", (dial_x + 20, y + 26), _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    _angle_dial(canvas, dial_x + tile_w // 2, y + 88, 42, state.current_angle, phase_color)
    y += 142

    # movement phase panel
    _round_rect(canvas, col_x, y, col_w, 74, 10, _PANEL)
    cv2.rectangle(canvas, (col_x, y), (col_x + 6, y + 74), phase_color, -1)
    cv2.putText(canvas, "MOVEMENT PHASE", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, state.phase, (col_x + 20, y + 50),
                _FONT, 0.8, phase_color, 2, cv2.LINE_AA)
    cv2.putText(canvas, _PHASE_DESC.get(state.phase, ""), (col_x + 20, y + 68),
                _FONT, 0.44, _MUTE, 1, cv2.LINE_AA)
    y += 88

    # tracking quality bar
    track_color = _GREEN if state.tracking_ok else _RED
    _round_rect(canvas, col_x, y, col_w, 52, 10, _PANEL)
    cv2.putText(canvas, "TRACKING QUALITY", (col_x + 20, y + 22),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    _bar(canvas, col_x + 20, y + 32, col_w - 40, 12, state.tracking_quality, track_color)
    y += 66

    # coaching ribbon
    _round_rect(canvas, col_x, y, col_w, 68, 10, _PANEL_HI)
    cv2.rectangle(canvas, (col_x, y), (col_x + 6, y + 68), _YELLOW, -1)
    cv2.putText(canvas, "COACHING", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, _truncate(state.cue, 46), (col_x + 20, y + 50),
                _FONT, 0.58, _TEXT, 1, cv2.LINE_AA)
    y += 82

    # phase timeline strip
    _round_rect(canvas, col_x, y, col_w, 110, 10, _PANEL)
    cv2.putText(canvas, "PHASE TIMELINE", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    _phase_timeline(canvas, col_x + 20, y + 40, col_w - 40, phases, state.phase)

    return canvas


def _round_rect(canvas: np.ndarray, x: int, y: int, w: int, h: int, r: int, color) -> None:
    r = max(0, min(r, w // 2, h // 2))
    if w <= 0 or h <= 0:
        return
    cv2.rectangle(canvas, (x + r, y), (x + w - r, y + h), color, -1)
    cv2.rectangle(canvas, (x, y + r), (x + w, y + h - r), color, -1)
    for cx, cy in ((x + r, y + r), (x + w - r, y + r),
                   (x + r, y + h - r), (x + w - r, y + h - r)):
        cv2.circle(canvas, (cx, cy), r, color, -1, cv2.LINE_AA)


def _chip(canvas: np.ndarray, x: int, y: int, text: str, color, filled: bool = False) -> None:
    (tw, th), _ = cv2.getTextSize(text, _FONT, 0.42, 1)
    pad = 8
    if filled:
        _round_rect(canvas, x, y, tw + 2 * pad, th + 2 * pad, 6, color)
        cv2.putText(canvas, text, (x + pad, y + th + pad - 1),
                    _FONT, 0.42, _BG, 1, cv2.LINE_AA)
    else:
        cv2.putText(canvas, text, (x, y + th + pad - 1),
                    _FONT, 0.42, color, 1, cv2.LINE_AA)


def _bar(canvas: np.ndarray, x: int, y: int, w: int, h: int, fraction: float, color) -> None:
    frac = max(0.0, min(1.0, float(fraction)))
    _round_rect(canvas, x, y, w, h, h // 2, _BG)
    if frac > 0:
        _round_rect(canvas, x, y, max(h, int(w * frac)), h, h // 2, color)
    cv2.putText(canvas, f"{frac * 100:.0f}%", (x + w - 42, y - 4),
                _FONT, 0.42, _TEXT, 1, cv2.LINE_AA)


def _depth_gauge(canvas: np.ndarray, x: int, y: int, w: int, h: int,
                 depth_pct: float, color) -> None:
    frac = max(0.0, min(1.0, depth_pct / 100.0))
    _round_rect(canvas, x, y, w, h, w // 2, _BG)
    fill_h = int(h * frac)
    if fill_h > 0:
        _round_rect(canvas, x, y + h - fill_h, w, fill_h, w // 2, color)
    cv2.putText(canvas, "DEPTH", (x - 4, y + h + 18), _FONT, 0.4, _MUTE, 1, cv2.LINE_AA)


def _angle_dial(canvas: np.ndarray, cx: int, cy: int, radius: int,
                angle: float | None, color) -> None:
    # Top half-ring gauge: joint flexion 0..180 deg.
    cv2.ellipse(canvas, (cx, cy), (radius, radius), 0, 180, 360, _BG, 8, cv2.LINE_AA)
    if angle is not None:
        frac = max(0.0, min(1.0, float(angle) / 180.0))
        cv2.ellipse(canvas, (cx, cy), (radius, radius), 0,
                    180, 180 + 180 * frac, color, 8, cv2.LINE_AA)
    text = "--" if angle is None else f"{angle:.0f}"
    (tw, _), _ = cv2.getTextSize(text, _FONT, 0.9, 2)
    cv2.putText(canvas, text, (cx - tw // 2, cy + 4), _FONT, 0.9, _TEXT, 2, cv2.LINE_AA)
    cv2.putText(canvas, "deg", (cx - 13, cy + 24), _FONT, 0.4, _MUTE, 1, cv2.LINE_AA)


def _phase_timeline(canvas: np.ndarray, x: int, y: int, w: int,
                    phases: list[str], current: str) -> None:
    n = max(1, len(phases))
    gap = 8
    seg = (w - gap * (n - 1)) // n
    for i, name in enumerate(phases):
        sx = x + i * (seg + gap)
        color = _PHASE_COLOR.get(name, _MUTE)
        active = name == current
        _round_rect(canvas, sx, y, seg, 30, 6, color if active else _PANEL_HI)
        if active:
            cv2.rectangle(canvas, (sx, y), (sx + seg, y + 30), _TEXT, 1, cv2.LINE_AA)
        label = name if len(name) <= 9 else name[:8] + "."
        (tw, _), _ = cv2.getTextSize(label, _FONT, 0.36, 1)
        txt_color = _BG if active else _MUTE
        cv2.putText(canvas, label, (sx + max(4, (seg - tw) // 2), y + 20),
                    _FONT, 0.36, txt_color, 1, cv2.LINE_AA)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "."


def _draw_skeleton(canvas: np.ndarray, x0: int, y0: int, w: int, h: int,
                   joints: list[Any], color) -> None:
    # Project 3D joints to a 2D side view: horizontal = x_mm, vertical = z_mm.
    pts: list[tuple[float, float] | None] = []
    for j in joints:
        if j is None or len(j) < 3:
            pts.append(None)
        else:
            pts.append((float(j[0]), float(j[2])))
    valid = [p for p in pts if p is not None]
    if len(valid) < 2:
        msg = "WAITING FOR POSE"
        (tw, _), _ = cv2.getTextSize(msg, _FONT, 0.7, 2)
        cv2.putText(canvas, msg, (x0 + (w - tw) // 2, y0 + h // 2),
                    _FONT, 0.7, _MUTE, 2, cv2.LINE_AA)
        return

    xs = [p[0] for p in valid]
    zs = [p[1] for p in valid]
    span_x = max(1.0, max(xs) - min(xs))
    span_z = max(1.0, max(zs) - min(zs))
    pad = 40
    scale = min((w - 2 * pad) / span_x, (h - 2 * pad) / span_z)
    off_x = x0 + (w - span_x * scale) / 2.0
    off_y = y0 + (h - span_z * scale) / 2.0

    def to_px(p):
        px = int(off_x + (p[0] - min(xs)) * scale)
        py = int(off_y + (max(zs) - p[1]) * scale)  # flip: z up -> y down
        return px, py

    screen = [to_px(p) if p is not None else None for p in pts]
    for a, b in _SKELETON_EDGES:
        if screen[a] is not None and screen[b] is not None:
            cv2.line(canvas, screen[a], screen[b], color, 3, cv2.LINE_AA)
    for s in screen:
        if s is not None:
            cv2.circle(canvas, s, 6, _BG, -1, cv2.LINE_AA)
            cv2.circle(canvas, s, 6, _TEXT, 2, cv2.LINE_AA)
```

- [ ] **Step 4: Run the dashboard tests to verify they pass**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/test_live_trainer.py -v`
Expected: PASS — all `RepCounter` and `Dashboard` tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/project_cam/assessment/live_trainer/dashboard.py tests/test_live_trainer.py
git commit -m "feat: add OpenCV dashboard renderer for live trainer"
```

---

### Task 4: UDP receive loop and CLI entry point

**Files:**
- Create: `src/project_cam/assessment/live_trainer/__main__.py`

- [ ] **Step 1: Implement `__main__.py`**

Create `src/project_cam/assessment/live_trainer/__main__.py`:

```python
"""CLI + UDP receive loop for the live push-up / squat trainer.

Run: PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.live_trainer \
         --host 127.0.0.1 --port 5015 --exercise squat
"""

from __future__ import annotations

import argparse
import json
import socket
import time

import cv2

from ..io import normalize_frame
from ..kinematics import frame_kinematics
from ..rules import DEFAULT_CONFIG_PATH, exercise_rules, load_rules
from .dashboard import render_dashboard
from .rep_state import make_counter


def run(host: str, port: int, exercise: str, config_path: str, fps: float,
        log_jsonl: str | None = None) -> int:
    config = load_rules(config_path)
    rules = exercise_rules(config, exercise)
    counter = make_counter(exercise, rules)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(0.2)

    window = f"Project_Cam Live Trainer - {exercise}"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    log_fh = open(log_jsonl, "w", encoding="utf-8") if log_jsonl else None
    last_joints: list = [None] * 17
    count = 0
    print(f"[TRAINER] exercise={exercise}  listening on {host}:{port}")
    print("[TRAINER] press 'q' or ESC in the window to quit")
    try:
        while True:
            try:
                data, _addr = sock.recvfrom(65535)
                packet = json.loads(data.decode("utf-8"))
                if isinstance(packet, dict) and packet.get("type") == "joints":
                    frame = normalize_frame(packet, index=count,
                                            default_fps=fps, source="udp")
                    metrics = frame_kinematics(frame)
                    state = counter.update(metrics)
                    last_joints = frame["joints"]
                    count += 1
                    if log_fh is not None:
                        log_fh.write(json.dumps({
                            "frame": frame["frame_index"],
                            "time_s": frame["time_s"],
                            "rep_count": state.rep_count,
                            "incomplete_count": state.incomplete_count,
                            "phase": state.phase,
                            "angle": state.current_angle,
                            "tracking_quality": state.tracking_quality,
                            "cue": state.cue,
                        }) + "\n")
            except socket.timeout:
                pass
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            canvas = render_dashboard(exercise, counter.state, last_joints)
            cv2.imshow(window, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        if log_fh is not None:
            log_fh.close()
        cv2.destroyAllWindows()
    print(f"[TRAINER] stopped. reps={counter.state.rep_count} "
          f"incomplete={counter.state.incomplete_count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live push-up / squat trainer.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5015)
    ap.add_argument("--exercise", choices=["squat", "push_up"], default="squat")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--log-jsonl", default=None,
                    help="Optional path to record per-frame trainer state as JSONL.")
    args = ap.parse_args(argv)
    return run(host=args.host, port=args.port, exercise=args.exercise,
               config_path=args.config, fps=args.fps, log_jsonl=args.log_jsonl)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify the CLI parses and imports cleanly**

Run: `PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.live_trainer --help`
Expected: PASS — argparse prints usage showing `--host`, `--port`, `--exercise {squat,push_up}`, `--config`, `--fps`, `--log-jsonl`. No import errors.

- [ ] **Step 3: Commit**

```bash
git add src/project_cam/assessment/live_trainer/__main__.py
git commit -m "feat: add UDP receive loop and CLI for live trainer"
```

---

### Task 5: Shell wrapper

**Files:**
- Create: `apps/athlete_assessment/run_live_trainer.sh`

- [ ] **Step 1: Create the wrapper script**

Create `apps/athlete_assessment/run_live_trainer.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

EXERCISE="${1:-squat}"
HOST="${PROJECT_CAM_ASSESSMENT_HOST:-127.0.0.1}"
PORT="${PROJECT_CAM_ASSESSMENT_PORT:-5015}"

PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.live_trainer \
  --host "$HOST" \
  --port "$PORT" \
  --exercise "$EXERCISE" \
  "${@:2}"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x apps/athlete_assessment/run_live_trainer.sh`

- [ ] **Step 3: Verify the wrapper forwards arguments**

Run: `apps/athlete_assessment/run_live_trainer.sh squat --help`
Expected: PASS — argparse usage is printed (the wrapper resolves the project root, picks `squat`, and forwards `--help`).

- [ ] **Step 4: Run the full test suite one final time**

Run: `PYTHONPATH=src ./venv/bin/python -m pytest tests/ -v`
Expected: PASS — every test passes, including `tests/test_live_trainer.py` and the updated `tests/test_assessment_kairat_hardening.py`.

- [ ] **Step 5: Commit**

```bash
git add apps/athlete_assessment/run_live_trainer.sh
git commit -m "feat: add run_live_trainer.sh wrapper for the live trainer"
```

---

### Task 6: Manual garage acceptance (no code — operator checklist)

This task is run on the physical 4-camera rig. It produces no commits; it validates the live behaviour and surfaces threshold tuning needs.

- [ ] **Step 1: Start the live tracker (Terminal 1)**

Run: `apps/athlete_assessment/run_live_tracking_for_assessment.sh`
Expected: The 4-cam viewer opens; console shows `[INFO] UDP target stream enabled -> 127.0.0.1:5015`.

- [ ] **Step 2: Start the trainer for squats (Terminal 2)**

Run: `apps/athlete_assessment/run_live_trainer.sh squat`
Expected: The dashboard window opens. With nobody in the arena it shows `TRACKING` near 0% and the cue `Low tracking - step fully into camera view`.

- [ ] **Step 3: Perform 5 squats**

Stand in the arena, perform 5 full squats. Watch the dashboard.
Expected: `COUNT` reaches 5 (or within 1 — record the exact number). `MOVEMENT PHASE` cycles STANDING -> DESCENDING -> BOTTOM -> ASCENDING. `TRACKING` stays above 50%. If count is off by more than 1, note the observed knee angles and tune `enter_angle_deg` / `descent_angle_deg` / `min_pelvis_travel_mm` in `configs/exercises/football_academy_u10.yaml` under `squat`.

- [ ] **Step 4: Perform 3 deliberately shallow squats**

Expected: `COUNT` does not increase; `incomplete` rises and the cue reads `Shallow rep - go deeper`.

- [ ] **Step 5: Restart the trainer for push-ups and perform 5 push-ups**

Run: `apps/athlete_assessment/run_live_trainer.sh push_up`
Perform 5 floor push-ups within camera view.
Expected: `COUNT` reaches 5 (or within 1). If wrists/ankles are occluded on the floor, `TRACKING` drops and reps are skipped rather than miscounted — if so, note it (camera placement / athlete position is the fix, per the spec assumptions). Deliberately sag the hips during one rep and confirm the cue reads `Trunk bent ... - keep body straight`.

- [ ] **Step 6: Confirm the live tracker is unaffected**

Expected: While the trainer runs, the Terminal 1 viewer FPS and UDP flow remain stable (the trainer is a pure UDP consumer and does not back-pressure the sender). Record the tracker FPS before and during trainer use.

---

## Notes for the Executor

- `tests/test_live_trainer.py` is fully self-contained — it builds synthetic COCO-17 joint frames and runs the real `frame_kinematics`, so no camera, GPU, or UDP socket is needed for any unit test.
- The dashboard tests construct canvases headlessly; they never call `cv2.imshow`, so they pass in CI without a display.
- Thresholds in the `push_up` config block (and the new squat `descent_angle_deg`) are deliberately conservative starting points. Task 6 is expected to surface real numbers; tuning them is a config-only change, no code edit.
- If `cv2.namedWindow` fails on a headless executor while running `__main__.py`, that is expected — `__main__.py` is exercised only via `--help` in Task 4 Step 2 and on the physical rig in Task 6.
