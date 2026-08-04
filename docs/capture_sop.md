# Project_Cam Capture SOP

A one-page session protocol for recording a usable athlete assessment in the
garage arena. Hand this to a new operator and they should be able to produce a
valid C3D + HTML report in under 20 minutes.

## Hardware checklist (do once per session)

- [ ] All 4 USB cameras powered and recognized by Linux (`v4l2-ctl --list-devices`).
- [ ] Arena floor cleared, AprilTag markers in `arena_fixed/` positions undisturbed.
- [ ] Lighting steady: no direct sunlight onto cameras, no flickering fluorescents.
- [ ] BLM unplugged from serial bus if you are doing assessment-only capture.
      The recorder does not need it. Leave power off so you cannot accidentally fire.
- [ ] Athlete wearing fitted clothing (loose hoodies kill joint detection).

## Calibration check (every athlete, every session)

The calibration gate is the only thing standing between you and a report that
silently mislabels a bad recording as "usable." Do not skip it.

```bash
# Terminal 1 — start the live viewer (no BLM):
./Parallel_working/run_live_parallel_yolopose.sh

# Terminal 2 — record a 15-second T-pose (arms straight out, palms forward):
apps/athlete_assessment/record_joints_udp.sh \
  data/raw/athlete_001_tpose.jsonl \
  athlete_001_tpose athlete_001 calibration 10 male

# Terminal 2 — verify calibration is stable:
apps/assessment_calibration/run_pre_session_check.sh \
  data/raw/athlete_001_tpose.jsonl \
  data/reports/athlete_001_pre_session_calibration.json
```

**Pass criteria:** Status `ok`, shoulder-width std ≤ 5 mm, both shoulder-to-wrist
std ≤ 5 mm. If status is `warning`, do NOT proceed — re-pose and re-record. The
single most common cause is the athlete not holding the T-pose still for the full
15 seconds.

## Squat capture

```bash
# Terminal 2 — 15-second recording, 5 reps at a comfortable pace:
apps/athlete_assessment/record_joints_udp.sh \
  data/raw/athlete_001_squat.jsonl \
  athlete_001_squat athlete_001 squat 10 male
```

Athlete cues:
- Start standing, feet shoulder-width apart, toes slightly out.
- Descend slowly until thighs parallel to floor (or as deep as comfortable).
- Drive through heels back to standing.
- Repeat 5 times within the 15-second window.

## Generate the report

```bash
PROJECT_CAM_CALIBRATION_REPORT=data/reports/athlete_001_pre_session_calibration.json \
apps/athlete_assessment/run_offline_assessment.sh \
  data/raw/athlete_001_squat.jsonl \
  squat \
  data/reports/athlete_001_squat_report.json \
  athlete_001 10 male

# Or directly with C3D export for biomech-lab partners:
PYTHONPATH=src ./venv/bin/python -m project_cam.assessment.offline_assess \
  --input data/raw/athlete_001_squat.jsonl \
  --exercise squat \
  --athlete-id athlete_001 --age 10 --sex male --fps 15 \
  --session-id athlete_001_squat_session_001 \
  --output data/reports/athlete_001_squat_report.json \
  --html-output data/reports/athlete_001_squat_report.html \
  --c3d-output data/reports/athlete_001_squat_report.c3d \
  --calibration-report data/reports/athlete_001_pre_session_calibration.json
```

## Reading the HTML report

- **Data Quality** (numeric 0-100) — purely a tracking-confidence score. >75 = High.
- **Movement Quality** (`Looks good` / `Needs review` / `Cannot score`) —
  derived from coaching flags. Independent of Data Quality on purpose; a session
  can have High data and still warrant review if the athlete moved poorly.
- **Coaching flags** (`coaching` severity) — actionable. These drive
  Movement Quality.
- **Info observations** (`info` severity) — diagnostic only. The `knee_line_deviation`
  observation in particular is depth-confounded and is NOT a coaching signal.
  See [reports.py](../src/project_cam/assessment/reports.py) for the inline note.

## Known failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `calibration_gate: failed` | Athlete swayed during T-pose | Re-record T-pose, make sure they hold still 15 s |
| Low Data Quality (<50) | Bad lighting, occluded joint, athlete in dark clothing | Better light, fitted clothing, athlete inside arena bounds |
| 0 reps detected | Athlete did not complete full squat range | Check `min_pelvis_travel_mm` in config matches athlete height; coach deeper squat |
| `metric_confidence: blocked` for left/right knee | Knee occluded by camera angle most of the session | Re-record with athlete farther from the East/West cameras |
| Valgus flag fires on visibly-clean squat | Athlete may genuinely have asymmetric knee tracking; OR threshold too tight | Compare against `data/raw/athlete_001_squat_clean.jsonl` baseline; tune `max_knee_valgus_signed_ratio` in [football_academy_u10.yaml](../configs/exercises/football_academy_u10.yaml) |

## Closed-loop (with BLM)

This SOP covers assessment-only. For the closed-loop demo (live viewer + launcher),
use a session-id and event log for the demo narrative:

```bash
# Terminal 1 — live viewer:
./Parallel_working/run_live_blm.sh --session-id demo_001 \
  --event-log-output data/events/demo_001_viewer.jsonl

# Terminal 2 — launcher:
./venv/bin/python garage_lab_combined/scripts/blm_follow.py \
  --serial-port /dev/ttyUSB0 --launcher-yaw-deg 0 \
  --joint right_shoulder --correction-mode linear \
  --min-confidence 0.55 --min-cameras 2
```

Then during the demo, press `r` in the live-viewer window when the athlete
reacts in time, or `n` when they do not. Each keypress emits an event into
`data/events/demo_001_viewer.jsonl` for post-session analysis. The `session_id`
field joins this stream with the launcher decision log.
