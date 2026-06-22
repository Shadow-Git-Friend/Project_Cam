# THESIS TITLE

**Pose Guided Predictive Ballistics for Body Part-Targeted Football Training**

Arlen Smagulov  
Submitted in fulfilment of the requirements for the degree of Master of Science in Electrical and Computer Engineering  
School of Engineering and Digital Sciences  
Department of Electrical and Computer Engineering  
Nazarbayev University  
Supervisors: Sultangali Arzykulov (Main Supervisor), Mohammad Hashmi (Co-Supervisor)  
Date of Completion: [Month Year]

---

# DECLARATION
I hereby declare that this manuscript is the result of my own work except for quotations and citations which have been duly acknowledged.

[Signature]  
Name: [Student Name]  
Date: [Date]

---

# Abstract
This thesis presents a computer-vision pipeline for 3D reconstruction of a football training space using four fixed RGB cameras, with the long-term goal of controlling an intelligent ball-launching machine. The core motivation is that current launcher-based training systems are typically open-loop: they release balls at predefined settings but do not adapt to real-time 3D player position, body pose, or dynamic target geometry. The proposed approach replaces dedicated local sensors with a camera-only framework that jointly estimates ball trajectory, human skeleton keypoints, camera poses, and arena geometry in a shared world frame.

The system was developed incrementally from earlier dual-camera and lab 4-camera experiments into a new garage deployment. A calibrated arena model was built using a metric AprilTag map (`Dimensions.txt`) and robust extrinsics estimation. Camera intrinsics were re-estimated at 1280x720 using a full A4 ChArUco board and per-camera reprojection errors below 0.73 px. Final extrinsics achieved per-camera reprojection errors of 1.18-5.23 px with camera-position consistency checks against measured camera coordinates. Synchronized four-camera recording, 3D triangulation of ball and human joints, and unified rendering of arena + tags + cameras + skeleton + ball were implemented in one reproducible pipeline.

Quantitative validation was performed in the same world coordinate system (mm). For ball localization, a 36-point static ground-truth dataset and dynamic clips (`ball_slow`, `ball_fast`, `no_ball`) were collected. Raw static ball error was mean 150.77 mm (RMSE 167.39 mm, P95 288.34 mm). A lightweight axis-wise correction model reduced error to mean 95.17 mm (RMSE 102.23 mm, P95 166.51 mm). Dynamic validation showed stable operation for slow motion (97.5% detection, no large jumps) and expected degradation in fast throws due to blur/occlusion (89.1% detection). For human joints, an 81-trial touch protocol (62 valid trials) produced mean 143.38 mm and P95 198.73 mm, with joint-dependent bias.

The main contribution is not final launcher actuation, but a calibrated perception backbone with measured error bounds, robust data collection protocols, and a practical integration roadmap for voice-commanded targeting and physics-based shot planning. The thesis defines what is ready today and what remains before safe closed-loop launcher deployment.

---

# Acknowledgements
I would like to thank my supervisors for academic guidance and technical feedback throughout this project. I also thank my collaborators and lab mates for support during repeated camera setup, calibration sessions, and data collection in both lab and garage environments. I acknowledge the support of Nazarbayev University and the Department of Electrical and Computer Engineering for providing the infrastructure and resources needed to complete this work.

---

# Table of Contents
Target manuscript length: 60-100 pages (excluding appendices).  

1. Introduction  
2. Literature And Technology Review  
3. System Design And Implementation  
4. Experimental Protocols And Metrics  
5. Results And Analysis  
6. Novelty, Innovation, And Practical Significance  
7. Intelligent Launcher Integration Roadmap  
8. Conclusion And Future Work  
Bibliography/References  
Appendices

---

# List of Abbreviations
- CV: Computer Vision
- GT: Ground Truth
- PnP: Perspective-n-Point
- RMSE: Root Mean Square Error
- EMA: Exponential Moving Average
- FPS: Frames Per Second
- ROI: Region of Interest
- DLT: Direct Linear Transform
- DoF: Degrees of Freedom
- API: Application Programming Interface

---

# List of Tables
- Table 3.1: Final camera intrinsics at 1280x720
- Table 3.2: Final camera extrinsics quality metrics
- Table 4.1: Ball static GT design (36 points)
- Table 5.1: Ball static results (raw vs corrected)
- Table 5.2: Dynamic ball validation summary
- Table 5.3: Joint-touch 3D validation summary
- Table 7.1: Launcher integration phases

---

# List of Figures
- Figure 3.1: Garage arena coordinate frame and dimensions
- Figure 3.2: AprilTag world map and camera placements
- Figure 3.3: 3D arena reconstruction and camera pose visualization
- Figure 3.4: Unified render (arena + skeleton + ball)
- Figure 5.1: Ball static GT vs estimated points (raw)
- Figure 5.2: Ball static GT vs estimated points (corrected)
- Figure 5.3: Dynamic trajectory plots (`ball_slow`, `ball_fast`, `no_ball`)
- Figure 5.4: Joint-touch GT vs estimated 3D points
- Figure 7.1: Proposed closed-loop smart launcher architecture

---

# Chapter 1 - Introduction

## 1.1 Problem Context
Modern football and footbot training systems often include ball-launching machines, but in many deployments the launcher remains a fixed-function mechanism: speed, direction, and timing are set manually or from pre-programmed routines. The system does not fully perceive where the athlete is in 3D, which body part is exposed, or whether a launched ball crossed a designated target gate in world coordinates.

This thesis addresses that gap with a camera-only 3D perception pipeline. The core objective is to build a calibrated digital twin of a garage training arena where ball position, body keypoints, camera poses, and target geometry are represented in one metric coordinate system. This perception layer is the required prerequisite for future intelligent launcher control.

## 1.2 Project Motivation
The work was motivated by practical constraints and application needs:
- Existing launcher workflows are not adaptive to live player geometry.
- Sensor-heavy alternatives increase hardware complexity and maintenance.
- Fixed cameras are already available and can be leveraged as a scalable sensing layer.
- The project requires measurable accuracy in millimeters before any command-to-shot control loop can be considered safe.

## 1.3 Research Objectives
The thesis pursues five objectives:
1. Build a stable four-camera synchronized recording and processing pipeline.
2. Calibrate intrinsics and extrinsics for a garage arena with AprilTag-based world geometry.
3. Reconstruct ball and human 3D keypoints from multi-view detections.
4. Quantify error and bias using repeatable GT protocols.
5. Define a realistic integration roadmap for smart launcher aiming and shot validation.

## 1.4 Scope
In-scope:
- 3D perception pipeline and visualization.
- Ground-truth protocols and quantitative evaluation.
- Bias correction modeling and validation tools.
- System architecture for launcher integration.

Out-of-scope (current stage):
- Full hardware integration with launcher motors/actuators.
- End-to-end voice-commanded physical shooting in closed loop.
- Final industrial-grade real-time optimization.

## 1.5 Thesis Contributions
This thesis contributes:
- A complete garage-specific multi-camera CV pipeline in world metric units.
- Robust practical calibration workflow under real deployment constraints.
- Error-characterized 3D ball and joint estimates suitable for engineering decisions.
- Implementation artifacts and scripts enabling repeatable experimentation.

---

# Chapter 2 - Literature And Technology Review

## 2.1 Multi-View Geometry For Sports Tracking
3D reconstruction from multiple calibrated cameras is a mature approach in computer vision [1], [2]. In practical systems, two components dominate final accuracy:
- Intrinsic calibration quality,
- Extrinsic/world-frame consistency.

For sports tracking, synchronized multi-view acquisition is essential because small timing shifts produce significant triangulation drift during fast motion.

## 2.2 Camera Calibration In Real Environments
ChArUco-based calibration is widely used for robust corner detection and practical board handling [3], [4]. AprilTag systems are effective for persistent environment anchoring and camera pose estimation in metric spaces [5], [6].

Compared with controlled lab setups, real garages introduce additional failure modes: uneven lighting, partially visible tags, reflections, tag contamination, and camera remounting. The calibration strategy in this thesis explicitly handles these factors with robust outlier rejection and per-camera tag filtering.

## 2.3 Ball And Pose Detection Models
The pipeline uses YOLO-family detectors for ball localization and RTMPose/MMPose for 2D body keypoints [7], [8]. Inference confidence alone is insufficient for 3D reliability; therefore, this work combines model confidence with geometric consistency checks (minimum camera count, reprojection threshold, speed gating).

## 2.4 Sensor-Based Vs Vision-Based Target Detection
Traditional training systems frequently depend on hardware gates, impact sensors, or dedicated trigger devices. A vision-based alternative can infer target crossing directly from camera data, enabling flexible target definitions (for example, 1.0x1.0 m or 1.0x1.5 m virtual planes) without additional wiring per zone.

The key tradeoff is that vision pipelines require rigorous calibration and drift management. This thesis quantifies those errors to establish operational boundaries.

## 2.5 Positioning Of This Thesis
Most prior works solve either ball tracking, pose estimation, or static calibration independently. The practical novelty here is the integrated engineering pipeline: synchronized four-camera capture, AprilTag world anchoring, joint+ball triangulation, continuous visualization, and quantitative GT-based tuning in the same deployment space.

---

# Chapter 3 - System Design And Implementation

## 3.1 Development Evolution Across Project_Cam
Project evolution followed three technical phases:

### Phase A: Dual-camera baseline
Early work in `Sport_center` and `src/core` focused on stereo/dual-view ball reconstruction and rendering. This phase validated basic triangulation and speed estimation logic.

### Phase B: Lab 4-camera reconstruction
The lab pipeline produced multi-camera renders such as `output/videos/final_3d_robot.mp4`, combining body and ball in a reconstructed scene. It proved feasibility but used lab-specific calibration.

### Phase C: Garage migration and unified pipeline
`garage_lab_combined` introduced a new world map, new camera mappings, revised calibration, GT protocols, and unified scripts for capture, processing, evaluation, and rendering.

## 3.2 Hardware And Runtime Configuration
- Cameras: four fixed Hikvision DS-E12 USB cameras.
- Runtime profile: 1280x720, ~15 FPS capture.
- World units: millimeters.
- Camera role mapping persisted via `/dev/v4l/by-path` entries in `garage_lab_combined/config/cameras.yaml`.

## 3.3 Arena Coordinate System And AprilTag Map
Arena dimensions from `garage_lab_combined/cal/extrinsics/Dimensions.txt`:
- X = 6230 mm
- Y = 3050 mm
- Z = 2950 mm

World origin is set at North-East floor corner. AprilTag corners are stored as explicit `c0..c3` metric points for IDs 0..23. This enables direct world-anchored PnP calibration and consistent triangulation scale.

## 3.4 Intrinsics Calibration Pipeline
Scripts:
- `garage_lab_combined/scripts/auto_capture_charuco_multi.py`
- `garage_lab_combined/scripts/calibrate_intrinsics_from_images.py`

A full A4 ChArUco board (7x10, 29.7 mm square, 22.275 mm marker, dictionary 4x4_1000) was used to improve corner coverage and reduce center-detection failures seen in older captures.

### Table 3.1 - Final camera intrinsics at 1280x720
| Camera | Frames Used | Reprojection Error (px) |
|---|---:|---:|
| camNorth | 77 | 0.7279 |
| camEast  | 78 | 0.3998 |
| camSouth | 77 | 0.4844 |
| camWest  | 80 | 0.3570 |

These values indicate strong per-camera lens models for the target resolution.

## 3.5 Extrinsics Calibration Pipeline
Main script:
- `garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py`

Method highlights:
- AprilTag detection (`DICT_APRILTAG_36h11`),
- Iterative robust PnP,
- Point-level and tag-level outlier rejection,
- Optional per-camera include/exclude tag maps,
- Camera-position drift check against measured camera coordinates.

Final extrinsics used in downstream processing:
- `garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json`

### Table 3.2 - Final extrinsics quality
| Camera | RMSE (px) | Position Error (m) | Inlier Points |
|---|---:|---:|---:|
| camNorth | 1.44 | 0.266 | 651 |
| camEast  | 1.18 | 0.218 | 668 |
| camSouth | 5.23 | 0.174 | 672 |
| camWest  | 2.26 | 0.116 | 1001 |

South camera had the highest reprojection error after a physical shift and partial re-calibration; this was accepted temporarily for ongoing pipeline work and flagged for future refinement.

## 3.6 Synchronized Recording
Script:
- `garage_lab_combined/scripts/record_short_clips_multi.py`

Features:
- Simultaneous 4-camera clip recording,
- Optional pre-record delay to allow operator positioning,
- Stable naming per trial,
- Per-clip metadata logging.

Synchronization was manually verified with flashlight events and frame trimming when needed.

## 3.7 3D Ball + Skeleton Processing
Script:
- `garage_lab_combined/scripts/process_4cam_to_3d.py`

Pipeline steps per frame:
1. Ball detection from all views (YOLO model).
2. Per-camera point undistortion.
3. Multi-view triangulation.
4. Reprojection-error-based camera rejection.
5. Optional speed gate and EMA smoothing for ball track.
6. Person keypoint detection (RTMPose).
7. Per-camera target person selection to reduce identity switching.
8. Joint-wise triangulation with minimum camera constraints.

Output format is frame-wise JSON with:
- `ball` (3D point),
- `ball_cams` and `ball_reproj_px`,
- `joints` (17 COCO keypoints in 3D).

## 3.8 Unified 3D Visualization
Main rendering scripts:
- `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- `garage_lab_combined/scripts/render_apriltag_arena_360.py`
- `garage_lab_combined/scripts/live_4cam_arena_view.py`

Delivered visual modes:
- Offline presentation render (arena + tags + cameras + skeleton + ball),
- 360-degree orbit view of reconstructed arena,
- Live popup visualization for real-time monitoring.

---

# Chapter 4 - Experimental Protocols And Metrics

## 4.1 Ball Static Ground-Truth Protocol
Protocol document:
- `garage_lab_combined/gt_eval/BALL_DETECTION_PIPELINE.md`

Dataset:
- 36 fixed points (3 x-values x 3 y-values x 4 z-values),
- All coordinates in mm,
- 4-second synchronized clip per trial.

Evaluation script:
- `garage_lab_combined/scripts/evaluate_ball_static_gt.py`

## 4.2 Dynamic Ball Protocol
Three dynamic clips were collected:
- `ball_slow` (20 s): stability test,
- `ball_fast` (20 s): stress under motion blur/high speed,
- `no_ball` (15 s): false-positive check.

## 4.3 Joint-Touch Ground-Truth Protocol
Protocol document:
- `garage_lab_combined/gt_eval/JOINT_TOUCH_3D_PIPELINE.md`

Dataset design:
- 81 planned trials,
- Joints: `left_shoulder`, `right_hip`, `right_knee`,
- 9 XY positions x 3 platform levels x 3 joints.

Evaluation script:
- `garage_lab_combined/scripts/evaluate_pose_joint_touch_gt.py`

## 4.4 Evaluation Metrics
For both ball and joints, metrics included:
- Per-trial error vector: `ex, ey, ez`,
- Norm error: `|e| = sqrt(ex^2 + ey^2 + ez^2)`,
- Aggregate statistics: mean, median, RMSE, P90, P95, max,
- Axis bias: mean `ex`, `ey`, `ez`,
- Static precision: frame-to-frame spread during hold windows,
- Detection quality: valid-frame ratio, cameras used, reprojection error.

## 4.5 Correction Models
The evaluation pipeline exports correction models:
- Global bias compensation,
- Per-axis linear correction (`gt ~= a*est + b`),
- Joint-specific bias terms (for pose).

These models are diagnostic and optional at run time. They are not a replacement for proper recalibration when camera geometry changes.

---

# Chapter 5 - Results And Analysis

## 5.1 Calibration Quality Summary
Intrinsics quality was strong for all cameras (<0.73 px reprojection). Extrinsics were acceptable for three cameras with low reprojection error, while camSouth remained weaker after physical movement and partial replacement of only one camera extrinsics.

This confirms an important practical fact: in real deployments, camera movement immediately invalidates geometric assumptions and must trigger targeted or full recalibration.

## 5.2 Ball Static GT Results (36 points)
Source:
- `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_static_raw/summary_metrics.json`
- `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_static_corrected/summary_metrics.json`

### Table 5.1 - Ball static results
| Metric | Raw | Corrected |
|---|---:|---:|
| Mean error (mm) | 150.77 | 95.17 |
| Median error (mm) | 156.55 | 84.18 |
| RMSE (mm) | 167.39 | 102.23 |
| P95 (mm) | 288.34 | 166.51 |
| Max (mm) | 361.83 | 214.60 |
| Mean detection ratio | 1.000 | 1.000 |
| Mean cameras used | 2.87 | 2.87 |
| Mean reprojection (px) | 6.01 | 6.01 |

Interpretation:
- Raw static localization had a clear systematic bias, mainly negative in Z and positive in X.
- Axis-wise correction removed mean bias and significantly reduced error statistics.
- However, corrected performance still remains above aggressive control targets (<60 mm mean), so calibration/visibility improvements remain required.

## 5.3 Dynamic Ball Results
Source:
- `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_dynamic_summary.json`

### Table 5.2 - Dynamic ball validation
| Clip | Detect Ratio | Mean Reproj (px) | Jump P95 (mm) | Max Jump (mm) |
|---|---:|---:|---:|---:|
| ball_slow | 0.975 | 4.03 | 58.16 | 173.07 |
| ball_fast | 0.891 | 6.51 | 462.70 | 814.46 |
| no_ball | 0.000 | - | - | - |

Interpretation:
- Slow motion tracking is stable and practically usable.
- Fast throws expose expected limitations from blur, occlusion, and low camera overlap.
- No-ball test showed zero false positives in that session, which is a positive sign for trigger reliability.

## 5.4 Joint-Touch 3D Results
Source:
- `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/reports/summary_metrics.json`

### Table 5.3 - Joint-touch summary
| Metric | Value |
|---|---:|
| Planned trials | 81 |
| Valid trials | 62 |
| Missing/failed | 19 |
| Mean error (mm) | 143.38 |
| RMSE (mm) | 147.73 |
| P95 (mm) | 198.73 |
| Max (mm) | 217.34 |
| Mean detection ratio | 1.000 |

Per-joint mean error:
- left_shoulder: 164.38 mm
- right_hip: 150.38 mm
- right_knee: 110.03 mm

Interpretation:
- System precision during static holds is high (small frame-to-frame spread), but absolute bias remains significant.
- Shoulder is hardest due to higher Z and pose/model uncertainty.
- Result quality is currently sufficient for visualization and coarse targeting, but not sufficient for high-precision autonomous impact targeting.

## 5.5 Root-Cause Analysis
Observed dominant error sources:
1. Camera movement between sessions and partial recalibration mismatch.
2. Limited camera overlap for some workspace regions.
3. Ball visibility often only from 2 cameras.
4. Motion blur and occlusion in fast throws.
5. Human GT uncertainty in joint-touch experiments (operator cannot place anatomical landmarks with millimeter repeatability).

## 5.6 Key Engineering Takeaway
The pipeline is mature enough for:
- calibrated 3D visualization,
- quantitative evaluation,
- identifying where and why errors happen.

The pipeline is not yet ready for high-accuracy closed-loop launcher control without additional geometric hardening and rigid-target validation.

---

# Chapter 6 - Novelty, Innovation, And Practical Significance

## 6.1 Practical Novelty
The main novelty is system-level integration in a real non-lab environment:
- AprilTag-defined metric arena,
- four-camera synchronized capture,
- simultaneous 3D ball + skeleton reconstruction,
- goal/target reasoning in a common world frame,
- quantitative GT protocols for both ball and body landmarks.

Most similar training setups treat launchers as open-loop output devices. This work reframes the launcher as a future closed-loop agent that can react to perceived 3D context.

## 6.2 Replacing Dedicated Target Sensors With Vision
A critical innovation direction is replacing distributed target sensors with camera-based event detection:
- Define targets in world coordinates (for example 1.0x1.0 m and 1.0x1.5 m planes),
- Detect ball crossing events by reconstructed 3D trajectory and plane intersection,
- Validate hits without adding wired sensors at every target.

Benefits:
- Reconfigurable targets in software,
- Less physical maintenance,
- Shared sensing for both targeting and analytics.

## 6.3 Why This Matters For Stakeholders
Stakeholders expecting near-finished launcher intelligence should see this project as a staged delivery:
- Stage delivered now: calibrated perception stack + quantified error map.
- Stage pending: command-to-shot control and safe hardware actuation.

This is a defensible engineering progression because control quality cannot exceed perception quality.

---

# Chapter 7 - Intelligent Launcher Integration Roadmap

## 7.1 Current Status (As Of 2026-03-11)
Implemented:
- 4-camera calibrated perception in shared world frame,
- ball and skeleton 3D reconstruction,
- target/zone modeling capability in 3D,
- GT-based accuracy evaluation and bias modeling,
- live/offline visualization.

Not yet implemented end-to-end:
- voice-command interface bound to live target selection,
- launcher kinematic/ballistic solver linked to actuator commands,
- real hardware feedback loop with shot verification.

## 7.2 Proposed Closed-Loop Architecture
1. Voice input: command parser maps utterances to target semantics (`left arm`, `right leg`, `body`, `head`).
2. Target resolver: convert semantic label to selected 3D keypoint with temporal confidence checks.
3. Safety gate: require stable estimate over N frames, minimum 3-camera support, and confidence threshold.
4. Shot planner: solve launch angle and speed using projectile model and launcher calibration.
5. Actuation layer: send command to launcher controller.
6. Post-shot verifier: cameras confirm whether trajectory intersected commanded target zone.

## 7.3 Ballistic Model (Engineering Form)
For a launcher-origin point \((x_0, y_0, z_0)\) and target \((x_t, y_t, z_t)\), required initial velocity \(v_0\) and launch angles can be estimated from projectile equations with gravity and drag approximations. In practice, empirical calibration is required because launcher mechanics introduce non-ideal behavior.

Planned approach:
- Fit a launcher response model from measured shots,
- Use model predictive correction to reduce miss distance,
- Keep hard safety constraints on shot envelope and no-fire zones.

## 7.4 Safety And Reliability Requirements
Before autonomous shots:
- Rigid-target GT mean error should be <= 60 mm and P95 <= 90 mm,
- Camera health monitor should detect drift/movement,
- No-fire interlock for low confidence or occluded target,
- Human-safe exclusion zones and emergency stop must be active.

## 7.5 Implementation Phases
### Table 7.1 - Integration phases
| Phase | Scope | Exit Criterion |
|---|---|---|
| P1 | Perception freeze | stable calibration + GT report accepted |
| P2 | Voice command parser | command-to-keypoint mapping verified offline |
| P3 | Shot planner simulation | predicted miss distance under threshold in simulation |
| P4 | Hardware-in-the-loop | controlled test shots with manual confirmation |
| P5 | Closed-loop trials | automatic command->shot->verification cycle |

---

# Chapter 8 - Conclusion And Future Work

## 8.1 Conclusion
This thesis established a full multi-camera 3D perception framework for a garage football training setup. The pipeline now provides synchronized capture, robust calibration, 3D triangulation of ball and body keypoints, and integrated world-frame visualization. Most importantly, it provides quantified accuracy and bias measurements rather than only qualitative demos.

Ball tracking results show good practical stability in static and slow dynamic scenarios, with clear degradation under high-speed throws. Joint localization is operational but still biased for precise control applications. These outcomes are expected for a first end-to-end deployment in a constrained real environment and give a concrete path for improvement.

The project therefore meets its current technical objective: building and validating the perception backbone required for intelligent launcher control.

## 8.2 Future Work
Priority next steps:
1. Run rigid-target GT campaign after final camera lock and full recalibration.
2. Improve overlap and tag coverage for 3-camera minimum in most workspace regions.
3. Integrate command parser and target resolver.
4. Build launcher response model and ballistic solver with safety gates.
5. Execute staged hardware-in-the-loop tests and close the loop with shot verification.

When these steps are completed, the system can transition from "3D analytics and visualization" to a true smart training platform where commanded body-part targeting is executed and verified automatically.

---

# Bibliography/References
[1] Hartley, R., and Zisserman, A., 2004, *Multiple View Geometry in Computer Vision*, 2nd ed., Cambridge University Press, Cambridge, UK.

[2] Szeliski, R., 2022, *Computer Vision: Algorithms and Applications*, 2nd ed., Springer, Cham, Switzerland.

[3] Garrido-Jurado, S., Munoz-Salinas, R., Madrid-Cuevas, F. J., and Marin-Jimenez, M. J., 2014, "Automatic generation and detection of highly reliable fiducial markers under occlusion," *Pattern Recognit.*, 47(6), pp. 2280-2292.

[4] OpenCV Documentation, 2026, "ArUco and ChArUco calibration modules," https://docs.opencv.org, accessed Mar. 11, 2026.

[5] Olson, E., 2011, "AprilTag: A robust and flexible visual fiducial system," *Proc. IEEE Int. Conf. Robot. Autom.*, pp. 3400-3407.

[6] Wang, J., Olson, E., and Kaess, M., 2016, "AprilTag 2: Efficient and robust fiducial detection," *Proc. IEEE/RSJ Int. Conf. Intell. Robots Syst.*, pp. 4193-4198.

[7] Jocher, G., et al., 2023-2026, "Ultralytics YOLO documentation and implementation notes," https://docs.ultralytics.com, accessed Mar. 11, 2026.

[8] DAI, X., et al., 2023, "RTMPose: Real-Time Multi-Person Pose Estimation based on MMPose," OpenMMLab Technical Documentation, https://mmpose.readthedocs.io, accessed Mar. 11, 2026.

[9] Bishop, C. M., 2006, *Pattern Recognition and Machine Learning*, Springer, New York, NY.

[10] Project_Cam Repository, 2026, "Garage unified pipeline scripts and reports," internal technical artifact, `/home/hanush/Desktop/Project_Cam`.

[11] `garage_lab_combined/scripts/process_4cam_to_3d.py`, 2026, internal implementation artifact.

[12] `garage_lab_combined/scripts/calibrate_extrinsics_apriltag_robust.py`, 2026, internal implementation artifact.

[13] `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_static_raw/summary_metrics.json`, 2026, internal experiment report.

[14] `garage_lab_combined/gt_eval/ball_tuning_20260306_164519/reports_dynamic_summary.json`, 2026, internal experiment report.

[15] `garage_lab_combined/gt_eval/joint_tuning_20260310_124311/reports/summary_metrics.json`, 2026, internal experiment report.

[16] `garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json`, 2026, internal calibration output.

[17] `garage_lab_combined/cal/intrinsics/camNorth_intrinsics.json`, `camEast_intrinsics.json`, `camSouth_intrinsics.json`, and `camWest_intrinsics.json`, 2026, internal calibration outputs.

[18] `MSc(ECE)_Handbook_v-1 11-06-2025_MB.pdf`, 2025, School of Engineering and Digital Sciences, Nazarbayev University.

---

# Appendices

## Appendix A - Key Project Paths
- `garage_lab_combined/README.md`
- `garage_lab_combined/config/cameras.yaml`
- `garage_lab_combined/config/runtime.yaml`
- `garage_lab_combined/cal/extrinsics/Dimensions.txt`
- `garage_lab_combined/cal/extrinsics/extrinsics_final_20260309_162025.json`
- `garage_lab_combined/scripts/process_4cam_to_3d.py`
- `garage_lab_combined/scripts/render_arena_ball_skeleton.py`
- `garage_lab_combined/scripts/live_4cam_arena_view.py`
- `garage_lab_combined/gt_eval/BALL_DETECTION_PIPELINE.md`
- `garage_lab_combined/gt_eval/JOINT_TOUCH_3D_PIPELINE.md`

## Appendix B - Current GT Result Snapshot
- Ball static raw: mean 150.77 mm, RMSE 167.39 mm, P95 288.34 mm
- Ball static corrected: mean 95.17 mm, RMSE 102.23 mm, P95 166.51 mm
- Ball dynamic slow/fast/no-ball detect ratio: 0.975 / 0.891 / 0.000
- Joint-touch: 62/81 valid, mean 143.38 mm, P95 198.73 mm
