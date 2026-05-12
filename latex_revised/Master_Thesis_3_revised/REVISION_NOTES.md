# Revision Notes — Master_Thesis_3_revised

This file accompanies the revised LaTeX project. It summarises (a) how each evaluator comment was addressed and (b) the section-by-section changes made on top of the original `latex_old_version/Master_Thesis_3_/` baseline.

The goal of the revision is two-fold: respond to the evaluator's three written comments, and incorporate the substantial post-submission engineering and validation work (YOLO-Pose backend, TensorRT FP16 deployment, Kalman-prediction tuning, ball-detection robustness layer, BLM firmware control_12 with single-MCU 921 600 baud architecture, integrated live test on three named joints 2026-04-09, multi-modal Vosk voice integration). All numerical anchors from the original thesis (95.17 mm ball, 143.38 mm joint, all per-joint figures, the linear correction model, the 36-trial and 81-trial ground-truth tables) are preserved verbatim; new content is additive and is honestly framed as partial validation where the underlying experiment has not yet reached the moving-target closed-loop firing regime.

---

## How each evaluator comment was addressed

### Evaluator Comment 1 — "Literature review not sufficiently critical; compare with closest existing systems and justify design choices"

Addressed in Chapter 2 (Literature Review and Background Theory):

1. **§2.7 expanded with two new subsections**: "Why the observed accuracy gap is acceptable" and "Design-choice justification". The first explicitly acknowledges that this work's 95 mm ball / 143 mm joint figures are worse than Category-B motion capture (sub-mm) and Category-C ball-only research (50-100 mm), and explains why the combined capability-cost envelope (joint targeting + closed-loop actuation at commodity cost) is the novelty rather than point-wise accuracy. The second subsection ties each major design decision (4 commodity USB cameras vs stereo/depth, ChArUco+AprilTag vs SLAM, DLT/SVD vs bundle adjustment, YOLO-Pose primary with MMPose reference, CV Kalman, 3-cam minimum for joints, ESP32 single-MCU 921 600 baud, voice via UDP IPC) to the limitation of the analogue it replaces.
2. **Three new sub-topics added** to Chapter 2 itself: real-time pose estimation under edge-deployment constraints (§2.4 sub-section grounds YOLO-Pose), Kalman filtering for sports/human-motion tracking (§2.5 grounds the predictive layer), and voice-command interfaces in HRI (§2.7 grounds the Vosk integration). These new sub-topics use four newly-added citations (YOLO-Pose, NVIDIA TensorRT, Kalman 1960, Bar-Shalom) plus existing ones; the pre-existing reference set is unchanged in numbering.
3. **Research-gap statement** at the end of §2.7 is rewritten to combine the prior gap with the explicit partial-validation caveat (the closed-loop moving-target regime is identified as future work).

### Evaluator Comment 2 — "Evaluation is partial, not a complete demonstration; conclusions should be carefully framed"

Addressed throughout, with the partial-validation framing applied at every overclaim surface:

1. **Abstract** (frontmatter/abstract.tex) rewritten to open with an explicit "strong but partial validation" sentence, and to enumerate exactly what was and was not validated.
2. **§1.4 Novelty Claims** rewritten with each of the four claims carrying an explicit scope qualifier tying it to the validation regime actually achieved (aim-only, controlled live-aim single-shot fire on named joints, voice-bridge wiring in dry-run / aim-only). Closed-loop moving-target firing is consistently identified as future work in every claim where the boundary applies.
3. **§2.7 Research Gap** appends an explicit clause acknowledging that the validation regime is static + aim-only + controlled fire, with closed-loop moving-target validation as future work.
4. **§5 Chapter 5 opener** has a new "Scope of Validation" preamble paragraph that explicitly enumerates validated regimes and the unvalidated boundary.
5. **§5.3 line "Both acceptance criteria are met"** softened to "the two principal acceptance thresholds defined in §4.4 are satisfied for the static ball-localisation task" with an explicit reminder that the bias parameters were fitted in-sample.
6. **§6.1 Contribution 1 body** carries a "within the validation regimes reached in this thesis" clause and explicitly identifies the moving-target closed-loop regime as future work.
7. **§6.2 Table 6.1** updated: RQ1 and RQ2 stay "Satisfied" (those are the static-perception regimes within their own thresholds); RQ3 moves from "Partial" to "Satisfied within static / live-aim regime; moving-target firing pending"; new RQ4 row for the voice-bridge wiring marked "Satisfied for wiring; closed-loop voice firing pending".
8. **§6.3 Limitations** explicitly retains and strengthens the "closed-loop firing on a moving subject" bullet, adds an "in-sample bias-correction fitting" bullet, an "RPM-to-velocity calibration pending" bullet, and a "constant-velocity assumption on jump motion" bullet.
9. **§6.4 Future Work** opens with the closed-loop-firing + RPM-calibration milestone as the most urgent item, explicitly framed as the unvalidated boundary.

### Evaluator Comment 3 — "Awkward phrasing, grammar, repetition; substantial language polishing"

Addressed by surgical sentence-level rewrites across all chapters and frontmatter. Specific defects fixed:

- Acknowledgements: "show his best thanks…from the bottom of his heart" → formal academic phrasing.
- §1.1: "The reason is obvious", "The athlete has to be in the planned sequence of movements of the simulator" → idiomatic English.
- §1.4 Novelty Claim 1: "They determine this by observing the athlete" (subject-verb disagreement; the launcher is singular) and "uses the ball launcher themselves as the target" (nonsensical pronoun) → rewritten.
- §3 throughout: passive-voice chains tightened; section title "Why This Is Non-Trivial" replaced by "Why Real-Time Targeting Is Non-Trivial".
- §6.5: "The authors comment on this and underpin that" (single-author thesis, wrong verb) → "The author acknowledges this and emphasises that".
- Recurring patterns (e.g. "is being dealt with in this paper", "which means that", "both of the main acceptance criteria") tightened or removed throughout.

The polish pass is surgical: clean prose was left alone to avoid introducing inconsistency.

---

## Section-by-section changelog

### Frontmatter

- **`frontmatter/abstract.tex`** — fully rewritten (~350 words). New three-paragraph structure: scope + partial-validation framing; technical pipeline summary including YOLO-Pose / TRT / Kalman / voice bridge; quantitative results + S0-S4 + integrated live test reference + explicit unvalidated boundary.
- **`frontmatter/acknowledgements.tex`** — rewritten in formal academic register; adds explicit acknowledgement of TensorRT and the colleagues who participated in bring-up.
- **`frontmatter/abbreviations.tex`** — extended from ~17 to ~33 entries. New entries cover post-submission terms: ASR, BLDC, BLE, CV (Kalman model), DRV8825, ESC, FOV, FSM, FP16, IPC, ISR, JSONL, KF, NEMA-23, PWM, TRT, UART, USB, Vosk, YOLO-Pose, plus the symbols v0, g, F/H/Q/R_KF/P used in the new Kalman section.
- **`frontmatter/declaration.tex`** — unchanged.

### Chapter 1 — Introduction

- **§1.1 Motivation** — language polish; colloquialisms removed; statement of accessibility gap tightened. No structural change.
- **§1.2 Research Objectives** — expanded from three to four research questions. Original RQ1 (ball static accuracy) and RQ2 (joint accuracy) kept verbatim. RQ3 reframed to cover the integration protocol explicitly, including the controlled live test. New RQ4 covers the multi-modal voice-bridge wiring, demarcated to wiring + dry-run + aim-only.
- **§1.3 Scope and Constraints** — hardware list updated to include ESP32 single-MCU + 921 600 baud + TensorRT + Vosk; subject still single-person; integration scope expanded to "aim-only + live-aim + controlled single-shot trials including integrated live test"; explicit identification of moving-target firing as future work.
- **§1.4 Novelty Claims** — expanded from three to four claims. Claims 1, 2, 3 retain their original assertions but are reframed with scope qualifiers; new Claim 4 covers the multi-modal voice + auto-reload training-mode interface.
- **§1.5 Thesis Structure** — updated to match the expanded chapter content (notes the seven literature topics in Ch 2; the additional methodology sections in Ch 3; the new protocol sections in Ch 4; the new results sections in Ch 5).

### Chapter 2 — Literature Review

- **§§2.1–2.3** — language polish; substance unchanged.
- **§2.3** — short paragraph added on TensorRT FP16 deployment with dynamic batch and the practical reason for it.
- **§2.4 Pose Estimation** — kept; added new sub-section "Real-time pose estimation under edge-deployment constraints" introducing YOLO-Pose, the latency rationale, and the position of MMPose as a reference back-end.
- **§2.5 NEW — Kalman Filtering for Sports and Human-Motion Tracking** — new section grounding the Kalman work, with the CV-model assumption and its known failure mode on jump motion called out explicitly.
- **§2.6 Ballistic Modelling** — language polish; inline note that aerodynamic drag and Magnus effects are absorbed into the empirical correction model rather than modelled explicitly.
- **§2.7 NEW — Voice-Command Interfaces in HRI** — short section grounding the Vosk integration choice and the rationale for running ASR in a separate process via UDP.
- **§2.8 Safety in Autonomous Actuated Systems** — extended with explicit ISO 13849-1 and IEC 60204-1 references for the safety-architecture mapping in Chapter 3.
- **§2.9 Summary, Critical Comparison, and Research Gap** — Table 2.1 retained; existing per-category paragraphs polished; **two new subsections added**: "Why the observed accuracy gap is acceptable" and "Design-choice justification". The bold research-gap sentence is rewritten with the partial-validation caveat appended.

(Note: the section numbering is preserved at the document level by `nuthesis.cls`; subsection insertions are within existing top-level §2.7 and renumber the chapter automatically.)

### Chapter 3 — System Design and Methodology (largest expansion)

- **§3.1 Arena Setup** — unchanged.
- **§3.2 Hardware Architecture** — substantially expanded with mechanical (gimbal, worm-gear self-locking, flywheel pair, DRV8825 pusher with thermal management, limit-switch polarity rationale) and power (24 V motor rail per IEC 60204-1, single-star ground topology, hardware E-STOP). ESP32 selection justified explicitly against Arduino UNO. Table 3.2 (BLM command set) extended to include `info`, `jv`/`jh`/`jf`/`js`, `jsset`/`jfspeedset`/`jfaccelset` with category column.
- **§3.3 Software Architecture** — pipeline expanded to eight stages, including the smoothing+prediction stage and the safety-gating stage.
- **§§3.4–3.6** — calibration and synchronisation sections retained with minor language polish.
- **§3.7 3D Triangulation** — extended with three new subsections: "Robust Ball Triangulation" (iterative reprojection rejection plus the new candidate-selection gates: max-side, min-side, KF-distance), "Single-Camera Geometric Fallback" (ray-to-Z-plane intersection, flag-guarded, ball-only), and updates to Quality Filtering (adaptive EMA snap behaviour).
- **§3.8 Ballistic Solver** — equations preserved verbatim; "Why This Is Non-Trivial" renamed to "Why Real-Time Targeting Is Non-Trivial" and the prose tightened. RPM-to-velocity calibration explicitly identified as pending future work.
- **§3.9 NEW — Predictive Tracking with a Kalman Filter** — full presentation of the per-joint and per-ball CV Kalman filter: state, transition, measurement, predict-ahead, the per-task tuning (q=500/r=10 for joints; q=800/r=25 for ball), max-physical-speed gate, coast-through-drop window, and the predictive-payload UDP semantics.
- **§3.10 NEW — BLM Firmware: control_12_full.ino** — FSM diagram (IDLE → RETRACTING → DISPENSING; IDLE → SHOOTING with RPM gate), firmware-level interlocks (RPM gate, angle clamp, pusher-enable thermal discipline), telemetry suppression rationale.
- **§3.11 NEW — Communication Stack** — physical/link layer (USB 921 600 ASCII), rationale for USB-serial primary vs BLE backup, two UDP channels (5005 launcher targets, 5006 voice bridge), JSONL decision-log schema.
- **§3.12 NEW — Multi-Modal Voice-Command Integration** — Vosk grammar (16 phrases mapped to COCO joints + control verbs), UDP IPC isolation rationale, auto-reload mode for rapid-fire training, explicit note that all voice paths are behind the same safety gates as keyboard input.
- **§3.13 NEW — Ball Detection Robustness** — three flag-guarded gates (max-box-side, min-box-side, KF-distance), input-image-size lever (672 default, 960 option for bounce), explicit reference to the offline analyzer and the regenerated mosaic visualisation.
- **§3.14 (renumbered) Safety Architecture** — extended into the layered-interlocks L1-L10 enumeration, ISO/IEC standards alignment, and the six-stage integration checklist summary referring forward to Appendix A.

### Chapter 4 — Ground-Truth Evaluation Protocols

- **§§4.1–4.4** — preserved verbatim except for whitespace/formatting normalisation. The 36-point ball static dataset, the 81-trial joint-touch dataset, the dynamic validation clips, and the bias-correction model are the evaluator's numerical anchors and are left as-is.
- **§4.5 NEW — Pose Backend Ablation Protocol** — three motion sequences (walk, jog, jump), 449 frames × 4 cameras, cached 2D keypoints fed through the same DLT/SVD pipeline; metrics: per-sequence detection rate, per-image and batched inference latency, 3D jitter difference.
- **§4.6 NEW — Kalman Prediction Tuning Protocol** — q × r × Δt_pred grid; pass criterion is positive percentage improvement over the naive baseline.
- **§4.7 NEW — Ball Detection Analyser Protocol** — confidence + image-size sweep on per-camera frames or four-camera tiled mosaics; complementary mosaic-renderer that overlays the analyzer's bounding boxes back on the tiled video for visual false-positive/negative inspection.
- **§4.8 NEW — BLM Integration Protocol** — summary of the six-stage protocol with explicit pass criteria for S0, S1, S2, S3, S4, S5, S6; explicit identification of the moving-target regime (S5/S6 in motion) as future work.

### Chapter 5 — Results and Analysis

- **NEW § Scope of Validation** — preamble at the chapter top enumerating the validated regimes and the unvalidated moving-target boundary; restates the in-sample-fitting limitation.
- **§§5.1–5.5** — preserved verbatim including all numerical anchors (95.17 mm, 102.23 mm RMSE, 166.51 mm P95; 143.38 mm joint mean, 198.73 mm P95; 110.03 / 150.38 / 164.38 mm per-joint; bias X +50.68 / Y +46.57 / Z −106.98). Soft-language change in §5.3: "Both acceptance criteria are met" → "the two principal acceptance thresholds defined in §4.4 are satisfied for the static ball-localisation task".
- **§5.6 NEW — YOLO-Pose vs MMPose Backend Ablation** — 6.2× live and 3.6× offline speed-up; 3D jitter within 5 mm; per-camera detection rate within 6 pp on frontal views, ~6 pp lower on most oblique views. TODO marker for the export plot from `Parallel_working/output/ablation_results/`.
- **§5.7 NEW — Kalman Prediction Tuning Results** — q=500 / r=10 / horizon 400 ms; ~47% walk improvement, 34-39% jog improvement, neutral on jump (CV limitation). TODO marker for the prediction-results plot.
- **§5.8 NEW — Ball Detection Robustness Improvements** — model upgrade (74.9% → 84.2% jump detection); imgsz 672 → 960 (camNorth bounce 58% → 98% at +8 ms latency); candidate-selection gates eliminate person-as-ball, marker/cone false positives; safe to lower conf 0.40 → 0.25 with gates on. TODO marker for the bounce/fast/slow plots.
- **§5.9 NEW — Integrated Live Test (2026-04-09)** — left_shoulder, right_knee, nose results; explicit description of nose-shot deviation attributed to RPM-to-velocity calibration; E-STOP latch < 100 ms verified three times during the session; JSONL log archived. TODO marker for the test photograph.
- **§5.10 NEW — Multi-Modal Voice-Command Wiring Validation** — 16-phrase grammar exercised in dry-run + aim-only; no safety-gate bypass observed; closed-loop voice firing on a moving subject identified as future work. TODO marker for the voice-bridge block diagram.
- **§5.11 NEW — Summary of Validated and Unvalidated Regimes** — explicit closing summary listing the eight validated regimes and the one unvalidated boundary.

### Chapter 6 — Conclusions and Future Work

- **§6.1 Summary of Contributions** — expanded from three to four contributions, mirroring §1.4. Opening paragraph reframes the chapter as a partial validation with explicit enumeration of what was demonstrated end-to-end.
- **§6.2 Objectives Achievement** — RQ1 / RQ2 unchanged; RQ3 status updated to "Satisfied within static / live-aim regime; moving-target firing pending"; new RQ4 row "Satisfied for wiring; closed-loop voice firing pending". Table 6.1 updated to four rows.
- **§6.3 Limitations** — kept all original limitations; added "in-sample bias-correction fitting", "closed-loop firing on a moving subject", "RPM-to-velocity calibration pending", "constant-velocity assumption on jump motion".
- **§6.4 Future Work** — opening section now combines closed-loop moving-target firing and the empirical RPM-to-velocity calibration as the two most urgent items. Predictive lead-time compensation moved up. SLAM, multi-person, held-out evaluation, and Virtual 3D Goal sections retained.
- **§6.5 Professional / Ethical** — language polish ("The authors comment on this and underpin" rewritten); substance unchanged.

### Backmatter

- **`backmatter/appendix_a.tex`** — Status column added to the six-stage integration checklist table; every row marked Passed 2026-04-09 (S0.1 through S5.3) or Pending (moving target) (S6.1, S6.3) or Passed for cycles run (S6.2). Preamble extended with explicit reference to the integrated live test on three named joints.
- **`backmatter/appendix_b.tex`** — preserved verbatim (canonical script invocation listings).
- **`backmatter/appendix_c.tex`** — preserved verbatim (full ground-truth grids).
- **`backmatter/appendix_d.tex`** — preserved verbatim (calibration figures).
- **`backmatter/appendix_e.tex`** — preserved verbatim (YOLO ball training results).
- **`backmatter/appendix_f.tex`** — preserved verbatim (smoke-test frames).
- **`backmatter/appendix_g.tex`** — NEW. Two reference tables: full BLM firmware command map (Table G.1) and the voice-bridge grammar (Table G.2). Wired into `main.tex` after `appendix_f`.

### `references.bib`

- Original 36 entries preserved verbatim with original keys (`ref1` … `ref36`); none are renumbered or removed.
- 12 new entries appended (`ref37_yolopose` … `ref48_voice_hri`):
  - `ref37_yolopose` (Maji et al. 2022) — YOLO-Pose paper.
  - `ref38_tensorrt` (NVIDIA) — TensorRT Developer Guide.
  - `ref39_kalman1960` (Kalman 1960) — original Kalman filter paper.
  - `ref40_baryam_kf` (Bar-Shalom et al. 2001) — Estimation with Applications to Tracking.
  - `ref41_vosk` (Alpha Cephei) — Vosk offline ASR.
  - `ref42_drv8825` (TI) — DRV8825 datasheet.
  - `ref43_esp32` (Espressif) — ESP32 datasheet.
  - `ref44_iso13849` (ISO) — ISO 13849-1.
  - `ref45_iec60204` (IEC) — IEC 60204-1.
  - `ref46_charuco_aruco` (Garrido-Jurado et al. 2016) — Mixed-integer ArUco generation.
  - `ref47_pose_review` (Zheng et al. 2023) — Deep-learning pose-estimation survey.
  - `ref48_voice_hri` (Stiefelhagen et al. 2007) — Multi-modal HRI on a humanoid.

### `main.tex`

- Single-line addition: `\input{backmatter/appendix_g}` after `appendix_f`. The preamble, frontmatter wiring, chapter wiring, bibliography wiring, and `\appendix` directive are unchanged.

### Built artefacts

- The build artefacts (`.aux`, `.log`, `.toc`, `.lof`, `.lot`, `.bbl`, `.blg`, `.out`) from the original folder are removed in the revised copy. Overleaf will regenerate these on the first compile.

---

## What is *not* changed

- Chapter / section / table / figure / equation numbering at the top level. Subsection insertions in §2.7, §3.7, and §6.4 are within existing parents and renumber automatically.
- Existing reference keys `ref1` … `ref36`. New entries are appended with named keys (`ref37_yolopose` …) so no existing `\cite` invocation breaks.
- `nuthesis.cls`, `nu_logo.png`, the existing `figures/` directory, the title page macro.
- All preserved numerical anchors (per the verification checks at the bottom of this document).

---

## Verification commands

The user can spot-check the revision against the original by running, from the repo root:

```bash
# Numerical anchors preserved
diff <(grep -hroE '[0-9]+\.[0-9]+~?mm|[0-9]+\.[0-9]+ mm' latex_old_version/Master_Thesis_3_/chapters/ latex_old_version/Master_Thesis_3_/frontmatter/ | sort -u) \
     <(grep -hroE '[0-9]+\.[0-9]+~?mm|[0-9]+\.[0-9]+ mm' latex_revised/Master_Thesis_3_revised/chapters/ latex_revised/Master_Thesis_3_revised/frontmatter/ | sort -u)
# Old anchors should be a subset of new (only additions allowed)

# Cite keys: revised set should be a superset of old
diff <(grep -hroE '\\cite\{[^}]+\}' latex_old_version/Master_Thesis_3_/ | sort -u) \
     <(grep -hroE '\\cite\{[^}]+\}' latex_revised/Master_Thesis_3_revised/ | sort -u)

# Brace balance per file
for f in latex_revised/Master_Thesis_3_revised/chapters/*.tex; do
  echo "$f: open=$(tr -cd '{' < "$f" | wc -c) close=$(tr -cd '}' < "$f" | wc -c)"
done
```

For the Overleaf build itself, see `README.txt`.
