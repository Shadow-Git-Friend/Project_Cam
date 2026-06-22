# Project_Cam / Proxiball 3D — Master Brief for an External LLM
### Self-contained whole-project context · 2026-05-28

**Read this first.** You are an LLM being asked to reason deeply about this project. You can browse the
repository on GitHub but you do **not** have the author's local machine. This document is written to be
**self-contained**: it explains the whole system, the current hardware, the arena, where the cameras
are and where they *should* be, what currently works, what is broken, and the open questions the author
wants help with. Repo paths are given inline so you can open them on GitHub for detail.

> **Honesty rules (the author insists on these):** this is a **domestic garage**, not a professional
> motion-capture lab. It is **not** 5 m × 5 m. The cameras are **not** synchronized global-shutter
> units (yet). Do not assume Vicon/OptiTrack accuracy. When a fact is a measurement, it's labelled as
> such; when it's a plan or estimate, it's labelled too.

---

## 1. What this project is

- **Title:** *Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking.*
- **Author:** Hanush — MSc ECE, Nazarbayev University, Astana, Kazakhstan. (Master's thesis project.)
- **One sentence:** four fixed cameras reconstruct a person's **pose** and a **ball** in 3D inside a
  garage arena; a custom **Ball-Launching Machine (BLM)** aims and fires at chosen targets (a body joint
  or a projected goal); a **projector** paints interactive targets on a wall.
- **Two faces of the project:**
  1. **Thesis (now):** prove the method — multi-view triangulation, pose-guided ballistic targeting,
     and a safety state machine on the launcher. Accuracy already meets the thesis targets.
  2. **Product vision (later) — "Proxiball 3D":** a low-cost installable football/athlete training +
     biomechanics arena for academies (see `Project_Cam_Deep_Research_Report_Converted.pdf` and
     `proxiball_3d-main/projectors_research.md`). Not in scope for the thesis, but it drives some
     hardware decisions (cameras, projector, safety).

---

## 2. The garage arena (geometry + coordinate frame)

Authoritative source: `arena_fixed/cal/extrinsics/Dimensions_fixed.txt`.

```
Arena (measured):  X = 6230 mm (length)   Y = 3050 mm (width)   Z = 2950 mm (height)
World origin:      North-East floor corner = (0, 0, 0); units = mm
North wall: X = 0        South wall: X = 6230   (← the garage door; projection + impact surface)
East wall:  Y = 0        West wall:  Y = 3050
Z: vertical, up from floor
```

- Walls are calibrated with **AprilTag** markers (extrinsics); each camera's intrinsics come from
  **ChArUco** capture. `arena_fixed/` owns the Y-axis convention and the current extrinsics — treat it
  as the geometry source of truth.
- The **South wall is the garage door**: it is both the **projection surface** for the goal game and the
  **ball-impact surface**. (The product report argues this dual use is problematic; see §7.)

---

## 3. Cameras — current hardware and placement

**Hardware (measured — see `cameras.md`):** 4× **Hikvision DS-E12**, **rolling-shutter, USB 2.0**,
1920×1080 MJPG @ 30 fps (recently unlocked; long-stable point was 1280×720 @ 15 fps). All four share
**one** Intel xHCI USB controller → shared bandwidth. **No hardware synchronization.** Effective
**~15–18 fps ceiling** (USB-2 isochronous contention + inference). Connected via 5 m / 10 m active USB
extension cables (which still negotiate only USB-2).

**Placement.** Original (`Dimensions_fixed.txt`, cm → mm):

| Camera | Position (mm) | Mount | Faces |
|---|---|---|---|
| camNorth | (50, 1100, 2260) | high on **North** wall | **south, face-on to the impact/projection wall** |
| camSouth | (6180, 1530, 2270) | high on **South** wall | north (mounted *on* the impact/projection wall) |
| camEast | (1620, 50, 2120→**~450**) | **East** wall — **remounted low 2026-05-25** | across the arena (lateral) |
| camWest | (1600, 2970, 2170→**~450**) | **West** wall — **remounted low 2026-05-25** | across the arena (lateral) |

**Recent remount (2026-05-25, `Remounted_West_East/`):** camEast & camWest were lowered from ~2.1 m to
**~0.45 m** to capture **legs/ankles during push-ups** (the high mounts couldn't see horizontal floor
postures). This new bundle is a **candidate calibration** at 1920×1080 — **not yet fully validated for
live geometry** (important; see §6). The projector goal game runs on this bundle.

---

## 4. The full pipeline (how a frame becomes an action)

Canonical live path: `Parallel_working/scripts/live_4cam_arena_view_parallel.py` (see `CANONICAL.md`).

1. **Capture** — threaded grab from the 4 USB cameras (buffer size 1 to reduce latency).
2. **Detect (per camera):**
   - **Ball:** YOLO TensorRT engine `models/ball/yolo26m-672.engine` (FP16, imgsz 672).
   - **Pose:** YOLO-Pose (`yolo11m-pose`, ~6× faster) or MMPose (RTMDet+RTMPose).
3. **Triangulate (multi-view):** `triangulate_multi()` (SVD) for joints; `robust_triangulate_ball()`
   (iterative reprojection-rejection) for the ball. **These functions are geometry-critical — protected.**
4. **Smooth + predict:** per-point **Kalman filter** (constant-velocity) for jitter + 200–400 ms lookahead.
5. **Broadcast:** 3D targets over **UDP** to the launcher runtime.
6. **Act (BLM):** the launcher applies **safety gates** (zone, confidence, min-cameras, angle clamps,
   RPM gate) then aims/fires.

**Measured performance (15 fps operating point, `cameras.md`/`CLAUDE.md`):** post-correction precision
~3–4 mm; ball static error ~95–157 mm, joint-touch ~143–179 mm (systematic bias, correctable by the
correction model); pose-to-aim latency ~50 ms; YOLO ~8 ms, YOLO-Pose 6–9 ms (TRT).

---

## 5. Subsystems

- **BLM (Ball-Launching Machine):** ESP32, firmware `control_12_full.ino`, **921600 baud**, flywheel
  **RPM gate** before firing, stepper aiming (pitch/yaw clamped ±30°), pusher/reload, safety FSM.
  Safety stages **S0–S4 + integrated live fire PASSED (2026-04-09)**. Perception decides targets; the
  launcher enforces safety. (`garage_lab_combined/scripts/`, `.claude/rules/safety.md`.)
- **Voice bridge:** colleague's **Vosk** model in a separate venv → UDP to the BLM follow script
  (joint selection, shoot/reload by voice). Multi-venv to avoid polluting the project env.
- **Projector goal game (NEW, 2026-05-28):** `proxiball_3d-main/projector/` — projects a **3×3 grid**
  (A1–A3 / B1–B3 / C1–C3) on the South wall; each camera projects its ball detection onto the wall
  plane → grid zone; **consensus voting** across cameras (+ a 0.25 s temporal window) decides a HIT
  (ball in the active target zone) or MISS (other zone). SCORE/MISS HUD. Calibration from
  `Remounted_West_East/`; grid bounds from `proxiball_3d-main/projector/homography.json`.

---

## 6. What currently works vs what is broken

**Works:** per-camera YOLO **ball detection is good** (median confidence ~0.87); pose pipeline,
triangulation math, Kalman, UDP, BLM safety + live fire on joints, voice, the projector game's
rendering/scoring loop, recording tools.

**Broken right now (the most important thing for you to understand):** the projector goal game barely
scores, and the recorded session (`IMG_1962.MOV`) + the system's own telemetry show **the multi-camera
geometry essentially never agrees**. Analyzing 32,217 logged frames
(`docs/video_analysis_IMG_1962_2026-05-28.md`):

- ≥2 cameras detect a ball in 42–52 % of frames, **but 0 of 14,604 of those frames triangulated below
  200 px reprojection error** (median ~1,400 px; the camEast+camNorth pair ~48,600 px).
- **camSouth detections never map into the grid (0 %).**
- Consensus (a scorable crossing) is reached in **~0.05 %** of frames; dominant `no_hit_reason` is
  `no-consensus` (74–80 %).

**Interpretation (layered causes, most→least dominant):**
1. **Calibration is off** for the current `Remounted_West_East/`-at-1920×1080 setup. Suspects:
   intrinsics not regenerated/scaled for the runtime resolution; post-remount extrinsics inconsistent;
   `homography.json` calibrated at **1920×1200** but the projector runs at **1920×1080** (the app prints
   this warning). This is a **free software fix** and the **immediate blocker**.
2. **No hardware sync + rolling shutter** (hardware ceiling): even with perfect calibration, the 4
   un-synced rolling-shutter cameras cannot triangulate a *fast* ball (each sees it at a different
   instant/position). This is why the author bounces the ball first (slow rebound = detectable). Fixed
   only by **global-shutter, hardware-triggered cameras** — see
   `docs/camera_procurement_research_2026-05-28.md`.

> **Key takeaway for you:** "buy new cameras" is necessary for fast play, but will **not** fix the
> current scoring failure on its own — recalibration must happen too.

---

## 7. Camera placement — current weaknesses and how to allocate better

This is an area the author explicitly wants help reasoning about.

**Problem 1 — camSouth is on the wall it must score.** camSouth (6180,1530,2270) sits **on the South
wall**, the very surface the grid is projected on and balls hit. A camera mounted on the target wall
cannot localize *where* on that wall a ball lands (balls approach head-on; the wall is around/behind the
camera). This matches its **0 % in-grid** telemetry. The product report
(`Project_Cam_Deep_Research_Report_Converted.pdf`) independently flags camSouth as also sitting **in the
projector's light cone** and recommends **relocating it** (e.g., to a corner looking diagonally across
the arena).

**Problem 2 — two tasks want different layouts (only 4 cameras).**
- **Pose / athlete assessment** (push-ups, squats) wants full-body coverage incl. ankles/knees → drove
  the **low** East/West remount and keeps North/South high. Optimized for *people*.
- **Ball + goal detection** wants cameras viewing the **impact wall face-on** plus the **flight and
  bounce volume**. Best: camNorth (far, face-on). Worst: camSouth (on the wall). Lateral cams help only
  if they see the wall plane well.
- These pull in different directions; the current rig is tuned for pose, which partly explains the poor
  goal-detection geometry.

**Problem 3 — bounce blind-spot.** Documented (`.claude/rules/perf.md`, CLAUDE.md): at the moment a ball
bounces near the wall, **only camNorth reliably sees it** (~58–98 % with higher input resolution); the
other three are 10–17 % regardless of detector tuning — the ball is geometrically outside their
frustums. So the floor-near-wall region is under-covered.

**Suggested directions to evaluate (not yet decided):**
- **Stop scoring from a camera mounted on the target wall.** Relocate/repurpose camSouth (PDF suggests a
  corner diagonal mount) so it adds flight-path coverage instead of bad south-wall votes.
- **Guarantee ≥2 cameras with overlapping, face-on views of the full ball flight path AND the
  bounce/floor-near-wall region** to kill the blind-spot.
- With **global-shutter + hardware sync** (the planned upgrade), placement can prioritize
  baseline/overlap and the dominant task without worrying about temporal skew.
- If the project later affords **>4 cameras**, the clean separation is a **dedicated wall-facing stereo
  pair for goal detection** + the **4-cam pose rig** — instead of forcing one 4-cam array to do both.
- **Discipline:** any placement change requires re-running **intrinsics (at the runtime resolution) +
  extrinsics + projector homography**, validated to **< 25 px** reprojection on a static ball before the
  geometry is trusted.

---

## 8. Open questions (where the author wants your deep thinking)

1. **Root-cause the calibration failure.** Given §6's numbers (0 frames < 200 px; camSouth 0 % in-grid;
   homography 1920×1200 vs runtime 1920×1080; recent remount), what is the most likely chain of errors
   and the minimal fix sequence? How to verify (acceptance gates)?
2. **Optimal 4-camera placement** for the *dual* pose + goal-detection task in a 6230×3050×2950 mm
   garage with a South-wall projection/impact surface. Should camSouth move? Where? What's the
   coverage/accuracy trade-off vs the push-up pose needs?
3. **Camera upgrade** — review/critique `docs/camera_procurement_research_2026-05-28.md` (global-shutter,
   hardware-synced, GigE-PoE vs USB3, KZ sourcing) and the integration plan (a `CameraSource`
   abstraction; ESP32 hardware trigger).
4. **Bounce blind-spot** — placement and/or sensing changes to capture the ball at/after bounce.
5. **Closed-loop accuracy** — RPM→ball-exit-velocity calibration (the ballistic solver currently assumes
   a fixed ~10 m/s; shot accuracy degrades at higher RPM).
6. **Pose limitation** — push-ups require the body axis along Y (E–W); N-facing reps are geometrically
   degenerate (see project memory / SOP). Better mitigations?

---

## 9. Repository map (navigate on GitHub)

| Path | What it is |
|---|---|
| `Parallel_working/scripts/live_4cam_arena_view_parallel.py` | **Canonical** live viewer: capture→detect→triangulate→Kalman→UDP; owns the ball-tracking robustness logic |
| `garage_lab_combined/` | Production runtime: BLM scripts (`launcher_runtime_from_udp.py`, `blm_follow.py`, `live_aim_test.py`), configs (`config/runtime.yaml`, `config/cameras.yaml`) |
| `arena_fixed/` | Y-axis fix + **authoritative extrinsics** + `Dimensions_fixed.txt` |
| `Remounted_West_East/` | Post-remount **candidate** calibration bundle (used by the projector game) |
| `proxiball_3d-main/projector/` | **Projector goal game** (`run_goal_target_multicam.sh`, `goal_target_game_multicam.py`, `homography.json`) |
| `models/ball/` | Ball detection engines (`yolo26m-672.engine`) |
| `cameras.md` | Camera hardware + USB-bandwidth analysis (committee-grade) |
| `docs/video_analysis_IMG_1962_2026-05-28.md` | Frame + telemetry analysis of the recorded session (the §6 evidence) |
| `docs/camera_procurement_research_2026-05-28.md` | Global-shutter camera buying report |
| `docs/project_cam_full_work_and_projector_plan.md` | Long prior plan (arena, pipeline, projector roadmap; predates the 2026-05-28 projector work + the calibration finding) |
| `Project_Cam_Deep_Research_Report_Converted.pdf` / `proxiball_3d-main/projectors_research.md` | Product/commercial + projector deep-research (academy market, projector, safety, BoM) |
| `CLAUDE.md`, `.claude/rules/*.md` | Engineering guardrails (geometry, perf, safety, workflow) |

**Protected (do not propose silently changing):** `triangulate_multi`, `transform_world_point_y`,
`ema_update`, UDP axis semantics, `arena_fixed/` extrinsics, BLM safety gates.

---

## 10. TL;DR for the next LLM

A garage-scale, 4-camera 3D tracking rig drives a ball launcher and a projector goal game. The cameras
**detect the ball well**, but the system **can't place it in 3D** because (a) the current multi-camera
**calibration is off** (free fix, the immediate blocker) and (b) the cameras are **rolling-shutter and
unsynchronized** (hardware ceiling — fixes fast-ball tracking, requires a purchase). camSouth is also
**mis-placed** (mounted on the wall it scores). Help most by: root-causing the calibration, designing the
**best 4-camera placement** for the dual pose+goal task, and sanity-checking the **global-shutter +
hardware-sync camera upgrade**. Keep the honesty rules in §0.
