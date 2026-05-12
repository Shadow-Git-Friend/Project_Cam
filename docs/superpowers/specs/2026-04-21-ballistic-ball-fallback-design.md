# Ballistic-Aware Single-Cam Ball Fallback — Design Spec

**Date:** 2026-04-21
**Status:** Approved, ready for implementation plan
**Scope:** `Parallel_working/scripts/live_4cam_arena_view_parallel.py` (isolated)

## Problem

Live ball 3D tracking fails in two modes during real testing with
`--ball-imgsz 960 --ball-single-cam-fallback`:

- **Bounce freeze (mode b):** Ball tracks correctly while airborne, then at the
  bounce instant it freezes / jumps below the floor, then never recovers.
- **Occlusion non-recovery (mode c):** After ~1s of occlusion, ball fades out
  and stays lost even when camNorth clearly re-acquires the detection.

Pose tracking (13 joints, no Z-plane trick) is smooth and accurate in the same
conditions. The bug is ball-specific.

## Root Cause

Two interacting defects in the current single-cam fallback (L1825-1857 of
`live_4cam_arena_view_parallel.py`):

1. **Stale KF-Z target during bounce.** The fallback projects the single-cam
   ray onto a Z-plane taken from `ball_kf.predict_ahead(1/fps)`. The KF is a
   constant-velocity model — it cannot reverse Z-velocity on a bounce. At the
   bounce instant, KF keeps predicting downward, so the ray intersects a Z
   below the real ball. The bad 3D point updates the KF, making velocity even
   more wrong. Divergence locks in.

2. **Max-frames counter semantics bug.** `ball_frames_since_detect` resets to
   `0` on every successful single-cam fallback. The `--ball-single-cam-max-frames`
   cap (docstring says "without a multi-cam re-lock") is supposed to force a
   multi-cam re-lock after 15 single-cam frames. It never fires as long as
   camNorth keeps seeing the ball. KF drifts on a floated Z indefinitely.

Net effect: the single-cam fallback actively poisons the KF instead of
supplementing it.

## Solution Overview

Two-state ballistic model replaces the stale KF-Z target when exactly one
camera sees the ball. Gravity-informed Z prediction. Counter semantics fixed
unconditionally. All flag-guarded; flag OFF = bit-identical to current
behavior.

## Architecture

All changes in a single file:
`Parallel_working/scripts/live_4cam_arena_view_parallel.py`.

**Not touched:** `triangulate_multi`, `transform_world_point_y`, `ema_update`,
UDP schema, safety gates, any file in `garage_lab_combined/`, any pose code.

## Components

### 1. `BallFlightState` (new dataclass)

Tracks:
- `mode: {AIRBORNE, FLOOR}`
- `last_multicam_pos_mm: np.ndarray[3]`
- `last_multicam_vel_mm_s: np.ndarray[3]`
- `t_last_multicam: float`
- `frames_since_multicam: int`

Lives alongside existing `ball_kf`. Initialized to `FLOOR` with zeros.

Velocity source is defined explicitly during implementation: on each accepted
multi-cam lock, velocity is estimated by finite difference from the previous
accepted multi-cam lock. `vz` is lightly smoothed and clipped to a sane range
before being promoted into `BallFlightState`, so one noisy multi-cam frame
cannot poison subsequent single-cam ballistic prediction.

### 2. `ballistic_predict_z(z0, vz, dt_s, g, floor) -> float` (new helper)

Pure kinematics, no iteration:

```
z_new = z0 + vz*dt - 0.5*g*dt^2
return max(z_new, floor)
```

Returns the predicted Z. Caller inspects whether it clamped to floor to flip
state to `FLOOR`.

### 3. Modified single-cam call site (L1825-1843)

When `n_cams == 1 AND args.ball_single_cam_fallback AND args.ball_ballistic_fallback`:

1. `dt = t_now - state.t_last_multicam`
2. If `state.mode == AIRBORNE`:
   `target_z = ballistic_predict_z(last_z, last_vz, dt, g, floor)`
   If `target_z <= floor + 1e-3`: flip `state.mode = FLOOR`
3. If `state.mode == FLOOR`:
   `target_z = args.ball_single_cam_floor_mm`
4. Call existing `project_ray_to_z_plane(obs_norm, R, tvec, target_z)` (unchanged).
5. KF update with measurement noise multiplied by `--ball-single-cam-meas-noise-mult`.
6. Increment `state.frames_since_multicam`.

When flag is OFF: call site unchanged from today.

### 4. State transitions

- **FLOOR → AIRBORNE:** multi-cam lock arrives with `vz > --ball-bounce-liftoff-vz-mm-s`
  for ≥2 consecutive frames (debounce).
- **AIRBORNE → FLOOR:** `ballistic_predict_z` clamped to floor, OR at a multi-cam
  lock `z < floor + 30mm` with `vz < 0`.

On every multi-cam lock (≥2 cams): update `last_multicam_pos_mm`,
`last_multicam_vel_mm_s`, `t_last_multicam`; reset `frames_since_multicam = 0`.
Only accepted multi-cam lock frames are allowed to count toward the
`FLOOR → AIRBORNE` debounce; any non-multicam frame breaks the streak. A
single-cam fallback frame can never self-promote the flight state to
`AIRBORNE`.

### 5. Counter semantics fix (unconditional, no flag)

New counter `ball_frames_since_multicam`, incremented on single-cam fallback
use, reset to `0` on any multi-cam lock. The `--ball-single-cam-max-frames`
cap now checks **this** counter (not `ball_frames_since_detect`).
`ball_frames_since_detect` keeps its coast semantics. This is a bug-fix that
applies regardless of ballistic mode.

### 6. New CLI flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--ball-ballistic-fallback` | OFF | Enable gravity-aware single-cam target_z |
| `--ball-gravity-mm-s2` | 9810 | Gravitational acceleration |
| `--ball-bounce-liftoff-vz-mm-s` | 500 | FLOOR→AIRBORNE threshold |
| `--ball-single-cam-meas-noise-mult` | 3.0 | KF meas-noise scaling on single-cam |

## Data Flow (ball path only; pose untouched)

```
4 frames → YOLO (imgsz) → per-cam argmax → ball_obs
  ├─ ≥2 cams:  SVD → update BallFlightState (pos, vz, t) → frames_since_multicam = 0
  ├─ 1 cam + flags ON:  ballistic target_z → ray projection → KF update (widened noise)
  │                      → ball_frames_since_multicam += 1
  └─ 0 cams:   coast via KF + velocity damping (unchanged)
→ ball_state → UDP (unchanged schema) → viz (unchanged)
```

## Error Handling

- `project_ray_to_z_plane → None`: fall through to coast path (existing).
- `target_z < floor`: clamp to floor, flip state to `FLOOR`.
- `target_z > 4000 mm` (ceiling sanity): fall through to coast — prevents
  ballistic runaway on bad state.
- `frames_since_multicam > --ball-single-cam-max-frames`: stop using fallback,
  coast only, force multi-cam re-lock.
- `ball_frames_since_detect > ball_coast_frames`: reset KF fresh (existing,
  preserved).
- Existing `--ball-log-jsonl` output is extended to log per-frame source
  (`multi`, `single_ballistic`, `single_legacy`, `coast`, `none`), flight
  state, state transitions, relock counters, effective measurement-noise
  multiplier, target Z, and fallback reject reason for diagnosis.

## Testing Plan

1. **Record `bounce_01` regression fixture** (keystone output):
   ```
   ./venv/bin/python Parallel_working/scripts/record_test_sequence.py \
     --out Parallel_working/output/test_sequences/bounce_01 \
     --duration 8 --fps 15
   ```
   Clean toss + 2 bounces. Per-cam frames + timestamps.

2. **Offline detection-rate sanity** — confirm `imgsz=960` still hits ~98% on
   camNorth for the new fixture:
   ```
   ./venv/bin/python Parallel_working/scripts/ball_detection_analyzer.py \
     --sequence Parallel_working/output/test_sequences/bounce_01 \
     --imgsz 672 960 --conf 0.15 0.25 0.40
   ```

3. **Flag-off regression** — run live without `--ball-ballistic-fallback`.
   Trajectory must be bit-identical to pre-change for a 10-second run.

4. **Flag-on live** — full stack:
   ```
   ./Parallel_working/run_live_blm.sh --ball-imgsz 960 --ball-single-cam-fallback \
     --ball-ballistic-fallback --ball-log-jsonl Parallel_working/output/ball_ballistic_$(date +%s).jsonl
   ```
   Expect: no floor penetration, occlusion recovery ≤1 frame after camNorth
   re-acquires.

## Acceptance Criteria

- **Flag OFF:** trajectory diff <1mm vs. pre-change, 10-second run.
- **Flag ON, `bounce_01` replay:** ball Z ≥ floor − 10mm every frame.
- **Flag ON, `bounce_01`:** ball visible in 3D view on ≥90% of frames from
  first detection onward.
- **Flag ON, `bounce_01`:** JSONL shows bounded single-cam fallback streaks,
  explicit re-locks, and any coast-only / rejected-fallback frames are
  attributable from per-frame debug fields.
- **Flag ON, live:** after ≥2s occlusion + camNorth re-acquires, ball locks
  to ray∩floor within 1 frame.

## Out of Scope

- Multi-hypothesis detection (Approach C) — Phase 2, needs fixtures first.
- Flipping `run_live_blm.sh` defaults — separate commit after live validation.
- Flipping `--ball-conf` default — separate commit.
- Pose / joint tracking — untouched.
- Any `garage_lab_combined/` changes.

## Files Modified

- `Parallel_working/scripts/live_4cam_arena_view_parallel.py` (only code changes)
- NEW: `Parallel_working/output/test_sequences/bounce_01/` (fixture recording)
- `.claude/rules/perf.md` (one-line "Ball Detection Levers" update)
