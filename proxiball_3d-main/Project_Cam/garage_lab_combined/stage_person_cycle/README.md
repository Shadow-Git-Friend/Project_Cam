# Stage-2 Person Cycle (right_knee -> nose -> body_center)

This folder contains the dedicated workflow for the next integration stage:
- Track live person with 4 cameras.
- BLM sequence on `start`:
  1. aim to `right_knee`, keep wheels spinning 30s,
  2. home + wait 10s,
  3. aim to `nose`, keep wheels spinning 30s,
  4. home + wait 10s,
  5. aim to `body_center`, keep wheels spinning 30s.

All logs for this stage should be written under this folder (`sessions/...`).

## 1) Create session folder

```bash
cd /home/hanush/Desktop/Project_Cam
SESSION="garage_lab_combined/stage_person_cycle/sessions/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$SESSION"/{logs,reports}
echo "$SESSION"
```

## 2) Terminal A: start live 4-cam UDP stream

```bash
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_final.json \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \
  --udp-target-host 127.0.0.1 \
  --udp-target-port 5005 \
  --udp-target-joints right_knee,nose,left_hip,right_hip \
  --udp-target-conf-min 0.35 \
  --udp-target-cams-min 2
```

Notes:
- `body_center` is derived automatically from `(left_hip + right_hip)/2`.
- Keep person in view of at least 3 cameras when possible.

## 3) Terminal B: start launcher runtime

```bash
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 \
  --launcher-x-mm 600 --launcher-y-mm 1560 --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets right_knee,nose,body_center \
  --disable-zone-check \
  --target-hold-sec-map right_knee:30,nose:30,body_center:30 \
  --home-between-targets \
  --home-wait-sec 10 \
  --run-once-per-start \
  --shoot-enabled \
  --fixed-speed-kmh 40 \
  --velocity-to-rpm 68 \
  --pitch-trim-deg -1.0 \
  --yaw-trim-deg 0.0 \
  --max-abs-angle-deg 40 \
  --no-setzero-on-start \
  --home-on-start --home-on-exit \
  --dry-run-log-jsonl "$SESSION/logs/person_cycle.jsonl"
```

Operator commands:
- `start` = run one full cycle
- `shoot` = manual feeder pulse during hold window (optional)
- `reload` = manual reload
- `home` = go to `set 0 0 0 0`
- `estop` / `clear` / `status` / `quit`

## 4) Metrics/report after run

```bash
./venv/bin/python garage_lab_combined/stage_person_cycle/analyze_person_cycle_metrics.py \
  --log "$SESSION/logs/person_cycle.jsonl" \
  --out-dir "$SESSION/reports" \
  --expected-sequence right_knee,nose,body_center
```

Outputs:
- `$SESSION/reports/person_cycle_summary.json`
- `$SESSION/reports/person_cycle_report.md`

## 5) Recommended acceptance checks

- All 3 targets have at least one `OK` event.
- No `ESTOP` and no repeated `OUT_OF_RANGE`.
- `hold_valid_ratio` near 1.0 for each target.
- `hold_xyz_std_mm` remains low and stable during 30s windows.
- Visual hit consistency improves after pitch/yaw/speed trims.
