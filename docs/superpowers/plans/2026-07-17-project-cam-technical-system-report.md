# Project Cam Technical System Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a technically rigorous, readable, English Word report that explains the current Project_Cam system to a junior computer-vision engineer and clearly separates measured evidence, implemented code, working-tree prototypes, and planned work.

**Architecture:** Maintain the report body as reviewable Markdown, generate explanatory diagrams and the DOCX through a reproducible Python build script, and verify both the technical claims and the rendered Word output. The report is tied to the 2026-07-17 repository snapshot on branch `feature/multi-person-face-id-desktop-20260712` at committed HEAD `7f937dbc`, with working-tree-only capabilities labelled explicitly.

**Tech Stack:** Markdown, Python 3, Pillow, python-docx, Pandoc, LibreOffice headless, pdftotext/pdfinfo, repository code/configuration/JSON evidence.

---

### Task 1: Establish the report source and evidence vocabulary

**Files:**
- Create: `docs/reports/project_cam_technical_system_report_en.md`
- Reference: `docs/superpowers/specs/2026-07-15-garage-pilot-product-design.md`
- Reference: `configs/calibration/usb6_manifest.yaml`
- Reference: `arena_fixed/config/calibration_manifest.yaml`
- Reference: `Parallel_working/output/perf_lowlag_20260702_185011.jsonl`

- [ ] **Step 1: Add the report front matter and snapshot declaration**

  State the title, intended reader, evidence date, branch, committed HEAD, dirty-tree caveat, and the distinction between current code and working-tree-only features.

- [ ] **Step 2: Define a four-level maturity legend**

  Use exactly these categories throughout the report: `Measured`, `Implemented`, `Prototype`, and `Planned`. Explain that software tests do not constitute hardware, human-subject, or safety commissioning.

- [ ] **Step 3: Add an executive summary that frames the whole system**

  Describe Project_Cam as a multi-camera sports-vision and launcher-research platform, not merely a pose detector and not a commissioned production launcher.

- [ ] **Step 4: Create a source-of-truth table**

  Rank raw tracked artifacts and current code above active design/configuration, and rank narrative documentation and ignored local logs below them. Identify `docs/current_status.md`, `CANONICAL.md`, and the model registry as partially stale rather than silently treating them as current truth.

- [ ] **Step 5: Scan the source for prohibited overclaims**

  Run:

  ```bash
  rg -n -i "4\.4 mm accuracy|4\.4 mm shot|production-ready|safety-certified|all tests pass|276 tests|first-year|for a student" docs/reports/project_cam_technical_system_report_en.md
  ```

  Expected: no unqualified claims and no student framing.

### Task 2: Write the complete system and CV narrative

**Files:**
- Modify: `docs/reports/project_cam_technical_system_report_en.md`
- Reference: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`
- Reference: `Parallel_working/run_live_lowlag.sh`
- Reference: `src/project_cam/tracking/`
- Reference: `src/project_cam/closed_loop/`
- Reference: `src/project_cam/assessment/`
- Reference: `src/project_cam/training/`
- Reference: `project-cam-desktop/`

- [ ] **Step 1: Explain hardware, calibration, coordinate frames, and capture timing**

  Cover rolling-shutter USB cameras, lack of hardware synchronization, latest-frame asynchronous aggregation, freshness limits, intrinsics/extrinsics, normalized coordinates, projection matrices, and the 4-camera versus 6-camera evidence boundary.

- [ ] **Step 2: Explain pose inference and multi-view reconstruction**

  Cover YOLO-Pose/MMPose paths, TensorRT fixed-shape constraints, batching, confidence thresholds, person selection, SVD triangulation, reprojection pruning, left/right repair, and geometric hypothesis splitting. Include equations and a numerical triangulation example.

- [ ] **Step 3: Explain temporal processing and multi-person identity**

  Cover adaptive EMA, One-Euro display filtering, optional Kalman prediction, pelvis-based track association, primary-athlete switching, local YuNet/SFace identification, voting, and the no-liveness/unvalidated-scenario limitations.

- [ ] **Step 4: Explain ball tracking, athlete assessment, and training drills**

  Cover ball detection/triangulation/flight state/single-camera fallback, coaching-screen assessment outputs, and the five working-tree view-only drills. Avoid presenting session outputs as validated biomechanics truth.

- [ ] **Step 5: Explain launcher ownership and fail-closed safety**

  Cover the aim-only API, single launcher owner, firing-line snapshots, arm/shoot revalidation, all-person safety packets, primary-athlete policy gaps, uncalibrated RPM-to-speed mapping, and the distinction between implemented safety code and commissioning.

- [ ] **Step 6: Explain desktop, data flow, MLOps, privacy, and licensing**

  Distinguish the committed Tk control center from the untracked Tauri application; label static analytics/matches as demo data; document absent model checksums/provenance, open Ultralytics/SMPL decisions, local biometric embeddings, and youth-pilot governance requirements.

- [ ] **Step 7: Add failure-driven case studies**

  Include concise `Failure -> Diagnosis -> Engineering decision -> Remaining risk` callouts for asynchronous camera refresh, TensorRT shape mismatch, concurrent CUDA instability, left/right label artifacts, and uncalibrated launcher speed.

### Task 3: Build diagrams and the Word document reproducibly

**Files:**
- Create: `scripts/build_project_cam_technical_system_report.py`
- Create: `docs/assets/project_cam_report/system_architecture.png`
- Create: `docs/assets/project_cam_report/pose_geometry.png`
- Create: `docs/assets/project_cam_report/multi_person_flow.png`
- Create: `docs/assets/project_cam_report/fire_control_boundary.png`
- Create: `docs/assets/project_cam_report/evidence_ladder.png`
- Create: `docs/Project_Cam_Technical_System_Report_EN.docx`

- [ ] **Step 1: Implement deterministic diagram generation**

  Use Pillow to draw five 1600-pixel-wide diagrams with a consistent navy/blue/teal palette, readable labels, arrows, captions, and no external assets.

- [ ] **Step 2: Implement report compilation**

  Invoke Pandoc from the script, apply a generated reference DOCX, add a cover page, table of contents, numbered headings, page breaks, headers, footers, page numbers, table styling, figure captions, and local-source citations.

- [ ] **Step 3: Run the builder**

  Run:

  ```bash
  ./venv/bin/python scripts/build_project_cam_technical_system_report.py
  ```

  Expected: the five diagrams and `docs/Project_Cam_Technical_System_Report_EN.docx` are created without modifying the old introductory DOCX.

### Task 4: Verify technical integrity and rendering

**Files:**
- Verify: `docs/reports/project_cam_technical_system_report_en.md`
- Verify: `docs/Project_Cam_Technical_System_Report_EN.docx`

- [ ] **Step 1: Verify report structure and evidence qualifiers**

  Confirm that every planned section exists, all numeric claims name their rig/profile/date, `4.4 mm` is labelled repeatability, the 6-camera rig is labelled prototype, and working-tree-only features are marked.

- [ ] **Step 2: Verify DOCX package integrity**

  Run:

  ```bash
  unzip -t docs/Project_Cam_Technical_System_Report_EN.docx
  ```

  Expected: `No errors detected`.

- [ ] **Step 3: Render the DOCX to PDF and inspect its dimensions**

  Run:

  ```bash
  mkdir -p /tmp/project_cam_report_verify
  libreoffice --headless --convert-to pdf --outdir /tmp/project_cam_report_verify docs/Project_Cam_Technical_System_Report_EN.docx
  pdfinfo /tmp/project_cam_report_verify/Project_Cam_Technical_System_Report_EN.pdf
  ```

  Expected: successful conversion and approximately 30-35 readable pages.

- [ ] **Step 4: Extract and scan rendered text**

  Run:

  ```bash
  pdftotext -layout /tmp/project_cam_report_verify/Project_Cam_Technical_System_Report_EN.pdf /tmp/project_cam_report_verify/report.txt
  rg -n "635|234|156\.90|288\.34|178\.98|243\.77|4\.39|54\.17|113\.97|prototype|not commissioned" /tmp/project_cam_report_verify/report.txt
  ```

  Expected: the current evidence values and their qualifiers appear in the rendered output.

- [ ] **Step 5: Perform visual spot checks**

  Render representative PDF pages to PNG and inspect the cover, table of contents, a dense table, an equation/geometry section, each diagram, and the limitations/roadmap pages for clipping, overflow, blank pages, or unreadable text.

- [ ] **Step 6: Run final prohibited-claim scan**

  Confirm that the document does not describe the reader as a first-year student, does not equate repeatability with accuracy, and does not claim that 6-camera accuracy, Face ID, firing safety, or the Tauri product is validated/commissioned/reproducible.
