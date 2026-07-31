# USB6 Camera Rebind and Fail-Fast Design

**Date:** 2026-07-29

## Context

The six physical USB cameras are present and individually deliver MJPG frames,
but the live USB6 runtime config contains stale `by-path` links for all four
generic 1080P cameras. Only the two Logitech C920 cameras use stable `by-id`
links, so the existing preflight admits exactly two cameras and the viewer
continues because its global minimum is two.

The camera bodies and mounts did not move; only the USB hubs were connected to
different computer ports. The calibrated role mapping was recovered by
comparing fresh frames with the synchronized 2026-07-01 dataset. Static
landmarks and feature-matching inliers agree on the following mapping:

| Calibrated role | Current device |
|---|---|
| `camUsb01_C920` | `/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_9718C21F-video-index0` |
| `camUsb02_1080P` | `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:4.1:1.0-video-index0` |
| `camUsb03_C920` | `/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_7B879F0F-video-index0` |
| `camUsb04_1080P` | `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:6.1.1:1.0-video-index0` |
| `camUsb05_1080P` | `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:5.1.1:1.0-video-index0` |
| `camUsb06_1080P` | `/dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1.1:1.0-video-index0` |

## Scope

1. Update both the legacy runtime USB6 YAML and the promoted USB6 profile to
   the recovered mapping.
2. Add a `--min-active-cameras` viewer option with a default of `2`, preserving
   existing four-camera and graceful-degradation behavior.
3. Make the mirrored USB6 skeleton launcher require all six cameras by passing
   `--min-active-cameras 6`. The training wrapper inherits this requirement.
4. Apply the threshold twice:
   - after V4L2 preflight, before CUDA/TensorRT model loading;
   - after actual `VideoCapture.open`, because a responding node can still fail
     to start a stream.
5. Include the requested and observed counts plus the config path in failures.

## Data Flow

The viewer loads the configured camera roles, calculates the required minimum,
and preflights each device. Fewer than the required number stops startup before
model loading. Cameras that pass preflight are opened normally. The active set
is checked again before capture and inference begin.

The USB6 launcher opts into a minimum of six. Other callers retain the current
minimum of two unless they explicitly request a stricter threshold.

## Testing

The change follows a red-green cycle:

1. Add a config contract that all six calibrated roles resolve to the recovered
   device links.
2. Add a launcher contract requiring `--min-active-cameras 6`.
3. Add behavioral tests for threshold validation and for preflight/open count
   decisions using pure helpers, without requiring camera hardware.
4. Run the focused USB6 and desktop-training tests, then the complete suite.
5. Run a view-only simultaneous six-camera probe at `640x360@10` with MJPG and
   confirm that all six streams produce frames. Do not load or access launcher
   hardware.

## Error Handling

`--min-active-cameras` must be at least two and no greater than the number of
configured cameras. Invalid values fail immediately. Missing or unresponsive
devices are still logged individually. The final error reports whether the
failure occurred during preflight or stream opening.

## Non-Goals

- No automatic image-based remapping during ordinary runtime.
- No changes to intrinsics, extrinsics, camera mounts, pose geometry, firing
  control, or launcher behavior.
- No claim that changing hubs preserves sufficient aggregate USB bandwidth;
  the simultaneous probe verifies only the current low-resolution training
  profile.

