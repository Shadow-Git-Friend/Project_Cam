# MSc Thesis Defense Speaker Script - 20 Minute Version

Target pace: about 125-135 words per minute. Main talk uses slides 1-15 and should take about 17-18 minutes. Slides 16-23 are appendix/Q&A only; do not present them during the timed talk unless the committee asks.

## Slide 1 - Title - 0:45

Good morning, respected committee members. My name is Arlen Smagulov, and today I will present my MSc thesis, "Pose Guided Predictive Ballistics for Body Part-Targeted Football Training."

The goal of this work is to connect real-time multi-camera perception with a physical ball launching machine, so that the system can aim at selected body joints rather than simply repeating a fixed launch angle. I will focus on the motivation, system design, calibration, validation results, safety constraints, and the remaining boundary of the work.

## Slide 2 - Motivation - 1:00

The motivation comes from a gap between two existing options. On one side, commercial ball launchers are useful but open-loop: a human sets the direction and the machine repeats. They do not react to the athlete's live position.

On the other side, high-end motion capture systems can track motion very accurately, but they are expensive, marker-based, and not realistic for a normal training environment.

My thesis asks whether low-cost cameras can bridge this gap: can we build a garage-scale system that observes the athlete, estimates body joints in 3D, and uses those coordinates to guide a launcher?

## Slide 3 - Problem Statement and Objectives - 1:20

The central question is: can a ball launcher use 3D body-joint tracking for safe autonomous aiming?

I evaluated this through four objectives. First, ball localisation: the target was below 120 mm mean 3D error, and the corrected result was 95.17 mm. Second, joint localisation: the target was below 180 mm mean 3D error, and the validated result was 143.38 mm over the valid joint trials.

Third, safe integration: the system passed staged validation from S0 to S4, including emergency-stop response below 100 ms. Fourth, practicality: the perception layer uses commodity cameras and open-source software, with perception hardware around 200 USD.

The important boundary is that RQ1 and RQ2 are met. RQ3 and RQ4 are validated for static and live-aim operation, while moving-target firing remains future work.

## Slide 4 - Background and Research Gap - 1:15

This slide positions the work against the alternatives. Optical motion capture gives very high accuracy, but it is costly, marker-based, and not connected to a ball launcher. Commercial launchers are affordable, but they are open-loop and do not know where the athlete is.

Research prototypes often solve part of the problem, for example perception or actuation, but the gap is the low-cost integration of live 3D joint perception with a safety-gated launcher.

My approach is not to claim motion-capture-level accuracy. The contribution is a combined system: low-cost cameras, 3D perception, prediction, safety gates, and physical launcher control in a domestic garage arena.

## Slide 5 - Key Technical Components - 1:00

The thesis contribution has six technical parts.

First, pose-reactive aiming: live body joints drive the ball launching machine aim. Second, four-camera targeting: the system reaches 95.17 mm corrected mean ball error. Third, real-time pose inference: TensorRT batching keeps YOLO-Pose fast enough for the 15 FPS loop.

Fourth, safety validation: the system includes staged tests and an emergency stop. Fifth, the voice interface allows training-mode control through the same safety gates. Sixth, the work includes datasets and logs: 36 ball grid points and 81 joint-touch trials.

Together, these turn a conventional launcher into a pose-guided, safety-gated training system.

## Slide 6 - Proposed System - 1:10

This slide shows the full pose-to-aim integration. The hardware platform is the ball launching machine, but the thesis contribution is the layer that makes it perception-guided.

Four cameras observe the arena. The software detects the ball and human pose, triangulates observations into a common 3D world frame, predicts the selected target joint, solves the required yaw, pitch, and wheel-speed command, then sends safety-gated commands to the ESP32 firmware.

So the system is not only computer vision and not only mechanical actuation. The contribution is the integration path from perception to prediction, safety, and physical control.

## Slide 7 - Architecture and Pipeline - 1:20

The runtime target is 15 FPS, which gives a frame budget of about 67 ms. The pipeline starts with four camera capture streams, then YOLO ball detection and YOLO-Pose inference using TensorRT FP16 batching.

The 2D detections are converted into 3D coordinates through SVD-DLT triangulation. The coordinates are smoothed and predicted using EMA and a constant-velocity Kalman filter. Then the ballistic solver computes yaw, pitch, and RPM, while the supervisor applies safety gates before sending serial commands to the ESP32 firmware.

In the representative optimized log, the total live loop P95 is about 64 ms, which fits the 67 ms frame budget. The validated claim here is sustained live-aim operation at 15 FPS. Full moving-target firing still requires RPM-to-velocity calibration.

## Slide 8 - Hardware Implementation - 1:15

The hardware is intentionally low-cost and garage-scale. The four Hikvision USB cameras cost around 120 USD total. The thesis perception hardware is around 200 USD, and the indicative BLM bill of materials is around 358 USD.

The launcher uses NEMA-23 steppers, worm-gear reducers, flywheel motors, an ESP32 controller, drivers, wiring, and a chassis. The arena uses 24 AprilTag fiducials on the walls for extrinsic calibration.

The key point is that this setup does not require a motion-capture lab, a green screen, or marker suits. It fits in a domestic garage and demonstrates the concept with commodity hardware.

## Slide 9 - Software Implementation - 1:15

The software stack has several layers. The perception layer uses YOLO-Pose for body joints and a custom YOLO ball detector. Inference runs with TensorRT FP16 in a four-camera batch.

The geometry layer uses SVD-DLT multi-view triangulation. The ball path also uses iterative reprojection-error rejection, because false detections and edge views can otherwise corrupt triangulation.

The filter layer uses adaptive EMA and a constant-velocity Kalman model. The supervisor is written in Python and applies safety gates, ballistic solving, and serial command generation. Finally, the ESP32 firmware executes the low-level state machine.

The main idea is that detections are not sent directly to hardware. They become safety-gated pitch, yaw, and RPM commands.

## Slide 10 - Calibration and Geometry - 1:15

Calibration is what makes the four cheap cameras useful as one 3D measurement system. Intrinsic calibration is done with a ChArUco board, giving reprojection errors in the 2 to 8 pixel range.

For extrinsic calibration, the arena walls contain 24 AprilTags at measured 3D positions. A robust PnP pipeline with RANSAC and sigma-clipping estimates each camera pose. The resulting extrinsic RMSE is about 3 to 7 pixels after outlier rejection.

The overlay validation checks whether known AprilTag corners reproject back into each camera frame. In all four cameras, the reprojected corners align within about 5 to 10 pixels for most visible tags. This calibrated world frame is the basis for all 3D joint coordinates.

## Slide 11 - Methodology and Experiments - 1:25

The evaluation combines accuracy, dynamic behaviour, safety, and traceability.

For ball ground truth, I used a 36-point grid and measured mean and P95 error. For joint-touch ground truth, I used 81 trials, where the system estimated named body-joint positions and compared them to measured reference positions.

Dynamic clips were used to inspect tracking stability under slow motion, fast blur, and empty-scene conditions. The slow-motion sequence stayed below large jump thresholds, the fast sequence exposed blur stress, and the no-ball control had approximately zero false positives.

Bias correction was evaluated because the arena calibration produced a repeatable systematic offset. The correction improves mean error, but I treat it honestly as an in-sample correction, not a universal calibration model.

## Slide 12 - Key Results - 1:30

The key results are the quantitative core of the thesis.

For the ball, the raw mean error was 150.77 mm, and the corrected mean error was 95.17 mm, with P95 at 166.51 mm. This meets the 120 mm mean-error target.

For joints, the mean error was 143.38 mm over the valid trials, with P95 at 198.73 mm. The per-joint means were about 110 mm for the right knee, 150 mm for the right hip, and 164 mm for the left shoulder.

For safety, the emergency-stop latch response was below 100 ms. For runtime, the system sustains 15 FPS, and the YOLO-Pose batch inference is about 6.2 ms. So within the validated static and live-aim scope, the localisation, safety, and runtime targets are supported.

## Slide 13 - Limitations and Challenges - 1:15

The limitations are important because they define what this thesis proves and what it does not yet prove.

First, fully autonomous firing at a moving human subject is future work. The system has validated static and live-aim single-shot behaviour, but not the final moving-target closed-loop regime.

Second, the bias correction is fitted from the evaluated ground-truth data, so it improves the measured operating volume but should not be claimed as a general solution outside that volume.

Third, occlusion remains a challenge. The system needs enough camera views, usually at least three for joints. Fourth, RPM-to-velocity calibration has not yet been empirically completed, so ballistic accuracy can still improve.

## Slide 14 - Conclusions and Contributions - 1:15

In conclusion, this thesis provides strong partial validation of a low-cost, pose-guided ball launching system.

The first contribution is pose-reactive aiming: live 3D joints can drive the BLM aim. The second is low-cost 3D perception using four USB cameras instead of expensive motion capture. The third is safety-gated integration, including staged validation and emergency-stop response below 100 ms. The fourth is a training-mode interface through keyboard and voice commands behind safety gates.

The system is not finished as a deployment product, but it demonstrates that the core method is feasible. The remaining disadvantages are explicit: in-sample bias fitting, occlusion limits, and missing RPM-to-velocity calibration.

## Slide 15 - Future Work, Ethics, and Standards - 1:30

The next technical milestone is moving-target closed-loop firing with calibrated RPM-to-velocity mapping. That means measuring actual ball exit speed at different RPM settings and replacing the theoretical relationship with an empirical curve or lookup table.

Safety is handled as an engineering requirement, not an afterthought. The thesis maps risks to ISO 12100 hazard analysis, ISO 13849-1 safety-related control, IEC 60204-1 wiring and emergency-stop design, and ISO 10218-1 operator-zone constraints.

The dual-use risk is also acknowledged. This is a projectile system, so operation must remain gated by an operator, an emergency stop, and an exclusion zone. The intended use is controlled sports training and rehabilitation, not unsupervised automated firing.

That concludes the main presentation. Thank you for your attention, and I welcome your questions.

## Appendix Slide 16 - Live Demo Video - Q&A only

If asked for a hardware demo: This is the real garage-arena hardware video, not a simulation. It shows the physical setup and confirms that the perception-to-hardware pipeline was tested on the real system. I will play only the clearest 20 to 30 seconds.

## Appendix Slide 17 - 10-Layer Safety Stack - Q&A only

If asked about safety depth: The key point is that unsafe actuation is blocked at several independent levels: software zone and confidence gates, angle and RPM clamps, firmware gates, arm confirmation, hardware emergency stop, link-loss watchdog, and exception shutdown.

## Appendix Slide 18 - Latency Budget - Q&A only

If asked about timing: The representative optimized log has total-loop P95 around 64 ms, which fits the 67 ms budget for 15 FPS. The 6.2 ms number refers only to YOLO-Pose batch inference, not the entire end-to-end loop.

## Appendix Slide 19 - ECE Curriculum Mapping - Q&A only

If asked how this fits ECE: The project combines signal processing, control, embedded systems, computer networks, and engineering ethics. The thesis is an integrated systems-engineering project rather than only a computer-vision benchmark.

## Appendix Slide 20 - Why Not RealSense? - Q&A only

If asked about depth cameras: Four RGB cameras give redundancy and occlusion tolerance at about 120 USD total. Four RealSense units would cost around 800 USD or more. The current system already reaches 95.17 mm corrected ball error indoors, so the cost increase was not justified for this thesis scope.

## Appendix Slide 21 - Kalman Filter and Jumps - Q&A only

If asked about the Kalman filter: The constant-velocity Kalman model works best for smooth motion and reduces jitter. Sudden jumps cause prediction error spikes and recovery over the next few frames. This limitation is acknowledged, and more jump-robust models are future work.

## Appendix Slide 22 - RPM-to-Velocity Calibration - Q&A only

If asked about RPM calibration: The protocol is designed but not yet executed. The plan is to use a Doppler radar gun or high-speed camera to measure exit velocity over multiple RPM settings, then fit a curve or lookup table for the ballistic solver.

## Appendix Slide 23 - Firmware Command Excerpt - Q&A only

If asked about firmware enforcement: The ESP32 does not blindly accept raw commands. It checks arm state, clamps angles, and gates RPM before updating target pitch, yaw, and wheel speeds.
