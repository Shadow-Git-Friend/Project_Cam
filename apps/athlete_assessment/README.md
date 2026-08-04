# Athlete Assessment MVP

This app layer records Project_Cam live 3D COCO-17 joints over UDP and generates
offline JSON coaching reports.

Record live joints:

```bash
apps/athlete_assessment/record_joints_udp.sh data/raw/session_001_joints.jsonl session_001 athlete_001 squat 10 male
```

The recorder waits 10 seconds by default before saving frames, then records for
15 seconds and stops automatically. This gives a single tester time to walk to
the arena center and prevents walking back to the keyboard from being included.
Override the delay when needed:

```bash
PROJECT_CAM_RECORD_DELAY_SEC=5 apps/athlete_assessment/record_joints_udp.sh data/raw/session_001_joints.jsonl session_001 athlete_001 squat 10 male
PROJECT_CAM_RECORD_DELAY_SEC=0 apps/athlete_assessment/record_joints_udp.sh data/raw/session_001_joints.jsonl session_001 athlete_001 squat 10 male
```

Override the automatic recording duration when needed:

```bash
PROJECT_CAM_RECORD_DURATION_SEC=15 apps/athlete_assessment/record_joints_udp.sh data/raw/tpose.jsonl tpose athlete_001 calibration 10 male
PROJECT_CAM_RECORD_DURATION_SEC=35 apps/athlete_assessment/record_joints_udp.sh data/raw/squat.jsonl squat athlete_001 squat 10 male
```

Run live tracking in another terminal:

```bash
apps/athlete_assessment/run_live_tracking_for_assessment.sh
```

Generate a report:

```bash
apps/athlete_assessment/run_offline_assessment.sh data/raw/session_001_joints.jsonl squat data/reports/session_001_squat_report.json athlete_001 10 male
```

Optional maturity and calibration context:

```bash
PROJECT_CAM_STANDING_HEIGHT_CM=140 \
PROJECT_CAM_SITTING_HEIGHT_CM=72 \
PROJECT_CAM_BODY_MASS_KG=34 \
PROJECT_CAM_CALIBRATION_REPORT=data/reports/tpose_calibration_check.json \
apps/athlete_assessment/run_offline_assessment.sh data/raw/session_001_joints.jsonl squat data/reports/session_001_squat_report.json athlete_001 10 male
```

The wrapper writes both JSON and HTML by default. Set
`PROJECT_CAM_ASSESSMENT_HTML_OUTPUT=""` to skip HTML generation.
