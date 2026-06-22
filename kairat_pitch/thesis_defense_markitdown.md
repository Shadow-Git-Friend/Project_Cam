<!-- Slide number: 1 -->

![seds logo.jpg](Picture107.jpg)

![image.png](Picture106.jpg)

# Pose-Guided Predictive Ballistics
with Multi-Camera 3D Tracking

MSc Thesis Defense
School of Engineering & Digital Sciences · Nazarbayev University

Arlen Smagulov
Supervisor: Prof. Sultangali Arzykulov  ·  Co-supervisor: Prof. Mohammad Hashmi
Astana, 2026
1

Arlen · MSc ECE · Nazarbayev University

### Notes:
Good afternoon, committee. The title of the thesis is Pose-Guided Predictive Ballistics with Multi-Camera 3D Tracking. I am Hanush, MSc ECE. I will speak for about seventeen minutes and leave a three minute buffer inside our fifteen to twenty minute slot. I would ask that questions be held until the end so the argument can land as a whole. Transition cue: let me start with why this problem matters before we open any code or geometry.

<!-- Slide number: 2 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Motivation

Need for Low-Cost Pose-Reactive Ball Delivery

![](Picture4.jpg)

![student wearing a suit with sensors in a room that captures movements.](Picture2.jpg)
Fixed launchers cannot react

MoCap is costly and marker-based

Training needs joint-specific delivery

Low-cost cameras can bridge the gap

This thesis builds pose-guided aiming

Figure 2. RIT Motion Capture Lab
Figure 1. Soccer Innovations Ball Launcher

Takeaway: affordable pose-reactive training, Moving-target (Sec 1.3, 6.4).
RIT Motion Capture Lab image: https://www.rit.edu/facilities/motion-capture-mocap-labSoccer Innovations ball launcher image: https://soccerinnovations.com/ball-launcher/

2

### Notes:
“This project starts from a simple gap.
Commercial ball launchers can repeat shots, but they cannot react to the athlete. They do not know where the player is or which body part should receive the ball.
Professional motion-capture systems can track the body accurately, but they are expensive, marker-based, and mainly used in labs.
So, the motivation is to build a low-cost, markerless system that uses cameras to estimate body joints in 3D and guide the ball launcher.”

<!-- Slide number: 3 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Problem Statement & Objectives

Can a ball launcher use 3D body-joint tracking for safe autonomous aiming?

Ball localisation
Joint localisation
Objective 2
Objective 1
Mean 3D ball error below 120 mm  →  Achieved: 95.17 mm corrected
Mean 3D joint error below 180 mm  →  Achieved: 143.38 mm (62 trials)

Safe integration
Practicality
Objective 4
Objective 3
Commodity cameras, open-source stack, and low-cost perception hardware.
Six-stage validation S0–S4 completed 2026-04-09. E-STOP <100 ms

Takeaway: all four objectives are met. Unvalidated boundary: closed-loop firing at a moving subject — the immediate next milestone.

3

### Notes:
“The main question is whether a ball launcher can use real-time 3D body-joint tracking for safe autonomous aiming.
I focused on four objectives.
First, ball localisation. The target was below 120 millimetres mean 3D error, and the achieved result was 95.17 millimetres.
Second, joint localisation. The target was below 180 millimetres, and the achieved result was 143.38 millimetres over 62 valid trials.
Third, safe integration. The system passed stages S0 to S4, and the emergency stop response was below 100 milliseconds.
Fourth, practicality. The perception system uses four USB cameras and costs about 200 US dollars.
So, the system is validated in static and live-aim conditions. Moving-target closed-loop firing remains the next milestone.”

<!-- Slide number: 4 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Background & Research Gap

Gap: low-cost systems rarely combine 3D joint tracking with physical launcher actuation.
Table 1. Existing categories and the gap this thesis fills.

Approach

Cost

Accuracy

Markerless

Closed-loop

Optical MoCap (OptiTrack, Vicon)

USD 50k–200k

Very High

No

No launcher

Commercial launchers

USD 200–4k

N/A

Yes

Open-loop only

Vision-guided sports robots [24,25]

USD 2k–10k

Medium–high

Usually

Fixed zones; ball-only

This work

~USD 500

Targeting-level

Yes

Aim + controlled single-shot

Takeaway: low-cost markerless 3D perception is connected to real launcher aiming; moving-target firing remains next.

4

### Notes:
Here I compare my system with the closest existing categories.
Commercial ball launchers are affordable and useful for repetitive training, but they are open-loop. They do not sense the athlete and cannot adapt the shot to a specific body part.
Optical motion-capture systems, such as Vicon or OptiTrack, provide very high 3D accuracy. However, they are expensive, marker-based, and mainly used for tracking only. They are not integrated with a ball launcher.
Vision-guided sports robots are closer to my work because they combine vision with physical actuation. However, they usually target fixed zones, for example in tennis or table-tennis setups, rather than named body joints such as the knee, hip, or shoulder.
My thesis focuses on this gap: a low-cost, markerless system that reconstructs body joints in 3D and connects them to a real Ball Launching Machine. In this work, static and live-aim integration are validated, while moving-target closed-loop firing remains the next milestone.”

<!-- Slide number: 5 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Key Technical Components

Six contributions across perception, control, safety, and interaction
01
Pose-reactive aiming at low-cost
Markerless, aim-only validated, commodity hardware
02
Validated 4-camera 3D targeting pipeline (Table 5.1)
DLT/SVD, 95.17 mm corrected ball mean
03
High-speed YOLO-Pose launch loop
6.2 ms/frame TRT FP16, 15 FPS live pipeline
04
Six-stage safety validation architecture (Sec 3.14.3)
S0-S4 passed 2026-04-09, E-STOP <100 ms
05
Multi-modal voice command interface
Offline ASR + UDP inter-process channel
06
Reproducible GT datasets & JSONL logs
36-pt ball grid + 81-trial joint-touch protocol

Takeaway:a conventional launcher is upgraded into a pose-guided, safety-gated training system.

5

<!-- Slide number: 6 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# What I inherited — and what I built

Upgrading a 2-DOF launcher to the Working vision, 3D targeting, and safety machine.

Inherited (BLM)
2-DOF ball launcher

Flywheels + ESP32

Pan/tilt actuation
			Open-loop only
Thesis additions
4-camera perception

3D joint targeting

Safety supervisor
Static/live-aim validated
No perception
Validated scope
✓ Static shots
✓ Live aim-only
↻ Moving target (next)

Takeaway: inherited BLM hardware upgraded with pose-guided aiming and safety gating.

6

### Notes:
This slide is where I clearly separate inherited hardware from my thesis contribution. The launcher platform did not start from zero, but the thesis contribution is not mechanical duplication. It is the integration of perception, triangulation, ballistic computation, safety gating, and evaluation into one working autonomous loop. Saying this early helps the committee attribute the right novelty to the thesis rather than to the entire machine history.

<!-- Slide number: 7 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# The pose-to-aim pipeline

Low-cost 3D perception → prediction → safety-gated BLM control
Output
Safe set command + aimed BLM
Input
4 camera frames
→
Perception
4 cameras + YOLO-Pose · 6.2 ms/badge
1
↓
3D reconstruction
DLT/SVD joint triangulation · 1.0 ms
2
↓
Prediction + ballistics
Kalman filter · pitch/yaw/RPM solver · 1.6 ms
3
↓
Safety supervisor
Zones · confidence · E-STOP <100 ms
4
↓
Firmware + actuation
ESP32 FSM · 921,600 baud serial
5

Takeaway: the thesis contribution is the integration of perception, prediction, safety, and BLM control.

7

### Notes:
This slide is where I clearly separate inherited hardware from my thesis contribution. The launcher platform did not start from zero, but the thesis contribution is not mechanical duplication. It is the integration of perception, triangulation, ballistic computation, safety gating, and evaluation into one working autonomous loop. Saying this early helps the committee attribute the right novelty to the thesis rather than to the entire machine history.

<!-- Slide number: 8 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Architecture & Pipeline

End-to-end runtime: ≈15 ms, below the 67 ms frame budget at 15 FPS.

![](Picture11.jpg)

Takeaway: compute pipeline ≈15 ms; 52 ms headroom remains within the 67 ms frame budget.

8

### Notes:
“The system runs as a left-to-right pipeline. First, four camera frames are captured, then YOLO detects the ball and pose keypoints using TensorRT FP16. The detections are triangulated into 3D using SVD-DLT, then smoothed with adaptive EMA and a per-joint Kalman filter.
The predicted joint position is sent through UDP to the Python supervisor, where the ballistic solver computes pitch, yaw, and wheel speed. The command is then sent over a 921,600-baud serial link to the ESP32 finite-state machine.
The important point is timing. The compute pipeline takes about 15 milliseconds end-to-end, which is well below the 67 millisecond frame budget for 15 FPS. This gives around 52 milliseconds of headroom for overhead, mechanical settling, and safety checks.”

<!-- Slide number: 9 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Hardware Implementation

Practical actuation paired with low-cost components:

![](Picture14.jpg)

![](Picture6.jpg)

![](Picture4.jpg)
4× Hikvision DS-E12 USB cameras (1280×720, ~$30 each).

ESP32 MCU running cooperative FSM (921,600 baud serial link).

![](Picture11.jpg)

![](Picture5.jpg)

![](Picture7.jpg)

![](Picture9.jpg)

![](Picture8.jpg)
NEMA-23 steppers with worm-gear reducers (self-locking for safety).

Takeaway: expensive MoCap is not required for the validated pose-guided aiming pipeline.

9

### Notes:
This slide shows the hardware implementation.
The perception side uses four low-cost Hikvision USB cameras, each running at 1280 by 720 resolution. These cameras are placed around the garage arena and calibrated into one shared 3D coordinate frame using AprilTag markers on the walls.
The actuation side uses the inherited Ball Launching Machine platform. It includes an ESP32 controller, NEMA-23 stepper motors for pan and tilt, worm-gear reducers for self-locking, and counter-rotating flywheels for launching the ball.
The important point is that the expensive part of professional motion capture is replaced by a low-cost camera setup. The perception hardware is about 200 US dollars, while the launcher hardware is integrated as the actuation platform.”

<!-- Slide number: 10 -->

![image.png](Picture2.jpg)
SEDS · NU
Safety architecture

Defence-in-depth: every actuation command must defeat all gates before the launcher moves.
SOFTWARE GATES — L1 TO L7, L9–L10
HARDWARE GATE — L8
Zone gate
Target must lie inside per-joint safe zone
L1

Hardware E-STOP (L8)
Normally-closed mushroom switch – Latches 24 V motor rail off in <100 ms – Cannot be overridden in software

Confidence gate
Min 3 cameras + confidence > 0.45
L2
Stability gate
Sliding-window std dev below threshold
L3
INTEGRATION STAGES
S0
Preflight
S1
ESP32
S2
No cams
S3
Live aim
S4
Safety
S5
Fire →
Angle clamp
Pitch [0°–30°] · yaw [−30°–30°]
L4
✓ S0–S4 passed on real hardware · 2026-04-09
RPM gate
Both flywheels ≥ 400 RPM before fire
L5
ISO 12100
ISO 13849-1
IEC 60204-1
ISO 10218-1
Link-loss safe stop
UDP timeout → auto stop + zero command
L9
Exception path
Any uncaught Python exception → safe stop
L10

Takeaway: 10 layered gates + hardware E-STOP ensure no unsafe actuation is possible; S0–S4 validated on real hardware.

10

<!-- Slide number: 11 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Software Implementation

YOLO-Pose + TensorRT enables real-time 4-camera inference within the 67 ms frame budget.

Layer

Module / Tool

Perception

YOLO-Pose + custom YOLO ball detector

![](Picture4.jpg)

Inference

TensorRT FP16, 4-camera batch

Geometry

SVD-DLT multi-view triangulation

Robust ball

iterative reprojection-error rejection

Filter

adaptive EMA + CV Kalman prediction

Supervisor

Python, safety gates, ballistic solver

Firmware

control_12_full.ino, ESP32 FSM

Takeaway: multi-camera detections become safety-gated pitch, yaw, and RPM commands.

11

### Notes:
“This slide shows the software implementation. The perception system uses YOLO-Pose for body joints and a custom YOLO detector for the ball. Both are accelerated with TensorRT FP16 so that four-camera inference fits inside the 15 FPS timing budget.
After detection, the system triangulates 2D observations into 3D using SVD-DLT. The result is smoothed with adaptive EMA and predicted using a constant-velocity Kalman filter.
The Python supervisor then applies safety gates and computes the ballistic command: pitch, yaw, and wheel RPM. Finally, the ESP32 firmware receives the command and executes it through the finite-state machine.
So the key idea is that the software converts camera detections into safe launcher commands.

<!-- Slide number: 12 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Calibration & Geometry

Unifying four cameras into one millimetre-scale world frame.

![](Picture4.jpg)

Takeaway: one calibrated world frame enables 3D joint coordinates from four USB cameras.

12

### Notes:
This slide explains how the four cameras are connected into one coordinate system.
First, each camera is intrinsically calibrated using a ChArUco board. This gives the camera matrix and distortion parameters.
Second, the arena uses 24 AprilTag markers on the walls. These are used for extrinsic calibration, so each camera has a known position and orientation in the same world frame.
The origin is defined at the arena floor corner, and all coordinates are measured in millimetres.
After this, 2D detections from multiple cameras can be triangulated using SVD-DLT. For human joints, I require at least three camera views because pose keypoints are noisier than ball detections.”

<!-- Slide number: 13 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Methodology & Experiments

Evaluation combines localisation accuracy, dynamic tracking, safety, and traceability.

Experiment

Input

Metric

Outcome

Ball GT

36-point grid

Mean / P95

95.17 mm mean

Joint-touch GT

81 trials

Mean / P95

143.38 mm, 62 valid

Dynamic clips

3 clips

Stability

3D trajectory verified

Bias correction

Axis offsets from GT

Corrected vs raw error

Ball mean drops to 95.17 mm

Safety checklist

S0–S4

Pass / fail + logs

Passed, E-STOP <100 ms

Decision logging

JSONL logs

Auditability

Every actuation logged

Takeaway: quantitative localisation, safety gates, and logging support controlled live-aim validation.

1313

### Notes:
For evaluation, I used four main experiment groups.
First, ball localisation was tested using a 36-point static grid. After bias correction, the mean 3D error was 95.17 millimetres.
Second, joint localisation was tested using a joint-touch protocol. Out of 81 trials, 62 were valid, with a mean 3D error of 143.38 millimetres.
Third, I tested dynamic clips such as slow ball motion, fast ball motion, and no-ball scenes to check stability and false positives.
Finally, the BLM integration was tested using a staged safety protocol from S0 to S4, with JSONL logging for every decision. This makes each command traceable and keeps the evaluation safety-gated

<!-- Slide number: 14 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# A1 · Live Demo

Arena 3D tracking

14

### Notes:
Play if asked for a demo or if a three-to-five-minute buffer opens. Mute audio. Keep the clip to twenty or thirty seconds; longer loops lose the panel. Before pressing play, state what they are looking at: four-camera capture, live triangulation, and Kalman-smoothed joint trace. If the video cannot be embedded inline on the target machine, substitute the mosaic2d fallback from V-02 in the assets checklist and narrate the same framing.

<!-- Slide number: 15 -->

![image.png](Picture2.jpg)
SEDS · NU
Results — visual proof

Both localisation objectives met. All errors fall below their acceptance thresholds.

Objective 1 — Ball localisation error
Objective 2 — Joint localisation by body part
180 mm
3D mean error (mm) · threshold: 180 mm
3D mean error (mm) · threshold: 120 mm

Right
knee
✓
110
120 mm

Raw
pipeline

✗
150.8

✓
Right
hip
150

✓
Corrected
pipeline
Left
shoulder

✓
164

95.2

─ 120 mm threshold  —  37% improvement from bias correction (in-sample, Sec 4.4.2, 6.3)
─ 180 mm threshold  —  knee is easiest, shoulder hardest
Objective 2 passed · all 3 joints < 180 mm ✓
Objective 1 passed · 95.2 mm < 120 mm ✓
95.2 mm
corrected ball mean
(obj. 1 threshold: 120)
143.4 mm
joint mean overall
(obj. 2 threshold: 180)
<100 ms
E-STOP latch
response time
15 FPS
live YOLO-Pose
pipeline speed

Takeaway: bias correction drops ball error 37% below threshold; all three joints clear the 180 mm target.

15

<!-- Slide number: 16 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Key Results — Accuracy, Safety, Runtime

Acceptance thresholds met within the validated static/live-aim scope.

![](Picture10.jpg)

![](Picture12.jpg)

Takeaway: localisation targets were met; safety and runtime support static/live-aim validation.

1616

### Notes:
This slide summarises the main results.
For ball localisation, the corrected mean 3D error was 95.17 millimetres, which is below the 120 millimetre target.
For joint localisation, the mean error was 143.38 millimetres across 62 valid trials, below the 180 millimetre target. The knee had the lowest error, while the shoulder had the highest error because it is higher in the arena and has weaker camera overlap.
The safety result was also validated in the static and live-aim regime. The emergency stop response was below 100 milliseconds.
Finally, the software runs at 15 FPS. YOLO-Pose with TensorRT processes a four-camera batch in about 6.2 milliseconds, which fits within the real-time frame budget

<!-- Slide number: 17 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Limitations & Challenges

Validated: perception, 3D targeting, safety gates, and static/live-aim tests.
Pending: moving-subject closed-loop firing.

![](Picture5.jpg)

Takeaway: the validated scope (perception → safety-gated static shots) is a strong partial validation. The unvalidated boundary is precisely defined: moving-subject closed-loop firing.

1717

### Notes:
This slide summarises the main limitations.
The system is validated for perception, 3D targeting, safety gates, and static or live-aim tests. However, fully autonomous closed-loop firing at a moving subject has not yet been validated, and I define this clearly as the next milestone.
There are also practical limitations. The evaluation used one subject, one indoor arena, and controlled lighting. In the joint-touch experiment, 19 out of 81 trials were invalid mainly because the joint was not visible from enough cameras.
Another limitation is the ballistic model. The RPM-to-velocity calibration is still missing, so future work should measure the real exit velocity of the ball at different wheel speeds.
Finally, the Kalman filter works well for smooth walking or jogging, but abrupt jumps are harder because they violate the constant-velocity assumption

<!-- Slide number: 18 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Conclusions & Contributions

Static/live-aim validation completed; moving-target firing remains future work.

Low-cost 3D perception
2
Perception ≈USD 120; Total ≈USD 500

Training-mode interface
Pose-reactive aiming
4
1
Voice commands behind safety gates
BLM aims from live 3D joints

Safety-gated integration
3
S0–S4 passed; E-STOP <100 ms

Takeaway: strong partial validation; key disadvantage: moving-target firing NOT validated.

1818

### Notes:
To conclude, this thesis makes four main contributions.
First, it demonstrates pose-reactive aiming, where the launcher computes pitch, yaw, and wheel-speed commands from live 3D body-joint positions.
Second, it shows that low-cost 3D perception is feasible using four commodity USB cameras and open-source vision tools, with perception hardware around 200 US dollars.
Third, it contributes a safety-gated integration protocol. The system passed stages S0 to S4, the emergency stop response was below 100 milliseconds, and every actuation decision was logged.
Fourth, it integrates a training-mode interface where voice commands can select joints and control the system without bypassing the safety gates.
Overall, the thesis provides a strong partial validation of the pose-guided BLM concept. The remaining milestone is full closed-loop firing at a moving subject.

<!-- Slide number: 19 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
# Future Work + Ethics & Standards

Next milestone: moving-target closed-loop firing with calibrated RPM-to-velocity mapping.
Safety & Ethics
Future roadmap

ISO 12100
ISO 13849-1
Safety-related control — NC E-STOP = Cat-1 stop
Machinery safety — L1–L10 hazard analysis

IEC 60204-1
ISO 10218-1
Wiring, fusing — 24V/50A fuse sizing
Exclusion zone during operation
Applicability: sports training, rehabilitation, adaptive PE. Dual-use potential acknowledged (Sec 6.5).

Takeaway: future work closes the moving-target loop while preserving safety, traceability, and ethical deployment.

1919

### Notes:
This final slide shows the roadmap and safety framing.
The immediate next milestone is moving-target closed-loop firing. To do that properly, the RPM-to-velocity calibration must first be completed, because the system needs the ball flight time to aim at the predicted future joint position.
After that, the next steps are predictive lead compensation, SLAM-based camera re-localisation, and the Virtual 3D Goal, which would measure ball impact using the same camera system instead of physical sensors.
On the safety side, the design is aligned with machinery and robotics safety principles: risk assessment, safety-related control, electrical safety, emergency stop behaviour, and human exclusion during operation.
So future work is not only about increasing autonomy. It is about closing the moving-target loop while keeping the system safe, traceable, and ethically controlled.”

<!-- Slide number: 20 -->

![nu_theme-2.png](NUThemeBackground.jpg)

Acknowledgements

![Supervisor person icon](Graphic62.jpg)

![Colleagues group icon](Graphic64.jpg)

![Co-supervisor people icon](Graphic63.jpg)
Thank You
Supervisor
Co-supervisor
Colleagues
Dr. Sultangali Arzykulov
Dr. Mohammad Hashmi
Yessimkhan Orynbay
Azamat Shmitov
Altay Kairat
I sincerely thank my Supervisor, Co-Supervisor, and colleagues for their guidance and support
Questions are welcome.
2020

<!-- Slide number: 21 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
APPENDIX
# A2 · 10-Layer Safety Stack

OPERATOR (human authority, top) → SOFTWARE GATES (L1-L6: zone, confidence, stability, angle clamps, RPM clamps) → HARDWARE INTERLOCKS (L7-L10: firmware RPM gate, arm+confirm, NC E-STOP, link-loss watchdog, exception shutdown). Each layer is independently sufficient to prevent unsafe actuation.

L1

Zone gate — reject targets outside safe arena

L6

RPM gate (Python side)

L2

Confidence gate — per-joint + ball detection score

L7

RPM gate (firmware side)

L3

Stability gate — multi-frame temporal filter

L8

Arm state + typed confirmation

L4

Angle clamp (Python side)

L9

Hardware E-STOP (NC) + link-loss watchdog

L5

Angle clamp (firmware side)

L10

Python exception path — safe shutdown
[Hidden slide — unhide only if panel asks a relevant question]

Key points: angle clamp and RPM gate each implemented TWICE (Python + firmware). NC E-STOP means broken wire = safe stop. Link-loss watchdog auto-safes on network drop.

### Notes:
Use if the panel asks what happens if X fails. Walk from L1 down: software gates first, then hardware interlocks, then the human authority. Key points to volunteer: the angle clamp and RPM gate are each implemented twice, once in Python and once on the ESP32, so either layer alone is sufficient. The hardware E-STOP is normally-closed so a broken wire stops the machine, not starts it. Close by naming the link-loss watchdog as the answer to network-drop questions.

<!-- Slide number: 22 -->

![nu_theme-2.png](NUThemeBackground.jpg)

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
SEDS - NU
APPENDIX
APPENDIX
# A3 · End-to-End Latency Budget
A3 - End-to-End Latency Budget

Per-stage timings from the live run.

![](Picture48.jpg)

[Hidden slide — unhide only if panel asks a relevant question]
[Hidden slide - unhide only if panel asks a relevant question]

Total perception: ~15 ms. Well under the 67 ms (15 FPS) budget with 52 ms headroom. Kalman 200-400 ms prediction window covers the mechanical settling time — this is why predictive tracking matters.
Total perception ~15 ms; budget 67 ms; headroom 52 ms.

### Notes:
Use if the panel asks about real-time guarantees. Before pointing at numbers, name the three dominant stages: YOLO inference, triangulation plus Kalman, and mechanical settling. Volunteer that the ninety-fifth percentile for perception stays inside two frame intervals at fifteen FPS, which is why the Kalman predict-step of two hundred to four hundred milliseconds covers worst-case launcher travel. If pushed, note that the latency table is the artifact behind the hundred-and-twenty millisecond claim on slide six.

<!-- Slide number: 23 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
APPENDIX
# A4 · ECE Curriculum Mapping

Courses → concepts → evidence in the thesis.

Course

Concept used

Evidence in thesis

Signals & Systems

Kalman filter, EMA, frequency domain

Per-joint CV Kalman; adaptive EMA tuning

Control Systems

Closed-loop feedback, stability

Supervisor → FSM → motor loop; stop paths

Embedded Systems

RTOS-like cooperative FSM, UART

control_12_full.ino at 921,600 baud

Computer Networks

UDP vs TCP, link-loss handling

UDP target broadcast + watchdog timeout

Engineering Ethics

Risk, safety, responsible deployment

ISO 12100 / 13849-1 / IEC 60204-1 alignment
[Hidden slide — unhide only if panel asks a relevant question]

### Notes:
Use only if asked which courses prepared you for this. Pick two rows to highlight, not five. Signals and Systems maps directly to the Kalman filter and the EMA smoother. Control Systems is the supervisor-to-motor loop. Embedded Systems is the cooperative finite-state machine in control_12_full.ino. Computer Networks covers the UDP link and the watchdog. Engineering Ethics maps to the three ISO standards on slide fifteen. End with one sentence on which course was most directly applied.

<!-- Slide number: 24 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
APPENDIX · Q&A BACKUP
# Q: Why not use Intel RealSense depth cameras?
Cost, redundancy architecture, and occlusion tolerance drive the 4x USB camera choice
 Cost comparison
 4x Hikvision DS-E12 USB cameras: ~$120 total ($30 each)
 4x Intel RealSense D435: ~$800+ total ($200+ each)
 Recycled PC handles all inference — no depth-specific compute needed
 Redundancy architecture
 4 overlapping views: if one camera is occluded, 3 remain for triangulation
 RealSense single unit = single point of failure; depth occlusion by ball or limb is common
 DLT/SVD triangulation explicitly designed for variable camera-count inputs
 Accuracy argument
 95.17 mm corrected ball mean achieved with commodity RGB cameras
 RealSense depth noise at 3-5 m range is 3-20 mm — marginal gain for 7x cost increase
 Scope
 Controlled indoor arena only. Outdoor / variable lighting is acknowledged future work.

### Notes:
Answer: 4x USB cameras give occlusion redundancy, cost $120 vs. $800+ for RealSense, and already achieve 95.17 mm accuracy at indoor arena distances.

<!-- Slide number: 25 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
APPENDIX · Q&A BACKUP
# Q: How does the Kalman filter handle sudden position jumps?
Constant-velocity model with process noise — tested in Section 5.7, honest about limitations
 Kalman model used
 Constant-velocity (CV) model: state = [x, y, z, vx, vy, vz]
 Process noise Q tuned to allow fast re-acquisition after direction changes
 Prediction window: 200-400 ms ahead to compensate mechanical settling time
 Jump sequence behaviour (Section 5.7)
 On sudden position jumps, prediction error spikes then recovers within 2-3 frames (133-200 ms)
 Ablation showed neutral-to-negative improvement on jump sequences vs. EMA alone
 This is acknowledged honestly: Kalman helps smooth normal motion, not abrupt jumps
 Why it still matters
 For steady-state walking/running, CV Kalman reduces targeting jitter significantly
 The 200-400 ms prediction covers mechanical lag — without it, the shot always hits where the target WAS
 Extended Kalman or IMM models are future work for jump-robust prediction

### Notes:
Answer: CV Kalman works well for smooth motion; jump sequences show neutral improvement vs. EMA alone (acknowledged in Section 5.7). The prediction window is essential to cover mechanical settling lag.

<!-- Slide number: 26 -->

![nu_theme-2.png](NUThemeBackground.jpg)
SEDS · NU
APPENDIX · Q&A BACKUP
# Q: When and how will RPM-to-velocity calibration be completed?
Protocol designed (Section 6.4.3) — Doppler radar or high-speed camera approach
 Current state
 Ballistic solver currently uses an analytic RPM-to-velocity model (theoretical relationship)
 No empirical ground-truth mapping yet: RPM commanded vs. actual ball exit speed
 This is listed as the #2 future work item after closed-loop moving-target firing
 Planned calibration protocol (Section 6.4.3)
 Option A: Doppler radar gun — direct ball exit speed measurement per RPM setting
 Option B: High-speed camera (240+ fps) — pixel-tracking ball over known distance
 50-100 shots across RPM range (0, 500, 1000, 1500, 2000 RPM per motor)
 Fit polynomial or lookup table: commanded RPM → measured exit speed (m/s)
 Impact on current results
 Current ball accuracy (95.17 mm) is achieved WITHOUT empirical calibration
 Empirical calibration expected to reduce ballistic error further — accuracy will improve
 Safety clamps on RPM (firmware + Python) remain regardless of calibration state

### Notes:
Answer: protocol designed (Section 6.4.3), not yet executed. Doppler radar or high-speed camera approach. Current 95.17 mm accuracy is achieved without it — empirical calibration will improve results further.

<!-- Slide number: 27 -->
Q1 (Methodology): Why did you choose a four-camera setup instead of a single depth camera like the Intel RealSense?
SEDS · NU
APPENDIX · Q&A BACKUP
Redundancy, cost efficiency, and occlusion tolerance justify the 4x USB camera setup
Redundancy architecture
▸ DLT/SVD triangulation requires minimum 2 cameras, but 3+ makes the system over-determined and robust to per-camera noise (Sec 2.1, p.7; Sec 3.6)
▸ If one camera is occluded, three remain for triangulation; minimum-camera-count threshold is configurable (default 2 for ball, 3 for joints)
▸ 4-camera overlap ensures even at arena edges, most joints are visible to at least 3 cameras (Sec 3.7.5, p.26)
Accuracy & cost trade-off
▸ Two cameras: only baseline-dependent depth estimate, sensitive to calibration error
▸ Three cameras: minimum for reliable joint tracking; four adds redundancy needed for a safety-gated system (Sec 2.9.2, p.15)
▸ 4x Hikvision DS-E12: ~$120 total; 4x Intel RealSense D435: ~$800+; marginal depth gain for 7x cost

### Notes:
Answer: Four cameras provide redundancy for DLT/SVD triangulation (min 2 required, 3+ for over-determined robustness). If one is occluded, three remain. The 4-camera overlap ensures joint visibility at arena edges. Two cameras are baseline-dependent and error-sensitive; three is the minimum for joints; four adds the safety-gated redundancy. Cost: ~$120 vs ~$800+ for RealSense. (Sec 2.1, 2.9.2, 3.6, 3.7.5)

<!-- Slide number: 28 -->
Q2 (Methodology): Explain your extrinsic calibration process. Why use AprilTags on the walls rather than a standard bundle adjustment?
SEDS · NU
APPENDIX · Q&A BACKUP
AprilTag-based PnP with RANSAC provides robust extrinsic calibration without checkerboard overlap constraints
Extrinsic calibration process
▸ 24 AprilTag fiducial markers placed on arena walls at known world-frame coordinates (Sec 3.5.1, p.23)
▸ Each tag provides 4 corner points with known 3D positions; PnP algorithm recovers camera pose (R,T) by minimising reprojection error
▸ RANSAC-based outlier rejection followed by iteratively re-weighted least squares with sigma-clipping at scale=2.0
Why AprilTags over bundle adjustment
▸ Removes 8-15% of tag corner observations, primarily from tags at oblique angles (Sec 3.5.2, p.23; Sec 5.2, p.45)
▸ AprilTags do not require overlapping checkerboard views across cameras — each camera calibrates independently against the wall markers
▸ Overlay validation confirms reprojected corners within 5-10 px of detected positions across all cameras (Sec 5.2)

### Notes:
Answer: 24 AprilTag markers on walls at known coordinates provide 4 corner points each. PnP with RANSAC + iteratively re-weighted least squares recovers camera pose (R,T), removing 8-15% outlier observations. Wall-mounted tags avoid the need for overlapping checkerboard views across cameras, enabling independent per-camera calibration. (Sec 3.5.1, 3.5.2, 5.2)

<!-- Slide number: 29 -->
Q3 (Methodology): Why is robust rejection necessary for the ball but handled differently for joints?
SEDS · NU
APPENDIX · Q&A BACKUP
Ball detection is ambiguous (multiple candidates), while joint keypoints use a minimum-camera-count gate instead
Ball: reprojection-error rejection
▸ The ball detector can produce multiple candidate detections per frame (shadows, highlights, similar objects)
▸ DLT/SVD triangulation of all 2D candidates followed by reprojection-error rejection removes false matches
▸ This is necessary because even one erroneous 2D detection can pull the 3D estimate far from the true position
Joints: minimum-camera-count gate
▸ YOLO-Pose produces exactly 17 keypoints per person per camera — no candidate ambiguity
▸ Instead of reprojection rejection, joints use a minimum-camera-count threshold (default 3) for triangulation
▸ If fewer than 3 cameras see a joint, that joint is marked invalid rather than triangulated with high error (Sec 5.4, p.49)

### Notes:
Answer: Ball detection can produce multiple ambiguous candidates per frame, so reprojection-error rejection is needed to filter false matches. Joint keypoints from YOLO-Pose have no candidate ambiguity (17 keypoints per person), so a minimum-camera-count gate (default 3) is used instead — joints with insufficient views are marked invalid. (Sec 3.6, 5.4)

<!-- Slide number: 30 -->
SEDS · NU
Q4 (Results): What caused the Z-axis bias of -103 mm in the raw static ball data?
APPENDIX · Q&A BACKUP
Ceiling-mounted cameras at shallow downward angles cause systematic under-estimation of elevation
Geometric cause
▸ ez = -103 mm means triangulated ball positions are systematically placed ~103 mm below true elevation (Sec 4.4.2, p.40; Fig 5.1)
▸ All four cameras are mounted near the ceiling: at low Z (200-700 mm from floor), the shallow downward-looking ray angles are geometrically sensitive
▸ Small calibration errors in extrinsic Z positions of cameras cause triangulated points to be placed below their true elevation (Sec 5.3, p.46)
Correction approach
▸ Linear per-axis bias correction model (scale + offset per axis) reduces mean from 150.77 mm to 95.17 mm (Fig 5.1)
▸ However, this correction is fitted in-sample on the same 36-point dataset, so it may underestimate generalisation error (Sec 4.4.2, p.41; Sec 6.3)

### Notes:
Answer: The -103 mm Z-axis bias is caused by ceiling-mounted cameras: at low Z (200-700 mm), shallow downward ray angles amplify small extrinsic calibration errors, placing triangulated points below true elevation. Linear per-axis correction reduces mean from 150.77 to 95.17 mm, but is in-sample. (Sec 4.4.2, 5.3, 6.3)

<!-- Slide number: 31 -->
SEDS · NU
Q5 (Results): Why do joint errors range from 110 mm (right knee) to 164 mm (left shoulder)?
APPENDIX · Q&A BACKUP
Higher joints have weaker triangulation geometry and more frequent occlusion from the subject's own body
Error hierarchy explanation
▸ Joint error increases monotonically from right_knee (110.03 mm) to right_hip (150.38 mm) to left_shoulder (164.38 mm)
▸ Higher joints are closer to ceiling-mounted cameras and observed at increasingly oblique angles, weakening triangulation geometry (Sec 5.4, p.49; Fig 5.6)
▸ The left shoulder is the joint most likely to be occluded by the subject's head and neck
Invalid trials
▸ 19/81 invalid trials (23.5%) occur primarily because the subject's body occluded the target joint from one or more cameras
▸ This reduces the camera count below the minimum-3 threshold for accurate joint triangulation (Sec 5.4, p.49; Sec 4.2.2, p.38)
▸ This is a real operational constraint of the system, not a processing artefact

### Notes:
Answer: Joint error increases from knee to shoulder because higher joints are observed at more oblique angles from ceiling-mounted cameras, weakening triangulation geometry. The left shoulder also suffers most from self-occlusion. 19/81 trials were invalid due to insufficient camera views. (Sec 4.2.2, 5.4, Fig 5.6)

<!-- Slide number: 32 -->
SEDS · NU
Q6 (Results): Why might the corrected 95.17 mm figure underestimate the true generalization error?
APPENDIX · Q&A BACKUP
In-sample bias correction on the 36-point dataset cannot guarantee out-of-sample performance
In-sample correction risk
▸ Bias and scale parameters estimated from the same 36-point static ball dataset used for final accuracy reporting (Sec 4.4.2, p.41)
▸ Corrected figures (95.17 mm mean, 166.51 mm P95) are a near-upper bound on the dataset, not out-of-sample generalisation (Sec 5.3, p.46; Sec 6.3, p.59)
▸ With a held-out calibration set, corrected error would likely be somewhat higher because in-sample fit exploits dataset-specific noise patterns
Mitigation in thesis
▸ The thesis explicitly identifies this as a limitation (Sec 6.3) and proposes a held-out calibration grid as future work (Sec 6.4.6, p.62)
▸ Temporal precision of 3.79 mm (P95: 8.51 mm) demonstrates that dominant error source is systematic calibration bias rather than random noise
▸ The correction model specifically addresses systematic bias — exactly what it was designed for

### Notes:
Answer: The 95.17 mm figure is corrected in-sample on the same 36-point dataset, so it may exploit dataset-specific noise patterns. A held-out calibration set would likely yield a higher corrected error. The thesis explicitly acknowledges this limitation (Sec 6.3) and proposes held-out calibration as future work. Temporal precision (3.79 mm) confirms bias dominates over noise. (Sec 4.4.2, 5.3, 6.3, 6.4.6)

<!-- Slide number: 33 -->
Q7 (Safety & Ethics): Walk me through the hardware E-STOP design. How does it align with ISO 13849-1?
SEDS · NU
APPENDIX · Q&A BACKUP
NC mushroom switch implements a Category 1 stop by removing energy from the motor rail
E-STOP hardware design
▸ Layer 8: normally-closed (NC) mushroom switch on the 24V motor rail
▸ Pressing the switch opens the circuit, de-energising the motor rail — the launcher cannot move (Sec 3.14.2, p.35)
▸ Two-action release: manual clear + physical reset required; cannot be overridden in software
ISO 13849-1 alignment
▸ Implements a Category 1 stop: controlled cessation followed by removal of energy (Sec 3.14.2)
▸ NC design means broken wire = safe stop (fails to de-energised state), consistent with safety philosophy
▸ Link-loss watchdog on L9 auto-sends stop + set 0 0 0 0 on serial/UDP timeout (Sec 3.14.1, p.35)

### Notes:
Answer: The hardware E-STOP (L8) is a normally-closed mushroom switch on the 24V motor rail. Pressing it de-energises the rail, implementing an ISO 13849-1 Category 1 stop. Two-action release (manual clear + reset) prevents accidental re-enable. NC design means broken wire = safe stop. Link-loss watchdog (L9) auto-safes on timeout. (Sec 3.14.1, 3.14.2)

<!-- Slide number: 34 -->
Q8 (Safety & Ethics): Why did you stop at Stage S4? What does S5/S6 require?
SEDS · NU
APPENDIX · Q&A BACKUP
Incremental protocol: S4 validates safety gates; S5/S6 require controlled fire and full-cycle reliability
Why S4 is the stopping point
▸ The six stages are: S0 (serial connectivity), S1 (manual ESP32 commands), S2 (runtime without cameras, synthetic targets), S3 (live aim-only, no ball), S4 (safety verification: E-STOP, latch, link-loss) (Sec 3.14.3, p.35; Appendix A)
▸ S4 has a defined pass criterion: E-STOP response <100 ms and latch hold until manual clear
▸ Each stage validates a component before the next is exercised; protocol is deliberately incremental
What S5/S6 require
▸ S5: controlled fire with operator behind launcher, exclusion zone enforced, single-shot mode (Sec 3.14.3)
▸ S6: full-cycle reliability — repeated fire sequences with logging and safety regression testing
▸ If E-STOP failed to latch at S4, the system would NOT proceed to S5 — pass criterion is mandatory

### Notes:
Answer: S4 is the validated stopping point because it verifies all safety gates (E-STOP <100 ms, latch, link-loss). S5 requires controlled single-shot fire with exclusion zone discipline. S6 requires full-cycle reliability with repeated sequences and regression testing. The protocol is incremental; each stage must pass before proceeding. (Sec 3.14.3, Appendix A)

<!-- Slide number: 35 -->
SEDS · NU
Q9 (Safety & Ethics): Defend why it is ethical to develop an autonomous targeting system.
APPENDIX · Q&A BACKUP
Safety architecture, explicit target designation, and dual-use acknowledgment ensure ethical deployment
Ethical framework
▸ Section 6.5 (p.64) explicitly states: 'a system capable of autonomously tracking human body parts and directing a projectile at them has obvious dual-use potential beyond sports training'
▸ The safety architecture (operator presence, hardware E-STOP, explicit target designation, six-stage protocol) is the necessary safeguard for any deployment outside controlled research
▸ ISO 12100, ISO 13849-1, IEC 60204-1, and ISO 10218-1 alignment demonstrates responsible engineering practice
Mitigating dual-use risk
▸ Operator must explicitly designate the target joint and arm the system; no autonomous target selection
▸ Exclusion zone discipline during controlled fire (ISO 10218-1) ensures no bystander is down-range
▸ The thesis frames the system as a training tool for sports, rehabilitation, and adaptive PE — not as a weapon

### Notes:
Answer: The thesis acknowledges dual-use potential (Sec 6.5, p.64) but argues the safety architecture is the necessary safeguard: operator presence, hardware E-STOP, explicit target designation, six-stage protocol, and ISO alignment. The system requires human authorisation for every shot. It is framed as a sports/rehab training tool, not an autonomous weapon. (Sec 3.14, 6.5)

<!-- Slide number: 36 -->
Q10 (Novelty): How does your system functionally differ from a commercial Lobster Elite machine?
SEDS · NU
APPENDIX · Q&A BACKUP
Open-loop repetition vs. pose-reactive autonomous aiming with real-time 3D joint tracking
Lobster Elite: open-loop launcher
▸ Human sets angle, speed, and interval; machine repeats that programme indefinitely with no awareness of athlete's position (Sec 1.1, p.1; Table 2.1, p.14)
▸ Costs USD 200-4,000; provides repetitive training but cannot adapt to body position
▸ No perception, no joint targeting, no safety gating related to athlete position
This system: pose-reactive aiming
▸ BLM autonomously computes pitch, yaw, and wheel RPM from real-time 3D joint coordinates derived from multi-view pose estimation (Sec 1.4, p.4)
▸ Operator selects which joint to target but does not specify the trajectory
▸ Perception hardware ~USD 120; total hardware ~USD 358; qualitative departure: the launcher decides its own aim based on live observation (Sec 6.1, p.57)

### Notes:
Answer: The Lobster Elite is open-loop: a human sets angle/speed/interval and it repeats blindly. This system's BLM autonomously computes pitch/yaw/RPM from real-time 3D joint coordinates via YOLO-Pose. The operator selects the target joint but the launcher decides its own aim. Cost: ~USD 358 total vs. USD 200-4,000 for commercial launchers. (Sec 1.1, 1.4, 2.1, 6.1)

<!-- Slide number: 37 -->
Q11 (Novelty): How does your system differ from a Category B laboratory MoCap system like Vicon or OptiTrack?
SEDS · NU
APPENDIX · Q&A BACKUP
Observation-only vs. perception + actuation; 1-3 orders of magnitude lower cost; markerless operation
Vicon/OptiTrack: observation-only
▸ Reconstruct 3D positions to sub-mm accuracy but have no integrated actuation and no launcher control (Sec 1.1, p.1; Sec 2.1, p.7)
▸ Cost USD 50,000-200,000; require dedicated studios and reflective markers on subjects
▸ Inaccessible to community clubs, physiotherapy practices, and individual training (Sec 1.1)
This system: markerless perception + actuation
▸ Commodity USB cameras at ~USD 30 each, with markerless YOLO-Pose estimation, achieve targeting-level accuracy (95.17 mm ball, 143.38 mm joint) in a domestic garage
▸ Key difference is not accuracy but the combination of low-cost markerless perception WITH physical launcher actuation (Sec 2.9.3, p.16)
▸ 1-3 orders of magnitude lower cost; no markers required; works in domestic settings

### Notes:
Answer: Vicon/OptiTrack are observation-only (sub-mm accuracy, no actuation, USD 50k-200k, marker-based, lab-only). This system combines markerless YOLO-Pose perception with physical launcher actuation at 1-3 orders of magnitude lower cost (~USD 358), achieving targeting-level accuracy in a domestic garage without markers. (Sec 1.1, 2.1, 2.9.3)

<!-- Slide number: 38 -->
Q12 (Future Work): What specific technical step must be completed before the Kalman filter's predict-ahead output can be safely used for moving targets?
SEDS · NU
APPENDIX · Q&A BACKUP
Empirical RPM-to-velocity calibration is the prerequisite for computing accurate ball flight time and prediction horizons
The RPM-to-velocity calibration prerequisite
▸ The Kalman filter ships a predict-ahead output at 200-400 ms horizon in the UDP target packet (Sec 6.4.2, p.61)
▸ To aim at the predicted position at ball arrival time, you must know the flight time — which depends on muzzle speed (Sec 5.9, p.55; Sec 6.4.3, p.61)
▸ Current ballistic solver assumes a fixed 10 m/s muzzle speed, accurate only at 500-600 RPM; at 800 RPM, live-test nose shots were off-target
Calibration protocol
▸ Option A: Doppler radar gun for direct ball exit speed measurement per RPM setting (Sec 6.4.3, p.61)
▸ Option B: High-speed camera at 240+ fps for pixel-tracking over a known distance
▸ 50-100 shots across RPM range (0, 500, 1000, 1500, 2000 RPM per motor), fitting polynomial or lookup table
▸ Safety RPM clamps remain regardless of calibration state (Sec 3.14.1)

### Notes:
Answer: Empirical RPM-to-velocity calibration is required before moving-target predictive aiming. The Kalman predict-ahead output needs accurate flight time, which depends on muzzle speed. Currently a fixed 10 m/s is assumed, causing off-target shots at higher RPM. Protocol: Doppler radar or high-speed camera, 50-100 shots across RPM range. (Sec 5.9, 6.4.1, 6.4.3)
