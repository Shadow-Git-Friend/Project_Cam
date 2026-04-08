# FPS Optimization — Recommended Implementation Order

**Pipeline:** `garage_lab_combined/scripts/live_4cam_arena_view.py`
**Baseline:** `arena_fixed/run_live_visual_invert_quality.sh`
**Locked reference:** `arena_fixed/output/world_frame_views_live_quality.png`
**Hardware:** NVIDIA RTX 2080 Ti, 4× Hikvision DS-E12 USB cameras, Linux

---

## Estimated Baseline Budget (before optimization)

| Stage | Estimated ms/frame | % of budget |
|---|---|---|
| Matplotlib 3D redraw | 80–200 | 40–55% |
| Camera capture (serial) | 60–130 | 25–35% |
| MMPose inference | 40–80 | 15–20% |
| YOLO inference | 15–30 | 5–8% |
| Mosaic + display | 5–10 | 2–3% |
| Triangulation + UDP | 1–3 | <1% |
| **Total** | **~200–450** | **~2–5 FPS** |

---

## Step 1 — Add StageTimer Profiling (~10 min, zero risk)

**Purpose:** Prove where time is actually spent before cutting anything.

Add a `StageTimer` class that records per-stage moving-average durations and prints a summary every 60 frames.

```python
# Add after existing imports
class StageTimer:
    """Per-stage moving-average timer with periodic log dumps."""
    def __init__(self, window=60):
        self._t0 = {}
        self._totals = {}
        self._counts = {}
        self._window = window
        self._history = {}

    def start(self, stage: str):
        self._t0[stage] = time.perf_counter()

    def stop(self, stage: str) -> float:
        dt = time.perf_counter() - self._t0.get(stage, time.perf_counter())
        self._totals[stage] = self._totals.get(stage, 0.0) + dt
        self._counts[stage] = self._counts.get(stage, 0) + 1
        if stage not in self._history:
            self._history[stage] = deque(maxlen=self._window)
        self._history[stage].append(dt * 1000.0)
        return dt * 1000.0

    def report(self, frame_idx: int):
        if frame_idx % 60 != 0 or frame_idx == 0:
            return
        parts = []
        total_ms = 0.0
        for stage in ['capture', 'ball', 'pose', 'triang', 'udp', 'viz3d', 'mosaic']:
            h = self._history.get(stage)
            if h and len(h) > 0:
                avg = sum(h) / len(h)
                total_ms += avg
                parts.append(f"{stage}={avg:.1f}")
        parts.append(f"TOTAL={total_ms:.1f}ms")
        print(f"[PERF f={frame_idx}] {' | '.join(parts)}")
```

Instrument the main loop by wrapping each stage with `timer.start('stage')` / `timer.stop('stage')` and calling `timer.report(frame_idx)` at the end of each iteration.

**Expected output:**
```
[PERF f=60]  capture=85.2 | ball=22.1 | pose=55.3 | triang=1.8 | udp=0.1 | viz3d=142.6 | mosaic=6.3 | TOTAL=313.4ms
```

**Geometry risk:** NONE — read-only instrumentation.

---

## Step 2 — Add ThreadedCapture (~15 min, zero geometry risk)

**Purpose:** Eliminate serial camera I/O blocking. Currently four `cap.read()` calls execute one after another, each potentially waiting up to 67ms for a frame at 15 FPS.

```python
import threading

class ThreadedCapture:
    """Grabs frames in a background thread so main loop never blocks on I/O."""
    def __init__(self, cap, name="cam"):
        self._cap = cap
        self._name = name
        self._frame = None
        self._lock = threading.Lock()
        self._running = True
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()

    def _reader(self):
        while self._running:
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._lock:
                    self._frame = frame

    def read(self):
        with self._lock:
            f = self._frame
            self._frame = None
        return (f is not None), f

    def release(self):
        self._running = False
        self._t.join(timeout=2.0)
        self._cap.release()
```

Replace the camera initialization block so each `cv2.VideoCapture` is wrapped in `ThreadedCapture`. The main loop's `caps[cam].read()` calls remain identical in signature.

**Why geometry-safe:** Frames are identical pixels. Only the waiting is moved off the main thread. Intrinsics, extrinsics, and triangulation math are untouched.

**Expected gain:** +30–50% FPS (capture stage drops from 60–130ms to ~5–15ms).

---

## Step 3 — Replace Matplotlib 3D with OpenCV Rasterisation (~45 min, biggest win)

**Purpose:** Eliminate the dominant bottleneck. The current `draw_live_scene()` calls `ax.cla()` every frame, redraws all 24 tag polygons, 12 arena edges, 4 camera markers, 3 axis quivers, 4 text labels — then calls `plt.pause(0.001)` which forces a synchronous GUI flush. This takes 80–200ms per frame.

**Approach:** Build a `FastArenaRenderer` class that:

1. At init, pre-renders the static arena (wireframe, tags, cameras, axes) into a single OpenCV image using a virtual pinhole camera positioned to match the matplotlib `view_elev`/`view_azim` angles.
2. Each frame, copies the cached background (`np.copy`, ~0.3ms) and draws only the dynamic elements (ball point, ball trail, skeleton joints and bones) using `cv2.line`, `cv2.circle`, `cv2.arrowedLine`.
3. Displays via `cv2.imshow` (already used for the 2D mosaic) instead of `plt.pause`.

**Key implementation details:**

- Virtual camera extrinsic: convert `view_elev`/`view_azim` to a look-at camera matrix pointed at the arena centre.
- Virtual camera intrinsic: focal length = `width * 0.9`, principal point at image centre.
- `_ymirror()` method replicates `transform_world_point_y()` exactly.
- `_project()` method: standard `K @ (R @ P + t)` pinhole projection with behind-camera filtering.
- Static background rendered once at startup (~50ms). Per-frame `render()` is ~1–3ms.

**Why geometry-safe:** Uses the exact same world coordinates. The 3D-to-2D mapping is a standard pinhole model. No coordinate transforms are changed — `_ymirror` mirrors `transform_world_point_y` identically. The `--no-world-y-mirror`, `--invert-y-axis-display`, and `--draw-global-axes` flags all map to equivalent renderer constructor parameters.

**Expected gain:** viz3d stage drops from 80–200ms to 1–3ms. This alone can double or triple total FPS.

---

## Step 4 — Create Three Shell Wrapper Presets (~5 min, zero risk)

Create `run_live_quality.sh`, `run_live_balanced.sh`, and `run_live_maxfps.sh` in `arena_fixed/`.

All three share the same geometry-critical flags:
```bash
--config garage_lab_combined/config/cameras.yaml
--intrinsics-dir garage_lab_combined/cal/intrinsics
--extrinsics arena_fixed/cal/extrinsics/extrinsics_fixed.json
--dimensions arena_fixed/cal/extrinsics/Dimensions_fixed.txt
--no-world-y-mirror
--invert-y-axis-display
--draw-global-axes --global-axis-len-mm 900
--ball-device cuda:0 --pose-device cuda:0
--width 1280 --height 720 --fps 15
```

**Quality mode** (~8–12 FPS): `--pose-every 1 --ball-every 1 --viz-every 1 --show-2d --show-3d --udp-target-cams-min 4`

**Balanced mode** (~15–20 FPS): `--pose-every 2 --ball-every 2 --viz-every 2 --mosaic-every 2 --show-2d --show-3d --ema-alpha 0.30 --udp-target-cams-min 3`

**Max-FPS mode** (~25–35 FPS): `--pose-every 3 --ball-every 3 --viz-every 3 --mosaic-every 3 --no-show-3d --show-2d --ema-alpha 0.25 --udp-target-cams-min 3`

---

## Step 5 — Run Validation Checklist (~15 min)

### Accuracy Validation (must pass before deploying any change)

| # | Test | Acceptance Criteria | How to Check |
|---|---|---|---|
| 1 | World frame axes direction | +X toward South wall, +Y toward West wall, +Z up — identical to `world_frame_views_live_quality.png` | Visual comparison of 3D view with locked reference image |
| 2 | Skeleton placement sanity | Person at arena centre → skeleton at correct XYZ, knees < hips < shoulders | Visual check in 3D view |
| 3 | UDP output regression | Same physical pose → UDP XYZ within ±5mm of baseline | Log UDP packets with `nc -ul 5005`, compare |
| 4 | Ball triangulation regression | Static ball at known position → 3D estimate within ±10mm of baseline | Place ball, compare output |
| 5 | Y-mirror correctness | `--no-world-y-mirror` produces unmirrored coordinates | Check UDP Y values vs tape measurement |
| 6 | Extrinsics file unchanged | `arena_fixed/cal/extrinsics/extrinsics_fixed.json` not modified | `md5sum` before and after |

### FPS Validation

| # | Metric | Quality | Balanced | Max-FPS |
|---|---|---|---|---|
| 1 | Mean FPS (60s window) | ≥ 8 | ≥ 15 | ≥ 25 |
| 2 | P5 FPS (worst 5%) | ≥ 5 | ≥ 10 | ≥ 18 |
| 3 | Frame-to-UDP latency | < 120ms | < 80ms | < 50ms |
| 4 | Capture frame drops | < 5% | < 10% | < 15% |

### Quick Regression Script

```bash
#!/usr/bin/env bash
# Run baseline for 30s headless, capture UDP, then run optimized, diff
echo "=== Baseline ==="
timeout 30 ./arena_fixed/run_live_visual_invert_quality.sh \
  --max-runtime-sec 30 --no-show-2d --no-show-3d 2>&1 | tee /tmp/baseline.log &
nc -ul -p 5005 -w 35 > /tmp/udp_baseline.jsonl &
wait

echo "=== Optimized ==="
timeout 30 ./arena_fixed/run_live_visual_optimized.sh \
  --max-runtime-sec 30 --no-show-2d --no-show-3d 2>&1 | tee /tmp/optimized.log &
nc -ul -p 5005 -w 35 > /tmp/udp_optimized.jsonl &
wait

grep "\[PERF\]" /tmp/baseline.log
grep "\[PERF\]" /tmp/optimized.log

echo "=== UDP diff ==="
diff \
  <(jq -r '.joints | to_entries[] | "\(.key) \(.value.x_mm|round) \(.value.y_mm|round) \(.value.z_mm|round)"' /tmp/udp_baseline.jsonl | tail -20) \
  <(jq -r '.joints | to_entries[] | "\(.key) \(.value.x_mm|round) \(.value.y_mm|round) \(.value.z_mm|round)"' /tmp/udp_optimized.jsonl | tail -20)
```

---

## Step 6 — Batch undistort_points (~10 min, minor win)

Replace per-point `undistort_points()` calls with a vectorized version that processes all points for a camera in one `cv2.undistortPoints` call.

```python
def undistort_points_batch(pts_list, k, d):
    if not pts_list:
        return []
    arr = np.array(pts_list, dtype=np.float64).reshape(-1, 1, 2)
    und = cv2.undistortPoints(arr, k, d)
    return [und[i, 0] for i in range(len(pts_list))]
```

**Geometry risk:** NONE — same math, fewer Python-to-C++ round trips.

**Expected gain:** ~2–5ms saved per frame.

---

## Step 7 — Downscaled Inference, Full-Res Triangulation (~20 min, medium risk)

Run YOLO and MMPose on 640×360 frames instead of 1280×720. Scale detection coordinates back to full resolution before undistortion and triangulation.

```python
INFER_SCALE = 0.5
frame_batch_infer = [cv2.resize(f, None, fx=INFER_SCALE, fy=INFER_SCALE,
                                 interpolation=cv2.INTER_LINEAR) for f in frame_batch]

# After detection, scale coordinates back:
cx, cy = cx / INFER_SCALE, cy / INFER_SCALE
kpts = kpts / INFER_SCALE
```

**Why geometry-safe:** Undistortion and triangulation still operate on coordinates in the original 1280×720 intrinsic calibration space. Only the detection networks see fewer pixels.

**Risk:** MEDIUM — detection recall may drop for small/distant targets. Validate by comparing joint localisation error before and after.

**Expected gain:** YOLO and RTMPose run ~2–3× faster at half resolution.

---

## Step 8 — Parallel CUDA Streams for YOLO + MMPose (~30 min)

Run ball detection and pose estimation concurrently on separate CUDA streams using `concurrent.futures.ThreadPoolExecutor`.

```python
import concurrent.futures
import torch

ball_stream = torch.cuda.Stream()
pose_stream = torch.cuda.Stream()

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    ball_future = pool.submit(run_ball_on_stream, frame_batch) if run_ball else None
    pose_future = pool.submit(run_pose_on_stream, frame_batch) if run_pose else None
    ball_results = ball_future.result() if ball_future else None
    pose_results = pose_future.result() if pose_future else None
```

**Caveat:** Both models share cuda:0. Without separate CUDA streams, PyTorch serializes operations on the default stream. Each model function must wrap inference in `with torch.cuda.stream(stream):`.

**Expected gain:** ~20–40% on inference if the RTX 2080 Ti has sufficient SM occupancy for both models simultaneously.

---

## Step 9 — Replace MMPoseInferencer with Direct RTMPose ONNX (~2–3 hours)

`MMPoseInferencer` is a high-level wrapper that runs RTMDet (person detector) → crop → RTMPose (keypoint estimator) → post-process. For a single-person scenario, skip the detector entirely and run RTMPose directly on the full frame or on a YOLO-provided person bounding box.

Export RTMPose to ONNX, load with `onnxruntime.InferenceSession` using `CUDAExecutionProvider`. This eliminates:
- RTMDet overhead (~15–25ms per frame)
- MMPose Python wrapper overhead
- Redundant person detection (YOLO already provides bounding boxes)

**Expected gain:** 2–3× pose inference speedup.

**Risk:** LOW for geometry (same keypoint output format). HIGH for implementation effort.

---

## Safe Tuning Matrix — Quick Reference

| Parameter | Safe Range | Geometry Risk |
|---|---|---|
| `--pose-every` | 1–3 | **NONE** — update rate only |
| `--ball-every` | 1–3 | **NONE** — update rate only |
| `--viz-every` | 1–5 | **NONE** — display only |
| `--mosaic-every` | 1–3 | **NONE** — display only |
| `--show-3d` | on/off | **NONE** — disabling removes matplotlib |
| `--show-2d` | on/off | **NONE** — display only |
| `--ema-alpha` | 0.2–0.5 | **LOW** — smoothing only |
| `--trail-len` | 5–50 | **NONE** — display only |
| `--pose-conf` | 0.3–0.6 | **MEDIUM** — affects joint filtering |
| `--ball-conf` | 0.25–0.6 | **LOW** — affects ball detection rate |
| `--udp-target-cams-min` | 2–4 | **MEDIUM** — lower = noisier |
| `--width/--height` | **DO NOT CHANGE** | **CRITICAL** — must match intrinsics |
| `--no-world-y-mirror` | **DO NOT CHANGE** | **CRITICAL** — world frame |
| `--extrinsics` | **DO NOT CHANGE** | **CRITICAL** — world frame |
| `--dimensions` | **DO NOT CHANGE** | **CRITICAL** — arena geometry |

---

*Generated: 2026-03-26*
*Target script: `garage_lab_combined/scripts/live_4cam_arena_view.py` (926 lines)*
*All optimizations preserve geometric correctness with the arena_fixed world frame.*
