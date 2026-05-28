# MSc Defense Deck Revision — Design

**Date:** 2026-04-27
**Owner:** Arlen Smagulov (Hanush)
**Source deck:** `thesis_defense_presentation/thesis_defense_final.pptx` (22 slides)
**Output deck:** `thesis_defense_presentation/thesis_defense_final_revised.pptx`
**Drivers:** GLM committee report (`MSc_Defense_Committee_Evaluation_Report.pdf`) and Gemini 3.1 Pro review (`gemini3.1pro review.txt`); thesis source of truth is `latex_revised/Master_Thesis_3_revised/`.

## 1. Goal

Apply slide-level corrections that close the gap between the deck and the manuscript so the oral defense lands at the **75 %+ pass threshold** instead of the simulated 52.84 %. Changes are **wording, numbers, table cells, and two appendix asset embeds** — no template, master, palette, logo, or font changes.

## 2. Hard constraints

1. **Preserve the NU brown template, NU logo, SEDS logo, master slide, fonts, and palette** verbatim. Do not edit slide masters, theme XML, or layout placeholders. Only edit text-frame contents, table cell contents, and add two media items inside existing placeholder shapes.
2. **No new factual claims** beyond what is already in `latex_revised/Master_Thesis_3_revised/chapters/chapter{1..6}.tex`. Every number on every slide must be traceable to a thesis section, table, or figure.
3. **Original `thesis_defense_final.pptx` is untouched.** All edits land in `thesis_defense_final_revised.pptx`. The original is the rollback point; the lock file in LibreOffice does not block this.
4. **No closed-loop / full-autonomy claims** anywhere on the deck. Replace with "aim-only + controlled single-shot" in line with thesis Sec 1.3 / 5.11.
5. **Geometry, calibration, and safety architecture are not redesigned.** This task is a presentation pass over an already-frozen thesis.

## 3. Scope (B+ from brainstorming)

Touches 12 of 22 slides, plus 1 new hidden appendix slide.

### 3.1 Per-slide change matrix

| # | Slide | Change class | Action |
|---|---|---|---|
| 1 | Title | Footer name only | Footer text frame `Hanush · MSc ECE · Nazarbayev University` → `Arlen Smagulov · MSc ECE · Nazarbayev University`. Title, subtitle, logos, layout untouched. |
| 2 | Motivation | Add evidence | Add 2 inline reference markers (`[OptiTrack]`, `[Lobster]`) on the bullet block. Source: thesis Sec 1.1 / 2.1. No image changes. |
| 3 | Problem & Objectives | Soften claim | Takeaway rewritten: "RQ1/RQ2 met; RQ3/RQ4 satisfied for static + controlled live-aim only — moving-target firing is the unvalidated boundary (Sec 1.3, 6.4)." |
| 4 | Background table | Column rename + cell rewrite | Column header `Closed-loop` → `Live-aim closed loop`. "This work" cell `Static/live-aim validated` → `Aim + controlled single-shot validated`. |
| 5 | Six contributions | Drop overclaim, add refs | Card 01 strapline: drop "closed-loop"; replace with "Markerless live-aim, commodity hardware (Sec 5.9)". Each card gains a Sec/Table reference suffix. |
| 8 | Hardware | Cost honesty | Headline: `under USD 200` → `≈USD 358 total; perception ≈USD 120 (Sec 3.2, Table 3.2)`. Cost table gets a final **Total ≈USD 358** row. Add bullet: "AprilTag fiducials on walls for extrinsic calibration (Sec 3.5)". |
| 9 | Software | De-clutter | Move firmware `handle_set()` excerpt off this slide. Add two missing pipeline rows: *"Robust ball: iterative reprojection-error rejection (Sec 3.7.2)"* and *"Filter: adaptive EMA + CV Kalman (Sec 5.7)"*. |
| 10 | Calibration | Add numbers | Add bullets: Intrinsic reproj **2–8 px** (Sec 5.1); Extrinsic RMSE **3–7 px**, **8–15 %** outlier corner rejection (Sec 5.2); PnP + RANSAC + σ=2.0 sigma-clipping (Sec 3.5.2); Overlay validation **5–10 px** across all 4 cams (Sec 5.2). |
| 11 | Methodology | Tighten metrics | Replace "3D trajectory verified" with explicit dynamic-clip pass criteria from Sec 4.3: *<800 mm frame-to-frame jumps for slow*, *motion-blur stress for fast*, *near-zero false-positive for no-ball*. Bias-correction row → *"Raw 150.77 mm → corrected 95.17 mm (Fig 5.1)"*. Append note: *"Bias correction fitted in-sample on the same 36-pt set (Sec 4.4.2, 6.3)"*. |
| 12 | Key Results | Add P95 + raw/corrected | New mini-row of P95 numbers: **Ball P95 166.51 mm · Joint P95 198.73 mm · per-joint P95 171 / 172 / 200 mm** (Tables 5.1, 5.2, 5.3). New raw→corrected callout box: **150.77 → 95.17 mm**. Subtitle adjusted: "All thresholds met within validated static / live-aim scope." |
| 13 | Limitations | Expand 1 → 6 bullets | (1) closed-loop firing at moving subject UNVALIDATED (Sec 1.3, 6.3); (2) in-sample bias correction (Sec 4.4.2, 6.3); (3) **19 / 81 joint-touch invalid (23.5 %)** due to occlusion (Sec 5.4); (4) RPM→velocity not empirically calibrated (Sec 5.9, 6.4.3); (5) single-person, single-arena, indoor-only (Sec 6.3); (6) CV Kalman neutral on jump motion (Sec 5.7). |
| 14 | Conclusions | Drop overclaim, add disadvantages | Card 1 strapline: drop "closed-loop". C2 → "4 USB cameras, ≈USD 120 perception / ≈USD 358 total". Add a "Disadvantages" line (handbook criterion 7): *"In-sample bias fit · 3-camera occlusion floor · RPM→velocity not yet calibrated"*. |
| 15 | Future Work + Ethics | Dual-use + standards how | Add a **Dual-use** bullet quoting Sec 6.5: *"A system capable of autonomously tracking human body parts and directing a projectile has obvious dual-use potential beyond sports training; the safety architecture (operator presence, hardware E-STOP, exclusion zone, six-stage protocol) is the necessary safeguard."* Replace the bare ISO list with one-line *how* per row: ISO 13849-1 → NC E-STOP = Cat-1 stop (L8); IEC 60204-1 → 24V/50A fuse, single star-point ground; ISO 10218-1 → operator-only zone; ISO 12100 → L1–L10 hazard map. |
| 16 | A1 Live demo | Embed media | Replace the literal `[PLACEHOLDER_VIDEO_1: …]` text with an embedded video shape pointing at `thesis_defense_presentation/IMG_1589 (online-video-cutter.com).mp4`. If `python-pptx` `add_movie` fails, fall back to a poster image with a visible note "Video file: IMG_1589 (online-video-cutter.com).mp4 — drag in via LibreOffice". |
| 18 | A3 Latency | Build real table | Replace the literal `[PLACEHOLDER_TABLE_1: …]` text with a 3-column table built from `Parallel_working/output/perf_blm_20260409_133818.jsonl` (newest perf log on disk). Columns: **Stage / Mean ms / P95 ms** over fields `capture_ms, ball_ms, pose_ms, triang_ms, udp_ms, viz3d_ms, total_ms, end_to_end_ms`. Caption notes the file and frame count. |
| **NEW A5** | Firmware excerpt (hidden appendix) | Add slide | Hidden appendix slide titled "A5 · Firmware command excerpt" carrying the `handle_set()` block that left slide 9. Same template, same SEDS footer, same `APPENDIX` corner label. |

### 3.2 Slides explicitly **not** changed

S6 (Pose-to-Aim integration figure), S7 (architecture figure), S17 (10-layer safety stack — already comprehensive), S19 (ECE curriculum mapping), S20–S22 (Q&A backup) are left as-is. S1 is touched only for the footer name fix in §3.1.

## 4. Tooling and file handling

- **Library:** `python-pptx` (already in `venv/`) for all text and table edits; raw `lxml` only if `add_movie` requires it for slide 16.
- **Working file:** `thesis_defense_presentation/thesis_defense_final_revised.pptx`. Original preserved. The LibreOffice lock on the original is a non-issue because the revised file is a separate path.
- **Helpers:** a single `scripts/revise_defense_deck.py` (new) that opens the original, applies every change in §3.1 sequentially, and writes the revised file. The script is idempotent (re-running produces the same output) and prints a per-slide diff summary.
- **Asset paths used:**
  - Demo video: `thesis_defense_presentation/IMG_1589 (online-video-cutter.com).mp4`
  - Latency JSONL: `Parallel_working/output/perf_blm_20260409_133818.jsonl`
  - Source-of-truth thesis: `latex_revised/Master_Thesis_3_revised/chapters/chapter{1..6}.tex`
  - Navigation indices to consult during plan execution: `CLAUDE.md`, `latex_revised/Master_Thesis_3_revised/REVISION_NOTES.md`, `latex_revised/Master_Thesis_3_revised/EVALUATOR_RESPONSE.md`, `latex_revised/Master_Thesis_3_revised/README.txt`.

## 5. Source-of-truth numbers (frozen for this revision)

All numbers below come from the manuscript chapter files. Any slide cell quoting one of these uses the value below verbatim.

| Symbol | Value | Thesis source |
|---|---|---|
| Ball mean | 95.17 mm | Table 5.1 |
| Ball P95 | 166.51 mm | Table 5.1 |
| Ball raw mean | 150.77 mm | Sec 5.3, Fig 5.1 |
| Ball raw P95 | 288.34 mm | Sec 5.3 |
| Per-axis raw bias (X / Y / Z) | +50.7 / +46.6 / −107.0 mm | Sec 5.3 |
| Temporal precision (mean / P95) | 3.79 / 8.51 mm | Table 5.1 |
| Joint mean | 143.38 mm | Table 5.2 |
| Joint P95 | 198.73 mm | Table 5.2 |
| Joint trial validity | 62 / 81 = 76.5 % | Table 5.2, Sec 5.4 |
| Per-joint mean (knee / hip / shoulder) | 110.0 / 150.4 / 164.4 mm | Table 5.3 |
| Per-joint P95 (knee / hip / shoulder) | 171 / 172 / 200 mm | Table 5.3 |
| Intrinsic reproj | 2–8 px | Sec 5.1 |
| Extrinsic RMSE | 3–7 px after 8–15 % outlier rejection | Sec 5.2 |
| Overlay validation | 5–10 px | Sec 5.2 |
| YOLO-Pose latency | 6.2 ms / 4-cam batch (TRT FP16) | Sec 5.6 |
| MMPose reference latency | 38.5 ms / image | Sec 5.6 |
| Pipeline budget | 67 ms (15 FPS); ≈15 ms compute → 52 ms headroom | Sec 3.3 |
| E-STOP latch | <100 ms | Sec 3.14.3 |
| Six-stage protocol | S0–S4 passed 2026-04-09 | Sec 3.14.3, Appendix A |
| Cost (perception / total BLM) | ≈USD 120 / ≈USD 358 | Sec 3.2, Table 3.2 |

The GLM report rounds slightly differently (e.g. it cited Y bias as +14 mm rather than the thesis's +47 mm); **the thesis values above win** wherever the two disagree.

## 6. Verification plan

After the revise script runs:

1. **Programmatic check** (same script, post-write): re-open the revised pptx and assert
   - no slide text contains the literal substring `[PLACEHOLDER_`,
   - no slide text contains the words `closed-loop` *unless* it appears in the row label "Live-aim closed loop" or in a quoted limitation,
   - the 12 critical strings appear at least once each in the deck: `150.77`, `166.51`, `198.73`, `≈USD 358`, `≈USD 120`, `Dual-use`, `in-sample`, `ISO 13849-1`, `NC E-STOP`, `2–8 px`, `3–7 px`, `Arlen Smagulov`,
   - the slide count is 23 (was 22; +1 for new A5),
   - slides 16, 17, 18, 19, A5 remain marked hidden.
2. **PDF render** via `libreoffice --headless --convert-to pdf` of the revised pptx into the same folder. The PDF path is printed so the user can flip through it before defense.
3. **Manual eyeball gate** (user, in LibreOffice): confirm the NU brown master, NU logo, SEDS logo, fonts, palette, and footer chrome are all unchanged versus the original.

## 7. Out of scope (deferred)

- Any change to slide master, theme XML, palette, fonts, logos, or footer chrome.
- Any change to the figures embedded on slides 6, 7, 10, 12, 13 (architecture, calibration, results scatter, joint boxplot).
- Recording new perf data or a new demo clip — only the existing files are used.
- Editing the manuscript (`latex_revised/`).
- Anything in `Parallel_working/`, `garage_lab_combined/`, `arena_fixed/`, or BLM firmware.

## 8. Risks

| Risk | Mitigation |
|---|---|
| `python-pptx` `add_movie` produces an unviewable shape on slide 16 | Fall back to a poster image + on-slide note; user drags video in via LibreOffice (one click). |
| Editing a table cell drops its style | Each table edit reads existing run formatting and re-applies it; do not call `cell.text = …`, instead replace runs in-place. |
| New A5 appendix slide picks the wrong layout and loses the NU template | Duplicate slide 19's layout (existing appendix slide) as the source layout for A5. |
| Footer/master text accidentally edited | Script touches only `slide.shapes` text frames whose `name` does not match the master/layout placeholder set; logos and bottom-bar shapes are skipped by name. |
| Slide hidden flag accidentally cleared on an appendix slide | Script reads `show=False` before edit and re-asserts it after edit on slides 16–19 and the new A5. |

## 9. Acceptance criteria

The revision is complete when:

1. All 13 rows of §3.1 are reflected in the revised deck.
2. The verification checks in §6 all pass.
3. Eyeballing the revised deck in LibreOffice shows no template / logo / palette regression versus the original.
4. The revised deck is committed to git on a fresh commit alongside this design doc.
