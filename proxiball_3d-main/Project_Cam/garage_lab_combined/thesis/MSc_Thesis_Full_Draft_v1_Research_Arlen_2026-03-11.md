# Pose Guided Predictive Ballistics for Body Part-Targeted Football Training

**Author:** Arlen Smagulov  
**Program:** Master of Science in Electrical and Computer Engineering  
**School:** School of Engineering and Digital Sciences  
**Department:** Department of Electrical and Computer Engineering  
**University:** Nazarbayev University  
**Main Supervisor:** Sultangali Arzykulov  
**Co-Supervisor:** Mohammad Hashmi  
**Draft Date:** March 11, 2026

---

## Declaration
I hereby declare that this manuscript is the result of my own work except for quotations and citations which have been duly acknowledged.

---

## Abstract
This research develops and validates a multi-camera computer-vision framework for body-part-targeted football training, with the long-term objective of driving an intelligent ball-launching machine in closed loop. Existing launcher-based systems in practical training contexts are often open-loop: the launcher acts as a ballistic source that sends balls according to predefined patterns, while player state and target events are measured through partial sensing or not measured in a unified 3D world frame. The central hypothesis of this thesis is that a calibrated four-camera vision stack can replace fragmented sensing and provide sufficiently accurate 3D perception for adaptive training decisions.

The work is organized as an end-to-end research pipeline over the complete `Project_Cam` repository, not only the final garage package. The project evolution is traced from early stereo and dual-camera studies (`Sport_center`, `src/core`, `src/legacy`), through four-camera laboratory reconstruction (`output/videos/final_3d_robot.mp4` and related artifacts), to full garage deployment and quantitative validation (`garage_lab_combined`). The final implementation combines: (i) robust camera calibration (ChArUco intrinsics, AprilTag extrinsics), (ii) synchronized four-camera acquisition, (iii) 3D triangulation of ball and 17-keypoint skeleton, (iv) world-frame visualization of arena geometry plus camera poses, and (v) structured ground-truth (GT) evaluation protocols for ball and human joints.

Quantitative validation demonstrates that the system is operational and measurable. Final per-camera intrinsics reprojection error is below 0.73 px at 1280x720 for all four cameras. Final extrinsics quality is camera-dependent, with reprojection RMSE in the range 1.18-5.23 px under real deployment disturbances. Ball static GT (36 points) reports mean error 150.77 mm (raw), improved to 95.17 mm with axis-wise correction. Dynamic ball tests show stable slow-motion performance and expected degradation under fast throws. Joint-touch GT (81 planned, 62 valid) reports mean 143.38 mm with clear per-joint bias trends.

The main contribution is not a finished launcher-control product; it is a calibrated perception and validation backbone with explicit error bounds, drift handling, and integration logic. This foundation enables the next stage: voice-commanded target selection, physics-based shot planning, and safety-constrained launcher actuation in a closed-loop training environment.

---

## Acknowledgements
I would like to thank my supervisors, Sultangali Arzykulov and Mohammad Hashmi, for continuous guidance, technical feedback, and research direction. I also thank my colleagues who participated in repeated calibration sessions, synchronized recordings, and manual GT data collection. Their support made it possible to transition from isolated prototypes to a full integrated research pipeline in a realistic garage environment.

---

## Table of Contents
1. Introduction  
2. Research Context and Literature Review  
3. Project Evolution Across `Project_Cam`  
4. Methodology and System Architecture  
5. Experimental Design and Protocols  
6. Results and Analytical Discussion  
7. Innovation, Novelty, and Practical Significance  
8. Roadmap to Intelligent Launcher Integration  
9. Conclusion and Future Work  
References  
Appendices

---

## List of Abbreviations
- CV: Computer Vision
- GT: Ground Truth
- RMSE: Root Mean Square Error
- PnP: Perspective-n-Point
- DLT: Direct Linear Transform
- EMA: Exponential Moving Average
- FPS: Frames Per Second
- ROI: Region of Interest
- ASME: American Society of Mechanical Engineers (citation format used)
- HIL: Hardware-In-the-Loop

---

## List of Tables
- Table 1.1 Research questions and hypotheses
- Table 3.1 Project folder-to-function map
- Table 4.1 Camera hardware and runtime configuration
- Table 4.2 Final intrinsic calibration summary
- Table 4.3 Final extrinsic calibration summary
- Table 5.1 Ball static GT design matrix
- Table 6.1 Ball static GT metrics (raw vs corrected)
- Table 6.2 Dynamic ball metrics
- Table 6.3 Joint-touch 3D metrics
- Table 8.1 Closed-loop launcher integration phases

---

## List of Figures
- Figure 3.1 Project evolution timeline (stereo -> lab -> garage)
- Figure 4.1 Unified architecture of data acquisition, inference, triangulation, and rendering
- Figure 4.2 Arena coordinate frame and AprilTag wall layout
- Figure 4.3 Camera-pose visualization in the garage world frame
- Figure 5.1 Static GT point layout in 3D
- Figure 6.1 Static ball GT: raw estimated vs true points
- Figure 6.2 Static ball GT: corrected estimated vs true points
- Figure 6.3 Dynamic trajectories: slow / fast / no-ball
- Figure 6.4 Joint-touch GT: per-joint error distribution
- Figure 8.1 Proposed command-to-shot closed-loop architecture

---

# Chapter 1 - Introduction

## 1.1 Background
Football training systems increasingly include automated launchers, but practical deployments still rely heavily on manual setup and fixed programs. The launcher typically follows preconfigured direction-speed patterns and cannot reliably adapt to where an athlete is in the actual 3D scene at each instant. In this context, even high-quality mechanical launchers are underused because sensing and intelligence layers are incomplete.

This thesis addresses that sensing-intelligence gap. The research goal is to establish a camera-only 3D perception stack that can estimate athlete body keypoints, ball trajectory, and target events in a shared metric coordinate system. The target application is body-part-targeted training where commands such as "left shoulder" or "right leg" can eventually trigger adaptive shots.

## 1.2 Motivation
The motivation is both scientific and engineering-driven:
- Scientifically, we need measurable, reproducible 3D localization in a constrained real environment (garage) with known geometry.
- Practically, we need a deployment-ready pipeline that tolerates camera index changes, lighting variation, partial occlusions, and operator workflow constraints.
- Strategically, replacing specialized distributed sensors with vision-based event detection can reduce hardware overhead and improve reconfigurability.

## 1.3 Problem Statement
The central problem is not just "detecting a ball" or "estimating a skeleton". The actual research problem is to connect multiple subsystems so that they are physically consistent and usable for control:
1. Multi-camera acquisition must be synchronized enough for triangulation.
2. Intrinsics and extrinsics must define a reliable world frame.
3. 2D detections must be robustly converted to 3D tracks.
4. Error and bias must be quantified against known GT points.
5. The resulting 3D outputs must be interpretable for future launcher control.

## 1.4 Research Questions and Hypotheses
### Table 1.1 Research questions and hypotheses
- **RQ1:** Can a four-camera fixed setup in a garage produce stable and measurable 3D ball/joint reconstruction in millimeters?
  - **H1:** Yes, if intrinsics and extrinsics are recalibrated for the exact deployment and validated with GT protocols.
- **RQ2:** What are the dominant practical error sources after deployment transition from lab to garage?
  - **H2:** Camera movement, partial overlap, and reduced multi-view visibility dominate more than model confidence thresholds.
- **RQ3:** Can post-hoc bias correction materially improve static localization quality?
  - **H3:** Axis-wise linear correction reduces mean and high-percentile errors but does not replace proper calibration.
- **RQ4:** Is the current system sufficient for immediate autonomous launcher control?
  - **H4:** Not yet for high-precision targeting; it is sufficient as a validated perception backbone for staged integration.

## 1.5 Scope and Delimitations
In scope:
- Full CV pipeline from acquisition to 3D render.
- Quantitative GT evaluations for ball and human joints.
- Drift-aware calibration and partial recalibration strategy.
- System-level integration roadmap for launcher control.

Out of scope in the current thesis stage:
- Final autonomous launcher actuation in production conditions.
- Final voice-command deployment and end-to-end shot execution.
- Formal human-subject biomechanics modeling.

## 1.6 Thesis Organization
The manuscript follows a research thesis structure: literature and context, system evolution, methods, experiments, results, discussion of novelty, and integration roadmap. This structure is chosen to emphasize reproducibility and explicit evidence over demonstration-only presentation.

---

# Chapter 2 - Research Context and Literature Review

## 2.1 Multi-View Geometry Foundations
Multi-view 3D reconstruction relies on calibrated camera models and projection consistency. In practice, DLT/PnP methods provide a mathematically consistent path from 2D image observations to 3D coordinates, but final performance depends strongly on data quality and calibration fidelity. The distinction between intrinsic and extrinsic error is critical:
- Intrinsic error affects per-camera ray correctness.
- Extrinsic error affects world-frame consistency between cameras.

For control applications, both must be controlled simultaneously.

## 2.2 Calibration In Real-World Environments
ChArUco and AprilTag-based workflows are common due to robust corner detection and practical marker management. However, real spaces introduce non-idealities: lens blur at edges, tag warping, wall non-planarity, dirt/occlusion, and operator handling variance. The literature generally assumes cleaner acquisition conditions than those encountered in this garage project. Therefore, robust filtering and repeated validation become mandatory.

## 2.3 Real-Time Ball and Pose Estimation
YOLO-family detectors provide practical tradeoffs of speed and detection quality. RTMPose/MMPose models provide strong 2D skeleton estimates, but identity switching and keypoint confidence instability occur in multi-person or partial-occlusion scenes. For 3D, confidence thresholds alone are insufficient; geometric consistency constraints are needed.

## 2.4 Sensorized Training vs Vision-Centric Training
Many commercial systems still depend on fixed sensor targets, impact switches, or localized trigger hardware. Vision-centric alternatives can define virtual target zones in software and verify events through 3D trajectories. This shifts complexity from hardware wiring to calibration and perception reliability.

## 2.5 Gap Addressed by This Thesis
The identified gap is a practical, integrated, validated pipeline in a non-lab deployment. Prior partial solutions address pieces of the problem (single-camera ball detection, dual-camera triangulation, or separate pose estimation). This thesis contributes integration and measured performance under deployment constraints.

---

# Chapter 3 - Project Evolution Across `Project_Cam`

## 3.1 Why Whole-Repository Analysis Matters
The final garage pipeline is understandable only when connected to earlier stages. `Project_Cam` contains multiple generations of scripts, calibration assets, and experiment outputs. The current architecture is the result of iterative convergence, not a one-shot implementation.

## 3.2 Stage A: Early Core and Legacy Prototypes (`src/legacy`, `src/core`, `src/calibration`)
Early scripts implemented:
- camera capture and basic synchronization assumptions,
- ChArUco calibration routines,
- triangulation from two and then four cameras,
- initial 3D rendering of skeleton/ball trajectories.

Examples:
- `src/legacy/main_3d_tracker.py`: early stereo + YOLO triangulation loop.
- `src/legacy/record_motion_4cam.py`: four-camera pose triangulation with 2x2 monitoring view.
- `src/core/triangulate_3d.py`, `src/core/triangulate_v2.py`: triangulation math and reprojection logic.
- `src/core/render_3d_robot.py`, `src/core/render_3d_full.py`: offline 3D reconstruction visualization.

These scripts established technical feasibility but had weaker deployment hardening and limited standardized GT evaluation.

## 3.3 Stage B: Multi-Camera Acquisition Hardening (`GARAGE_CAMERAS`)
`GARAGE_CAMERAS` evolved the recording layer with robust ffmpeg-based capture:
- multi-device recording,
- device include/exclude filters,
- preview grid support,
- buffering/timestamp controls,
- high-throughput recording management.

This stage solved operational capture issues that directly affected downstream triangulation quality.

## 3.4 Stage C: Imported Garage Baseline (`garage-20260217T113109Z-3-001`)
This folder contributed two critical baselines:
1. A mature AprilTag arena reconstruction setup (`extrinsics_1`) with known tag geometry and camera pose outputs.
2. A footbonaut-oriented dual-camera system (`environment`) showing high-speed inference and metric tracking principles.

The project reused lessons and assets from this baseline while adapting to a new four-camera garage deployment and new workflow requirements.

## 3.5 Stage D: Unified Garage Research Pipeline (`garage_lab_combined`)
`garage_lab_combined` is the integration layer that unified:
- runtime configuration (`config/cameras.yaml`, `config/runtime.yaml`),
- calibration scripts (intrinsics + robust extrinsics),
- synchronized short-clip recording tools,
- four-camera 3D processing,
- advanced rendering and live visualization,
- GT evaluation and reporting for ball and joints.

This stage is where the work became a measurable research pipeline rather than a set of demos.

## 3.6 Stage E: Quantitative Evaluation and Error Modeling
The repository introduced protocol-driven validation in `gt_eval`:
- `BALL_DETECTION_PIPELINE.md` and supporting scripts for 36-point static + dynamic tests.
- `JOINT_TOUCH_3D_PIPELINE.md` and scripts for 81 planned joint-touch trials.
- automatic metrics (mean, RMSE, P95, axis bias, static precision), and correction models.

This stage is the key transition from visual plausibility to quantified evidence.

## 3.7 Folder-to-Logic Connection
### Table 3.1 Project folder-to-function map
- `src/*`: foundational algorithms, early experiments, and core math.
- `GARAGE_CAMERAS/*`: robust acquisition subsystem.
- `garage-20260217.../*`: inherited baselines for garage mapping and high-speed tracking ideas.
- `garage_lab_combined/*`: final integrated research pipeline and evaluation framework.
- `output/*`, `data/*`, `cal/*`: archived outputs and intermediate artifacts documenting iterative progress.

This flow demonstrates continuity: each newer layer addresses limitations discovered in previous stages.

---

# Chapter 4 - Methodology and System Architecture

## 4.1 Research Methodology
The methodology follows a design-build-validate loop:
1. Build deployable subsystem (capture, calibration, inference, visualization).
2. Run controlled experiments with measurable GT.
3. Quantify error and bias.
4. Refine model parameters and calibration strategy.
5. Re-test under fixed protocol.

This iterative process aligns with research-based engineering methodology where claims are accepted only after measurement.

## 4.2 Hardware and Runtime Setup
### Table 4.1 Camera hardware and runtime configuration
- Camera model: Hikvision DS-E12 (USB)
- Number of cameras: 4 (camNorth, camEast, camSouth, camWest)
- Capture resolution: 1280x720
- Capture FPS target: 15
- Inference target: 5-15 FPS depending on mode
- World unit: millimeters

Camera logical mapping is stabilized through by-path device references in:
- `garage_lab_combined/config/cameras.yaml`

## 4.3 World Frame and Arena Geometry
The world frame is defined by `garage_lab_combined/cal/extrinsics/Dimensions.txt`:
- X = 6230 mm
- Y = 3050 mm
- Z = 2950 mm
- Origin: North-East floor corner

The same file stores camera measured coordinates and AprilTag corner coordinates (`c0..c3`) for each ID. This is essential because the extrinsics solver uses these values directly as geometric truth.

## 4.4 Intrinsics Calibration Process
Main scripts:
- `garage_lab_combined/scripts/auto_capture_charuco_multi.py`
- `garage_lab_combined/scripts/calibrate_intrinsics_from_images.py`

Workflow:
1. Collect per-camera ChArUco images with sufficient corner quality.
2. Filter frames by minimum corners.
3. Solve per-camera intrinsics.
4. Save camera matrix, distortion coefficients, reprojection error, image size.

### Table 4.2 Final intrinsic calibration summary
| Camera | Frames used | Reprojection error (px) |
|---|---:|---:|
| camNorth | 77 | 0.7279 |
| camEast  | 78 | 0.3998 |
| camSouth | 77 | 0.4844 |
| camWest  | 80 | 0.3570 |

## 4.5 Extrinsics Calibration Process
Main script:
- `garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py`

Key design choices:
- AprilTag detection in each selected frame.
- Robust PnP with iterative rejection of high-error points/tags.
- Optional camera-specific tag inclusion maps for difficult views.
- Position drift monitoring against manually measured camera coordinates.

Final operational extrinsics file:
- `garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json`

### Table 4.3 Final extrinsic calibration summary
| Camera | RMSE (px) | Position error (m) | Inlier points |
|---|---:|---:|---:|
| camNorth | 1.44 | 0.266 | 651 |
| camEast  | 1.18 | 0.218 | 668 |
| camSouth | 5.23 | 0.174 | 672 |
| camWest  | 2.26 | 0.116 | 1001 |

## 4.6 Synchronized Recording Method
Main script:
- `garage_lab_combined/scripts/record_short_clips_multi.py`

Capabilities:
- multi-camera simultaneous short clips,
- start-delay for operator movement to target point,
- per-clip metadata.

This script supports both controlled GT collection and general smoke tests.

## 4.7 3D Inference and Triangulation Pipeline
Main processing script:
- `garage_lab_combined/scripts/process_4cam_to_3d.py`

Pipeline logic:
1. Run ball detector on synchronized frames from four cameras.
2. Convert pixel centroids to undistorted normalized rays.
3. Triangulate candidate 3D point from all available observations.
4. Reject worst camera iteratively by reprojection error until threshold met or minimum cameras violated.
5. Apply optional speed gate and EMA smoothing.
6. Run 2D pose detector per camera.
7. Select consistent person target per camera to reduce switching.
8. Triangulate each joint independently from confident views.

Output per frame includes:
- `ball`, `ball_cams`, `ball_reproj_px`,
- `joints` list of 17 3D points (or null when not estimable).

## 4.8 Rendering and Live Monitoring
Main scripts:
- `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- `garage_lab_combined/scripts/render_apriltag_arena_360.py`
- `garage_lab_combined/scripts/live_4cam_arena_view.py`

These modules produce:
- static and orbital arena visualizations,
- full trajectory + skeleton playback,
- live pop-up monitoring for system diagnostics.

Visualization is not only for presentation; it is critical for identifying coordinate drift, identity switches, and impossible trajectories.

## 4.9 Goal Detection and Target Concepts
Legacy and core modules also include target-zone and hybrid goal logic:
- `src/core/fast_goal_detector.py`
- `src/core/hybrid_goal_detector.py`
- `src/core/render_3d_with_goal.py`

These modules informed the future integration where target planes (1.0x1.0 m / 1.0x1.5 m) are interpreted in world coordinates and hit/miss events are camera-verified.

---

# Chapter 5 - Experimental Design and Protocols

## 5.1 Experimental Philosophy
The thesis applies two complementary principles:
- **Controlled static tests** for absolute accuracy and bias estimation.
- **Dynamic stress tests** for realism under blur, speed, and occlusion.

Both are required because low static error does not guarantee stable dynamic behavior.

## 5.2 Ball Static GT Protocol (36 Points)
Protocol document:
- `garage_lab_combined/gt_eval/BALL_DETECTION_PIPELINE.md`

Grid design:
- X: 3000, 4000, 5000 mm
- Y: 2300, 1600, 1000 mm
- Z: 200, 750, 1300, 1800 mm

Total trials: 3 x 3 x 4 = 36.

Each trial records one 4-second synchronized clip with a rigidly held ball center at known world coordinates.

## 5.3 Ball Dynamic Protocol
Three additional clips evaluate temporal robustness:
- `ball_slow` (gentle movement),
- `ball_fast` (real throws),
- `no_ball` (false positive check).

This protocol isolates different failure modes and avoids overfitting static-only tuning.

## 5.4 Joint-Touch GT Protocol (81 Planned)
Protocol document:
- `garage_lab_combined/gt_eval/JOINT_TOUCH_3D_PIPELINE.md`

Planned design:
- 9 XY positions,
- 3 platform levels,
- 3 joints (`left_shoulder`, `right_hip`, `right_knee`).

Total planned trials: 81.  
Completed valid trials in current run: 62.

## 5.5 Rigid-Target Protocol for Geometry Baseline
Additional protocol exists for rigid-point validation:
- `garage_lab_combined/gt_eval/RIGID_GT_PIPELINE.md`

Its purpose is to separate geometric camera error from human placement uncertainty. This is particularly important before launcher control where geometric miss translates directly to shot miss.

## 5.6 Metrics
Reported metrics include:
- per-trial vector error (`ex, ey, ez`),
- norm error (`|e|`),
- mean/median/RMSE/P90/P95/max,
- axis bias,
- static precision (`std_norm` in hold windows),
- detection coverage and camera-count statistics.

This metric set provides both control relevance (absolute error) and confidence diagnostics (stability and coverage).

## 5.7 Threats to Validity
- manual joint-touch placement uncertainty,
- inconsistent multi-camera visibility in edge regions,
- camera movement between sessions,
- partial recalibration when only one camera moved,
- frame-level synchronization residual offsets.

The protocols and logs were designed to expose these threats rather than hide them.

---

# Chapter 6 - Results and Analytical Discussion

## 6.1 Intrinsics and Extrinsics Outcomes
Intrinsics quality is strong and consistent across all cameras (<0.73 px). Extrinsics quality is good for most cameras but not uniform, particularly after physical camera shifts. This directly supports the project observation that mechanical stability and recalibration discipline dominate long-term accuracy.

## 6.2 Ball Static GT Results
Source files:
- `.../reports_static_raw/summary_metrics.json`
- `.../reports_static_corrected/summary_metrics.json`

### Table 6.1 Ball static GT metrics
| Metric | Raw | Corrected |
|---|---:|---:|
| Mean (mm) | 150.77 | 95.17 |
| Median (mm) | 156.55 | 84.18 |
| RMSE (mm) | 167.39 | 102.23 |
| P90 (mm) | 236.38 | 142.18 |
| P95 (mm) | 288.34 | 166.51 |
| Max (mm) | 361.83 | 214.60 |
| Detection ratio | 1.000 | 1.000 |
| Mean cameras used | 2.87 | 2.87 |
| Mean reprojection (px) | 6.01 | 6.01 |

Interpretation:
- There is clear raw systematic bias, especially in Z.
- Linear axis correction significantly improves absolute error.
- Despite improvements, corrected performance is still above strict autonomous-control targets.

## 6.3 Dynamic Ball Results
Source file:
- `.../reports_dynamic_summary.json`

### Table 6.2 Dynamic metrics
| Clip | Detect ratio | Mean reproj px | Jump P95 mm | Jump max mm |
|---|---:|---:|---:|---:|
| ball_slow | 0.975 | 4.03 | 58.16 | 173.07 |
| ball_fast | 0.891 | 6.51 | 462.70 | 814.46 |
| no_ball | 0.000 | - | - | - |

Interpretation:
- Slow dynamic behavior is stable and suitable for live visualization and moderate-speed use cases.
- Fast throws reveal instability and occasional large jumps.
- No-ball session confirms strong false-positive suppression under tested background.

## 6.4 Joint-Touch Results
Source file:
- `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/reports/summary_metrics.json`

### Table 6.3 Joint-touch metrics
| Metric | Value |
|---|---:|
| Trials total | 81 |
| Trials valid | 62 |
| Trials missing/failed | 19 |
| Mean error (mm) | 143.38 |
| Median (mm) | 148.90 |
| RMSE (mm) | 147.73 |
| P95 (mm) | 198.73 |
| Max (mm) | 217.34 |
| Mean detection ratio | 1.000 |

Per-joint means:
- left_shoulder: 164.38 mm
- right_hip: 150.38 mm
- right_knee: 110.03 mm

Interpretation:
- The system is precise (low intra-window jitter) but not yet highly accurate in absolute terms.
- Shoulder error is highest, consistent with greater occlusion and geometric sensitivity.
- Human placement uncertainty likely inflates measured joint error relative to rigid-point tests.

## 6.5 Analytical Synthesis
The results support three conclusions:
1. Calibration and visibility, not raw detector confidence, are the main bottlenecks.
2. Bias correction is useful but must be treated as secondary to geometric correctness.
3. The system is ready for guided integration experiments but not for high-stakes autonomous targeting without additional hardening.

## 6.6 Error Budget Perspective
A practical error budget emerges:
- Intrinsics: small contributor (sub-pixel reprojection).
- Extrinsics drift and tag-map inconsistency: major contributor.
- Limited multi-camera overlap: major contributor in edge regions.
- Dynamic blur/occlusion: major contributor for fast motion.
- Human GT uncertainty: significant contributor in joint tests.

This decomposition provides a clear optimization sequence for the next stage.

---

# Chapter 7 - Innovation, Novelty, and Practical Significance

## 7.1 Core Innovation Claim
The primary innovation is the transition from launcher-centric automation to perception-centric training intelligence. In the traditional paradigm, the launcher is the center and sensing is auxiliary. In this work, calibrated perception is the center and launcher commands become a downstream decision problem.

## 7.2 Why This Is Novel In Practice
The novelty is not a single algorithmic component; it is an integrated, measured stack deployed in a realistic environment:
- metric world reconstruction via AprilTags,
- four-camera synchronized 3D tracking,
- unified arena-camera-ball-skeleton rendering,
- GT-driven bias and precision analysis,
- explicit path toward command-driven targeting.

## 7.3 Sensor Replacement Strategy
A major practical contribution is the concept of replacing distributed target sensors with camera-defined world zones:
- targets are defined in software,
- shot events are verified via 3D trajectory intersection,
- geometry can be reconfigured quickly for different training plans.

This improves flexibility and reduces physical infrastructure complexity.

## 7.4 Research University Alignment
As a research-based university project, this thesis emphasizes:
- explicit hypotheses,
- measurable protocols,
- reproducible scripts and outputs,
- critical analysis of failures,
- realistic claims and staged roadmap.

The contribution is therefore both scientific (validated methodology) and translational (deployable system architecture).

---

# Chapter 8 - Roadmap to Intelligent Launcher Integration

## 8.1 Current System Readiness
Ready now:
- calibrated 3D perception pipeline,
- world-frame event geometry,
- quantified ball and joint localization behavior,
- live and offline visualization.

Not yet ready:
- direct launcher actuator control loop,
- production-grade voice command integration,
- verified autonomous hit accuracy at strict thresholds.

## 8.2 Proposed Closed-Loop Pipeline
1. **Command intake:** parse text/voice command into target semantics.
2. **Target mapping:** map command to dynamic 3D point or zone (e.g., left shoulder).
3. **Confidence gate:** require stable estimate, minimum camera support, and quality score.
4. **Ballistics solver:** compute launch parameters from launcher-to-target geometry.
5. **Actuation:** transmit command to launcher hardware.
6. **Verification:** use camera pipeline to confirm hit/miss and update adaptation model.

## 8.3 Safety and Ethics Constraints
Autonomous training machinery requires strict safeguards:
- no-fire if confidence is low,
- no-fire under occlusion/identity ambiguity,
- physical exclusion zones,
- emergency stop channel,
- command authentication and audit logs.

## 8.4 Phase Plan
### Table 8.1 Integration phases
- **P1:** Perception freeze and rigid GT qualification.
- **P2:** Command parser + target semantic binding.
- **P3:** Physics model + simulation-only shot planner.
- **P4:** Hardware-in-the-loop manual-supervised tests.
- **P5:** Closed-loop autonomous trials under safety constraints.

## 8.5 Quantitative Exit Criteria for Autonomy
Before full autonomous shots:
- rigid-point mean error <= 60 mm,
- rigid-point P95 <= 90 mm,
- reliable >=3 camera support for most operational target volume,
- dynamic fast-motion outlier rate reduced below safety threshold.

These criteria convert qualitative readiness into measurable engineering gates.

---

# Chapter 9 - Conclusion and Future Work

## 9.1 Conclusion
This thesis delivered a full research-grade perception pipeline for body-part-targeted football training in a realistic garage setup. The work integrated multiple generations of `Project_Cam` artifacts into one coherent system and validated it with explicit GT protocols. The resulting system can reconstruct and visualize 3D arena context, camera poses, ball trajectory, and human keypoints in a single world frame.

The results confirm that the project has crossed the threshold from prototype demos to measurable engineering evidence. At the same time, they also show that autonomous launcher control requires another stage of geometric hardening and rigid-target validation.

## 9.2 Main Contributions
1. End-to-end four-camera 3D pipeline with calibration, triangulation, rendering, and evaluation.
2. Repository-wide integration linking legacy, lab, and garage stages.
3. Quantitative GT methodology for ball and joint tracking quality.
4. Bias modeling and correction workflow.
5. Realistic closed-loop integration roadmap.

## 9.3 Future Work
Immediate priorities:
- full rigid-target campaign after final camera lock,
- improved camera overlap and recalibration discipline,
- command-to-target binding implementation,
- ballistics calibration with launcher response model,
- safety-constrained HIL trials.

Longer-term priorities:
- online adaptive calibration checks,
- multi-person identity robustness,
- predictive aiming under motion models,
- curriculum-based training personalization.

The final intended outcome is a smart training platform where verbal task definitions are transformed into reliable, safe, and measurable targeted shots.

---

# References (ASME Numeric Style, Draft)
[1] Hartley, R., and Zisserman, A., 2004, *Multiple View Geometry in Computer Vision*, 2nd ed., Cambridge University Press, Cambridge, UK.

[2] Szeliski, R., 2022, *Computer Vision: Algorithms and Applications*, 2nd ed., Springer, Cham.

[3] Garrido-Jurado, S., Munoz-Salinas, R., Madrid-Cuevas, F. J., and Marin-Jimenez, M. J., 2014, "Automatic generation and detection of highly reliable fiducial markers under occlusion," *Pattern Recognit.*, 47(6), pp. 2280-2292.

[4] OpenCV, 2026, "ArUco and ChArUco modules," https://docs.opencv.org, accessed Mar. 11, 2026.

[5] Olson, E., 2011, "AprilTag: A robust and flexible visual fiducial system," *Proc. IEEE Int. Conf. Robot. Autom.*, pp. 3400-3407.

[6] Wang, J., Olson, E., and Kaess, M., 2016, "AprilTag 2: Efficient and robust fiducial detection," *Proc. IEEE/RSJ Int. Conf. Intell. Robots Syst.*, pp. 4193-4198.

[7] Ultralytics, 2026, "YOLO documentation," https://docs.ultralytics.com, accessed Mar. 11, 2026.

[8] OpenMMLab, 2026, "MMPose documentation," https://mmpose.readthedocs.io, accessed Mar. 11, 2026.

[9] `src/legacy/main_3d_tracker.py`, internal repository artifact, Project_Cam.

[10] `src/legacy/record_motion_4cam.py`, internal repository artifact, Project_Cam.

[11] `GARAGE_CAMERAS/record_cams.py`, internal repository artifact, Project_Cam.

[12] `garage-20260217T113109Z-3-001/garage/environment/README.md`, internal repository artifact.

[13] `garage_lab_combined/scripts/process_4cam_to_3d.py`, internal repository artifact.

[14] `garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py`, internal repository artifact.

[15] `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_static_raw/summary_metrics.json`, internal report.

[16] `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_dynamic_summary.json`, internal report.

[17] `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/reports/summary_metrics.json`, internal report.

[18] `MSc(ECE)_Handbook_v-1 11-06-2025_MB.pdf`, School of Engineering and Digital Sciences, Nazarbayev University.

---

# Appendix A - Whole-Repository Logical Map
- `src/legacy`, `src/core`, `src/calibration`: prototype and mathematical core.
- `GARAGE_CAMERAS`: robust acquisition tooling.
- `garage-20260217T113109Z-3-001`: inherited garage and footbonaut baselines.
- `garage_lab_combined`: integrated deployment and evaluation package.
- `output`, `data`, `cal`: historical outputs and calibration artifacts documenting evolution.

# Appendix B - Key Reproducibility Artifacts
- Intrinsics: `garage_lab_combined/cal/intrinsics/*_intrinsics.json`
- Extrinsics: `garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json`
- Arena map: `garage_lab_combined/cal/extrinsics/Dimensions.txt`
- Processing: `garage_lab_combined/scripts/process_4cam_to_3d.py`
- Rendering: `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- Ball GT reports: `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/*`
- Joint GT reports: `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/*`

# Appendix C - Draft Figure Insertion Plan
Insert at least 18 figures across Chapters 3-8, prioritizing:
- calibration overlays,
- arena-camera render views,
- GT scatter comparisons,
- dynamic trajectories,
- joint error boxplots,
- closed-loop architecture block diagram.

