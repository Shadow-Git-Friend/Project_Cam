# Slide Plan — MSc Thesis Defense

**Title:** Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking
**Author:** Hanush · **Institution:** Nazarbayev University · **Program:** MSc ECE
**Target time:** 17 min speaking + 3 min buffer (within 15–20 min slot)
**Deck size:** 15 visible slides + 4 hidden appendix = 19 total
**Design tokens:** accent `#E88B40`, text `#1F1F1F`, bg `#FFFFFF`, fill `#F5F2ED`, subtext `#8A8A8A`

| # | Title | Time | Cumulative |
|---|---|---|---|
| 1 | Title | 0:30 | 0:30 |
| 2 | Motivation | 1:00 | 1:30 |
| 3 | Problem & Objectives | 1:15 | 2:45 |
| 4 | Background | 1:15 | 4:00 |
| 5 | Proposed System | 1:00 | 5:00 |
| 6 | Architecture | 1:30 | 6:30 |
| 7 | Hardware | 1:30 | 8:00 |
| 8 | Software | 1:15 | 9:15 |
| 9 | Calibration | 1:15 | 10:30 |
| 10 | Methodology | 1:30 | 12:00 |
| 11 | Key Results | 1:30 | 13:30 |
| 12 | Analysis | 1:15 | 14:45 |
| 13 | Limitations | 1:00 | 15:45 |
| 14 | Conclusions | 1:00 | 16:45 |
| 15 | Future Work + Ethics | 1:00 | 17:45 |

**Total: 17:45. Buffer before 20:00: 2:15.**

---

## Slide 1 — Title

- **Objective:** Identify the thesis, author, committee, and institution in one glance.
- **Content**
  - Title: "Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking"
  - MSc Thesis Defense — School of Engineering & Digital Sciences — Nazarbayev University
  - Author: Hanush
  - Supervisor: [FILL ME]
  - Committee: [FILL ME]
  - Date: [FILL ME]
- **Visual:** NU logo top-left; [PLACEHOLDER_SCREENSHOT_1: arena hero photo showing 4 cameras + launcher] right half.
- **Notes:** Greet the committee, state the full title once. Announce the 17-minute budget and ask questions be held for the end. Do not read author/committee names off the slide — they already see them.
- **Time:** 0:30

## Slide 2 — Motivation & Context

- **Objective:** Establish why the problem matters before any technical content.
- **Content**
  - Commercial ball launchers are open-loop — blind to the athlete.
  - Pro motion capture (OptiTrack, Vicon) costs USD 50k–200k.
  - Sports and rehabilitation need joint-aware, reactive delivery.
  - This thesis: USD ~200 perception, closed-loop, markerless.
- **Visual:** [PLACEHOLDER_SCREENSHOT_2: split card — left a commercial ball launcher, right a pro MoCap lab].
- **Takeaway:** A real, affordable gap to close.
- **Notes:** Anchor the panel on adaptive delivery before CV shows up. This framing protects against "this is just a vision paper" from an ECE committee. Mention sports and rehab as two concrete markets.
- **Time:** 1:00

## Slide 3 — Problem Statement & Objectives

- **Objective:** State what is being solved and how success is measured.
- **Content**
  - O1 — Sub-200 mm joint 3D accuracy (mean).
  - O2 — End-to-end latency ≤ 400 ms, ≥ 15 FPS.
  - O3 — Perception BOM under USD 500.
  - O4 — ECE-grade safety with ISO-aligned stop paths.
- **Visual:** 4-tile grid with orange numerals O1–O4.
- **Takeaway:** Four measurable objectives set the scoring rubric.
- **Notes:** State the four objectives as the internal scoring rubric of this thesis. Each will reappear with a verdict on the results slide. Do not add a fifth objective during Q&A.
- **Time:** 1:15

## Slide 4 — Background & Related Work

- **Objective:** Position the work in the literature and among peer projects.
- **Content**
  - Optical MoCap (OptiTrack, Vicon) — accurate, costly, markered `[VERIFY]`.
  - Monocular pose (OpenPose `[VERIFY]`, MediaPipe, YOLO-Pose) — cheap, no metric depth.
  - Multi-view triangulation (Hartley & Zisserman, SVD-DLT) — geometry core `[VERIFY citation]`.
  - Bachelor-team single-cam launcher baseline; yessimkhan 2025 omnidirectional launcher.
- **Visual:** 2×2 comparison table — rows: MoCap / Mono / Multi-view / This work — columns: Cost / Accuracy / Markerless / Closed-loop.
- **Takeaway:** Multi-view + YOLO-Pose is the affordable-accurate sweet spot.
- **Notes:** Mention the two in-lab precursors by name — panel will respect explicit positioning against the team's own previous work. Keep all citations factual; `[VERIFY]` any name that is not in the thesis bibliography.
- **Time:** 1:15

## Slide 5 — Proposed System — Engineering First

- **Objective:** Shift framing from "a CV project" to "an ECE system".
- **Content**
  - Five layers: Chassis · Electronics · Firmware FSM · Supervisor · Perception.
  - Perception is a replaceable *sensor module*.
  - Contribution is in integration, safety, and BOM — not any single layer.
- **Visual:** [PLACEHOLDER_DIAGRAM_1: five-layer vertical stack, orange down-arrows = command path, gray up-arrows = telemetry].
- **Takeaway:** An ECE integration, with CV as one component.
- **Notes:** This slide is load-bearing for rubric points. Speak slowly. Say: "the novelty is in how these layers are glued together, not in any one layer." Stand on this sentence.
- **Time:** 1:00

## Slide 6 — Architecture / Pipeline

- **Objective:** Show the full data path and its latency budget.
- **Content**
  - Capture → YOLO ball + YOLO-Pose (TRT FP16) → SVD-DLT triangulation → adaptive EMA → Kalman → UDP → supervisor → ballistic solver → ESP32 FSM.
  - Perception + command: ~120 ms; mechanical settling: ~80 ms; total: ~200 ms.
- **Visual:** [PLACEHOLDER_DIAGRAM_2: horizontal block diagram with per-block millisecond labels].
- **Takeaway:** Every stage has a measured cost.
- **Notes:** Walk left-to-right without diving into any single block. Promise the panel that accuracy, latency, and safety each get their own slide. This is the map, not the territory.
- **Time:** 1:30

## Slide 7 — Hardware Implementation

- **Objective:** Demonstrate hardware competence — the ECE rubric centre of gravity.
- **Content**
  - 4× Hikvision DS-E12 USB cameras, 1280 × 720, ~USD 30 each.
  - ESP32 as single MCU (dual-core, 240 MHz, native UART > 1 Mbaud).
  - 2× NEMA-23 + 1:50 worm-gear reducers (self-locking on power loss).
  - DRV8825 pusher, counter-rotating BLDC flywheels, 24 V fused rail.
  - Normally-closed E-STOP, ISO 13849-1 Cat. 1 stop path.
- **Visual:** [PLACEHOLDER_SCREENSHOT_3: arena photo] + BOM table (6 rows, approximate USD).
- **Takeaway:** Commodity parts assembled with system-level rigour.
- **Notes:** Highlight the *single-ESP32* migration — this replaced a legacy Arduino+ESP32 bridge and removed ~80 ms of parsing tail. Point to the worm-gear self-locking as a mechanical safety feature.
- **Time:** 1:30

## Slide 8 — Software Implementation

- **Objective:** Name every layer of the stack with a module that owns it.
- **Content**
  - Perception: YOLO-Pose (17 COCO kpts) + custom YOLO ball, TensorRT FP16.
  - Geometry: `triangulate_multi()` SVD-DLT, `robust_triangulate_ball()` iterative.
  - Filtering: adaptive EMA + per-joint Kalman (CV, PN=500, MN=10).
  - Supervisor: Python + pyserial, zone/conf/stability gates, linear GT correction.
  - Firmware: `control_12_full.ino`, cooperative FSM, 921 600 baud.
- **Visual:** Two-column — left: framework/module table; right: the `set v h wl wr` firmware excerpt.
- **Takeaway:** Every layer has a named, reviewable module.
- **Notes:** Emphasize TensorRT FP16 — this is what buys the 15 FPS target on a single RTX 2080 Ti. Avoid deep CV internals; the audience is ECE.
- **Time:** 1:15

## Slide 9 — Calibration & Geometry

- **Objective:** Prove the geometric foundation is version-controlled and auditable.
- **Content**
  - Intrinsics: ChArUco per-camera, RMS reprojection 0.73 px `[VERIFY]`.
  - Extrinsics: 24-tag AprilTag wall + robust PnP-RANSAC.
  - World frame: X = length, Y = width, Z = up, all mm.
  - `arena_fixed` set owns the Y-axis convention.
- **Visual:** [PLACEHOLDER_DIAGRAM_3: ChArUco pattern top-left; 3D arena plot with 4 camera frusta right].
- **Takeaway:** Geometry is versioned and frozen.
- **Notes:** State that 0.73 px RMS is at calibration resolution. Redirect resolution-change questions to the appendix — it requires intrinsic rescaling.
- **Time:** 1:15

## Slide 10 — Methodology & Experiments

- **Objective:** Show the experimental discipline backing every number.
- **Content**
  - GT rig: measured static grid + joint-touch protocol.
  - Sequences: walk / jog / jump — 449 frames × 4 cams × 15 FPS.
  - Ablations: EMA α sweep, adaptive snap, YOLO-Pose vs MMPose.
  - Kalman tuning: process/measurement noise grid.
  - Bring-up: S0–S4 + integrated live test, PASSED 2026-04-09.
- **Visual:** Experiment matrix table (rows: experiments; cols: inputs, metric, outcome).
- **Takeaway:** Every claim has a recorded sequence behind it.
- **Notes:** Stress that tuning used *recorded* sequences — results are reproducible. Mention the S0–S4 ladder as engineering discipline, not overkill.
- **Time:** 1:30

## Slide 11 — Key Results

- **Objective:** Deliver the headline numbers against the four objectives.
- **Content**
  - Ball static: mean 156.90 mm, P95 288.34 mm, precision 3.09 mm.
  - Joint-touch: mean 178.98 mm, P95 243.77 mm, precision 4.39 mm.
  - Bias X+83, Z−125 mm — correctable by linear model.
  - YOLO-Pose TRT FP16: 6.2 ms/image (6.2× MMPose 38.5 ms).
  - Perception + command: ~120 ms; 15 FPS sustained.
- **Visual:** `viz_gt_bias_analysis.png` (left, 60%) + latency bars from `viz_speed_comparison.png` (right, 40%). Paths: `Parallel_working/output/ablation_results/`.
- **Takeaway:** O1 and O2 met; O3 met at USD ~200; O4 proven by bring-up.
- **Notes:** Place a green tick next to O1 and O2 as you speak. Acknowledge the bias up front — do not let the panel catch it.
- **Time:** 1:30

## Slide 12 — Analysis & Interpretation

- **Objective:** Interpret the numbers and defend the method.
- **Content**
  - Bias is fixed and calibration-limited — linear correction removes it.
  - Precision 3–4 mm ≈ the sensor is consistent, only offset.
  - YOLO-Pose: <5 mm 3D jitter delta vs MMPose at 6× speed.
  - Kalman (PN=500, MN=10): +47% walk, +34–39% jog, ~neutral jump.
- **Visual:** `viz_backend_comparison.png` + `viz_gt_joint_errors.png` side-by-side.
- **Takeaway:** Error is calibration-limited, not perception-limited.
- **Notes:** Most important interpretive slide. Expect "179 mm is a lot" — answer: precision is 4 mm, bias is correctable, perception is not the bottleneck.
- **Time:** 1:15

## Slide 13 — Limitations & Challenges

- **Objective:** Own the trade-offs; map each to a mitigation.
- **Content**
  - Constant-velocity Kalman ~neutral on jump motion (acceleration-aware future).
  - Ball exit velocity uncalibrated at 800 RPM — solver uses fixed 10 m/s.
  - Horizontal stepper backlash ~2° (software-compensated).
  - Bounce: ball outside 3-cam frustum — single-cam fallback covers it.
  - One-camera sun-saturation → graceful degradation to 3-cam triangulation.
- **Visual:** `viz_ema_ablation_jitter.png` with labelled arrow to the jump bar.
- **Takeaway:** Bounded, documented, mitigated.
- **Notes:** The rubric rewards honest self-assessment. Frame each limitation with its mitigation to close cleanly. Do not hedge.
- **Time:** 1:00

## Slide 14 — Conclusions & Contributions

- **Objective:** Close the loop with six named engineering contributions.
- **Content**
  - 921 600-baud USB serial migration (replaces BLE Nordic UART).
  - Single-ESP32 consolidation (replaces Arduino+ESP32 two-MCU stack).
  - Closed limit-switch FSM with 10 s dispense timeout.
  - ±30° software angle clamp — prevents ESP32 reboot.
  - Python-side RPM gate — defence-in-depth with firmware.
  - Live-tuning commands (`jsset`, `jfspeedset`, `jfaccelset`).
- **Visual:** 6-tile contribution grid (orange numerals 1–6, dark text, warm fill).
- **Takeaway:** An ECE contribution that happens to use CV.
- **Notes:** Deliver each contribution as a one-sentence engineering fact. No hedging. This slide is the thesis's defence against "what did *you* do, not the team?".
- **Time:** 1:00

## Slide 15 — Future Work + Ethics & Standards

- **Objective:** Show extensibility and responsible engineering.
- **Content**
  - Future: RPM→m/s radar-gun calibration, acceleration-aware Kalman, ROS2, HMAC link auth.
  - Standards honored: ISO 12100, ISO 13849-1 Cat. 1, IEC 60204-1, ISO 10218-1.
  - Applicability: sports training, rehabilitation, adaptive PE instruction.
  - Open-sourcing the perception layer is planned `[VERIFY]`.
- **Visual:** Two columns — left: roadmap with orange chevrons; right: compliance badges grid.
- **Takeaway:** Extensible and responsibly engineered.
- **Notes:** Close with: "Thank you — I am happy to take questions." Do not thank supervisors here; do that verbally off-slide.
- **Time:** 1:00

---

## Appendix — Hidden slides (unhide only if a question warrants)

### A1 — Live Demo

- **Objective:** Play a visual proof point on demand.
- **Content:** Single-line caption under the video.
- **Visual:** [PLACEHOLDER_VIDEO_1: `Parallel_working/output/recordings/arena3d_20260417_123348.mp4`, trimmed to 20–30 s, muted].
- **Notes:** Play if committee asks for a demo or if a 3–5 min buffer opens. Stage it muted. If the file is missing, fall back to the 2D mosaic `mosaic2d_20260415_132441_slow.mp4`.

### A2 — 10-Layer Safety Stack

- **Objective:** Answer any "what if X fails?" question decisively.
- **Content:** L1 Zone · L2 Confidence · L3 Stability · L4 Angle clamp (Py + FW) · L5 RPM gate (Py + FW) · L6 Arm state · L7 Typed confirm · L8 Hardware E-STOP · L9 Link-loss auto-stop · L10 Exception path.
- **Visual:** Vertical stack diagram, operator at top (orange), hardware at bottom (gray).
- **Notes:** Source: `thesis_engineering_chapter.md` §Safety. Use when panel asks about failure modes.

### A3 — End-to-End Latency Budget

- **Objective:** Answer "real-time?" questions with numbers.
- **Content:** [PLACEHOLDER_TABLE_1: frame-by-frame table from `Parallel_working/output/perf_blm_20260417_134210.jsonl`].
- **Visual:** Table — stage | mean ms | P95 ms. Include: capture, ball detect, pose, triangulation, EMA, Kalman, UDP, serial, mechanical settle.
- **Notes:** Sum of means is the perception + command number quoted on slide 6.

### A4 — ECE Curriculum Mapping

- **Objective:** Pivot the defense to ECE coursework if a panelist goes there.
- **Content:** 3-column grid — Course | Concept used | Evidence in thesis.
  - Signals & Systems → sampling, aliasing → 15 FPS frame sync notes in `docs/archive/legacy_notes/new_complete.md`.
  - Control Systems → stability gate, Kalman CV model → §Filtering in thesis.
  - Embedded Systems → ESP32 cooperative FSM, DRV8825 timing → `control_12_full.ino`.
  - Computer Networks → UDP-over-loopback payload schema → `launcher_runtime_from_udp.py`.
  - Engineering Ethics → ISO-aligned stop paths, operator exclusion zones → §Safety.
- **Notes:** Use only if asked "which courses prepared you for this?".

---

## Global notes

- Pre-defense rehearsal: record two dry runs, target 16:30–17:30 total speaking, refine slides that overrun by >10 s.
- If the committee arrives late, cut slide 4 (Background) to 45 s and slide 13 (Limitations) to 45 s for a 16 min variant.
- If the committee asks to see code live, open `live_4cam_arena_view_parallel.py` (not the firmware) in a separate window — never modify during defense.
- **Do not** introduce new numbers during Q&A that are not on a slide or in `qa_bank.md`.
