# Push-up and Squat Coach — Improvement Brief for an External LLM

You are advising on a real-time vision-guided fitness coach for kids' push-up
and squat assessment. The system works end-to-end; the rep counter is
reliable; what remains is a class of *tracking-quality* problems that I want
fresh ideas on. Below is the full context.

## 1. Hardware and arena

- 4 fixed USB cameras (`camNorth`, `camEast`, `camSouth`, `camWest`) mounted
  at elevated positions around a ~5 m × 5 m arena. Cameras are
  calibrated (intrinsics `K, D` + extrinsics `R, t`, all in millimetres).
- Capture: 1280×720, 15 FPS target.
- World frame: X = arena length, Y = arena width, Z = vertical (up). Origin
  at arena corner. All coordinates in mm.
- Floor is the action surface; a thin mat in the middle for push-ups.
- GPU: RTX 2080 Ti. YOLO11m-Pose exported to TensorRT FP16, dynamic batch=4
  (~6 ms per 4-camera batch). MMPose was the previous backend (~40 ms/img);
  we chose YOLO-Pose for the FPS budget.
- The lab is cluttered: cables, balls, boxes, mats, a basketball net frame,
  a footwear pile — i.e. lots of false-positive candidates for "leg-like"
  blobs near the floor.

## 2. Per-frame pipeline

1. Threaded capture of 4 frames.
2. YOLO11m-Pose batched on 4 frames → 17 COCO-17 keypoints per camera
   (`x, y, score`).
3. Multi-view SVD triangulation per joint → 3D world-frame point (mm) +
   `joint_conf` (reprojection-based) + `joint_cams` (number of cameras the
   joint was seen by; ≥2 required to triangulate).
4. Per-joint Kalman filter (constant-velocity, PN=500, MN=10), 400 ms ahead
   prediction.
5. Frame kinematics computes:
   - `angles_deg`: elbows, knees, shoulders, hips, `trunk_to_leg`
     (shoulder–hip–ankle).
   - `distances`: shoulder width, hip width, stance width, pelvis Z.
   - `asymmetry_deg`: |L − R| per joint.
   - `posture.torso_incline_deg`: inclination of shoulder_mid → hip_mid,
     in `[0°=plank, 90°=standing]`.
   - `quality.joint_conf`, `quality.joint_cams` (per-joint).
6. Rep counter consumes kinematics → `state.{rep_count, phase, acquired, cue, ...}`.
7. Coach overlay picks the best camera, crops a stable ROI, projects 3D
   joints → 2D in that camera, repairs weak raw 2D, smooths temporally,
   validates legs, draws skeleton + angles + floor line + cue.

## 3. Rep counter (`src/project_cam/assessment/live_trainer/rep_state.py`)

Two-state hysteresis on the smoothed signal angle (elbow for push-up, knee
for squat). EMA smoothing on the L+R averaged signal.

YAML thresholds (`configs/exercises/football_academy_u10.yaml`):

```yaml
push_up.live_trainer:
  descent_angle_deg: 138       # smoothed elbow bends past this -> open
  bottom_angle_deg: 122        # at/below this -> depth gate satisfied
  top_angle_deg: 150           # smoothed elbow straightens past this -> close
  min_rom_deg: 45              # min ROM for a valid rep
  noise_rom_deg: 18            # smaller ROM -> ignored as noise
  smoothing_alpha: 0.6
  min_cycle_frames: 5
  max_signal_asymmetry_deg: 45
  max_posture_incline_deg: 35  # acquisition: torso incline upper bound
  acquire_min_frames: 4        # consecutive plank frames to acquire a set
  release_min_frames: 8        # consecutive lost frames to release a set
```

Squat block is analogous but on knee angle, with
`min_pelvis_travel_mm: 150` as an OR-path depth gate (a deep enough pelvis
drop also counts as full depth).

**Push-up acquisition gate (`_pushup_posture_ok`):**
- `torso_incline_deg ≤ 35°`.
- Both `left_elbow` and `right_elbow` angles present (this implies both
  shoulders, elbows, wrists, and hips are present).
- **Deliberately does NOT require ankles.** Ankles are unreliable in
  oblique side views, and depending on them used to flicker the gate
  mid-set.

The gate is debounced both ways: 4 consecutive verified-plank frames to
acquire a set; 8 consecutive lost frames to release it. While `acquired`
but the current frame isn't a verified plank (tracking dropout or
half-stood), the state machine is **held** — never advances or closes a
cycle. This is what kills "stand up = false rep".

Other safeguards:
- `max_signal_asymmetry_deg = 45`: if L/R elbow disagree more than this,
  the frame is held (signature of a keypoint swap).
- `min_cycle_frames = 5`: a closed cycle spanning too few frames is
  treated as noise (kills rapid double counts).
- Trunk-misalignment cue is suppressed when ankle `joint_cams < 2`.

## 4. Coach overlay (`src/project_cam/assessment/live_trainer/coach_overlay.py`)

- **Camera selection (`select_best_camera`):**
  - Squat: `0.72·align + 0.28·pose_score`. Prefers front/back views.
  - Push-up: `0.55·align + 0.20·pose_score + 0.25·leg_score`. Prefers side
    views *with visible legs* (the leg term is a recent fix because the
    selector used to ignore legs entirely).
  - `align` = `|view · desired_body_axis|` where desired is lateral for
    push-up, forward for squat.
- **Sticky camera lock:** during a push-up set the camera stays locked.
  After acquisition loss the lock holds for a 30-frame (~2 s) grace
  window so a brief posture-gate flicker doesn't trigger a disorienting
  switch.
- **ROI:** fixed-size 720×560 crop, EMA-panning, no auto-zoom.
- **Keypoint repair (`repair_overlay_keypoints`):** projects 3D joints
  back to 2D for push-up lower body (hips, knees, ankles) and substitutes
  over weak raw 2D when valid. Substitution requires the resulting bone
  to its parent be within 4× shoulder span.
- **Temporal stabilizer:** per-joint EMA (α=0.5), coast through 6 missing
  frames, jump gate rejecting a >160-px single-frame teleport, snap on
  re-acquire.
- **Leg validation (`validate_leg_chain`):** anchors on the shoulder→hip
  torso axis; per side validates knee then ankle. Bone length must be
  within `[0.30, 1.9]×` torso (single segment) or `[0.6, 3.2]×` (hip→
  ankle full leg if knee was dropped); direction must be within ±60° of
  the body axis; per-joint score must be ≥ 0.5. Failing joints get score
  zeroed → not drawn.

The floor line is drawn at median y of valid wrists + ankles. With leg
validation dropping bad ankles, it falls back to wrists (the real
push-up floor contact).

## 5. What works today (verified against two screencasts)

- No false reps while standing/walking. Acquisition gate + debouncing
  block phantom cycles during walk-in.
- No false count while standing up at end of set. The "held" state
  during non-plank frames prevents the rising elbow from closing a cycle.
- Squat counting is solid.
- Camera locks during a set.
- Skeleton attaches to upper body (shoulders/elbows/wrists/hips)
  reliably.
- Trunk-misalignment cue no longer fires falsely when ankles aren't
  multi-cam tracked.

## 6. What still fails

### P1 — Legs mistracked during push-ups, oblique side views (dominant)

**Symptom:** during a real push-up the hip→knee→ankle chain attaches to
floor clutter (cables, boxes, shoes) or splays. Not a teleport — it's
**stably wrong** frame after frame in roughly the same place.

**Why:** YOLO11m-Pose mis-detects legs when the body is low to the
floor and the camera is oblique. Legs are foreshortened, partly
occluded by the torso, and easily confused with floor clutter. To
triangulate a joint we need ≥2 cameras; for push-up legs only 1 camera
often sees them clearly.

**Current mitigation:** `validate_leg_chain` *drops* untrustworthy leg
joints rather than drawing them wrong. The overlay is honest but the
legs are then simply absent. We do not currently recover correct leg
positions.

**Constraints:** pose backend is YOLO11m-Pose TRT FP16 (chosen for the
~6 ms latency budget). Switching backends has cost. Cameras are
calibrated and physically fixed; re-mounting is possible but expensive
in calibration time.

### P2 — Push-up depth measurement could be more robust

Depth gate is `smoothed_elbow ≤ 122°`. But:
- Short-armed kids have smaller absolute elbow angles at depth.
- A truly deep push-up (chest-to-floor) and a half-rep can have similar
  elbow angles depending on technique.
- Pelvis Z drop is available but the squat-style `min_pelvis_travel_mm`
  OR-path is not used for push-ups.

### P3 — Per-athlete proportions not learned

Each child has different limb lengths. `validate_leg_chain` uses a
single torso anchor with ratios `[0.3, 1.9]×`. A per-athlete anchor
(learned from the first few clean frames of a set) would be tighter.

### P4 — Squat valgus / knee tracking quality

Squat counting works, but the *form metrics* (knee valgus, knee-line
deviation) depend on knees being accurately tracked. We don't have a
knee-specific validator.

### P5 — Single-camera fallback for joints

The ball pipeline has `project_ray_to_z_plane`: when only 1 camera sees
the ball, we intersect that camera's undistorted ray with a known
Z-plane (floor) to get a 3D point. The same idea might work for push-up
ankles (floor Z = 0 is known). We don't currently do this for joints,
only for the ball.

## 7. Guardrails — do not violate

- All coordinates in mm.
- Do not modify these functions without strong justification:
  `triangulate_multi` (SVD), `transform_world_point_y`, `ema_update`,
  UDP payload schema (axis order is consumed by a launcher hardware
  device downstream).
- Don't trade geometric correctness for FPS without explicit approval.
- Squat path must not regress. Any push-up change must leave squat
  behavior identical.
- The test suite at `tests/test_live_trainer.py` and
  `tests/test_live_coach_overlay.py` (97 tests) defines expected
  behavior. Any change must keep them all passing.

## 8. What I'm asking from you

Concrete, technically-grounded ideas. Not generic "improve the model".
Address as many of these as you can:

1. **Recovering correct push-up legs** (the main open problem):
   - Would running a higher-resolution pose model on a leg-ROI crop help,
     and how to integrate it inside the ~15 FPS budget?
   - Would a single-camera ray-to-floor-Z-plane projection for ankles
     (analogous to our ball pipeline) work? What are its failure modes
     for joints vs balls?
   - Would a per-set leg anchor (learn limb lengths from the first few
     good frames, then enforce them) make sense? How to do it robustly
     without a startup delay the athlete can feel?
   - Are there lightweight 2D pose refinement networks (HRNet, ViTPose-S,
     RTMPose) that could run as a "second pass" on a leg crop only, on
     the camera that already has the best leg view? Latency budget?
   - Multi-hypothesis association — keep top-K detections per joint and
     pick the chain that minimises a global plausibility cost?

2. **Push-up depth measurement.** Is smoothed elbow angle the right
   primitive? Would chest-Z, shoulder-Z, or pelvis-Z be more robust?
   How to combine signals without making the counter flaky on different
   body types?

3. **Per-athlete proportions.** How to learn and use limb-length priors
   *during* the first few clean frames of a set without latency.

4. **Squat form metrics quality.** Specific ideas for tightening valgus
   and knee-line measurements given the 4-cam triangulation pipeline.

5. **Camera placement / coverage.** Given the 4 fixed elevated cameras
   and floor-level action, is there a re-arrangement that would
   fundamentally fix the legs problem, or are we stuck with this
   geometry?

6. **Anything we're missing.** If there's a class of approach we haven't
   considered (e.g., physics-informed priors, multi-task pose models
   that predict joint visibility, body-part attention, learned
   plausibility nets), name it concretely and say what it would take
   to integrate.

## 9. Response format

A prioritised list. Each item with:
- The idea in 1 short paragraph.
- What code or data we would need to change (be specific — file paths,
  function names, new helpers).
- Expected impact on the open problems (P1–P5).
- Risk / failure modes.
- Rough integration cost (LOC, latency, calibration effort).

No preamble, no fluff, no "great question." If you don't have a
concrete idea for an item, skip it.
