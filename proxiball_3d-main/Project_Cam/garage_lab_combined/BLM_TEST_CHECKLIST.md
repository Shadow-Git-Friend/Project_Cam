# BLM Incremental Test Checklist

This file is the single source of truth for Ball Launching Machine (BLM) integration progress.
Use it as a living checklist so we do not lose the plan over time.

## How To Use
- Mark completed items by changing `[ ]` to `[x]`.
- For each completed test, add evidence path (log/video) in the `Evidence` column.
- Do not move to the next stage until all pass criteria in the current stage are met.

## Scope (Current v1)
- Targets: `right_knee`, `right_hip`, `left_shoulder`
- Low-level ESP commands: `set v h wl wr`, `shoot`, `reload`, `center`, `stop`, `setzero`
- Runtime architecture: cameras -> 3D joints -> UDP -> launcher runtime -> serial -> ESP32

## Current Assets (Already Implemented)
- [x] UDP target streaming from live perception (`garage_lab_combined/scripts/live_4cam_arena_view.py`)
- [x] Launcher runtime controller (`garage_lab_combined/scripts/launcher_runtime_from_udp.py`)
- [x] Safety controls (`start`, `estop`, `clear`, `status`, `quit`)
- [x] Decision logging (`--dry-run-log-jsonl`)

## Stage Checklist

| ID | Stage | Test | Pass Criteria | Status | Evidence |
|---|---|---|---|---|---|
| S0.1 | Preflight | Confirm camera/extrinsics/intrinsics load | Live viewer starts, 4 cams visible, no crash for 2 min | [ ] | |
| S0.2 | Preflight | Confirm serial link to ESP32 | Runtime opens serial and accepts commands | [ ] | |
| S0.3 | Preflight | Confirm launcher pose values | `launcher_x/y/z/yaw` validated with static target sanity check | [ ] | |
| S1.1 | ESP only | Manual low-level command test | `set`, `center`, `stop`, `shoot`, `reload` all execute correctly | [ ] | |
| S1.2 | ESP only | Angle clamp test | Commands beyond +/-30 deg are safely clamped by firmware | [ ] | |
| S1.3 | ESP only | RPM telemetry test | `L:... R:...` received while wheels run | [ ] | |
| S2.1 | Runtime no cameras | Feed synthetic UDP targets | Runtime computes command and sends `set` without errors | [ ] | |
| S2.2 | Runtime no cameras | Zone rejection test | Out-of-zone targets logged as `OUT_OF_RANGE` and not fired | [ ] | |
| S2.3 | Runtime no cameras | Stability gating test | Noisy targets logged as `LOW_CONFIDENCE` | [ ] | |
| S3.1 | Live aim-only | Target acquire for each joint | Each joint gets stable lock within timeout | [ ] | |
| S3.2 | Live aim-only | Sequence behavior | `right_knee -> right_hip -> left_shoulder -> repeat` works | [ ] | |
| S3.3 | Live aim-only | Return-to-zero behavior | After each aim, launcher returns to `center` | [ ] | |
| S4.1 | Safety | E-STOP response time | `estop` causes immediate `stop` and no further actuation | [ ] | |
| S4.2 | Safety | E-STOP latch behavior | System stays blocked until `clear` is issued | [ ] | |
| S4.3 | Safety | Link loss behavior | On UDP/serial interruption, runtime goes to safe stop | [ ] | |
| S5.1 | Controlled fire | Single shot on one joint | 1 commanded shot after aim and RPM gate | [ ] | |
| S5.2 | Controlled fire | No unintended extra shots | Exactly one `shoot` per trigger event | [ ] | |
| S5.3 | Controlled fire | Post-shot safe state | Returns to `center` and waits for next valid target | [ ] | |
| S6.1 | Full cycle | 10-cycle reliability test | 10 full target cycles without crash or unsafe behavior | [ ] | |
| S6.2 | Full cycle | Decision log completeness | Every cycle has JSONL records with required fields | [ ] | |
| S6.3 | Full cycle | Report-ready outputs | Logs + summary plots generated for professor review | [ ] | |

## Required Log Fields (Decision JSONL)
- `timestamp`
- `input_joint_name`
- `raw_world_xyz_mm`
- `transformed_launcher_xyz`
- `calculated_pitch_yaw_v`
- `decision` (`OK`, `OUT_OF_RANGE`, `LOW_CONFIDENCE`, `ESTOP`)
- `execution_time_ms`

## Runbook Commands

### 1) Start live cameras with UDP target stream
```bash
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,right_hip,left_shoulder
```

### 2) Start launcher runtime in safe aim-only mode
```bash
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 \
  --launcher-x-mm 600 --launcher-y-mm 1560 --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets right_knee,right_hip,left_shoulder \
  --zone-csv garage_lab_combined/gt_eval/joint_tuning_20260310_124311/trials_joint_81_mm.csv \
  --no-shoot-enabled \
  --dry-run-log-jsonl garage_lab_combined/output/blm_logs/aim_decisions.jsonl
```

### 3) Operator commands (runtime terminal)
- `start`
- `estop`
- `clear`
- `status`
- `quit`

## Session Notes Template
Fill this after each test day.

```text
Date:
Operator:
Build/Commit:
Stage IDs tested:
What passed:
What failed:
Safety incidents:
Parameter changes:
Next session plan:
Evidence paths:
```

## Next After v1
- ROS2 message/service/action layer
- Launcher empirical calibration map (distance -> RPM/angles correction)
- Voice command mapping (`"right knee"`, `"right hip"`, `"left shoulder"`) with command arbitration
