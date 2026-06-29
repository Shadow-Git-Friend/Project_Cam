# Speaker Script Based on `thesis_defense_final.pptx`

Target duration: 17-18 minutes for slides 1-15. Keep slides 16-22 for appendix/Q&A only unless the committee asks. This script follows the original deck, but the spoken wording is intentionally more defensible where the slide text overstates the validation scope.

## Slide 1 - Title - 0:40

Good morning, respected committee members. My name is Arlen Smagulov, and today I will present my MSc thesis on pose-guided predictive ballistics with multi-camera 3D tracking.

The goal of this work is to move from a conventional fixed ball launcher toward a system that can observe an athlete, estimate body-joint positions in 3D, and use that information to aim a ball launching machine under explicit safety constraints.

## Slide 2 - Motivation - 1:00

The motivation comes from a practical gap in sports training technology.

Conventional ball launchers can repeat a shot, but they do not react to the athlete's current body position. A coach or operator sets the direction manually, and the launcher repeats that direction.

On the other side, professional motion-capture systems can track human motion very accurately, but they are expensive, marker-based, and usually require lab infrastructure.

This thesis explores a lower-cost alternative: using four commodity cameras to estimate body joints in 3D and connect that perception layer to a physical ball launching machine.

## Slide 3 - Problem Statement and Objectives - 1:25

The main research question is whether a ball launcher can use 3D body-joint tracking for safe autonomous aiming.

I structured the work around four objectives. The first objective is ball localisation. The target was mean 3D ball error below 120 mm, and the corrected result was 95.17 mm.

The second objective is joint localisation. The target was mean 3D joint error below 180 mm, and the result over the valid joint-touch trials was 143.38 mm.

The third objective is safe integration. The system was validated through staged tests from S0 to S4, including an emergency-stop response below 100 ms.

The fourth objective is practicality: commodity cameras, open-source tools, and a perception hardware cost around 200 USD. The important boundary is that moving-subject closed-loop firing is not yet fully validated and remains the next milestone.

## Slide 4 - Background and Research Gap - 1:15

This slide compares the thesis against existing options.

Optical motion capture systems such as OptiTrack or Vicon provide very high accuracy, but they are costly, marker-based, and are not directly connected to a physical launcher.

Commercial launchers are much cheaper, but they are open-loop. They launch balls to pre-set directions rather than reacting to live athlete position.

Vision-guided sports robots exist in research, but many are expensive, use fixed zones, or do not combine markerless 3D joint tracking with a safety-gated launcher.

The gap addressed here is a low-cost system that connects live multi-camera 3D perception to a physical BLM control pipeline.

## Slide 5 - Key Technical Components - 1:20

The work consists of six technical components.

First, pose-reactive aiming: the launcher target is derived from live body-joint coordinates, rather than from a manually selected angle.

Second, a validated four-camera 3D targeting pipeline, using DLT/SVD triangulation and reaching 95.17 mm corrected mean ball error.

Third, a high-speed YOLO-Pose inference loop using TensorRT FP16, supporting live operation at 15 FPS.

Fourth, a staged safety architecture: S0 to S4 tests were passed, and the emergency stop response was below 100 ms.

Fifth, a multi-modal voice command interface using offline speech recognition and UDP communication.

Sixth, reproducible datasets and logs, including a 36-point ball grid and an 81-trial joint-touch protocol.

## Slide 6 - Proposed System: Pose-to-Aim Integration - 1:10

This slide shows the full system concept.

The inherited BLM hardware provides the mechanical actuation, but the thesis contribution is the perception-to-aim integration around it.

Four cameras observe the arena. The software detects the ball and body joints, reconstructs 3D positions in a common world frame, predicts the selected target joint, and computes the pitch, yaw, and wheel-speed commands needed for the launcher.

Those commands are not sent directly to the motors. They pass through safety gates and then go to the ESP32 firmware, which runs the low-level finite-state machine.

## Slide 7 - Architecture and Pipeline - 1:20

The runtime goal is 15 FPS, which gives approximately 67 ms per frame.

The pipeline begins with four camera capture streams. It then runs YOLO-Pose and the ball detector, triangulates detections into 3D, applies EMA and Kalman filtering, computes the ballistic solution, checks safety gates, and sends commands over serial to the ESP32 firmware.

The important point is not just raw inference speed. The important point is that the software pipeline is fast enough for live aiming at the 15 FPS operating point.

When discussing timing, I treat the small millisecond values as compute-stage timings, while the full live-loop timing includes capture, processing, communication, and rendering overhead. The validated claim is live-aim operation within the 15 FPS frame budget.

## Slide 8 - Hardware Implementation - 1:20

The hardware was designed to stay practical and low-cost.

The sensing layer uses four Hikvision DS-E12 USB cameras at 1280 by 720 resolution. The cameras cost about 30 USD each, so the four-camera set is around 120 USD.

The BLM includes NEMA-23 steppers, worm-gear reducers, flywheel motors, ESCs, an ESP32 microcontroller, drivers, wiring, and a chassis. The worm-gear reducers are important because they are self-locking and improve safety during aiming.

The arena is a domestic garage with AprilTag fiducials on the walls for extrinsic calibration. The main takeaway is that the system does not need a professional motion-capture lab. It fits in a normal garage-scale environment.

## Slide 9 - Software Implementation - 1:25

The software implementation has several layers.

The perception layer uses YOLO-Pose for human joints and a custom YOLO detector for the ball. Inference uses TensorRT FP16 and processes the four camera views as a batch.

The geometry layer uses SVD-DLT triangulation to convert multi-view 2D detections into 3D world coordinates. For the ball, I also use iterative reprojection-error rejection to reduce the effect of false detections and weak camera views.

The filtering layer combines adaptive EMA and a constant-velocity Kalman model. The supervisor, written in Python, applies the ballistic solver and safety gates.

Finally, the ESP32 firmware executes the low-level control logic. The key point is that visual detections become safety-gated pitch, yaw, and RPM commands.

## Slide 10 - Calibration and Geometry - 1:15

Calibration is what makes four low-cost cameras behave as a single 3D measurement system.

Intrinsic calibration is performed using a ChArUco board, which estimates each camera's internal parameters and lens distortion. Extrinsic calibration is then performed using AprilTag fiducials mounted on the garage walls at measured 3D positions.

The result is one common world coordinate frame in millimetres. Once every camera is registered to that frame, a 2D joint detection from multiple camera views can be triangulated into a 3D joint coordinate.

This calibrated geometry is the foundation for both the accuracy experiments and the BLM aiming commands.

## Slide 11 - Methodology and Experiments - 1:25

The methodology combines localisation accuracy, dynamic tracking, safety checks, and reproducibility.

For ball localisation, I used a 36-point ground-truth grid and measured mean and P95 3D error.

For joint localisation, I used an 81-trial joint-touch protocol. The system estimated named body joints, and those estimates were compared against measured reference points.

Dynamic clips were used to inspect tracking stability under different conditions, including ordinary motion, fast motion, and no-ball cases.

Bias correction was also evaluated because the calibration produced a repeatable systematic offset. This correction reduced error, but it should be interpreted within the measured operating volume rather than as a universal correction.

Finally, the safety checklist documents the staged integration tests and logs.

## Slide 12 - Key Results - 1:30

The key results show that the main localisation and runtime targets were met within the validated scope.

For ball localisation, the corrected mean error was 95.17 mm. This is below the 120 mm target.

For joint localisation, the mean error was 143.38 mm over the valid joint-touch trials, which is below the 180 mm target. The per-joint means were approximately 110 mm for the knee, 150 mm for the hip, and 164 mm for the shoulder.

For safety, the emergency-stop latch response was below 100 ms. For runtime, the live system operated at 15 FPS.

Together, these results support static and live-aim validation. They do not yet prove full moving-target closed-loop firing, which is why that remains future work.

## Slide 13 - Limitations and Challenges - 1:15

The limitations define the boundary of the thesis.

The validated parts are perception, 3D targeting, safety gates, and static or live-aim tests. The main pending part is full closed-loop firing at a moving human subject.

There are also technical limitations. Occlusion can reduce the number of usable camera views. The bias correction is fitted from the evaluated ground-truth data, so it should not be overgeneralised outside the measured operating volume.

Finally, RPM-to-velocity calibration has not yet been completed empirically. That calibration is required to improve ballistic accuracy in future moving-target experiments.

## Slide 14 - Conclusions and Contributions - 1:15

In conclusion, this thesis provides strong partial validation of a low-cost, pose-guided BLM system.

The first contribution is pose-reactive aiming: the launcher can aim from live 3D joint estimates. The second contribution is low-cost 3D perception using four USB cameras instead of an expensive motion-capture system.

The third contribution is safety-gated integration, including staged validation and an emergency-stop response below 100 ms. The fourth contribution is a training-mode interface, including voice commands behind safety gates.

The system is not yet a finished deployment product, but it demonstrates that the core method is feasible and identifies the remaining work clearly.

## Slide 15 - Future Work, Ethics, and Standards - 1:30

The main future-work milestone is moving-target closed-loop firing with calibrated RPM-to-velocity mapping.

That requires measuring actual ball exit speed at different commanded RPM values, using either a Doppler radar gun or a high-speed camera. The result would be an empirical curve or lookup table used by the ballistic solver.

Safety and ethics are central because this is a projectile system. The thesis aligns the safety design with ISO 12100 for risk assessment, ISO 13849-1 for safety-related control, IEC 60204-1 for wiring and emergency-stop design, and ISO 10218-1 for human exclusion during operation.

The intended applications are sports training, rehabilitation, and adaptive physical education, but only under controlled operator-supervised conditions.

That concludes the main presentation. Thank you for your attention, and I welcome your questions.

## Slide 16 - Appendix Live Demo - Q&A only

If asked: This appendix slide is for a short real-hardware demo. I would show only the clearest 20 to 30 seconds and use it to demonstrate that the garage-arena system was run on physical hardware, not only simulation.

## Slide 17 - Appendix Safety Stack - Q&A only

If asked: The safety architecture is layered. Software checks include zone, confidence, stability, angle, and RPM gates. Firmware checks repeat the angle and RPM protection. Hardware protection includes arm confirmation, a normally-closed emergency stop, link-loss watchdog, and safe shutdown paths.

## Slide 18 - Appendix Latency Budget - Q&A only

If asked: The key timing point is that the optimized live loop supports 15 FPS. The committee should distinguish inference-stage timing from full loop timing. Prediction over 200 to 400 ms is used to compensate for mechanical settling and target motion.

## Slide 19 - Appendix ECE Curriculum Mapping - Q&A only

If asked: The project combines signals and systems through EMA and Kalman filtering, control systems through the supervisor-to-FSM control loop, embedded systems through the ESP32 firmware, networks through UDP and watchdog handling, and engineering ethics through safety standards and risk assessment.

## Slide 20 - RealSense Question - Q&A only

If asked why not RealSense: The four RGB cameras provide occlusion redundancy at much lower cost. Four Hikvision cameras cost about 120 USD total, while four RealSense D435 units would cost around 800 USD or more. The commodity RGB setup already achieved 95.17 mm corrected ball error indoors, so RealSense was not necessary for this thesis scope.

## Slide 21 - Kalman Filter Question - Q&A only

If asked about sudden jumps: The constant-velocity Kalman model works best for smooth motion and reduces jitter. For sudden jumps, prediction error can spike and recover over the next few frames. This is acknowledged as a limitation, and more jump-robust models such as IMM filters are future work.

## Slide 22 - RPM Calibration Question - Q&A only

If asked about RPM-to-velocity calibration: The protocol is designed but not yet executed. The plan is to measure ball exit speed across RPM settings with a Doppler radar gun or high-speed camera, then fit a polynomial or lookup table for the ballistic solver.
