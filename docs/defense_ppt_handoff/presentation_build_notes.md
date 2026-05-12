# Presentation Build Notes — Windows Laptop Procedure

Step-by-step guide to go from the handoff package on this Linux workstation to a finished `.pptx` on your Windows laptop, using **Claude in PowerPoint** (Microsoft 365 Copilot Claude connector, or the Claude desktop app with the PowerPoint plugin).

---

## 0. Before you start

- Have `defense_ppt_handoff_prompt.md`, `slide_plan.md`, `assets_checklist.md`, `qa_bank.md`, and this file on the Windows laptop (either via USB stick, OneDrive, or `git pull`).
- Have the `defense_assets/` folder described in `assets_checklist.md` §5 on the same laptop.
- Have PowerPoint 2021 or Microsoft 365 Desktop installed.
- Have Claude enabled inside PowerPoint (either via Microsoft Copilot or the Claude plugin). Confirm the chat pane opens and responds before pasting the prompt.

---

## 1. Copy the handoff package to Windows

From this Linux machine, package everything into one folder:

```bash
cd /home/hanush/Desktop/Project_Cam
tar czf defense_handoff.tar.gz \
    docs/defense_ppt_handoff/ \
    Parallel_working/output/recordings/arena3d_20260417_123348.mp4 \
    Parallel_working/output/recordings/mosaic2d_20260415_132441_slow.mp4 \
    Parallel_working/output/ablation_results/viz_gt_bias_analysis.png \
    Parallel_working/output/ablation_results/viz_gt_joint_errors.png \
    Parallel_working/output/ablation_results/viz_backend_comparison.png \
    Parallel_working/output/ablation_results/viz_speed_comparison.png \
    Parallel_working/output/ablation_results/viz_ema_ablation_jitter.png \
    control_12_full.ino
```

Transfer `defense_handoff.tar.gz` to the Windows laptop (USB stick, OneDrive, or `scp`). On Windows, extract with 7-Zip or the built-in tar command:

```powershell
tar -xzf defense_handoff.tar.gz
```

Create the working folder `C:\Users\<you>\Documents\MSc_Defense\` and move the extracted files in, preserving paths.

---

## 2. Prepare the to-build assets

Before running Claude in PowerPoint, have these ready (see `assets_checklist.md` §2):

- `system_stack.png` — draw in draw.io or Excalidraw, export 1920×1080 PNG.
- `pipeline_latency.png` — same tool, same export size.
- `arena_hero.jpg`, `hardware_closeup.jpg` — phone photos, cropped to 16:9.
- `live_viewer_screenshot.png` — OS screenshot of `run_live_parallel_yolopose.sh` running.
- `demo_clip_trimmed.mp4` — trim `arena3d_20260417_123348.mp4` to 20–30 s.

To trim the demo clip inside PowerPoint: Insert > Video > From My PC → select file → on the video, Playback > Trim Video → set start/end sliders. Alternatively use Windows Video Editor (pre-installed: `mswvideoeditor:`) for a sharper crop.

All missing diagrams can be built with free tools:
- **draw.io Desktop** (`https://www.drawio.com/`) — no account, offline, SVG/PNG export.
- **Excalidraw** (`https://excalidraw.com/`) — browser-based, hand-drawn aesthetic.
- Use orange `#E88B40`, gray `#8A8A8A`, fill `#F5F2ED` to match the deck palette.

---

## 3. Run Claude in PowerPoint

1. Open PowerPoint → **New Blank Presentation** → File > Save As `MSc_Defense_Hanush.pptx` in `C:\Users\<you>\Documents\MSc_Defense\`.
2. Open the Claude chat pane (Copilot sidebar or Claude plugin).
3. Open `defense_ppt_handoff_prompt.md` in Notepad. Select all (Ctrl+A), copy (Ctrl+C).
4. Paste into the Claude chat pane (Ctrl+V). Send.
5. Wait for Claude to finish generating. It will:
   - Apply the custom theme (Accent 1 = `#E88B40`).
   - Build the 15 visible slides + 4 hidden appendix.
   - Insert orange-outlined rectangles in place of `[PLACEHOLDER_*]` tokens.
   - Add speaker notes on every slide.
   - Print the self-check report in its final message.

Expected runtime: 3–8 minutes depending on the Claude variant.

---

## 4. Verify the generated deck

Open the deck. Run through the self-check from the prompt:

- **Slide count**: Home > Select Pane or View > Slide Sorter. Confirm 19 slides total, with slides 16–19 marked Hidden (grayed out in the thumbnail pane).
- **Palette**: Design > Variants > Colors > Customize Colors. Confirm Accent 1 = `#E88B40` (RGB 232, 139, 64). If not, click Edit, fix it, Save As "NU Defense Palette".
- **Fonts**: Design > Fonts. Should be Inter/Calibri. If Inter is missing, download and install from `https://rsms.me/inter/` or let the fallback to Calibri remain.
- **Aspect ratio**: Design > Slide Size > Widescreen (16:9, 13.333 × 7.5 in).
- **Placeholders preserved**: Search across all slides (Home > Find > find `[PLACEHOLDER`). Every match should be an orange-outlined rectangle.
- **Speaker notes**: View > Notes Page. Scroll. Every slide must have ≥ 50 words.
- **No animations**: Transitions > None on every slide (except the subtle Fade). Animations pane should be empty except for Appear on grouped evidence, if any.

If any check fails, re-prompt Claude with: *"Please re-check slide N against the specification — it is missing X."*

---

## 5. Replace placeholders with real assets

Go slide-by-slide, click the orange-outlined placeholder rectangle, Insert > Picture (or Insert > Video for A1), replace. Keep the placeholder's position and size — Claude sized them correctly.

Mapping (from `assets_checklist.md`):

| Slide | Placeholder | Replace with |
|---|---|---|
| 1 | `[PLACEHOLDER_SCREENSHOT_1]` | `arena_hero.jpg` |
| 2 | `[PLACEHOLDER_SCREENSHOT_2]` | Split-card image (you build this) or keep placeholder |
| 5 | `[PLACEHOLDER_DIAGRAM_1]` | `system_stack.png` |
| 6 | `[PLACEHOLDER_DIAGRAM_2]` | `pipeline_latency.png` |
| 7 | `[PLACEHOLDER_SCREENSHOT_3]` | `hardware_closeup.jpg` |
| 9 | `[PLACEHOLDER_DIAGRAM_3]` | ChArUco pattern PNG + arena plot |
| 11 | (figure refs) | `viz_gt_bias_analysis.png` + `viz_speed_comparison.png` |
| 12 | (figure refs) | `viz_backend_comparison.png` + `viz_gt_joint_errors.png` |
| 13 | (figure ref) | `viz_ema_ablation_jitter.png` |
| A1 | `[PLACEHOLDER_VIDEO_1]` | `demo_clip_trimmed.mp4` |
| A3 | `[PLACEHOLDER_TABLE_1]` | Insert > Table; fill from `perf_blm_20260417_134210.jsonl` |

Leave these as-is until the relevant data is collected:
- Any `[VERIFY]` in a citation — verify against the thesis bibliography first.
- `[FILL ME]` on slide 1 — wait for supervisor/committee/date confirmation.
- `[MISSING EVIDENCE]` on slide 13 — intentional; it is a stated limitation.

---

## 6. Add the NU logo to the master slide

1. View > Slide Master.
2. On the top master slide, Insert > Pictures > `nu_logo.svg` (or PNG). Scale to 32 × 32 pt at top-left.
3. Close Master View.
4. Every slide now inherits the logo.

If you do not have the NU logo yet, leave the placeholder. The defense can run without it; just do not ship an unofficial version.

---

## 7. Fill speaker notes where flagged

Search all notes for `[FILL ME]` (some appear in the notes, not the body). Replace with short connectives. Do not pad — notes are for the presenter's memory, not for the committee.

---

## 8. Time the deck

1. Slide Show > Rehearse Timings. Run through the deck at defense pace (not faster).
2. Target total: 16:30–17:30.
3. Overruns: cut slide 4 (Background) from 1:15 → 0:45 or slide 13 (Limitations) from 1:00 → 0:45. Both are mentioned in `slide_plan.md` global notes.
4. Underruns: slow down slide 11 (Results) or add a sentence about calibration discipline on slide 9.

---

## 9. Export a PDF backup

File > Export > Create PDF/XPS. Save as `MSc_Defense_Hanush.pdf` next to the `.pptx`. This is your panic backup if the .pptx fails to open on the defense-room computer.

Also: File > Info > Save copies in `.pptx` and `.pptx` with fonts embedded (File > Options > Save > Embed fonts in the file → "Embed only the characters used").

---

## 10. Pre-defense checklist (day before)

- [ ] Rehearsed at least twice end-to-end.
- [ ] All `[PLACEHOLDER_*]`, `[FILL ME]` replaced or intentionally kept.
- [ ] `[VERIFY]` items checked against the thesis bibliography.
- [ ] Deck opens clean on the defense-room computer (arrive early to test).
- [ ] PDF backup on USB stick.
- [ ] `.pptx` and PDF on OneDrive as a second backup.
- [ ] Demo video plays with sound muted by default.
- [ ] Printed one-page contribution handout (5 copies).
- [ ] Appendix slides still Hidden in the main flow.

---

## 11. Common failure modes and fixes

| Symptom | Fix |
|---|---|
| Claude generates 15 slides without the hidden appendix. | Re-prompt: *"You only built 15 slides. Build the 4 hidden appendix slides A1–A4 per the spec and mark them Hidden."* |
| Colors look corporate-blue, not orange. | Design > Variants > Colors > Customize Colors, set Accent 1 to RGB 232, 139, 64 exactly. Save as custom palette. |
| Fonts render as Times New Roman on the defense-room laptop. | Embed fonts via File > Options > Save > Embed fonts in the file. |
| Demo video refuses to play. | Right-click video > Playback > Compress Media > HD (720p). Re-embed. |
| A slide is cluttered. | Move half the content to an appendix slide; keep main deck to the one-message rule. |
| Speaker notes are empty. | Re-prompt: *"Add speaker notes of at least 60 words to slide N."* |
| Total time is over 20 min. | Trim slides 4, 10, 13 by 15 s each; rehearse again. |

---

## 12. If Claude in PowerPoint is unavailable

Fallback: use the Claude web app or desktop app, paste the handoff prompt, ask it to return a structured JSON/Markdown slide-by-slide plan, then build the deck manually in PowerPoint using `slide_plan.md` as the template. Estimated time: 4–6 hours versus 30 minutes with the plugin. This is why we optimized the prompt for the plugin path.

---

**Summary:** 1-hour build on the Windows laptop if assets are prepared, 3–4 hours if you still need to draw the diagrams and trim the video. Start at least 48 hours before the defense.
