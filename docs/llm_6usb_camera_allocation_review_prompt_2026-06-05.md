# LLM Handoff Prompt: 6-USB-Camera Allocation Review for Project_Cam

Use this prompt with another LLM when you want it to review the full Project_Cam repository and propose the best physical allocation of the **six USB cameras currently available** in the garage.

---

## Copy-Paste Prompt

You are reviewing a large robotics / computer-vision project named **Project_Cam**. The repository is massive, but you must inspect it carefully and ground your answer in actual files, scripts, configs, calibration data, and existing project constraints. Your task is to recommend the best physical allocation of the **six USB webcams currently available** in the garage, not the future industrial HikRobot/GigE cameras.

The goal is to optimize the temporary 6-camera garage setup for these priorities, in this order:

1. **BLM aiming / shooting safety and accuracy**: stable 3D joint positions for target joints such as right knee, nose, body center, shoulder/hip, and enough redundancy for safe aim-only and controlled shooting tests.
2. **Human pose estimation**: standing motion, squats, push-ups, legs/ankles/feet, side-view posture, and occlusion survival.
3. **Projector target hitting on the South wall**: ball flight to targets, target-zone hit detection, and bounce/low-ball visibility.
4. **General ball tracking**: enough multi-view coverage for low and fast ball motion.

Do **not** give generic advice. Read the repository and produce a concrete engineering recommendation with camera roles, coordinates, look-at points, mounting tolerances, trade-offs, and validation steps.

## Repository Root

Assume the repo root is:

```text
/home/hanush/Desktop/Project_Cam
```

If you have shell access, start with:

```bash
cd /home/hanush/Desktop/Project_Cam
rg -n "BLM|launcher|shoot|aim|squat|push.?up|projector|homography|goal|target|extrinsics|intrinsics|camera" -S .
```

Prefer `rg`, `sed`, and targeted file reads. Do not skim only one file; the project has multiple subsystems.

## Current Arena / Coordinate System

Read:

```text
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
```

Important facts:

- Garage dimensions:
  - `X = 623 cm` = `6230 mm`
  - `Y = 305 cm` = `3050 mm`
  - `Z = 295 cm` = `2950 mm`
- Origin:
  - North-East floor corner: `(0, 0, 0)`
- Axes:
  - `X`: North wall to South wall
  - `Y`: East wall to West wall
  - `Z`: upward
- Walls:
  - North wall: `X=0`
  - South wall / projector target wall: `X=6230 mm`
  - East wall: `Y=0`
  - West wall: `Y=3050 mm`

Existing calibrated 4-camera positions from `Dimensions_fixed.txt` are in **centimeters**:

| Old role | Position cm | Position mm |
|---|---:|---:|
| `CamNorth` | `(5, 110, 226)` | `(50, 1100, 2260)` |
| `CamEast` | `(162, 5, 212)` | `(1620, 50, 2120)` |
| `CamWest` | `(160, 297, 217)` | `(1600, 2970, 2170)` |
| `CamSouth` | `(618, 153, 227)` | `(6180, 1530, 2270)` |

Do not assume those are still optimal for the new temporary 6-camera test. They are the old 4-camera calibrated layout.

## Current Six USB Cameras

Read:

```text
garage_lab_combined/config/cameras_6usb_test.yaml
garage_lab_combined/config/cameras.yaml
```

Current temporary 6-camera capture config:

```yaml
cameras:
  camUsb01_C920:
    device: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:6.1:1.0-video-index0
  camUsb02_1080P:
    device: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1:1.0-video-index0
  camUsb03_C920:
    device: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:2.4:1.0-video-index0
  camUsb04_1080P:
    device: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:5.1.1:1.0-video-index0
  camUsb05_1080P:
    device: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:7.1.1:1.0-video-index0
  camUsb06_1080P:
    device: /dev/v4l/by-path/pci-0000:00:14.0-usb-0:13.1:1.0-video-index0
```

Hardware facts from recent testing:

- There are **six USB webcams**:
  - `2 × Logitech C920`
  - `4 × 1080P USB Camera` / Hikvision-style USB webcams
- All six are currently USB2 `480M` devices on the same USB controller/bus, so bandwidth is constrained.
- MJPG is required for all-six streaming; raw/uncompressed is not feasible.
- Measured all-six capture-only results:

| Requested mode | Real behavior |
|---|---|
| `640x360@30 MJPG` | all 6 open; about `16-21` fresh FPS per camera |
| `1280x720@30 MJPG` | all 6 open; about `17-23` fresh FPS per camera |
| `1920x1080@30 MJPG` | all 6 open; about `13-21` fresh FPS per camera, not recommended |

For temporary live BLM/pose tests, treat this as roughly **20 fresh FPS per camera**, not true 30 FPS.

## Important Files To Inspect

You must inspect at least these files before giving a recommendation:

```text
CLAUDE.md
CANONICAL.md
plan.md
cameras.md
docs/project_cam_full_work_and_projector_plan.md
docs/remount_playbook_2026-05-20.md
docs/live_coach_pushup_handoff_for_llm.md
docs/live_coach_pushup_improvement_prompt_for_llm.md
arena_fixed/cal/extrinsics/Dimensions_fixed.txt
arena_fixed/cal/extrinsics/extrinsics_fixed.json
arena_fixed/BLM_AIM_STAGE2.md
arena_fixed/scripts/run_blm_aim_test.sh
garage_lab_combined/config/cameras.yaml
garage_lab_combined/config/cameras_6usb_test.yaml
garage_lab_combined/cal/intrinsics/*.json
garage_lab_combined/BLM_TEST_CHECKLIST.md
garage_lab_combined/scripts/blm_follow.py
garage_lab_combined/scripts/launcher_runtime_from_udp.py
garage_lab_combined/scripts/live_aim_test.py
Parallel_working/scripts/live_4cam_arena_view_parallel.py
Parallel_working/scripts/record_test_sequence.py
Parallel_working/run_live_parallel_smooth_v2.sh
configs/exercises/football_academy_u10.yaml
tests/test_assessment_kairat_hardening.py
proxiball_3d-main/projector/homography.json
proxiball_3d-main/projector/static_grid_goal_logic.py
proxiball_3d-main/projector/goal_target_game_multicam.py
scripts/visualize_camera_coverage.py
scripts/optimize_camera_geometry.py
```

Also inspect generated outputs if present:

```text
scripts/coverage_out/
Parallel_working/output/usb6_video_test_640/
Parallel_working/output/usb6_video_test_720/
Parallel_working/output/usb6_capture_benchmark.json
```

## Known Caveats From Previous Review

There is an optimizer:

```text
scripts/optimize_camera_geometry.py
```

It is useful, but do not trust its output blindly. Previous review found that it weighted the South-wall projector target zone too strongly compared with BLM/pose. If you use or modify it, make sure the scoring reflects this priority:

1. BLM aiming safety / 3D joint robustness
2. Pose for squats and push-ups, including ankles/feet near floor
3. Ball/projector target wall

Specific caveats:

- Do not optimize only for projector target hits.
- For push-ups, at least two side/low cameras should see ankles, feet, wrists, and body near floor.
- Avoid placing one “low side” camera at about `Z=1050 mm` if its intended role is feet/push-up floor visibility; that is too high for the low-body role.
- Include the northern/middle working area if BLM aiming tests happen there.
- Any physical remount invalidates old extrinsics and old BLM correction model.

## BLM / Launcher Context

The BLM is the ball-launching machine. It uses live 3D joints from cameras and computes aiming angles / target commands. Important current launcher assumptions:

- Approximate BLM position from prior work:
  - `(X, Y, Z) ≈ (600, 1560, 500) mm`
- It aims into the arena, generally toward the middle and South direction.
- Old BLM safety and mechanical tests remain useful, but any camera remount invalidates camera-to-3D calibration and any old correction model.
- After remount:
  1. recalibrate intrinsics if cameras/lenses changed;
  2. recalibrate extrinsics for all active cameras;
  3. verify static reprojection / triangulation;
  4. run pose gate without launcher firing;
  5. run S2 aim-only;
  6. refit correction model;
  7. run S4 soft-target shooting before any human-adjacent test.

## Projector / South-Wall Target Context

Read:

```text
proxiball_3d-main/projector/homography.json
proxiball_3d-main/projector/static_grid_goal_logic.py
proxiball_3d-main/projector/goal_target_game_multicam.py
```

The projector goal target is on the **South wall** at `X=6230 mm`. Prior analysis found the real projected 3×3 target hit region is approximately:

```text
South wall hit region:
U = 791..2439 mm
V = 790..1701 mm
X = 6230 mm
```

Do not assume the entire South wall is an active target. Optimize for the real projected target region plus bounce/low-ball region in front of the South wall.

## What You Must Deliver

Return a structured engineering report. It must include:

1. **Repo Understanding**
   - Briefly summarize what you inspected.
   - Cite exact files that informed your reasoning.

2. **Current Constraints**
   - Current six camera types.
   - USB/MJPG/FPS limitations.
   - Why this is a temporary USB layout, not the future industrial-camera solution.

3. **Recommended 6-Camera Allocation**
   - A table with six cameras.
   - For each camera:
     - camera ID / device role;
     - physical mount position `(X,Y,Z)` in **mm**;
     - look-at point `(X,Y,Z)` in **mm**;
     - mount wall/side;
     - height;
     - role;
     - acceptable tolerance.

4. **Geometry Rationale**
   - Explain how the layout improves:
     - BLM aiming;
     - 3D joint triangulation;
     - squats;
     - push-ups;
     - occlusion survival;
     - ball trajectory;
     - South-wall target hits.

5. **What Not To Do**
   - Identify bad placements and why.
   - Mention if keeping all six near North wall, all high, or all target-wall-focused is bad.

6. **Calibration Plan**
   - Exact order after remount:
     - device mapping;
     - intrinsics check;
     - extrinsics;
     - reprojection validation;
     - static joint/ball validation;
     - BLM aim-only;
     - correction-model refit.

7. **Validation Commands**
   - Give commands using existing scripts where possible:
     - capture video with all six;
     - visualize coverage;
     - run optimizer if modified;
     - run tests relevant to pose/assessment/projector.

8. **Final Recommendation**
   - Give one recommended final layout.
   - Also give a fallback layout if there are physical obstructions in the garage.

## Output Format Required

Use this exact table format for the final layout:

| Camera | Use this physical camera | Mount XYZ mm | Look-at XYZ mm | Wall/side | Height role | Main purpose | Tolerance |
|---|---|---:|---:|---|---|---|---|

Use millimeters only. Do not mix cm/mm.

Also include this section:

```text
Decision:
I recommend / do not recommend physically remounting the six current USB cameras now because ...
```

Your recommendation must be honest about risk: if the temporary USB cameras are not good enough for robust BLM shooting, say so clearly and explain what tests are still allowed.

## Strong Initial Hypothesis To Verify Or Improve

Do not blindly accept this, but use it as a starting point:

- Keep two high/north or corner cameras for whole-body / South-facing coverage.
- Use two side-low cameras around the middle of the garage for ankles, feet, push-ups, squats, and side-view body posture.
- Use one South/high or rear-looking camera for reverse view and occlusion recovery.
- Use one low South/East-side camera for floor bounce and South-wall target-ball visibility.
- Prioritize BLM + pose over projector target score.

Possible starting zones, not final coordinates:

| Role | Suggested zone |
|---|---|
| high North/East oblique | `X≈50..300`, `Y≈400..900`, `Z≈1800..2300` |
| high North/West oblique | `X≈50..300`, `Y≈2150..2650`, `Z≈1800..2400` |
| low East side | `X≈2500..3800`, `Y≈50..150`, `Z≈300..600` |
| low West side | `X≈2500..3800`, `Y≈2900..3000`, `Z≈300..600` |
| high South/rear | `X≈6000..6200`, `Y≈1300..2500`, `Z≈2000..2600` |
| low bounce/target | `X≈4300..5600`, `Y≈50..300 or 2750..3000`, `Z≈200..500` |

The final answer should improve or correct these zones based on repository evidence and geometry.

## Safety Note

Do not recommend live shooting at a human immediately after remount. The correct path is:

```text
remount -> calibration -> static validation -> S2 aim-only -> correction-model refit -> S4 soft target -> only then human-safe testing
```

If your layout is only suitable for pose/projector testing but not shooting, say that explicitly.

