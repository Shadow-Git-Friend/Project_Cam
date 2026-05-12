# **POSE GUIDED PREDICTIVE BALLISTICS FOR BODY** **PART–TARGETED FOOTBALL TRAINING**

by

## **Arlen Smagulov** **Submitted in fulfilment of the requirements for the degree of**


Master of Science in Electrical and Computer Engineering

## **School of Engineering and Digital Sciences** **Department of Electrical and Computer Engineering** Supervisor: Prof. Sultangali Arzykulov Co-supervisor: Prof. Mohammad Hashmi Nazarbayev University **March 2026**


# **DECLARATION**

I hereby, declare that this manuscript, entitled “Pose Guided Predictive Ballistics for


Body Part–Targeted Football Training”, is the result of my own work except for quotations


and citations which have been duly acknowledged. I also declare that, to the best of my


knowledge and belief, it has not been previously or concurrently submitted, in whole or


in part, for any other degree or diploma at Nazarbayev University or any other national or


international institution.


Signature(s):


Name: Arlen Smagulov


Date: 2026


ii

# **ACKNOWLEDGEMENTS**


The author would like to show his best thanks to the thesis supervisory committee from


the bottom of his heart for their help and constructive criticism during this project. The Depart

ment of Electrical and Computer Engineering at Nazarbayev University is also to be thanked for


providing this research with an academic framework. The open-source communities that sup

port OpenCV, Ultralytics YOLO, MMPose, and the larger Python scientific computing ecosys

tem, in general, made the technical implementation possible.


iii

# **ABSTRACT**


Automated ball-launching machines are widely used in sports training but, to the best of


the author’s knowledge, operate in open-loop mode: the trainer configures a fixed angle, speed,


and interval, and the machine repeats that program regardless of where the athlete stands or how


they move. This thesis presents the design, implementation, and evaluation of a vision-guided


ball launching system capable of autonomously computing aim parameters for specific human


body joints (right knee, right hip, and left shoulder) in real time within a domestic garage arena.


The system has been validated in aim-only mode and in controlled static single-shot trials; fully


autonomous closed-loop firing at a moving human subject remains as immediate future work.


The system uses four fixed commodity USB cameras (Hikvision DS-E12, approximately


USD 30 each) calibrated using ChArUco boards for intrinsic parameters and AprilTag fiducial


markers for extrinsic world-frame registration. Ball detection is performed using a YOLO

based detector and human pose is estimated using the MMPose framework with the COCO 17

keypoint skeleton model. Multi-view triangulation resolves detected 2D observations into 3D


world-frame coordinates in millimetres. A ballistic solver continuously computes the required


pitch angle, yaw angle, and wheel motor RPM to direct a Ball Launching Machine (BLM) at the


triangulated joint position. Low-level actuation is handled by an ESP32 microcontroller com

manding two stepper motors and two wheel motors. A six-stage incremental safety validation


protocol governs integration, including an E-STOP latch with a measured response time below


100 milliseconds.


iv

# **TABLE OF CONTENTS**


**DECLARATION** **i**


**ACKNOWLEDGEMENTS** **ii**


**ABSTRACT** **iii**


**LIST OF TABLES** **viii**


**LIST OF FIGURES** **ix**


**LIST OF ABBREVIATIONS AND SYMBOLS** **xi**


**1** **Chapter 1:** **Introduction** **1**


1.1 Motivation and Problem Statement . . . . . . . . . . . . . . . . . . . . . . . . 1


1.2 Research Objectives . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 2


1.3 Scope and Constraints . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 3


1.4 Statement of Novelty and Contributions . . . . . . . . . . . . . . . . . . . . . 3


1.5 Thesis Structure . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 5


**2** **Chapter 2:** **Literature Review and Background Theory** **6**


2.1 Multi-Camera 3D Reconstruction . . . . . . . . . . . . . . . . . . . . . . . . . 6


2.2 Camera Calibration Techniques . . . . . . . . . . . . . . . . . . . . . . . . . . 7


2.2.1 Intrinsic Calibration . . . . . . . . . . . . . . . . . . . . . . . . . . . . 7


2.2.2 Extrinsic Calibration . . . . . . . . . . . . . . . . . . . . . . . . . . . 7


2.3 Object Detection for Sports Applications . . . . . . . . . . . . . . . . . . . . . 8


2.4 Human Pose Estimation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 8


2.5 Ballistic Modelling and Actuator Control . . . . . . . . . . . . . . . . . . . . . 9


v


2.6 Safety in Autonomous Actuated Systems . . . . . . . . . . . . . . . . . . . . . 10


2.7 Summary and Research Gap . . . . . . . . . . . . . . . . . . . . . . . . . . . 11


**3** **Chapter 3:** **System Design and Methodology** **13**


3.1 Arena Setup and Coordinate System . . . . . . . . . . . . . . . . . . . . . . . 13


3.2 Hardware Architecture . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 14


3.2.1 Cameras . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 14


3.2.2 Ball Launching Machine . . . . . . . . . . . . . . . . . . . . . . . . . 14


3.2.3 ESP32 Microcontroller . . . . . . . . . . . . . . . . . . . . . . . . . . 14


3.2.4 PC–ESP32 Architecture Split . . . . . . . . . . . . . . . . . . . . . . . 15


3.3 Software Architecture and Pipeline Overview . . . . . . . . . . . . . . . . . . 15


3.4 Intrinsic Calibration Pipeline . . . . . . . . . . . . . . . . . . . . . . . . . . . 15


3.4.1 Board Specification and Detection . . . . . . . . . . . . . . . . . . . . 15


3.4.2 Calibration Procedure . . . . . . . . . . . . . . . . . . . . . . . . . . . 17


3.4.3 Output and Validation . . . . . . . . . . . . . . . . . . . . . . . . . . . 17


3.5 Extrinsic Calibration Pipeline . . . . . . . . . . . . . . . . . . . . . . . . . . . 17


3.5.1 AprilTag Detection . . . . . . . . . . . . . . . . . . . . . . . . . . . . 17


3.5.2 Robust PnP Optimisation . . . . . . . . . . . . . . . . . . . . . . . . . 18


3.5.3 Overlay Validation . . . . . . . . . . . . . . . . . . . . . . . . . . . . 18


3.6 Multi-Camera Synchronisation . . . . . . . . . . . . . . . . . . . . . . . . . . 18


3.7 3D Triangulation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 19


3.7.1 Ball Triangulation . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 19


3.7.2 Pose Joint Triangulation . . . . . . . . . . . . . . . . . . . . . . . . . 19


3.7.3 Quality Filtering . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 19


3.8 Ballistic Solver and Targeting Logic . . . . . . . . . . . . . . . . . . . . . . . 20


3.8.1 Target Vector Computation . . . . . . . . . . . . . . . . . . . . . . . . 20


3.8.2 Yaw Angle Computation . . . . . . . . . . . . . . . . . . . . . . . . . 20


3.8.3 Pitch Angle Computation . . . . . . . . . . . . . . . . . . . . . . . . . 21


3.8.4 Wheel RPM Computation . . . . . . . . . . . . . . . . . . . . . . . . 21


3.8.5 Why This Is Non-Trivial . . . . . . . . . . . . . . . . . . . . . . . . . 21


vi


3.8.6 Dynamic Target Tracking Behaviour . . . . . . . . . . . . . . . . . . . 22


3.9 Safety Architecture . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 22


3.9.1 E-STOP Latch . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 22


3.9.2 Multi-Level Gating . . . . . . . . . . . . . . . . . . . . . . . . . . . . 22


3.9.3 Six-Stage Integration Checklist . . . . . . . . . . . . . . . . . . . . . . 23


**4** **Ground-Truth Evaluation Protocols** **24**


4.1 Ball Static Ground-Truth Dataset . . . . . . . . . . . . . . . . . . . . . . . . . 24


4.1.1 Dataset Design . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 24


4.1.2 Capture Protocol . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 25


4.1.3 Processing . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 25


4.2 Joint-Touch Ground-Truth Dataset . . . . . . . . . . . . . . . . . . . . . . . . 25


4.2.1 Dataset Design . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 25


4.2.2 Capture Protocol . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 27


4.2.3 Processing . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 27


4.3 Dynamic Validation Clips . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 27


4.4 Error Metrics and Bias Correction Model . . . . . . . . . . . . . . . . . . . . . 28


4.4.1 Primary Metrics . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 28


4.4.2 Axis Bias and Correction Model . . . . . . . . . . . . . . . . . . . . . 28


**5** **Chapter 5:** **Results and Analysis** **30**


5.1 Intrinsic Calibration Results . . . . . . . . . . . . . . . . . . . . . . . . . . . . 30


5.2 Extrinsic Calibration Results . . . . . . . . . . . . . . . . . . . . . . . . . . . 30


5.3 Ball Static Localisation Results . . . . . . . . . . . . . . . . . . . . . . . . . . 31


5.4 Human Pose Joint-Touch Results . . . . . . . . . . . . . . . . . . . . . . . . . 34


5.5 Dynamic Detection Results . . . . . . . . . . . . . . . . . . . . . . . . . . . . 36


**6** **Chapter 6:** **Conclusions and Future Work** **39**


6.1 Summary of Contributions . . . . . . . . . . . . . . . . . . . . . . . . . . . . 39


6.2 Objectives Achievement . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 39


6.3 Limitations . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 40


vii


6.4 Future Work . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 41


6.4.1 Closed-Loop Autonomous Firing and Moving-Target Prediction . . . . 41


6.4.2 Empirical Ballistic Calibration Map . . . . . . . . . . . . . . . . . . . 41


6.4.3 SLAM-Based Camera Re-Localisation and Self-Recalibration . . . . . 42


6.4.4 Multi-Person Tracking and Joint Assignment . . . . . . . . . . . . . . 42


6.4.5 Virtual 3D Goal: Replacing Physical Sensors with Camera-Based Im

pact Detection . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 42


6.5 Professional and Ethical Considerations . . . . . . . . . . . . . . . . . . . . . 43


**REFERENCES** **45**


**A** **BLM Integration Test Checklist** **49**


**B** **Key Script Listings** **51**


**C** **Ground-Truth Data Tables** **53**


**D** **Arena Calibration Figures** **56**


**E** **YOLO Ball Detector Training Results** **61**


**F** **System Qualitative Results** **64**


viii

# **LIST OF TABLES**


2.1 Existing system categories and their limitations . . . . . . . . . . . . . . . . . 11


3.1 Camera positions in world-frame coordinates (mm) . . . . . . . . . . . . . . . 13


3.2 BLM low-level serial command set . . . . . . . . . . . . . . . . . . . . . . . . 14


4.1 Ball static ground-truth grid definition . . . . . . . . . . . . . . . . . . . . . . 25


4.2 Joint-touch trial design: XY grid positions (mm) . . . . . . . . . . . . . . . . . 26


4.3 Joint-touch platform and joint heights . . . . . . . . . . . . . . . . . . . . . . 26


5.1 Ball static localisation summary metrics (corrected pipeline) . . . . . . . . . . 31


5.2 Joint-touch 3D ground-truth summary metrics (62 valid trials) . . . . . . . . . 34


5.3 Per-joint error breakdown . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 34


6.1 Research question objectives achievement summary . . . . . . . . . . . . . . . 40


A.1 BLM six-stage integration test checklist . . . . . . . . . . . . . . . . . . . . . 49


ix

# **LIST OF FIGURES**


3.1 System architecture in action: live 4-camera arena view showing YOLO ball de

tection (green bounding box), MMPose skeleton overlay (COCO 17-keypoint),


and 3D triangulated positions during continuous operation. . . . . . . . . . . . 16


4.1 Ball static GT grid: 36-point 3D scatter in arena frame. . . . . . . . . . . . . . 24


4.2 Joint-touch trial grid: 9 XY positions and 3 height levels. . . . . . . . . . . . . 26


5.1 Ball static localisation: raw vs corrected 3D error comparison, demonstrating


the linear bias correction model reducing mean error from 150.77 mm to 95.17


mm. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 32


5.2 3D scatter of ground-truth (blue) vs corrected estimated (coloured by error mag

nitude) ball positions across all 36 trials. The colour bar indicates error norm in


mm. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 33


5.3 XY-plane slices at four Z heights (200, 750, 1300, 1800 mm) showing ground

truth (blue circles) vs corrected estimates (red crosses). . . . . . . . . . . . . . 33


5.4 Joint-touch 3D error boxplot by joint type, showing right_knee (110.03 mm


mean), right_hip (150.38 mm), and left_shoulder (164.38 mm). . . . . . . . . . 35


5.5 Joint-touch ground-truth vs estimated positions: 3D scatter plot showing all 62


valid trials with GT markers and estimated positions colour-coded by joint type. 36


5.6 Mean 3D error by joint type: bar chart confirming the monotonic increase in er

ror from knee to shoulder, consistent with decreasing camera visibility at greater


heights. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 37


5.7 Dynamic ball trajectory reconstructions: 3D plots of the four validation clips


( _ball_slow_, _ball_fast_, _ball_fast_ema0.1_, and _no_ball_ ) showing start (green) and


end (red) markers. . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 37


x


D.1 _Arena_ _floor_ _plan_ _with_ _camera_ _positions,_ _AprilTag_ _locations,_ _and_ _world-frame_


_axis overlay on all four live camera feeds._ . . . . . . . . . . . . . . . . . . . . 56


D.2 _Extrinsic overlay validation:_ _reprojected AprilTag corners (red/green markers)_


_overlaid on each camera’s live frame, confirming calibration accuracy._ . . . . . 57


D.3 _3D_ _arena_ _world-frame_ _renders_ _showing_ _camera_ _positions_ _(coloured_ _markers),_


_BLM_ _position_ _(red),_ _coordinate_ _axes,_ _and_ _AprilTag_ _wall_ _positions_ _from_ _three_


_viewing angles._ . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 57


D.4 _ChArUco_ _calibration_ _board_ _(A4,_ _300_ _dpi,_ _7_ _×_ _10_ _squares,_ _DICT_4X4_1000)_


_used for intrinsic calibration of all four cameras._ . . . . . . . . . . . . . . . . 58


D.5 _Intrinsic_ _calibration_ _reprojection_ _error_ _per_ _camera:_ _bar_ _chart_ _showing_ _per-_


_camera mean reprojection error after ChArUco calibration._ . . . . . . . . . . . 59


D.6 _Extrinsic calibration RMSE per camera:_ _bar chart showing residual reprojec-_


_tion error after robust PnP optimisation with sigma-clipping._ . . . . . . . . . . 60


E.1 _YOLOv26s ball detector training curves:_ _loss, precision, recall, and mAP over_


_75 training epochs._ . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 61


E.2 _Normalised confusion matrix for the YOLOv26s ball detector on the validation_


_set._ . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . 61


E.3 _Precision-Recall curve for the YOLOv26s ball detector._ . . . . . . . . . . . . . 62


E.4 _Sample training batch:_ _YOLOv26s ball detection annotations on training images._ 62


E.5 _Validation predictions vs ground truth._ . . . . . . . . . . . . . . . . . . . . . . 63


F.1 _Live_ _system_ _smoke_ _test_ _frames_ _showing_ _4-camera_ _arena_ _view_ _with_ _ball_ _detec-_


_tion (green bounding box), pose skeleton overlay (COCO 17-keypoint), and 3D_


_triangulated positions at three time points during continuous operation._ . . . . 64


F.2 _Smoke test frame at t ≈_ 5 _._ 3 _s._ . . . . . . . . . . . . . . . . . . . . . . . . . . . 64


F.3 _Smoke test frame at t ≈_ 13 _._ 3 _s._ . . . . . . . . . . . . . . . . . . . . . . . . . . 65


F.4 _Smoke test frame at t ≈_ 21 _._ 3 _s._ . . . . . . . . . . . . . . . . . . . . . . . . . . 65


xi

# **LIST OF ABBREVIATIONS AND SYMBOLS**








|Abbreviation /<br>Symbol|Definition|
|---|---|
|BLM|Ball Launching Machine|
|COCO|Common Objects in Context (keypoint dataset for-<br>mat)|
|DLT|Direct Linear Transform|
|EMA|Exponential Moving Average|
|ESP32|Espressif Systems ESP32 microcontroller|
|FPS|Frames Per Second|
|GT|Ground Truth|
|MMPose|OpenMMLab Pose Estimation Framework|
|P90 / P95|90th / 95th percentile of error distribution|
|PnP|Perspective-n-Point (camera pose estimation algo-<br>rithm)|
|RMSE|Root Mean Square Error|
|RPM|Revolutions Per Minute|
|SVD|Singular Value Decomposition|
|UDP|User Datagram Protocol|
|YOLO|You Only Look Once (object detection architecture)|
|K|Camera intrinsic matrix|
|R, T|Rotation matrix, Translation vector (extrinsic param-<br>eters)|
|_θ_|Angle (pitch or yaw, degrees)|
|∆_X_, ∆_Y_, ∆_Z_|Component differences of targeting vector (mm)|


1

# **CHAPTER 1.** **CHAPTER 1: INTRODUCTION**

### **1.1 Motivation and Problem Statement**


Sports training demands repetition, precision, and adaptability. An athlete practising ball recep

tion (whether in basketball, football, volleyball, or rehabilitation) benefits most from a delivery


system that challenges them at the right position, at the right time, directed at the right part of


their body. For decades, automated ball-launching machines have provided the repetition, but


not the precision and not the adaptability.


Every commercial ball launcher on the market today operates in what this thesis terms


an **open-loop** mode. The coach or athlete programs a fixed trajectory: a specific launch angle, a


specific wheel speed producing a specific ball velocity, and a fixed interval between shots. The


machine executes that program indefinitely. It has no sensors. It has no awareness of whether


the athlete is standing, crouching, moving left, or has stepped off the court entirely. Whether


the intended target is the athlete’s right knee at a height of 380 mm or their shoulder at 1600


mm, the launcher fires the same trajectory it was programmed to fire. The athlete has to be in


the planned sequence of movements of the simulator.


This is the main problem that is being dealt with in this paper. The reason is obvious,


high-performance athletic training needs a system that reacts to and adjusts to where the athlete


is positioned at the beginning, as opposed to just running a fixed area of the arena. Currently,


there is no available and comprehensive system to be able to provide this.


The difference compared to other options highlights this gap. At one end of the spec

trum are commercial, open-loop launchers such as the Lobster Elite Liberty, Spinshot Player,


and iPong Pro. They are readily available and inexpensive (ranging from $200 to $2,000), but


ineffective. These are not systems, but merely tools. On the other end, professional labora

tory motion-capture installations (OptiTrack [1], Vicon [2], PhaseSpace [3]) can reconstruct the


full three-dimensional position of every joint on a human body to sub-millimetre accuracy in


real time. However, these systems cost USD 50,000 to over USD 200,000, require dedicated


2


calibrated studio environments, demand that subjects wear reflective markers, and have no in

tegrated actuation. They observe, but they do not act. Furthermore, the cost and operational


complexity place them entirely outside the reach of the sports training contexts where adap

tive delivery would be most valuable: community sports clubs, physiotherapy practices, school


athletic programmes, and individual training environments.


The Ball Launching Machine (BLM) described in this thesis is neither of these. It is not


a conventional launcher that a human programs and forgets. It is a **smart machine** : a system


that continuously observes the athlete through four calibrated cameras, reconstructs the three

dimensional position of specific body joints in real time, computes the required pitch angle, yaw


angle, and ball speed to reach that joint, and autonomously commands the physical launcher to


aim and fire. No human operator sets the angle. No human pre-programs the path. The machine


decides its own aim, based entirely on where the person is and which body part has been selected


as the target.


The right knee, right hip, and left shoulder were chosen as the body parts to work on be

cause they cover a range of heights and allow for different types of training: low ball reception,


mid-body interception, and overhead or upper-body challenges. These points in the arena are


not random. They are called joints and are updated every frame as live 3D world-frame coordi

nates from the MMPose COCO 17-keypoint skeleton model. The target coordinate changes as


the athlete moves, and the ballistic solver keeps recalculating.


The main idea of this thesis is the change from a fixed, human-programmed firing path


to an autonomous, pose-reactive targeting system.

### **1.2 Research Objectives**


This work is guided by three research questions:


**RQ1:** Is it possible for a four-camera multi-view triangulation pipeline to attain an


average 3D localisation error of less than 120 mm for a stationary ball within a typical domestic


garage arena?


**RQ2:** Is it possible for a human pose estimation pipeline to get a mean 3D joint locali

sation error of less than 180 mm, which is good enough for targeting the right knee, right hip,


3


and left shoulder?


**RQ3:** Is it possible to safely validate the integrated perception-to-actuation pipeline with


a real Ball Launching Machine in a home setting, employing a structured incremental testing


methodology?


Chapter 4 discusses specific data validation protocols that provide numerical answers to


these questions, and Chapter 5 describes how they were used.

### **1.3 Scope and Constraints**


This work is being carried out within the scope of the following definitions:


**Physical environment:** A domestic garage arena measuring 6230 mm (X) _×_ 3050 mm


(Y) _×_ 2950 mm (Z), with four cameras mounted at fixed positions near the ceiling perimeter.


**Hardware:** Four Hikvision DS-E12 USB webcams, one custom Ball Launching Ma

chine with stepper motor driven pan/tilt and wheel motor driven ball projection, one ESP32


microcontroller for low level actuation. Total perception hardware cost is about USD 200.


**Software:** Python: version 3.10 with OpenCV [4], Ultralytics YOLO [5], MMPose [6],


NumPy [7], SciPy [8]. All of the components are open source.


**Subject:** Evaluation of single person. Multi-person scenarios are not the scope of this


thesis.


**Stage** **of** **integration:** The BLM targeting system has been verified in aim-only mode


(motors activated, no projectile discharged) and in regulated single-shot static tests. Complete


autonomous closed-loop shooting with a moving human subject is the next urgent milestone


and is designated as future development in Section 6.4.


**Lighting:** Controlled indoor lighting. The system has not been tested under varying


natural light conditions or outdoors.

### **1.4 Statement of Novelty and Contributions**


The following three claims represent original contributions to this work:


**Novelty Claim 1: The Autonomous Aiming Machine.** All commercially available ball


launchers are passive instruments. A person sets the direction, and the machine follows. This


4


system changes this relationship. The ball launcher control (BLM) of this work autonomously


calculates pitch, yaw, and wheel speeds based on real-time 3D joint coordinates derived from


the athlete’s posture using multiple cameras, and then sends sequential commands to execute


the movement task. The launcher does not know in advance where to aim for the next throw.


They determine this by observing the athlete. This is not a launcher with a retrofitted camera,


but rather a guidance system whose primary purpose is to aim at a person and which uses the


ball launcher themselves as the target. This difference is the central innovation of this work and


represents a departure from all currently available commercial systems.


**Novelty Claim 2:** **Low-Cost Multi-Camera Pose-to-Launch Pipeline.** Prior research


on closed-loop sports targeting has either employed costly depth cameras (such as Intel Re

alSense and structured light systems) or conducted experiments in controlled laboratory envi

ronments with professional motion capture technology. This work demonstrates that four com

modity USB cameras costing approximately USD 30 each, combined entirely with open-source


detection and pose estimation models (YOLO, MMPose) and an AprilTag-based calibration


workflow, can achieve sub-200 mm joint targeting accuracy in a real, uncontrolled domestic


arena. The total cost of perception hardware is about $200, which is one to three orders of mag

nitude lower than similar systems. This finding demonstrates that the fundamental functionality


of pose-reactive ball delivery can be realized beyond laboratory environments and is available


to practitioners without the need for specialized infrastructure.


**Novelty Claim 3: Structured Safety-Gated Integration Protocol.** No previously pub

lished work about vision-guided ball launchers includes a reproducible and evidence-based


methodology for staged validation of these systems. This thesis adds the contribution of a


six-stage incremental integration checklist covering preflight check through ESP32 testing,


aim only validation, safety gating verification, and controlled firing where the defined crite

ria for each stage are met and their evidence must be logged. Every actuation decision is


logged to a structured JSONL file with some fields as: timestamp, input joint name, raw


3D world coordinate, computed pitch and yaw, decision outcome (OK, OUT_OF_RANGE,


LOW_CONFIDENCE, ESTOP). This framework is intended to be a repeatable one for any


type of vision-guided actuated system being used in an uncontrolled environment.


5

### **1.5 Thesis Structure**


Chapter 2 overviews the pertinent literature in six areas of related technical activity: multi

camera 3D reconstruction, camera calibration, object detection, human pose estimation, ballis

tic modelling and safety in autonomous actuated systems. It ends with a clear contrast of this


work to extant commercial/research systems.


Chapter 3 focuses on describing the full design of the system and methodology, from the


arena set-up and hardware choices to camera calibration pipelines, synchronising, triangulating,


the ballistic solver and the safety architecture.


Chapter 4 specifies the parameters for ground truth evaluation, that is the 36-point static


ball dataset, the 81-trial joint touch dataset, and the dynamic validation clips.


Chapter 5 provides all quantitative results including a state-of-the-art comparison table.


Chapter 6 states conclusions, assesses objective achievement, individual limitations and


sets a concrete roadmap for future work including Virtual 3D Goal concept.


6

# **CHAPTER 2.** **CHAPTER 2: LITERATURE REVIEW AND BACKGROUND** **THEORY**

### **2.1 Multi-Camera 3D Reconstruction**


Recovering the three dimensional position of the objects from two dimensional image obser

vations is a classical problem in computer vision. The theoretical foundation is based on that


of pinhole camera model, which models the projection of a 3D point **P** = ( _X,Y,_ _Z_ ) to an image


point **p** = ( _u,_ _v_ ) as done by the relation:


_s_ _·_ [ _u,_ _v,_ 1] _[T]_ = _K ·_ [ _R|T_ ] _·_ [ _X,Y,_ _Z,_ 1] _[T]_ (2.1)


where _K_ is the intrinsic matrix of 3 _×_ 3 representing the focal lengths and principal point


of the camera, _R_ is the rotation matrix 3 _×_ 3, _T_ is the translation vector with a length of 3 _×_ 1


representing the camera position and attitude in the world frame and _s_ is the scalar projection


depth [9].


When the same object appears in two or more calibrated cameras at the same time, the


3D position of the object can be reproduced using the triangulation method. The geometrical


principle here is epipolar geometry: the projection rays from both cameras that pass through


the 2D point to be observed must intersect in the 3D located at the true 3D point in the ideal


case of no noise [10]. In practice, due to image noise and imperfections in the calibration of


the imaging system, rays even from convergence points very rarely coincide. The Direct Linear


Transform (DLT) method develops triangulation as a system of linear equations and solves


this linear equation for the 3D point minimising the algebraic reprojection error using Singular


Value Decomposition (SVD) [9].


Triangulation accuracy is determined by two main factors: the quality of camera cali

bration and the number of cameras with more valid observations. In underconstrained configu

rations (where only one camera observes the target) no triangulation is possible. With exactly


7


two cameras, depth reconstruction is sensitive to the baseline between cameras and to any cali

bration error [11]. With three or more cameras, redundancy in the system of equations improves


robustness. This motivates the minimum camera count requirements used in this work (Section


3.6).


Multi-camera 3D reconstruction has been applied extensively in sports science. Systems


have been deployed for ball tracking in tennis [12], football [13], and cricket [14], and for full

body motion capture in biomechanics research [2]. These applications typically use carefully


calibrated synchronised cameras in purpose-built environments. The contribution of this work


is demonstrating equivalent reconstruction capability with commodity hardware in a domestic,


uncontrolled arena.

### **2.2 Camera Calibration Techniques**


_**2.2.1**_ _**Intrinsic Calibration**_


Camera intrinsic calibration determines the parameters of the imaging model: focal lengths


( _fx_, _fy_ ), principal point ( _cx_, _cy_ ), and lens distortion coefficients. The widely adopted approach,


due to Zhang [15], uses a planar calibration pattern observed from multiple viewpoints. The


method solves for intrinsic and extrinsic parameters simultaneously through homography de

composition, then refines all parameters with non-linear optimisation minimising reprojection


error.


In this work, a ChArUco calibration board is used, which combines a chessboard pattern


with embedded ArUco markers. ChArUco boards offer two advantages over plain chessboards:


individual square corners can be identified even when the board is partially occluded, and the


ArUco marker IDs provide unambiguous corner labelling that eliminates the corner-order am

biguity present in plain chessboard patterns [16]. The board used measures 5 _×_ 7 squares with


21.5 cm square size.


_**2.2.2**_ _**Extrinsic Calibration**_


Extrinsic calibration determines each camera’s position and orientation ( _R_, _T_ ) in a common


world frame. This is the prerequisite for multi-view triangulation: all cameras must share the


8


same world coordinate system for their projection rays to be compared.


AprilTag fiducial markers, developed at the University of Michigan [17], are used exten

sively for this purpose. Each tag encodes a unique binary ID and allows the tag’s four corners to


be detected and their 3D positions estimated from a single camera image, given known tag size,


using the Perspective-n-Point (PnP) algorithm. When multiple tags at known world positions


are detected, the camera pose can be recovered by minimising reprojection error across all tag


corners. Robust estimation techniques, such as RANSAC-based outlier rejection and iteratively


re-weighted least squares with sigma-clipping, reduce the influence of incorrectly detected tags


[18].

### **2.3 Object Detection for Sports Applications**


Real-time object detection has been transformed by the YOLO (You Only Look Once) family


of architectures [19], which formulate detection as a single-pass regression problem predict

ing bounding boxes and class probabilities from a full image in one forward pass through a


convolutional neural network. Subsequent versions (YOLOv5, YOLOv8, YOLO11) have suc

cessively optimized the accuracy-speed tradeoff allowing them to be deployed in commodity


GPU hardware at frame rates in real time [5].


Ball detection in sports is a particular problem compared to object detection in general,


as balls are small, partially occluded, suffer from a lot of motion blur during fast velocities


and have to be separated from similarly shaped parts of background objects. Prior work on


ball tracking in sports has made use of a variety of approaches including background subtrac

tion, colour-based filtering, and deep learning detectors [12, 13]. For this system, the version


Ultralytics YOLO11 is used, with the level of confidence for detecting objects set by empiri

cal approach individually for each experiment (0.25–0.45) for the balance between the rate of


false-positive events with detection recall.

### **2.4 Human Pose Estimation**


Human pose estimation is the task of detecting the spatial configuration of a person’s body from


image data. The problem is commonly formulated as keypoint detection: estimating the 2D (or


9


3D) coordinates of a set of anatomically defined body landmarks from one or more camera


views [20].


The COCO keypoint format defines 17 anatomical landmarks: nose, eyes, ears, shoul

ders, elbows, wrists, hips, knees, and ankles. This convention has become the dominant bench

mark standard, and the majority of modern pose estimation models produce COCO-format


output [21]. Top-down approaches, which first detect persons with a bounding-box detector


and then run a specialised keypoint network on each detected person, generally achieve higher


per-keypoint accuracy than bottom-up approaches that detect all keypoints first and group them


afterwards.


MMPose [6], the pose estimation framework used in this work, implements both paradigms


and provides pre-trained models on COCO-format benchmarks. For this system, a top-down


pipeline is used with the HRNet backbone, which has demonstrated strong performance on


COCO benchmark evaluations [22].


Extending 2D pose estimation to 3D using multiple cameras follows the same multi

view triangulation principle as ball localisation: 2D joint observations from multiple cameras


are combined via DLT/SVD to recover 3D joint positions. The accuracy of 3D joint reconstruc

tion is inherently limited by the 2D pose estimation accuracy, the camera calibration quality,


and the number of cameras with valid joint visibility.

### **2.5 Ballistic Modelling and Actuator Control**


A ball projected from a launcher at initial speed _v_ 0, pitch angle _θ_, and yaw angle _φ_ follows a


parabolic trajectory under gravity (neglecting air resistance for first-order approximation). The


equations of motion are:


_x_ ( _t_ ) = _v_ 0 _·_ cos( _θ_ ) _·_ cos( _φ_ ) _·_ _t_ (2.2)


_y_ ( _t_ ) = _v_ 0 _·_ cos( _θ_ ) _·_ sin( _φ_ ) _·_ _t_ (2.3)


10


_z_ ( _t_ ) = _v_ 0 _·_ sin( _θ_ ) _·_ _t −_ [1] 2 _[·]_ _[g]_ _[·]_ _[t]_ [2] (2.4)


where _g_ = 9810 mm/s [2] is gravitational acceleration. Given a target point ( _Tx,_ _Ty,_ _Tz_ ) and


launcher origin ( _Bx,_ _By,_ _Bz_ ), the system of equations (2.2)–(2.4) can be solved for the required


launch parameters. For a fixed target range and height difference, two valid pitch angles gen

erally exist (the low and high trajectory solutions); the lower-angle solution is preferred in this


system as it minimises flight time and therefore targeting uncertainty due to athlete movement


[23].


Stepper motors provide an appropriate actuation mechanism for launcher pan/tilt posi

tioning: their open-loop step-counting control provides predictable angular displacement with

out requiring continuous position feedback, and their holding torque maintains aim angle against


mechanical vibration from the wheel motors [24].

### **2.6 Safety in Autonomous Actuated Systems**


Any system that combines computer vision decision-making with physical actuation must ad

dress safety as a first-class design concern. The relevant engineering context is machine safety


standards: IEC 62061 (functional safety of machinery) [25] and ISO 10218 (safety of industrial


robots) [26] both mandate that automated systems implement a defined safe state and a reliable


means of commanding transition to that state under fault conditions [25].


An Emergency Stop (E-STOP) function, mandatory in ISO 12100, must interrupt haz

ardous motion immediately and latch in the stopped state until a deliberate human reset action


is taken [27]. Response time requirements vary by hazard level; for a ball launcher in a do

mestic training environment with no proximity hazard to the operator during normal operation,


a response time below 200 ms is considered acceptable practice. The system described in this


thesis achieves a measured E-STOP response time below 100 ms.


The broader principle of incremental validation, testing each subsystem in isolation be

fore integration and each integration stage before full operation, is standard practice in safety

critical embedded systems development [28] and is formalised in this work as the six-stage


BLM test checklist (Section 3.9).


11

### **2.7 Summary and Research Gap**


The following table organises existing systems into three categories and positions this work


relative to them.


_**Table 2.1.**_ _**Existing system categories and their limitations**_
















|Category|Example Sys-<br>tems|Cost (ap-<br>prox.)|Accuracy|Limitations|
|---|---|---|---|---|
|A:<br>Com-<br>mercial<br>Open-Loop<br>Launchers|Lobster<br>Elite<br>Liberty, Spinshot<br>Player, iPong Pro|USD 200–<br>2,000|N/A<br>(no<br>sensing)|No perception; fxed<br>paths; cannot target<br>athlete|
|B:<br>Pro-<br>fessional<br>Lab Motion<br>Capture|OptiTrack<br>[1],<br>Vicon [2], Phas-<br>eSpace [3]|USD<br>50,000–<br>200,000+|<1<br>mm<br>(with<br>markers)|Lab-only; no actua-<br>tion; requires mark-<br>ers; inaccessible|
|C:<br>Re-<br>search<br>Prototype<br>Vision<br>Systems|Robot<br>tennis/table-<br>tennis,<br>ball-<br>serving robots|USD<br>2,000–<br>10,000|50–100<br>mm<br>(ball<br>only)|Fixed-zone<br>target-<br>ing;<br>lab<br>environ-<br>ments;<br>no<br>joint<br>targeting|



Category A systems dominate sports training deployment globally. Their limitation is


not cost; it is architecture. They are incapable of perception-guided targeting regardless of


budget, because they have no sensors.


Category B systems exist in biomechanics research and high-performance sports science


institutes. Their accuracy is exemplary, but their deployment model makes them inaccessible


for the majority of training contexts. Furthermore, they observe, but they do not act. No system


in this category integrates with a ball launcher.


Category C systems represent the closest research analogues to this work. Prior systems


for robotic table tennis [29] and tennis ball serving [30] demonstrate vision-guided launching


but target fixed zones on the court, not body parts of the athlete. They operate in controlled lab

oratory environments and use stereo camera pairs or depth cameras costing significantly more


than the commodity USB cameras used here. Critically, none of the reviewed systems demon

strates joint-level targeting, meaning that the launch target is a named anatomical landmark on


a moving human.


The research gap is therefore precisely stated: **no** **prior** **system** **combines** **commod-**


12


**ity multi-camera 3D reconstruction, real-time human joint localisation from open-source**


**pose** **estimation,** **and** **a** **physical** **ballistic** **controller** **targeting** **those** **joints,** **deployed** **and**


**evaluated in an uncontrolled domestic environment at low cost.** This thesis fills that gap.


13

# **CHAPTER 3.** **CHAPTER 3: SYSTEM DESIGN AND METHODOLOGY**

### **3.1 Arena Setup and Coordinate System**


The experimental arena is a domestic garage measuring 6230 mm in the X direction (depth from


camera north wall to south wall), 3050 mm in the Y direction (width), and 2950 mm in the Z


direction (height). The origin of the world coordinates is considered to be at the North-East


corner of the floor of the arena with the **X-axis** pointing from the North wall toward the South


wall (increasing toward the launcher end), the **Y-axis** pointing from the East wall toward the


West wall, and the **Z-axis** pointing vertically upward.


All coordinates in this thesis are expressed in millimetres. The athlete operates in the


central region of the arena approximately between X = 2500 mm and X = 5000 mm.


_**Table 3.1.**_ _**Camera positions in world-frame coordinates (mm)**_

|Camera|X (mm)|Y (mm)|Z (mm)|Description|
|---|---|---|---|---|
|CamNorth|50|1100|2260|North wall, central<br>height|
|CamEast|1620|50|2120|East<br>wall,<br>near<br>North end|
|CamWest|1600|2970|2170|West<br>wall,<br>near<br>North end|
|CamSouth|6180|1530|2270|South wall, central|



The four cameras are mounted at ceiling height near the perimeter walls, providing


overlapping fields of view across the central arena volume where the athlete operates. The


placement was optimised to maximise the number of cameras simultaneously looking at the


target area with a nominal design target of three or more cameras looking at the athlete clearly


at any position within the area of operation.


Twenty-four fiducial markers in the form of AprilTag markers (IDs 0–23; 21.5 cm _×_


21.5 cm) are attached to the walls of the arena at known spots. Their world-frame coordinates


are stored in the extrinsics calibration file and used during the extrinsic calibration process


described in Section 3.5.


14

### **3.2 Hardware Architecture**


_**3.2.1**_ _**Cameras**_


The four cameras are Hikvision DS-E12 USB webcams operating at a capture resolution of


1280 _×_ 720 pixels and a target frame rate of 15 FPS. These are consumer-grade, fixed-focus


cameras with no hardware synchronisation capability. Software synchronisation via flashlight


marker frames is used instead (Section 3.6). Each camera costs approximately USD 30.


_**3.2.2**_ _**Ball Launching Machine**_


The BLM consists of two wheel motors (Left and Right) that spin in opposite directions to


project the ball, where the differential in motor speeds can impart spin and speed is controlled


by setting wheel motor RPM parameters; two stepper motors controlling vertical rotation (pitch,


V parameter) and horizontal rotation (yaw, H parameter), where each step corresponds to a


defined angular increment; and a ball feed mechanism controlled by the `shoot` and `reload`


commands.


The BLM is positioned at approximately X = 600 mm, Y = 1560 mm, Z = 500 mm, near


the North wall, centred in Y, at approximately half the arena height. Its launch direction points


toward the South wall (increasing X direction) where the athlete operates.


_**3.2.3**_ _**ESP32 Microcontroller**_


An ESP32 microcontroller receives serial commands from the host PC and translates them into


motor control signals. The command protocol is described in Table 3.2.


_**Table 3.2.**_ _**BLM low-level serial command set**_


|Command|Syntax|Effect|
|---|---|---|
|set|`set V H WL WR`|Set vertical angle V (degrees), horizontal angle H (degrees),<br>left wheel speed WL, and right wheel speed WR|
|shoot|`shoot`|Trigger one ball ejection cycle|
|reload|`reload`|Retract ball feed mechanism for next round|
|center|`center`|Return all axes to zero position|
|stop|`stop`|Stop all motors immediately|
|setzero|`setzero`|Register current position as logical zero|


15


_**3.2.4**_ _**PC–ESP32 Architecture Split**_


High-level computation (camera capture, YOLO inference, MMPose inference, triangulation,


ballistic solving, safety gating, and decision logging) runs on the host PC. The ESP32 receives


only pre-computed motor commands and executes them. This split provides three advantages:


faster iteration (firmware changes are not needed to modify targeting logic), safer debugging


(actuation can be disabled by stopping the PC-side process with no firmware modifications),


and computational efficiency (GPU inference is available on the PC but not the ESP32).

### **3.3 Software Architecture and Pipeline Overview**


The processing pipeline proceeds through seven stages executed sequentially per frame. Stage


1 is **Multi-Camera Capture**, where four cameras are polled in software for the current frame


at 1280 _×_ 720 px. Stage 2 is **Ball Detection**, where YOLO11 inference on each camera frame


produces a 2D bounding box and confidence for any detected ball. Stage 3 is **Pose Estimation**,


where MMPose HRNet inference on each camera frame produces 17 2D keypoint coordinates


and per-keypoint confidence values for any detected person. Stage 4 is **3D** **Triangulation**,


where valid 2D observations from stages 2 and 3 are passed to the multi-view DLT/SVD solver


to produce 3D world-frame coordinates for the ball and for each joint. Stage 5 is **Filtering**,


where EMA smoothing and outlier rejection are applied to 3D outputs. Stage 6 is **Ballistic**


**Solve**, where for the active target joint, pitch, yaw, and wheel RPM are computed. Stage 7 is


**Actuation**, where the serial command is dispatched to ESP32 (in operational mode) or logged


to JSONL (in dry-run mode).


The system is implemented in Python 3.10. Key libraries: OpenCV 4.x [4] (camera I/O,


image processing, calibration), Ultralytics YOLO11 [5] (ball detection), MMPose 1.x [6] (pose


estimation), NumPy [7] and SciPy [8] (numerical computation), Matplotlib (visualisation).

### **3.4 Intrinsic Calibration Pipeline**


_**3.4.1**_ _**Board Specification and Detection**_


A ChArUco board of 5 columns _×_ 7 rows of squares (size of the square 21.5 cm) is used.


ArUco markers embedded in alternate squares are used to provide identifier numbers for par

16


_**Figure 3.1.**_ _**System architecture in action:**_ _**live 4-camera arena view showing YOLO ball**_
_**detection (green bounding box), MMPose skeleton overlay (COCO 17-keypoint), and 3D**_
_**triangulated positions during continuous operation.**_


17


ticular corners of the board that can be used for partial-board detection. The script streamlines


the image collection process: the stream from all four cameras is used, the ChArUco corners


are detected in each frame and the corner number is automatically saved when the number of


detected corners is greater than 25, and the detection is stable for 3 seconds. This hands-free


method ensures enough pose diversity without operator timing errors.


_**3.4.2**_ _**Calibration Procedure**_


Per-camera calibrating is done independently. For each camera, OpenCV [4] is used to estimate


intrinsic matrix _K_ and distortion coefficients ( _k_ 1, _k_ 2, _p_ 1, _p_ 2, _k_ 3) using minimisation of the


reprojection error for all the collected frames. A good 30 valid frames per camera is aimed at.


Frames with less than 25 corners detected are dropped before calibration.


The intrinsic calibration is done at 1280 _×_ 720 resolution, which is the resolution that the


system operates with. Calibrating at a different resolution than operation introduces a scaling


error in the focal length and principal point, which would propagate as a systematic triangulation


bias.


_**3.4.3**_ _**Output and Validation**_


Calibration outputs per-camera _K_ matrix and distortion vector, stored as JSON files in `garage_`


`lab_combined/cal/intrinsics/` . Per-camera reprojection error is computed over the full


calibration frame set as a quality indicator. Values in the range of 2–8 pixels are considered


acceptable for this application.

### **3.5 Extrinsic Calibration Pipeline**


_**3.5.1**_ _**AprilTag Detection**_


Twenty-four AprilTag markers (family tag36h11, IDs 0–23, 21.5 cm side length) are affixed


to the arena walls at pre-measured world-frame positions stored in the calibration configura

tion. The script `calibrate_extrinsics_apriltag_robust.py` runs AprilTag detection on


still frames captured from each camera and assembles a set of PnP correspondences: for each


detected tag corner, a 3D world position and a 2D image position.


18


_**3.5.2**_ _**Robust PnP Optimisation**_


Camera pose ( _R_, _T_ ) is estimated for each camera via PnP with iterative refinement. An outlier


rejection step with sigma-scale = 2.0 discards tag corner observations whose reprojection error


exceeds two standard deviations of the residual distribution. This step eliminates the influence


of misdetected tags or physical measurement errors in tag positions. The result is a per-camera


rotation matrix _R_ and translation vector _T_ defining the camera’s position and orientation in the


world frame.


_**3.5.3**_ _**Overlay Validation**_


Extrinsic quality is validated visually by reprojecting the known AprilTag corner positions back


into each camera image using the estimated ( _K_, _R_, _T_ ) and overlaying the reprojected corners


on the captured frame. When reprojected corners align tightly with detected corners across all


cameras, the extrinsic calibration is considered valid. This validation is performed after any


physical camera movement and before any data collection session.

### **3.6 Multi-Camera Synchronisation**


The four Hikvision DS-E12 cameras have no hardware synchronisation signal. Software syn

chronisation is achieved through a flashlight sync marker protocol: a handheld flashlight is


flashed briefly at the start of each recording session, creating a detectable brightness spike in


all four camera streams simultaneously. Frame alignment is performed by finding the flashlight


spike frame in each stream and offsetting the subsequent frames accordingly.


For the ground-truth evaluation sessions, which use static holds of 3–4 seconds, synchro

nisation accuracy of _±_ 2 frames (approximately 130 ms at 15 FPS) is acceptable, as the target


is stationary during the hold window. For the dynamic validation clips, synchronisation accu

racy would directly impact the quality of triangulation; larger temporal offset between cameras


would make the apparent parallax of a moving ball larger which would introduce triangulation


error.


A minimum of two cameras is required for triangulation, 3 or more cameras are targeted


when experimental data collection is performed. The detection and triangulation code imposes


19


a configurable limitation for the number of cameras needed (2 is used for the evaluation exper

iments), as well as stores the number of cameras used in each frame for post-hoc analysis.

### **3.7 3D Triangulation**


_**3.7.1**_ _**Ball Triangulation**_


For each frame with a ball detection reported in two or more cameras with a confidence larger


than the configured threshold value (0.25–0.45 and depends on each experiment) by the YOLO


object detector, the 2D bounding box centre coordinates are combined into a set of ray equations


using the ( _K_, _R_, _T_ ) parameters collected per camera. The DLT method constructs a matrix _A_


which has the following property: a point _P_ in 3D will satisfy _A_ _·_ _P_ = 0 in a homogeneous least

squares sense. SVD of _A_ returns _P_ as the right singular vector corresponding to the smallest


singular value [9].


_**3.7.2**_ _**Pose Joint Triangulation**_


For each of the COCO keypoints, the same procedure is followed using the 2D keypoint coordi

nate from each camera where the joint confidence exceeds the pose confidence threshold (0.35)


and the joint is observed by at least 3 cameras. And the minimum number of cameras for pose


triangulation is higher when compared to ball triangulation (3 versus 2) since joint observations


are naturally more noisy when compared to ball centre estimates.


_**3.7.3**_ _**Quality Filtering**_


After the application of triangulation, two filters of quality are implemented:


**Reprojection error check:** The triangulated 3D point is projected into each contribut

ing camera using the known ( _K_, _R_, _T_ ) parameters. If the pixel distance between the projected


position and the original detection is larger than the maximum reprojection error threshold (14–


18 pixels depending on experiment), the point is discriminated as an outlier and removed from


further processing of that frame.


**EMA** **smoothing:** Accepted 3D points are smoothed using an Exponential Moving


Average filter with smoothing coefficient _α_ = 0 _._ 25. This suppresses frame-to-frame jitter while


preserving the trajectory of a slowly moving target. The smoothed position is used as input to


20


the ballistic solver.

### **3.8 Ballistic Solver and Targeting Logic**


_**3.8.1**_ _**Target Vector Computation**_


The ballistic solver takes as input the current 3D world-frame target position _T_ = ( _Tx,_ _Ty,_ _Tz_ )


in millimetres, sourced from the EMA-filtered and confidence-gated triangulated joint posi

tion. The BLM pivot point (launch origin) is a fixed, calibrated world-frame coordinate _B_ =


( _Bx,_ _By,_ _Bz_ ) = (600 _,_ 1560 _,_ 500) mm.


The targeting vector from launcher to target is:


∆ _X_ = _Tx −_ _Bx_ (3.1)


∆ _Y_ = _Ty −_ _By_ (3.2)


∆ _Z_ = _Tz −_ _Bz_ (3.3)


The horizontal ground distance from launcher to target is:


_D_ horiz = �∆ _X_ [2] + ∆ _Y_ [2] (3.4)


_**3.8.2**_ _**Yaw Angle Computation**_


The required yaw (horizontal rotation) angle of the launcher to point at the target in the arena


plane is:


_θ_ yaw = atan2(∆ _Y,_ ∆ _X_ ) (3.5)


This is measured relative to the launcher’s reference direction (pointing along the posi

tive X axis). The result is converted to degrees and offset by the configured yaw trim parameter


`--yaw-trim-deg`, which compensates for any mechanical zero offset in the stepper motor hom

ing procedure.


21


_**3.8.3**_ _**Pitch Angle Computation**_


The pitch angle is derived from the projectile motion equations (2.2)–(2.4). For a target at


horizontal distance _D_ horiz and height difference ∆ _Z_, the required pitch angle _θ_ pitch for a given


initial ball speed _v_ 0 satisfies:


_g_ _·_ _D_ [2]
∆ _Z_ = _D_ horiz _·_ tan( _θ_ pitch) _−_ horiz (3.6)
2 _·_ _v_ [2]
0 _[·]_ [cos][2][(] _[θ]_ [pitch][)]


This is a transcendental equation in _θ_ pitch. For applied launch distances in the arena


(2000–5000 mm) and the chosen ball speeds, some numerical solving of the equation is done.


To minimise flight time and to enhance targeting precision for a moving athlete, the lower-angle


solution is chosen.


The result is compensated by the pitch trim parameter `--pitch-trim-deg` to eliminate


mechanical offset.


_**3.8.4**_ _**Wheel RPM Computation**_


Wheel RPM is proportional to desired initial ball speed _v_ 0. The empirical mapping of the RPM


and the ball speed is set up by calibration shots. A parameter `--speed-scale` can be used to


do runtime adjustment without changes to the firmware.


_**3.8.5**_ _**Why This Is Non-Trivial**_


The targeting computation is not a look-up table or pre-programmed direction. There are a


couple of reasons that make it a very real-time control challenge. First, the target _T_ is changed


every frame (at 15 FPS) when the athlete is moving, and the solver is required to run its calcu

lation within a single frame time (approximately 67 ms) to not issue stale commands. Second,


gravity serves to couple pitch angle to ball speed: the same target can be hit at multiple ( _θ_, _v_ 0)


combinations, and the solver is faced with having to choose the physically valid lower-angle


solution and verify that it is in the mechanical range of the launcher stepper (nominally _±_ 30


degrees from horizontal). Third, the BLM stepper motor has a finite step resolution, so the


solver rounds to the nearest achievable step position and logs the angular residual error for


post-session analysis. Fourth, the BLM’s mechanical zero (the position after `setzero` ) must be


22


registered to the world-frame coordinate system, and this registration is performed through the


yaw and pitch trim calibration procedure validated in the aim-only tests (Section 5.6).


_**3.8.6**_ _**Dynamic Target Tracking Behaviour**_


The system operates as a state machine with three targeting states. In the **ACQUIRING** state,


the joint has been detected in fewer than the minimum required cameras, or the EMA-filtered


position has not yet stabilised, and no command is dispatched. In the **LOW_CONFIDENCE**


state, the detection confidence is below threshold, or the joint position has changed by more


than 50 mm in the last 10 frames; the last valid command is held and the decision is logged as


LOW_CONFIDENCE. In the **READY** state, the joint position is stable (movement below 50


mm over 10 frames) and confidence is above threshold; the ballistic solve is executed and the


serial command is dispatched.


A transition from READY back to ACQUIRING occurs if the joint disappears from the


camera views (e.g., the athlete moves behind a wall or crouches below the camera field of view).


The system does not fire in any other state than that of the E-STOP cleared (READY).

### **3.9 Safety Architecture**


_**3.9.1**_ _**E-STOP Latch**_


An Emergency Stop function is designed as a software latch in the launcher runtime process.


When a user types `estop` in the runtime terminal, all the motor commands are immediately


stopped and the latch is placed. The system does not permit any additional actuation commands


until `clear` is explicitly typed by the operator to release the latch. The measured response time


from entry into the `estop` command to stop of the motor has a time of less than 100 ms.


_**3.9.2**_ _**Multi-Level Gating**_


Before any actuation command is dispatched, the following checks are performed in sequence.


First, the **E-STOP** **check** verifies that the latch is cleared. Second, the **camera** **count** **check**


confirms that at least two cameras have contributed to the current triangulation. Third, the **con-**


**fidence check** ensures that detection confidence exceeds threshold for all contributing cameras.


Fourth, the **zone check** verifies that the target coordinate falls within the defined safe operating


23


zone (nominally the central arena area; coordinates near walls or outside the arena bounds are


rejected as OUT_OF_RANGE). Fifth, the **stability check** confirms that the target is in READY


state (see Section 3.8.6).


Failure at any check results in the decision being logged as the appropriate failure cate

gory and no command being sent.


_**3.9.3**_ _**Six-Stage Integration Checklist**_


Integration of the full system follows a mandatory staged protocol to prevent unsafe operation


before each component has been validated in isolation. The six stages are as follows. **Preflight**


verifies the camera stream, calibration files, and serial line. **ESP32 Only** tests all motor com

mands via direct serial terminal with no camera or BLM active. **Runtime Without Cameras**


injects synthetic UDP target packets to verify solver and safety gating logic. **Live** **Aim-Only**


runs the full pipeline active, with motors commanded to correct aim angles and no ball loaded.


**Safety Verification** performs E-STOP, latch, link-loss, and zone-rejection tests under live con

ditions. **Controlled** **Firing** conducts single shots with ball loaded, one at a time, with the


operator present.


Each stage has defined pass criteria. A stage is not passed until all criteria are met and


evidence (terminal logs, video, JSONL records) is archived. Stage 6 defines full cycle reliability


testing.


24

# **CHAPTER 4.** **GROUND-TRUTH EVALUATION PROTOCOLS**

### **4.1 Ball Static Ground-Truth Dataset**


_**4.1.1**_ _**Dataset Design**_


A 36-point static dataset was designed to evaluate ball localisation accuracy across a represen

tative volume of the arena. The grid covers X at 3000, 4000, 5000 mm (3 positions, spanning


the central third of the arena depth), Y at 1000, 1600, 2300 mm (3 positions, spanning most of


the arena width), and Z at 200, 700, 1200, 1800 mm (4 heights, from near-floor to above head


height).


Total: 3 _×_ 3 _×_ 4 = 36 trials, labelled B001–B036.


_**Figure 4.1.**_ _**Ball static GT grid:**_ _**36-point 3D scatter in arena frame.**_


25


_**Table 4.1.**_ _**Ball static ground-truth grid definition**_

|X (mm)|Y (mm)|Z levels (mm)|Trial IDs|
|---|---|---|---|
|3000|2300|200, 700, 1200, 1800|B001, B010, B019, B028|
|4000|2300|200, 700, 1200, 1800|B002, B011, B020, B029|
|5000|2300|200, 700, 1200, 1800|B003, B012, B021, B030|
|3000|1600|200, 700, 1200, 1800|B004, B013, B022, B031|
|4000|1600|200, 700, 1200, 1800|B005, B014, B023, B032|
|5000|1600|200, 700, 1200, 1800|B006, B015, B024, B033|
|3000|1000|200, 700, 1200, 1800|B007, B016, B025, B034|
|4000|1000|200, 700, 1200, 1800|B008, B017, B026, B035|
|5000|1000|200, 700, 1200, 1800|B009, B018, B027, B036|



_**4.1.2**_ _**Capture Protocol**_


For each trial, a rigid holder positions the ball centre at the target coordinate, the scene is kept


static for 3–4 seconds with all four cameras recording, and the trial ID and any anomalies are


logged in `trials_notes.csv` .


The ball centre position is measured physically using a tape measure referenced to the


arena coordinate origin, with an estimated physical placement accuracy of _±_ 5 mm.


_**4.1.3**_ _**Processing**_


Each trial’s 4-camera clip is processed by `evaluate_ball_static_gt.py`, which extracts the


YOLO ball detection in each frame, runs triangulation with the configured parameters (confi

dence threshold 0.45, minimum 2 cameras, maximum reprojection error 14 px, EMA _α_ = 0 _._ 25),


and computes statistics over the stable hold window (the middle 60% of frames, excluding the


first and last 20% to avoid edge effects from placement and removal).

### **4.2 Joint-Touch Ground-Truth Dataset**


_**4.2.1**_ _**Dataset Design**_


The joint-touch dataset evaluates the 3D localisation accuracy of three specific human joints


under a controlled physical reference condition.


XY positions (9 points, 3 _×_ 3 grid in central arena area):


Platform heights (Z base): 0 mm, 400 mm, 640 mm (three rigid platforms of different


heights).


26


_**Table 4.2.**_ _**Joint-touch trial design:**_ _**XY grid positions (mm)**_

|XY Position Index|X (mm)|Y (mm)|
|---|---|---|
|1|2600|1100|
|2|3200|1100|
|3|3800|1100|
|4|2600|1600|
|5|3200|1600|
|6|3800|1600|
|7|2600|2100|
|8|3200|2100|
|9|3800|2100|



Joints evaluated: `right_knee`, `right_hip`, `left_shoulder` .


Expected joint heights above platform base are `right_knee` at base + 500 mm, `right_hip`


at base + 1000 mm, and `left_shoulder` at base + 1560 mm.


Total trials: 9 positions _×_ 3 heights _×_ 3 joints = 81 trials, labelled J001–J081.


_**Figure 4.2.**_ _**Joint-touch trial grid:**_ _**9 XY positions and 3 height levels.**_


_**Table 4.3.**_ _**Joint-touch platform and joint heights**_


|Platform Level|Z base (mm)|right_knee Z|right_hip Z|left_shoulder Z|
|---|---|---|---|---|
|Floor|0|500|1000|1560|
|Platform 1|400|900|1400|1960|
|Platform 2|640|1140|1640|2200|


27


_**4.2.2**_ _**Capture Protocol**_


For each trial, the subject stands with the designated body joint touching a physical target


marker placed at the specified XY position and height. The subject holds the position stati

cally for 3–4 seconds. Capture begins from a neutral (non-touching) position and transitions to


the hold; the evaluator extracts the hold window for analysis.


Validity criteria: a trial is valid if the joint is detected in at least 3 cameras during the


hold window, the detection ratio (frames with valid detection / total frames in hold window) is


_≥_ 0 _._ 80, and no obvious physical placement error was noted in the trial log.


Of 81 trials, 62 were classified as valid (76.5% validity rate). The 19 invalid trials were


mostly because of the camera visibility (the joint was occluded by the subject’s own body from


some camera angles) or the detection ratio was below threshold.


_**4.2.3**_ _**Processing**_


For each valid trial’s 4-camera clip, MMPose inference with confidence threshold 0.35, mini

mum 3 cameras for pose triangulation, maximum reprojection error 14 px, and EMA _α_ = 0 _._ 25


is applied. The triangulated 3D position value within the hold window is computed as a mean


value and is compared to the physical reference position.

### **4.3 Dynamic Validation Clips**


Successive dynamic validation clips were recorded to evaluate the behaviour of the system in


non-static conditions. The `ball_slow` clip (20 seconds) involves the ball being gently moved


with hand in the form of arcs and straight lines with the velocity of motion about 0.2–0.8 m/s; its


purpose is to evaluate temporal tracking stability and continuous 3D trajectory reconstruction,


with a pass criterion of no more than 3D frame-to-frame jumps of less than 800 mm. The


`ball_fast` clip (20 seconds) consists of real throws through the centre of the arena with normal


playing speeds with changes in direction and close to wall trajectories; its purpose is to stress

test detection under motion blur and rapid acceleration, with a pass criterion of acceptable


detection coverage, outlier rate controlled, and all detected points within arena bounds. The


`no_ball` clip (15 seconds) has the ball removed from the scene under normal arena lighting


28


with a person present and moving; its purpose is to measure false-positive ball detection rate,


with a pass criterion of false positive count close to zero.

### **4.4 Error Metrics and Bias Correction Model**


_**4.4.1**_ _**Primary Metrics**_


For each trial, the 3D Euclidean error is computed as:


~~�~~
_e_ = ( _x_ est _−_ _x_ gt) [2] +( _y_ est _−_ _y_ gt) [2] +( _z_ est _−_ _z_ gt) [2] (4.1)


where ( _x_ est _,_ _y_ est _,_ _z_ est) is the mean estimated 3D position over the hold window and ( _x_ gt _,_ _y_ gt _,_ _z_ gt)


is the physical reference position.


Summary statistics reported: mean error, median error, RMSE, 90th percentile (P90),


95th percentile (P95), and maximum error.


_**4.4.2**_ _**Axis Bias and Correction Model**_


Systematic errors in camera calibration manifest as biases in the estimated 3D positions. Per

axis bias vectors are computed as:


bias _X_ = mean( _x_ est _−_ _x_ gt) over all trials (4.2)


bias _Y_ = mean( _y_ est _−_ _y_ gt) over all trials (4.3)


bias _Z_ = mean( _z_ est _−_ _z_ gt) over all trials (4.4)


A linear correction model fits a scale and offset per axis to minimise residual error after


correction. The corrected estimate is:


_x_ corr = ( _x_ est _−_ bias _X_ ) _·_ scale _X_ (4.5)


Analogous expressions apply for Y and Z. The pipeline results reported in Chapter 5


29


use the corrected model. It should be noted that the bias and scale parameters were estimated


from the same 36-point static ball dataset used for final accuracy reporting; an independent


held-out calibration set was not used. The correction therefore reflects in-sample fitting, and


the reported corrected errors may underestimate the true generalisation error. This limitation


should be considered when interpreting the corrected accuracy figures.


30

# **CHAPTER 5.** **CHAPTER 5: RESULTS AND ANALYSIS**


Analogous expressions apply for Y and Z. The pipeline results reported in Chapter 5 use the


corrected model. It should be noted that the bias and scale parameters were estimated from


the same 36-point static ball dataset used for final accuracy reporting; an independent held-out


calibration set was not used. The correction therefore reflects in-sample fitting, and the reported


corrected errors may underestimate the true generalisation error. This limitation should be


considered when interpreting the corrected accuracy figures.

### **5.1 Intrinsic Calibration Results**


Intrinsic calibration was performed at 1280 _×_ 720 resolution for all four cameras using the


ChArUco auto-capture procedure. Subsequently 30–40 valid frames per camera were collected


to achieve stable parameter estimates.


Per-camera reprojection errors after calibration are in the range of 2–8 pixels between


the four cameras which is acceptable for this application. The difference between cameras is due


to the quality of the lenses and the spatial distribution of captured calibration poses. CamSouth,


located furthest from the area normally calibrated, had the highest reprojection error of this


range, and took 2 captures to get a valid calibration frame set.


The resulting K matrices confirm focal lengths in the expected range for a 1280-pixel

wide sensor with a moderately wide field of view, and distortion coefficients consistent with a


barrel distortion pattern typical of low-cost webcam lenses. Undistortion is applied to all frames


before detection inference and before triangulation.

### **5.2 Extrinsic Calibration Results**


Extrinsic calibration using the 24-AprilTag wall grid produced camera poses with residual re

projection errors of 3–7 pixels after robust outlier rejection. On average, sigma-scale = 2.0


outlier rejection removed 8–15% of tag corner observations, primarily from tags at oblique


31


angles near the arena edges where detection reliability decreases.


The overlay validation procedure (reprojecting known AprilTag corner positions back


into each camera frame and comparing with detected positions) confirmed visual alignment


across all four cameras. In all cameras, reprojected corners fell within 5–10 pixels of detected


corners across the majority of the visible tags.


The resulting world-frame camera positions (Table 3.1) are consistent with physical tape


measurements of the mounted camera positions to within approximately _±_ 30 mm, confirming


the calibration is geometrically reasonable.

### **5.3 Ball Static Localisation Results**


_**Table 5.1.**_ _**Ball static localisation summary metrics (corrected pipeline)**_

|Metric|Value|
|---|---|
|Trials valid|36 / 36 (100%)|
|Mean 3D error|95.17 mm|
|Median 3D error|84.18 mm|
|RMSE|102.23 mm|
|P90|142.18 mm|
|P95|166.51 mm|
|Maximum error|214.60 mm|
|Mean reprojection error|6.01 px|
|Mean cameras used|2.87|
|Mean detection ratio (hold window)|1.000|
|Mean temporal precision (std over hold)|3.79 mm|
|P95 temporal precision|8.51 mm|



The uncorrected pipeline exhibited systematic biases: X-axis bias of +50.68 mm (esti

mated positions shifted toward higher X), Y-axis bias of +46.57 mm (estimated positions shifted


toward higher Y), and Z-axis bias of −106.98 mm (estimated positions systematically below true


height).


The Z-axis bias is the dominant systematic error. It is attributed primarily to the camera


mounting heights: all four cameras are mounted near the ceiling, which means that they see


the ball from above. Triangulation of a ball at low Z (200–700 mm from the floor) consists of


shallow downward looking ray angles, which are geometrically sensitive to small calibration


errors of the extrinsic Z positions of the cameras. The negative Z bias is consistent with the


fact that the cameras have been calibrated as a bit lower than their true physical height causing


32


triangulated points to be placed below their true elevation.


After the application of the linear axis correction model the mean error decreases from


approx. 150.77 mm (raw) to 95.17 mm (corrected) and the P95 from approx. 288.34 mm to


166.51 mm. Both of the main acceptance criteria (mean < 120 mm, P95 < 200 mm) are met by


the corrected pipeline.


Temporal precision, defined as the standard deviation of repeated estimates of the same


static point over the hold window, averages 3.79 mm with a P95 of 8.51 mm. This demon

strates that the triangulation pipeline is highly repeatable given consistent input observations;


the dominant error source is systematic calibration bias rather than random noise.


_**Figure 5.1.**_ _**Ball static localisation:**_ _**raw vs corrected 3D error comparison, demonstrating**_
_**the linear bias correction model reducing mean error from 150.77 mm to 95.17 mm.**_


A spatial overview of the entire 36-point static evaluation grid is given in Figure 5.2.


These ground-truth positions (blue) are associated with its corrected estimate, coloured accord

ing to its error magnitude. The greatest errors (warm colours, 150–215 mm) are centred around


the corners of the arena and at the highest layer of the Z (1800 mm) where the cameras see


the ball at near-vertical angles and the geometry for triangulation is weakest. Low to moderate


errors (cool colours, <100 mm) dominate the mid-height layers (750–1300 mm), confirming


that the correction model is most effective in the central working volume of the arena.


The slice view in Figure 5.3 isolates each height layer, making the spatial distribution of


33


_**Figure 5.2.**_ _**3D scatter of ground-truth (blue) vs corrected estimated (coloured by error**_
_**magnitude) ball positions across all 36 trials.**_ _**The colour bar indicates error norm in mm.**_


_**Figure 5.3.**_ _**XY-plane slices at four Z heights (200, 750, 1300, 1800 mm) showing**_
_**ground-truth (blue circles) vs corrected estimates (red crosses).**_


34


errors easier to interpret. At Z = 200 mm and Z = 750 mm, the corrected estimates closely track


the ground-truth grid, with small and consistent offsets. At Z = 1300 mm, a slight drift in the


X direction becomes visible at the far end of the arena (X _≈_ 5000 mm). At Z = 1800 mm, the


offsets are largest and least uniform, reflecting the diminished triangulation baseline that results


from all cameras being mounted near the ceiling.

### **5.4 Human Pose Joint-Touch Results**


_**Table 5.2.**_ _**Joint-touch 3D ground-truth summary metrics (62 valid trials)**_

|Metric|Value|
|---|---|
|Trials valid|62 / 81 (76.5%)|
|Mean 3D error|143.38 mm|
|Median 3D error|148.90 mm|
|RMSE|147.73 mm|
|P90|182.04 mm|
|P95|198.73 mm|
|Maximum error|217.34 mm|



_**Table 5.3.**_ _**Per-joint error breakdown**_

|Joint|Mean error (mm)|P95 (mm)|
|---|---|---|
|right_knee|110.03|170.75|
|right_hip|150.38|172.31|
|left_shoulder|164.38|199.54|



The right knee achieves the lowest mean error (110.03 mm), consistent with its posi

tion at mid-height where all four cameras have favourable viewing geometry. The right hip is


observed at a greater height and can be partially occluded by the subject’s torso from lateral


cameras, resulting in higher error (150.38 mm). The left shoulder, at the greatest height (1560–


2200 mm depending on platform level), is closest to the ceiling camera mounting positions


and therefore observed at increasingly oblique angles; additionally, the left shoulder is the joint


most likely to be occluded by the subject’s head and neck. This produces the highest mean error


(164.38 mm).


The global P95 of 198.73 mm is below the acceptance threshold of 280 mm, and the


per-joint P95 values (170.75, 172.31, 199.54 mm) are all below the per-joint thresholds (220,


220, 250 mm respectively). The mean error of 143.38 mm is below the acceptance threshold of


180 mm.


35


The 19 invalid trials (23.5% of 81) represent a limitation of the evaluation methodology.


In most invalid cases, the subject’s body occluded the target joint from one or more cameras


during the hold, reducing the camera count below the minimum threshold. This is a real op

erational constraint: the system requires at least three cameras with clear joint visibility for


accurate 3D joint localisation.


_**Figure 5.4.**_ _**Joint-touch 3D error boxplot by joint type, showing right_knee (110.03 mm**_
_**mean), right_hip (150.38 mm), and left_shoulder (164.38 mm).**_


The box plot in Figure 5.4 agrees with the error hierarchy per joint quantitatively. The


right_knee has the lowest median error (111.5 mm), and the widest error in the spread (IQR


_≈_ 45 mm), including one outlier above 217 mm. The right_hip depicts a tighter distribution


(IQR _≈_ 20 mm) with a median of 150.7 mm suggesting better consistency of error but higher


errors. The left_shoulder has the greatest median (161.6 mm) and a narrow IQR, indicating that


the Z-axis bias has uniform effect on this high joint. Two outliers close to 205 mm (right_hip)


and 217 mm (right_knee) are trials in which the mannequin was placed at the arena boundary,


where less than three cameras were able to track the target joint.


Figure 5.5 visualises the spatial correspondence between ground-truth and estimated


joint positions in the full volume of the arena. The connecting lines between GT and EST


pairs highlight consistent directional offset between estimates with left_shoulder estimates in


blue setting an offset of -118 mm in Z and right_knee estimates in green having the smallest


mean displacement of 110 mm for the whole. The estimates from the right_hip (orange) have


a tight clustering in mid-volume with spatially uniform error. This joint-dependent pattern is


36


_**Figure 5.5.**_ _**Joint-touch ground-truth vs estimated positions:**_ _**3D scatter plot showing all 62**_
_**valid trials with GT markers and estimated positions colour-coded by joint type.**_


consistent with the varying visibility by the camera at different body heights, with lower joints


(knee) being more reliably triangulated, because they are in the strongest part of the camera


overlap zone.


Figure 5.6 summarises the per-joint mean errors as a bar chart: left_shoulder 164.4 mm,


right_hip 150.4 mm and right_knee 110.0 mm. The monotonic decrease in shoulder to knee is


coherent with the decreasing camera visibility with height of the body discussed in Section 5.4.

### **5.5 Dynamic Detection Results**


The 3D trajectory reconstructions for all 4 dynamic validation clips are shown in Figure 5.7.


There were no jumps in the 3D reconstruction at all: the _ball_slow_ clip ran for 20 seconds with


no frame-to-frame jumps measured over 800 mm. The EMA filter was able to suppress minor


jitter without lag being noticeable. In the _ball_fast_ clip, the trajectory is more erratic, which is to


be expected in the situation of higher ball speeds where their motion blur restricts their detection


confidence. A stronger EMA smoothing application ( _α_ = 0 _._ 1) in _ball_fast_ema0.1_ effectively


tightens the trajectory at the expense of a small lag. The _no_ball_ control clip correctly produced


no sustained trajectory, confirming the detector does not hallucinate ball positions when no ball


37


_**Figure 5.6.**_ _**Mean 3D error by joint type:**_ _**bar chart confirming the monotonic increase in**_
_**error from knee to shoulder, consistent with decreasing camera visibility at greater heights.**_


_**Figure 5.7.**_ _**Dynamic ball trajectory reconstructions:**_ _**3D plots of the four validation clips**_
_**(ball_slow, ball_fast, ball_fast_ema0.1, and no_ball) showing start (green) and end (red)**_
_**markers.**_


38


is present. These results confirm the pipeline is suitable for tracking moving targets at moderate


speeds in the arena.


39

# **CHAPTER 6.** **CHAPTER 6: CONCLUSIONS AND FUTURE WORK**

### **6.1 Summary of Contributions**


This thesis has presented the design, implementation, and quantitative evaluation of a vision

guided ball launching system validated through aim-only and controlled static single-shot trials.


The three stated contributions are assessed as follows:


Contribution 1, The Autonomous Aiming Machine: A Ball Launching Machine has


been demonstrated to autonomously compute and execute its own aim direction (pitch angle,


yaw angle, and launch speed) derived exclusively from live 3D reconstruction of a human ath

lete’s body joints. No human operator sets the trajectory. The system identifies the target joint


in three-dimensional space and directs the launcher accordingly, representing, to the best of the


author’s knowledge, a qualitative departure from the surveyed commercial ball machines.


Contribution 2, Low-Cost Multi-Camera Pose-to-Launch Pipeline: The complete per

ception pipeline (four commodity USB cameras at approximately USD 30 each, ChArUco


intrinsic calibration, AprilTag extrinsic calibration, YOLO ball detection, MMPose joint es

timation, and DLT/SVD triangulation) achieves a ball localisation mean error of 95.17 mm and


a joint localisation mean error of 143.38 mm in a real domestic arena. The total hardware cost


of the perception system is approximately USD 200.


Contribution 3, Structured Safety-Gated Integration Protocol: A six-stage incremental


integration checklist with per-stage pass criteria and mandatory decision logging has been de

veloped, progressed through Stages 0–4, and documented. The E-STOP latch responds in under


100 ms. Every actuation decision is recorded to a JSONL log providing full traceability.

### **6.2 Objectives Achievement**


This section evaluates whether the three research objectives defined in Section 1.2 have been


met, based on the quantitative results presented in Chapter 5.


**RQ1:** **Ball** **3D** **Localisation** **Accuracy.** The target was to achieve a mean 3D ball


40


localisation error below 120 mm using commodity USB cameras. The 36-point static ball


evaluation yielded a corrected mean error of 95.17 mm, RMSE of 102.23 mm, and P95 of


166.51 mm. The mean error target is satisfied with a margin of approximately 25 mm.


**RQ2:** **Human** **Pose** **Joint** **Localisation** **Accuracy.** The target was a mean 3D joint


localisation error below 180 mm. The 81-trial joint-touch evaluation (62 valid trials) yielded


a mean error of 143.38 mm, RMSE of 147.73 mm, and P95 of 198.73 mm. Per-joint analysis


shows right knee at 110.03 mm (best), right hip at 150.38 mm, and left shoulder at 164.38 mm


(worst, consistent with reduced camera visibility at shoulder height). The mean error target is


satisfied with a margin of approximately 37 mm.


**RQ3: Safe Staged Integration.** The target was to demonstrate a reproducible, evidence

based safety validation methodology. The six-stage integration checklist has been progressed


through Stages 0–4, with all pass criteria met. The E-STOP latch responds in under 100 ms.


Every actuation decision is recorded to a structured JSONL log. Stage 5 (full autonomous


closed-loop firing at a moving subject) remains as future work, so this objective is assessed as


partially satisfied.


Table 6.1 summarises the achievement status.


_**Table 6.1.**_ _**Research question objectives achievement summary**_

|Research Question|Target|Achieved|Status|
|---|---|---|---|
|RQ1: Ball 3D localisation|Mean error_ <_ 120 mm|95.17 mm|Satisfed|
|RQ2: Joint 3D localisation|Mean error_ <_ 180 mm|143.38 mm|Satisfed|
|RQ3: Safe integration|Staged safety validation|Stages 0–4 done|Partial|


### **6.3 Limitations**


Three-camera minimum requirement: Accurate 3D triangulation requires at least three cameras


with simultaneous line of sight to the target joint. At the edges of the arena, or when the


athlete’s body occludes certain cameras, the system degrades to two-camera triangulation with


significantly higher error. The 19/81 invalid joint-touch trials (23.5%) are primarily attributable


to this constraint.


Joint-touch ground-truth methodology: The physical contact protocol introduces a sys

tematic error between the surface contact point and the true joint centre (approximately 30–50


41


mm). This component of the measured error is not attributable to the vision system.


No BLM hardware homing: The ESP32 stepper motors use logical zero positioning


(software reset to setzero) with no physical limit switches or encoders. Cumulative step errors


over multiple sessions can drift the mechanical zero, requiring periodic re-homing. This limits


the long-term repeatability of absolute aim angles without recalibration.


Single-person, single-arena evaluation: All experiments were conducted with one sub

ject in one fixed arena. Generalisation to different subjects (different body proportions), differ

ent arenas, or different lighting conditions has not been evaluated.


Closed-loop firing not yet demonstrated: The system has been validated in aim-only


mode and in controlled static single-shot trials, but fully autonomous closed-loop shooting at a


moving human subject has not yet been demonstrated. This is the immediate next experimental


milestone.

### **6.4 Future Work**


_**6.4.1**_ _**Closed-Loop Autonomous Firing and Moving-Target Prediction**_


The immediate next step is to progress Stage 5 and Stage 6 of the BLM integration checklist:


controlled single-shot firing at a static human subject (aim-only confirmed, ball loaded), fol

lowed by moving-target trials. The latter requires predictive tracking: estimating the future


position of the target joint at the moment the ball will arrive (given ball flight time), rather


than targeting the current joint position. A simple linear extrapolation of the EMA-filtered joint


velocity is the proposed first implementation.


_**6.4.2**_ _**Empirical Ballistic Calibration Map**_


The current ballistic solver uses a first-principles projectile model neglecting aerodynamic drag


and the mechanical imprecision of the wheel-motor speed-to-velocity mapping. An empirical


calibration map, measuring actual ball landing positions for a grid of (RPM, pitch, yaw) settings,


would allow a correction table to be learned and applied at runtime, reducing systematic aiming


error. This is analogous to the bias correction model applied to the perception pipeline.


42


_**6.4.3**_ _**SLAM-Based Camera Re-Localisation and Self-Recalibration**_


Currently, any physical movement of a camera requires manual extrinsic re-calibration using the


AprilTag procedure. A SLAM (Simultaneous Localisation and Mapping) [31] approach would


allow the system to detect calibration drift automatically by tracking feature points between


sessions and flagging when reprojection errors exceed a threshold. This would make the system


self-monitoring and reduce the maintenance burden.


_**6.4.4**_ _**Multi-Person Tracking and Joint Assignment**_


The current system assumes a single person in the arena. Extending to multiple subjects re

quires person-level tracking (associating each detected skeleton with a specific individual across


frames and across cameras) and a mechanism for the operator to designate which person is the


target. Standard multi-object tracking algorithms (ByteTrack [32], StrongSORT [33]) are can

didates for this extension.


_**6.4.5**_ _**Virtual 3D Goal:**_ _**Replacing Physical Sensors with Camera-Based Impact Detection**_


A significant limitation of current training validation tools is their reliance on physical sensors


to detect whether the ball reached its target. Pressure mats, tripwires, and light-curtain arrays re

port a binary hit/miss signal. They require installation, can break down, cannot be repositioned


easily, and provide no information about where within the target zone the ball arrived.


The planned next major capability extension is a software-defined Virtual 3D Goal us

ing the existing 4-camera infrastructure. The concept is as follows: a 1 _×_ 1 metre rectangle


is defined in world-frame coordinates, centred on the target zone (e.g., centred on the athlete’s


torso at the expected interception height), oriented perpendicular to the expected ball trajec

tory. The camera system already tracks the ball’s 3D position frame-by-frame. When the ball’s


trajectory crosses this plane (detected via a ray-plane intersection test between consecutive 3D


position estimates), the system logs the exact 3D crossing coordinate, the ball velocity vector


at crossing, the time of crossing, and the offset from the designated target joint centroid. This


yields per-shot accuracy data with millimetre resolution, with no hardware required at the goal


location.


43


This concept is directly inspired by professional instrumented training arenas such as the


Footbot system [34], that define virtual goal boundaries in 3D space using multi-camera tracking


in contrast to physical sensors. Systems of this type at the professional level cost hundreds


of thousands of dollars and are installed only in elite training facilities. Since the 4-camera


perception infrastructure in this work is already deployed, calibrated and tracking the ball in


3D, the Virtual 3D Goal capability requires only additional software logic: the crossing event


detection algorithm, integration with the existing JSONL decision log and the visualisation of


crossing positions in 3D arena overlay.


This ability provides a complete transform into a full training instrument, going from


smart launcher to full, self-contained training capability, firing at the athlete and measuring if


the ball arrived at the desired target, and recording the result, while not having any actual sensor


hardware on the target (the goal). The data produced (a per-shot (x, y) impact map on the


virtual goal plane, with velocity and timing) would enable quantitative training analytics that


are currently unavailable in any affordable training system.

### **6.5 Professional and Ethical Considerations**


Physical safety: The BLM projects balls at speeds sufficient to cause injury, particularly at


close range or if directed at the face or head. The safety architecture described in Section 3.9


is designed to prevent unintended firing, but any deployment of the full system with live ball


launching must be accompanied by a physical safety briefing, mandatory personal protective


equipment (eye protection at minimum), and exclusion of bystanders from the ball flight path.


The six-stage integration protocol enforces that safety gating is validated before any ball is


loaded.


Video data and privacy: All ground-truth evaluation sessions involve video recording of


a human subject. Data is stored locally and has not been shared with third parties. Any future


publication of results should anonymise subject identity in published figures if the subject has


not provided explicit consent for identification.


Open-source intent: The processing pipeline, calibration scripts, evaluation tools, and


decision logging framework developed in this thesis are intended for open-source release. Mak

44


ing the full software stack publicly available would allow other researchers and practitioners to


replicate or extend the system, consistent with the goal of making adaptive ball delivery acces

sible beyond well-funded institutions.


Dual-use consideration: A system that can autonomously track human body parts and


direct a projectile at them has potential for usage in applications not related to sports training.


The authors comment on this and underpin that the safety architecture (presence of operator,


E-STOP control and explicit target designation) is necessarily the safeguard if this technology


is ever deployed.


45

# **REFERENCES**


[1] NaturalPoint Inc. Optitrack motion capture systems, 2024. URL `[https://optitrack.com](https://optitrack.com)` .


[2] M. Windolf, N. Götzen, and M. Morlock. Systematic accuracy and precision analysis of video


motion capturing systems   - exemplified on the vicon-460 system. _Journal_ _of_ _Biomechanics_, 41


(12):2776–2780, 2008.


[3] PhaseSpace Inc. Phasespace impulse x2e motion capture system, 2024. URL `[https://](https://phasespace.com)`


`[phasespace.com](https://phasespace.com)` .


[4] G. Bradski. The opencv library. _Dr. Dobb’s Journal of Software Tools_, 25(11):120–125, 2000.


[5] G. Jocher, A. Chaurasia, and J. Qiu. Ultralytics yolov26, 2025. URL `[https://github.com/](https://github.com/ultralytics/ultralytics)`


`[ultralytics/ultralytics](https://github.com/ultralytics/ultralytics)` .


[6] MMPose Contributors. Openmmlab pose estimation toolbox and benchmark, 2020. GitHub repos

itory.


[7] C. R. Harris, K. J. Millman, S. J. van der Walt, R. Gommers, P. Virtanen, D. Cournapeau, E. Wieser,


J. Taylor, S. Berg, N. J. Smith, R. Kern, M. Picus, S. Hoyer, M. H. van Krevelen, M. Brett,


A. Haldane, J. F. del Río, M. Wiebe, P. Peterson, P. Gérard-Marchant, K. Sheppard, T. Reddy,


W. Weckesser, H. Abbasi, C. Gohlke, and T. E. Oliphant. Array programming with numpy. _Nature_,


585(7825):357–362, 2020.


[8] P. Virtanen, R. Gommers, T. E. Oliphant, M. Haberland, T. Reddy, D. Cournapeau, E. Burovski,


P. Peterson, W. Weckesser, J. Bright, S. J. van der Walt, M. Brett, J. Wilson, K. J. Millman, N. May

orov, A. R. J. Nelson, E. Jones, R. Kern, E. Larson, C. J. Carey, [˙] I. Polat, Y. Feng, E. W. Moore,


J. VanderPlas, D. Laxalde, J. Perktold, R. Cimrman, I. Henriksen, E. A. Quintero, C. R. Harris,


A. M. Archibald, A. H. Ribeiro, F. Pedregosa, and P. van Mulbregt. Scipy 1.0: fundamental algo

rithms for scientific computing in python. _Nature Methods_, 17(3):261–272, 2020.


[9] R. Hartley and A. Zisserman. _Multiple View Geometry in Computer Vision_ . Cambridge University


Press, Cambridge, UK, 2nd edition, 2004.


46


[10] H. C. Longuet-Higgins. A computer algorithm for reconstructing a scene from two projections.


_Nature_, 293:133–135, 1981.


[11] T. Kanade and M. Okutomi. A stereo matching algorithm with an adaptive window: theory and


experiment. _IEEE_ _Transactions_ _on_ _Pattern_ _Analysis_ _and_ _Machine_ _Intelligence_, 16(9):920–932,


1994.


[12] G. Pingali, Y. Jean, and I. Carlbom. Real time tracking for enhanced tennis broadcasts. In _Proceed-_


_ings_ _of_ _IEEE_ _Conference_ _on_ _Computer_ _Vision_ _and_ _Pattern_ _Recognition_ _(CVPR)_, pages 260–265,


Santa Barbara, CA, 1998.


[13] P. R. Kamble, A. G. Keskar, and K. M. Bhurchandi. Ball tracking in sports: a survey. _Artificial_


_Intelligence Review_, 52(3):1655–1705, 2019.


[14] Hawk-Eye Innovations Ltd. Hawk-eye ball tracking technology, technical overview document,


2023.


[15] Z. Zhang. A flexible new technique for camera calibration. _IEEE Transactions on Pattern Analysis_


_and Machine Intelligence_, 22(11):1330–1334, 2000.


[16] S. Garrido-Jurado, R. Muñoz-Salinas, F. J. Madrid-Cuevas, and M. J. Marín-Jiménez. Automatic


generation and detection of highly reliable fiducial markers under occlusion. _Pattern Recognition_,


47(6):2280–2292, 2014.


[17] E. Olson. Apriltag: A robust and flexible visual fiducial system. In _Proceedings of IEEE Interna-_


_tional Conference on Robotics and Automation (ICRA)_, pages 3400–3407, Shanghai, China, 2011.


[18] M. A. Fischler and R. C. Bolles. Random sample consensus: a paradigm for model fitting with


applications to image analysis and automated cartography. _Communications_ _of_ _the_ _ACM_, 24(6):


381–395, 1981.


[19] J. Redmon, S. Divvala, R. Girshick, and A. Farhadi. You only look once: unified, real-time ob

ject detection. In _Proceedings_ _of_ _IEEE_ _Conference_ _on_ _Computer_ _Vision_ _and_ _Pattern_ _Recognition_


_(CVPR)_, pages 779–788, Las Vegas, NV, 2016.


[20] Z. Cao, G. Hidalgo, T. Simon, S. E. Wei, and Y. Sheikh. Openpose: realtime multi-person 2d


pose estimation using part affinity fields. _IEEE_ _Transactions_ _on_ _Pattern_ _Analysis_ _and_ _Machine_


_Intelligence_, 43(1):172–186, 2021.


47


[21] T. Y. Lin, M. Maire, S. Belongie, J. Hays, P. Perona, D. Ramanan, P. Dollár, and C. L. Zitnick.


Microsoft coco: common objects in context. In _Proceedings of European Conference on Computer_


_Vision (ECCV)_, pages 740–755, Zurich, Switzerland, 2014.


[22] K. Sun, B. Xiao, D. Liu, and J. Wang. Deep high-resolution representation learning for visual


recognition. _IEEE Transactions on Pattern Analysis and Machine Intelligence_, 43(10):3349–3364,


2019.


[23] J. L. Meriam and L. G. Kraige. _Engineering_ _Mechanics:_ _Dynamics_ . Wiley, Hoboken, NJ, 7th


edition, 2012.


[24] M. T. Jones. _Embedded Systems Design with the Atmel AVR Microcontroller_ . Cengage Learning,


Boston, MA, 2016.


[25] International Electrotechnical Commission. Iec 62061: Safety of machinery - functional safety


of safety-related control systems, 2021.


[26] International Organization for Standardization. Iso 10218-1: Robots and robotic devices — safety


requirements for industrial robots — part 1: Robots, 2011.


[27] International Organization for Standardization. Iso 12100: Safety of machinery — general princi

ples for design, 2011.


[28] I. Sommerville. _Software Engineering_ . Pearson, Harlow, UK, 10th edition, 2016.


[29] K. Muelling, J. Kober, O. Kroemer, and J. Peters. Learning to select and generalise striking move

ments in robot table tennis. _International Journal of Robotics Research_, 32(3):263–279, 2013.


[30] H. Fässler, H. A. Beyer, and J. T. Wen. A robot ping pong player: optimized mechanics, high


performance 3d vision and intelligent sensor control. _Robotersysteme_, 6:161–170, 1990.


[31] C. Cadena, L. Carlone, H. Carrillo, Y. Latif, D. Scaramuzza, J. Neira, I. Reid, and J. J. Leonard.


Past, present, and future of simultaneous localization and mapping: toward the robust-perception


age. _IEEE Transactions on Robotics_, 32(6):1309–1332, 2016.


[32] Y. Zhang, P. Sun, Y. Jiang, D. Yu, F. Weng, Z. Yuan, P. Luo, W. Liu, and X. Wang. Bytetrack:


multi-object tracking by associating every detection box. In _Proceedings of European Conference_


_on Computer Vision (ECCV)_, pages 1–21, Tel Aviv, Israel, 2022.


48


[33] Y. Du, Z. Zhao, Y. Song, Y. Zhao, F. Su, T. Gong, and H. Meng. Strongsort: make deepsort great


again. _IEEE Transactions on Multimedia_, 25:8725–8737, 2023.


[34] Footbot Ltd. Footbot interactive football training system, technical product description, 2024. URL


`[https://www.footbot.io](https://www.footbot.io)` .


49

# **APPENDIX A.** **BLM INTEGRATION TEST CHECKLIST**


The following table is the complete six-stage integration checklist used to govern safe deploy

ment of the Ball Launching Machine. Each row defines a test ID, stage, test description, and


pass criteria.


_**Table A.1.**_ _**BLM six-stage integration test checklist**_








|ID|Stage|Test|Pass Criteria|
|---|---|---|---|
|S0.1|Prefight|Camera and calibration load|Live viewer starts, 4 cams visible,<br>no crash for 2 min|
|S0.2|Prefight|Serial link to ESP32|Runtime opens serial and accepts<br>commands|
|S0.3|Prefight|Launcher pose sanity check|launcher_x/y/z/yaw validated with<br>static target|
|S1.1|ESP32 only|Manual low-level command<br>test|set, center, stop, shoot, reload all<br>execute correctly|
|S1.2|ESP32 only|Angle clamp test|Commands beyond _±_30 deg safely<br>clamped|
|S1.3|ESP32 only|RPM telemetry test|L: ... R: ... received while wheels<br>run|
|S2.1|Runtime|Synthetic UDP target feed|Runtime computes command and<br>sends set without error|
|S2.2|Runtime|Zone rejection test|Out-of-zone<br>targets<br>logged<br>as<br>OUT_OF_RANGE|
|S2.3|Runtime|Stability gating test|Noisy<br>targets<br>logged<br>as<br>LOW_CONFIDENCE|
|S3.1|Aim-only|Target acquire per joint|Each joint gets stable lock within<br>timeout|


50

|ID|Stage|Test|Pass Criteria|
|---|---|---|---|
|S3.2|Aim-only|Sequence behaviour|right_knee<br>_→_<br>right_hip<br>_→_<br>left_shoulder_ →_repeat|
|S3.3|Aim-only|Return to zero|After each aim, launcher returns to<br>centre|
|S4.1|Safety|E-STOP response time|estop causes immediate stop, re-<br>sponse_ <_ 100 ms|
|S4.2|Safety|E-STOP latch behaviour|System stays blocked until clear is-<br>sued|
|S4.3|Safety|Link-loss behaviour|On UDP/serial interruption, run-<br>time goes to safe stop|
|S5.1|Fire|Single shot on one joint|1 commanded shot after aim and<br>RPM gate|
|S5.2|Fire|No unintended extra shots|Exactly one shoot per trigger event|
|S5.3|Fire|Post-shot safe state|Returns to centre and waits for next<br>valid target|
|S6.1|Full cycle|10-cycle reliability|10 full target cycles without crash or<br>unsafe behaviour|
|S6.2|Full cycle|Decision log completeness|Every cycle has JSONL records<br>with required felds|
|S6.3|Full cycle|Report-ready outputs|Logs and summary plots generated|



Required JSONL decision log fields per event are: `timestamp`, `input_joint_name`,


`raw_world_xyz_mm`, `transformed_launcher_xyz`, `calculated_pitch_yaw_v`, `decision`


(OK / OUT_OF_RANGE / LOW_CONFIDENCE / ESTOP), and `execution_time_ms` .


51

# **APPENDIX B.** **KEY SCRIPT LISTINGS**

### **B.1 Live 4-Camera Arena View with UDP Target Streaming**


Canonical live visual command:


Listing B.1: Live 4-camera arena view command

```
 cd /home/hanush/Desktop/Project_Cam

 ./venv/bin/python garage_lab_combined/scripts/live_4cam_arena_view.py \

 --config garage_lab_combined/config/cameras.yaml \

 --intrinsics-dir garage_lab_combined/cal/intrinsics \

 --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \

 --dimensions garage_lab_combined/cal/extrinsics/Dimensions.txt \

 --ball-device cuda:0 \

 --pose-device cpu \

 --show-3d

### **B.2 Launcher Runtime Controller (UDP to Serial)**

```

Listing B.2: Launcher runtime controller invocation

```
 ./venv/bin/python garage_lab_combined/scripts/launcher_runtime_from_udp.py

```

_�→_ `\`

```
 --serial-port /dev/ttyUSB0 \

 --launcher-x-mm 600 \

 --launcher-y-mm 1560 \

 --launcher-z-mm 500 \

 --launcher-yaw-deg 0 \

 --targets left_shoulder right_hip right_knee \

 --dry-run-log-jsonl session_log.jsonl

```

52

### **B.3 Ball Static Ground-Truth Evaluation**


Listing B.3: Ball static ground-truth evaluation

```
 ./venv/bin/python garage_lab_combined/scripts/evaluate_ball_static_gt.py \

 --session-dir garage_lab_combined/gt_eval/ball_tuning_20260306 \

 --intrinsics-dir garage_lab_combined/cal/intrinsics \

 --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \

 --conf 0.45 \

 --ball-min-cams 2 \

 --ball-max-reproj-px 14 \

 --ball-ema-alpha 0.25

### **B.4 Joint-Touch Ground-Truth Evaluation**

```

Listing B.4: Joint-touch ground-truth evaluation

```
 ./venv/bin/python

```

_�→_ `garage_lab_combined/scripts/evaluate_pose_joint_touch_gt.py` `\`

```
 --session-dir garage_lab_combined/gt_eval/joint_tuning_20260310 \

 --intrinsics-dir garage_lab_combined/cal/intrinsics \

 --extrinsics garage_lab_combined/cal/extrinsics/extrinsics_main.json \

 --conf 0.45 \

 --pose-conf 0.35 \

 --pose-min-cams 3 \

 --ball-ema-alpha 0.25

```

53

# **APPENDIX C.** **GROUND-TRUTH DATA TABLES**

### **C.1 Ball Static GT: Full 36-Point Grid** **C.2 Joint-Touch GT: XY Grid and Height Levels**


54


|Trial|X_gt (mm)|Y_gt (mm)|Z_gt (mm)|
|---|---|---|---|
|B001|3000|2300|200|
|B002|4000|2300|200|
|B003|5000|2300|200|
|B004|3000|1600|200|
|B005|4000|1600|200|
|B006|5000|1600|200|
|B007|3000|1000|200|
|B008|4000|1000|200|
|B009|5000|1000|200|
|B010|3000|2300|700|
|B011|4000|2300|700|
|B012|5000|2300|700|
|B013|3000|1600|700|
|B014|4000|1600|700|
|B015|5000|1600|700|
|B016|3000|1000|700|
|B017|4000|1000|700|
|B018|5000|1000|700|
|B019|3000|2300|1200|
|B020|4000|2300|1200|
|B021|5000|2300|1200|
|B022|3000|1600|1200|
|B023|4000|1600|1200|
|B024|5000|1600|1200|
|B025|3000|1000|1200|
|B026|4000|1000|1200|
|B027|5000|1000|1200|
|B028|3000|2300|1800|
|B029|4000|2300|1800|
|B030|5000|2300|1800|
|B031|3000|1600|1800|
|B032|4000|1600|1800|
|B033|5000|1600|1800|
|B034|3000|1000|1800|
|B035|4000|1000|1800|
|B036|5000|1000|1800|


55


|Platform Level|Z base (mm)|right_knee Z|right_hip Z|left_shoulder Z|
|---|---|---|---|---|
|Floor|0|500|1000|1560|
|Platform 1|400|900|1400|1960|
|Platform 2|640|1140|1640|2200|


|XY Position Index|X (mm)|Y (mm)|
|---|---|---|
|1|2600|1100|
|2|3200|1100|
|3|3800|1100|
|4|2600|1600|
|5|3200|1600|
|6|3800|1600|
|7|2600|2100|
|8|3200|2100|
|9|3800|2100|


56

# **APPENDIX D.** **ARENA CALIBRATION FIGURES**


_**Figure D.1.**_ _**Arena floor plan with camera positions, AprilTag locations, and world-frame**_
_**axis overlay on all four live camera feeds.**_


57


_**Figure D.2.**_ _**Extrinsic overlay validation:**_ _**reprojected AprilTag corners (red/green markers)**_
_**overlaid on each camera’s live frame, confirming calibration accuracy.**_


_**(a)**_ _**(b)**_


_**(c)**_ _**(d)**_


_**Figure D.3.**_ _**3D arena world-frame renders showing camera positions (coloured markers),**_
_**BLM position (red), coordinate axes, and AprilTag wall positions from three viewing angles.**_


_**(a)**_ _**(b)**_ _**(c)**_


58


_**Figure D.4.**_ _**ChArUco calibration board (A4, 300 dpi, 7**_ _×_ _**10 squares, DICT_4X4_1000)**_
_**used for intrinsic calibration of all four cameras.**_


59


_**Figure D.5.**_ _**Intrinsic calibration reprojection error per camera:**_ _**bar chart showing**_
_**per-camera mean reprojection error after ChArUco calibration.**_


60


_**Figure D.6.**_ _**Extrinsic calibration RMSE per camera:**_ _**bar chart showing residual**_
_**reprojection error after robust PnP optimisation with sigma-clipping.**_


61

# **APPENDIX E.** **YOLO BALL DETECTOR TRAINING RESULTS**


_**Figure E.1.**_ _**YOLOv26s ball detector training curves:**_ _**loss, precision, recall, and mAP over**_
_**75 training epochs.**_


_**Figure E.2.**_ _**Normalised confusion matrix for the YOLOv26s ball detector on the validation**_
_**set.**_


62


_**Figure E.3.**_ _**Precision-Recall curve for the YOLOv26s ball detector.**_


_**Figure E.4.**_ _**Sample training batch:**_ _**YOLOv26s ball detection annotations on training**_
_**images.**_


63


_**Figure E.5.**_ _**Validation predictions vs ground truth.**_


_**(a)**_ _**(b)**_


64

# **APPENDIX F.** **SYSTEM QUALITATIVE RESULTS**


_**Figure F.1.**_ _**Live system smoke test frames showing 4-camera arena view with ball detection**_
_**(green bounding box), pose skeleton overlay (COCO 17-keypoint), and 3D triangulated**_
_**positions at three time points during continuous operation.**_


_**Figure F.2.**_ _**Smoke test frame at**_ _t ≈_ 5 _._ 3 _**s.**_


65


_**Figure F.3.**_ _**Smoke test frame at**_ _t ≈_ 13 _._ 3 _**s.**_


_**Figure F.4.**_ _**Smoke test frame at**_ _t ≈_ 21 _._ 3 _**s.**_


