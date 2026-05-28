# Assets Checklist — Defense Deck

Legend: ✅ ready · 🔧 to prepare · 🚧 nice-to-have. All paths are relative to `/home/hanush/Desktop/Project_Cam/` unless stated otherwise.

---

## 1. Ready-to-use assets (✅)

### Demo videos

| ID | Path | Size | Where used |
|---|---|---|---|
| V-01 | `Parallel_working/output/recordings/arena3d_20260417_123348.mp4` | 16 MB | Appendix A1 (main demo) |
| V-02 | `Parallel_working/output/recordings/mosaic2d_20260417_123348.mp4` | 162 MB | A1 fallback (2D grid) |
| V-03 | `Parallel_working/output/recordings/mosaic2d_20260415_132441_slow.mp4` | 65 MB | A1 alternate (slow-motion throw) |
| V-04 | `Parallel_working/output/recordings/mosaic2d_20260415_132722_bounce.mp4` | 52 MB | Bounce Q&A backup |
| V-05 | `Parallel_working/output/test_sequences/bounce_08_long_occlusion_then_reacquire/detections_*_mosaic.mp4` | ~5 MB | Robustness Q&A backup |

### Result plots (all from `Parallel_working/output/ablation_results/`)

| ID | File | Slide |
|---|---|---|
| P-01 | `viz_gt_bias_analysis.png` | 11 (primary results) |
| P-02 | `viz_gt_joint_errors.png` | 12 |
| P-03 | `viz_gt_ball_errors.png` | 12 backup |
| P-04 | `viz_backend_comparison.png` | 12 |
| P-05 | `viz_speed_comparison.png` | 11 (latency bars) |
| P-06 | `viz_ema_ablation_jitter.png` | 13 |
| P-07 | `viz_detection_rates.png` | 13 backup |
| P-08 | `garage_lab_combined/gt_eval/session_20260303/visualizations/joint_touch_3d_gt_vs_est.png` | 12 backup |
| P-09 | `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/visualizations/joint_touch_error_boxplot.png` | 12 backup |

### Tables / numeric sources

| ID | File | Purpose |
|---|---|---|
| T-01 | `garage_lab_combined/gt_eval/session_20260303/trials.csv` | Per-trial ball GT |
| T-02 | `garage_lab_combined/gt_eval/session_20260303/reports/trial_errors_B02_B10.csv` | Ball error rows |
| T-03 | `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/trials_joint_81_mm.csv` | Joint trial data |
| T-04 | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_joint/trial_errors.csv` | Final arena_fixed joint results |
| T-05 | `garage_lab_combined/gt_eval/rigid_trials_18_mm.csv` | Rigid baseline |

### Calibration artefacts

| ID | File | Purpose |
|---|---|---|
| C-01 | `garage_lab_combined/cal/intrinsics/camNorth_intrinsics.json` | Slide 9 cam intrinsics quote |
| C-02 | `garage_lab_combined/cal/intrinsics/camEast_intrinsics.json` | Slide 9 |
| C-03 | `garage_lab_combined/cal/intrinsics/camSouth_intrinsics.json` | Slide 9 |
| C-04 | `garage_lab_combined/cal/intrinsics/camWest_intrinsics.json` | Slide 9 |
| C-05 | `arena_fixed/cal/extrinsics/extrinsics_fixed.json` | Slide 9 extrinsics source |
| C-06 | `arena_fixed/cal/extrinsics/Dimensions_fixed.txt` | Slide 9 arena dims |
| C-07 | `garage_lab_combined/cal/boards/Charuco_A4_300dpi_7x10_29.7mmSquare_22.275mmMarker_DICT4X4_1000.pdf` | Slide 9 ChArUco pattern |

### Firmware & perf logs

| ID | File | Purpose |
|---|---|---|
| F-01 | `control_12_full.ino` (557 lines) | Slide 8 code excerpt source |
| F-02 | `Parallel_working/output/perf_blm_20260417_134210.jsonl` | Appendix A3 latency table source |
| F-03 | `Parallel_working/output/ball_log_20260421_140804.jsonl` | Q&A backup (ball track traces) |
| F-04 | `Parallel_working/output/ball_log_20260421_152247.jsonl` | Q&A backup |

### Camera validation shots

| ID | File | Purpose |
|---|---|---|
| X-01 | `Parallel_working/output/test_captures/camNorth.jpg` | Optional on slide 7/9 |
| X-02 | `Parallel_working/output/test_captures/camEast.jpg` | Optional |
| X-03 | `Parallel_working/output/test_captures/camSouth.jpg` | Optional |
| X-04 | `Parallel_working/output/test_captures/camWest.jpg` | Optional |

---

## 2. To prepare before defense (🔧)

| ID | Asset | Slide | Recipe |
|---|---|---|---|
| D-01 | System block diagram — five-layer stack | 5 | Draw in draw.io or Excalidraw. Export 1920×1080 PNG. Background `#F5F2ED` or transparent. Five stacked rounded boxes top-to-bottom: Perception → Supervisor → Firmware FSM → Electronics → Chassis. Two arrow columns: orange `#E88B40` down (command), soft-gray `#8A8A8A` up (telemetry). |
| D-02 | Pipeline with latency budget | 6 | Horizontal block diagram: Capture → Detect → Triangulate → EMA → Kalman → UDP → Supervisor → Ballistic → Serial → ESP32 FSM. Millisecond label under each block (use numbers from CLAUDE.md latency section). Export 1920×1080 PNG. |
| D-03 | Arena hero photo | 1, 2 | Wide-angle shot of 4-camera arena + launcher on a tripod. Centre launcher, show at least 2 cameras in frame. Shoot 3:2 or 16:9. Crop to 1920×1080. |
| D-04 | Hardware close-up photo | 7 | Macro of ESP32 board + wiring harness + E-STOP button. Shoot from 45° angle. Crop to 1920×1080. |
| D-05 | Live viewer screenshot | 8 | Open `run_live_parallel_yolopose.sh` on the dev machine, capture a frame with all four 2D tiles + the 3D arena plot visible. Use OS screenshot, crop to just the window, export 1920×1080 PNG. |
| D-06 | Trimmed demo clip | A1 | Trim V-01 to 20–30 s, keep best segment (visible motion, stable tracking). Use PowerPoint's built-in Video → Trim or Windows Video Editor. Save as `demo_clip_<date>.mp4` next to V-01. |
| D-07 | BOM table PNG or embedded object | 7 | 6-row table: Cameras (4×) | ESP32 | DRV8825 | 2× NEMA-23 | 2× BLDC + ESCs | Misc. Columns: Component, Qty, Approx USD. Fill totals to ~USD 355 (perception ~USD 200 plus actuation). Tag uncertain costs with `[VERIFY]`. |
| D-08 | 6-tile contribution grid | 14 | In PowerPoint directly: 3×2 grid. Each tile: orange numeral 1–6, one-line contribution in `#1F1F1F` 20 pt, warm-fill `#F5F2ED` background, 1 pt orange border. |
| D-09 | Experiment matrix table | 10 | Rows: Intrinsic cal, Extrinsic cal, EMA ablation, Backend compare, Kalman tune, S0–S4 bring-up. Columns: Inputs, Metric, Outcome. Keep each cell to ≤8 words. |
| D-10 | Compliance badges grid | 15 | 2×2 grid of mono-color ISO/IEC badges: `ISO 12100`, `ISO 13849-1 Cat.1`, `IEC 60204-1`, `ISO 10218-1`. Plain orange-outlined boxes with the standard code inside — no official logos. |

---

## 3. Nice-to-have (🚧)

| ID | Asset | Where |
|---|---|---|
| N-01 | Official NU logo (SVG/PNG) | Master slide, title, all headers. Fetch from NU brand kit; mark `[VERIFY]` until obtained. |
| N-02 | Supervisor headshot & titles | Title slide speaker notes; do not display. |
| N-03 | Committee names, titles, affiliations | Title slide — replace `[FILL ME]` once confirmed. |
| N-04 | Defense date & time | Title slide; `[FILL ME]` until scheduled. |
| N-05 | Audio voice-over for demo video | A1. Optional; a muted clip is fine. |
| N-06 | Printed one-page handout (PDF of the 6-tile contribution grid) | Leave 5 copies on the committee table. |

---

## 4. Missing / deferred evidence (🚨)

| ID | Missing | Slide | Placeholder to keep |
|---|---|---|---|
| M-01 | RPM→muzzle-speed calibration curve | 13 | `[MISSING EVIDENCE]` — stated limitation, do not invent. |
| M-02 | Bundle-adjustment or Cramér-Rao lower bound analysis | Q&A backup | `[VERIFY]` — referenced in QA only if asked; do not put on main deck. |
| M-03 | Published peer paper of this thesis | 15 (future work) | `[VERIFY]` — open-sourcing mention stays conditional. |

---

## 5. Consolidation: what to copy to the Windows laptop

Create a folder `defense_assets/` on the Windows machine and drop in:

```
defense_assets/
├── videos/
│   ├── arena3d_20260417_123348.mp4          (V-01)
│   ├── mosaic2d_20260415_132441_slow.mp4    (V-03, fallback)
│   └── demo_clip_trimmed.mp4                (D-06 output)
├── plots/
│   ├── viz_gt_bias_analysis.png             (P-01)
│   ├── viz_gt_joint_errors.png              (P-02)
│   ├── viz_backend_comparison.png           (P-04)
│   ├── viz_speed_comparison.png             (P-05)
│   └── viz_ema_ablation_jitter.png          (P-06)
├── diagrams/
│   ├── system_stack.png                     (D-01)
│   └── pipeline_latency.png                 (D-02)
├── photos/
│   ├── arena_hero.jpg                       (D-03)
│   ├── hardware_closeup.jpg                 (D-04)
│   └── live_viewer_screenshot.png           (D-05)
├── firmware/
│   └── control_12_full.ino                  (F-01 — for the code excerpt)
├── logo/
│   └── nu_logo.svg                          (N-01, to be fetched)
└── docs/
    ├── defense_ppt_handoff_prompt.md
    ├── slide_plan.md
    ├── assets_checklist.md
    ├── qa_bank.md
    └── presentation_build_notes.md
```

Total estimated size: <250 MB including V-01. Fits any USB stick or OneDrive upload.
