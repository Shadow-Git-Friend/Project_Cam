# MSc Thesis Plan (ECE) - Project_Cam

Date: 2026-03-11  
Author: Arlen Smagulov

## 1. Basis Of This Plan
This plan is aligned to `MSc(ECE)_Handbook_v-1 11-06-2025_MB.pdf`.

Constraint applied exactly as requested:
- Handbook pages reviewed: `1-7` and `11-22`
- Handbook pages intentionally skipped: `8-10`

## 2. Handbook Compliance Checklist (Working Checklist)

### 2.1 Manuscript structure and order
Required order to follow in final thesis:
1. Front cover (title page)
2. Declaration form (Appendix V format)
3. Abstract (<= 500 words)
4. Acknowledgements
5. Table of Contents
6. List of Abbreviations
7. List of Tables
8. List of Figures
9. Main chapters
10. Bibliography/References
11. Appendices

### 2.2 Formatting constraints
- Language: English
- Font: Times New Roman, 12 pt, black
- Line spacing: double in body text
- Paragraph first-line indent: 1.25 cm
- Margins: at least 2.5 cm on all sides
- Text alignment: justified
- No decorative borders/headers
- Pagination: all pages numbered except title page (center top or bottom)
- Length: <= 100 pages excluding appendices

### 2.3 Chapter numbering
- Chapters: `1, 2, 3, ...`
- Sections: `1.1, 1.2, ...`
- Subsections: `1.1.1, 1.1.2, ...`

### 2.4 Referencing
- Use ASME numeric style by default: `[1]`, `[1,2]`, `[5-7]`
- Reference list ordered by first appearance in text

## 3. Proposed Thesis Title
**Pose Guided Predictive Ballistics for Body Part-Targeted Football Training**

## 4. Problem Statement (How It Will Be Written)
Current commercial training setups generally treat the launcher as a blind ball source. They do not close the loop using real-time 3D understanding of player pose, ball trajectory, and dynamic target zones in the same calibrated world frame.

This thesis develops and validates a computer-vision-first pipeline that:
- Reconstructs a calibrated 3D arena with AprilTags,
- Triangulates 3D ball and human keypoints from four synchronized cameras,
- Evaluates metric error against ground truth,
- Prepares the technical basis for command-driven smart aiming and shot execution.

## 5. Novelty And Contribution Claims (Drafted For Defense)
1. A full 4-camera garage calibration and reconstruction workflow in millimeters, using AprilTag world geometry and ChArUco intrinsics.
2. Unified 3D visualization combining arena mesh, camera poses, AprilTag map, ball trajectory, and full-body skeleton.
3. Quantitative GT protocol for ball localization (36 static points + dynamic stress tests).
4. Quantitative GT protocol for joint-touch localization (81 planned trials, 62 valid in current run).
5. Bias modeling and post-correction framework for both ball and joint localization.
6. System architecture proposal for future voice-commanded smart launcher control and hit validation using camera-only sensing.

## 6. Chapter Plan (Page Budget)
Target total manuscript length: **60-100 pages** (excluding appendices), aligned to handbook limits.
Recommended body target: ~72-88 pages.

### Chapter 1 - Introduction (8-10 pages)
- Context: football/footbot training and smart automation gap
- Problem definition and motivation
- Research objectives and thesis questions
- Contributions and scope
- Thesis structure

### Chapter 2 - Literature And Technology Review (12-16 pages)
- Ball launching systems and limitations of fixed launch logic
- Multi-camera calibration and triangulation methods
- Real-time ball detection and 2D/3D pose estimation
- Sensor-based vs camera-based target/goal detection
- Positioning of this work vs existing approaches

### Chapter 3 - System Design And Methodology (16-22 pages)
- Hardware setup (4 fixed Hikvision cameras, garage dimensions)
- Coordinate system and AprilTag map
- Intrinsics calibration (ChArUco)
- Extrinsics calibration (robust AprilTag PnP)
- Video synchronization strategy
- 3D reconstruction pipeline (ball + skeleton)
- Rendering/visualization pipeline

### Chapter 4 - Experimental Protocols (12-16 pages)
- Static ball GT protocol (36 points)
- Dynamic ball tests (`ball_slow`, `ball_fast`, `no_ball`)
- Joint-touch GT protocol (81 planned)
- Metrics: error norm, RMSE, P95, axis bias, static precision, detection ratio
- Validation scripts and reproducibility notes

### Chapter 5 - Results And Analysis (14-18 pages)
- Intrinsics and extrinsics calibration quality
- Ball GT raw performance and corrected performance
- Dynamic robustness and false-positive behavior
- Joint 3D localization performance by joint class
- Root-cause analysis of residual error sources

### Chapter 6 - Intelligent Launcher Integration Roadmap (8-12 pages)
- Current status (implemented vs pending)
- Voice command parsing and target binding concept
- World-to-launcher frame transform and ballistic solver concept
- Safety interlocks and confidence gating
- Implementation phases and acceptance criteria

### Chapter 7 - Conclusion And Future Work (5-8 pages)
- Key findings
- Practical readiness level today
- Next milestones to field deployment

## 6.1 Front Matter (institution + supervision)
- School of Engineering and Digital Sciences
- Department of Electrical and Computer Engineering
- Nazarbayev University
- Student: Arlen Smagulov
- Main Supervisor: Sultangali Arzykulov
- Co-Supervisor: Mohammad Hashmi

## 7. Figures And Tables Plan

### Core figures to include
- Arena world frame diagram and camera locations
- AprilTag wall layout and ID map
- Extrinsics overlay validation examples
- 3D render snapshots (arena + ball + skeleton)
- Ball static GT: GT vs estimated (raw and corrected)
- Dynamic trajectory plots (`slow`, `fast`, `no_ball`)
- Joint GT: 3D GT vs estimated, per-joint boxplots
- Proposed smart launcher architecture block diagram

### Core tables to include
- Camera specifications and runtime settings
- Final intrinsics per camera
- Final extrinsics quality metrics per camera
- Ball static GT summary (raw/corrected)
- Dynamic test summary
- Joint test summary (global + per-joint)
- Risk register and mitigation strategy

## 8. What Will Be Explicitly Declared As Not Finished Yet
To avoid over-claiming in manuscript and defense:
- Launcher closed-loop control is not yet integrated in hardware.
- Voice-commanded targeting is at architecture/design stage.
- Ballistic solver and actuator command layer are not yet validated in real shots.
- Present work provides calibrated perception and quantitative error baseline needed before control-loop deployment.

Suggested phrasing in thesis:
"The present thesis delivers the perception, calibration, and quantitative validation backbone, while launcher actuation remains an ongoing integration phase."

## 9. Mapping To Handbook Assessment Criteria
- Problem/objectives (10%): Chapters 1 and 6
- Literature/technology review (15%): Chapter 2
- Methodology/design/implementation (35%): Chapter 3
- Testing/results/evaluation/future work (30%): Chapters 4, 5, 7
- Structure/presentation compliance (10%): front matter + formatting + references

## 10. Immediate Writing Workflow
1. Freeze the chapter structure and title.
2. Populate Chapter 3 and Chapter 5 first (strongest technical evidence).
3. Write Chapter 2 with targeted references that directly support methods.
4. Write Chapter 6 carefully as "near-term engineering roadmap", not finished product.
5. Finalize Abstract and Conclusion last.

## 11. Files To Treat As Primary Evidence
- `garage_lab_combined/cal/intrinsics/*_intrinsics.json`
- `garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json`
- `garage_lab_combined/cal/extrinsics/Dimensions.txt`
- `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_static_raw/summary_metrics.json`
- `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_static_corrected/summary_metrics.json`
- `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_dynamic_summary.json`
- `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/reports/summary_metrics.json`
- `garage_lab_combined/scripts/process_4cam_to_3d.py`
- `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- `garage_lab_combined/scripts/live_4cam_arena_view.py`
