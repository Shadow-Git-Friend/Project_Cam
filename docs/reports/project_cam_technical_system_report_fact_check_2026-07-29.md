# Project_Cam Technical Report Fact Check — 2026-07-29

This ledger records the material claims rechecked while completing the
display-fix adversarial review. “Verified” means the named source supports the
claim at this repository snapshot; it does not extend software evidence into
live commissioning, product certification, or legal advice.

## Repository and Runtime Claims

| Claim | Source | Result | Disposition |
|---|---|---|---|
| Branch and committed snapshot | `git branch --show-current`; `git rev-parse --short HEAD` | `feature/multi-person-face-id-desktop-20260712`; `7f937dbc` | verified |
| Bone consistency is display-only and default-on | `Parallel_working/scripts/live_4cam_arena_view_parallel.py`; `tests/test_display_state_isolation.py`; `tests/test_display_fix_defaults.py` | clamp receives the copied render buffer; default is `True` | verified |
| Left/right repair uses conclusive per-pair verdicts with chain fallback only for ambiguous pairs | `fix_lr_swaps_for_cam`; `tests/test_pose_lr_fix.py` | current code and regression tests agree | verified |
| Secondary tracks do not share the primary bone bank | primary-handoff and secondary-state blocks; `tests/test_skeleton_stabilize_integration.py` | secondaries have independent render state and no bank | verified limitation |

## Quantitative Evidence

| Claim | Source | Result | Disposition |
|---|---|---|---|
| Four-camera ball ground truth | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/summary_metrics.json` | 36/36; mean 156.90 mm; P95 288.34 mm; repeatability 3.09 mm | verified and scope retained |
| Four-camera joint ground truth | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_joint/summary_metrics.json` | 62/81; mean 178.98 mm; P95 243.77 mm; repeatability 4.39 mm | verified with missing-trial caveat |
| Six-camera calibration/capture status | `configs/calibration/usb6_manifest.yaml` | calibration-fit values recorded; one-controller and missing-static-GT limitations retained | verified and qualified |
| Full Python suite | `venv/bin/python -m pytest -o addopts=''` | 682 passed across 60 test files, API group included; one deprecation warning | re-measured after the display-fix guards; supersedes 673/59 |
| Critical targeted set | exact 11-file command in the report | 245 passed | supersedes 239, which predated the L/R margin and anti-churn guards |
| API `TestClient` group | `tests/test_api_*.py` (5 modules) | 25 passed in 0.98 s | contradicts the earlier "environment-level hang" exclusion; cause unknown, so CI remains the authority |

## Safety and Maturity Claims

| Claim | Source | Result | Disposition |
|---|---|---|---|
| UDP and firing-line snapshot use measured state, not display state | live UDP block; `tests/test_display_state_isolation.py` | both consume `joints_state` | verified software contract |
| Fire control is fail-closed in software | `src/project_cam/safety`; launcher runtime; fire-control tests | malformed, stale, or inconsistent state blocks | verified in software only |
| Launcher is commissioned for athlete use | repository evidence | no hardware commissioning artifact exists | claim remains explicitly rejected |
| RPM-to-m/s relationship is calibrated | runtime and calibration helper | speed remains assumed/unverified | retained as P0 blocker |

## External Licensing Claims

| Claim | Source | Result | Disposition |
|---|---|---|---|
| Ultralytics commercial redistribution is resolved | current official Ultralytics licensing page and repository license, checked 2026-07-29 | official materials describe AGPL-3.0 and commercial licensing paths; this repository contains no evidence of a completed commercial-license decision | retain as open P0; do not state legal entitlement |
| OpenCV YuNet/SFace model redistribution is resolved | current official OpenCV Zoo repository and per-model documentation, checked 2026-07-29 | OpenCV Zoo is Apache-2.0 overall; the YuNet directory states MIT and the SFace directory states Apache-2.0; exact bundled artifacts, hashes, notices, and product obligations still need an inventory | qualify; do not claim complete product clearance |

Authoritative sources checked on 2026-07-29:

- [Ultralytics licensing](https://www.ultralytics.com/license)
- [Ultralytics official repository and license](https://github.com/ultralytics/ultralytics)
- [OpenCV Zoo official repository](https://github.com/opencv/opencv_zoo)
- [OpenCV Zoo YuNet model documentation](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md)
- [OpenCV Zoo SFace model documentation](https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/README.md)
