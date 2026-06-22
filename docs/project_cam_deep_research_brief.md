# Project_Cam Deep Research Brief

Project_Cam Deep Research Brief: Live Coach, Pose Tracking, and Project Reality Check

This document consolidates the DOCX review, corrected project facts, current
live-coach architecture, push-up/squat tracking diagnosis, and the next research
checklist into one reusable file.

## Executive Summary

The biggest correction is that Project_Cam is not a 5 m x 5 m professional
motion-capture arena. The active project is a low-cost, markerless, four-camera
domestic garage system with a measured arena of 6230 mm x 3050 mm x 2950 mm.
The system uses fixed USB cameras, calibrated intrinsics/extrinsics, YOLO-based
pose/ball perception, SVD triangulation, Kalman filtering, and safety-gated BLM
control.

The live push-up/squat coach is currently a real in-process overlay on top of
the canonical four-camera runtime. Squat tracking is mostly stable because the
athlete is upright and the hips/knees/ankles remain visible to multiple cameras.
Push-ups are harder: floor-level, side/oblique posture causes ankle and knee
visibility failures, left/right ambiguity, and clutter attachment. Bad lower-body
geometry then corrupts trunk-angle cues and floor/contact visualization.

The recommended near-term work is intentionally small and targeted:

1. Add temporal ankle reliability before allowing the trunk cue.
2. Use wrists-only push-up floor anchors by default, adding ankles only after
   strict multi-frame validation.
3. Add elbow angle velocity clamping to reject single-frame spikes.
4. Add debug logging around bad video timestamps.
5. Defer full identity tracking and single-camera ankle recovery to a larger
   geometry pass.

## Verified Project Facts

- Arena size is 6230 mm x 3050 mm x 2950 mm, not 5 m x 5 m.
- The physical environment is a domestic garage arena, not a professional
  motion-capture lab.
- The active four-camera hot path is
  `Parallel_working/scripts/live_4cam_arena_view_parallel.py`.
- The active live-coach launcher is
  `apps/athlete_assessment/run_live_coach.sh`.
- Active calibration comes from the `arena_fixed` bundle:
  `arena_fixed/cal/extrinsics/extrinsics_fixed.json`,
  `arena_fixed/cal/extrinsics/Dimensions_fixed.txt`, and
  `garage_lab_combined/cal/intrinsics/`.
- The current local live-coach unit-test count is 43 tests:
  18 in `tests/test_live_trainer.py` and 25 in
  `tests/test_live_coach_overlay.py`.
- The current repo state has `pytest` unavailable in `./venv`, so the reliable
  local verification command for these two files is `unittest`.
- The active project coordinate convention is millimetres at runtime. Source
  geometry files may store camera positions in metres or dimensions in
  centimetres, then convert downstream.
- The current prompt file
  `docs/live_coach_pushup_improvement_prompt_for_llm.md` still contains the
  incorrect `~5 m x 5 m arena` framing. This report corrects that fact without
  editing the prompt file.

## DOCX Disinformation and Corrections

| Wrong or risky statement from DOCX / prompt-derived material | Correct project fact | Evidence path | Research impact |
| --- | --- | --- | --- |
| "The physical testing arena consists of a 5 m x 5 m motion capture environment." | Arena is a domestic garage measuring 6230 mm x 3050 mm x 2950 mm. | `README.md`, `arena_fixed/cal/extrinsics/Dimensions_fixed.txt`, `latex_revised/Master_Thesis_3_revised/chapters/chapter3.tex` | Changes all reasoning about camera coverage, camera spacing, occlusion, and coordinate limits. |
| "Motion capture environment." | The project intentionally avoids professional motion-capture infrastructure. It is markerless, low-cost, and garage-scale. | `README.md`, `thesis_defense_qa.md`, `latex_revised/Master_Thesis_3_revised/chapters/chapter1.tex` | Do not compare system behavior as if it had Vicon/OptiTrack lab assumptions. |
| "Four fixed elevated USB cameras around a ~5 m x 5 m arena." | Four cameras are fixed, but their measured arena coordinates come from the garage geometry: `camNorth`, `camEast`, `camWest`, `camSouth` in centimetres in `Dimensions_fixed.txt`. | `arena_fixed/cal/extrinsics/Dimensions_fixed.txt` | Camera coverage and side-view quality must be analyzed from real camera placement. |
| "All 97 automated tests in the two live coach files." | Current two live-coach files contain 43 unittest tests: 18 trainer tests and 25 overlay tests. | `tests/test_live_trainer.py`, `tests/test_live_coach_overlay.py` | Do not claim 97 tests unless counting a broader historical test suite and documenting the scope. |
| Formula placeholders shown as `[]`. | These are unresolved generation gaps, not project math. | DOCX extracted text | Do not cite placeholder equations as technical evidence. |
| "RTMPose-S adds 1.2 ms" and similar latency numbers. | Not proven in this repo. Current verified latency anchors are YOLO-Pose TRT around 6.2 ms and MMPose around 38.5 ms/image. | `CLAUDE.md`, `README.md`, `latex_revised/Master_Thesis_3_revised/chapters/chapter5.tex` | Benchmark any second-pass model locally before using it in a plan. |
| "Reduces false cues by estimated 85%." | Not measured in current evidence. | No matching repo artifact found | Treat as a hypothesis, not a result. |
| Single-camera ankle fallback code in DOCX. | The correct known working ray-to-Z-plane implementation is the ball helper in the canonical live script. | `Parallel_working/scripts/live_4cam_arena_view_parallel.py` | Reuse the project helper pattern rather than the malformed DOCX pseudocode. |
| "MMPose required ~40 ms per frame." | Project docs usually state 38.5 ms/image or about 80 ms batched 4-cam in one benchmark context. | `CLAUDE.md`, `README.md` | Keep per-image vs per-four-camera timing precise. |
| Treating floor/mat placement as calibrated proof. | The arena floor is calibrated as Z=0; the mat is an action surface, not a separate geometric calibration unless measured. | `Dimensions_fixed.txt`, live-coach docs | Floor-line logic should use actual visible contacts and strict validation. |

## Whole Project Explanation

Project_Cam is a pose-guided predictive ballistics and athlete-assessment
system. The high-level goal is to reconstruct human body joints in 3D from
commodity cameras, predict near-future target motion, compute aim parameters,
and control a physical Ball Launching Machine (BLM) safely.

The project has two connected product directions:

1. A vision-guided BLM that can aim at selected body joints such as shoulder,
   hip, or knee.
2. An athlete-assessment stack that records movement, computes biomechanics
   metrics, and exports reports for coaching or lab handoff.

### Physical Setup

The arena is a domestic garage with a measured world frame:

- X dimension: 6230 mm.
- Y dimension: 3050 mm.
- Z dimension: 2950 mm.
- Origin: North-East floor corner.
- X axis: North wall toward South wall.
- Y axis: East wall toward West wall.
- Z axis: vertical up.

The camera roles are:

- `camNorth`
- `camEast`
- `camSouth`
- `camWest`

The BLM position is documented as approximately `(600, 1560, 500)` mm, facing
the South wall in the active coordinate convention.

### Hardware

The perception hardware uses four fixed commodity USB cameras. The thesis and
repo docs identify Hikvision DS-E12 class cameras in the low-cost setup. The
actuation side is a custom BLM with stepper-driven aiming, flywheel launch, a
pusher/reload mechanism, and ESP32 low-level control.

The active firmware is `control_12_full.ino`, with key properties:

- 921600 baud USB serial.
- ESP32 state machine.
- PULLUP limit switches triggered on LOW.
- RPM gate before shooting.
- Commands such as `set`, `shoot`, `reload`, `stop`, `center`, `setzero`,
  and `info`.

### Calibration

Calibration is split into:

- Intrinsics: per-camera camera matrix and distortion coefficients from
  ChArUco calibration.
- Extrinsics: AprilTag wall calibration into the arena world frame.
- Dimensions: fixed arena geometry and tag positions.
- Correction model: bias/linear correction fitted from ground-truth evaluation.

The active geometry source of truth is the `arena_fixed` bundle. Do not mix it
with old extrinsics unless explicitly doing an evaluation comparison.

### Runtime Perception Stack

The canonical runtime is the parallel four-camera script:

`Parallel_working/scripts/live_4cam_arena_view_parallel.py`

The live coach wrapper runs it with:

- active camera config from `garage_lab_combined/config/cameras.yaml`;
- intrinsics from `garage_lab_combined/cal/intrinsics`;
- extrinsics from `arena_fixed/cal/extrinsics/extrinsics_fixed.json`;
- dimensions from `arena_fixed/cal/extrinsics/Dimensions_fixed.txt`;
- YOLO-Pose backend;
- coach overlay enabled;
- ball tracking disabled for the coach-only mode.

The runtime loop is:

1. Capture frames from four fixed cameras.
2. Run ball detector if enabled.
3. Run pose backend if enabled.
4. Convert 2D observations into undistorted normalized image points.
5. Triangulate each joint when at least two cameras see it.
6. Smooth/display joints through EMA and stale-frame gates.
7. Optionally stream selected joints over UDP.
8. Optionally render 3D arena and coach overlay.

### Pose and Triangulation

The live coach uses COCO-17 keypoints. YOLO11m-Pose is the current real-time
primary because it fits the frame budget better than MMPose. MMPose remains a
reference/backend comparison path and is used in older/offline flows.

Each joint is triangulated independently from per-camera 2D keypoints. In the
canonical live script, a joint needs observations from at least two cameras.
The output state includes:

- `joints_state`: 3D world joint position.
- `joints_conf_state`: mean observation confidence.
- `joints_cam_state`: number of cameras contributing to that joint.

This is important for push-ups: if an ankle has only one good camera, the
current joint triangulation path cannot recover it as a 3D point.

### Kalman and Prediction

The project uses constant-velocity Kalman filtering for smooth current state and
short-horizon prediction. Current documented tuning anchors:

- Joints: process noise around 500, measurement noise around 10.
- Best BLM prediction horizon: roughly 200-400 ms.
- Jump motion is a known limitation of a constant-velocity model.

Ball tracking has additional robustness gates:

- iterative reprojection rejection;
- dedicated ball Kalman filter;
- max-speed gate;
- coast-through-dropout;
- optional single-camera ray-to-Z-plane fallback.

The ball fallback is currently ball-specific, not joint-specific.

### Ballistic and Launcher Stack

The launcher side consumes target joint positions, applies correction, computes
pitch/yaw/RPM, and sends serial commands to the BLM. Safety rules are central:
only authorized runtime paths should send `shoot`, and `--shoot-enabled` is
guarded by preflight and safety validation assumptions.

The current project status includes staged validation through aim-only and
controlled firing. Full autonomous closed-loop firing at a moving human subject
remains a boundary that should be described honestly unless newly validated.

### Assessment Stack

The assessment workflow records JSONL joint streams and converts them into:

- JSON reports;
- HTML coach-facing reports;
- C3D exports for biomechanics tools such as Mokka, Visual3D, OpenSim, or
  `ezc3d`.

Core assessment modules:

- `src/project_cam/assessment/kinematics.py`
- `src/project_cam/assessment/segmentation.py`
- `src/project_cam/assessment/rules.py`
- `src/project_cam/assessment/reports.py`
- `src/project_cam/assessment/exports/c3d_writer.py`

For live coach work, `kinematics.py` is central because it defines the actual
angles and posture metrics used by the rep counter.

## Live Coach Architecture

The live coach has two modes in the repository history, but the recommended
current path is the in-process overlay:

`apps/athlete_assessment/run_live_coach.sh`

This starts the canonical four-camera live script and enables the coach overlay.
The old split mode used UDP joints plus a separate dashboard process, but the
single-process overlay is preferred because it has access to current frames,
raw per-camera 2D pose, triangulated 3D joints, and coach state in one place.

### Rep Counter

The rep counter lives in:

`src/project_cam/assessment/live_trainer/rep_state.py`

It is a two-state hysteresis machine:

- Push-up signal: average of left/right elbow angle.
- Squat signal: average of left/right knee angle.
- Smoothing: EMA on the signal angle.
- Descent/bottom/top thresholds come from
  `configs/exercises/football_academy_u10.yaml`.

Push-up defaults include:

- descent angle: 138 degrees;
- bottom angle: 122 degrees;
- top angle: 150 degrees;
- minimum ROM: 45 degrees;
- noise ROM: 18 degrees;
- smoothing alpha: 0.6;
- minimum cycle frames: 5;
- maximum signal asymmetry: 45 degrees;
- maximum posture incline: 35 degrees;
- acquire frames: 4;
- release frames: 8.

The push-up acquisition gate deliberately does not require ankles. It checks:

- torso incline is sufficiently horizontal;
- both elbow angles are present.

This prevents bad ankle tracking from causing set acquisition flicker. The
tradeoff is that ankles can still poison trunk cue calculation later unless
trunk cue reliability is strong enough.

### Kinematics

The live trainer consumes `frame_kinematics()`, which computes:

- elbow, knee, shoulder, hip angles;
- trunk-to-leg angles as shoulder-hip-ankle;
- shoulder width, hip width, stance width, pelvis Z;
- left/right asymmetry;
- knee line and valgus ratios;
- torso incline;
- joint confidence/camera-count quality.

The important dependency chain is:

`ankle quality -> trunk_to_leg angle -> trunk cue correctness`

That chain explains why a visually straight torso can still receive a false
trunk warning when ankle geometry is wrong.

### Coach Overlay

The overlay lives in:

`src/project_cam/assessment/live_trainer/coach_overlay.py`

The overlay does not open cameras by itself. It receives frames, 2D keypoints,
3D projected keypoints, metrics, and rep state from the live script.

The overlay steps are:

1. Select best camera.
2. Keep a sticky camera lock during push-up sets.
3. Crop a stable ROI.
4. Project triangulated 3D joints back into the selected camera.
5. Repair push-up lower-body drawing with projected 3D joints when valid.
6. Smooth and coast keypoints.
7. Validate push-up leg chains.
8. Draw floor guide, skeleton, angle labels, depth meter, and coaching cue.

Camera selection is exercise-specific:

- Squats prefer front/back body view.
- Push-ups prefer side view and include lower-body visibility in the score.

The overlay validator currently drops bad push-up leg joints rather than trying
to recover them. This is honest visualization, but not full lower-body recovery.

## Push-Up Tracking Failure Analysis

The user-observed failures from the screencast are consistent with the current
architecture:

- At push-up bottoms, ankles and knees can collapse, misattach, or attach to
  floor clutter.
- Trunk cue can fire falsely because trunk angle depends on shoulder-hip-ankle.
- Floor/contact line can float too high if bad ankles are included.
- Elbow angle can spike when one side is occluded or mislabeled near a phase
  transition.

### Root Cause Pattern

Push-up lower-body failure is dominated by floor-level visibility and identity
ambiguity:

1. Athlete is low to the ground.
2. Legs are foreshortened in side/oblique views.
3. Torso can occlude knees/ankles.
4. The floor contains clutter and leg-like edges.
5. YOLO-Pose can produce plausible but wrong lower-body keypoints.
6. Multi-view triangulation needs at least two cameras.
7. If only one camera is correct, the joint is missing.
8. If two cameras are confidently wrong, the joint can be wrong but still pass
   simple camera-count checks.

This produces cascading failures:

- ankle/keypoint geometry fails;
- trunk-to-leg angle becomes unreliable;
- trunk cue becomes unreliable;
- floor guide can be pulled by the bad ankle;
- phase state can become noisy if elbow angles spike at the same time.

### What The Current System Already Mitigates

The live coach already has meaningful defenses:

- Push-up acquisition excludes ankles.
- Acquisition/release is debounced.
- State machine holds on non-plank frames during an acquired set.
- Large left/right elbow disagreement holds the frame.
- Very short cycles are ignored.
- Camera selection favors push-up side view with visible legs.
- Camera lock avoids mid-rep view switching.
- Projected lower-body keypoints can repair weak raw 2D.
- Repaired keypoints are smoothed and coasted.
- A 160 px overlay jump gate rejects single-frame teleporting.
- Push-up leg validation drops implausible knees/ankles.
- Trunk cue is suppressed when ankle camera count is below two.

### Remaining Gaps

The current trunk cue reliability is current-frame only. A one-frame or
short-streak false ankle with enough cameras can still pass. It should require
temporal reliability, not just current-frame camera count.

The current floor guide still uses wrists plus ankles for push-ups when ankles
are considered valid. Since wrists are the true hand-floor contact and ankles
are advisory in a push-up, the safer default is wrists-only, adding ankles only
after strict validation for several consecutive frames.

The current signal smoother is an EMA. It does not explicitly reject impossible
per-frame elbow angle velocity. An angular-velocity guard would reduce residual
single-frame spikes near transitions.

The current overlay can drop bad legs, but it does not recover correct legs when
multi-view triangulation fails. Correct recovery is a larger feature involving
single-camera projection, per-athlete proportions, or second-pass ROI pose.

## Squat Tracking Status

Squat tracking is currently much healthier than push-up tracking.

Reasons:

- Athlete is upright.
- Hips, knees, and ankles are separated in image space.
- Multiple cameras usually see the lower body.
- The body is less merged with floor clutter.
- Knee and pelvis motion are easier to triangulate than floor-level ankles.

Current squat counter behavior:

- Signal is knee angle.
- Pelvis travel can satisfy depth as an OR-path.
- Knee valgus cue uses `knee_valgus_signed_ratio`.
- Squat overlay does not run push-up leg-chain validation.

Known squat risk:

- Side/diagonal views can show mild left/right crossing or tilt artifacts.
- Knee valgus/form metrics depend on accurate hip-knee-ankle geometry.
- A squat-specific knee/hip validator may be useful later, but it is lower
  priority than push-up lower-body recovery because current observed squat
  failures are not catastrophic.

## Current Code Reality

### What Is Already Implemented

- Push-up acquisition gate excludes ankles.
- Debounced acquire/release for push-up set acquisition.
- Hold behavior when a frame is not a verified plank.
- Elbow/knee asymmetry hold via `max_signal_asymmetry_deg`.
- Minimum cycle frames via `min_cycle_frames`.
- Current-frame ankle camera-count gate for trunk cue.
- Camera selection for push-up includes lower-body visibility.
- Sticky push-up camera lock.
- Stable ROI crop.
- Projected 3D lower-body repair for push-up overlay.
- Push-up leg validation with confidence, body-axis, and length-ratio checks.
- Overlay keypoint stabilizer with EMA, coast-through-dropout, and jump gate.
- Ball-only single-camera ray-to-Z-plane fallback helper.
- Active `unittest` coverage for live trainer and coach overlay.

### What Is Not Implemented Yet

- Temporal ankle reliability streak for trunk cue.
- Wrists-only push-up floor line by default.
- Elbow angular-velocity clamp.
- Per-athlete skeletal priors.
- Single-camera ankle fallback.
- RTMPose/ROI second-pass refinement.
- Deep left/right identity tracking over time.
- Push-up-specific debug export around failure timestamps.
- Squat-specific knee/hip quality validator.

### Guardrails

Do not casually change:

- `triangulate_multi`
- `transform_world_point_y`
- `ema_update`
- UDP axis semantics and payload schema
- `arena_fixed` calibration semantics
- BLM shooting paths

Any push-up improvement should keep the squat path behavior-identical unless a
change is explicitly scoped to both exercises.

## Recommended Next Work

1. Trunk cue temporal ankle reliability.

   Add a small streak counter in `RepCounter` for push-ups. Only allow trunk
   cues when both ankles have `joint_cams >= 2` for at least 5 consecutive
   frames. This turns the current single-frame reliability gate into a temporal
   gate.

2. Push-up wrists-only floor anchor unless ankles pass strict multi-frame
   validity.

   In `_draw_floor_guides`, use wrists as the default push-up ground IDs.
   Include ankles only if both ankles pass validation and a short ankle-valid
   streak. The simplest first version can keep this overlay-local and avoid
   touching triangulation.

3. Elbow angle velocity clamp.

   Add a scalar filter around the push-up signal angle. Reject impossible jumps
   such as greater than about 60 degrees per frame unless sustained for two or
   three frames. This protects phase state and labels from one-frame elbow
   occlusion spikes.

4. Add debug logging around bad timestamps.

   For push-up research videos, log enough per-frame data to diagnose each bad
   cue:

   - selected camera;
   - raw per-camera ankle/knee/wrist/elbow scores;
   - `joint_cams`;
   - `joint_conf`;
   - `left/right trunk_to_leg`;
   - floor anchor IDs;
   - acquisition/plank state;
   - cue emitted;
   - reason a cue was suppressed or emitted.

5. Defer full identity swap tracking and single-camera ankle fallback.

   These are more invasive. Full identity tracking likely belongs closer to
   per-camera association or triangulation outlier rejection. Single-camera
   ankle fallback can be valuable, but it needs clear validation against tibia
   length, foot contact assumptions, and bad floor-plane intersections.

## Deep Research Checklist

Use this checklist for the next video review.

### Per-Frame Data To Log

- Timestamp and frame index.
- Selected coach camera.
- Push-up acquisition state.
- Current phase and status.
- Cue text.
- Raw left/right elbow angles.
- Smoothed signal angle.
- Elbow angular delta from prior frame.
- Left/right trunk-to-leg angles.
- `joint_cams` for wrists, elbows, hips, knees, ankles.
- `joint_conf` for wrists, elbows, hips, knees, ankles.
- Raw per-camera 2D scores for knees and ankles.
- Whether each leg joint passed `validate_leg_chain`.
- Floor anchor joint IDs used for the yellow line.

### Timestamp Labels To Mark

- Push-up top.
- Push-up bottom.
- Trunk cue onset.
- Trunk cue offset.
- Floor line visibly too high.
- Elbow angle spike.
- Lower-body collapse.
- Squat diagonal/cross-over frame.

### Failure Classes

Classify every bad frame into one of these buckets:

- Missing triangulation: fewer than two cameras saw the joint.
- Confident wrong triangulation: two or more cameras saw the wrong object.
- Overlay-only issue: 3D joint is plausible but projected/drawn badly.
- State-machine issue: geometry is acceptable but phase/cue logic is wrong.
- Camera-selection issue: another camera had better leg visibility.
- Floor-anchor issue: wrong joints were used for the guide line.
- Identity issue: left/right side swapped or crossed.

### Research Questions

- Do false trunk cues occur after one-frame ankle reliability spikes or after
  sustained wrong ankle geometry?
- Does the floor line improve if ankles are removed completely from push-up
  floor anchors?
- Are elbow spikes visible in raw 2D, triangulated 3D, or only after smoothing?
- Does the selected camera have the best lower-body score at the bad timestamp?
- Does a lower side camera or different athlete orientation actually solve the
  push-up lower-body failure?
- Can a single-camera ankle-to-floor projection pass tibia-length checks in
  real video, or does it drift too much laterally?

## Evidence Index

Core project files:

- `README.md`
- `CLAUDE.md`
- `CANONICAL.md`

Arena and calibration:

- `arena_fixed/cal/extrinsics/Dimensions_fixed.txt`
- `arena_fixed/cal/extrinsics/extrinsics_fixed.json`
- `arena_fixed/config/arena_dimensions.yaml`
- `arena_fixed/config/calibration_manifest.yaml`
- `garage_lab_combined/cal/intrinsics/`
- `garage_lab_combined/config/cameras.yaml`

Live runtime:

- `apps/athlete_assessment/run_live_coach.sh`
- `Parallel_working/scripts/live_4cam_arena_view_parallel.py`
- `Parallel_working/run_live_parallel_yolopose.sh`

Live trainer and overlay:

- `src/project_cam/assessment/live_trainer/rep_state.py`
- `src/project_cam/assessment/live_trainer/coach_overlay.py`
- `src/project_cam/assessment/live_trainer/dashboard.py`
- `src/project_cam/assessment/live_trainer/__main__.py`
- `configs/exercises/football_academy_u10.yaml`

Kinematics and assessment:

- `src/project_cam/assessment/kinematics.py`
- `src/project_cam/assessment/joints.py`
- `src/project_cam/assessment/offline_assess.py`
- `src/project_cam/assessment/reports.py`
- `src/project_cam/assessment/exports/c3d_writer.py`

Tests:

- `tests/test_live_trainer.py`
- `tests/test_live_coach_overlay.py`
- `tests/test_threshold_regression.py`
- `tests/test_assessment_tier1.py`

Prompt and handoff docs:

- `docs/live_coach_pushup_improvement_prompt_for_llm.md`
- `docs/live_coach_pushup_handoff_for_llm.md`

Thesis/reference docs:

- `latex_revised/Master_Thesis_3_revised/chapters/chapter1.tex`
- `latex_revised/Master_Thesis_3_revised/chapters/chapter3.tex`
- `latex_revised/Master_Thesis_3_revised/chapters/chapter5.tex`
- `thesis_defense_qa.md`

External files reviewed for this brief:

- `/home/hanush/Downloads/Pose Tracking Improvement Recommendations.docx`
- `/home/hanush/Videos/Screencasts/Screencast from 05-20-2026 01:11:48 PM.webm`

Verification commands used during preparation:

```bash
PYTHONPATH=src ./venv/bin/python -m unittest discover -s tests -p 'test_live_trainer.py' -v
PYTHONPATH=src ./venv/bin/python -m unittest discover -s tests -p 'test_live_coach_overlay.py' -v
rg -n "^\s*def test_" tests/test_live_trainer.py tests/test_live_coach_overlay.py | wc -l
```
