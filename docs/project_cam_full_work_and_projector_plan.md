# Project_Cam Full System and Garage Projector Plan

This document is a large working brief for explaining the whole Project_Cam
system, the current live-coach work, the future roadmap, and a garage projector
plan. It is written for handing to another LLM, a collaborator, a supervisor, or
your future self before doing another deep research pass.

The most important rule for reading this file:

- **Current reality** means something already exists in this repository or is
  documented by the active project files.
- **Future design** means a proposed next system direction. Do not present it as
  built until code, tests, calibration, and a live garage run prove it.

---

## 1. Executive Summary

Project_Cam is a four-camera, markerless, garage-scale 3D perception and
robotic ball-launching system. The core thesis version tracks a person and a
ball in a domestic garage arena, reconstructs 3D joints from four fixed USB
cameras, predicts near-future motion, and sends safety-gated commands to a Ball
Launching Machine (BLM). The newer athlete-assessment layer turns the same 3D
joint stream into movement-quality reports, C3D files, HTML coach reports, and
live exercise coaching.

The system is **not** a professional motion-capture lab and it is **not** a
5 m x 5 m arena. The verified arena is a domestic garage measuring:

```text
X = 6230 mm
Y = 3050 mm
Z = 2950 mm
```

The active world origin is the North-East floor corner. All runtime coordinates
are in millimetres.

The live coach path currently focuses on squats and push-ups. Squat tracking is
mostly stable because the athlete remains upright and lower-body joints stay
visible. Push-up tracking is harder because the athlete is close to the floor,
often viewed from a side/oblique angle, and legs/ankles become occluded or
confused with floor objects. The current code now contains several targeted
push-up robustness fixes: push-up acquisition does not require ankles, the
trunk cue requires a temporal ankle-camera streak, the floor guide defaults to
wrists, and the elbow signal has an angular-velocity clamp.

The next large product idea is to turn the garage into an interactive training
arena with a projector. The projector should **not** replace the 3D camera
system. It should act as the athlete-facing display layer: target zones,
countdowns, coach cues, player cards, score, safety status, and adaptive drill
instructions. The cameras remain the truth source for pose, ball, and outcome
measurement.

For the first projector prototype, the safest recommendation is:

1. Start with a **wall projection**, preferably on a clear wall or screen area
   outside the direct ball-impact path.
2. Use a simple **2D homography** between projector pixels and the wall plane.
3. Keep the projector high, fixed, protected, and out of camera glare.
4. Use a browser full-screen UI as the projector output.
5. Only later add floor projection or mixed wall/floor projection, because floor
   projection creates shadows, occlusion, parallax, and calibration complexity.

---

## 2. Current Project Reality

### 2.1 Project Identity

Project_Cam is described in the repository as:

```text
Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking
```

The core idea is:

1. Observe a domestic garage arena with four fixed cameras.
2. Detect human pose and ball positions in each camera.
3. Convert 2D observations into 3D world coordinates.
4. Smooth and predict the target.
5. Aim a physical BLM at selected body joints or target zones.
6. Log the full session for evaluation, coaching, and reporting.

The newer direction adds athlete assessment:

1. Record 3D joint streams.
2. Segment reps.
3. Compute kinematics and movement-quality metrics.
4. Generate JSON, HTML, and C3D outputs.
5. Show live exercise coaching overlays.
6. Later, drive an adaptive training game.

### 2.2 Verified Arena Geometry

The active arena is documented in
`arena_fixed/cal/extrinsics/Dimensions_fixed.txt`.

The measured dimensions are:

```text
X = 623 cm = 6230 mm
Y = 305 cm = 3050 mm
Z = 295 cm = 2950 mm
```

World-frame description:

```text
Origin: North-East floor corner at (0, 0, 0)
North wall: X = 0
South wall: X = 6230 mm
East wall:  Y = 0
West wall:  Y = 3050 mm
Z axis:     vertical up from floor
```

The four fixed cameras are documented in centimetres:

```text
CamNorth = (5,   110, 226) cm
CamEast  = (162, 5,   212) cm
CamWest  = (160, 297, 217) cm
CamSouth = (618, 153, 227) cm
```

Converted to approximate millimetres:

```text
CamNorth = (50,   1100, 2260) mm
CamEast  = (1620, 50,   2120) mm
CamWest  = (1600, 2970, 2170) mm
CamSouth = (6180, 1530, 2270) mm
```

These cameras are high on the walls, roughly 2.12 m to 2.27 m above the floor.
That high mounting helps full-body coverage for standing movement but makes
horizontal floor postures such as push-ups difficult, especially at ankles and
knees.

### 2.3 Physical Setup Summary

Current physical system:

- Domestic garage arena.
- Four fixed USB cameras.
- AprilTag wall markers for extrinsic calibration.
- ChArUco intrinsics per camera.
- Arena dimensions and tag positions stored in `arena_fixed`.
- BLM with ESP32 firmware and serial control.
- Optional voice bridge via Vosk in a separate environment.
- Operator laptop running live viewer, assessment scripts, and launcher tools.

Important correction:

- Do not call the arena a professional motion-capture lab.
- Do not call it 5 m x 5 m.
- Do not assume Vicon/OptiTrack-style marker accuracy.
- Do not assume ceiling-mounted synchronized global-shutter cameras unless the
  hardware has changed and been documented.

### 2.4 Canonical Runtime Stack

The active canonical live path is:

```text
Parallel_working/scripts/live_4cam_arena_view_parallel.py
```

The live coach wrapper is:

```text
apps/athlete_assessment/run_live_coach.sh
```

That wrapper runs the canonical live script with the current garage assets:

```text
--config garage_lab_combined/config/cameras.yaml
--intrinsics-dir garage_lab_combined/cal/intrinsics
--extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json
--dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt
--pose-backend yolopose
--coach-overlay
--no-track-ball
```

The active calibration bundle is:

```text
arena_fixed/cal/extrinsics/extrinsics_fixed.json
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
garage_lab_combined/cal/intrinsics/
arena_fixed/config/calibration_manifest.yaml
```

The repository already has an explicit canonical manifest:

```text
CANONICAL.md
```

Use that file to decide which scripts are active when folder names are
confusing.

---

## 3. Whole Project Explanation

### 3.1 The Big Goal

Project_Cam is trying to make a low-cost intelligent sports training system.
The central question is:

```text
Can a domestic garage, commodity cameras, and custom robotics produce useful
3D athlete tracking, target prediction, robotic ball launching, and movement
assessment without a professional motion-capture lab?
```

The answer in the current project is partially yes:

- 3D pose and ball tracking exist.
- The BLM can be commanded and safety-gated.
- Live aim tests and controlled firing have been documented.
- Athlete assessment can generate reports and C3D output.
- Live squat/push-up coaching exists.
- The system still has known limitations with push-up lower-body tracking,
  fast motion, camera synchronization, and full product orchestration.

### 3.2 Main Product Directions

There are four connected product directions.

#### Direction A: Pose-Guided BLM

The original thesis core:

1. Detect human joints.
2. Reconstruct target joint in 3D.
3. Predict where the joint will be after latency.
4. Convert target to launcher pitch/yaw/RPM.
5. Aim the BLM.
6. Optionally shoot after safety checks.

This is the robotic closed-loop part.

#### Direction B: Athlete Assessment

The assessment system:

1. Records 3D joint streams as JSONL.
2. Runs kinematic analysis.
3. Segments movements into reps.
4. Scores tracking quality and movement quality separately.
5. Exports coach-facing HTML.
6. Exports C3D for biomechanics tools.

This is the sports science / coach reporting part.

#### Direction C: Live Coach

The live coach:

1. Runs on top of the live four-camera viewer.
2. Selects the best camera view for the exercise.
3. Crops a stable ROI around the athlete.
4. Draws skeleton, angle labels, floor guide, phase, rep count, and cues.
5. Maintains a rep-counting state machine for squats or push-ups.
6. Uses exercise-specific rules.

This is the immediate user-facing feedback part.

#### Direction D: Adaptive Weakness Arena With Projector

The future product:

1. The athlete enters the garage.
2. Cameras assess movement quality.
3. The system discovers weaknesses such as valgus, asymmetry, reaction delay,
   poor scan rate, or unstable single-leg control.
4. A projector shows game-like cues, target zones, scores, and player cards.
5. The BLM adapts drills to target the weakness.
6. The final output is a coach report plus an athlete-facing result.

This is the future demo/product layer.

---

## 4. Hardware System

### 4.1 Cameras

Current known camera properties from repository docs:

- Four fixed USB cameras.
- Runtime resolution commonly 1280 x 720.
- Capture target commonly 15 FPS in the live coach wrapper.
- Higher performance experiments discuss 30 FPS, but production-proof status
  depends on sustained live tests.

Camera names:

```text
camNorth
camEast
camSouth
camWest
```

The camera system is not just for display. It is the measurement layer.

Each camera contributes:

- 2D ball detections.
- 2D human pose keypoints.
- Observation confidence.
- Camera-specific view of occlusions.

The multi-camera stack combines those observations into world coordinates.

### 4.2 BLM

BLM means Ball Launching Machine.

The active firmware is documented as:

```text
control_12_full.ino
```

Important properties:

- ESP32 control.
- Serial baud: 921600.
- Limit switches use PULLUP and trigger on LOW.
- Flywheel RPM gate before shooting.
- Stepper-driven aiming.
- Pusher/reload mechanism.
- Commands such as `set`, `shoot`, `reload`, `stop`, `center`, `setzero`,
  `info`, and jog commands.

Important safety idea:

```text
The perception stack should decide targets; the launcher runtime should enforce
safety gates before a physical shot.
```

Do not make random UI code send raw shoot commands.

### 4.3 Voice Bridge

The voice system is separate from the main project venv. It uses Vosk and sends
recognized commands over UDP to `blm_follow.py`.

Current file:

```text
garage_lab_combined/scripts/voice_bridge.py
```

Current voice path:

```text
microphone -> Vosk recognizer -> voice_bridge.py -> UDP 127.0.0.1:5006
-> blm_follow.py --voice-port 5006
```

Example commands:

```text
head -> nose
left knee -> left_knee
right shoulder -> right_shoulder
go / shoot -> shoot
reload -> reload
pause / stop -> pause
resume -> resume
quit -> quit
```

For the future projector product, voice can be used in two ways:

1. Operator control: start, pause, reload, choose joint.
2. Athlete game cue: "look left", "block right", "scan", "go".

Those two modes should eventually be separated so a child cannot accidentally
trigger unsafe launcher commands by shouting a phrase.

### 4.4 Projector

The projector is not part of the proven current stack. It is a future display
layer.

Its job should be:

- Show target zones.
- Show countdowns.
- Show safe/unsafe status.
- Show exercise prompts.
- Show player cards.
- Show weakness reveal.
- Show scores, combo, badges, and drill progress.
- Show coach-friendly visual summaries between reps.

Its job should **not** be:

- Replace camera tracking.
- Replace launcher safety gates.
- Determine whether the athlete was hit.
- Determine whether a joint is valid.
- Be the only source of safety instructions.

---

## 5. Calibration System

### 5.1 Intrinsics

Intrinsics describe each camera's internal lens model:

- camera matrix;
- distortion coefficients;
- image resolution.

Active intrinsics directory:

```text
garage_lab_combined/cal/intrinsics/
```

The code must not change runtime resolution casually, because intrinsics are
resolution-sensitive unless properly scaled.

### 5.2 Extrinsics

Extrinsics describe each camera's pose in the world:

- rotation;
- translation;
- camera position;
- projection matrix.

Active extrinsics:

```text
arena_fixed/cal/extrinsics/extrinsics_fixed.json
```

Do not mix this with old extrinsics unless doing a controlled comparison.

### 5.3 Dimensions and AprilTags

The dimensions file is the human-readable source for:

- arena dimensions;
- wall definitions;
- camera positions;
- AprilTag size;
- AprilTag IDs by wall;
- AprilTag corner coordinates.

File:

```text
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
```

The AprilTags make the garage a measurable world coordinate system.

### 5.4 Correction Model

The project has documented systematic bias in the arena-fixed evaluation.
Important idea:

```text
Precision can be good even when absolute bias is present.
```

The correction model compensates systematic spatial bias before launcher
control. The exact correction mode should be documented per run because
changing it changes target aim.

### 5.5 Projector Calibration, Future

A projector is mathematically like an inverse camera:

```text
camera:    world point -> camera pixel
projector: projector pixel -> world light ray / surface point
```

For the first version, do not overbuild full 3D projector calibration. Use
planar mapping:

```text
projector pixel <-> wall point on X = constant
```

or:

```text
projector pixel <-> floor point on Z = 0
```

This can be solved with a homography if the surface is planar.

Future projector calibration stages:

1. Manual four-corner wall calibration.
2. Camera-observed projected dot grid on a wall.
3. Camera-observed projected dot grid on the floor.
4. Full projector intrinsics/extrinsics if needed.
5. Multi-surface mapping if wall + floor projection are both used.

---

## 6. Software Runtime Stack

### 6.1 Live Viewer

Canonical live viewer:

```text
Parallel_working/scripts/live_4cam_arena_view_parallel.py
```

Responsibilities:

- Open cameras.
- Capture frames.
- Run pose backend.
- Run ball backend if enabled.
- Triangulate joints.
- Smooth joint and ball states.
- Predict future positions if enabled.
- Render 3D and 2D views.
- Send target joints over UDP if enabled.
- Render live coach overlay if enabled.
- Emit event logs if enabled.

### 6.2 Pose Backends

Current documented options:

- YOLO-Pose: current real-time primary.
- MMPose / RTMPose path: older or reference path.

Current real-time preference:

```text
--pose-backend yolopose
```

Reason:

- YOLO-Pose is much faster in the documented local benchmarks.
- It fits the live loop better.
- The push-up problems are not simply "backend too slow"; they are visibility,
  perspective, and identity problems.

### 6.3 Ball Tracking

Ball tracking includes:

- ball detector;
- robust triangulation;
- reprojection rejection;
- Kalman filter;
- max-speed gate;
- coast-through-dropout;
- ball-only single-camera ray-to-Z-plane fallback.

Important distinction:

```text
Ball-only single-camera fallback exists.
Single-camera ankle fallback does not exist as an active general joint solution.
```

### 6.4 Joint Triangulation

The current live script has `triangulate_multi`.

Known guardrail:

```text
Do not casually edit triangulate_multi.
```

The active joint triangulation path needs at least two valid camera
observations per joint. This is why ankles can disappear in push-ups:

- one camera sees the ankle clearly;
- another camera has the ankle occluded or mislabeled;
- the joint fails the two-camera requirement or triangulates badly.

### 6.5 Smoothing and Prediction

The runtime uses smoothing and Kalman-style prediction to handle noise and
latency. The important engineering tension:

```text
More smoothing gives a stable overlay but increases lag.
Less smoothing gives responsiveness but exposes keypoint jitter.
```

The live coach needs different smoothness than the BLM:

- Coach overlay can tolerate slight visual smoothing.
- Launcher aim needs accurate prediction and explicit safety confidence.
- Assessment reports need transparent quality metrics.

### 6.6 UDP and Closed-Loop Logging

UDP target stream default port:

```text
5005
```

Voice command UDP default port:

```text
5006
```

Event logger:

```text
src/project_cam/closed_loop/event_log.py
```

Canonical event vocabulary currently includes:

```text
session_start
target_chosen
aim_command_sent
ball_launched
athlete_reacted
outcome_scored
safety_gate_blocked
session_end
```

The event log should become the backbone for future projector sessions. Every
projected cue, BLM plan, target reveal, safety block, athlete reaction, and
outcome should be reconstructable from JSONL.

---

## 7. Athlete Assessment Stack

### 7.1 Recording

The assessment stack records JSONL joint streams. Relevant file:

```text
src/project_cam/assessment/udp_record.py
```

Recording stores:

- joints;
- joint confidence;
- joint camera counts;
- metadata;
- session identity.

### 7.2 Kinematics

Kinematics file:

```text
src/project_cam/assessment/kinematics.py
```

This computes frame-level metrics such as:

- joint angles;
- left/right asymmetry;
- pelvis values;
- knee valgus metrics;
- trunk-to-leg angles;
- quality fields.

For push-ups, trunk-to-leg angle depends on the ankle chain. That is why bad
ankles can corrupt the trunk cue.

### 7.3 Offline Assessment

Offline assessment entry point:

```text
src/project_cam/assessment/offline_assess.py
```

Outputs:

- JSON report;
- HTML report;
- optional C3D;
- movement-quality and data-quality separation.

### 7.4 C3D Export

C3D writer:

```text
src/project_cam/assessment/exports/c3d_writer.py
```

Purpose:

- export COCO-17 joints as virtual markers;
- preserve session metadata;
- support tools such as Mokka, Visual3D, OpenSim, and `ezc3d`.

### 7.5 Exercise Rules

Current football academy config:

```text
configs/exercises/football_academy_u10.yaml
```

Active exercises:

- squat;
- push_up.

Deferred exercises include:

- single_leg_squat;
- plank;
- countermovement_jump;
- drop_landing;
- lateral_shuffle;
- cutting;
- slalom_dribble;
- wall_volley.

Important principle from the config:

```text
Use configurable coaching thresholds and each athlete's own baseline; do not
compare children blindly to professional-player templates.
```

---

## 8. Live Coach Architecture

### 8.1 Entry Point

Run:

```bash
apps/athlete_assessment/run_live_coach.sh squat
apps/athlete_assessment/run_live_coach.sh push_up
```

The wrapper runs the canonical parallel live viewer with `--coach-overlay`.

### 8.2 Main Modules

Live trainer modules:

```text
src/project_cam/assessment/live_trainer/rep_state.py
src/project_cam/assessment/live_trainer/coach_overlay.py
src/project_cam/assessment/live_trainer/dashboard.py
src/project_cam/assessment/live_trainer/__main__.py
```

Main responsibilities:

- `rep_state.py`: pure state machine for rep count, phase, depth, cues.
- `coach_overlay.py`: camera selection, ROI, overlay drawing, keypoint repair.
- `dashboard.py`: live dashboard render.
- `__main__.py`: UDP-based trainer runner.

### 8.3 Rep State Machine

The rep counter uses a two-state cycle:

```text
UP/STANDING -> DOWN/DESCENDING -> UP/STANDING
```

For squats:

- signal joint: knees;
- depth mostly from knee angle and pelvis travel;
- cue: knee valgus.

For push-ups:

- signal joint: elbows;
- acquisition gate requires verified push-up posture;
- cue: trunk alignment;
- ankles are not required to acquire a push-up set.

Key protection logic now present in `rep_state.py`:

- push-up acquisition excludes ankles;
- acquire and release are debounced;
- left/right signal asymmetry can hold a frame;
- minimum cycle frames reject fast jitter cycles;
- trunk cue requires both ankles to have enough cameras for a streak;
- push-up elbow signal has angular-velocity spike rejection.

### 8.4 Overlay Pipeline

The overlay path inside the live viewer is:

1. Select camera.
2. Lock camera during active push-up set.
3. Crop stable ROI.
4. Project 3D joints back into the selected camera crop.
5. Repair push-up lower-body overlay keypoints when projected 3D is valid.
6. Stabilize overlay keypoints with EMA, dropout coast, and jump gate.
7. Project coach zone / floor polygon.
8. Render header, skeleton, angle labels, floor guide, depth meter, and cue.

Important current module:

```text
src/project_cam/assessment/live_trainer/coach_overlay.py
```

Key overlay protections now present:

- push-up camera selection weights lower-body visibility;
- stable ROI avoids zoom jitter;
- projected lower-body repair has limb-length sanity checks;
- push-up leg-chain validation drops bad knees/ankles;
- overlay keypoint stabilizer smooths source switches and coasts dropouts;
- push-up floor anchor defaults to wrists;
- ankles are added to the floor line only after a valid streak.

### 8.5 Current Live Coach Tests

As of this documentation pass, the two live-coach test files contain:

```text
tests/test_live_coach_overlay.py: 35 tests
tests/test_live_trainer.py:       25 tests
Total:                            60 tests
```

The older research brief mentioned 43 tests because it was written before the
latest push-up robustness additions. Use the current repo state when claiming
test count.

---

## 9. Push-Up Tracking Failure Model

### 9.1 Main Failure

The main push-up failure is lower-body visibility and identity quality.

When the athlete is in a push-up:

- body is low to floor;
- ankles are far from torso;
- feet may overlap floor clutter;
- knees and ankles may be self-occluded;
- camera view is side/oblique, not clean orthographic side;
- one camera may confidently label a background point as an ankle;
- another camera may not see the joint;
- triangulation can fail, collapse, or produce a plausible-looking wrong point.

### 9.2 Cascade of Bad Leg Geometry

Bad ankle/knee geometry affects multiple downstream systems:

1. **Trunk cue**: trunk-to-leg angle depends on shoulder, hip, and ankle. If the
   ankle is wrong, the cue can falsely say "Trunk bent - keep body straight".
2. **Floor guide**: if floor line uses bad ankles, the line can move above the
   real contact surface.
3. **Overlay skeleton**: bad lower-body joints make the visual overlay look
   broken even if torso/elbows are usable.
4. **Camera selection**: if a camera appears to have legs but they are wrong, a
   bad view may be chosen.
5. **Rep state**: elbow spikes or left/right swaps can open/close cycles if not
   gated.

### 9.3 What Has Been Fixed Recently

Current code contains the targeted fixes recommended by the recent push-up
research:

- Trunk cue now requires sustained ankle reliability, not one frame.
- Push-up floor guide defaults to wrists.
- Ankles enter floor guide only after a temporal validity streak.
- Elbow signal has a velocity clamp.
- Push-up acquisition does not require ankles.
- Push-up camera selection considers lower-body quality.
- Overlay keypoint stabilizer reduces leg jitter.
- Leg-chain validator drops implausible lower-body joints.

### 9.4 What Still Needs Deep Research

The hard remaining problems are deeper than overlay drawing:

- single-camera ankle recovery;
- multi-view identity consistency;
- left/right leg and arm swap tracking;
- triangulation-level outlier rejection;
- per-athlete skeletal priors;
- ROI second-pass pose refinement;
- better logging to classify each bad frame.

The safest next research should not jump immediately into changing
`triangulate_multi`. First collect evidence frame-by-frame:

- raw 2D detections per camera;
- raw confidence per joint;
- `joint_cams`;
- selected camera;
- projected 3D overlay positions;
- final repaired overlay positions;
- rep-state signal angle;
- cue emitted;
- floor anchor IDs used.

---

## 10. Squat Tracking Status

Squat tracking is easier than push-up tracking in this garage.

Reasons:

- athlete is upright;
- knees, hips, and ankles are more visible;
- lower body is not flat on the floor;
- there is less background clutter directly under the joints;
- camera heights give decent front/back or diagonal views;
- depth and knee-angle signals are less dependent on a far ankle point.

Current squat concerns:

- side/diagonal views can still introduce left/right ambiguity;
- perspective can create leg crossing artifacts;
- knee valgus is sensitive to camera and 3D reconstruction quality;
- aggressive depth counting can overcount if thresholds are too permissive;
- youth-athlete movement variability needs baseline-aware thresholds.

Current recommendation:

```text
Do not over-optimize squat until it produces actual false counts or wrong cues.
Push-up lower-body reliability remains the priority.
```

---

## 11. Current Code Reality

### 11.1 Current Verified Files

Core docs:

```text
README.md
CLAUDE.md
CANONICAL.md
docs/project_cam_deep_research_brief.md
docs/capture_sop.md
```

Core live scripts:

```text
Parallel_working/scripts/live_4cam_arena_view_parallel.py
apps/athlete_assessment/run_live_coach.sh
garage_lab_combined/scripts/blm_follow.py
garage_lab_combined/scripts/launcher_runtime_from_udp.py
garage_lab_combined/scripts/live_aim_test.py
garage_lab_combined/scripts/voice_bridge.py
```

Calibration:

```text
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
arena_fixed/cal/extrinsics/extrinsics_fixed.json
arena_fixed/config/calibration_manifest.yaml
garage_lab_combined/cal/intrinsics/
```

Assessment:

```text
src/project_cam/assessment/kinematics.py
src/project_cam/assessment/offline_assess.py
src/project_cam/assessment/reports.py
src/project_cam/assessment/udp_record.py
src/project_cam/assessment/exports/c3d_writer.py
configs/exercises/football_academy_u10.yaml
```

Live coach:

```text
src/project_cam/assessment/live_trainer/rep_state.py
src/project_cam/assessment/live_trainer/coach_overlay.py
src/project_cam/assessment/live_trainer/dashboard.py
tests/test_live_trainer.py
tests/test_live_coach_overlay.py
```

Future adaptive arena design:

```text
docs/superpowers/specs/2026-05-14-adaptive-weakness-arena-design.md
```

### 11.2 Guardrails

Files/functions that should not be changed casually:

```text
triangulate_multi
transform_world_point_y
ema_update
UDP axis semantics
arena_fixed extrinsics and dimensions
BLM firmware safety behavior
launcher shoot gating
```

Reason:

- geometry bugs can silently corrupt all 3D positions;
- Y-axis mistakes can aim the BLM to the wrong side;
- smoothing mistakes can break both display and control;
- firmware mistakes can create physical safety risk.

### 11.3 Known Debt

Known software debt from `CANONICAL.md` and current structure:

- multiple copies of some geometry helpers remain;
- `Parallel_working` is canonical despite its experimental folder name;
- some legacy scripts still exist;
- full `ArenaConfig` / calibration-manifest loading is not uniformly adopted;
- hard real-time 30 FPS product mode still needs sustained validation;
- projector support is not implemented.

---

## 12. Future Product Vision

### 12.1 One-Sentence Vision

```text
Turn a domestic garage into a camera-aware, robot-assisted, projected training
arena that measures an athlete, adapts to their weakness, and produces a coach
report in one short session.
```

### 12.2 Future Athlete Experience

Athlete enters the garage.

The projector shows:

- name / session ready screen;
- calibration stance outline;
- countdown;
- drill instructions;
- target zones;
- score;
- badges;
- safety status;
- final player card.

The cameras observe:

- posture;
- joint motion;
- reaction time;
- tracking quality;
- exercise reps;
- ball flight if enabled.

The BLM acts as:

- a physical challenge source;
- a robot opponent;
- a controllable target generator;
- a way to create reaction and decision-making drills.

The coach receives:

- live dashboard;
- event timeline;
- assessment report;
- C3D export;
- before/after comparison;
- recommended drills.

### 12.3 Future Coach Experience

Coach should be able to answer:

- Did the athlete complete the session?
- Was tracking quality good enough?
- What weakness was detected?
- How confident is the result?
- Did performance improve during the session?
- Which video/event moments should be reviewed?
- What should the athlete train next?

### 12.4 Future Research Value

The projector system can make future research easier because it creates
controlled stimuli:

- projected target appears at known time;
- BLM aim event occurs at known time;
- voice cue occurs at known time;
- athlete reaction measured from 3D pose;
- outcome logged in JSONL;
- all events share one session ID.

This turns messy demo videos into structured experiments.

---

## 13. Garage Projector Plan

### 13.1 Projector Role

The projector is an **arena display actuator**.

It should be treated like another output device:

```text
camera system -> session state -> projector UI
camera system -> session state -> BLM plan
camera system -> session state -> coach report
```

It should not be treated as measurement truth.

### 13.2 What the Projector Should Show

During setup:

- "Camera check";
- "Step into coach zone";
- T-pose / calibration silhouette;
- tracking confidence indicator;
- safe/unsafe state;
- start countdown.

During live exercise:

- rep count;
- target depth;
- floor/contact guide;
- simple corrective cue;
- countdown timer;
- phase indicator.

During adaptive BLM drills:

- target lane;
- "scan left/right" cue;
- "block" or "receive" direction;
- safe zone boundary;
- next ball warning;
- score and combo;
- "pause" / "reload" / "stand clear" status.

After the session:

- player card;
- top weakness;
- before/after delta;
- badges;
- coach report ready indicator.

### 13.3 Recommended First Surface: Wall

The first projector prototype should use wall projection, not floor projection.

Why wall first:

- easier calibration;
- less athlete shadow;
- less foot/body occlusion;
- less ball scuffing;
- easier rectangular display;
- safer for bright projected content;
- easier to keep out of the camera floor region;
- easier to explain in a demo.

Wall projection can show:

- target zones;
- score;
- player card;
- drill instructions;
- large visible countdown;
- safety status;
- "boss" / robot opponent graphics.

### 13.4 Floor Projection Later

Floor projection is attractive because it can show:

- foot placement zones;
- cones;
- agility lanes;
- jump/landing boxes;
- push-up hand positions;
- lateral shuffle targets.

But it is harder:

- athlete blocks the light;
- feet cover the target;
- camera tracking sees projected graphics on the floor;
- bright graphics may confuse detectors;
- parallax becomes more visible;
- floor scuffs and texture affect readability;
- projector must be mounted above or steeply angled;
- keystone correction may reduce precision.

Recommendation:

```text
Prototype wall projection first. Add floor projection only after wall UI and
camera/BLM integration are stable.
```

### 13.5 Top-Down Garage Layout

Coordinate convention:

```text
North wall: X = 0
South wall: X = 6230 mm
East wall:  Y = 0
West wall:  Y = 3050 mm
```

Approximate top-down map:

```text
              North wall, X = 0
        Y=0 ---------------------------- Y=3050
            |         CamNorth          |
            |       (50,1100)           |
            |                           |
            |                           |
 East wall  |                           | West wall
 Y = 0      |                           | Y = 3050
            | CamEast         CamWest   |
            | (1620,50)      (1600,2970)|
            |                           |
            |                           |
            |                           |
            |        Athlete zone       |
            |                           |
            |          BLM              |
            |    approx center lane     |
            |                           |
            |         CamSouth          |
            |       (6180,1530)         |
            -----------------------------
              South wall, X = 6230
```

This is not a final projector mount drawing. It is the coordinate map for
reasoning about placement.

### 13.6 Projector Placement Options

#### Option A: South-Wall Projection

Project onto or near the South wall.

Advantages:

- South wall already has `camSouth`, so its plane is well-described by
  calibration markers.
- Athlete looking south sees the main display.
- Good for player card, target board, and post-session results.

Risks:

- `camSouth` is near that wall, so projection can glare into the camera or
  wash out tags.
- BLM may face toward the same wall depending current orientation.
- Projector must be protected from ball impact.
- If the athlete stands between projector and wall, shadows may appear.

Best use:

- large UI;
- target board;
- coach/athlete display;
- not precise foot placement.

#### Option B: North-Wall Projection

Project onto or near the North wall.

Advantages:

- Far from South-side BLM in many layouts.
- Athlete can face north for non-BLM assessment drills.
- Good for calibration and instruction screens.

Risks:

- Depending camera/projector position, athlete may turn away from BLM.
- May not align with current ball-launch direction.
- Camera glare needs checking.

Best use:

- assessment-only sessions;
- calibration;
- coach UI;
- low-risk first projector tests.

#### Option C: Side-Wall Projection

Project onto East or West wall.

Advantages:

- Visible from the long axis.
- Could be useful for lateral movement drills.
- May avoid direct BLM ball path.

Risks:

- Garage is only 3050 mm wide, so throw distance may be tight.
- Athlete may be close to the wall, causing shadows.
- Side-wall target zones may not match launcher geometry.

Best use:

- lateral shuffle instructions;
- scoreboard;
- side feedback panel.

#### Option D: Floor Projection

Project onto the floor plane `Z = 0`.

Advantages:

- Directly marks where feet/hands should go.
- Useful for agility and exercise zones.
- Feels like an interactive arena.

Risks:

- Highest calibration and shadow complexity.
- Most likely to interfere with pose detection.
- Most likely to be blocked by athlete.
- Requires careful projector angle and brightness.

Best use:

- later phase;
- foot placement;
- agility lanes;
- push-up hand zones;
- cone replacement.

### 13.7 Recommended First Physical Mount

Recommended first prototype:

```text
Fixed high mount, wall projection, protected from balls, outside direct camera
view as much as possible.
```

Practical placement principles:

1. Mount the projector high enough that the athlete does not block most of the
   beam.
2. Keep it below or beside the camera optical axes if direct glare appears.
3. Do not point the projector into any camera lens.
4. Do not wash out AprilTags used for calibration.
5. Keep power and HDMI/USB-C cables away from the athlete and BLM.
6. Put the projector outside the most likely ball-impact path.
7. Use a physical shield if there is any chance a foam ball can hit the lens.
8. Use a fixed mount, not a table, once calibration matters.

### 13.8 Side-View Height Layout

Approximate height context:

```text
Z = 2950 mm  ceiling
             ------------------------------------------------
              possible high projector mount

Z = 2120-2270 mm   cameras high on walls
             [Cam]                              [Cam]

Z = 1500-2000 mm   wall projection / player card / target board
             |--------------------------------------------|
             |        projected game / target UI          |
             |--------------------------------------------|

Z = 500-1200 mm    BLM / athlete torso / ball path area
             [BLM]       athlete movement zone

Z = 0 mm      floor
             ------------------------------------------------
```

Do not put critical text where the athlete's body blocks it during the drill.
For live drills, put essential projected instructions above shoulder height or
to the side of the movement lane.

### 13.9 Projector Safety Rules

Projector safety rules:

- no direct bright beam into athlete eyes;
- no beam directly into camera lenses;
- no loose cable across the floor;
- projector must be mechanically secure;
- projector must not block cameras;
- projector must not block BLM emergency access;
- projected graphics must not hide physical hazards;
- do not rely on projection as the only safety warning;
- stop/reload/estop physical controls must remain visible.

For children:

- avoid flashing patterns;
- avoid distracting graphics during ball launch;
- make "stand clear" obvious and simple;
- keep the coach/operator in control.

### 13.10 Projector Brightness and Detector Interference

The projector changes the visual environment. It can affect:

- pose detector background;
- ball detector background;
- AprilTag contrast;
- camera exposure;
- athlete shadows;
- floor texture.

Mitigation:

- use stable lighting;
- avoid projecting high-contrast human-shaped graphics behind athlete;
- avoid flickering animation in key tracking areas;
- keep calibration tags unprojected or masked;
- test detector confidence with projector on and off;
- log camera exposure settings if possible;
- keep UI away from expected keypoint locations when doing measurement-heavy
  exercises.

---

## 14. Projector Technical Architecture

### 14.1 First Version: Browser Full-Screen UI

The simplest architecture:

```text
session_manager -> local HTTP/SSE UI -> browser full-screen on projector
```

Why browser:

- easy to render text, graphics, score, panels;
- works with HDMI projector as second display;
- can run full-screen in Chrome;
- can receive live state through Server-Sent Events or WebSocket;
- separate from real-time camera loop;
- can be captured for demo video.

Future file idea:

```text
src/project_cam/training_session/game_ui_server.py
src/project_cam/training_session/game_ui_static/
```

This matches the existing Adaptive Weakness Arena design spec.

### 14.2 Event-Driven UI

Do not have projector UI poll random files. Use structured session state.

Suggested event flow:

```text
live viewer -> UDP joints/metrics -> session manager
launcher runtime -> event logger -> session manager
voice bridge -> session manager
session manager -> projector UI events
session manager -> BLM plan packets
session manager -> event log
```

Projected UI states:

```text
idle
camera_check
calibration
baseline_drill
player_card
recon_drill
weakness_reveal
adaptive_hunt
verdict
paused
safety_blocked
technical_fault
```

### 14.3 Coordinate Mapping

For a wall:

```text
world wall plane -> projector pixel
```

Example South wall plane:

```text
X = 6230 mm
Y from 0 to 3050 mm
Z from 0 to 2950 mm
```

A wall target can be defined in world coordinates:

```text
target rectangle:
  wall = south
  y_min_mm = 900
  y_max_mm = 2100
  z_min_mm = 900
  z_max_mm = 1800
```

Then map its four world-wall corners to projector pixels using a homography.

For the floor:

```text
Z = 0
X from 0 to 6230 mm
Y from 0 to 3050 mm
```

Floor projection also uses a homography, but the athlete will often occlude the
surface.

### 14.4 Suggested Future Config

Future config path:

```text
configs/projector/garage_projector.yaml
```

Suggested fields:

```yaml
schema_version: project_cam.projector.v1
projector:
  name: garage_wall_projector
  mode: wall_homography
  output:
    display_index: 1
    width_px: 1920
    height_px: 1080
    fullscreen: true
  surface:
    type: wall
    wall: south
    plane: X=6230
    world_corners_mm:
      top_left: [6230, 2500, 2200]
      top_right: [6230, 500, 2200]
      bottom_right: [6230, 500, 500]
      bottom_left: [6230, 2500, 500]
  homography:
    world_uv_order: [top_left, top_right, bottom_right, bottom_left]
    projector_pixels:
      top_left: [120, 80]
      top_right: [1800, 80]
      bottom_right: [1800, 980]
      bottom_left: [120, 980]
  masks:
    no_project_world_regions:
      - reason: april_tags
        wall: south
        rectangles_mm: []
  safety:
    max_brightness_during_shot: 0.7
    hide_motion_graphics_during_launch: true
```

This file does not exist yet. It is a proposed future config.

### 14.5 Suggested Calibration Procedure

Manual first version:

1. Mount projector physically.
2. Open full-screen calibration page.
3. Project four draggable corner markers.
4. Place the projected rectangle on a known wall/screen area.
5. Enter the corresponding world wall coordinates.
6. Save homography to YAML.
7. Project a grid.
8. Verify with camera screenshots that grid points land where expected.
9. Mask AprilTags or sensitive camera regions.

Camera-assisted version:

1. Project a dot grid.
2. Detect dots in camera frames.
3. Convert camera detections into world wall/floor coordinates using existing
   calibrated cameras.
4. Fit projector homography.
5. Reproject validation points.
6. Report pixel and millimetre residuals.

### 14.6 Validation Metrics for Projector Mapping

For wall projection:

- corner error in projector pixels;
- wall-coordinate error in mm;
- camera-observed validation residual;
- target zone visibility;
- camera detector confidence with projector on/off;
- no glare into cameras.

For floor projection:

- floor-coordinate error in mm;
- occlusion rate from athlete body;
- visibility under shoes;
- pose/ball detector confidence with graphics on/off;
- shadow severity score from camera frames.

Acceptance target for first wall prototype:

```text
Projected target zones land within roughly 30-50 mm of intended wall position.
```

This is enough for visual game cues. It is not enough to claim lab-grade
measurement.

---

## 15. Projector and BLM Integration

### 15.1 Important Separation

The projector shows the target. The BLM launcher runtime decides whether a
physical shot is allowed.

Do not design it as:

```text
projector target -> direct shoot
```

Design it as:

```text
session manager chooses drill intent
session manager shows projected cue
session manager sends target plan to launcher layer
launcher layer applies confidence/safety gates
launcher layer aims or blocks
event log records result
```

### 15.2 BLM Target Constraints

Known constraints from project docs:

- yaw is clamped;
- pitch is clamped;
- RPM gate must pass before shooting;
- full shot safety must be staged and explicitly enabled.

The Adaptive Weakness Arena spec notes pitch clamp `[0, 30]` and yaw clamp
`+/-30`. Treat those as current design constraints unless current firmware
documentation proves otherwise.

Implication:

- Projected low floor targets may be great for footwork, but the BLM cannot
  necessarily shoot at those low targets.
- For BLM-fired drills, target chest/torso-height zones are more realistic.
- Floor zones can be used as movement instructions while the ball targets
  remain safe upper-body zones.

### 15.3 Example Drill With Projector

Drill: lateral defensive slide.

Projected UI:

1. Show athlete start box.
2. Show left and right lanes on wall or floor.
3. Countdown 3, 2, 1.
4. Flash left lane.
5. Voice says "close the lane".
6. BLM aims to chest-height left-side target if safety gates pass.
7. Cameras measure first movement, knee valgus, pelvis movement, reaction time.
8. Projector shows score and form cue.
9. Event log records all events.

Measured data:

- cue timestamp;
- BLM aim timestamp;
- ball launch timestamp if fired;
- pelvis first movement timestamp;
- knee valgus p95 during cut;
- reaction latency;
- success/fail.

### 15.4 Example Drill Without Firing

Drill: projected scan challenge.

Projected UI:

1. Show center target.
2. Flash left/right side icons on wall.
3. Ask athlete to scan both sides.
4. Cameras estimate head direction from pose.
5. Score based on scan timing and body orientation.

No BLM shot needed.

This is safer for early projector integration and useful for debugging UI,
events, and camera interference.

---

## 16. Future Implementation Roadmap

### Phase 0: Documentation and Measurement

Goal:

```text
Stop guessing. Establish physical and software truth.
```

Tasks:

1. Confirm the latest working tree state after Claude/Codex changes.
2. Run current live-coach tests.
3. Record a new push-up and squat screencast after the latest fixes.
4. Add debug logging for bad timestamps and bad push-up frames.
5. Measure projector candidate surfaces in the garage.
6. Choose first projector surface.
7. Record camera frames with a bright screen/projector on to check detector
   interference.

Exit criteria:

- current tests pass;
- latest push-up behavior is re-evaluated;
- first projector surface is chosen;
- no claim is made that projector integration exists.

### Phase 1: Wall Projector Prototype Without BLM Fire

Goal:

```text
Get a stable projected UI in the garage without touching launcher safety.
```

Tasks:

1. Create `configs/projector/garage_projector.yaml`.
2. Create a basic full-screen browser UI.
3. Add manual wall homography calibration.
4. Render calibration grid and target zones.
5. Send fake session events to the UI.
6. Run cameras with projector on and compare pose confidence.

Exit criteria:

- wall UI can run full-screen;
- projector mapping is repeatable after restart;
- cameras still track athlete with projector on;
- no BLM commands are sent.

### Phase 2: Projector Plus Live Coach

Goal:

```text
Use the projector to support squat/push-up sessions.
```

Tasks:

1. Mirror live coach state to projector UI.
2. Show rep count, phase, and cue on the wall.
3. Show "step into coach zone" and "low tracking".
4. Show exercise-specific simple visuals.
5. Log projected cue timestamps.

Exit criteria:

- live coach overlay and projector UI agree on rep count and cue;
- projected text is readable from athlete position;
- no projected graphics degrade tracking.

### Phase 3: Adaptive Session Manager

Goal:

```text
Create a session state machine that can orchestrate drills, projector UI,
voice, metrics, and logs.
```

Future module:

```text
src/project_cam/training_session/
```

Suggested files:

```text
session_manager.py
live_metrics.py
weakness_detector.py
adaptive_targeter.py
game_ui_server.py
projector_mapper.py
projector_calibration.py
drill_library.py
coach_report.py
```

Exit criteria:

- one full no-fire drill runs end to end;
- session JSONL reconstructs every state transition;
- projected UI follows session state;
- coach report can consume the event log.

### Phase 4: BLM Aim-Only Integration

Goal:

```text
Connect adaptive plans to BLM aim without firing.
```

Tasks:

1. Add a plan-packet input to the launcher layer, disabled by default.
2. Convert drill target to launcher target.
3. Aim with `--no-shoot-enabled`.
4. Log safety blocks and aim decisions.
5. Display BLM state on projector.

Exit criteria:

- BLM moves according to drill plan;
- no firing;
- all aim decisions are logged;
- safety blocks are visible on projector and coach UI.

### Phase 5: Controlled Foam-Ball Live Fire

Goal:

```text
Only after safety validation, run controlled low-speed foam-ball drills.
```

Tasks:

1. Re-run BLM preflight.
2. Verify RPM-to-speed calibration.
3. Verify pitch/yaw constraints.
4. Add operator armed state.
5. Use only chest-height safe target zones.
6. Fire only after confidence gates pass.
7. Record full event and video session.

Exit criteria:

- safety procedure documented;
- operator can pause/stop instantly;
- no unlogged shots;
- no child/youth session until adult/self tests pass.

### Phase 6: Floor Projection

Goal:

```text
Add floor cues only after wall projection is reliable.
```

Tasks:

1. Add floor homography.
2. Test shadows.
3. Test detector confidence with floor graphics.
4. Add foot placement zones.
5. Add agility lane graphics.
6. Add floor masks to avoid confusing pose/ball detection.

Exit criteria:

- floor targets are visible;
- pose confidence does not drop materially;
- athlete can understand cues while moving;
- calibration survives projector restart.

### Phase 7: Pilot Product

Goal:

```text
Deliver a short, coach-friendly, athlete-friendly session.
```

Output:

- 5-minute athlete session;
- projected game UI;
- optional safe BLM drill;
- report JSON;
- HTML/PDF coach report;
- C3D export;
- replay video;
- event audit log.

---

## 17. Projector Research Questions

Before buying or mounting anything, answer these with measurements:

1. Which wall has the cleanest projection surface?
2. Which wall can be used without shining into cameras?
3. Which wall is outside the most likely BLM ball path?
4. Where can a projector be mounted securely?
5. Is there power near the mount?
6. Can cables be routed away from the athlete?
7. What is the required throw distance for the desired image size?
8. Does the projector need short-throw?
9. Is the room bright enough that the projection washes out?
10. Does projection reduce YOLO-Pose confidence?
11. Does projection reduce ball detector confidence?
12. Does projection wash out AprilTags?
13. Does the athlete cast a severe shadow?
14. Is the projected text readable during motion?
15. Can the operator see and override the session at all times?

Avoid choosing a projector model before answering the physical placement and
throw-distance questions.

---

## 18. Deep Research Checklist for the Next LLM

Give the next LLM this checklist.

### 18.1 First Read

Read these files first:

```text
README.md
CLAUDE.md
CANONICAL.md
docs/project_cam_deep_research_brief.md
docs/project_cam_full_work_and_projector_plan.md
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
apps/athlete_assessment/run_live_coach.sh
Parallel_working/scripts/live_4cam_arena_view_parallel.py
src/project_cam/assessment/live_trainer/rep_state.py
src/project_cam/assessment/live_trainer/coach_overlay.py
configs/exercises/football_academy_u10.yaml
docs/superpowers/specs/2026-05-14-adaptive-weakness-arena-design.md
```

### 18.2 Repo-First Rules

Rules for the next LLM:

- Do not infer implementation from external articles if repo code is available.
- Do not recommend geometry-critical changes without proving the current
  failure source.
- Do not edit `triangulate_multi` casually.
- Do not edit axis semantics casually.
- Do not claim projector integration exists yet.
- Do not claim professional motion-capture conditions.
- Do not use the old 5 m x 5 m arena framing.

### 18.3 Push-Up Review Checklist

For each bad push-up timestamp, log:

- video timestamp;
- exercise phase;
- selected camera;
- `joint_cams` for shoulders, elbows, wrists, hips, knees, ankles;
- `joint_conf` for same joints;
- raw 2D pose scores per selected camera;
- projected 3D keypoints in ROI;
- repaired overlay keypoints;
- final stabilized overlay keypoints;
- floor anchor IDs;
- ankle streak;
- trunk cue emitted or suppressed;
- elbow raw angle;
- elbow clamped angle;
- smoothed signal;
- rep state.

Classify each failure:

- missing triangulation;
- confident wrong triangulation;
- raw 2D selected-camera issue;
- projected 3D overlay issue;
- overlay-only rendering issue;
- state-machine issue;
- cue logic issue;
- camera selection issue.

### 18.4 Projector Review Checklist

For projector planning, collect:

- exact desired projection surface;
- wall/floor dimensions;
- mount height;
- throw distance;
- image size;
- camera glare screenshots;
- AprilTag visibility with projector on;
- pose confidence with projector on/off;
- ball detector confidence with projector on/off;
- shadow severity;
- athlete readability;
- cable/power constraints;
- ball-impact risk.

### 18.5 Safety Checklist

Before live-fire projector sessions:

- BLM preflight passed;
- launcher stop works;
- emergency stop path clear;
- no loose cables;
- projector protected;
- no direct eye beam;
- all shots logged;
- operator armed state required;
- no child sessions before adult/self validation;
- report distinguishes measured facts from game graphics.

---

## 19. Suggested Prompt for Claude or Another LLM

Use this if you want another implementation LLM to review and work on the repo:

```text
You are working on Project_Cam. This is a real local repository for a
four-camera domestic-
garage 3D pose, ball-tracking, BLM launcher, athlete
assessment, and live-coach system.

First read these files carefully:
- docs/project_cam_full_work_and_projector_plan.md
- docs/project_cam_deep_research_brief.md
- README.md
- CLAUDE.md
- CANONICAL.md
- arena_fixed/cal/extrinsics/Dimensions_fixed.txt
- apps/athlete_assessment/run_live_coach.sh
- Parallel_working/scripts/live_4cam_arena_view_parallel.py
- src/project_cam/assessment/live_trainer/rep_state.py
- src/project_cam/assessment/live_trainer/coach_overlay.py
- configs/exercises/football_academy_u10.yaml
- docs/superpowers/specs/2026-05-14-adaptive-weakness-arena-design.md

Do not assume the arena is 5 m x 5 m. The verified garage is
6230 mm x 3050 mm x 2950 mm. Do not describe it as a professional
motion-capture lab.

Separate current reality from future design. The projector plan is future
design unless you find implemented code and tests.

Before implementing anything:
1. Summarize the current repo state.
2. Identify which proposed items are already implemented.
3. Identify which proposed items are not implemented.
4. Recommend the smallest safe patch set.
5. Do not modify geometry-critical functions such as triangulate_multi,
   transform_world_point_y, ema_update, or UDP axis semantics unless you can
   prove the issue and explain tests.

For live coach, pay special attention to push-up lower-body reliability,
ankle/knee identity, trunk cue gating, floor anchor logic, elbow signal spikes,
and selected-camera behavior.

For projector work, start with documentation or a no-BLM-fire wall-projection
prototype. Do not connect projector UI directly to physical shooting.
```

---

## 20. Evidence Index

### 20.1 Verified Current Reality

Arena dimensions and camera positions:

```text
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
```

Project overview and arena setup:

```text
README.md
```

Current canonical stack:

```text
CANONICAL.md
```

Runtime guardrails and active BLM/voice facts:

```text
CLAUDE.md
```

Live coach wrapper:

```text
apps/athlete_assessment/run_live_coach.sh
```

Canonical live viewer:

```text
Parallel_working/scripts/live_4cam_arena_view_parallel.py
```

Exercise rules:

```text
configs/exercises/football_academy_u10.yaml
```

### 20.2 Current Live Coach Evidence

Rep state:

```text
src/project_cam/assessment/live_trainer/rep_state.py
```

Coach overlay:

```text
src/project_cam/assessment/live_trainer/coach_overlay.py
```

Live coach tests:

```text
tests/test_live_trainer.py
tests/test_live_coach_overlay.py
```

### 20.3 Assessment Evidence

Capture SOP:

```text
docs/capture_sop.md
```

Kinematics:

```text
src/project_cam/assessment/kinematics.py
```

Offline assessment:

```text
src/project_cam/assessment/offline_assess.py
```

C3D export:

```text
src/project_cam/assessment/exports/c3d_writer.py
```

Event logging:

```text
src/project_cam/closed_loop/event_log.py
```

### 20.4 Future Design Evidence

Adaptive Weakness Arena design:

```text
docs/superpowers/specs/2026-05-14-adaptive-weakness-arena-design.md
```

Deep research brief:

```text
docs/project_cam_deep_research_brief.md
```

This file:

```text
docs/project_cam_full_work_and_projector_plan.md
```

---

## 21. Final Notes

The projector can make Project_Cam feel much more like a complete training
arena, but it should be added carefully. The camera system is already sensitive
to lighting, occlusion, calibration, and perspective. A projector adds visual
power but also adds new failure modes.

The correct order is:

1. Stabilize and verify current live coach.
2. Add projector as display-only wall UI.
3. Validate tracking with projector on.
4. Add session orchestration.
5. Add BLM aim-only integration.
6. Add controlled live fire only after safety gates are proven again.
7. Add floor projection last.

That order keeps the system honest: measurement first, display second, physical
actuation last.
