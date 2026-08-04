# Self-Contained Prompt: Best 6-Camera Allocation for Project_Cam Garage

Use this file when the other LLM **does not have access to the Project_Cam repository or code**. Everything important is included below.

---

## Copy-Paste Prompt

You are an expert in multi-camera computer vision, sports robotics, 3D pose estimation, and camera geometry. You do **not** have access to the source code or repository, so base your answer only on the project brief below. Your task is to recommend the best physical allocation of **six currently available USB webcams** in a garage arena for Project_Cam.

The system is used for:

1. **BLM aiming / shooting**: a ball-launching machine uses live 3D human joint positions to aim. Safety and stable 3D targeting are the highest priorities.
2. **Pose estimation**: standing body pose, squats, push-ups, ankles/feet/wrists near the floor, side-view posture, and occlusion survival.
3. **Projector target game**: ball hits projected targets on the South wall.
4. **Ball tracking**: low and fast ball motion, ball flight toward the South wall, and bounce/floor events.

Do not give generic advice. Give concrete camera positions, look-at points, roles, and validation steps.

---

## Arena Geometry

Coordinate system:

- Origin: **North-East floor corner**.
- Units: **millimeters**.
- `X`: North to South.
- `Y`: East to West.
- `Z`: upward.

Garage dimensions:

```text
X = 6230 mm
Y = 3050 mm
Z = 2950 mm
```

Walls:

```text
North wall: X = 0
South wall / projector target wall: X = 6230
East wall: Y = 0
West wall: Y = 3050
Floor: Z = 0
Ceiling: Z = 2950
```

Critical coordinate sanity rules:

- Do **not** swap X and Y.
- North/South are controlled by **X**, not Y.
- East/West are controlled by **Y**, not X.
- Valid coordinate ranges:
  - `0 <= X <= 6230`
  - `0 <= Y <= 3050`
  - `0 <= Z <= 2950`
- If a camera is wall-mounted, at least one horizontal coordinate must be close to a wall plane:
  - North wall camera: `X ≈ 0`
  - South wall camera: `X ≈ 6230`
  - East wall camera: `Y ≈ 0`
  - West wall camera: `Y ≈ 3050`
- A coordinate such as `Y=5980` is impossible in this garage because `Y` only goes to `3050`.
- A coordinate such as `X=3115, Y=50` is on/near the **East wall**, not on the North wall.
- A coordinate such as `X=6180, Y=1525` is on/near the **South wall**, not on the West wall.
- Every final recommendation must include a short coordinate sanity check confirming that all six mount points are inside the valid range and actually lie on the claimed wall.

Existing old 4-camera calibrated layout, included only as historical reference:

| Old role | Old mount XYZ mm |
|---|---:|
| CamNorth | `(50, 1100, 2260)` |
| CamEast | `(1620, 50, 2120)` |
| CamWest | `(1600, 2970, 2170)` |
| CamSouth | `(6180, 1530, 2270)` |

Do **not** assume the old 4-camera layout is optimal for the temporary 6-camera setup. A remount will require new calibration.

---

## Current Six Cameras

The current physical cameras are USB webcams:

```text
2 × Logitech C920
4 × 1080P USB Camera / Hikvision-style USB webcams
```

Temporary camera IDs:

| Camera ID | Type |
|---|---|
| camUsb01_C920 | Logitech C920 |
| camUsb02_1080P | 1080P USB Camera |
| camUsb03_C920 | Logitech C920 |
| camUsb04_1080P | 1080P USB Camera |
| camUsb05_1080P | 1080P USB Camera |
| camUsb06_1080P | 1080P USB Camera |

Cable-reach constraint:

- The **two Logitech C920 cameras only have short/default USB cables** and must be placed close enough to the PC to connect without additional long USB3/active extension cables.
- The **four 1080P USB / Hikvision-style cameras have the longer active USB cables** and should be used for the farther wall positions.
- Therefore, when assigning physical camera types to roles, prefer:
  - `C920` cameras for the closer low side positions;
  - `1080P USB` cameras for the two North-high positions, South-high position, and bounce/target position.
- This is a cable-driven compromise. The C920 cameras are acceptable on low side roles, but their framing must be checked carefully because they may have slightly narrower field of view than the 1080P USB cameras.

Measured capture limitations:

- All six are USB2-style webcams and are constrained by USB bandwidth and MJPG decoding.
- MJPG is required. Raw/uncompressed video is not feasible.
- Treat the current six-camera USB setup as a **temporary testing rig**, not a final production camera architecture.

Measured all-six capture results:

| Requested mode | Result |
|---|---|
| `640x360@30 MJPG` | all 6 open; about `16-21` fresh FPS per camera |
| `1280x720@30 MJPG` | all 6 open; about `17-23` fresh FPS per camera |
| `1920x1080@30 MJPG` | all 6 open; about `13-21` fresh FPS per camera; not recommended |

Recommended temporary operating mode:

```text
1280x720 MJPG for visual quality when latency is acceptable.
640x360 MJPG for lower-lag stress testing.
Assume around 20 fresh FPS per camera, not true 30 FPS.
```

---

## BLM / Launcher Context

BLM means ball-launching machine. It uses live 3D joints from camera triangulation to compute aiming angles and target commands.

Approximate BLM position:

```text
BLM position ≈ (600, 1560, 500) mm
```

The BLM is near the North side and aims into the arena toward the middle/South direction. Human targets for tests should generally be in the central or South-central working area, not pressed against the North wall.

Important: after any camera remount, old extrinsics and old BLM correction models are invalid. Do **not** recommend live shooting at a human immediately after remount.

Safe sequence:

```text
remount
-> camera device mapping
-> intrinsics check
-> extrinsics calibration
-> static reprojection validation
-> static joint/ball validation
-> pose gate without launcher firing
-> S2 aim-only
-> correction-model refit
-> S4 soft-target shooting
-> only then human-safe testing
```

---

## Human Pose Requirements

The layout must support:

- standing pose;
- squats;
- push-ups;
- ankles and feet near the floor;
- wrists/hands near the floor;
- knees/hips/shoulders;
- side-view posture quality;
- occlusion survival when the body blocks one camera.

For squats, side cameras are important for knee/hip/ankle geometry and body-depth ambiguity.

For push-ups, low side cameras are important because the body is close to the floor. A camera at about `Z=1000 mm` is too high if its main role is feet/ankle/floor push-up visibility. Prefer at least two low side views around `Z=300-600 mm`.

For BLM targeting, at least 3-camera visibility of key joints is preferred where possible.

---

## Projector / Target Wall Context

The projector targets are on the South wall:

```text
South wall plane: X = 6230 mm
```

The projector does **not** display targets over the whole wall. It displays a calibrated 3×3 target grid onto a measured rectangular region of the South wall. The system uses a projector-to-wall homography:

```text
Projector image size used for calibration:
proj_w = 1920 px
proj_h = 1200 px

Wall coordinate system for the South wall:
U = east-to-west across the South wall, approximately same direction as arena Y
V = floor-to-ceiling, same direction as arena Z
World point on target wall = (X=6230, Y=U, Z=V)
```

Projector calibration points:

| Label | Projector pixel `(px, py)` | South-wall `(U, V)` mm |
|---|---:|---:|
| TL | `(192, 120)` | `(600, 1940)` |
| TR | `(1728, 120)` | `(2630, 1940)` |
| BL | `(192, 1080)` | `(600, 700)` |
| BR | `(1728, 1080)` | `(2630, 700)` |
| CTR | `(960, 600)` | `(1615, 1310)` |

The calibrated projector rectangle therefore covers roughly:

```text
U = 600..2630 mm
V = 700..1940 mm
X = 6230 mm
```

Inside that calibrated rectangle, the game draws a 3×3 target grid with margins/padding. The actual active target cells occupy approximately:

```text
South wall hit region:
U = 791..2439 mm
V = 790..1701 mm
X = 6230 mm
```

Interpret this as a South-wall target area roughly around the middle horizontal span and mid-height region. Camera allocation should optimize visibility of the physical world region:

```text
X = 6230 mm
Y ≈ 791..2439 mm
Z ≈ 790..1701 mm
```

The projector display process is:

```text
software target grid in projector pixels
-> homography maps projector pixels to South-wall U/V millimeters
-> cameras detect ball/impact in image space
-> camera geometry projects detections to South-wall U/V
-> hit is counted when multiple cameras vote for the same 3×3 target zone
```

The camera layout should see:

- ball flight toward the South wall;
- ball contact/hit region;
- low bounce region near the South wall and floor.

However, projector target scoring is lower priority than BLM aiming and human pose.

---

## What The Layout Must Balance

Priority order:

1. BLM aiming safety / stable 3D joint triangulation.
2. Pose estimation for squats and push-ups.
3. Occlusion survival.
4. Ball tracking and South-wall/projector target hits.

Do not over-optimize only for the projector target wall. A layout with all cameras high and pointed at the South wall is bad because it will fail push-ups, ankles/feet, and side-view pose.

Do not put all cameras near the North wall. That weakens triangulation for the middle/South working area and ball/target events.

Do not put all cameras high. At least two low side cameras are needed.

---

## Audited Cable-Aware Final Layout

Use this as the recommended final layout unless a real mounting obstacle or cable-length problem is found during temporary mounting. The key correction from the earlier cable-aware draft is that the two C920 side-low cameras should look lower: use `(3400, 1500, 450)`, not `(3300, 1500, 650)`.

| Camera | Use this physical camera | Mount XYZ mm | Look-at XYZ mm | Wall/side | Height role | Main purpose | Tolerance |
|---|---|---:|---:|---|---|---|---|
| `camNorth_EastHigh` | 1080P USB, long cable | `(80, 550, 2200)` | `(3600, 1500, 1100)` | North wall | High | BLM corridor, whole body, pose redundancy | ±200 mm, ±8° |
| `camNorth_WestHigh` | 1080P USB, long cable | `(80, 2500, 2200)` | `(3600, 1500, 1100)` | North wall | High | second high angle, 3D redundancy | ±200 mm, ±8° |
| `camEast_Low` | Logitech C920, short cable | `(3100, 80, 450)` | `(3400, 1500, 450)` | East wall | Low | push-ups, ankles/feet, squat side view | ±150 mm, ±6° |
| `camWest_Low` | Logitech C920, short cable | `(3100, 2970, 450)` | `(3400, 1500, 450)` | West wall | Low | mirror low side, feet/wrists, occlusion | ±150 mm, ±6° |
| `camSouth_High` | 1080P USB, long cable | `(6150, 2300, 2300)` | `(2800, 1500, 1000)` | South wall | High rear | reverse view, body depth, ball approach | ±250 mm, ±10° |
| `camBounce_TargetLow` | 1080P USB, long cable | `(5000, 80, 350)` | `(6230, 1600, 850)` | East wall near South | Low target | bounce, low ball, projector target region | ±250 mm, ±10° |

Findings from the audited geometric check:

- Geometry is strong for pose: approximate model gives `>=2` camera coverage for nearly all working pose points and `>=3` coverage around `94%`.
- Push-up coverage improves with the lower side-camera aim: center push-up body-box framing improves from about `67%` to `83%` for each C920 in the geometric check.
- Projector target coverage is acceptable, but not maximal: target wall visibility mainly comes from the two North-high cameras plus the bounce/target camera. `camSouth_High` is mostly for reverse body/ball approach, not direct wall-hit observation.
- The layout is still limited by current hardware: USB rolling-shutter webcams, no hardware sync, and roughly `17-23` fresh FPS per camera at `1280x720`.

Test plan before permanent drilling:

- Put the PC or powered USB hub near the arena center, around `X≈3100`, `Y≈1525`, so both C920 short cables can reach the side-low mounts.
- Tape or temporary-mount the two C920s and record a push-up video; confirm the full head-to-feet body stays in frame.
- Run all-six capture at `1280x720 MJPG`; verify no camera stalls and fresh FPS stays near the previous measured range.
- After physical remount: measure real XYZ, recalibrate extrinsics, validate static joint/ball reprojection, then run S2 aim-only before any shooting.

Assumptions:

- PC or powered USB hub can sit near arena center.
- C920 cable length is enough for `camEast_Low` and `camWest_Low`; if not, replace the farther low-side C920 with a 1080P USB camera on a long cable.
- This setup is suitable for pose, aim-only, soft-target, and projector testing. It is not safe for live human-adjacent shooting until recalibration and validation pass.

Possible working volume for BLM/pose tests:

```text
X ≈ 1700..5600 mm
Y ≈ 600..2450 mm
Z joints ≈ 100..2200 mm
```

The layout should still avoid completely losing the North/mid area because the launcher is near the North side and some setup/testing may happen there.

---

## Required Output

Return a concise but technical engineering report with:

1. Your recommended final six-camera allocation.
2. A short explanation of why each camera is placed there.
3. A fallback layout if one side wall or one mounting point is blocked.
4. What placements to avoid.
5. Calibration and validation sequence.
6. Whether you recommend physically remounting the current USB cameras now.
7. A coordinate sanity check confirming that:
   - no axis was swapped;
   - every mount coordinate is inside the garage;
   - every claimed wall/side matches the coordinate.

Use this exact table format:

| Camera | Use this physical camera | Mount XYZ mm | Look-at XYZ mm | Wall/side | Height role | Main purpose | Tolerance |
|---|---|---:|---:|---|---|---|---|

Use millimeters only.

End with this section:

```text
Decision:
I recommend / do not recommend physically remounting the six current USB cameras now because ...
```

Be honest about risk. If the temporary USB camera layout is good enough for pose and aim-only testing but not enough for robust human-adjacent live shooting, say that clearly.
