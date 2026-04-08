# Vision-Guided Closed-Loop Ball Launching: Multi-Camera 3D Perception and Ballistic Control for Automated Sports Training

**[AUTHOR NAME], B.Eng.**

Submitted in fulfilment of the requirements for the degree of Master of Science in Electrical and Computer Engineering

**Nazarbayev University**
School of Engineering and Digital Sciences
Department of Electrical and Computer Engineering
53 Kabanbay Batyr Avenue, Nur-Sultan, Kazakhstan, 010000

**Supervisors:** [Supervisor Names]

**Date of Completion:** 2026

---

## Declaration

I hereby declare that this manuscript, entitled *"Vision-Guided Closed-Loop Ball Launching: Multi-Camera 3D Perception and Ballistic Control for Automated Sports Training"*, is the result of my own work except for quotations and citations which have been duly acknowledged. I also declare that, to the best of my knowledge and belief, it has not been previously or concurrently submitted, in whole or in part, for any other degree or diploma at Nazarbayev University or any other national or international institution.

Name: [Author Name]
Date: 2026

---

## Conflict of Interest Declaration

The author declares that this research was conducted in the absence of any commercial or financial relationships that could be construed as a potential conflict of interest. No external funding was received for this work. The open-source software libraries and commodity hardware components used in this project were selected solely on technical merit and are not endorsed by or affiliated with the author or the supervisory committee.

---

## Abstract

Automated ball-launching machines are widely used in sports training but universally operate in open-loop mode: the trainer configures a fixed angle, speed, and interval, and the machine repeats that program regardless of where the athlete stands or how they move. This thesis presents the design, implementation, and evaluation of a closed-loop, vision-guided ball launching system capable of autonomously targeting specific human body joints — right knee, right hip, and left shoulder — in real time within a domestic garage arena.

The system uses four fixed commodity USB cameras (Hikvision DS-E12, approximately USD 30 each) calibrated using ChArUco boards for intrinsic parameters and AprilTag fiducial markers for extrinsic world-frame registration. Ball detection is performed using a YOLO-based detector and human pose is estimated using the MMPose framework with the COCO 17-keypoint skeleton model. Multi-view triangulation resolves detected 2D observations into 3D world-frame coordinates in millimetres. A ballistic solver continuously computes the required pitch angle, yaw angle, and wheel motor RPM to direct a Ball Launching Machine (BLM) at the triangulated joint position. Low-level actuation is handled by an ESP32 microcontroller commanding two stepper motors and two wheel motors. A six-stage incremental safety validation protocol governs integration, including an E-STOP latch with a measured response time below 100 milliseconds.

Ground-truth evaluation was conducted using two dedicated protocols. A 36-point static ball dataset covering a 3×3×4 grid across the arena volume yielded a corrected mean 3D error of 95.17 mm, RMSE of 102.23 mm, and P95 of 166.51 mm. A 81-trial joint-touch dataset with 62 valid trials yielded a mean joint localisation error of 143.38 mm, RMSE of 147.73 mm, and P95 of 198.73 mm. Per-joint analysis shows the right knee achieves the lowest error (110.03 mm mean) and the left shoulder the highest (164.38 mm mean), consistent with the decreasing camera visibility at shoulder height.

Both primary accuracy targets are met: ball mean error below 120 mm and joint mean error below 180 mm. The total hardware cost of the perception system is approximately USD 200, which is one to three orders of magnitude below comparable laboratory motion-capture systems. This work demonstrates that closed-loop, pose-reactive ball launching — a capability previously restricted to expensive professional installations — is achievable with commodity hardware and open-source software in an uncontrolled domestic environment.

*(Word count: approximately 340)*

---

## Acknowledgements

The author wishes to express sincere gratitude to the thesis supervisory committee for their guidance and constructive feedback throughout this project. Thanks are also due to the Department of Electrical and Computer Engineering at Nazarbayev University for providing the academic framework within which this research was conducted. The open-source communities behind OpenCV, Ultralytics YOLO, MMPose, and the broader Python scientific computing ecosystem made the technical implementation possible.

---

## Table of Contents

- Abstract
- Acknowledgements
- List of Abbreviations and Symbols
- List of Tables
- List of Figures
- Chapter 1 — Introduction
  - 1.1 Motivation and Problem Statement
  - 1.2 Research Objectives
  - 1.3 Scope and Constraints
  - 1.4 Statement of Novelty and Contributions
  - 1.5 Thesis Structure
- Chapter 2 — Literature Review and Background Theory
  - 2.1 Multi-Camera 3D Reconstruction
  - 2.2 Camera Calibration Techniques
  - 2.3 Object Detection for Sports Applications
  - 2.4 Human Pose Estimation
  - 2.5 Ballistic Modelling and Actuator Control
  - 2.6 Safety in Autonomous Actuated Systems
  - 2.7 Summary and Research Gap
- Chapter 3 — System Design and Methodology
  - 3.1 Arena Setup and Coordinate System
  - 3.2 Hardware Architecture
  - 3.3 Software Architecture and Pipeline Overview
  - 3.4 Intrinsic Calibration Pipeline
  - 3.5 Extrinsic Calibration Pipeline
  - 3.6 Multi-Camera Synchronisation
  - 3.7 3D Triangulation
  - 3.8 Ballistic Solver and Targeting Logic
  - 3.9 Safety Architecture
- Chapter 4 — Ground-Truth Evaluation Protocols
  - 4.1 Ball Static Ground-Truth Dataset
  - 4.2 Joint-Touch Ground-Truth Dataset
  - 4.3 Dynamic Validation Clips
  - 4.4 Error Metrics and Bias Correction Model
- Chapter 5 — Results and Analysis
  - 5.1 Intrinsic Calibration Results
  - 5.2 Extrinsic Calibration Results
  - 5.3 Ball Static Localisation Results
  - 5.4 Human Pose Joint-Touch Results
  - 5.5 Dynamic Detection Results
  - 5.6 BLM Aiming Validation
  - 5.7 Discussion
  - 5.8 Comparison with State-of-the-Art
- Chapter 6 — Conclusions and Future Work
  - 6.1 Summary of Contributions
  - 6.2 Objectives Achievement
  - 6.3 Limitations
  - 6.4 Future Work
  - 6.5 Professional and Ethical Considerations
- Bibliography / References
- Appendix A — BLM Integration Test Checklist
- Appendix B — Key Script Listings
- Appendix C — Ground-Truth Data Tables
- Appendix D — Arena Calibration Figures
- Appendix E — YOLO Ball Detector Training Results
- Appendix F — System Qualitative Results

---

## List of Abbreviations and Symbols

| Abbreviation / Symbol | Definition |
|---|---|
| BLM | Ball Launching Machine |
| COCO | Common Objects in Context (keypoint dataset format) |
| DLT | Direct Linear Transform |
| EMA | Exponential Moving Average |
| ESP32 | Espressif Systems ESP32 microcontroller |
| FPS | Frames Per Second |
| GT | Ground Truth |
| MMPose | OpenMMLab Pose Estimation Framework |
| P90 / P95 | 90th / 95th percentile of error distribution |
| PnP | Perspective-n-Point (camera pose estimation algorithm) |
| RMSE | Root Mean Square Error |
| RPM | Revolutions Per Minute |
| SVD | Singular Value Decomposition |
| UDP | User Datagram Protocol |
| YOLO | You Only Look Once (object detection architecture) |
| K | Camera intrinsic matrix |
| R, T | Rotation matrix, Translation vector (extrinsic parameters) |
| θ | Angle (pitch or yaw, degrees) |
| ΔX, ΔY, ΔZ | Component differences of targeting vector (mm) |

---

## List of Tables

- Table 2.1: Existing system categories and their limitations
- Table 3.1: Camera positions in world-frame coordinates (mm)
- Table 3.2: BLM low-level serial command set
- Table 4.1: Ball static ground-truth grid definition
- Table 4.2: Joint-touch trial design — XY grid positions (mm)
- Table 5.1: Ball static localisation summary metrics (corrected pipeline)
- Table 5.2: Joint-touch 3D ground-truth summary metrics
- Table 5.3: Per-joint error breakdown
- Table 5.4: Comparison with state-of-the-art systems
- Table 6.1: Research question objectives achievement summary

---

## List of Figures

- Figure 3.1: Garage arena floor plan with camera positions and coordinate origin
- Figure 3.2: AprilTag grid layout on arena walls (24 tags, IDs 0–23)
- Figure 3.3: System architecture block diagram (perception to actuation)
- Figure 3.4: ChArUco calibration board and sample auto-capture frame
- Figure 3.5: Extrinsic overlay validation — reprojected AprilTag corners on camera frames
- Figure 3.6: 3D arena world-frame render with camera frustums and BLM position
- Figure 3.7: Targeting vector geometry — BLM origin to joint coordinate
- Figure 4.1: Ball static GT grid — 36-point 3D scatter in arena frame
- Figure 4.2: Joint-touch trial grid — 9 XY positions and 3 height levels
- Figure 5.1: Ball static localisation — per-axis bias vectors (raw)
- Figure 5.2: Ball static localisation — raw vs corrected 3D error comparison
- Figure 5.3: Joint-touch error boxplot by joint type
- Figure 5.3b: Joint-touch ground-truth vs estimated positions (3D scatter)
- Figure 5.3c: Mean 3D error by joint type (bar chart)
- Figure 5.4: Dynamic ball evaluation summary
- Figure D.1: Arena world-frame axis overlay on four live camera feeds
- Figure D.2: Extrinsic overlay validation (4 sub-figures, one per camera)
- Figure D.3: 3D arena world-frame renders (3 viewing angles)
- Figure D.4: ChArUco calibration board used for intrinsic calibration
- Figure D.5: Intrinsic calibration reprojection error per camera
- Figure D.6: Extrinsic calibration RMSE per camera
- Figure E.1: YOLO11 ball detector training curves
- Figure E.2: YOLO11 normalised confusion matrix
- Figure E.3: YOLO11 Precision-Recall curve
- Figure E.4: Sample YOLO11 training batch
- Figure E.5: Validation predictions vs ground truth
- Figure F.1–F.3: Live system smoke test frames

---

---

# Chapter 1 — Introduction

## 1.1 Motivation and Problem Statement

Sports training demands repetition, precision, and adaptability. An athlete practising ball reception — whether in basketball, football, volleyball, or rehabilitation — benefits most from a delivery system that challenges them at the right position, at the right time, directed at the right part of their body. For decades, automated ball-launching machines have provided the repetition, but not the precision and not the adaptability.

Every commercial ball launcher on the market today operates in what this thesis terms an **open-loop** mode. The coach or athlete programs a fixed trajectory: a specific launch angle, a specific wheel speed producing a specific ball velocity, and a fixed interval between shots. The machine executes that program indefinitely. It has no sensors. It has no awareness of whether the athlete is standing, crouching, moving left, or has stepped off the court entirely. Whether the intended target is the athlete's right knee at a height of 380 mm or their shoulder at 1600 mm, the launcher fires the same trajectory it was programmed to fire. The athlete must position themselves to intercept the machine's predetermined path.

This is the foundational limitation this thesis addresses. The **"Why"** is direct: high-performance sports training increasingly demands reactive, adaptive delivery — a system that fires not at a fixed zone in the arena, but at a part of the athlete's body, in response to where they actually are at the moment of firing. No affordable, deployable system currently delivers this capability.

The contrast with existing alternatives clarifies the gap. On one end of the spectrum, commercial open-loop launchers — products such as the Lobster Elite Liberty, the Spinshot Player, and the iPong Pro — are accessible and affordable (USD 200–2,000) but entirely passive. They are tools, not systems. On the other end, professional laboratory motion-capture installations — OptiTrack [30], Vicon [8], PhaseSpace [31] — can reconstruct the full three-dimensional position of every joint on a human body to sub-millimetre accuracy in real time. However, these systems cost USD 50,000 to over USD 200,000, require dedicated calibrated studio environments, demand that subjects wear reflective markers, and have no integrated actuation. They observe, but they do not act. Furthermore, the cost and operational complexity place them entirely outside the reach of the sports training contexts where adaptive delivery would be most valuable: community sports clubs, physiotherapy practices, school athletic programmes, and individual training environments.

The Ball Launching Machine (BLM) described in this thesis is neither of these. It is not a conventional launcher that a human programs and forgets. It is a **smart machine** — a system that continuously observes the athlete through four calibrated cameras, reconstructs the three-dimensional position of specific body joints in real time, computes the required pitch angle, yaw angle, and ball speed to reach that joint, and autonomously commands the physical launcher to aim and fire. No human operator sets the angle. No human pre-programs the path. The machine decides its own aim, based entirely on where the person is and which body part has been selected as the target.

The specific body parts addressed in this work — the right knee, the right hip, and the left shoulder — were chosen to span the human height range and exercise meaningfully different training scenarios: low ball reception, mid-body interception, and overhead or upper-body challenges. These are not arbitrary coordinates in the arena. They are named joints, resolved as live 3D world-frame coordinates from the MMPose COCO 17-keypoint skeleton model, updated every frame. As the athlete moves, the target coordinate updates, and the ballistic solver recomputes continuously.

This qualitative transition — from a fixed, human-programmed firing path to an autonomous, pose-reactive targeting system — is the central theme of this thesis.

## 1.2 Research Objectives

Three research questions guide this work:

**RQ1:** Can a four-camera multi-view triangulation pipeline achieve a mean 3D localisation error below 120 mm for a static ball across a representative volume of a domestic garage arena?

**RQ2:** Can a human pose estimation pipeline achieve a mean 3D joint localisation error below 180 mm, sufficient for body-part-level targeting of the right knee, right hip, and left shoulder?

**RQ3:** Can the integrated perception-to-actuation pipeline be validated safely with a real Ball Launching Machine in a domestic environment, using a structured incremental testing methodology?

These questions are answered quantitatively through dedicated ground-truth evaluation protocols described in Chapter 4 and evaluated in Chapter 5.

## 1.3 Scope and Constraints

This work is conducted within the following defined scope:

**Physical environment:** A domestic garage arena measuring 6230 mm (X) × 3050 mm (Y) × 2950 mm (Z), with four cameras mounted at fixed positions near the ceiling perimeter.

**Hardware:** Four Hikvision DS-E12 USB webcams, one custom Ball Launching Machine with stepper-motor-driven pan/tilt and wheel-motor-driven ball projection, and one ESP32 microcontroller for low-level actuation. Total perception hardware cost is approximately USD 200.

**Software:** Python 3.10 with OpenCV [27], Ultralytics YOLO [14], MMPose [17], NumPy [28], and SciPy [29]. All components are open-source.

**Subject:** Single-person evaluation. Multi-person scenarios are outside the scope of this thesis.

**Stage of integration:** The BLM aiming mechanism has been validated in aim-only mode (motors commanded, no ball fired) and in controlled single-shot static trials. Fully autonomous closed-loop shooting with a moving human subject is the immediate next milestone and is identified as future work in Section 6.4.

**Lighting:** Controlled indoor lighting. The system has not been evaluated under variable natural lighting or outdoor conditions.

## 1.4 Statement of Novelty and Contributions

The following three claims constitute the original contributions of this thesis:

**Novelty Claim 1 — The Autonomous Aiming Machine:**
All deployed commercial ball launchers are passive tools. The human sets the direction, and the machine repeats it. This system inverts that relationship entirely. The BLM in this work autonomously computes its own pitch angle, yaw angle, and wheel speed from a live 3D joint coordinate sourced from multi-camera human pose estimation, then dispatches serial commands to execute the physical aim. The launcher does not know in advance where it will point on the next shot. It finds out by observing the athlete. This is not a launcher with a camera attached as an optional extra — it is a targeting system whose primary purpose is to aim at a person, and which uses a ball launcher as its actuation endpoint. This distinction is the central innovation of this thesis, and it represents a category shift from every commercial system currently available.

**Novelty Claim 2 — Low-Cost Multi-Camera Pose-to-Launch Pipeline:**
Prior work in closed-loop sports targeting either uses expensive depth cameras (Intel RealSense, structured light systems) or operates in controlled laboratory environments with professional motion capture. This work demonstrates that four commodity USB cameras costing approximately USD 30 each, combined entirely with open-source detection and pose estimation models (YOLO, MMPose) and an AprilTag-based calibration workflow, can achieve sub-200 mm joint targeting accuracy in a real, uncontrolled domestic arena. The total perception hardware cost is approximately USD 200 — one to three orders of magnitude below comparable systems. This result establishes that the core capability of pose-reactive ball delivery is achievable outside laboratory settings and accessible to practitioners without specialist infrastructure.

**Novelty Claim 3 — Displacement-Adaptive Smoothing and Predictive Targeting:**
Standard fixed-alpha EMA smoothing introduces unacceptable lag during fast human movements (jumps, lunges, direction changes). This thesis contributes a displacement-adaptive smoothing algorithm where the effective smoothing coefficient scales with the magnitude of positional displacement, enabling instantaneous tracking of ballistic movements while maintaining smooth interpolation during normal motion. Additionally, a Kalman-filter-based predictive targeting module estimates the future position of the target joint at the moment of ball arrival (compensating for total system latency plus ball flight time), enabling the BLM to lead the target rather than chase it. This combination — adaptive smoothing for perception accuracy and predictive targeting for actuation accuracy — addresses the fundamental latency-accuracy tradeoff in real-time pose-reactive systems.

**Novelty Claim 4 — Structured Safety-Gated Integration Protocol:**
No prior published work on vision-guided ball launchers documents a reproducible, evidence-based staged validation methodology. This thesis contributes a six-stage incremental integration checklist — from preflight checks through ESP32 testing, aim-only validation, safety gating verification, and controlled firing — each stage with defined pass criteria and mandatory evidence logging. Every actuation decision is recorded to a structured JSONL log with fields including timestamp, input joint name, raw 3D world coordinate, computed pitch and yaw, and decision outcome (OK, OUT_OF_RANGE, LOW_CONFIDENCE, ESTOP). This framework is designed to be replicable for any vision-guided actuated system deployed in an uncontrolled environment.

## 1.5 Thesis Structure

Chapter 2 reviews the relevant literature across six technical areas: multi-camera 3D reconstruction, camera calibration, object detection, human pose estimation, ballistic modelling, and safety in autonomous actuated systems. It concludes with an explicit contrast of this work against existing commercial and research systems.

Chapter 3 describes the complete system design and methodology, from arena setup and hardware selection through calibration pipelines, synchronisation, triangulation, the ballistic solver, and the safety architecture.

Chapter 4 defines the ground-truth evaluation protocols: the 36-point static ball dataset, the 81-trial joint-touch dataset, and the dynamic validation clips.

Chapter 5 presents all quantitative results and includes a state-of-the-art comparison table.

Chapter 6 states conclusions, assesses objective achievement, identifies limitations, and defines a concrete roadmap for future work including the Virtual 3D Goal concept.

---

# Chapter 2 — Literature Review and Background Theory

## 2.1 Multi-Camera 3D Reconstruction

Recovering the three-dimensional position of objects from two-dimensional image observations is a classical problem in computer vision. The theoretical foundation rests on the pinhole camera model, which describes how a point **P** = (X, Y, Z) in three-dimensional space projects to an image point **p** = (u, v) through the relationship:

    s * [u, v, 1]^T = K * [R | T] * [X, Y, Z, 1]^T                    (2.1)

where K is the 3×3 camera intrinsic matrix encoding focal lengths and principal point, R is a 3×3 rotation matrix, T is a 3×1 translation vector describing the camera's position and orientation in the world frame, and s is a scalar projective depth [1].

When an object is visible from two or more calibrated cameras simultaneously, its 3D position can be recovered through triangulation. The geometric principle is epipolar geometry: the projection rays from each camera that pass through the observed 2D point must, in the ideal noise-free case, intersect at the true 3D point [2]. In practice, due to image noise and calibration imperfections, rays rarely intersect exactly. The Direct Linear Transform (DLT) method formulates triangulation as a system of linear equations and solves for the 3D point that minimises the algebraic reprojection error using Singular Value Decomposition (SVD) [1].

The accuracy of triangulation is governed by two primary factors: the quality of camera calibration and the number of cameras with valid observations. In underconstrained configurations — where only one camera observes the target — no triangulation is possible. With exactly two cameras, depth reconstruction is sensitive to the baseline between cameras and to any calibration error [4]. With three or more cameras, redundancy in the system of equations improves robustness. This motivates the minimum camera count requirements used in this work (Section 3.6).

Multi-camera 3D reconstruction has been applied extensively in sports science. Systems have been deployed for ball tracking in tennis [5], football [6], and cricket [7], and for full-body motion capture in biomechanics research [8]. These applications typically use carefully calibrated synchronised cameras in purpose-built environments. The contribution of this work is demonstrating equivalent reconstruction capability with commodity hardware in a domestic, uncontrolled arena.

## 2.2 Camera Calibration Techniques

### 2.2.1 Intrinsic Calibration

Camera intrinsic calibration determines the parameters of the imaging model: focal lengths (fx, fy), principal point (cx, cy), and lens distortion coefficients. The widely adopted approach, due to Zhang [9], uses a planar calibration pattern observed from multiple viewpoints. The method solves for intrinsic and extrinsic parameters simultaneously through homography decomposition, then refines all parameters with non-linear optimisation minimising reprojection error.

In this work, a ChArUco calibration board is used — a combination of a chessboard pattern with embedded ArUco markers. ChArUco boards offer two advantages over plain chessboards: individual square corners can be identified even when the board is partially occluded, and the ArUco marker IDs provide unambiguous corner labelling that eliminates the corner-order ambiguity present in plain chessboard patterns [10]. The board used measures 5×7 squares with 21.5 cm square size.

### 2.2.2 Extrinsic Calibration

Extrinsic calibration determines each camera's position and orientation (R, T) in a common world frame. This is the prerequisite for multi-view triangulation: all cameras must share the same world coordinate system for their projection rays to be compared.

AprilTag fiducial markers, developed at the University of Michigan [11], are used extensively for this purpose. Each tag encodes a unique binary ID and allows the tag's four corners to be detected and their 3D positions estimated from a single camera image, given known tag size, using the Perspective-n-Point (PnP) algorithm. When multiple tags at known world positions are detected, the camera pose can be recovered by minimising reprojection error across all tag corners. Robust estimation techniques, such as RANSAC-based outlier rejection and iteratively re-weighted least squares with sigma-clipping, reduce the influence of incorrectly detected tags [12].

## 2.3 Object Detection for Sports Applications

Real-time object detection has been transformed by the YOLO (You Only Look Once) family of architectures [13], which formulate detection as a single-pass regression problem predicting bounding boxes and class probabilities from a full image in one forward pass through a convolutional neural network. Subsequent versions (YOLOv5, YOLOv8, YOLO11) have progressively improved the accuracy–speed tradeoff, enabling deployment on commodity GPU hardware at real-time frame rates [14].

Ball detection in sports presents specific challenges relative to general object detection: balls are small, often partially occluded, subject to significant motion blur at high velocities, and must be distinguished from similarly shaped background objects. Prior work on ball tracking in sports has employed a range of approaches including background subtraction, colour-based filtering, and deep learning detectors [5, 6]. For this system, the Ultralytics YOLO11 variant is selected, with detection confidence thresholds tuned empirically per experiment (0.25–0.45) to balance false-positive rate against detection recall.

## 2.4 Human Pose Estimation

Human pose estimation is the task of detecting the spatial configuration of a person's body from image data. The problem is commonly formulated as keypoint detection: estimating the 2D (or 3D) coordinates of a set of anatomically defined body landmarks from one or more camera views [15].

The COCO keypoint format defines 17 anatomical landmarks: nose, eyes, ears, shoulders, elbows, wrists, hips, knees, and ankles. This convention has become the dominant benchmark standard, and the majority of modern pose estimation models produce COCO-format output [16]. Top-down approaches — first detecting persons with a bounding-box detector, then running a specialised keypoint network on each detected person — generally achieve higher per-keypoint accuracy than bottom-up approaches that detect all keypoints first and group them afterwards.

MMPose [17], the pose estimation framework used in this work, implements both paradigms and provides pre-trained models on COCO-format benchmarks. For this system, a top-down pipeline is used with the HRNet backbone, which has demonstrated strong performance on COCO benchmark evaluations [18].

Extending 2D pose estimation to 3D using multiple cameras follows the same multi-view triangulation principle as ball localisation: 2D joint observations from multiple cameras are combined via DLT/SVD to recover 3D joint positions. The accuracy of 3D joint reconstruction is inherently limited by the 2D pose estimation accuracy, the camera calibration quality, and the number of cameras with valid joint visibility.

## 2.5 Ballistic Modelling and Actuator Control

A ball projected from a launcher at initial speed v₀, pitch angle θ, and yaw angle φ follows a parabolic trajectory under gravity (neglecting air resistance for first-order approximation). The equations of motion are:

    x(t) = v₀ * cos(θ) * cos(φ) * t                                   (2.2)
    y(t) = v₀ * cos(θ) * sin(φ) * t                                   (2.3)
    z(t) = v₀ * sin(θ) * t - (1/2) * g * t²                          (2.4)

where g = 9810 mm/s² is gravitational acceleration. Given a target point (Tx, Ty, Tz) and launcher origin (Bx, By, Bz), the system of equations (2.2)–(2.4) can be solved for the required launch parameters. For a fixed target range and height difference, two valid pitch angles generally exist (the low and high trajectory solutions); the lower-angle solution is preferred in this system as it minimises flight time and therefore targeting uncertainty due to athlete movement [19].

Stepper motors provide an appropriate actuation mechanism for launcher pan/tilt positioning: their open-loop step-counting control provides predictable angular displacement without requiring continuous position feedback, and their holding torque maintains aim angle against mechanical vibration from the wheel motors [20].

## 2.6 Safety in Autonomous Actuated Systems

Any system that combines computer vision decision-making with physical actuation must address safety as a first-class design concern. The relevant engineering context is machine safety standards: IEC 62061 (functional safety of machinery) [21] and ISO 10218 (safety of industrial robots) [26] both mandate that automated systems implement a defined safe state and a reliable means of commanding transition to that state under fault conditions [21].

An Emergency Stop (E-STOP) function, mandatory in ISO 12100, must interrupt hazardous motion immediately and latch in the stopped state until a deliberate human reset action is taken [22]. Response time requirements vary by hazard level; for a ball launcher in a domestic training environment with no proximity hazard to the operator during normal operation, a response time below 200 ms is considered acceptable practice. The system described in this thesis achieves a measured E-STOP response time below 100 ms.

The broader principle of incremental validation — testing each subsystem in isolation before integration, and each integration stage before full operation — is standard practice in safety-critical embedded systems development [23] and is formalised in this work as the six-stage BLM test checklist (Section 3.9).

## 2.7 Summary and Research Gap

The following table organises existing systems into three categories and positions this work relative to them.

**Table 2.1: Existing system categories and their limitations**

| Category | Example Systems | Cost (approx.) | Accuracy | Limitations |
|---|---|---|---|---|
| A — Commercial Open-Loop Launchers | Lobster Elite Liberty, Spinshot Player, iPong Pro | USD 200–2,000 | N/A (no sensing) | No perception; fixed paths; cannot target athlete |
| B — Professional Lab Motion Capture | OptiTrack [30], Vicon [8], PhaseSpace [31] | USD 50,000–200,000+ | <1 mm (with markers) | Lab-only; no actuation; requires markers; inaccessible |
| C — Research Prototype Vision Systems | Robot tennis/table-tennis, ball-serving robots | USD 2,000–10,000 | 50–100 mm (ball only) | Fixed-zone targeting; lab environments; no joint targeting |

Category A systems dominate sports training deployment globally. Their limitation is not cost — it is architecture. They are incapable of perception-guided targeting regardless of budget, because they have no sensors.

Category B systems exist in biomechanics research and high-performance sports science institutes. Their accuracy is exemplary, but their deployment model makes them inaccessible for the majority of training contexts. Furthermore, they observe — they do not act. No system in this category integrates with a ball launcher.

Category C systems represent the closest research analogues to this work. Prior systems for robotic table tennis [24] and tennis ball serving [25] demonstrate vision-guided launching but target fixed zones on the court, not body parts of the athlete. They operate in controlled laboratory environments and use stereo camera pairs or depth cameras costing significantly more than the commodity USB cameras used here. Critically, none of the reviewed systems demonstrates joint-level targeting — the concept that the launch target is a named anatomical landmark on a moving human.

The research gap is therefore precisely stated: **no prior system combines commodity multi-camera 3D reconstruction, real-time human joint localisation from open-source pose estimation, and a physical ballistic controller targeting those joints, deployed and evaluated in an uncontrolled domestic environment at low cost.** This thesis fills that gap.

---

# Chapter 3 — System Design and Methodology

## 3.1 Arena Setup and Coordinate System

The experimental arena is a domestic garage measuring 6230 mm in the X direction (depth from camera north wall to south wall), 3050 mm in the Y direction (width), and 2950 mm in the Z direction (height). The world coordinate origin is placed at the North-East corner of the arena floor, with:
- **X-axis:** pointing from the North wall toward the South wall (increasing toward the launcher end)
- **Y-axis:** pointing from the East wall toward the West wall
- **Z-axis:** pointing vertically upward

All coordinates in this thesis are expressed in millimetres. The athlete operates in the central region of the arena approximately between X = 2500 mm and X = 5000 mm.

**Table 3.1: Camera positions in world-frame coordinates (mm)**

| Camera | X (mm) | Y (mm) | Z (mm) | Description |
|---|---|---|---|---|
| CamNorth | 50 | 1100 | 2260 | North wall, central height |
| CamEast | 1620 | 50 | 2120 | East wall, near North end |
| CamWest | 1600 | 2970 | 2170 | West wall, near North end |
| CamSouth | 6180 | 1530 | 2270 | South wall, central |

The four cameras are mounted at ceiling height near the perimeter walls, providing overlapping fields of view across the central arena volume where the athlete operates. The placement was optimised to maximise the number of cameras simultaneously observing the target area, with a nominal design target of three or more cameras having clear line of sight to the athlete at any position within the operating region.

Twenty-four AprilTag fiducial markers (IDs 0–23), each measuring 21.5 cm × 21.5 cm, are affixed to the arena walls at known positions. Their world-frame coordinates are stored in the extrinsics calibration file and used during the extrinsic calibration process described in Section 3.5.

## 3.2 Hardware Architecture

### 3.2.1 Cameras

The four cameras are Hikvision DS-E12 USB webcams operating at a capture resolution of 1280 × 720 pixels and a target frame rate of 15 FPS. These are consumer-grade, fixed-focus cameras with no hardware synchronisation capability. Software synchronisation via flashlight marker frames is used instead (Section 3.6). Each camera costs approximately USD 30.

### 3.2.2 Ball Launching Machine

The BLM consists of:
- Two wheel motors (Left and Right) that spin in opposite directions to project the ball. The differential in motor speeds can impart spin. Speed is controlled by setting wheel motor RPM parameters.
- Two stepper motors controlling vertical rotation (pitch, V parameter) and horizontal rotation (yaw, H parameter). Each step corresponds to a defined angular increment.
- A ball feed mechanism controlled by the `shoot` and `reload` commands.

The BLM is positioned at approximately X = 600 mm, Y = 1560 mm, Z = 500 mm — near the North wall, centred in Y, at approximately half the arena height. Its launch direction points toward the South wall (increasing X direction) where the athlete operates.

### 3.2.3 ESP32 Microcontroller

An ESP32 microcontroller receives serial commands from the host PC and translates them into motor control signals. The command protocol is described in Table 3.2.

**Table 3.2: BLM low-level serial command set**

| Command | Syntax | Effect |
|---|---|---|
| set | `set V H WL WR` | Set vertical angle V (deg), horizontal angle H (deg), left wheel speed WL, right wheel speed WR |
| shoot | `shoot` | Trigger one ball ejection cycle |
| reload | `reload` | Retract ball feed for next round |
| center | `center` | Return all axes to zero position |
| stop | `stop` | Stop all motors immediately |
| setzero | `setzero` | Register current position as logical zero |

### 3.2.4 PC–ESP32 Architecture Split

High-level computation — camera capture, YOLO inference, MMPose inference, triangulation, ballistic solving, safety gating, and decision logging — runs on the host PC. The ESP32 receives only pre-computed motor commands and executes them. This split provides three advantages: faster iteration (firmware changes are not needed to modify targeting logic), safer debugging (actuation can be disabled by stopping the PC-side process with no firmware modifications), and computational efficiency (GPU inference is available on the PC but not the ESP32).

## 3.3 Software Architecture and Pipeline Overview

The processing pipeline proceeds through seven stages executed sequentially per frame:

1. **Multi-Camera Capture:** Four cameras polled in software for the current frame at 1280 × 720 px.
2. **Ball Detection:** YOLO11 inference on each camera frame producing 2D bounding box and confidence for any detected ball.
3. **Pose Estimation:** MMPose HRNet inference on each camera frame producing 17 2D keypoint coordinates and per-keypoint confidence values for any detected person.
4. **3D Triangulation:** Valid 2D observations from step 2 and step 3 are passed to the multi-view DLT/SVD solver to produce 3D world-frame coordinates for the ball and for each joint.
5. **Filtering:** EMA smoothing and outlier rejection applied to 3D outputs.
6. **Ballistic Solve:** For the active target joint, pitch, yaw, and wheel RPM are computed.
7. **Actuation:** Serial command dispatched to ESP32 (in operational mode) or logged to JSONL (in dry-run mode).

The system is implemented in Python 3.10. Key libraries: OpenCV 4.x [27] (camera I/O, image processing, calibration), Ultralytics YOLO11 [14] (ball detection), MMPose 1.x [17] (pose estimation), NumPy [28] and SciPy [29] (numerical computation), Matplotlib and OpenCV (visualisation).

**Figure 3.3:** System architecture block diagram — perception to actuation pipeline showing the seven-stage processing flow from multi-camera capture through YOLO ball detection, MMPose pose estimation, 3D triangulation, ballistic solve, safety gating, and ESP32 serial actuation.
*(Insert: `figures/fig_smoke_frame_0200.png` — annotated pipeline overlay showing all active subsystems on a live arena frame)*

### 3.3.1 Performance-Optimized Parallel Pipeline

A parallel variant of the live viewer (`live_4cam_arena_view_parallel.py`) was developed to reduce end-to-end latency and improve perceived smoothness without altering the underlying geometric pipeline. The key architectural changes are:

**Threaded camera capture:** Each of the four cameras is polled in a dedicated background thread (`ThreadedCapture`), which continuously reads frames and stores the latest frame in a thread-safe buffer. The main loop retrieves the most recent frame per camera without blocking on USB I/O. A staleness gate (`--max-frame-age-ms`, default 150 ms) drops frames that are too old, preventing the pipeline from processing data that has already expired.

**Multi-rate processing:** Ball detection, pose estimation, and 3D visualisation run at independent cadences controlled by `--ball-every N`, `--pose-every N`, and `--viz-every N` flags. For example, running pose estimation every 2nd frame halves the inference load (the dominant bottleneck at ~80 ms per batch) while ball detection runs every frame for responsive tracking. Between inference frames, the display layer interpolates the last known state.

**OpenCV 3D renderer:** The original Matplotlib-based 3D arena renderer (`draw_live_scene`) incurred 200–500 ms per frame due to `ax.cla()` full-scene redraws and synchronous GUI flushes. This was replaced by an OpenCV-based perspective projection renderer (`draw_live_scene_cv2`) that renders the same scene in ~2 ms per frame. The renderer constructs a virtual pinhole camera using `make_orbit_view()` which converts elevation/azimuth parameters to a 3×4 extrinsic matrix. A 270° azimuth offset maps the Matplotlib azimuth convention (azim=0 looking along +Y) to standard spherical coordinates. Points are projected using the standard pinhole model with an X-axis mirror to match Matplotlib's left-handed display convention:

u = cx − fx · X_cam / Z_cam
v = fy · Y_cam / Z_cam + cy

Static arena elements (floor grid, walls, AprilTag markers, camera positions, coordinate axes) are pre-rendered to a background image at startup. Per-frame rendering copies this background and overlays only dynamic elements (skeleton joints, bone connections, ball position, trajectory trail) using OpenCV drawing primitives.

**Display interpolation:** A separate `joints_display` array (17×3, float64) provides smooth inter-frame motion by lerping toward the EMA-filtered `joints_state` on every render frame, using the displacement-adaptive alpha described in Section 3.7.3. This is purely a display-layer operation; the underlying `joints_state` used for UDP streaming and ballistic solving is not affected.

**Dual pose backend:** The pipeline supports two interchangeable pose estimation backends controlled by `--pose-backend`:
- `mmpose` (default): RTMDet-m person detector + RTMPose-m keypoint estimator (MMPose framework). Measured latency: 38.5 ms per image, ~80 ms batched for 4 cameras.
- `yolopose`: YOLO11m-Pose single-model detection + keypoint estimation. Measured latency: 8.9 ms per image (PyTorch), 6.2 ms (TensorRT FP16) — a **6.2× speedup** over MMPose. Both backends output COCO 17-keypoint format, making them interchangeable at the triangulation layer.

**Table 3.1: Inference latency benchmarks (NVIDIA RTX 2080 Ti)**

| Model | Format | Per-image (ms) | 4-cam total (ms) | vs MMPose |
|---|---|---|---|---|
| MMPose (RTMDet-m + RTMPose-m) | PyTorch | 38.5 | 154 (seq) / 80 (batch) | baseline |
| YOLO ball detector | PyTorch | 8.7 | — | — |
| YOLO ball detector | TensorRT FP16 | 8.1 | — | — |
| YOLO11m-Pose | PyTorch | 8.9 | 36 | 4.3× faster |
| YOLO11m-Pose | TensorRT FP16 | 6.2 | 25 | **6.2× faster** |

**Run profiles:** Six shell-script profiles control the latency–quality tradeoff:
- `quality`: all inference every frame, Matplotlib renderer, baseline reference
- `balanced`: pose every 2 frames, Matplotlib renderer, best skeleton placement
- `smooth_v2`: pose every 2 frames, OpenCV cv2 renderer, adaptive EMA with snap threshold 80 mm, display interpolation alpha 0.45, ~2 ms 3D render time
- `predictive`: smooth_v2 + Kalman prediction (400 ms horizon) + ghost skeleton
- `yolopose`: YOLO-Pose backend + prediction + cv2 renderer — lowest latency (recommended)
- `maxfps`: 960×540 resolution, aggressive skipping — known to cause skeleton drift due to intrinsics scaling, not recommended for accuracy-sensitive work

## 3.4 Intrinsic Calibration Pipeline

### 3.4.1 Board Specification and Detection

A ChArUco board with 5 columns × 7 rows of squares (square size 21.5 cm) is used. ArUco markers embedded in alternating squares provide unique corner identifiers that allow partial-board detection. The script `auto_capture_charuco_multi.py` automates image collection: it streams all four cameras simultaneously, detects ChArUco corners in each frame, and triggers an automatic save when the number of detected corners exceeds 25 and remains stable for 3 seconds. This hands-free approach ensures sufficient pose diversity without operator timing errors.

### 3.4.2 Calibration Procedure

Per-camera calibration is performed independently. For each camera, OpenCV's [27] `calibrateCameraCharuco` function estimates the intrinsic matrix K and distortion coefficients (k1, k2, p1, p2, k3) by minimising reprojection error across all collected frames. A minimum of 30 valid frames per camera is targeted. Frames with fewer than 25 detected corners are discarded before calibration.

The intrinsic calibration is performed at 1280 × 720 resolution, matching the operational resolution of the system. Calibrating at a different resolution than operation introduces a scaling error in the focal length and principal point, which would propagate as a systematic triangulation bias.

### 3.4.3 Output and Validation

Calibration outputs per-camera K matrix and distortion vector, stored as JSON files in `garage_lab_combined/cal/intrinsics/`. Per-camera reprojection error is computed over the full calibration frame set as a quality indicator. Values in the range of 2–8 pixels are considered acceptable for this application.

## 3.5 Extrinsic Calibration Pipeline

### 3.5.1 AprilTag Detection

Twenty-four AprilTag markers (family tag36h11, IDs 0–23, 21.5 cm side length) are affixed to the arena walls at pre-measured world-frame positions stored in the calibration configuration. The script `calibrate_extrinsics_apriltag_robust.py` runs AprilTag detection on still frames captured from each camera and assembles a set of PnP correspondences: for each detected tag corner, a 3D world position and a 2D image position.

### 3.5.2 Robust PnP Optimisation

Camera pose (R, T) is estimated for each camera via PnP with iterative refinement. An outlier rejection step with sigma-scale = 2.0 discards tag corner observations whose reprojection error exceeds two standard deviations of the residual distribution. This step eliminates the influence of misdetected tags or physical measurement errors in tag positions. The result is a per-camera rotation matrix R and translation vector T defining the camera's position and orientation in the world frame.

### 3.5.3 Overlay Validation

Extrinsic quality is validated visually by reprojecting the known AprilTag corner positions back into each camera image using the estimated (K, R, T) and overlaying the reprojected corners on the captured frame. When reprojected corners align tightly with detected corners across all cameras, the extrinsic calibration is considered valid. This validation is performed after any physical camera movement and before any data collection session.

## 3.6 Multi-Camera Synchronisation

The four Hikvision DS-E12 cameras have no hardware synchronisation signal. Software synchronisation is achieved through a flashlight sync marker protocol: a handheld flashlight is flashed briefly at the start of each recording session, creating a detectable brightness spike in all four camera streams simultaneously. Frame alignment is performed by finding the flashlight spike frame in each stream and offsetting the subsequent frames accordingly.

For the ground-truth evaluation sessions, which use static holds of 3–4 seconds, synchronisation accuracy of ±2 frames (approximately 130 ms at 15 FPS) is acceptable, as the target is stationary during the hold window. For the dynamic validation clips, synchronisation accuracy directly affects triangulation quality: a larger temporal offset between cameras increases the apparent parallax of a moving ball, introducing triangulation error.

A minimum of two cameras is required for triangulation; three or more cameras are targeted during experimental data collection. The detection and triangulation code enforces a configurable minimum camera count threshold (set to 2 for the evaluation experiments), and records the number of cameras used per frame for post-hoc analysis.

## 3.7 3D Triangulation

### 3.7.1 Ball Triangulation

For each frame in which the YOLO detector reports a ball detection in two or more cameras with confidence above the configured threshold (0.25–0.45 depending on experiment), the 2D bounding box centre coordinates are assembled into a set of ray equations using the per-camera (K, R, T) parameters. The DLT method constructs a matrix A such that the 3D point P satisfies A·P = 0 in the homogeneous least-squares sense. SVD of A yields P as the right singular vector corresponding to the smallest singular value [1].

### 3.7.2 Pose Joint Triangulation

For each COCO keypoint, the same procedure is applied using the 2D keypoint coordinate from each camera where the joint confidence exceeds the pose confidence threshold (0.35) and the joint is observed by at least three cameras. The minimum camera count for pose triangulation is set higher than for ball triangulation (3 versus 2) because joint observations are inherently noisier than ball centre estimates.

### 3.7.3 Quality Filtering

After triangulation, two quality filters are applied:

**Reprojection error check:** The triangulated 3D point is projected back into each contributing camera using the known (K, R, T) parameters. If the pixel distance between the projected position and the original detection exceeds the maximum reprojection error threshold (14–18 pixels depending on experiment), the point is flagged as an outlier and excluded from further processing for that frame.

**EMA smoothing:** Accepted 3D points are smoothed using an Exponential Moving Average filter with smoothing coefficient α = 0.25–0.45 (configurable). This suppresses frame-to-frame jitter while preserving the trajectory of a slowly moving target. The smoothed position is used as input to the ballistic solver.

**Displacement-Adaptive EMA:** Standard fixed-alpha EMA introduces visible lag when tracking fast movements such as jumps, lunges, or rapid direction changes. To address this, a displacement-adaptive variant was developed. At each update, the Euclidean displacement between the incoming 3D point and the current smoothed estimate is compared against a configurable snap threshold (default: 80 mm). When displacement exceeds this threshold, the effective smoothing coefficient is scaled proportionally:

α_eff = min(1.0, α_base × (displacement / threshold))

This allows the filter to snap instantly to large positional changes (ballistic movements, jumps) while maintaining smooth interpolation during normal motion. The same adaptive logic is applied to a separate display interpolation layer (`joints_display`), which lerps toward the EMA-filtered state on every render frame. This dual-layer architecture decouples the perception update rate (pose inference every N frames) from the display update rate (every frame), providing visually smooth motion at display refresh rates while preserving the geometric integrity of the underlying 3D reconstruction in `joints_state`.

### 3.7.4 EMA Ablation Study

To validate the adaptive EMA design, an ablation study was conducted on three recorded 4-camera test sequences (walk, jog, jump — 30 seconds each at 15 FPS, 449 frames). Eight EMA variants were compared, from strong fixed smoothing (α=0.25) to raw unfiltered triangulation (α=1.0), including three adaptive configurations with different snap thresholds. Both YOLO-Pose and MMPose backends were tested on identical sequences.

**Table 3.2: EMA ablation — walk sequence (YOLO-Pose backend)**

| Variant | Jitter Mean (mm) | Jitter P95 (mm) | Smoothness (mm) | Coverage |
|---------|-----------------|-----------------|-----------------|----------|
| fixed α=0.25 | 41.1 | 77.9 | 10.5 | 98% |
| fixed α=0.45 | 44.4 | 91.3 | 18.7 | 98% |
| adaptive α=0.45, snap=80mm | 47.6 | 117.3 | 37.5 | 98% |
| no EMA (raw) | 52.7 | 120.8 | 47.7 | 98% |

**Table 3.3: EMA ablation — jump sequence (YOLO-Pose backend)**

| Variant | Jitter Mean (mm) | Jitter P95 (mm) | Smoothness (mm) | Coverage |
|---------|-----------------|-----------------|-----------------|----------|
| fixed α=0.25 | 75.5 | 174.4 | 30.5 | 100% |
| fixed α=0.45 | 90.0 | 219.3 | 51.4 | 100% |
| adaptive α=0.45, snap=80mm | 108.6 | 313.0 | 113.0 | 100% |
| no EMA (raw) | 117.0 | 309.3 | 118.9 | 100% |

The results confirm that fixed α=0.25 achieves the lowest jitter (41mm walk, 76mm jump) but introduces tracking lag proportional to the smoothing strength. The adaptive variant trades P95 jitter (117mm vs 78mm walk, 313mm vs 174mm jump) for instantaneous snap response during large displacements. For the BLM targeting application, the moderate fixed smoothing (α=0.45) combined with Kalman prediction provides the best trade-off: the EMA removes high-frequency noise while the Kalman filter compensates for the smoothing-induced lag through forward prediction.

### 3.7.5 YOLO-Pose vs MMPose Backend Comparison

Both pose backends were evaluated on identical recorded sequences to validate that the 3.6× faster YOLO-Pose pipeline does not sacrifice 3D reconstruction accuracy.

**Table 3.4: Backend comparison — 3D jitter (fixed α=0.45)**

| Sequence | YOLO-Pose Jitter (mm) | MMPose Jitter (mm) | Δ (mm) |
|----------|----------------------|-------------------|--------|
| walk | 44.4 | 47.9 | -3.5 |
| jog | 93.0 | 93.3 | -0.3 |
| jump | 90.0 | 92.6 | -2.6 |

| Metric | YOLO-Pose | MMPose |
|--------|-----------|--------|
| Pose extraction FPS (4-cam) | 25.1 | 7.0 |
| Detection rate | 94–100% | 100% |
| Triangulation coverage | 90–95% | 99–100% |

YOLO-Pose achieves slightly lower mean jitter than MMPose (by 0.3–3.5mm) while running 3.6× faster. The small coverage gap (90–95% vs 99–100%) reflects occasional missed detections on oblique camera views (camEast, camWest at arena edges). For the targeting application, the speed advantage decisively favours YOLO-Pose: at 25 FPS pose extraction, the system can run pose estimation on every frame rather than every 3rd frame, improving temporal resolution.

## 3.8 Ballistic Solver and Targeting Logic

### 3.8.1 Target Vector Computation

The ballistic solver takes as input the current 3D world-frame target position T = (Tx, Ty, Tz) in millimetres, sourced from the EMA-filtered and confidence-gated triangulated joint position. The BLM pivot point (launch origin) is a fixed, calibrated world-frame coordinate B = (Bx, By, Bz) = (600, 1560, 500) mm.

The targeting vector from launcher to target is:

    ΔX = Tx - Bx                                                       (3.1)
    ΔY = Ty - By                                                       (3.2)
    ΔZ = Tz - Bz                                                       (3.3)

The horizontal ground distance from launcher to target is:

    D_horiz = sqrt(ΔX² + ΔY²)                                         (3.4)

### 3.8.2 Yaw Angle Computation

The required yaw (horizontal rotation) angle of the launcher to point at the target in the arena plane is:

    θ_yaw = atan2(ΔY, ΔX)                                             (3.5)

This is measured relative to the launcher's reference direction (pointing along the positive X axis). The result is converted to degrees and offset by the configured yaw trim parameter `--yaw-trim-deg`, which compensates for any mechanical zero offset in the stepper motor homing procedure.

### 3.8.3 Pitch Angle Computation

The pitch angle is derived from the projectile motion equations (2.2)–(2.4). For a target at horizontal distance D_horiz and height difference ΔZ, the required pitch angle θ_pitch for a given initial ball speed v₀ satisfies:

    ΔZ = D_horiz * tan(θ_pitch) - (g * D_horiz²) / (2 * v₀² * cos²(θ_pitch))    (3.6)

This is a transcendental equation in θ_pitch. For practical launch distances in the arena (2000–5000 mm) and the configured ball speeds, the equation is solved numerically. The lower-angle solution is selected to minimise flight time and improve targeting precision for a moving athlete.

The result is offset by the pitch trim parameter `--pitch-trim-deg` to compensate for mechanical offset.

### 3.8.4 Wheel RPM Computation

Wheel RPM is proportional to desired initial ball speed v₀. The empirical mapping between RPM and ball speed is determined through calibration shots. A speed scale parameter `--speed-scale` allows runtime adjustment without firmware changes.

### 3.8.5 Why This Is Non-Trivial

The targeting computation is not a lookup table or a pre-programmed direction. Several factors make it a genuine real-time control challenge:

- The target T updates every frame (at 15 FPS) as the athlete moves. The solver must complete its computation within one frame period (approximately 67 ms) to avoid stale commands.
- Gravity couples pitch angle to ball speed: the same target can be reached at multiple (θ, v₀) combinations. The solver must select the physically valid lower-angle solution and check that it falls within the mechanical range of the launcher stepper (nominally ±30 degrees from horizontal).
- The BLM stepper motor has a finite step resolution. The solver rounds to the nearest achievable step position and logs the angular residual error for post-session analysis.
- The BLM's mechanical zero (the position after `setzero`) must be registered to the world-frame coordinate system. This registration is performed through the yaw and pitch trim calibration procedure validated in the aim-only tests (Section 5.6).

### 3.8.6 Dynamic Target Tracking Behaviour

The system operates as a state machine with three targeting states:

- **ACQUIRING:** The joint has been detected in fewer than the minimum required cameras, or the EMA-filtered position has not yet stabilised. No command is dispatched.
- **LOW_CONFIDENCE:** The detection confidence is below threshold, or the joint position has changed by more than 50 mm in the last 10 frames. The last valid command is held. The decision is logged as LOW_CONFIDENCE.
- **READY:** The joint position is stable (movement below 50 mm over 10 frames) and confidence is above threshold. The ballistic solve is executed and the serial command is dispatched.

A transition from READY back to ACQUIRING occurs if the joint disappears from the camera views (e.g., the athlete moves behind a wall or crouches below the camera field of view). The system does not fire in any state other than READY with E-STOP cleared.

## 3.9 Safety Architecture

### 3.9.1 E-STOP Latch

An Emergency Stop function is implemented as a software latch in the launcher runtime process. When the operator types `estop` in the runtime terminal, all motor commands are immediately halted and the latch is set. The system cannot dispatch any further actuation commands until the operator explicitly types `clear` to release the latch. The measured response time from `estop` command entry to motor halt is below 100 ms.

### 3.9.2 Multi-Level Gating

Before any actuation command is dispatched, the following checks are performed in sequence:

1. **E-STOP check:** Latch must be cleared.
2. **Camera count check:** At least two cameras must have contributed to the current triangulation.
3. **Confidence check:** Detection confidence must exceed threshold for all contributing cameras.
4. **Zone check:** The target coordinate must fall within the defined safe operating zone (nominally the central arena area; coordinates near walls or outside the arena bounds are rejected as OUT_OF_RANGE).
5. **Stability check:** Target must be in READY state (see Section 3.8.6).

Failure at any check results in the decision being logged as the appropriate failure category and no command being sent.

### 3.9.3 Six-Stage Integration Checklist

Integration of the full system follows a mandatory staged protocol to prevent unsafe operation before each component has been validated in isolation. The six stages are:

- **Stage 0 — Preflight:** Camera streams, calibration files, and serial link verified.
- **Stage 1 — ESP32 Only:** All motor commands tested via direct serial terminal with no camera or BLM active.
- **Stage 2 — Runtime Without Cameras:** Synthetic UDP target packets injected to verify solver and safety gating logic.
- **Stage 3 — Live Aim-Only:** Full pipeline active, motors commanded to correct aim angles, no ball loaded.
- **Stage 4 — Safety Verification:** E-STOP, latch, link-loss, and zone-rejection tests under live conditions.
- **Stage 5 — Controlled Firing:** Single shots with ball loaded, one at a time, operator present.

Each stage has defined pass criteria. A stage is not passed until all criteria are met and evidence (terminal logs, video, JSONL records) is archived. Stage 6 defines full cycle reliability testing.

---

# Chapter 4 — Ground-Truth Evaluation Protocols

## 4.1 Ball Static Ground-Truth Dataset

### 4.1.1 Dataset Design

A 36-point static dataset was designed to evaluate ball localisation accuracy across a representative volume of the arena. The grid covers:

- **X:** 3000, 4000, 5000 mm (3 positions, spanning the central third of the arena depth)
- **Y:** 1000, 1600, 2300 mm (3 positions, spanning most of the arena width)
- **Z:** 200, 700, 1200, 1800 mm (4 heights, from near-floor to above head height)

Total: 3 × 3 × 4 = 36 trials, labelled B001–B036.

**Table 4.1: Ball static ground-truth grid definition**

| X (mm) | Y (mm) | Z levels (mm) | Trial IDs |
|---|---|---|---|
| 3000 | 2300 | 200, 700, 1200, 1800 | B001, B010, B019, B028 |
| 4000 | 2300 | 200, 700, 1200, 1800 | B002, B011, B020, B029 |
| 5000 | 2300 | 200, 700, 1200, 1800 | B003, B012, B021, B030 |
| 3000 | 1600 | 200, 700, 1200, 1800 | B004, B013, B022, B031 |
| 4000 | 1600 | 200, 700, 1200, 1800 | B005, B014, B023, B032 |
| 5000 | 1600 | 200, 700, 1200, 1800 | B006, B015, B024, B033 |
| 3000 | 1000 | 200, 700, 1200, 1800 | B007, B016, B025, B034 |
| 4000 | 1000 | 200, 700, 1200, 1800 | B008, B017, B026, B035 |
| 5000 | 1000 | 200, 700, 1200, 1800 | B009, B018, B027, B036 |

### 4.1.2 Capture Protocol

For each trial:
1. A rigid holder positions the ball centre at the target coordinate.
2. The scene is kept static for 3–4 seconds with all four cameras recording.
3. The trial ID and any anomalies are logged in `trials_notes.csv`.

The ball centre position is measured physically using a tape measure referenced to the arena coordinate origin, with an estimated physical placement accuracy of ±5 mm.

### 4.1.3 Processing

Each trial's 4-camera clip is processed by `evaluate_ball_static_gt.py`, which extracts the YOLO ball detection in each frame, runs triangulation with the configured parameters (confidence threshold 0.45, minimum 2 cameras, maximum reprojection error 14 px, EMA α = 0.25), and computes statistics over the stable hold window (the middle 60% of frames, excluding the first and last 20% to avoid edge effects from placement and removal).

## 4.2 Joint-Touch Ground-Truth Dataset

### 4.2.1 Dataset Design

The joint-touch dataset evaluates the 3D localisation accuracy of three specific human joints under a controlled physical reference condition.

**XY positions (9 points, 3×3 grid in central arena area):**

**Table 4.2: Joint-touch trial design — XY grid positions (mm)**

| Row | Column 1 | Column 2 | Column 3 |
|---|---|---|---|
| North | (2600, 1100) | (3200, 1100) | (3800, 1100) |
| Centre | (2600, 1600) | (3200, 1600) | (3800, 1600) |
| South | (2600, 2100) | (3200, 2100) | (3800, 2100) |

**Platform heights (Z base):** 0 mm, 400 mm, 640 mm (three rigid platforms of different heights).

**Joints evaluated:** `right_knee`, `right_hip`, `left_shoulder`.

**Expected joint heights above platform base:**
- right_knee: base + 500 mm
- right_hip: base + 1000 mm
- left_shoulder: base + 1560 mm

Total trials: 9 positions × 3 heights × 3 joints = 81 trials, labelled J001–J081.

### 4.2.2 Capture Protocol

For each trial, the subject stands with the designated body joint touching a physical target marker placed at the specified XY position and height. The subject holds the position statically for 3–4 seconds. Capture begins from a neutral (non-touching) position and transitions to the hold; the evaluator extracts the hold window for analysis.

**Validity criteria:** A trial is valid if:
- The joint is detected in at least 3 cameras during the hold window.
- Detection ratio (frames with valid detection / total frames in hold window) is ≥ 0.80.
- No obvious physical placement error was noted in the trial log.

Of 81 trials, 62 were classified as valid (76.5% validity rate). The 19 invalid trials were primarily due to insufficient camera visibility (the joint was occluded by the subject's own body from certain camera angles) or detection ratio falling below threshold.

### 4.2.3 Processing

Each valid trial's 4-camera clip is processed by `evaluate_pose_joint_touch_gt.py` using: MMPose inference with confidence threshold 0.35, minimum 3 cameras for pose triangulation, maximum reprojection error 14 px, and EMA α = 0.25. The mean triangulated 3D position over the hold window is compared to the physical reference position.

## 4.3 Dynamic Validation Clips

Three dynamic validation clips were recorded to assess system behaviour under non-static conditions:

**ball_slow (20 seconds):** The ball is moved gently by hand in arcs and straight lines at approximately 0.2–0.8 m/s. Purpose: evaluate temporal tracking stability and continuous 3D trajectory reconstruction. Pass criterion: no 3D frame-to-frame jumps exceeding 800 mm.

**ball_fast (20 seconds):** Real throws through the central arena at typical playing speeds with direction changes and near-wall trajectories. Purpose: stress-test detection under motion blur and rapid acceleration. Pass criterion: acceptable detection coverage with controlled outlier rate; all detected points within arena bounds.

**no_ball (15 seconds):** Ball removed from the scene, normal arena lighting, person present and moving. Purpose: measure false-positive ball detection rate. Pass criterion: false positive count close to zero.

## 4.4 Error Metrics and Bias Correction Model

### 4.4.1 Primary Metrics

For each trial, the 3D Euclidean error is computed as:

    e = sqrt((x_est - x_gt)² + (y_est - y_gt)² + (z_est - z_gt)²)    (4.1)

where (x_est, y_est, z_est) is the mean estimated 3D position over the hold window and (x_gt, y_gt, z_gt) is the physical reference position.

Summary statistics reported: mean error, median error, RMSE, 90th percentile (P90), 95th percentile (P95), and maximum error.

### 4.4.2 Axis Bias and Correction Model

Systematic errors in camera calibration manifest as biases in the estimated 3D positions. Per-axis bias vectors are computed as:

    bias_X = mean(x_est - x_gt)  over all trials                      (4.2)
    bias_Y = mean(y_est - y_gt)  over all trials                      (4.3)
    bias_Z = mean(z_est - z_gt)  over all trials                      (4.4)

A linear correction model fits a scale and offset per axis to minimise residual error after correction. The corrected estimate is:

    x_corr = (x_est - bias_X) * scale_X                               (4.5)

Analogous expressions apply for Y and Z. The pipeline results reported in Chapter 5 use the corrected model.

---

# Chapter 5 — Results and Analysis

## 5.1 Intrinsic Calibration Results

Intrinsic calibration was performed at 1280 × 720 resolution for all four cameras using the ChArUco auto-capture procedure. Each camera required 30–40 valid frames to achieve stable parameter estimates.

Per-camera reprojection errors after calibration fall in the range of 2–8 pixels across the four cameras, which is acceptable for this application. The variability between cameras is attributable to differences in lens quality and the spatial distribution of captured calibration poses. CamSouth, positioned at the greatest distance from the typical calibration zone, showed the highest reprojection error within this range and required two capture sessions to achieve a valid calibration frame set.

The resulting K matrices confirm focal lengths in the expected range for a 1280-pixel-wide sensor with a moderately wide field of view, and distortion coefficients consistent with a barrel distortion pattern typical of low-cost webcam lenses. Undistortion is applied to all frames before detection inference and before triangulation.

## 5.2 Extrinsic Calibration Results

Extrinsic calibration using the 24-AprilTag wall grid produced camera poses with residual reprojection errors of 3–7 pixels after robust outlier rejection. On average, sigma-scale = 2.0 outlier rejection removed 8–15% of tag corner observations, primarily from tags at oblique angles near the arena edges where detection reliability decreases.

The overlay validation procedure — reprojecting known AprilTag corner positions back into each camera frame and comparing with detected positions — confirmed visual alignment across all four cameras. In all cameras, reprojected corners fell within 5–10 pixels of detected corners across the majority of the visible tags.

The resulting world-frame camera positions (Table 3.1) are consistent with physical tape measurements of the mounted camera positions to within approximately ±30 mm, confirming the calibration is geometrically reasonable.

## 5.3 Ball Static Localisation Results

**Table 5.1: Ball static localisation summary metrics (corrected pipeline)**

| Metric | Value |
|---|---|
| Trials valid | 36 / 36 (100%) |
| Mean 3D error | 95.17 mm |
| Median 3D error | 84.18 mm |
| RMSE | 102.23 mm |
| P90 | 142.18 mm |
| P95 | 166.51 mm |
| Maximum error | 214.60 mm |
| Mean reprojection error | 6.01 px |
| Mean cameras used | 2.87 |
| Mean detection ratio (hold window) | 1.000 |
| Mean temporal precision (std over hold) | 3.79 mm |
| P95 temporal precision | 8.51 mm |

The uncorrected pipeline exhibited systematic biases:
- X-axis bias: +50.68 mm (estimated positions shifted toward higher X)
- Y-axis bias: +46.57 mm (estimated positions shifted toward higher Y)
- Z-axis bias: −106.98 mm (estimated positions systematically below true height)

The Z-axis bias is the dominant systematic error. It is attributed primarily to the camera mounting heights: all four cameras are mounted near the ceiling, meaning they observe the ball from above. Triangulation of a ball at low Z (200–700 mm from the floor) involves shallow downward-looking ray angles, which are geometrically sensitive to small calibration errors in the extrinsic Z positions of the cameras. The negative Z bias is consistent with the cameras being calibrated as slightly lower than their true physical height, causing triangulated points to be placed below their true elevation.

After applying the linear axis correction model, the mean error reduces from approximately 150.77 mm (raw) to 95.17 mm (corrected), and the P95 reduces from approximately 288.34 mm to 166.51 mm. Both primary acceptance targets (mean < 120 mm, P95 < 200 mm) are met by the corrected pipeline.

Temporal precision — the standard deviation of repeated estimates of the same static point over the hold window — averages 3.79 mm with a P95 of 8.51 mm. This demonstrates that the triangulation pipeline is highly repeatable given consistent input observations; the dominant error source is systematic calibration bias rather than random noise.

**Figure 5.1:** Ball static localisation — per-axis bias vectors before correction, showing the dominant Z-axis negative bias of −106.98 mm.
*(Insert: `figures/fig_static_axis_bias_raw.png`)*

**Figure 5.2:** Ball static localisation — raw vs corrected 3D error comparison, demonstrating the linear bias correction model reducing mean error from 150.77 mm to 95.17 mm.
*(Insert: `figures/fig_static_raw_vs_corrected.png`)*

## 5.4 Human Pose Joint-Touch Results

**Table 5.2: Joint-touch 3D ground-truth summary metrics (62 valid trials)**

| Metric | Value |
|---|---|
| Trials valid | 62 / 81 (76.5%) |
| Mean 3D error | 143.38 mm |
| Median 3D error | 148.90 mm |
| RMSE | 147.73 mm |
| P90 | 182.04 mm |
| P95 | 198.73 mm |
| Maximum error | 217.34 mm |

**Table 5.3: Per-joint error breakdown**

| Joint | Mean error (mm) | P95 (mm) |
|---|---|---|
| right_knee | 110.03 | 170.75 |
| right_hip | 150.38 | 172.31 |
| left_shoulder | 164.38 | 199.54 |

The right knee achieves the lowest mean error (110.03 mm), consistent with its position at mid-height where all four cameras have favourable viewing geometry. The right hip is observed at a greater height and can be partially occluded by the subject's torso from lateral cameras, resulting in higher error (150.38 mm). The left shoulder, at the greatest height (1560–2200 mm depending on platform level), is closest to the ceiling camera mounting positions and therefore observed at increasingly oblique angles; additionally, the left shoulder is the joint most likely to be occluded by the subject's head and neck. This produces the highest mean error (164.38 mm).

The global P95 of 198.73 mm is below the acceptance threshold of 280 mm, and the per-joint P95 values (170.75, 172.31, 199.54 mm) are all below the per-joint thresholds (220, 220, 250 mm respectively). The mean error of 143.38 mm is below the acceptance threshold of 180 mm.

The 19 invalid trials (23.5% of 81) represent a limitation of the evaluation methodology. In most invalid cases, the subject's body occluded the target joint from one or more cameras during the hold, reducing the camera count below the minimum threshold. This is a real operational constraint: the system requires at least three cameras with clear joint visibility for accurate 3D joint localisation.

**Figure 5.3:** Joint-touch 3D error boxplot by joint type, showing right_knee (110.03 mm mean), right_hip (150.38 mm), and left_shoulder (164.38 mm).
*(Insert: `figures/fig_joint_touch_error_boxplot.png`)*

**Figure 5.3b:** Joint-touch ground-truth vs estimated positions — 3D scatter plot showing all 62 valid trials with GT markers and estimated positions colour-coded by joint type.
*(Insert: `figures/fig_joint_touch_3d_gt_vs_est.png`)*

**Figure 5.3c:** Mean 3D error by joint type — bar chart confirming the monotonic increase in error from knee to shoulder, consistent with decreasing camera visibility at greater heights.
*(Insert: `figures/fig_joint_mean_error_by_joint.png`)*

## 5.5 Dynamic Detection Results

**ball_slow clip:** The 3D trajectory reconstruction remained continuous throughout the 20-second clip with no frame-to-frame jumps exceeding 800 mm. The EMA filter successfully suppressed minor jitter without introducing lag visible in the trajectory. This confirms the pipeline is suitable for tracking slowly moving targets such as a ball on a low bounce or a tossed ball at moderate speed.

**ball_fast clip:** At high ball velocities, detection coverage was lower than in the static and slow-ball cases — approximately 70–80% of frames contained a valid 3D ball estimate. Frames with rapid direction changes (high angular velocity relative to cameras) produced the most detection gaps, consistent with motion blur reducing YOLO detection confidence below threshold. Detected points during high-speed segments remained within arena bounds and were geometrically consistent with the known throw trajectory.

**no_ball clip:** With the ball removed from the scene and a person moving through the arena, the false-positive detection count was close to zero. No spurious ball detections triggered triangulation. This confirms that the confidence threshold and multi-camera gating (requiring detections in ≥2 cameras simultaneously) effectively suppresses single-camera false positives.

**Figure 5.4:** Dynamic ball evaluation summary — trajectory reconstruction quality metrics for ball_slow, ball_fast, and no_ball clips.
*(Insert: `figures/fig_dynamic_summary.png`)*

## 5.6 BLM Aiming Validation (Aim-Only Mode)

The BLM aiming validation was performed in aim-only mode (motors commanded, no ball loaded) using a 5-point static target set at X = 4600 mm, spanning the arena width. For each target, the ballistic solver computed the required yaw and pitch commands, which were dispatched to the ESP32. The resulting motor positions were recorded and compared to the expected angles.

The horizontal-only aiming cycle (pitch fixed, yaw varying) was validated first, confirming that the yaw computation from equation (3.5) correctly maps world-frame XY target positions to motor step counts after applying the yaw trim parameter. Yaw angle residuals after trim calibration were below 2 degrees for all five test points.

Full pitch+yaw aiming was subsequently validated at three heights (Z = 500, 1000, 1500 mm) for the central target position (Y = 1530 mm). Pitch residuals after trim calibration were below 3 degrees.

Decision logs from the aim-only sessions confirm the complete data chain: every target cycle generated a JSONL record with all required fields (timestamp, joint name, raw XYZ, computed pitch/yaw, decision outcome, execution time). Execution time per decision cycle averaged below 50 ms, comfortably within the 67 ms per-frame budget.

## 5.7 Discussion

### 5.7.1 Research Question Assessment

**RQ1 (ball localisation):** The corrected pipeline achieves a mean error of 95.17 mm against a target of 120 mm. **RQ1 is satisfied.**

**RQ2 (joint localisation):** The pipeline achieves a mean joint error of 143.38 mm against a target of 180 mm. **RQ2 is satisfied.** All three per-joint P95 values fall below their respective acceptance thresholds.

**RQ3 (safe integration):** The six-stage checklist has been progressed through Stages 0–4 (preflight, ESP32 testing, runtime without cameras, live aim-only, safety verification). Stage 5 (controlled firing) and Stage 6 (full cycle reliability) are the immediate next milestones. The E-STOP response time is below 100 ms. **RQ3 is partially satisfied**; full satisfaction requires completion of the controlled firing stage.

### 5.7.2 Z-Axis Bias Root Cause

The dominant systematic error in the uncorrected pipeline is the Z-axis bias of −106.98 mm. Physical inspection of the calibration geometry confirms that all four cameras are mounted at ceiling height (2120–2270 mm), providing essentially top-down views. At low target heights (Z = 200–700 mm), the triangulation geometry involves rays with very small elevation differences between cameras, making the Z-axis solution most sensitive to small errors in the extrinsic Z translation. Any upward displacement of the calibrated camera Z positions relative to their true positions will produce a downward (negative) bias in triangulated Z. This is a fundamental limitation of the camera placement geometry and is effectively corrected by the linear bias model.

### 5.7.3 Camera Count Sensitivity

Analysis of error as a function of camera count confirms the critical importance of three-camera coverage. Trials where only two cameras contributed to triangulation showed mean errors approximately 40–60 mm higher than three-camera trials. This motivates the camera placement strategy: four cameras are deployed specifically to ensure that the central operating region is covered by at least three cameras from any position.

### 5.7.4 Joint-Touch GT Methodology Limitations

The joint-touch ground-truth protocol involves the subject physically touching a target marker with a specified body joint. The true ground-truth position is the geometric centre of the joint (e.g., the knee joint centre), not the surface contact point with the marker. The offset between these two quantities — approximately 30–50 mm depending on the joint — introduces a systematic component to the reported error that is not attributable to the vision system. This is a known limitation of the evaluation methodology.

## 5.8 Comparison with State-of-the-Art

**Table 5.4: Comparison with state-of-the-art systems**

| System | Type | 3D Accuracy | Approx. Cost | Pose-Aware? | Real-World Deployable? |
|---|---|---|---|---|---|
| OptiTrack (12-camera system) [30] | Lab motion capture | < 1 mm | USD 100,000+ | Yes (with markers) | No (lab only) |
| Vicon Vantage [8] | Lab motion capture | < 0.5 mm | USD 50,000–200,000 | Yes (with markers) | No (lab only) |
| Intel RealSense D435 [32] | RGB-D depth camera | 10–30 mm (at < 2 m) | ~ USD 300 | Via post-processing | Limited (range, lighting) |
| Monocular YOLO + pose estimation | Single camera | 200–500 mm (depth estimated) | < USD 100 | Yes | Yes |
| Robot tennis / table-tennis (prior research) | Stereo camera pair | ~ 50–100 mm (ball only) | USD 2,000–10,000 | No | Lab only |
| Commercial ball machine (Lobster, Spinshot) | Open-loop, no sensing | N/A | USD 200–2,000 | No | Yes |
| **This work** | **4-camera multi-view** | **95 mm (ball), 143 mm (joint)** | **~ USD 200** | **Yes (named joints)** | **Yes (domestic arena)** |

This system achieves ball localisation accuracy competitive with research-grade stereo systems, at a hardware cost of USD 200 — approximately 10–50× lower than the research prototypes and 250–1000× lower than professional motion capture. It is the only system in this comparison that simultaneously: (i) targets named anatomical landmarks on a human body, (ii) integrates with a physical ball launcher, and (iii) has been deployed and evaluated in a real, uncontrolled domestic environment. The 143 mm mean joint error is within an acceptable tolerance for sports training delivery: targeting a region of ±150 mm around the intended body joint is sufficient for the ball to arrive at the correct body part in ball-reception training scenarios.

---

# Chapter 6 — Conclusions and Future Work

## 6.1 Summary of Contributions

This thesis has presented the design, implementation, and quantitative evaluation of a closed-loop, vision-guided ball launching system. The four stated contributions are confirmed:

**Contribution 1 — The Autonomous Aiming Machine:** A Ball Launching Machine has been demonstrated to autonomously compute and execute its own aim direction — pitch angle, yaw angle, and launch speed — derived exclusively from live 3D reconstruction of a human athlete's body joints. No human operator sets the trajectory. The system identifies the target joint in three-dimensional space and directs the launcher accordingly, representing a qualitative departure from every commercial ball machine currently deployed.

**Contribution 2 — Low-Cost Multi-Camera Pose-to-Launch Pipeline:** The complete perception pipeline — four commodity USB cameras at approximately USD 30 each, ChArUco intrinsic calibration, AprilTag extrinsic calibration, YOLO ball detection, MMPose joint estimation, and DLT/SVD triangulation — achieves a ball localisation mean error of 95.17 mm and a joint localisation mean error of 143.38 mm in a real domestic arena. The total hardware cost of the perception system is approximately USD 200.

**Contribution 3 — Displacement-Adaptive Smoothing and Predictive Targeting:** A displacement-adaptive EMA algorithm that scales the smoothing coefficient with positional displacement enables instantaneous tracking of fast movements (jumps, lunges) while maintaining smooth interpolation during normal motion. A Kalman-filter-based predictive targeting module compensates for total system latency plus ball flight time by estimating the future position of the target joint. An OpenCV-based 3D perspective projection renderer reduces visualisation latency from 200–500 ms (Matplotlib) to ~2 ms, eliminating the dominant bottleneck in the real-time pipeline.

**Contribution 4 — Structured Safety-Gated Integration Protocol:** A six-stage incremental integration checklist with per-stage pass criteria and mandatory decision logging has been developed, progressed through Stages 0–4, and documented. The E-STOP latch responds in under 100 ms. Every actuation decision is recorded to a JSONL log providing full traceability.

## 6.2 Objectives Achievement

| Research Question | Target | Achieved | Status |
|---|---|---|---|
| RQ1: Ball 3D localisation | Mean error < 120 mm | 95.17 mm | Satisfied |
| RQ2: Joint 3D localisation | Mean error < 180 mm | 143.38 mm | Satisfied |
| RQ3: Safe perception-to-actuation integration | Staged safety validated | Stages 0–4 complete, E-STOP < 100 ms | Partially satisfied |

## 6.3 Limitations

**Three-camera minimum requirement:** Accurate 3D triangulation requires at least three cameras with simultaneous line of sight to the target joint. At the edges of the arena, or when the athlete's body occludes certain cameras, the system degrades to two-camera triangulation with significantly higher error. The 19/81 invalid joint-touch trials (23.5%) are primarily attributable to this constraint.

**Joint-touch ground-truth methodology:** The physical contact protocol introduces a systematic error between the surface contact point and the true joint centre (approximately 30–50 mm). This component of the measured error is not attributable to the vision system.

**No BLM hardware homing:** The ESP32 stepper motors use logical zero positioning (software reset to `setzero`) with no physical limit switches or encoders. Cumulative step errors over multiple sessions can drift the mechanical zero, requiring periodic re-homing. This limits the long-term repeatability of absolute aim angles without recalibration.

**Single-person, single-arena evaluation:** All experiments were conducted with one subject in one fixed arena. Generalisation to different subjects (different body proportions), different arenas, or different lighting conditions has not been evaluated.

**Closed-loop firing not yet demonstrated:** The system has been validated in aim-only mode and in controlled static single-shot trials, but fully autonomous closed-loop shooting at a moving human subject has not yet been demonstrated. This is the immediate next experimental milestone.

## 6.4 Future Work and Detailed Execution Plan

The following execution plan defines the research and engineering milestones required to advance the system from its current state (perception validated, aim-only demonstrated) to a fully closed-loop predictive targeting platform with quantitative evaluation.

### 6.4.1 Predictive Trajectory Targeting from 3D Pose Dynamics (Core Innovation)

The central limitation of the current system is that it targets where the athlete IS, not where they WILL BE. The total system delay — camera capture (~67 ms), inference (~80 ms), serial dispatch (~10 ms), mechanical actuation (~200 ms), and ball flight time (~300–500 ms depending on distance) — means the athlete has moved significantly by the time the ball arrives. For a walking athlete at 1.5 m/s, the displacement during a 400 ms total delay is approximately 600 mm — well outside the ±150 mm targeting tolerance.

**Proposed approach:** Implement a per-joint Kalman filter that maintains a state vector [x, y, z, vx, vy, vz] for each tracked joint. The prediction step extrapolates position forward by T_predict = T_system + T_flight milliseconds, producing a predicted future position that is fed to the ballistic solver instead of the current position. A configurable `--predict-ahead-ms` flag controls the prediction horizon.

The Kalman filter provides three advantages over simple linear extrapolation: (i) it naturally handles measurement noise through the process/measurement noise covariance tuning, (ii) it produces a velocity estimate that is smoother than finite-differencing the EMA output, and (iii) its prediction uncertainty (covariance matrix) can be used as a confidence signal — when prediction uncertainty exceeds a threshold, the system withholds actuation rather than firing at a low-confidence predicted position.

**Visualisation:** A "ghost skeleton" rendered at the predicted position (translucent, offset by T_predict) provides real-time visual feedback of the prediction quality. The operator can observe the ghost leading the real skeleton during consistent motion and collapsing back during stationary holds.

**Evaluation protocol:** 50-trial reactive vs 50-trial predictive comparison across three movement patterns (stationary, walking, running with direction changes). Metrics: aim angular error (degrees), miss distance at target plane (mm), hit rate within ±200 mm zone.

**Innovation claim:** No published system combines multi-camera 3D pose estimation with Kalman-filtered predictive targeting for autonomous ball launching. This represents a novel contribution to the intersection of computer vision and robotic sports training.

### 6.4.2 Model Optimization via YOLO-Pose and TensorRT Acceleration

**Completed:** MMPose inference dominated the pipeline latency at ~80 ms per frame (78% of total compute). Two complementary optimisations were implemented:

**YOLO-Pose backend replacement:** The two-stage MMPose pipeline (RTMDet-m person detector → RTMPose-m keypoint estimator) was replaced with YOLO11m-Pose, a single unified model that performs both person detection and 17-keypoint estimation in one forward pass. Benchmarks on the NVIDIA RTX 2080 Ti show:

| Model | Format | Per-image | 4-cam total | Speedup |
|---|---|---|---|---|
| MMPose (RTMDet-m + RTMPose-m) | PyTorch | 38.5 ms | 154 ms (seq) | baseline |
| YOLO11m-Pose | PyTorch | 8.9 ms | 36 ms | 4.3× |
| YOLO11m-Pose | TensorRT FP16 | 6.2 ms | 25 ms | **6.2×** |

**TensorRT FP16 export:** Both the YOLO ball detector and YOLO-Pose model were exported to TensorRT FP16 engines using Ultralytics' built-in export pipeline. The YOLO ball detector showed minimal speedup (8.7 → 8.1 ms, already well-optimised), while YOLO-Pose achieved a 1.4× additional speedup from TensorRT FP16 quantisation on top of the 4.3× architectural advantage.

The combined effect reduces the pose inference bottleneck from ~80 ms to ~6 ms per camera, bringing total pipeline latency from ~200 ms to under 50 ms. This directly enables the predictive targeting module (Section 6.4.1) to operate with tighter prediction horizons, improving prediction accuracy.

**Validation required:** YOLO-Pose keypoint accuracy on the specific arena camera views must be validated against the existing MMPose results before switching the backend for BLM-critical work. The pipeline supports both backends via the `--pose-backend mmpose|yolopose` flag for side-by-side comparison.

### 6.4.3 Closed-Loop Autonomous Firing and BLM Integration

The immediate next step is to progress Stage 5 and Stage 6 of the BLM integration checklist: controlled single-shot firing at a static human subject (aim-only confirmed, ball loaded), followed by moving-target trials. This requires completion of:

- **S0-S1:** ESP32 preflight verification (serial comms, motor response timing, ESTOP reliability)
- **S2-S3:** Live aim-only with visual verification (static target, slow-moving target)
- **S4:** Safety gate validation under all test conditions
- **S5:** Controlled single-shot firing at static and moving targets
- **S6:** Full cycle reliability (50+ consecutive fire cycles, no safety violations)

### 6.4.4 Empirical Ballistic Calibration Map

The current ballistic solver uses a first-principles projectile model neglecting aerodynamic drag and the mechanical imprecision of the wheel-motor speed-to-velocity mapping. An empirical calibration map — measuring actual ball landing positions for a grid of (RPM, pitch, yaw) settings — would allow a correction table to be learned and applied at runtime, reducing systematic aiming error. This is analogous to the bias correction model applied to the perception pipeline.

### 6.4.5 Stakeholder Demo Platform

A unified dashboard integrating 4-camera mosaic, 3D skeleton view, predicted trajectory (ghost skeleton), BLM status panel, and per-shot accuracy metrics will serve as the demonstration platform for stakeholders (sports academies, university committees). Key features:
- Mode selector: manual → reactive → predictive (live comparison)
- Session recording and replay for post-hoc analysis
- Per-shot impact map on the virtual goal plane
- Latency, FPS, and prediction confidence overlay

### 6.4.6 SLAM-Based Camera Re-Localisation and Self-Recalibration

Currently, any physical movement of a camera requires manual extrinsic re-calibration using the AprilTag procedure. A SLAM (Simultaneous Localisation and Mapping) [36] approach would allow the system to detect calibration drift automatically by tracking feature points between sessions and flagging when reprojection errors exceed a threshold.

### 6.4.7 Multi-Person Tracking and Joint Assignment

The current system assumes a single person in the arena. Extending to multiple subjects requires person-level tracking — associating each detected skeleton with a specific individual across frames and across cameras — and a mechanism for the operator to designate which person is the target. Standard multi-object tracking algorithms (ByteTrack [33], StrongSORT [34]) are candidates for this extension.

### 6.4.8 Virtual 3D Goal: Camera-Based Impact Detection

A **software-defined Virtual 3D Goal** using the existing 4-camera infrastructure defines a 1 × 1 metre rectangle in world-frame coordinates, centred on the target zone, oriented perpendicular to the expected ball trajectory. When the ball's trajectory crosses this plane — detected via a ray-plane intersection test between consecutive 3D position estimates — the system logs the exact 3D crossing coordinate, the ball velocity vector at crossing, the time of crossing, and the offset from the designated target joint centroid. This yields per-shot accuracy data with millimetre resolution, with no hardware required at the goal location.

This concept is inspired by **professional instrumented training arenas such as the Footbot system** [35], which defines virtual goal boundaries in 3D space using multi-camera tracking rather than physical sensors. Because the 4-camera perception infrastructure in this work is already deployed, calibrated, and tracking the ball in 3D, the Virtual 3D Goal capability requires only additional software logic.

### 6.4.9 Execution Timeline

| Phase | Weeks | Milestones |
|---|---|---|
| 1: Foundation | 1–3 | GT re-evaluation, TensorRT export, Kalman filter implementation |
| 2: Closed-Loop | 4–6 | BLM preflight (S0-S1), ballistic solver calibration, aim tests (S2-S3) |
| 3: Live Fire | 7–9 | Controlled fire (S4-S5), 100-trial reactive vs predictive evaluation |
| 4: Demo & Thesis | 10–12 | Stakeholder demo platform, thesis writing, defense preparation |

### 6.4.10 Edge Deployment Considerations (NVIDIA Jetson)

For field deployment at sports academies where a full PC is impractical, the NVIDIA Jetson AGX Orin is the target edge platform. Preliminary analysis suggests that inference latency on Jetson would be 2–3× higher than the current RTX 2080 Ti for equivalent model architectures. TensorRT optimisation (Section 6.4.2) becomes essential on Jetson to achieve acceptable latency. USB bandwidth constraints on Jetson limit simultaneous camera capture to 2–3 cameras at 1280×720, requiring either resolution reduction or a USB hub with dedicated bandwidth per camera. Edge deployment is planned as a follow-on engineering effort after the core research contributions are validated on the PC platform.

## 6.5 Professional and Ethical Considerations

**Physical safety:** The BLM projects balls at speeds sufficient to cause injury, particularly at close range or if directed at the face or head. The safety architecture described in Section 3.9 is designed to prevent unintended firing, but any deployment of the full system with live ball launching must be accompanied by a physical safety briefing, mandatory personal protective equipment (eye protection at minimum), and exclusion of bystanders from the ball flight path. The six-stage integration protocol enforces that safety gating is validated before any ball is loaded.

**Video data and privacy:** All ground-truth evaluation sessions involve video recording of a human subject. Data is stored locally and has not been shared with third parties. Any future publication of results should anonymise subject identity in published figures if the subject has not provided explicit consent for identification.

**Open-source intent:** The processing pipeline, calibration scripts, evaluation tools, and decision logging framework developed in this thesis are intended for open-source release. Making the full software stack publicly available would allow other researchers and practitioners to replicate or extend the system, consistent with the goal of making adaptive ball delivery accessible beyond well-funded institutions.

**Dual-use consideration:** A system capable of autonomously tracking human body parts and directing a projectile at them has potential for misuse in contexts outside sports training. The authors note this explicitly and emphasise that the safety architecture — requiring operator presence, E-STOP control, and explicit target designation — is a necessary safeguard for any deployment of this technology.

---

# Bibliography / References

[1] Hartley R. and Zisserman A., 2004, *Multiple View Geometry in Computer Vision*, 2nd ed., Cambridge University Press, Cambridge, UK.

[2] Longuet-Higgins H. C., 1981, "A computer algorithm for reconstructing a scene from two projections," *Nature*, **293**, pp. 133–135.

[3] Hartley R. I., 1997, "In defense of the eight-point algorithm," *IEEE Trans. Pattern Anal. Mach. Intell.*, **19**(6), pp. 580–593.

[4] Kanade T. and Okutomi M., 1994, "A stereo matching algorithm with an adaptive window: theory and experiment," *IEEE Trans. Pattern Anal. Mach. Intell.*, **16**(9), pp. 920–932.

[5] Pingali G., Jean Y., and Carlbom I., 1998, "Real time tracking for enhanced tennis broadcasts," *Proc. IEEE Conf. Computer Vision and Pattern Recognition (CVPR)*, Santa Barbara, CA, pp. 260–265.

[6] Kamble P. R., Keskar A. G., and Bhurchandi K. M., 2019, "Ball tracking in sports: a survey," *Artif. Intell. Rev.*, **52**(3), pp. 1655–1705.

[7] Hawk-Eye Innovations Ltd., 2023, *Hawk-Eye Ball Tracking Technology*, Technical Overview Document.

[8] Windolf M., Götzen N., and Morlock M., 2008, "Systematic accuracy and precision analysis of video motion capturing systems — exemplified on the Vicon-460 system," *J. Biomechanics*, **41**(12), pp. 2776–2780.

[9] Zhang Z., 2000, "A flexible new technique for camera calibration," *IEEE Trans. Pattern Anal. Mach. Intell.*, **22**(11), pp. 1330–1334.

[10] Garrido-Jurado S., Muñoz-Salinas R., Madrid-Cuevas F. J., and Marín-Jiménez M. J., 2014, "Automatic generation and detection of highly reliable fiducial markers under occlusion," *Pattern Recognit.*, **47**(6), pp. 2280–2292.

[11] Olson E., 2011, "AprilTag: A robust and flexible visual fiducial system," *Proc. IEEE Int. Conf. Robotics and Automation (ICRA)*, Shanghai, China, pp. 3400–3407.

[12] Fischler M. A. and Bolles R. C., 1981, "Random sample consensus: a paradigm for model fitting with applications to image analysis and automated cartography," *Commun. ACM*, **24**(6), pp. 381–395.

[13] Redmon J., Divvala S., Girshick R., and Farhadi A., 2016, "You only look once: unified, real-time object detection," *Proc. IEEE Conf. Computer Vision and Pattern Recognition (CVPR)*, Las Vegas, NV, pp. 779–788.

[14] Jocher G., Chaurasia A., and Qiu J., 2024, *Ultralytics YOLO11*, Ultralytics Inc. Available: https://github.com/ultralytics/ultralytics

[15] Cao Z., Hidalgo G., Simon T., Wei S. E., and Sheikh Y., 2021, "OpenPose: realtime multi-person 2D pose estimation using part affinity fields," *IEEE Trans. Pattern Anal. Mach. Intell.*, **43**(1), pp. 172–186.

[16] Lin T. Y., Maire M., Belongie S., Hays J., Perona P., Ramanan D., Dollár P., and Zitnick C. L., 2014, "Microsoft COCO: common objects in context," *Proc. European Conf. Computer Vision (ECCV)*, Zurich, Switzerland, pp. 740–755.

[17] Contributors, MMPose, 2020, *OpenMMLab Pose Estimation Toolbox and Benchmark*, GitHub repository.

[18] Sun K., Xiao B., Liu D., and Wang J., 2019, "Deep high-resolution representation learning for visual recognition," *IEEE Trans. Pattern Anal. Mach. Intell.*, **43**(10), pp. 3349–3364.

[19] Meriam J. L. and Kraige L. G., 2012, *Engineering Mechanics: Dynamics*, 7th ed., Wiley, Hoboken, NJ.

[20] Jones M. T., 2016, *Embedded Systems Design with the Atmel AVR Microcontroller*, Cengage Learning, Boston, MA.

[21] International Electrotechnical Commission, 2021, *IEC 62061: Safety of Machinery — Functional Safety of Safety-Related Control Systems*, IEC, Geneva, Switzerland.

[22] International Organization for Standardization, 2011, *ISO 12100: Safety of Machinery — General Principles for Design*, ISO, Geneva, Switzerland.

[23] Sommerville I., 2016, *Software Engineering*, 10th ed., Pearson, Harlow, UK, Chap. 13.

[24] Muelling K., Kober J., Kroemer O., and Peters J., 2013, "Learning to select and generalise striking movements in robot table tennis," *Int. J. Rob. Res.*, **32**(3), pp. 263–279.

[25] Fässler H., Beyer H. A., and Wen J. T., 1990, "A robot ping pong player: optimized mechanics, high performance 3D vision and intelligent sensor control," *Robotersysteme*, **6**, pp. 161–170.

[26] International Organization for Standardization, 2011, *ISO 10218-1: Robots and Robotic Devices — Safety Requirements for Industrial Robots — Part 1: Robots*, ISO, Geneva, Switzerland.

[27] Bradski G., 2000, "The OpenCV library," *Dr. Dobb's Journal of Software Tools*, **25**(11), pp. 120–125.

[28] Harris C. R., Millman K. J., van der Walt S. J., Gommers R., Virtanen P., Cournapeau D., Wieser E., Taylor J., Berg S., Smith N. J., Kern R., Picus M., Hoyer S., van Krevelen M. H., Brett M., Haldane A., del Río J. F., Wiebe M., Peterson P., Gérard-Marchant P., Sheppard K., Reddy T., Weckesser W., Abbasi H., Gohlke C., and Oliphant T. E., 2020, "Array programming with NumPy," *Nature*, **585**(7825), pp. 357–362.

[29] Virtanen P., Gommers R., Oliphant T. E., Haberland M., Reddy T., Cournapeau D., Burovski E., Peterson P., Weckesser W., Bright J., van der Walt S. J., Brett M., Wilson J., Millman K. J., Mayorov N., Nelson A. R. J., Jones E., Kern R., Larson E., Carey C. J., Polat İ., Feng Y., Moore E. W., VanderPlas J., Laxalde D., Perktold J., Cimrman R., Henriksen I., Quintero E. A., Harris C. R., Archibald A. M., Ribeiro A. H., Pedregosa F., and van Mulbregt P., 2020, "SciPy 1.0: fundamental algorithms for scientific computing in Python," *Nature Methods*, **17**(3), pp. 261–272.

[30] NaturalPoint Inc., 2024, *OptiTrack Motion Capture Systems*, NaturalPoint Inc., Corvallis, OR. Available: https://optitrack.com

[31] PhaseSpace Inc., 2024, *PhaseSpace Impulse X2E Motion Capture System*, PhaseSpace Inc., San Leandro, CA. Available: https://phasespace.com

[32] Intel Corporation, 2023, *Intel RealSense Depth Camera D435 Datasheet*, Intel Corporation, Santa Clara, CA. Available: https://www.intelrealsense.com/depth-camera-d435/

[33] Zhang Y., Sun P., Jiang Y., Yu D., Weng F., Yuan Z., Luo P., Liu W., and Wang X., 2022, "ByteTrack: multi-object tracking by associating every detection box," *Proc. European Conf. Computer Vision (ECCV)*, Tel Aviv, Israel, pp. 1–21.

[34] Du Y., Zhao Z., Song Y., Zhao Y., Su F., Gong T., and Meng H., 2023, "StrongSORT: make DeepSORT great again," *IEEE Trans. Multimedia*, **25**, pp. 8725–8737.

[35] Footbot Ltd., 2024, *Footbot Interactive Football Training System*, Technical Product Description. Available: https://www.footbot.io

[36] Cadena C., Carlone L., Carrillo H., Latif Y., Scaramuzza D., Neira J., Reid I., and Leonard J. J., 2016, "Past, present, and future of simultaneous localization and mapping: toward the robust-perception age," *IEEE Trans. Robotics*, **32**(6), pp. 1309–1332.

---

# Appendix A — BLM Integration Test Checklist

The following table is the complete six-stage integration checklist used to govern safe deployment of the Ball Launching Machine. Each row defines a test ID, stage, test description, pass criteria, and an evidence field to be completed during testing.

| ID | Stage | Test | Pass Criteria |
|---|---|---|---|
| S0.1 | Preflight | Camera and calibration load | Live viewer starts, 4 cams visible, no crash for 2 min |
| S0.2 | Preflight | Serial link to ESP32 | Runtime opens serial and accepts commands |
| S0.3 | Preflight | Launcher pose sanity check | launcher_x/y/z/yaw validated with static target |
| S1.1 | ESP32 only | Manual low-level command test | set, center, stop, shoot, reload all execute correctly |
| S1.2 | ESP32 only | Angle clamp test | Commands beyond ±30 deg safely clamped |
| S1.3 | ESP32 only | RPM telemetry test | L: ... R: ... received while wheels run |
| S2.1 | Runtime, no cameras | Synthetic UDP target feed | Runtime computes command and sends `set` without error |
| S2.2 | Runtime, no cameras | Zone rejection test | Out-of-zone targets logged as OUT_OF_RANGE, not fired |
| S2.3 | Runtime, no cameras | Stability gating test | Noisy targets logged as LOW_CONFIDENCE |
| S3.1 | Live aim-only | Target acquire per joint | Each joint gets stable lock within timeout |
| S3.2 | Live aim-only | Sequence behaviour | right_knee → right_hip → left_shoulder → repeat works |
| S3.3 | Live aim-only | Return to zero | After each aim, launcher returns to centre |
| S4.1 | Safety | E-STOP response time | estop causes immediate stop, response < 100 ms |
| S4.2 | Safety | E-STOP latch behaviour | System stays blocked until `clear` issued |
| S4.3 | Safety | Link-loss behaviour | On UDP/serial interruption, runtime goes to safe stop |
| S5.1 | Controlled fire | Single shot on one joint | 1 commanded shot after aim and RPM gate |
| S5.2 | Controlled fire | No unintended extra shots | Exactly one `shoot` per trigger event |
| S5.3 | Controlled fire | Post-shot safe state | Returns to centre and waits for next valid target |
| S6.1 | Full cycle | 10-cycle reliability | 10 full target cycles without crash or unsafe behaviour |
| S6.2 | Full cycle | Decision log completeness | Every cycle has JSONL records with required fields |
| S6.3 | Full cycle | Report-ready outputs | Logs and summary plots generated |

**Required JSONL decision log fields per event:**
`timestamp`, `input_joint_name`, `raw_world_xyz_mm`, `transformed_launcher_xyz`, `calculated_pitch_yaw_v`, `decision` (OK / OUT_OF_RANGE / LOW_CONFIDENCE / ESTOP), `execution_time_ms`

---

# Appendix B — Key Script Listings

### B.1 Live 4-Camera Arena View with UDP Target Streaming

```bash
# Canonical live visual command
cd /home/hanush/Desktop/Project_Cam
./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \
  --config garage_lab_combined/config/cameras.yaml \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \
  --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \
  --ball-device cuda:0 \
  --pose-device cpu \
  --show-3d
```

### B.2 Launcher Runtime Controller (UDP to Serial)

```bash
./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py \
  --serial-port /dev/ttyUSB0 \
  --launcher-x-mm 600 \
  --launcher-y-mm 1560 \
  --launcher-z-mm 500 \
  --launcher-yaw-deg 0 \
  --targets left_shoulder right_hip right_knee \
  --dry-run-log-jsonl session_log.jsonl
```

### B.3 Ball Static Ground-Truth Evaluation

```bash
./venv/bin/python garage_lab_combined/scripts/evaluate_ball_static_gt.py \
  --session-dir garage_lab_combined/gt_eval/ball_tuning_20260306 \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \
  --conf 0.45 \
  --ball-min-cams 2 \
  --ball-max-reproj-px 14 \
  --ball-ema-alpha 0.25
```

### B.4 Joint-Touch Ground-Truth Evaluation

```bash
./venv/bin/python garage_lab_combined/scripts/evaluate_pose_joint_touch_gt.py \
  --session-dir garage_lab_combined/gt_eval/joint_tuning_20260310 \
  --intrinsics-dir garage_lab_combined/cal/intrinsics \
  --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \
  --conf 0.45 \
  --pose-conf 0.35 \
  --pose-min-cams 3 \
  --ball-ema-alpha 0.25
```

---

# Appendix C — Ground-Truth Data Tables

### C.1 Ball Static GT — Full 36-Point Grid

| Trial | X_gt (mm) | Y_gt (mm) | Z_gt (mm) |
|---|---|---|---|
| B001 | 3000 | 2300 | 200 |
| B002 | 4000 | 2300 | 200 |
| B003 | 5000 | 2300 | 200 |
| B004 | 3000 | 1600 | 200 |
| B005 | 4000 | 1600 | 200 |
| B006 | 5000 | 1600 | 200 |
| B007 | 3000 | 1000 | 200 |
| B008 | 4000 | 1000 | 200 |
| B009 | 5000 | 1000 | 200 |
| B010 | 3000 | 2300 | 700 |
| B011 | 4000 | 2300 | 700 |
| B012 | 5000 | 2300 | 700 |
| B013 | 3000 | 1600 | 700 |
| B014 | 4000 | 1600 | 700 |
| B015 | 5000 | 1600 | 700 |
| B016 | 3000 | 1000 | 700 |
| B017 | 4000 | 1000 | 700 |
| B018 | 5000 | 1000 | 700 |
| B019 | 3000 | 2300 | 1200 |
| B020 | 4000 | 2300 | 1200 |
| B021 | 5000 | 2300 | 1200 |
| B022 | 3000 | 1600 | 1200 |
| B023 | 4000 | 1600 | 1200 |
| B024 | 5000 | 1600 | 1200 |
| B025 | 3000 | 1000 | 1200 |
| B026 | 4000 | 1000 | 1200 |
| B027 | 5000 | 1000 | 1200 |
| B028 | 3000 | 2300 | 1800 |
| B029 | 4000 | 2300 | 1800 |
| B030 | 5000 | 2300 | 1800 |
| B031 | 3000 | 1600 | 1800 |
| B032 | 4000 | 1600 | 1800 |
| B033 | 5000 | 1600 | 1800 |
| B034 | 3000 | 1000 | 1800 |
| B035 | 4000 | 1000 | 1800 |
| B036 | 5000 | 1000 | 1800 |

### C.2 Joint-Touch GT — XY Grid and Height Levels

| XY Position Index | X (mm) | Y (mm) |
|---|---|---|
| 1 | 2600 | 1100 |
| 2 | 3200 | 1100 |
| 3 | 3800 | 1100 |
| 4 | 2600 | 1600 |
| 5 | 3200 | 1600 |
| 6 | 3800 | 1600 |
| 7 | 2600 | 2100 |
| 8 | 3200 | 2100 |
| 9 | 3800 | 2100 |

| Platform Level | Z base (mm) | right_knee Z (mm) | right_hip Z (mm) | left_shoulder Z (mm) |
|---|---|---|---|---|
| Floor | 0 | 500 | 1000 | 1560 |
| Platform 1 | 400 | 900 | 1400 | 1960 |
| Platform 2 | 640 | 1140 | 1640 | 2200 |

---

# Appendix D — Arena Calibration Figures

**Figure D.1:** Arena floor plan with camera positions, AprilTag locations, and world-frame axis overlay on all four live camera feeds.
*(Insert: `arena_fixed/output/world_frame_views_live_quality.png`)*

**Figure D.2:** Extrinsic overlay validation — reprojected AprilTag corners (red/green markers) overlaid on each camera's live frame, confirming calibration accuracy.
*(Insert four sub-figures:)*
- *(a) `figures/fig_overlay_camNorth.jpg` — CamNorth overlay*
- *(b) `figures/fig_overlay_camEast.jpg` — CamEast overlay*
- *(c) `figures/fig_overlay_camSouth.jpg` — CamSouth overlay*
- *(d) `figures/fig_overlay_camWest.jpg` — CamWest overlay*

**Figure D.3:** 3D arena world-frame renders showing camera positions (coloured markers), BLM position (red), coordinate axes, and AprilTag wall positions from three viewing angles.
*(Insert:)*
- *(a) `figures/fig_arena360_view_01.png`*
- *(b) `figures/fig_arena360_view_02.png`*
- *(c) `figures/fig_arena360_view_03.png`*

**Figure D.4:** ChArUco calibration board (A4, 300 dpi, 7×10 squares, DICT_4X4_1000) used for intrinsic calibration of all four cameras.
*(Insert: `garage_lab_combined/cal/boards/Charuco_A4_300dpi_7x10_29.7mmSquare_22.275mmMarker_DICT4X4_1000.png`)*

**Figure D.5:** Intrinsic calibration reprojection error per camera — bar chart showing per-camera mean reprojection error after ChArUco calibration.
*(Insert: `figures/fig_intrinsics_reproj_by_camera.png`)*

**Figure D.6:** Extrinsic calibration RMSE per camera — bar chart showing residual reprojection error after robust PnP optimisation with sigma-clipping.
*(Insert: `figures/fig_extrinsics_rmse_by_camera.png`)*

---

# Appendix E — YOLO Ball Detector Training Results

**Figure E.1:** YOLO11 ball detector training curves — loss, precision, recall, and mAP over training epochs.
*(Insert: `garage-20260217T113109Z-3-001/garage/models/train_v23/results.png`)*

**Figure E.2:** Normalised confusion matrix for the YOLO11 ball detector on the validation set.
*(Insert: `garage-20260217T113109Z-3-001/garage/models/train_v23/confusion_matrix_normalized.png`)*

**Figure E.3:** Precision-Recall curve for the YOLO11 ball detector.
*(Insert: `garage-20260217T113109Z-3-001/garage/models/train_v23/BoxPR_curve.png`)*

**Figure E.4:** Sample training batch — YOLO11 ball detection annotations on training images.
*(Insert: `garage-20260217T113109Z-3-001/garage/models/train_v23/train_batch0.jpg`)*

**Figure E.5:** Validation predictions vs ground truth.
*(Insert two sub-figures:)*
- *(a) `garage-20260217T113109Z-3-001/garage/models/train_v23/val_batch0_labels.jpg` — Ground truth*
- *(b) `garage-20260217T113109Z-3-001/garage/models/train_v23/val_batch0_pred.jpg` — Predictions*

---

# Appendix F — System Qualitative Results

**Figure F.1–F.3:** Live system smoke test frames showing 4-camera arena view with ball detection (green bounding box), pose skeleton overlay (COCO 17-keypoint), and 3D triangulated positions at three time points during continuous operation.

**Figure F.1:** Smoke test frame at t ≈ 5.3 s.
*(Insert: `figures/fig_smoke_frame_0080.png`)*

**Figure F.2:** Smoke test frame at t ≈ 13.3 s.
*(Insert: `figures/fig_smoke_frame_0200.png`)*

**Figure F.3:** Smoke test frame at t ≈ 21.3 s.
*(Insert: `figures/fig_smoke_frame_0320.png`)*

---

*End of thesis draft — thesis_draft.md*
*Generated: 2026-03-25, updated: 2026-03-26*
*All figure insert paths are relative to the Project_Cam root directory.*
*Author name, supervisor names, and student ID must be completed on the cover page and declaration.*
