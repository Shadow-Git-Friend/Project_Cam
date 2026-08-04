# USB6 Camera Rebind and Fail-Fast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the calibrated six-camera role mapping after the USB hubs moved and make the training viewer fail before model loading unless all six cameras are available.

**Architecture:** Keep static calibrated roles in the two existing USB6 YAML files, because the four generic cameras expose the same serial number. Add two small pure count-validation helpers to the live viewer and reuse them at the preflight and stream-open boundaries. Preserve the general two-camera minimum; only the USB6 mirrored launcher opts into six.

**Tech Stack:** Python 3.10, pytest, OpenCV/V4L2, Bash, YAML

---

The work stays in the current dirty feature tree because it contains the
uncommitted reviewed runtime. Do not create commits; the user owns commits.

## File Map

- `garage_lab_combined/config/cameras_6usb_test.yaml`: active USB6 runtime device mapping.
- `configs/cameras/cameras_6cam_usb.yaml`: promoted USB6 profile; must match the active mapping.
- `Parallel_working/scripts/live_4cam_arena_view_parallel.py`: validates the requested camera minimum and enforces it at both startup boundaries.
- `Parallel_working/run_live_usb6_mirrored_skeleton.sh`: opts the training/view-only USB6 path into a six-camera minimum.
- `tests/test_live_parallel_usb6.py`: mapping, launcher, and pure threshold contracts.
- `CLAUDE.md`: records the confirmed cause, repair, and verification.

### Task 1: Rebind the Four Generic Cameras

**Files:**
- Modify: `tests/test_live_parallel_usb6.py`
- Modify: `garage_lab_combined/config/cameras_6usb_test.yaml`
- Modify: `configs/cameras/cameras_6cam_usb.yaml`

- [ ] **Step 1: Write the failing mapping contract**

Add `import yaml` and this test:

```python
def test_usb6_configs_match_recovered_calibrated_roles():
    expected = {
        "camUsb01_C920": "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_9718C21F-video-index0",
        "camUsb02_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:4.1:1.0-video-index0",
        "camUsb03_C920": "/dev/v4l/by-id/usb-046d_HD_Pro_Webcam_C920_7B879F0F-video-index0",
        "camUsb04_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:6.1.1:1.0-video-index0",
        "camUsb05_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:5.1.1:1.0-video-index0",
        "camUsb06_1080P": "/dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1.1:1.0-video-index0",
    }
    for path in (
        Path("garage_lab_combined/config/cameras_6usb_test.yaml"),
        Path("configs/cameras/cameras_6cam_usb.yaml"),
    ):
        cameras = yaml.safe_load(path.read_text())["cameras"]
        actual = {name: info["device"] for name, info in cameras.items()}
        assert actual == expected
```

- [ ] **Step 2: Run the contract and confirm RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_live_parallel_usb6.py::test_usb6_configs_match_recovered_calibrated_roles -v
```

Expected: FAIL because all four generic `by-path` values still describe the
old hub topology.

- [ ] **Step 3: Update both YAML mappings**

Set the six `device` values in both files to the exact `expected` mapping from
Step 1. Replace the stale per-port comments with a dated note:

```yaml
# Rebound 2026-07-29 after the USB hubs moved computer ports. Camera bodies
# stayed mounted; roles were recovered against the 2026-07-01 synchronized
# footage using static landmarks plus feature-matching inliers.
```

- [ ] **Step 4: Run the contract and confirm GREEN**

Run the Step 2 command.

Expected: `1 passed`.

### Task 2: Require Six Cameras on the USB6 Training Path

**Files:**
- Modify: `tests/test_live_parallel_usb6.py`
- Modify: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`
- Modify: `Parallel_working/run_live_usb6_mirrored_skeleton.sh`

- [ ] **Step 1: Write the failing count and launcher contracts**

Add `import pytest` and:

```python
def test_validate_min_active_cameras_rejects_values_outside_configured_range():
    live = load_live_module()

    assert live.validate_min_active_cameras(2, 6) == 2
    assert live.validate_min_active_cameras(6, 6) == 6
    with pytest.raises(ValueError, match="at least 2"):
        live.validate_min_active_cameras(1, 6)
    with pytest.raises(ValueError, match="configured camera count 6"):
        live.validate_min_active_cameras(7, 6)


def test_require_camera_count_reports_stage_config_and_counts():
    live = load_live_module()

    with pytest.raises(RuntimeError) as caught:
        live.require_camera_count(
            stage="passed preflight",
            available_count=2,
            configured_count=6,
            minimum=6,
            config_path="rig.yaml",
        )

    message = str(caught.value)
    assert "2/6" in message
    assert "require >=6" in message
    assert "passed preflight" in message
    assert "rig.yaml" in message


def test_usb6_skeleton_launcher_requires_all_six_cameras():
    launcher = Path(
        "Parallel_working/run_live_usb6_mirrored_skeleton.sh"
    ).read_text()

    assert "--min-active-cameras 6" in launcher
```

- [ ] **Step 2: Run the new contracts and confirm RED**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_live_parallel_usb6.py::test_validate_min_active_cameras_rejects_values_outside_configured_range \
  tests/test_live_parallel_usb6.py::test_require_camera_count_reports_stage_config_and_counts \
  tests/test_live_parallel_usb6.py::test_usb6_skeleton_launcher_requires_all_six_cameras -v
```

Expected: three failures because the helpers and launcher flag do not exist.

- [ ] **Step 3: Implement the pure validation helpers**

Add beside `v4l2_device_ready`:

```python
def validate_min_active_cameras(requested, configured_count):
    minimum = int(requested)
    configured = int(configured_count)
    if minimum < 2:
        raise ValueError("--min-active-cameras must be at least 2")
    if minimum > configured:
        raise ValueError(
            f"--min-active-cameras {minimum} exceeds configured camera count {configured}"
        )
    return minimum


def require_camera_count(
    *, stage, available_count, configured_count, minimum, config_path
):
    available = int(available_count)
    configured = int(configured_count)
    required = int(minimum)
    if available < required:
        raise RuntimeError(
            f"Only {available}/{configured} camera device(s) {stage}; "
            f"require >={required}. Config: {config_path}"
        )
```

- [ ] **Step 4: Add the CLI and enforce both boundaries**

Add:

```python
ap.add_argument(
    "--min-active-cameras",
    type=int,
    default=2,
    help="Minimum cameras that must pass preflight and open (default: 2).",
)
```

Immediately after the configured-camera check, save:

```python
configured_camera_count = len(active_cams)
min_active_cameras = validate_min_active_cameras(
    args.min_active_cameras, configured_camera_count
)
```

Replace the fixed preflight `len(ready_cams) < 2` block with:

```python
require_camera_count(
    stage="passed preflight",
    available_count=len(ready_cams),
    configured_count=configured_camera_count,
    minimum=min_active_cameras,
    config_path=args.config,
)
```

After failed captures are removed from `active_cams`, replace the fixed
two-camera open check with:

```python
require_camera_count(
    stage="opened",
    available_count=len(active_cams),
    configured_count=configured_camera_count,
    minimum=min_active_cameras,
    config_path=args.config,
)
```

- [ ] **Step 5: Opt the USB6 skeleton launcher into six**

Add `--min-active-cameras 6` next to its camera-open retry arguments:

```bash
  --min-active-cameras 6 \
  --camera-open-retries 20 --camera-open-retry-delay 5 \
```

- [ ] **Step 6: Run the new contracts and confirm GREEN**

Run the Step 2 command.

Expected: `3 passed`.

### Task 3: Verify Software and the Current Rig

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run the focused tests**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_live_parallel_usb6.py \
  tests/test_desktop_training_contracts.py \
  tests/test_usb6_gate_helpers.py -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run a simultaneous view-only six-camera probe**

Run a temporary Python probe that loads
`garage_lab_combined/config/cameras_6usb_test.yaml`, opens every configured
device with `cv2.CAP_V4L2`, requests `MJPG 640x360@10`, starts one reader thread
per camera, and requires at least one valid frame from every role within ten
seconds. The probe must release all captures in `finally` and must not import
or address launcher hardware.

Expected: `6/6 streams produced frames`.

- [ ] **Step 3: Run the complete suite and hygiene checks**

Run:

```bash
venv/bin/python -m pytest -o addopts=''
git diff --check
```

Expected: `673 passed`, the same two pre-existing warnings, and a clean diff
check.

- [ ] **Step 4: Record the result**

Append a dated `CLAUDE.md` entry containing:

- confirmed cause: four stale generic-camera `by-path` links after hub movement;
- recovered role mapping source: fixed mounts plus 2026-07-01 frame matching;
- fail-fast USB6 minimum of six at preflight and open boundaries;
- exact focused/full test results and simultaneous probe result;
- no launcher hardware access and no commit.

