 # Defense PPT Handoff Prompt — Paste Into Claude in PowerPoint

> Copy everything between the two horizontal rules below into the chat panel of Claude in PowerPoint on Windows. Do not edit it before pasting. After generation, follow `presentation_build_notes.md` to finish the deck.

---

You are a thesis-presentation architect. I am an MSc ECE student at **Nazarbayev University (NU)**. Build a defense PowerPoint (`.pptx`) for my master's thesis, **"Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking"**. Target speaking time is **17 minutes with a 3-minute buffer** inside a 15–20 min defense slot.

## Project brief (one paragraph — use as source of truth)

The thesis builds a closed-loop robotic ball launcher that uses four commodity USB cameras (1280×720 @ 15 FPS) with YOLO-Pose + YOLO ball detection and SVD-DLT multi-view triangulation to estimate a human target's 3D joints and ball position in millimetres. A per-joint Kalman filter with a constant-velocity model predicts target positions 200–400 ms ahead to compensate launcher latency. The 3D target is broadcast via UDP to a Python supervisor, which applies safety gates, a linear GT correction model, and an analytic low-arc ballistic solver before sending pitch/yaw/RPM commands at 921 600 baud to an ESP32 running a cooperative finite-state machine (`control_12_full.ino`). The system targets sports training and rehabilitation — an affordable (~USD 200 perception) alternative to professional motion-capture rigs (USD 50k–200k).

## Design system — non-negotiable

Slide size: **16:9 widescreen (13.333 in × 7.5 in)**. Master slide palette (NU-inspired warm academic, not corporate blue):

| Token | Hex | Use |
|---|---|---|
| Accent orange | `#E88B40` | Titles underline, section dividers, key numbers, data arrows |
| Dark text | `#1F1F1F` | Body, headings |
| White | `#FFFFFF` | Primary background |
| Warm light fill | `#F5F2ED` | Section-divider slides, quote cards, callout boxes |
| Soft gray | `#8A8A8A` | Subtext, captions, secondary lines |

Typography: sans-serif. Prefer **Inter**, fallback **Calibri** (both safe on Windows). Title 36 pt, message line 22 pt, body 20 pt, caption 14 pt. **Body text must never drop below 18 pt.**

Layout grid: 1 title + 1 one-line "message" sentence at the top (bold, 22 pt) + 1 visual **or** ≤5 short bullets below. **Never** put a full-slide orange background; the orange is an accent, applied as a 4-pt bar under titles, as chart highlights, and as divider ribbons only. Avoid gradients, drop shadows, emojis, clipart, and more than one animation per slide (Appear only).

Each slide follows the hierarchy: **Title → Message → Evidence → Takeaway**. The takeaway is a one-line sentence in the bottom bar in `#8A8A8A`.

## Hard rules

1. **Do not fabricate** numbers, citations, names, dates, or methods. Every quantitative claim in the inline content table below is grounded in the repo — reuse it verbatim.
2. **Preserve placeholder tokens exactly as written**: `[PLACEHOLDER_SCREENSHOT_N: …]`, `[PLACEHOLDER_VIDEO_N: …]`, `[PLACEHOLDER_DIAGRAM_N: …]`, `[PLACEHOLDER_TABLE_N: …]`, `[VERIFY]`, `[FILL ME]`, `[MISSING EVIDENCE]`. Render them as orange-outlined rectangles with the description as the caption so the user can replace them later. Do **not** substitute stock images or invented screenshots.
3. **Keep bullets short** — max 12 words per bullet, max 5 bullets per slide.
4. **Always add speaker notes** on every slide. Notes should be 60–90 words of connective tissue (not a script verbatim), with cue phrases for transitions.
5. **One message, one visual** per slide. If a slide would be cluttered, split it or move extra evidence to an appendix slide.
6. **Appendix slides must be present but hidden** from the main playback (use PowerPoint's Hide Slide) so they only surface when a panelist asks.
7. **No animations** other than a subtle `Appear` on grouped evidence. No slide transitions other than `Fade` at 0.3 s.
8. **Use real references** where the prompt provides them; mark every other citation as `[VERIFY]`.

## Rubric alignment (optimize for this)

The defense is graded on 100 points: 50 presentation + 50 technical.

- **Speech & Style (10 pts)** → clean typography, consistent hierarchy, no wall-of-text.
- **Structure (10 pts)** → the 15-slide flow below follows problem → literature → method → results → limitations → conclusion → future work. Preserve the order.
- **Visual aids (10 pts)** → prefer diagrams, tables, and result plots over bullet lists. The plan below names the specific figure for each results slide.
- **Q&A (20 pts)** → build the 4 appendix slides listed below; they are direct ammunition for panel questions.
- **Introduction (10 pts)** → slides 2–4 cover problem, objectives, literature, and relevance to industry/society.
- **Technical competency (30 pts)** → slides 5–12 show design justification, methodology, tools, results interpretation, and cost/efficiency arguments.
- **Conclusions + ethics (10 pts)** → slide 15 explicitly lists standards honored (ISO 12100, ISO 13849-1, IEC 60204-1), advantages, disadvantages, and real-world applicability.

## Inline slide specification (build exactly these slides, in this order)

Every slide below is in the format:
**N. Title — Message — [Bullets] — Visual — Takeaway — Notes (≤90 words) — Time**

### Main deck (15 slides, visible)

**1. Title — "Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking"**
- Subtitle: MSc Thesis Defense · School of Engineering & Digital Sciences · Nazarbayev University
- Author: Hanush · Supervisor: [FILL ME] · Committee: [FILL ME] · Date: [FILL ME]
- Visual: [PLACEHOLDER_SCREENSHOT_1: NU logo top-left + arena hero photo right]
- Takeaway: (none)
- Notes: Greet committee, state full title once. Establish the 17-minute budget and ask that questions be held.
- 30 s

**2. Motivation — Commercial launchers are blind. Professional MoCap is unaffordable.**
- Coaches need joint-specific delivery for training and rehab.
- Open-loop launchers cannot react to athlete position.
- OptiTrack/Vicon: USD 50k–200k + markers.
- This thesis: USD ~200 perception, closed-loop, markerless.
- Visual: [PLACEHOLDER_SCREENSHOT_2: split card — left: generic ball launcher photo, right: MoCap lab photo]
- Takeaway: There is a real, affordable gap to close.
- Notes: Frame the panel's attention on the *adaptive delivery* problem before any CV content. Emphasize that industry already uses the expensive solution — we are democratizing it.
- 60 s

**3. Problem Statement & Objectives**
- O1 — Sub-200 mm 3D joint accuracy (mean) in a 4 × 5 m arena.
- O2 — End-to-end latency ≤ 400 ms, perception ≥ 15 FPS.
- O3 — Perception BOM under USD 500.
- O4 — ECE-grade safety: multi-layer interlocks, ISO-aligned stop paths.
- Visual: 4-tile grid with orange accent numbers (O1–O4).
- Takeaway: Accuracy, latency, cost, and safety — measured, not claimed.
- Notes: State the four objectives as the scoring rubric of the thesis itself. Each will return as a green/red judgement on the results slide.
- 75 s

**4. Background & Related Work**
- Optical MoCap (OptiTrack, Vicon) — accurate, costly, markered.
- Monocular pose (OpenPose `[VERIFY]`, MediaPipe, YOLO-Pose) — cheap, no metric depth.
- Multi-view triangulation (Hartley & Zisserman, SVD-DLT) — our geometry core `[VERIFY citation]`.
- Bachelor-team precursor (single-cam launcher) and yessimkhan 2025 omnidirectional launcher.
- Visual: 2×2 comparison table (Cost | Accuracy | Markerless | Closed-loop) across MoCap / Mono / Multi-view / This work.
- Takeaway: Multi-view + YOLO-Pose is the sweet spot for this use case.
- Notes: Keep citations factual. Mark anything not in the thesis bibliography as `[VERIFY]`. The bachelor-team row is essential — it is the direct baseline the panel will compare against.
- 75 s

**5. Proposed System — Engineering First**
- Five stacked layers: Chassis · Electronics · Firmware FSM · Python supervisor · Perception (as a sensor).
- Perception is a *replaceable* sensor module, not the contribution.
- Engineering contribution: safety, real-time control, BOM, integration.
- Visual: [PLACEHOLDER_DIAGRAM_1: five-layer stack diagram, orange arrows showing downward command flow and upward telemetry flow]
- Takeaway: This is an ECE system; CV is one component.
- Notes: This slide re-anchors the defense for the ECE panel. Speak slowly here. Say: "the novelty is in how these layers are glued together, not in any one layer."
- 60 s

**6. Architecture / Pipeline**
- Capture → YOLO ball + YOLO-Pose (TRT FP16) → SVD-DLT triangulation → adaptive EMA → per-joint Kalman → UDP → Python supervisor → ballistic solver → 921 600-baud serial → ESP32 FSM.
- End-to-end latency budget: ~120 ms perception + command, ~80 ms mechanical settling.
- Visual: [PLACEHOLDER_DIAGRAM_2: horizontal pipeline with millisecond labels under each block; orange for data path, gray for telemetry]
- Takeaway: Every stage has a measured latency — no hidden cost.
- Notes: Walk left-to-right without diving in. Promise the panel that accuracy, latency, and safety each get their own slide. This is the map, not the territory.
- 90 s

**7. Hardware Implementation**
- 4× Hikvision DS-E12 USB cameras, 1280 × 720, ~USD 30 each.
- ESP32 (dual-core, 240 MHz, native UART >1 Mbaud) as single MCU.
- 2× NEMA-23 steppers + 1:50 worm-gear reducers (self-locking on power loss).
- DRV8825 pusher driver, counter-rotating BLDC flywheels, hobby servo dispenser.
- 24 V fused rail, normally-closed E-STOP, ISO 13849-1 Cat. 1 stop path.
- Visual: [PLACEHOLDER_SCREENSHOT_3: arena hardware photo, left] + BOM table, right (6 rows, approx USD costs).
- Takeaway: Commodity parts, system-level rigour.
- Notes: Highlight the *single-ESP32* consolidation — this replaced a legacy Arduino+ESP32 bridge and cuts ~80 ms of parsing. Mention the worm-gear self-locking property as a safety feature, not just mechanics.
- 90 s

**8. Software Implementation**
- Perception: YOLO-Pose (17 COCO keypoints) + custom YOLO ball detector, TensorRT FP16.
- Geometry: `triangulate_multi()` SVD-DLT, `robust_triangulate_ball()` iterative outlier rejection.
- Filtering: adaptive EMA + per-joint Kalman (CV model, PN=500, MN=10).
- Supervisor: Python + pyserial, zone/confidence/stability gates, linear GT correction.
- Firmware: `control_12_full.ino`, cooperative FSM, 921 600-baud command set.
- Visual: two-column slide — left: model/framework table; right: short code excerpt of the `set v h wl wr` command from the firmware.
- Takeaway: Every layer has a named, reviewable module.
- Notes: Emphasize the TensorRT FP16 step — it is what makes the 15 FPS target reachable on a single RTX 2080 Ti. Do not dwell on CV internals; the panel is ECE, not CV.
- 75 s

**9. Calibration & Geometry**
- Intrinsics: ChArUco, per-camera, RMS reprojection 0.73 px `[VERIFY]`.
- Extrinsics: 24-tag AprilTag wall + robust PnP-RANSAC, world origin at arena corner.
- World frame: X length, Y width, Z up, all in millimetres.
- `arena_fixed` set owns the current Y-axis convention.
- Protected: `triangulate_multi`, `transform_world_point_y`, `ema_update`.
- Visual: [PLACEHOLDER_DIAGRAM_3: ChArUco pattern top-left; 3D arena plot with 4 camera frusta right]
- Takeaway: Geometry is versioned, auditable, and frozen.
- Notes: State explicitly that 0.73 px RMS is at calibration resolution. If asked about 960×540 mode, redirect to the appendix — resolution changes require intrinsic rescaling.
- 75 s

**10. Methodology & Experiments**
- GT rig: measured static grid + joint-touch protocol.
- Recorded sequences: walk, jog, jump (449 frames × 4 cams × 15 FPS each).
- Ablations: EMA α sweep, adaptive-snap threshold, YOLO-Pose vs MMPose.
- Kalman tuning: process/measurement noise grid on recorded trials.
- Bring-up stages S0–S4 + integrated live test (all PASSED 2026-04-09).
- Visual: experiment matrix table (rows = experiments, columns = inputs/metric/outcome).
- Takeaway: Every claim has a recorded sequence behind it.
- Notes: Emphasize that we used *recorded* sequences for tuning, not live runs — this is why results are reproducible. Mention the bring-up ladder as engineering discipline.
- 90 s

**11. Key Results — Accuracy, Latency, Throughput**
- Ball static (arena_fixed): mean 156.90 mm, P95 288.34 mm, precision (std) 3.09 mm.
- Joint-touch (arena_fixed): mean 178.98 mm, P95 243.77 mm, precision 4.39 mm.
- Bias X+83, Z-125 mm — **correctable** by linear model.
- YOLO-Pose TRT FP16: 6.2 ms/image (6.2× faster than MMPose 38.5 ms).
- End-to-end perception + command: ~120 ms; 15 FPS sustained.
- Visual: `viz_gt_bias_analysis.png` (large, left) + latency bar chart from `viz_speed_comparison.png` (right). Both under `Parallel_working/output/ablation_results/`.
- Takeaway: Sub-200 mm joint accuracy and 6.2× speed-up hit objectives O1+O2.
- Notes: Put the green tick next to O1 and O2 as you speak. Acknowledge the bias up front — do not let the panel catch it.
- 90 s

**12. Analysis & Interpretation**
- Systematic bias (X+83, Z−125) is a fixed offset — a linear correction eliminates it.
- Precision (std 3–4 mm) is excellent → the sensor is *consistent*, only miscalibrated.
- YOLO-Pose reaches <5 mm 3D jitter delta vs MMPose at 6× speed — acceptable trade-off.
- Kalman PN=500, MN=10 gives +47% walk, +34–39% jog, ~neutral jump.
- Visual: `viz_backend_comparison.png` + `viz_gt_joint_errors.png` side by side.
- Takeaway: The error is *calibration-limited*, not *perception-limited*.
- Notes: This is the most important interpretive slide. The panel will push on "179 mm is a lot" — answer that precision is 4 mm and that bias is correctable. The perception is not the bottleneck.
- 75 s

**13. Limitations & Challenges**
- Constant-velocity Kalman ~neutral on jump motion (acceleration-aware model future work).
- Ball exit velocity uncalibrated at 800 RPM — ballistic solver assumes fixed 10 m/s.
- Horizontal stepper backlash ~2° (software-compensated).
- Bounce scenarios: ball outside 3-cam frustum — single-cam fallback (opt-in).
- Bright-sunlight saturation on one camera → graceful degradation to 3-cam triangulation.
- Visual: `viz_ema_ablation_jitter.png` + labelled arrow to the "jump" bar.
- Takeaway: The limitations are bounded, documented, and have a mitigation path.
- Notes: Do not hide limitations. The rubric rewards honest self-assessment. Frame each limitation with its mitigation to close cleanly.
- 60 s

**14. Conclusions & Contributions**
- Six specific MSc contributions: 921 600-baud USB serial migration, single-ESP32 consolidation, closed limit-switch FSM, ±30° software clamp, Python-side RPM gate, live-tuning commands.
- Sub-200 mm joint accuracy at USD ~200 perception: **achieved**.
- Bring-up S0–S4 + integrated fire: **passed** under operator supervision.
- Full codebase, calibration, GT data, and firmware are version-controlled.
- Visual: 6-tile contribution grid (orange numerals 1–6, dark text, warm-fill background).
- Takeaway: An ECE contribution that happens to use CV.
- Notes: Deliver each contribution as a one-sentence engineering fact. No hedging language here.
- 60 s

**15. Future Work + Ethics & Standards**
- Future: RPM→m/s radar-gun calibration; acceleration-aware Kalman; ROS2 migration; HMAC link authentication.
- Standards honored: ISO 12100 (machinery safety), ISO 13849-1 Cat. 1 (stop paths), IEC 60204-1 (control wiring/fusing), ISO 10218-1 (human exclusion).
- Real-world applicability: sports training, rehabilitation, adaptive PE instruction.
- Open-sourcing the perception layer is a near-term plan `[VERIFY]`.
- Visual: 2-column split — left: future roadmap bullets with orange chevrons; right: compliance badges grid.
- Takeaway: The work is extensible and responsibly engineered.
- Notes: Close with the sentence: "Thank you — I am happy to take questions." Do not thank supervisors here; do that verbally off-slide.
- 60 s

### Appendix (4 slides, hidden — unhide live only if a question warrants)

**A1. Live Demo**
- Visual: [PLACEHOLDER_VIDEO_1: arena3d_20260417_123348.mp4, trimmed to 20–30 s]. Source path: `Parallel_working/output/recordings/arena3d_20260417_123348.mp4`.
- Notes: Play if asked for a demo or if a 3–5 min buffer opens. Mute audio.

**A2. 10-Layer Safety Stack**
- Two-column list of layers L1–L10 from `thesis_engineering_chapter.md`: zone, confidence, stability, angle clamp (Py+FW), RPM gate (Py+FW), arm state, typed confirm, hardware E-STOP, link loss, Python exception path.
- Visual: stack diagram, orange at the top (operator), gray at the bottom (hardware).
- Notes: Use if panel asks "what happens if X fails?".

**A3. End-to-End Latency Budget**
- [PLACEHOLDER_TABLE_1: frame-by-frame latency table built from `Parallel_working/output/perf_blm_20260417_134210.jsonl`] Columns: stage, mean ms, p95 ms.
- Notes: Use if panel asks about real-time guarantees.

**A4. ECE Curriculum Mapping**
- 3-column grid: Course → Concept used → Evidence in thesis. Include Signals & Systems, Control Systems, Embedded Systems, Computer Networks, Engineering Ethics.
- Notes: Use only if asked "which courses prepared you for this?".

## Output requirements

1. Emit **one `.pptx` file** with a custom theme that encodes the palette above as the theme's Accent 1 (`#E88B40`), Text 1 (`#1F1F1F`), Background 1 (`#FFFFFF`), and a custom light fill (`#F5F2ED`).
2. Build a master slide with: top-left NU logo placeholder (32 × 32 pt), a 4-pt orange underline under the title text, a soft-gray takeaway bar at the bottom.
3. Appendix slides must be created and then marked **Hidden** so they do not appear in the normal run but remain available via the slide panel.
4. Every slide must have non-empty speaker notes following the bullet rules above.
5. Where the spec says `[PLACEHOLDER_…]`, insert a rectangle sized proportionally to the visual, outlined in `#E88B40` at 2 pt, filled with `#F5F2ED`, and containing the placeholder token as the caption in `#1F1F1F` 14 pt.
6. Do not re-interpret or embellish the numbers, names, or dates in the specification above. If you think a fact is wrong, leave it alone and add `[VERIFY]` to the speaker notes, not to the body.

## Self-check before returning the file

Confirm (in the final assistant message, not in the deck) that all of the following are true:
- [ ] Exactly 15 visible slides + 4 hidden appendix slides = 19 total.
- [ ] Every visible slide has a title, a 22-pt message line, a visual or bullet block, a soft-gray takeaway bar, and speaker notes ≥ 50 words.
- [ ] The theme colour "Accent 1" is `#E88B40` exactly (RGB 232, 139, 64).
- [ ] No emojis, no clipart, no stock photos, no gradients anywhere.
- [ ] Every `[PLACEHOLDER_…]`, `[VERIFY]`, `[FILL ME]`, and `[MISSING EVIDENCE]` token is preserved verbatim.
- [ ] Total estimated speaking time (sum of the per-slide budgets above) is between 15 and 20 minutes.
- [ ] Appendix slides are marked Hidden.

Return the `.pptx` and the self-check report. Do not ask clarifying questions — if a fact is missing, use the placeholder conventions above.

---
