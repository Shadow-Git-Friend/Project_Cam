# Canonical Stack Manifest

**Created:** 2026-04-20 (Tier 0 / T0.5).
**Purpose:** Resolve the canonical-stack ambiguity flagged in the architecture
review. Per-script status, single source of truth for active artifacts, and
documented migration debt — all without deleting any folders.

This file is the answer to "is X the canonical version?". When in doubt, this
manifest wins over folder names. Update when status changes; otherwise treat as
the read-only contract for what the project actually runs.

## Active runtime stack (canonical)

| Layer | Path | Notes |
|-------|------|-------|
| Live viewer (4-cam, threaded, dual backend) | [Parallel_working/scripts/live_4cam_arena_view_parallel.py](Parallel_working/scripts/live_4cam_arena_view_parallel.py) | Active hot path. Invoked by `Parallel_working/run_*.sh` (live + record). |
| Launcher runtime (UDP-driven, safety-gated) | [garage_lab_combined/scripts/launcher_runtime_from_udp.py](garage_lab_combined/scripts/launcher_runtime_from_udp.py) | Production. Only file authorized to send `shoot`. |
| BLM follow mode | [garage_lab_combined/scripts/blm_follow.py](garage_lab_combined/scripts/blm_follow.py) | Active. Voice-aware (`--voice-port`), auto-reload (`--auto-reload`). |
| Aim-only test | [garage_lab_combined/scripts/live_aim_test.py](garage_lab_combined/scripts/live_aim_test.py) | Active. S2 stage. |
| Voice bridge (separate venv) | [garage_lab_combined/scripts/voice_bridge.py](garage_lab_combined/scripts/voice_bridge.py) | Active. Runs under colleague's Vosk venv, NOT this project's venv. UDP IPC on 5006. |
| Firmware | `garage_lab_combined/scripts/control_12_full.ino` | Active. Baud 921600. |

## Active calibration artifacts (canonical)

The **single manifest** binding all five artifacts lives at [arena_fixed/config/calibration_manifest.yaml](arena_fixed/config/calibration_manifest.yaml). Tier 1.2 (`ArenaConfig`) will load through the manifest; pre-Tier 1, the individual paths below are still read directly by the 16+ scripts that parse the `.txt` / JSONs.

| Asset | Path | Status |
|-------|------|--------|
| Calibration manifest | [arena_fixed/config/calibration_manifest.yaml](arena_fixed/config/calibration_manifest.yaml) | **NEW (second-pass review addendum).** Binds intrinsics + extrinsics + dimensions + correction model + eval report into one bundle. |
| Extrinsics | [arena_fixed/cal/extrinsics/extrinsics_fixed.json](arena_fixed/cal/extrinsics/extrinsics_fixed.json) | **Single source of truth.** |
| Arena dimensions (txt, source) | [arena_fixed/cal/extrinsics/Dimensions_fixed.txt](arena_fixed/cal/extrinsics/Dimensions_fixed.txt) | Read by 16 scripts via regex. Source of truth. |
| Arena dimensions (YAML mirror) | [arena_fixed/config/arena_dimensions.yaml](arena_fixed/config/arena_dimensions.yaml) | Additive mirror (T0.4). Promote in Tier 1.2 (`ArenaConfig`). |
| Per-camera intrinsics | `garage_lab_combined/cal/intrinsics/cam{North,East,South,West}_intrinsics.json` | Active. JSON format. |
| GT correction models | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_{ball,joint}/correction_model.json` | Loaded by launcher scripts via `--correction-model`. |
| GT eval report | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/` | Reference accuracy bundle for current geometry. |

## Stack-zone definitions

- **`garage_lab_combined/`** — Production runtime. Touch only with explicit approval. 31 scripts.
- **`Parallel_working/`** — Perf experiments. Isolated. Hot-path live viewer lives here (`live_4cam_arena_view_parallel.py`) — paradoxically, it is canonical despite the folder label. 6 scripts.
- **`arena_fixed/`** — Owns the Y-axis fix and current extrinsics. Do not override.
- **`archive/`** — Frozen historical state. Read-only.
- **`/home/hanush/Desktop/Aldiyar/`** — Colleague's joint-angle project. Out of scope.
- **`voice_commands/`** — **experimental/local-only**. `voice_command_engine.py` is an earlier in-repo prototype; the operational voice path is the external `voice_bridge.py` UDP producer (runs under colleague's Vosk venv) → `blm_follow.py --voice-port`. Do not wire `voice_commands/` into the critical path unless it replaces the bridge.

## Per-script status (active scripts only — backups omitted)

### `garage_lab_combined/scripts/`

| Script | Status | Notes |
|--------|--------|-------|
| `launcher_runtime_from_udp.py` | **canonical** | T0.1 dead-code cleanup applied 2026-04-20. |
| `blm_follow.py` | **canonical** | Active follow mode + voice + auto-reload. |
| `live_aim_test.py` | **canonical** | S2/S3/S4 stage script. |
| `blm_interactive.py` | **canonical** | Raw serial terminal (boot-noise-filtered). |
| `voice_bridge.py` | **canonical** | Voice UDP producer (colleague's venv). |
| `voice_command_test.py` | **canonical** | Standalone voice tester. |
| `manual_aim_test.py` | active | Non-interactive aim sweep. |
| `live_4cam_arena_view.py` | **legacy** | Older single-process viewer. Superseded by `Parallel_working/scripts/live_4cam_arena_view_parallel.py`. T0.2 import swap applied. |
| `process_4cam_to_3d.py` | active | Offline 3D pipeline (MMPose-only — backend drift, see Tier 2.4). T0.2 import swap applied. |
| `common.py` | **NEW (T0.2)** | Shared helpers: `undistort_points`, `transform_world_point_y`, `ema_update`. |
| `calibrate_intrinsics_charuco_garage.py` | active | Writes `.npz` (drift, see Tier 2.2). |
| `calibrate_extrinsics_apriltag_robust.py` | active | Defaults now point to `arena_fixed` for initialization. |
| `render_apriltag_arena_360.py` | active | Defaults now point to `arena_fixed`. |
| `render_arena_ball_skeleton.py` | active | Defaults now point to `arena_fixed`. |
| `evaluate_*` (multiple) | active | GT eval scripts. |
| `calibrate_ball_rpm.py` | new (untracked) | RPM→m/s calibration helper (Phase 0 close-out). |

### `Parallel_working/scripts/`

| Script | Status | Notes |
|--------|--------|-------|
| `live_4cam_arena_view_parallel.py` | **canonical** | Active hot-path live viewer. T0.2 import swap deferred to Tier 1 (needs regression fixture). Defaults now point to `arena_fixed`. |
| `record_test_sequence.py` | active | Threaded 4-cam recording. |
| `ablation_ema_adaptive.py` | active | EMA ablation harness. T0.2 import swap deferred to Tier 1. |
| `validate_kalman_prediction.py` | active | Kalman validator. |
| `export_models_tensorrt.py` | active | TRT engine exporter (dynamic batch=4 patched). |
| `ball_model_sanity_check.py` | active | Ball model evaluation. |

## Migration debt (Tier 2)

### 1 code path still references legacy `extrinsics_main.json` (T2.3 migration to `extrinsics_fixed.json`)

Source of truth went to [arena_fixed/cal/extrinsics/extrinsics_fixed.json](arena_fixed/cal/extrinsics/extrinsics_fixed.json). The remaining live code reference is:

1. [garage_lab_combined/cal/extrinsics/visualize_arena.py](garage_lab_combined/cal/extrinsics/visualize_arena.py)

### 0 hardcoded `/home/hanush` paths in active `.py` / `.sh` files (T2.5)

Active scripts now use script-relative repo roots or `$PROJECT_CAM_VOSK_MODEL`. Remaining absolute-path mentions, if any, are in documentation text only.

### Helper-duplication remaining (T1+T2)

Tier 0 (done) consolidated 3 byte-identical helpers into `common.py` for `garage_lab_combined/scripts/`. Pending:

- `triangulate_multi` — 5 DIVERGED copies. Tier 1 (needs regression fixture).
- `world_to_launcher_xy_delta` — deduped for `blm_follow.py` + `live_aim_test.py` + `launcher_runtime_from_udp.py`; remaining copy in `manual_aim_test.py`.
- `solve_angles_ballistic` — deduped for `blm_follow.py` + `live_aim_test.py` + `launcher_runtime_from_udp.py`; remaining copy in `manual_aim_test.py`.
- `load_correction_model` / `apply_correction` — deduped for `blm_follow.py` + `live_aim_test.py` + `launcher_runtime_from_udp.py`; `manual_aim_test.py` still uses its raw-JSON variant.
- `SerialReader` + RPM telemetry filter — Tier 1 (mechanical extraction).
- 3 helpers in `Parallel_working/scripts/*` (`undistort_points`, `transform_world_point_y`, `ema_update`) — Tier 1 swap to import from `garage_lab_combined/scripts/common.py` via `sys.path` injection. Deferred to keep the active hot path frozen pre-defense.

### Calibration directory clutter (T2.1)

[garage_lab_combined/cal/extrinsics/](garage_lab_combined/cal/extrinsics/) has 31 extrinsics JSONs interleaved with ~951 non-JSON files (YAML mirrors, PNGs, MP4s, reports, `get-pip.py`). Tier 2.1 will move clutter into `archive_20260501/` via `git mv` and add a `MANIFEST.md`. No deletions.

## Tier 0 changes summary (2026-04-20)

| Step | Change | Verified |
|------|--------|----------|
| T0.1 | Deleted dead `load_correction_model` / `apply_correction` v1 (lines 96-127) in `launcher_runtime_from_udp.py`. v2 at lines 232/257 was already what the runtime used. | AST parses; remaining defs at lines 198/223; 4 call sites all postdate the def. |
| T0.2 | Created `garage_lab_combined/scripts/common.py` with 3 byte-identical helpers. Swapped imports in `live_4cam_arena_view.py` (3 helpers) and `process_4cam_to_3d.py` (1 helper). | AST + smoke import test pass. Numerical outputs verified for each helper. |
| T0.3 | Rewrote `requirements.txt` with curated deps + comments. Added `requirements.lock.txt` (121 lines from `pip freeze`). | Numpy version mismatch (txt 2.2.6 vs venv 1.26.4) corrected. |
| T0.4 | Created [arena_fixed/config/arena_dimensions.yaml](arena_fixed/config/arena_dimensions.yaml) mirroring `Dimensions_fixed.txt`. Additive — regex parsers in 16 scripts unchanged. | YAML round-trip verified (24 tags, asymmetries preserved). |
| T0.5 | This file. | — |
| T0.6 (second-pass addendum, 2026-04-20) | Created [calibration_manifest.yaml](arena_fixed/config/calibration_manifest.yaml) binding 5 calibration artifacts into one machine-readable bundle; flagged `voice_commands/voice_command_engine.py` as experimental. | YAML parses; manifest fields resolve. |

## Tier 1+ items added by second-pass review

Deferred from the 2026-04-20 second-pass review (not Tier-0-safe because they require regression fixtures and touch geometry/safety-critical code):

- **Shared control modules** — extract `LauncherClient` (set/reload/shoot/stop/center/telemetry) and the launcher math helpers (`world_to_launcher_xy_delta`, `solve_angles_ballistic`, correction-model apply) used by `blm_follow.py` + `live_aim_test.py` + `launcher_runtime_from_udp.py`. Matches Tier 2.6 in the existing plan.
- **Typed packet schemas** — `JointPacket`, `CorrectionModel`, `CalibrationBundle`, `VoiceCommandTransport`. Land with `ArenaConfig` in Tier 1.2.
- **Regression fixtures** — (1) arena_fixed geometry sanity bounds, (2) control-math parity on `reeval_arena_fixed_20260406` GT, (3) UDP schema contract (live viewer → launcher runtime), (4) voice-path contract (phrase → UDP payload → `blm_follow` command), (5) offline/live parity check for ball + joint triangulation (exposes `process_4cam_to_3d.py` backend drift).
- **Voice command vocabulary** — canonicalize the 16-phrase COCO-joint mapping into one schema shared by `voice_bridge.py` and `blm_follow.py` (currently duplicated inline).
