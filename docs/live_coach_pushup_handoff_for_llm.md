# Project_Cam Live Coach Push-Up Debug Handoff

This file is a handoff prompt/context bundle for another LLM or engineer.
It describes the current Project_Cam live coach work, the remaining push-up
visualization problem, and the relevant code paths to inspect and fix.

## Goal

Fix the live push-up coach overlay so it looks correct and useful:

- athlete should be visible in the selected camera ROI;
- skeleton should be attached to the athlete;
- knees/heels/ankles should not jump to wrong locations;
- push-up side view should be chosen instead of a visually confusing camera;
- floor/contact line should look like the athlete is grounded, not floating;
- angle labels should be readable and attached to correct joints;
- squat overlay must not regress, because squats currently look good.

## Current User-Observed Problem

The user ran:

```bash
cd /home/hanush/Desktop/Project_Cam
./apps/athlete_assessment/run_live_coach.sh push_up
```

The coach window opened. Screenshot showed:

- title: `Project_Cam Live Coach - push_up`;
- selected camera displayed as `camSouth`;
- athlete is lying near the bottom of the frame;
- overlay labels show `R elbow 75`, `L elbow 74`, `trunk 149`;
- status is `BOTTOM`, reps `0`;
- cue says `Trunk bent - keep body straight`;
- knees/heels/lower-body keypoints still look visually wrong or unreliable;
- skeleton lines appear attached partly correctly, but lower body and floor/contact
  guide are not convincing.

Important: the user is not necessarily asking for rep threshold tuning. The
main complaint is visual pose/keypoint quality in push-ups. Squats look good.

## Current Architecture

There are two live paths:

1. Old split mode:

```bash
./apps/athlete_assessment/run_live_tracking_for_assessment.sh
./apps/athlete_assessment/run_live_trainer.sh squat
./apps/athlete_assessment/run_live_trainer.sh push_up
```

This uses UDP joints and the OpenCV dashboard in:

- `src/project_cam/assessment/live_trainer/__main__.py`
- `src/project_cam/assessment/live_trainer/dashboard.py`
- `src/project_cam/assessment/live_trainer/rep_state.py`

2. New recommended single-process coach mode:

```bash
./apps/athlete_assessment/run_live_coach.sh squat
./apps/athlete_assessment/run_live_coach.sh push_up
```

This runs the 4-camera tracker and overlay in one process:

- `Parallel_working/scripts/live_4cam_arena_view_parallel.py`
- `src/project_cam/assessment/live_trainer/coach_overlay.py`

The single-process mode is preferred because it already has fresh camera frames,
2D YOLO pose, triangulated 3D joints, and rep state.

## Current Git State

At the time of this handoff, these files are changed/uncommitted:

```text
M Parallel_working/scripts/live_4cam_arena_view_parallel.py
M configs/exercises/football_academy_u10.yaml
M src/project_cam/assessment/live_trainer/__main__.py
M src/project_cam/assessment/live_trainer/dashboard.py
M src/project_cam/assessment/live_trainer/rep_state.py
M tests/test_live_trainer.py
?? apps/athlete_assessment/run_live_coach.sh
?? src/project_cam/assessment/live_trainer/coach_overlay.py
?? tests/test_live_coach_overlay.py
```

Do not revert these changes. They include the working squat fixes and new coach
overlay scaffolding.

## Relevant Code Files

Read these first:

```text
apps/athlete_assessment/run_live_coach.sh
Parallel_working/scripts/live_4cam_arena_view_parallel.py
src/project_cam/assessment/live_trainer/coach_overlay.py
src/project_cam/assessment/live_trainer/rep_state.py
tests/test_live_coach_overlay.py
tests/test_live_trainer.py
configs/exercises/football_academy_u10.yaml
```

Reference files for joint contract:

```text
src/project_cam/assessment/kinematics.py
src/project_cam/assessment/io.py
src/project_cam/assessment/joints.py
```

## Important Current Code Paths

### New launcher

File: `apps/athlete_assessment/run_live_coach.sh`

Relevant behavior:

```bash
PYTHONPATH=src ./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --no-world-y-mirror \
  --invert-y-axis-display \
  --no-track-ball \
  --pose-device cuda:0 \
  --pose-backend yolopose \
  --yolopose-model "$POSE_MODEL" \
  --width 1280 --height 720 --fps 15 \
  --pose-every 1 \
  --no-show-2d --no-show-3d \
  --viz-width 1180 --viz-height 720 \
  --coach-overlay \
  --coach-exercise "$EXERCISE"
```

### Coach CLI flags

File: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

Flags added:

```python
ap.add_argument("--coach-overlay", action=argparse.BooleanOptionalAction, default=False)
ap.add_argument("--coach-exercise", choices=["squat", "push_up"], default="squat")
ap.add_argument("--coach-zone-mm", default="")
```

### 3D projection into overlay

File: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

Current helper:

```python
def project_joints_to_overlay(joints, conf, cams, cam, extr, intr, roi, output_size, min_conf=0.35, min_cams=2):
    kpts = np.full((17, 2), np.nan, dtype=np.float32)
    scores = np.zeros((17,), dtype=np.float32)
    if cam not in extr or cam not in intr:
        return kpts, scores
    out_w, out_h = output_size
    sx = float(out_w) / max(1, roi.width)
    sy = float(out_h) / max(1, roi.height)
    joints_arr = np.asarray(joints, dtype=np.float64)
    conf_arr = np.asarray(conf, dtype=np.float64).reshape(-1)
    cams_arr = np.asarray(cams, dtype=np.int32).reshape(-1)
    for idx in range(min(17, len(joints_arr))):
        if idx >= len(conf_arr) or idx >= len(cams_arr):
            continue
        if conf_arr[idx] < min_conf or cams_arr[idx] < min_cams:
            continue
        pt = joints_arr[idx]
        if not np.isfinite(pt).all():
            continue
        try:
            uv = project_world_to_pixel(pt, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"])
        except Exception:
            continue
        if not np.isfinite(uv).all():
            continue
        kpts[idx] = [(float(uv[0]) - roi.x1) * sx, (float(uv[1]) - roi.y1) * sy]
        scores[idx] = float(np.clip(conf_arr[idx], 0.0, 1.0))
    return kpts, scores
```

### Overlay render call

File: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

The coach overlay currently:

1. selects a camera;
2. crops that camera;
3. projects 3D joints into crop coordinates;
4. repairs push-up lower-body keypoints;
5. renders overlay.

Relevant section:

```python
selected_cam = coach_select_best_camera(
    args.coach_exercise,
    joints_state,
    per_cam_pose,
    camera_positions,
    previous_camera=coach_prev_camera,
)

roi = coach_rois[selected_cam].update(src_frame.shape, pose_kpts, pose_scores)
crop, crop_kpts, _scale = coach_crop_frame_to_roi(
    src_frame, pose_kpts, roi, output_size=coach_output_size
)
projected_kpts, projected_scores = project_joints_to_overlay(
    joints_state,
    joints_conf_state,
    joints_cam_state,
    selected_cam,
    extr,
    intr,
    roi,
    coach_output_size,
)
overlay_kpts, overlay_scores = coach_repair_overlay_keypoints(
    args.coach_exercise,
    crop_kpts,
    pose_scores,
    projected_kpts,
    projected_scores,
)
coach_canvas = coach_render_overlay(
    crop,
    args.coach_exercise,
    coach_state,
    coach_metrics,
    overlay_kpts,
    overlay_scores,
    projected_floor=zone_poly,
)
```

### Camera selection

File: `src/project_cam/assessment/live_trainer/coach_overlay.py`

Current behavior:

```python
def select_best_camera(exercise, joints_3d, per_cam_pose, camera_positions, previous_camera=None, switch_margin=0.12):
    # Squats prefer front/back body view.
    # Push-ups prefer side body view.
    # Scores combine 3D body orientation with 2D pose confidence.
```

Hypothesis: this may still choose `camSouth` for push-ups even if it is visually
not the best camera. Camera selection needs better scoring for push-ups:

- prefer camera where shoulder-to-ankle body line has large horizontal span;
- reject/penalize camera where athlete is too close to bottom edge;
- reject/penalize camera where feet/knees are heavily occluded or confidence low;
- consider using projected 3D points to choose camera instead of only body axes;
- possibly allow `--coach-camera camEast|camWest|camNorth|camSouth` manual override.

### Current lower-body repair

File: `src/project_cam/assessment/live_trainer/coach_overlay.py`

Current repair logic:

```python
_PUSHUP_PROJECTED_REPAIR_JOINTS = (11, 12, 13, 14, 15, 16)

def repair_overlay_keypoints(exercise, raw_kpts, raw_scores, projected_kpts, projected_scores):
    pts = _coerce_kpts(raw_kpts)
    scores = _coerce_scores(raw_scores)
    if exercise != "push_up" or projected_kpts is None or projected_scores is None:
        return pts, scores

    proj_pts = _coerce_kpts(projected_kpts)
    proj_scores = _coerce_scores(projected_scores)
    for idx in _PUSHUP_PROJECTED_REPAIR_JOINTS:
        if _valid_joint(proj_pts, proj_scores, idx):
            pts[idx] = proj_pts[idx]
            scores[idx] = max(scores[idx], proj_scores[idx])
    return pts, scores
```

This helped but did not fully solve the visual issue in the screenshot.

## Current Test Commands

Use these commands after any fix:

```bash
cd /home/hanush/Desktop/Project_Cam
PYTHONPATH=src venv/bin/python -m py_compile \
  Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  src/project_cam/assessment/live_trainer/coach_overlay.py

PYTHONPATH=src venv/bin/python -m unittest discover -s tests -p 'test_live_coach_overlay.py' -v
PYTHONPATH=src venv/bin/python -m unittest discover -s tests -p 'test_live_trainer.py' -v
PYTHONPATH=src venv/bin/python -m unittest discover -s tests
```

Latest known result before this handoff:

```text
Ran 74 tests in ~2.1s
OK
```

## Likely Root Causes To Investigate

Do not blindly tune thresholds. First gather evidence.

### Root cause candidate 1: Wrong camera selected for push-ups

Observed selected camera: `camSouth`.

Possible issue:

- `select_best_camera()` chooses geometrically side-like camera, but visual crop is
  not actually the best push-up camera.
- Current scoring does not know if feet/knees are near frame edge or hidden.

Potential fix:

- Add camera-quality metrics for push-up:
  - torso/ankle horizontal span in 2D;
  - number of valid lower-body joints;
  - min distance of body bbox to image edges;
  - body bbox area not too small/not too huge;
  - projected 3D skeleton inside ROI.
- Add `--coach-camera` override for immediate manual debugging.
- Add `--coach-debug` overlay showing per-camera scores.

### Root cause candidate 2: 3D lower-body projection is still wrong

The code projects `joints_state` into the selected camera. If camera extrinsics,
Y mirror, or selected camera frame coordinate convention is inconsistent, projected
knees/heels can be offset.

Potential investigation:

- Draw both raw 2D keypoints and projected 3D keypoints in different colors for
  one debug run.
- Log pixel delta between raw and projected joints per camera.
- Check whether `--no-world-y-mirror` and display/UDP mirror conventions affect
  projected coach overlay.

### Root cause candidate 3: 3D triangulated knees/ankles are unreliable in push-up

Push-up feet/knees may be low, side-on, or occluded by body/floor. Multi-camera
triangulation may still be poor even if overlay projection is correct.

Potential investigation:

- Log `joints_conf_state` and `joints_cam_state` for joints 13,14,15,16.
- If camera count is often 2 but wrong, inspect per-camera raw keypoints.
- If camera count is low, tune camera view/model or use temporal/body-geometry constraints.

### Root cause candidate 4: ROI crop is still not push-up aware

ROI currently follows median of visible 2D keypoints. This prevents one bad heel
from dragging the crop, but it may crop off feet if the body is long horizontally.

Potential fix:

- For push-ups, ROI should center on shoulder/hip/ankle line and use a wider crop.
- Use fixed wide crop for push-ups, e.g. width 1120, height 520, rather than the
  current `min(args.width, 960)` by `min(args.height, 640)`.
- Or have exercise-specific ROI sizes.

## Recommended Next Implementation Plan

Implement in small test-driven steps:

1. Add tests for a push-up camera scorer:
   - camera with more valid lower-body points wins;
   - camera with body near bottom edge loses;
   - camera with larger shoulder-to-ankle horizontal span wins;
   - previous camera is kept only when score gap is small.

2. Add `--coach-camera` manual override:
   - if provided, skip auto camera selection;
   - this immediately lets the user try `camEast`, `camWest`, `camNorth`, `camSouth`.

3. Add `--coach-debug` mode:
   - print or overlay selected camera, per-camera score, lower-body valid count,
     2D confidence, 3D projection availability, ROI coordinates.

4. Add visual debug drawing:
   - raw 2D skeleton in thin blue;
   - projected 3D skeleton in thin yellow;
   - final repaired skeleton in thick red/green.
   This should be behind `--coach-debug` so normal UI stays clean.

5. Make push-up ROI wider and lower-body aware:
   - use exercise-specific ROI size;
   - for push-up, default crop should keep hands, shoulders, hips, knees, heels
     in frame and avoid crop jitter.

6. If projected 3D lower body is wrong:
   - verify mirror/extrinsics by projecting static known arena tag/floor corners;
   - compare raw vs projected joints per camera;
   - do not force projected joints unless they fall inside frame and are consistent
     with body geometry.

## Acceptance Criteria

Push-up overlay should satisfy:

- selected camera is visually suitable for side-view push-up;
- hands/shoulders/hips/knees/heels are visible in ROI;
- lower-body skeleton is not jumping to unrelated points;
- floor/contact line aligns with hands/feet, not through the torso;
- elbow/trunk labels are readable and not placed on top of the body;
- rep count/cues still update;
- squats remain visually good.

## Extra Context: Why Squats Work Better

Squats are upright and front-facing, so knees/ankles are easier for YOLO and
triangulation. Push-ups are harder:

- body is horizontal;
- knees/heels are low and can blend with floor/socks/background;
- side camera can occlude one side of the body;
- one bad foot point can distort skeleton/floor line;
- camera auto-selection must care about visual body layout, not just 3D body axis.

## Current Known Good Commands

Run squat:

```bash
./apps/athlete_assessment/run_live_coach.sh squat
```

Run push-up:

```bash
./apps/athlete_assessment/run_live_coach.sh push_up
```

Run old split mode if needed:

```bash
./apps/athlete_assessment/run_live_tracking_for_assessment.sh
./apps/athlete_assessment/run_live_trainer.sh push_up
```

## Suggested Prompt For Another LLM

Use this prompt:

```text
You are working in /home/hanush/Desktop/Project_Cam.

We built a Project_Cam live coach overlay for squats and push-ups. Squats look
good. Push-ups still look visually wrong: knees/heels/lower body are badly
detected or displayed. Screenshot shows the overlay selected camSouth, the body
is near bottom of frame, lower-body skeleton/floor line looks unreliable, and
labels show R elbow 75, L elbow 74, trunk 149, status BOTTOM.

Do not revert existing changes. Diagnose root cause systematically. Start by
reading:
- docs/live_coach_pushup_handoff_for_llm.md
- apps/athlete_assessment/run_live_coach.sh
- Parallel_working/scripts/live_4cam_arena_view_parallel.py
- src/project_cam/assessment/live_trainer/coach_overlay.py
- tests/test_live_coach_overlay.py

Main task:
Fix push-up visualization without regressing squats.

Focus areas:
1. Camera selection for push-up probably chooses a bad camera (`camSouth`).
2. Add manual --coach-camera override for debugging.
3. Add --coach-debug that shows camera scores and raw-vs-projected keypoints.
4. Make push-up ROI wider and body-line aware.
5. Validate projected 3D lower-body joints before using them.

Use TDD:
- Add tests before code changes.
- Run:
  PYTHONPATH=src venv/bin/python -m unittest discover -s tests -p 'test_live_coach_overlay.py' -v
  PYTHONPATH=src venv/bin/python -m unittest discover -s tests

Acceptance:
- push-up side view is stable;
- knees/heels are not jumping or attached to wrong places;
- body remains in frame;
- floor/contact guide aligns with hands/feet;
- squats still pass visually and tests still pass.
```


## Self-Contained Code Bundle

The other LLM may not have repository access. Paste this section together with the rest of the handoff. It contains the complete new files and the relevant tracker patch/snippets.

### Full file: `apps/athlete_assessment/run_live_coach.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

EXERCISE="${1:-squat}"
if [ "$#" -gt 0 ]; then
  shift
fi

POSE_MODEL="${PROJECT_CAM_POSE_MODEL:-yolo11m-pose.engine}"
if [ ! -f "$POSE_MODEL" ]; then
  POSE_MODEL="yolo11m-pose.pt"
fi

PYTHONPATH=src ./venv/bin/python Parallel_working/scripts/live_4cam_arena_view_parallel.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json \
  --dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt \
  --no-world-y-mirror \
  --invert-y-axis-display \
  --no-track-ball \
  --pose-device cuda:0 \
  --pose-backend yolopose \
  --yolopose-model "$POSE_MODEL" \
  --width 1280 --height 720 --fps 15 \
  --pose-every 1 \
  --viz-every 1 \
  --mosaic-every 2 \
  --no-show-2d --no-show-3d \
  --viz-backend cv2 \
  --viz-width 1180 --viz-height 720 \
  --ema-alpha 0.45 \
  --ema-snap-thresh-mm 80 \
  --display-smooth-alpha 0.45 \
  --joint-stale-frames 8 \
  --max-frame-age-ms 150 \
  --predict-ahead-ms 0 \
  --perf-log-every 60 \
  --coach-overlay \
  --coach-exercise "$EXERCISE" \
  "$@"
```

### Full file: `src/project_cam/assessment/live_trainer/coach_overlay.py`

```python
"""Camera-attached live coach overlay for the 4-camera trainer.

This module is intentionally pure OpenCV/numpy helper code: it does not open
cameras, windows, sockets, or config files. The tracker owns live frames and
passes the freshest 2D/3D pose into these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .rep_state import RepState


_FONT = cv2.FONT_HERSHEY_SIMPLEX

_TEXT = (245, 245, 245)
_MUTE = (165, 165, 172)
_DARK = (20, 22, 26)
_PANEL = (34, 36, 42)
_GREEN = (96, 215, 118)
_BLUE = (235, 178, 76)
_AMBER = (62, 190, 244)
_RED = (78, 86, 236)
_YELLOW = (88, 224, 238)

_SKELETON_EDGES = [
    (5, 7), (7, 9), (6, 8), (8, 10),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (5, 6), (11, 12), (5, 11), (6, 12),
]
_JOINTS_FOR_VALIDITY = (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
_PUSHUP_PROJECTED_REPAIR_JOINTS = (11, 12, 13, 14, 15, 16)

_PHASE_COLOR = {
    "STANDING": _GREEN, "TOP": _GREEN,
    "DESCENDING": _AMBER, "LOWERING": _AMBER,
    "BOTTOM": _RED,
    "ASCENDING": _BLUE, "PUSHING UP": _BLUE,
}


@dataclass(frozen=True)
class Roi:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) * 0.5, (self.y1 + self.y2) * 0.5)


@dataclass(frozen=True)
class AngleLabel:
    text: str
    anchor: tuple[int, int]
    color: tuple[int, int, int] = _YELLOW


class StableRoi:
    """Fixed-size crop that pans smoothly but never auto-zooms per frame."""

    def __init__(self, width: int = 720, height: int = 560, alpha: float = 0.18):
        self.width = int(width)
        self.height = int(height)
        self.alpha = float(max(0.01, min(1.0, alpha)))
        self._center: np.ndarray | None = None

    def update(self, frame_shape: tuple[int, ...], kpts: Any, scores: Any) -> Roi:
        h, w = int(frame_shape[0]), int(frame_shape[1])
        crop_w = min(max(1, self.width), w)
        crop_h = min(max(1, self.height), h)

        pose_center = _pose_center(kpts, scores)
        if pose_center is None:
            target = self._center if self._center is not None else np.array([w * 0.5, h * 0.5])
        else:
            target = pose_center

        if self._center is None:
            self._center = np.asarray(target, dtype=float)
        else:
            self._center = (1.0 - self.alpha) * self._center + self.alpha * np.asarray(target, dtype=float)

        cx = float(np.clip(self._center[0], crop_w * 0.5, w - crop_w * 0.5))
        cy = float(np.clip(self._center[1], crop_h * 0.5, h - crop_h * 0.5))
        self._center = np.array([cx, cy], dtype=float)

        x1 = int(round(cx - crop_w * 0.5))
        y1 = int(round(cy - crop_h * 0.5))
        x1 = max(0, min(w - crop_w, x1))
        y1 = max(0, min(h - crop_h, y1))
        return Roi(x1=x1, y1=y1, x2=x1 + crop_w, y2=y1 + crop_h)


def select_best_camera(
    exercise: str,
    joints_3d: list[Any] | np.ndarray,
    per_cam_pose: dict[str, tuple[Any, Any]],
    camera_positions: dict[str, Any],
    previous_camera: str | None = None,
    switch_margin: float = 0.12,
) -> str | None:
    """Choose the clearest exercise-appropriate camera.

    Squats prefer a front/back view of the body. Push-ups prefer a side view.
    Geometry comes from 3D body orientation and camera positions; 2D pose
    confidence gates out cameras that do not currently see the athlete.
    """
    if not per_cam_pose:
        return previous_camera

    center, lateral, forward = _body_axes(joints_3d)
    scores: dict[str, float] = {}
    for cam, pose in per_cam_pose.items():
        pose_score = _pose_quality(pose)
        if pose_score <= 0.0:
            continue
        align = 0.5
        cam_pos = _as_vec3(camera_positions.get(cam))
        if cam_pos is not None and center is not None and lateral is not None and forward is not None:
            view = center[:2] - cam_pos[:2]
            norm = float(np.linalg.norm(view))
            if norm > 1e-6:
                view /= norm
                desired = lateral if exercise == "push_up" else forward
                align = abs(float(np.dot(view, desired)))
        scores[cam] = 0.72 * align + 0.28 * pose_score

    if not scores:
        return previous_camera
    best = max(scores, key=scores.get)
    if previous_camera in scores:
        if scores[previous_camera] >= scores[best] * (1.0 - switch_margin):
            return previous_camera
    return best


def crop_frame_to_roi(
    frame: np.ndarray,
    kpts: Any,
    roi: Roi,
    output_size: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Crop frame to ROI and translate keypoints into crop coordinates.

    ``output_size`` is ``(width, height)``. When provided, the crop is resized
    and keypoints are scaled accordingly.
    """
    crop = frame[roi.y1:roi.y2, roi.x1:roi.x2].copy()
    pts = _coerce_kpts(kpts)
    pts[:, 0] -= roi.x1
    pts[:, 1] -= roi.y1
    scale = 1.0
    if output_size is not None and crop.size:
        out_w, out_h = int(output_size[0]), int(output_size[1])
        sx = out_w / max(1, roi.width)
        sy = out_h / max(1, roi.height)
        crop = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        pts[:, 0] *= sx
        pts[:, 1] *= sy
        scale = min(sx, sy)
    return crop, pts, scale


def repair_overlay_keypoints(
    exercise: str,
    raw_kpts: Any,
    raw_scores: Any,
    projected_kpts: Any | None,
    projected_scores: Any | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Prefer stable projected 3D joints where raw 2D pose is weak.

    Push-ups are the important case: single-camera YOLO frequently misplaces
    knees/heels when the athlete is side-on and close to the floor. The ROI
    still follows raw 2D pose, but drawing can use reprojected multi-camera
    joints for the lower body when they are available.
    """
    pts = _coerce_kpts(raw_kpts)
    scores = _coerce_scores(raw_scores)
    if exercise != "push_up" or projected_kpts is None or projected_scores is None:
        return pts, scores

    proj_pts = _coerce_kpts(projected_kpts)
    proj_scores = _coerce_scores(projected_scores)
    for idx in _PUSHUP_PROJECTED_REPAIR_JOINTS:
        if _valid_joint(proj_pts, proj_scores, idx):
            pts[idx] = proj_pts[idx]
            scores[idx] = max(scores[idx], proj_scores[idx])
    return pts, scores


def collect_angle_labels(
    exercise: str,
    metrics: dict[str, Any],
    kpts: Any,
    scores: Any,
) -> list[AngleLabel]:
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    angles = metrics.get("angles_deg") or {}
    labels: list[AngleLabel] = []

    def add(name: str, joint_idx: int, label: str) -> None:
        value = _finite_float(angles.get(name))
        if value is None or not _valid_joint(pts, scr, joint_idx):
            return
        x, y = pts[joint_idx]
        labels.append(AngleLabel(f"{label} {value:.0f}", (int(x) + 10, int(y) - 10)))

    if exercise == "push_up":
        add("left_elbow", 7, "L elbow")
        add("right_elbow", 8, "R elbow")
        trunk_vals = [
            _finite_float(angles.get("left_trunk_to_leg")),
            _finite_float(angles.get("right_trunk_to_leg")),
        ]
        trunk_present = [v for v in trunk_vals if v is not None]
        hips = [idx for idx in (11, 12) if _valid_joint(pts, scr, idx)]
        if trunk_present and hips:
            anchor = np.mean([pts[idx] for idx in hips], axis=0)
            labels.append(AngleLabel(f"trunk {np.mean(trunk_present):.0f}", (int(anchor[0]) + 12, int(anchor[1]) + 4)))
    else:
        add("left_knee", 13, "L knee")
        add("right_knee", 14, "R knee")
    return labels


def render_coach_overlay(
    frame: np.ndarray,
    exercise: str,
    state: RepState,
    metrics: dict[str, Any],
    kpts: Any,
    scores: Any,
    projected_floor: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    """Draw live coach graphics over a camera frame."""
    canvas = frame.copy()
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    phase_color = _PHASE_COLOR.get(state.phase, _MUTE)
    valid_count = sum(1 for idx in _JOINTS_FOR_VALIDITY if _valid_joint(pts, scr, idx))

    _draw_header(canvas, exercise, state, phase_color)
    if valid_count < 5 or not state.tracking_ok:
        _draw_waiting(canvas, "STEP INTO COACH ZONE" if valid_count < 5 else "LOW TRACKING")
        return canvas

    _draw_floor_guides(canvas, exercise, pts, scr, projected_floor)
    _draw_skeleton(canvas, pts, scr, phase_color)
    for label in collect_angle_labels(exercise, metrics, pts, scr):
        _draw_label(canvas, label)
    _draw_depth_meter(canvas, state.depth_pct, phase_color)
    _draw_cue(canvas, state.cue)
    return canvas


def _draw_header(canvas: np.ndarray, exercise: str, state: RepState, color) -> None:
    h, w = canvas.shape[:2]
    cv2.rectangle(canvas, (0, 0), (w, 86), _DARK, -1)
    title = "LIVE COACH"
    cv2.putText(canvas, title, (22, 34), _FONT, 0.9, _TEXT, 2, cv2.LINE_AA)
    cv2.putText(canvas, exercise.replace("_", " ").upper(), (22, 66), _FONT, 0.62, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, f"REPS {state.rep_count}", (w - 210, 34), _FONT, 0.78, _TEXT, 2, cv2.LINE_AA)
    cv2.putText(canvas, state.phase, (w - 210, 66), _FONT, 0.58, color, 2, cv2.LINE_AA)
    cv2.line(canvas, (22, 80), (min(w - 22, 270), 80), color, 4, cv2.LINE_AA)


def _draw_waiting(canvas: np.ndarray, message: str) -> None:
    h, w = canvas.shape[:2]
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 86), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.42, canvas, 0.58, 0, canvas)
    (tw, _), _ = cv2.getTextSize(message, _FONT, 0.95, 2)
    cv2.putText(canvas, message, ((w - tw) // 2, h // 2), _FONT, 0.95, _YELLOW, 2, cv2.LINE_AA)


def _draw_floor_guides(
    canvas: np.ndarray,
    exercise: str,
    pts: np.ndarray,
    scores: np.ndarray,
    projected_floor: list[tuple[float, float]] | None,
) -> None:
    if projected_floor and len(projected_floor) >= 2:
        poly = np.asarray(projected_floor, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [poly], isClosed=True, color=(70, 90, 96), thickness=2, lineType=cv2.LINE_AA)

    if exercise == "push_up":
        ground_ids = [idx for idx in (9, 10, 15, 16) if _valid_joint(pts, scores, idx)]
    else:
        ground_ids = [idx for idx in (15, 16) if _valid_joint(pts, scores, idx)]
    if not ground_ids:
        return
    y = int(np.median([pts[idx][1] for idx in ground_ids]))
    x_values = [pts[idx][0] for idx in ground_ids]
    x1 = int(max(0, min(x_values) - 120))
    x2 = int(min(canvas.shape[1] - 1, max(x_values) + 120))
    cv2.line(canvas, (x1, y), (x2, y), (76, 210, 228), 3, cv2.LINE_AA)
    cv2.line(canvas, (x1, y + 12), (x2, y + 12), (44, 94, 104), 1, cv2.LINE_AA)


def _draw_skeleton(canvas: np.ndarray, pts: np.ndarray, scores: np.ndarray, color) -> None:
    for a, b in _SKELETON_EDGES:
        if _valid_joint(pts, scores, a) and _valid_joint(pts, scores, b):
            cv2.line(canvas, _pt(pts[a]), _pt(pts[b]), color, 5, cv2.LINE_AA)
            cv2.line(canvas, _pt(pts[a]), _pt(pts[b]), (16, 18, 20), 1, cv2.LINE_AA)
    for idx in _JOINTS_FOR_VALIDITY:
        if _valid_joint(pts, scores, idx):
            cv2.circle(canvas, _pt(pts[idx]), 7, _DARK, -1, cv2.LINE_AA)
            cv2.circle(canvas, _pt(pts[idx]), 7, _TEXT, 2, cv2.LINE_AA)
    if _valid_joint(pts, scores, 0):
        cv2.circle(canvas, _pt(pts[0]), 13, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, _pt(pts[0]), 13, _TEXT, 2, cv2.LINE_AA)


def _draw_label(canvas: np.ndarray, label: AngleLabel) -> None:
    x, y = label.anchor
    text = label.text
    (tw, th), _ = cv2.getTextSize(text, _FONT, 0.48, 1)
    x = max(4, min(canvas.shape[1] - tw - 16, x))
    y = max(100, min(canvas.shape[0] - 8, y))
    cv2.rectangle(canvas, (x - 6, y - th - 8), (x + tw + 8, y + 5), _PANEL, -1)
    cv2.putText(canvas, text, (x, y), _FONT, 0.48, label.color, 1, cv2.LINE_AA)


def _draw_depth_meter(canvas: np.ndarray, depth_pct: float, color) -> None:
    h, w = canvas.shape[:2]
    x = w - 38
    y1 = 112
    y2 = h - 34
    cv2.rectangle(canvas, (x, y1), (x + 16, y2), _DARK, -1)
    frac = max(0.0, min(1.0, float(depth_pct) / 100.0))
    fill = int((y2 - y1) * frac)
    if fill > 0:
        cv2.rectangle(canvas, (x, y2 - fill), (x + 16, y2), color, -1)
    cv2.putText(canvas, "DEPTH", (w - 88, y2 + 20), _FONT, 0.38, _MUTE, 1, cv2.LINE_AA)


def _draw_cue(canvas: np.ndarray, cue: str) -> None:
    if not cue:
        return
    h, w = canvas.shape[:2]
    y = h - 70
    cv2.rectangle(canvas, (18, y), (min(w - 52, 720), y + 44), _PANEL, -1)
    cv2.rectangle(canvas, (18, y), (25, y + 44), _YELLOW, -1)
    cv2.putText(canvas, cue[:54], (36, y + 29), _FONT, 0.58, _TEXT, 1, cv2.LINE_AA)


def _pose_center(kpts: Any, scores: Any) -> np.ndarray | None:
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    valid = np.isfinite(pts).all(axis=1) & (scr >= 0.35)
    if int(np.count_nonzero(valid)) < 3:
        return None
    return np.median(pts[valid], axis=0)


def _pose_quality(pose: tuple[Any, Any]) -> float:
    if pose is None:
        return 0.0
    kpts, scores = pose
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    valid = np.isfinite(pts).all(axis=1) & (scr >= 0.35)
    if int(np.count_nonzero(valid)) < 5:
        return 0.0
    return float(np.clip(np.mean(scr[valid]), 0.0, 1.0))


def _body_axes(joints_3d: list[Any] | np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    pts = _coerce_joints3d(joints_3d)
    valid = np.isfinite(pts).all(axis=1)
    if int(np.count_nonzero(valid)) < 2:
        return None, None, None
    center_ids = [idx for idx in (5, 6, 11, 12) if valid[idx]]
    center = np.mean(pts[center_ids] if center_ids else pts[valid], axis=0)
    lateral = None
    for left, right in ((11, 12), (5, 6)):
        if valid[left] and valid[right]:
            d = pts[right, :2] - pts[left, :2]
            norm = float(np.linalg.norm(d))
            if norm > 1e-6:
                lateral = d / norm
                break
    if lateral is None:
        return center, None, None
    forward = np.array([-lateral[1], lateral[0]], dtype=float)
    return center, lateral, forward


def _coerce_joints3d(joints: list[Any] | np.ndarray) -> np.ndarray:
    out = np.full((17, 3), np.nan, dtype=float)
    if joints is None:
        return out
    for idx, value in enumerate(list(joints)[:17]):
        if value is None:
            continue
        try:
            arr = np.asarray(value, dtype=float).reshape(-1)[:3]
        except (TypeError, ValueError):
            continue
        if arr.shape[0] == 3 and np.isfinite(arr).all():
            out[idx] = arr
    return out


def _coerce_kpts(kpts: Any) -> np.ndarray:
    out = np.full((17, 2), np.nan, dtype=float)
    try:
        arr = np.asarray(kpts, dtype=float)
    except (TypeError, ValueError):
        return out
    if arr.ndim < 2:
        return out
    rows = min(17, arr.shape[0])
    cols = min(2, arr.shape[1])
    out[:rows, :cols] = arr[:rows, :cols]
    return out


def _coerce_scores(scores: Any) -> np.ndarray:
    out = np.zeros((17,), dtype=float)
    try:
        arr = np.asarray(scores, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return out
    rows = min(17, arr.shape[0])
    out[:rows] = np.nan_to_num(arr[:rows], nan=0.0)
    return out


def _as_vec3(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float).reshape(-1)[:3]
    except (TypeError, ValueError):
        return None
    if arr.shape[0] < 3 or not np.isfinite(arr).all():
        return None
    return arr


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _valid_joint(pts: np.ndarray, scores: np.ndarray, idx: int, threshold: float = 0.35) -> bool:
    return bool(idx < len(pts) and idx < len(scores) and scores[idx] >= threshold and np.isfinite(pts[idx]).all())


def _pt(value: np.ndarray) -> tuple[int, int]:
    return int(round(float(value[0]))), int(round(float(value[1])))
```

### Full file: `tests/test_live_coach_overlay.py`

```python
import unittest

import numpy as np


def _body_3d():
    joints = [None] * 17
    joints[5] = [-220.0, 0.0, 1500.0]
    joints[6] = [220.0, 0.0, 1500.0]
    joints[7] = [-300.0, 0.0, 1100.0]
    joints[8] = [300.0, 0.0, 1100.0]
    joints[9] = [-330.0, 0.0, 760.0]
    joints[10] = [330.0, 0.0, 760.0]
    joints[11] = [-180.0, 0.0, 950.0]
    joints[12] = [180.0, 0.0, 950.0]
    joints[13] = [-180.0, 0.0, 520.0]
    joints[14] = [180.0, 0.0, 520.0]
    joints[15] = [-180.0, 0.0, 80.0]
    joints[16] = [180.0, 0.0, 80.0]
    joints[0] = [0.0, 0.0, 1720.0]
    return joints


def _pose_2d(center_x=500.0, center_y=340.0, scale=1.0):
    kpts = np.full((17, 2), np.nan, dtype=np.float32)
    scores = np.zeros((17,), dtype=np.float32)
    points = {
        0: (center_x, center_y - 230 * scale),
        5: (center_x - 95 * scale, center_y - 150 * scale),
        6: (center_x + 95 * scale, center_y - 150 * scale),
        7: (center_x - 130 * scale, center_y - 55 * scale),
        8: (center_x + 130 * scale, center_y - 55 * scale),
        9: (center_x - 150 * scale, center_y + 50 * scale),
        10: (center_x + 150 * scale, center_y + 50 * scale),
        11: (center_x - 70 * scale, center_y + 10 * scale),
        12: (center_x + 70 * scale, center_y + 10 * scale),
        13: (center_x - 72 * scale, center_y + 155 * scale),
        14: (center_x + 72 * scale, center_y + 155 * scale),
        15: (center_x - 75 * scale, center_y + 295 * scale),
        16: (center_x + 75 * scale, center_y + 295 * scale),
    }
    for idx, pt in points.items():
        kpts[idx] = pt
        scores[idx] = 0.94
    return kpts, scores


class CoachCameraSelectionTests(unittest.TestCase):
    def test_squat_prefers_front_camera_from_body_orientation(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        camera_positions = {
            "camFront": np.array([0.0, -3200.0, 1700.0]),
            "camSide": np.array([3200.0, 0.0, 1700.0]),
        }
        per_cam_pose = {
            "camFront": _pose_2d(),
            "camSide": _pose_2d(),
        }

        chosen = select_best_camera("squat", _body_3d(), per_cam_pose, camera_positions)

        self.assertEqual(chosen, "camFront")

    def test_pushup_prefers_side_camera_from_body_orientation(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        camera_positions = {
            "camFront": np.array([0.0, -3200.0, 1700.0]),
            "camSide": np.array([3200.0, 0.0, 1700.0]),
        }
        per_cam_pose = {
            "camFront": _pose_2d(),
            "camSide": _pose_2d(),
        }

        chosen = select_best_camera("push_up", _body_3d(), per_cam_pose, camera_positions)

        self.assertEqual(chosen, "camSide")

    def test_camera_selection_keeps_previous_camera_on_small_score_changes(self):
        from project_cam.assessment.live_trainer.coach_overlay import select_best_camera

        camera_positions = {
            "camA": np.array([0.0, -3200.0, 1700.0]),
            "camB": np.array([0.0, -3000.0, 1700.0]),
        }
        pose_a = _pose_2d()
        pose_b = _pose_2d()
        pose_b[1][:] = np.minimum(1.0, pose_b[1] + 0.03)

        chosen = select_best_camera(
            "squat",
            _body_3d(),
            {"camA": pose_a, "camB": pose_b},
            camera_positions,
            previous_camera="camA",
        )

        self.assertEqual(chosen, "camA")


class CoachRoiTests(unittest.TestCase):
    def test_roi_stays_in_frame_and_uses_fixed_size_after_lock(self):
        from project_cam.assessment.live_trainer.coach_overlay import StableRoi

        roi = StableRoi(width=420, height=360, alpha=0.25)
        kpts_a, scores_a = _pose_2d(center_x=450.0, scale=0.8)
        kpts_b, scores_b = _pose_2d(center_x=900.0, scale=1.35)

        first = roi.update((720, 1280, 3), kpts_a, scores_a)
        second = roi.update((720, 1280, 3), kpts_b, scores_b)

        self.assertEqual(first.width, 420)
        self.assertEqual(first.height, 360)
        self.assertEqual(second.width, 420)
        self.assertEqual(second.height, 360)
        self.assertGreaterEqual(second.x1, 0)
        self.assertGreaterEqual(second.y1, 0)
        self.assertLessEqual(second.x2, 1280)
        self.assertLessEqual(second.y2, 720)
        self.assertLess(second.center[0], 900.0)

    def test_roi_center_is_not_dragged_by_one_bad_heel_keypoint(self):
        from project_cam.assessment.live_trainer.coach_overlay import StableRoi

        roi = StableRoi(width=420, height=360, alpha=1.0)
        kpts, scores = _pose_2d(center_x=650.0, center_y=360.0, scale=0.8)
        kpts[16] = [40.0, 40.0]
        scores[16] = 0.99

        locked = roi.update((720, 1280, 3), kpts, scores)

        self.assertGreater(locked.center[0], 520.0)


class CoachOverlayRenderingTests(unittest.TestCase):
    def test_pushup_overlay_prefers_projected_lower_body_keypoints(self):
        from project_cam.assessment.live_trainer.coach_overlay import repair_overlay_keypoints

        raw_kpts, raw_scores = _pose_2d()
        projected_kpts = np.full((17, 2), np.nan, dtype=np.float32)
        projected_scores = np.zeros((17,), dtype=np.float32)
        projected_kpts[13] = [410.0, 420.0]
        projected_kpts[14] = [510.0, 420.0]
        projected_kpts[15] = [390.0, 520.0]
        projected_kpts[16] = [530.0, 520.0]
        projected_scores[[13, 14, 15, 16]] = 0.95
        raw_kpts[15] = [80.0, 80.0]
        raw_kpts[16] = [90.0, 85.0]

        repaired_kpts, repaired_scores = repair_overlay_keypoints(
            "push_up", raw_kpts, raw_scores, projected_kpts, projected_scores
        )

        self.assertTrue(np.allclose(repaired_kpts[15], [390.0, 520.0]))
        self.assertTrue(np.allclose(repaired_kpts[16], [530.0, 520.0]))
        self.assertAlmostEqual(float(repaired_scores[15]), 0.95)
        self.assertTrue(np.allclose(repaired_kpts[7], raw_kpts[7]))

    def test_angle_labels_include_squat_knees(self):
        from project_cam.assessment.live_trainer.coach_overlay import collect_angle_labels

        kpts, scores = _pose_2d()
        metrics = {"angles_deg": {"left_knee": 96.0, "right_knee": 101.0}}

        labels = collect_angle_labels("squat", metrics, kpts, scores)
        texts = [label.text for label in labels]

        self.assertIn("L knee 96", texts)
        self.assertIn("R knee 101", texts)

    def test_angle_labels_include_pushup_elbows_and_trunk(self):
        from project_cam.assessment.live_trainer.coach_overlay import collect_angle_labels

        kpts, scores = _pose_2d()
        metrics = {
            "angles_deg": {
                "left_elbow": 88.0,
                "right_elbow": 91.0,
                "left_trunk_to_leg": 172.0,
                "right_trunk_to_leg": 174.0,
            }
        }

        labels = collect_angle_labels("push_up", metrics, kpts, scores)
        texts = [label.text for label in labels]

        self.assertIn("L elbow 88", texts)
        self.assertIn("R elbow 91", texts)
        self.assertIn("trunk 173", texts)

    def test_render_overlay_returns_canvas_and_draws_floor_guides(self):
        from project_cam.assessment.live_trainer.coach_overlay import render_coach_overlay
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.full((720, 1280, 3), 38, dtype=np.uint8)
        kpts, scores = _pose_2d()
        state = RepState(rep_count=2, status="DOWN", phase="BOTTOM",
                         current_angle=96.0, depth_pct=82.0,
                         tracking_quality=0.9, tracking_ok=True,
                         cue="Good rep")
        metrics = {"angles_deg": {"left_knee": 96.0, "right_knee": 101.0}}

        canvas = render_coach_overlay(frame, "squat", state, metrics, kpts, scores)

        self.assertEqual(canvas.shape, frame.shape)
        self.assertEqual(canvas.dtype, np.uint8)
        self.assertGreater(np.count_nonzero(canvas != frame), 1000)

    def test_render_overlay_handles_missing_pose_without_crashing(self):
        from project_cam.assessment.live_trainer.coach_overlay import render_coach_overlay
        from project_cam.assessment.live_trainer.rep_state import RepState

        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        kpts = np.full((17, 2), np.nan, dtype=np.float32)
        scores = np.zeros((17,), dtype=np.float32)

        canvas = render_coach_overlay(frame, "push_up", RepState(), {}, kpts, scores)

        self.assertEqual(canvas.shape, frame.shape)


if __name__ == "__main__":
    unittest.main()
```

### Relevant patch: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

This is a patch against the current base tracker file. It shows every coach-overlay integration point without pasting the full 2797-line tracker.

```diff
diff --git a/Parallel_working/scripts/live_4cam_arena_view_parallel.py b/Parallel_working/scripts/live_4cam_arena_view_parallel.py
index 41712ed9..f6402449 100644
--- a/Parallel_working/scripts/live_4cam_arena_view_parallel.py
+++ b/Parallel_working/scripts/live_4cam_arena_view_parallel.py
@@ -69,6 +69,13 @@ BALL_FLIGHT_FLOOR = "FLOOR"
 BALLISTIC_VZ_EMA_ALPHA = 0.35
 BALLISTIC_MAX_VZ_MM_S = 12000.0
 
+
+def ensure_project_src_on_path():
+    src_dir = Path(__file__).resolve().parent.parent.parent / "src"
+    if str(src_dir) not in sys.path:
+        sys.path.insert(0, str(src_dir))
+    return src_dir
+
 # --------------- BLM Demo: ballistic math + correction ---------------
 
 def _blm_forward_right(yaw_deg):
@@ -166,7 +173,7 @@ class StageTimer:
     def report(self, frame_idx, every):
         if every <= 0 or frame_idx == 0 or frame_idx % every != 0:
             return None
-        order = ["capture", "ball", "pose", "triang", "udp", "viz3d", "mosaic", "total"]
+        order = ["capture", "ball", "pose", "triang", "coach", "udp", "viz3d", "mosaic", "total"]
         parts = []
         payload = {"frame": int(frame_idx)}
         for stage in order:
@@ -345,6 +352,88 @@ def project_world_to_pixel(point_w, R, tvec, K, D):
     return uv.reshape(2)
 
 
+def parse_coach_zone_mm(value):
+    if not value:
+        return None
+    parts = [p.strip() for p in str(value).split(",") if p.strip()]
+    if len(parts) != 4:
+        raise RuntimeError("--coach-zone-mm must be x_min,y_min,x_max,y_max")
+    try:
+        x1, y1, x2, y2 = [float(p) for p in parts]
+    except ValueError as exc:
+        raise RuntimeError("--coach-zone-mm values must be numbers") from exc
+    return np.array(
+        [[x1, y1, 0.0], [x2, y1, 0.0], [x2, y2, 0.0], [x1, y2, 0.0]],
+        dtype=np.float64,
+    )
+
+
+def joints_array_to_frame(joints, conf, cams, frame_idx, fps):
+    out = []
+    arr = np.asarray(joints, dtype=np.float64)
+    for idx in range(17):
+        pt = arr[idx] if idx < len(arr) else np.full((3,), np.nan)
+        if np.isfinite(pt).all():
+            out.append([float(pt[0]), float(pt[1]), float(pt[2])])
+        else:
+            out.append(None)
+    return {
+        "frame_index": int(frame_idx),
+        "time_s": float(frame_idx) / max(1.0, float(fps)),
+        "joints": out,
+        "joint_conf": [float(v) for v in np.asarray(conf).reshape(-1)[:17]],
+        "joint_cams": [int(v) for v in np.asarray(cams).reshape(-1)[:17]],
+    }
+
+
+def project_zone_to_overlay(zone_mm, cam, extr, intr, roi, output_size):
+    if zone_mm is None or cam not in extr or cam not in intr:
+        return None
+    out_w, out_h = output_size
+    sx = float(out_w) / max(1, roi.width)
+    sy = float(out_h) / max(1, roi.height)
+    projected = []
+    for pt in zone_mm:
+        try:
+            uv = project_world_to_pixel(pt, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"])
+        except Exception:
+            return None
+        if not np.isfinite(uv).all():
+            return None
+        projected.append(((float(uv[0]) - roi.x1) * sx, (float(uv[1]) - roi.y1) * sy))
+    return projected
+
+
+def project_joints_to_overlay(joints, conf, cams, cam, extr, intr, roi, output_size, min_conf=0.35, min_cams=2):
+    kpts = np.full((17, 2), np.nan, dtype=np.float32)
+    scores = np.zeros((17,), dtype=np.float32)
+    if cam not in extr or cam not in intr:
+        return kpts, scores
+    out_w, out_h = output_size
+    sx = float(out_w) / max(1, roi.width)
+    sy = float(out_h) / max(1, roi.height)
+    joints_arr = np.asarray(joints, dtype=np.float64)
+    conf_arr = np.asarray(conf, dtype=np.float64).reshape(-1)
+    cams_arr = np.asarray(cams, dtype=np.int32).reshape(-1)
+    for idx in range(min(17, len(joints_arr))):
+        if idx >= len(conf_arr) or idx >= len(cams_arr):
+            continue
+        if conf_arr[idx] < min_conf or cams_arr[idx] < min_cams:
+            continue
+        pt = joints_arr[idx]
+        if not np.isfinite(pt).all():
+            continue
+        try:
+            uv = project_world_to_pixel(pt, extr[cam]["R"], extr[cam]["tvec"], intr[cam]["K"], intr[cam]["D"])
+        except Exception:
+            continue
+        if not np.isfinite(uv).all():
+            continue
+        kpts[idx] = [(float(uv[0]) - roi.x1) * sx, (float(uv[1]) - roi.y1) * sy]
+        scores[idx] = float(np.clip(conf_arr[idx], 0.0, 1.0))
+    return kpts, scores
+
+
 def ballistic_predict_z(z0, vz, dt_s, g, floor):
     dt_s = max(0.0, float(dt_s))
     z_new = float(z0) + float(vz) * dt_s - 0.5 * float(g) * dt_s * dt_s
@@ -1327,6 +1416,12 @@ def main():
     ap.add_argument("--record-video", default="", help="If set, write 3D arena view to this .mp4 path.")
     ap.add_argument("--record-fps", type=float, default=15.0, help="FPS for the recorded video (usually matches capture rate / viz_every).")
     ap.add_argument("--record-mosaic", default="", help="If set, also write the 4-cam 2D mosaic to this .mp4 path.")
+    ap.add_argument("--coach-overlay", action=argparse.BooleanOptionalAction, default=False,
+                    help="Show the low-lag in-process live coach overlay on the freshest camera ROI.")
+    ap.add_argument("--coach-exercise", choices=["squat", "push_up"], default="squat",
+                    help="Exercise logic and overlay labels for --coach-overlay.")
+    ap.add_argument("--coach-zone-mm", default="",
+                    help="Optional floor coach zone as x_min,y_min,x_max,y_max in arena millimetres.")
     ap.add_argument(
         "--ema-snap-thresh-mm",
         type=float,
@@ -1419,6 +1514,10 @@ def main():
     }
     profile_defaults = fast_defaults if args.high_performance else normal_defaults
 
+    if args.coach_overlay and args.show_3d is None:
+        args.show_3d = False
+    if args.coach_overlay and args.show_2d is None:
+        args.show_2d = False
     if args.show_3d is None:
         args.show_3d = profile_defaults["show_3d"]
     if args.show_2d is None:
@@ -1501,9 +1600,7 @@ def main():
     event_logger = None
     session_id = args.session_id.strip() if args.session_id else ""
     if args.event_log_output:
-        _src_dir = Path(__file__).resolve().parent.parent.parent / "src"
-        if str(_src_dir) not in sys.path:
-            sys.path.insert(0, str(_src_dir))
+        ensure_project_src_on_path()
         from project_cam.closed_loop import EventLogger  # noqa: E402
 
         if not session_id:
@@ -1527,6 +1624,36 @@ def main():
         )
         print(f"[OK] EventLogger enabled: {args.event_log_output} (session={session_id})")
 
+    coach_counter = None
+    coach_frame_kinematics = None
+    coach_select_best_camera = None
+    coach_crop_frame_to_roi = None
+    coach_repair_overlay_keypoints = None
+    coach_render_overlay = None
+    coach_roi_cls = None
+    if args.coach_overlay:
+        ensure_project_src_on_path()
+        from project_cam.assessment.kinematics import frame_kinematics as _coach_frame_kinematics  # noqa: E402
+        from project_cam.assessment.live_trainer.coach_overlay import (  # noqa: E402
+            StableRoi as _CoachStableRoi,
+            crop_frame_to_roi as _coach_crop_frame_to_roi,
+            repair_overlay_keypoints as _coach_repair_overlay_keypoints,
+            render_coach_overlay as _coach_render_overlay,
+            select_best_camera as _coach_select_best_camera,
+        )
+        from project_cam.assessment.live_trainer.rep_state import make_counter as _coach_make_counter  # noqa: E402
+        from project_cam.assessment.rules import DEFAULT_CONFIG_PATH, exercise_rules, load_rules  # noqa: E402
+
+        coach_rules = exercise_rules(load_rules(DEFAULT_CONFIG_PATH), args.coach_exercise)
+        coach_counter = _coach_make_counter(args.coach_exercise, coach_rules)
+        coach_frame_kinematics = _coach_frame_kinematics
+        coach_select_best_camera = _coach_select_best_camera
+        coach_crop_frame_to_roi = _coach_crop_frame_to_roi
+        coach_repair_overlay_keypoints = _coach_repair_overlay_keypoints
+        coach_render_overlay = _coach_render_overlay
+        coach_roi_cls = _CoachStableRoi
+        print(f"[INFO] Coach overlay enabled for {args.coach_exercise}")
+
     # Rising-edge tracker for target_chosen emits. We log a "target_chosen" event
     # every time blm_aim transitions from non-AIM_OK to AIM_OK (or the joint name
     # changes while still AIM_OK), not on every frame.
@@ -1540,10 +1667,10 @@ def main():
             udp_joint_indices_needed.add(JOINT_NAME_TO_IDX["right_hip"])
         elif idx is not None:
             udp_joint_indices_needed.add(idx)
-    triangulated_joint_indices = list(range(17)) if args.show_3d else sorted(udp_joint_indices_needed)
+    triangulated_joint_indices = list(range(17)) if (args.show_3d or args.coach_overlay) else sorted(udp_joint_indices_needed)
 
     ball_needed = args.track_ball and (args.show_3d or args.show_2d)
-    pose_needed = args.show_2d or bool(triangulated_joint_indices)
+    pose_needed = args.show_2d or args.coach_overlay or bool(triangulated_joint_indices)
     if args.high_performance:
         print(
             "[INFO] High-performance profile: "
@@ -1608,6 +1735,7 @@ def main():
     extr = load_extrinsics(args.extrinsics)
     dims, tags = parse_dimensions(args.dimensions)
     proj = {cam: extr[cam]["P"] for cam, _ in active_cams if cam in extr}
+    coach_zone_mm = parse_coach_zone_mm(args.coach_zone_mm) if args.coach_overlay else None
 
     ball_model = None
     if ball_needed:
@@ -1732,6 +1860,12 @@ def main():
         )
         for _ in range(17)
     ]
+    coach_prev_camera = None
+    coach_rois = {}
+    coach_state = coach_counter.state if coach_counter is not None else None
+    coach_metrics = {}
+    coach_window = f"Project_Cam Live Coach - {args.coach_exercise}"
+    coach_output_size = (int(args.viz_width), int(args.viz_height))
 
     frame_idx = 0
     t_start = time.time()
@@ -1752,6 +1886,8 @@ def main():
         print(f"[INFO] Ball JSONL enabled: {ball_log_path}")
 
     stop_hints = []
+    if args.coach_overlay:
+        stop_hints.append("press q in coach window")
     if args.show_2d:
         stop_hints.append("press q in 2D window")
     if args.show_3d:
@@ -2258,6 +2394,15 @@ def main():
                     joints_display[j] = dst + d_alpha * (src - dst)
             timer.stop("triang")
 
+            timer.start("coach")
+            if args.coach_overlay and coach_counter is not None and coach_frame_kinematics is not None:
+                coach_frame = joints_array_to_frame(
+                    joints_state, joints_conf_state, joints_cam_state, frame_idx, args.fps
+                )
+                coach_metrics = coach_frame_kinematics(coach_frame)
+                coach_state = coach_counter.update(coach_metrics)
+            timer.stop("coach")
+
             timer.start("udp")
             if udp_sock is not None and udp_target_addr is not None and udp_target_joint_pairs:
                 joints_payload = {}
@@ -2461,6 +2606,77 @@ def main():
                         break
             timer.stop("viz3d")
 
+            if args.coach_overlay and coach_state is not None:
+                camera_positions = {cam: extr[cam]["pos"] for cam, _ in active_cams if cam in extr}
+                selected_cam = coach_select_best_camera(
+                    args.coach_exercise,
+                    joints_state,
+                    per_cam_pose,
+                    camera_positions,
+                    previous_camera=coach_prev_camera,
+                )
+                if selected_cam is None and active_cams:
+                    selected_cam = active_cams[0][0]
+                if selected_cam is not None and selected_cam in cam_frames:
+                    coach_prev_camera = selected_cam
+                    src_frame = cam_frames[selected_cam]
+                    pose = per_cam_pose.get(selected_cam)
+                    if pose is None:
+                        pose_kpts = np.full((17, 2), np.nan, dtype=np.float32)
+                        pose_scores = np.zeros((17,), dtype=np.float32)
+                    else:
+                        pose_kpts, pose_scores = pose
+                    if selected_cam not in coach_rois:
+                        coach_rois[selected_cam] = coach_roi_cls(
+                            width=min(int(args.width), 960),
+                            height=min(int(args.height), 640),
+                            alpha=0.20,
+                        )
+                    roi = coach_rois[selected_cam].update(src_frame.shape, pose_kpts, pose_scores)
+                    crop, crop_kpts, _scale = coach_crop_frame_to_roi(
+                        src_frame, pose_kpts, roi, output_size=coach_output_size
+                    )
+                    projected_kpts, projected_scores = project_joints_to_overlay(
+                        joints_state,
+                        joints_conf_state,
+                        joints_cam_state,
+                        selected_cam,
+                        extr,
+                        intr,
+                        roi,
+                        coach_output_size,
+                    )
+                    overlay_kpts, overlay_scores = coach_repair_overlay_keypoints(
+                        args.coach_exercise,
+                        crop_kpts,
+                        pose_scores,
+                        projected_kpts,
+                        projected_scores,
+                    )
+                    zone_poly = project_zone_to_overlay(
+                        coach_zone_mm, selected_cam, extr, intr, roi, coach_output_size
+                    )
+                    coach_canvas = coach_render_overlay(
+                        crop,
+                        args.coach_exercise,
+                        coach_state,
+                        coach_metrics,
+                        overlay_kpts,
+                        overlay_scores,
+                        projected_floor=zone_poly,
+                    )
+                    cv2.putText(
+                        coach_canvas,
+                        selected_cam,
+                        (22, coach_canvas.shape[0] - 18),
+                        cv2.FONT_HERSHEY_SIMPLEX,
+                        0.56,
+                        (210, 210, 210),
+                        1,
+                        cv2.LINE_AA,
+                    )
+                    cv2.imshow(coach_window, coach_canvas)
+
             timer.start("mosaic")
             if args.show_2d and (frame_idx % args.mosaic_every == 0):
                 mosaic = make_mosaic(cam_frames, ball_boxes, per_cam_pose, copy_frames=False)
@@ -2484,10 +2700,16 @@ def main():
             timer.stop("mosaic")
 
             # Unified cv2 event pump (handles both 3D and 2D windows)
-            if args.show_2d or (args.show_3d and use_cv2_viz):
+            if args.coach_overlay or args.show_2d or (args.show_3d and use_cv2_viz):
                 _key = cv2.waitKey(1) & 0xFF
                 if _key == ord("q"):
                     break
+                if args.coach_overlay:
+                    try:
+                        if cv2.getWindowProperty(coach_window, cv2.WND_PROP_VISIBLE) < 1:
+                            break
+                    except cv2.error:
+                        pass
                 # Operator scoring for closed-loop demo (only meaningful when event log is on).
                 if event_logger is not None and _key != 255:
                     if _key == ord("r"):
```

### Relevant patch: `src/project_cam/assessment/live_trainer/__main__.py`

This is the old split-UDP trainer lag fix: drain all queued packets through the counter, render once from newest.

```diff
diff --git a/src/project_cam/assessment/live_trainer/__main__.py b/src/project_cam/assessment/live_trainer/__main__.py
index e8cc196f..ff88ee80 100644
--- a/src/project_cam/assessment/live_trainer/__main__.py
+++ b/src/project_cam/assessment/live_trainer/__main__.py
@@ -15,15 +15,93 @@ import cv2
 from ..io import normalize_frame
 from ..kinematics import frame_kinematics
 from ..rules import DEFAULT_CONFIG_PATH, exercise_rules, load_rules
-from .dashboard import render_dashboard
+from .dashboard import SkeletonView, render_dashboard
 from .rep_state import make_counter
 
+_RECV_BUF = 65535
+
+
+def _receive_available(sock: socket.socket) -> list[bytes]:
+    """Block briefly for one packet, then drain all queued packets.
+
+    The live tracker streams ~15 packets/s. If a render frame takes longer
+    than the packet interval, packets queue in the OS buffer and reading them
+    one-per-loop replays stale poses. The counter still needs every queued
+    sample, so this returns the drained FIFO and lets the render path draw only
+    once from the newest processed frame.
+    """
+    old_timeout = sock.gettimeout() if hasattr(sock, "gettimeout") else 0.2
+    try:
+        first, _addr = sock.recvfrom(_RECV_BUF)
+    except socket.timeout:
+        return []
+    except OSError:
+        return []
+    packets = [first]
+    sock.setblocking(False)
+    try:
+        while True:
+            try:
+                data, _addr = sock.recvfrom(_RECV_BUF)
+                packets.append(data)
+            except BlockingIOError:
+                break
+            except OSError:
+                break
+    finally:
+        sock.settimeout(old_timeout)
+    return packets
+
+
+def _parse_joint_packet(data: bytes) -> dict | None:
+    try:
+        packet = json.loads(data.decode("utf-8"))
+    except (json.JSONDecodeError, UnicodeDecodeError):
+        return None
+    if isinstance(packet, dict) and packet.get("type") == "joints":
+        return packet
+    return None
+
+
+def _process_joint_packets(
+    packets: list[bytes],
+    counter,
+    fps: float,
+    start_count: int,
+    log_fh=None,
+) -> tuple[list | None, int]:
+    """Feed every drained packet through kinematics/counter; return newest joints."""
+    count = start_count
+    last_joints = None
+    for data in packets:
+        packet = _parse_joint_packet(data)
+        if packet is None:
+            continue
+        frame = normalize_frame(packet, index=count, default_fps=fps, source="udp")
+        metrics = frame_kinematics(frame)
+        state = counter.update(metrics)
+        last_joints = frame["joints"]
+        count += 1
+        if log_fh is not None:
+            log_fh.write(json.dumps({
+                "frame": frame["frame_index"],
+                "time_s": frame["time_s"],
+                "rep_count": state.rep_count,
+                "incomplete_count": state.incomplete_count,
+                "phase": state.phase,
+                "angle": state.current_angle,
+                "tracking_quality": state.tracking_quality,
+                "cue": state.cue,
+            }) + "\n")
+    return last_joints, count
+
 
 def run(host: str, port: int, exercise: str, config_path: str, fps: float,
         log_jsonl: str | None = None) -> int:
     config = load_rules(config_path)
     rules = exercise_rules(config, exercise)
     counter = make_counter(exercise, rules)
+    skeleton_view = SkeletonView()
 
     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
     sock.bind((host, port))
@@ -39,37 +117,23 @@ def run(host: str, port: int, exercise: str, config_path: str, fps: float,
     print("[TRAINER] press 'q' or ESC in the window to quit")
     try:
         while True:
-            try:
-                data, _addr = sock.recvfrom(65535)
-                packet = json.loads(data.decode("utf-8"))
-                if isinstance(packet, dict) and packet.get("type") == "joints":
-                    frame = normalize_frame(packet, index=count,
-                                            default_fps=fps, source="udp")
-                    metrics = frame_kinematics(frame)
-                    state = counter.update(metrics)
-                    last_joints = frame["joints"]
-                    count += 1
-                    if log_fh is not None:
-                        log_fh.write(json.dumps({
-                            "frame": frame["frame_index"],
-                            "time_s": frame["time_s"],
-                            "rep_count": state.rep_count,
-                            "incomplete_count": state.incomplete_count,
-                            "phase": state.phase,
-                            "angle": state.current_angle,
-                            "tracking_quality": state.tracking_quality,
-                            "cue": state.cue,
-                        }) + "\n")
-            except socket.timeout:
-                pass
-            except (json.JSONDecodeError, UnicodeDecodeError):
-                pass
-
-            canvas = render_dashboard(exercise, counter.state, last_joints)
+            packets = _receive_available(sock)
+            if packets:
+                newest_joints, count = _process_joint_packets(
+                    packets, counter, fps=fps, start_count=count, log_fh=log_fh
+                )
+                if newest_joints is not None:
+                    last_joints = newest_joints
+
+            canvas = render_dashboard(exercise, counter.state, last_joints,
+                                      view=skeleton_view)
             cv2.imshow(window, canvas)
             key = cv2.waitKey(1) & 0xFF
             if key in (ord("q"), 27):
                 break
+            # also quit if the window was closed with the window-manager button
+            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
+                break
     except KeyboardInterrupt:
         pass
     finally:
```
