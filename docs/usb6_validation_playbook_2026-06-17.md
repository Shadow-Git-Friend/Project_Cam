# 6-USB Camera Validation Playbook

Date: 2026-06-17

This is the safe validation path for the temporary 6-USB-camera rig. It does
not replace production `garage_lab_combined/config/cameras.yaml` and it does
not make the rig safe for human-adjacent shooting.

## Current Hardware Truth

- Capture config: `garage_lab_combined/config/cameras_6usb_test.yaml`.
- Capture mode: `1280x720 MJPG @ 30 FPS`.
- Current observed devices: 2x Logitech C920 and 4x 1080P USB cameras.
- Previous check showed all six cameras on one USB2 controller
  (`Bus 001`, `usb-0000:00:14.0-*`), so USB redistribution is the first gate.

## Phase A - Capture-Only Gates

1. Move cameras across USB controllers before calibration:

   - Move both C920 cameras first.
   - If possible, move one 1080P USB camera too.
   - Prefer a different rear-bank / USB-C / GPU / Thunderbolt controller.

2. Run the strict USB and capture gate:

   ```bash
   ./venv/bin/python scripts/usb6_capture_gate.py \
     --config garage_lab_combined/config/cameras_6usb_test.yaml \
     --output-dir Parallel_working/output/usb6_gate_after_usb_split \
     --duration 30 --width 1280 --height 720 --fps 30 --fourcc MJPG \
     --mosaic-video
   ```

   Pass criteria:

   - `usb_controller_split_ok: true`.
   - `capture_ok: true`.
   - No camera disappears.
   - No camera has `max_gap_ms > 100`.

   If the cameras are still physically on one controller and you only want a
   capture benchmark, add `--allow-single-controller`. Do not use that flag as
   a real acceptance gate.

3. Run a 30-second framing/identity walkthrough:

   ```bash
   ./venv/bin/python Parallel_working/scripts/record_test_sequence.py \
     --config garage_lab_combined/config/cameras_6usb_test.yaml \
     --output Parallel_working/output/usb6_framing_walkthrough_$(date +%Y%m%d_%H%M%S) \
     --duration 30 --fps 30 --width 1280 --height 720 --fourcc MJPG \
     --output-format video --video-mode mosaic --countdown 0 --warmup 2
   ```

   During recording, walk north/center/south/east/west, wave close to each
   camera, do two squats, and hold two push-up positions.

4. Run the 10-minute stability test only after the strict gate passes:

   ```bash
   ./venv/bin/python Parallel_working/scripts/record_test_sequence.py \
     --config garage_lab_combined/config/cameras_6usb_test.yaml \
     --output Parallel_working/output/usb6_stability_10min_$(date +%Y%m%d_%H%M%S) \
     --duration 600 --fps 30 --width 1280 --height 720 --fourcc MJPG \
     --output-format video --video-mode mosaic --countdown 0 --warmup 2
   ```

## Phase B - Calibration Gates

1. Lock the physical role mapping after the walkthrough:

   | Role | Expected physical camera |
   |---|---|
   | `camNorth_EastHigh` | 1080P USB |
   | `camNorth_WestHigh` | 1080P USB |
   | `camEast_Low` | C920 |
   | `camWest_Low` | C920 |
   | `camSouth_High` | 1080P USB |
   | `camBounce_TargetLow` | 1080P USB |

2. Generate or scale intrinsics for the exact live resolution (`1280x720`).

   Validate before extrinsics:

   ```bash
   ./venv/bin/python scripts/validate_intrinsics_gate.py \
     --config garage_lab_combined/config/cameras_6usb_test.yaml \
     --intrinsics-dir garage_lab_combined/cal/intrinsics \
     --width 1280 --height 720 --max-reprojection-px 2.0 \
     --output Parallel_working/output/usb6_intrinsics_gate_$(date +%Y%m%d_%H%M%S).json
   ```

   Pass criteria:

   - every camera has an intrinsics JSON;
   - every JSON reports `image_width=1280`, `image_height=720`;
   - reprojection error is at or below the chosen threshold;
   - C920 intrinsics are fresh, not copied from the 1080P USB cameras.

3. Run six-camera extrinsics only after the intrinsics gate passes.

   Acceptance:

   - all six cameras have extrinsics;
   - overlay images align with wall/floor tags;
   - no axis flip or wrong wall-side position;
   - rollback backup `cal_backup/pre_6cam_remount_2026-06-05/` remains untouched.

4. Run static 3D validation.

   Use normalized undistorted observations with bare `[R|t]`. Do not validate
   with the projector-style `K @ [R|t]` path.

   Acceptance:

   - accepted points use at least two cameras;
   - mean reprojection is `<25 px`;
   - reconstructed XYZ is compared to measured millimeter ground truth.

## Phase C - 6-Camera Pipeline Work

The live pose/BLM stack still has old 4-camera assumptions in places, including
the default `camEast/camNorth/camSouth/camWest` ordering. Do not expect live
6-camera pose/BLM to be production-ready until this is generalized.

Implementation acceptance:

- live viewer opens arbitrary calibrated camera names from config;
- mosaic supports six cameras;
- triangulation uses all calibrated active cameras;
- UDP/log payloads preserve per-camera counts and stale-camera info;
- the old 4-camera production config still runs.

## Phase D - Functional Tests

Run only after Phases A-C pass:

- T-pose, 5 squats, 5 push-ups, and walking through center.
- BLM aim-only only: wheels off/RPM 0, no `--shoot-enabled`.
- Soft-target/projector only: empty arena or soft target, low-speed shots.

Do not use live human-adjacent shooting until static validation, aim-only, and
soft-target gates all pass.
