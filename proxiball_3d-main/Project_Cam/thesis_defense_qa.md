# Thesis Defense — Anticipated Q&A and Talking Points

**Author:** Hanush
**Programme:** MSc ECE, Nazarbayev University
**Date:** 2026-04-13
**Source of question set:** Direct intel from colleagues' bachelor defense (Mukhamediya / Shmitov / Kairat) + PhD examiner pattern.

> Two examiner archetypes were observed at the colleagues' defense:
> **(A) The non-CV ECE panel** — wants hardware, electronics, state-flow, and "where did your degree show up?". Pushed back hard with "CV is just a tool" and "the circuit is elementary."
> **(B) The PhD CV examiner (ксник)** — asked methodology: stratified buckets, testbench design, dataset composition, end-to-end signal flow.
>
> Below are the anticipated questions in each category, with crisp, defensible answers.

---

## Part A — ECE Panel (Hardware / Engineering Focus)

### A1. "Walk me through how the launcher actually shoots, from the moment a frame arrives to when the ball leaves the wheels."

**Answer (target time: 90 s, with state-flow slide visible):**

> A frame arrives at the supervisor at t=0. The capture thread already has it (threaded capture per camera, drops frames older than 200 ms). Pose inference runs through YOLO11m-Pose on TensorRT FP16 in 6.2 ms per camera; ball detection runs through YOLO in parallel in 8 ms.
>
> The four 2D keypoint sets are fed into a multi-view SVD-based DLT triangulation, producing a 3D point per joint in millimetres in the world frame. Adaptive EMA smooths jitter; a per-joint Kalman filter (constant-velocity model, 6-state) extrapolates 200–400 ms ahead because that is the latency budget of the actuation chain.
>
> The supervisor packs the current and predicted joint positions into a UDP packet and broadcasts on localhost. The launcher runtime listens, picks the requested target joint (e.g. right_shoulder), runs four safety gates: zone (target inside the GT-derived joint box), confidence (≥3 cameras, conf ≥ 0.45), stability (sliding-window std), and angle clamp (yaw ±30°, pitch [0°, 30°]).
>
> If all four pass, the supervisor solves the low-arc ballistic equation for pitch given the forward distance and target height, computes yaw from atan2 of the lateral offset in the launcher's rotated frame, applies the GT linear correction model to remove the systematic bias, and emits an ASCII command `set v h wl wr\n` over USB-serial at 921 600 baud.
>
> The ESP32's UART RX fires, the parser tokenises, the firmware drives STEP/DIR pulses to the two NEMA-23 stepper drivers via timer ISRs, and updates the BLDC ESC PWM duty cycles for the flywheel RPMs. The aim physically completes in ~80 ms depending on angle delta.
>
> When the operator types `shoot`, the same parser checks the firmware-side RPM gate — both flywheels must report ≥ 400 RPM — and only then asserts the DRV8825 enable line LOW and steps the pusher forward. The pusher pushes the ball into the pinch point of the counter-rotating wheels; the ball leaves at a speed determined by the wheel surface velocity and contact friction. The front limit switch closes, the FSM transitions back to IDLE, the DRV8825 enable goes HIGH, the coil cools.
>
> End-to-end latency, frame-to-ball-leave: about 120 ms in the perception+command path plus the mechanical settling time, which is why the Kalman predict-ahead is set to 400 ms.

### A2. "What's the state machine inside the firmware?"

```
IDLE ──reload──► RETRACTING ──back_LOW──► DISPENSING ──ball_LOW / 10 s──► IDLE
IDLE ──shoot───► SHOOTING ──RPM ≥ 400──► pusher_fwd ──front_LOW──► IDLE
```

Every transition is **gated by a sensor event**, not by a command. Commands set desired states; limit switches confirm actual states. The 10 s timeout in DISPENSING is the failure path — if no ball loads, the FSM returns to IDLE rather than hanging.

### A3. "Why a single ESP32, not the Arduino+ESP32 stack the bachelor team used?"

- Two cores: command parser on one, ISRs on the other.
- 240 MHz, 8× the Arduino UNO's clock.
- Native UART > 1 Mbaud — required for 921 600.
- On-chip BLE means a wireless backup channel is "free."
- Removing the inter-MCU TTL bridge eliminated the ~80 ms parsing tail measured in the precursor project.

### A4. "Why DRV8825 for the pusher, not A4988?"

- 2.5 A/phase vs. A4988's 2.0 A — the pusher's torque demand peaks the moment the ball contacts the spinning flywheels (highest back-EMF event).
- Integrated thermal shut-down.
- 1/32 micro-stepping (vs. 1/16) for smoother low-speed motion.
- And critically: the firmware drives the DRV8825 `nENABLE` HIGH between shots, so the pusher coil is cold in IDLE. This is the single most important thermal management detail in the project. Always-enabled would cook the motor in 30 minutes.

### A5. "Why 921 600 baud and not 115 200?"

At 115 200 the `info` response (~200 bytes) costs ~17 ms per round trip. The vision loop runs at ~15 fps (66 ms cycle). Spending ¼ of the cycle on serial I/O is wasteful. At 921 600 the same exchange costs ~2 ms — well below noise. The ESP32's UART supports it natively; no flow control needed because the supervisor paces commands and the firmware paces telemetry (and gates it on FSM state).

### A6. "Why limit switches with PULLUP and active-LOW, not PULLDOWN active-HIGH?"

Wire-break safety. With PULLUP active-LOW, a broken wire reads HIGH (unpressed), which is the safe default for a motion interlock — the FSM won't believe the pusher has reached its travel limit when in fact the wire fell off. With PULLDOWN active-HIGH, a broken wire would read LOW (pressed), which would falsely advance the FSM. PULLUP also eliminates external resistors — three components saved.

### A7. "Why USB-serial when the bachelors used BLE?"

Four reasons:
1. **Latency determinism.** USB-serial: sub-1 ms RX. BLE: connection-interval-bound, can stretch to 30 ms.
2. **Telemetry bandwidth.** BLE MTU ~244 bytes after ATT overhead × 7.5 ms minimum interval = a low ceiling. USB has none.
3. **Single failure mode.** USB is one cable. No pairing state, no bond storage, no Wi-Fi interference.
4. **Supervisor simplicity.** `pyserial` vs. `bleak` — smaller dependency, simpler error grammar.

BLE is **still compiled in** as the backup channel for the mobile app — it's a fall-back, not a deletion.

### A8. "Why worm-gear reducers, not planetary?"

**Self-locking.** A worm-gear cannot be back-driven from the output. On power loss the gimbal holds its aim with zero holding current. A planetary reducer would let the barrel droop under gravity, which with a loaded ball is a safety hazard. We pay for that property in efficiency (worm-gears are ~50 % efficient) and in ~2° backlash, which we compensate in software.

### A9. "What's your e-stop architecture?"

Normally-closed mushroom switch in series with the 24 V motor rail. Press → contact opens → motor supply cuts in < 100 ms (latch). The ESP32 stays alive on USB so the operator can `info` and log the event. Release requires (a) physical reset of the mushroom *and* (b) typed `clear` at the supervisor — two-action release per ISO 13849-1 Cat. 1.

### A10. "Show me the safety stack."

| L | Gate | Where | What it catches |
|---|---|---|---|
| 1 | Zone | Python | Joint outside arena |
| 2 | Confidence | Python | < 3 cameras or low conf |
| 3 | Stability | Python | Jittering target |
| 4 | Angle clamp ±30° | Python *and* firmware | Mechanical over-travel + ESP32 reboot prevention |
| 5 | RPM ≥ 400 | Python *and* firmware | Pusher jam |
| 6 | Arm state (`reload` first) | `blm_follow.py` | Aim before reload in shoot mode |
| 7 | Typed "yes" confirm | `live_aim_test.py` | Accidental fire |
| 8 | E-STOP physical | Hardware | Anything |
| 9 | Link loss | Python | UDP/serial timeout |
| 10 | Exception path | Python | Uncaught error |

### A11. "What standards are you compliant with?"

- ISO 12100 — machinery safety principles (hazard analysis).
- ISO 13849-1 — fail-safe stop paths (E-STOP is Cat. 1).
- IEC 60204-1 — control-circuit wiring, 24 V / 50 A fuse sizing, ground separation.
- ISO 10218-1 — robot/human exclusion zones during fire.

These aren't decorative — each one maps to a specific design decision (the E-STOP latch behaviour, the fuse rating, the operator-behind-launcher rule).

### A12. "How did you size the 24 V fuse?"

50 A breaker on the 24 V rail, sized to (a) carry both BLDC ESCs at peak (~30 A combined under acceleration) plus the stepper drivers (~5 A combined under stall), with margin per IEC 60204-1.

### A13. "How do you handle ground loops between the logic 5 V (USB) and the motor 24 V?"

Single-point star ground at the base plate. Logic GND (USB shield + ESP32 GND) ties to motor GND only at that point. Limit-switch returns are short jumpers to ESP32 GND directly, not via the motor harness.

### A14. "Can you replicate this build? What's the BOM cost?"

Yes — the chassis is reconfigurable extrusion, all electronics are off-the-shelf. The bachelor team's BOM was ~478 000 KZT for the core HW; this thesis adds nothing significant on top. The build steps are documented in Chapter [Engineering & Hardware] §7 (S0–S4 bring-up checklist).

### A15. "Where is *your* contribution if you reused the chassis?"

Six items, all electrical / embedded / supervisor-side:
1. BLE → USB-serial 921 600 migration (latency determinism).
2. Two-MCU stack → single ESP32 (eliminated the 80 ms tail).
3. Closed limit-switch FSM with 10 s dispense timeout.
4. Software angle clamp as crash-prevention interlock (discovered the ESP32 reboot at >±30°).
5. Python-side RPM gate complementing firmware-side (defence in depth).
6. Live-tuning commands (`jsset`, `jfspeedset`, `jfaccelset`) — no reflash iteration cycle.

---

## Part B — PhD CV Examiner (Methodology Focus)

### B1. "What are your stratified evaluation buckets?"

Three motion classes recorded as separate sequences:
- `walk_01` — slow translation, low joint velocity
- `jog_01` — moderate, mixed-direction
- `jump_01` — high vertical acceleration, the stress case for the constant-velocity Kalman model

449 frames per camera per sequence. Within each, distance buckets (near / mid / far) are derived from the world-frame X coordinate. The Kalman validation script reports per-bucket P50/P95 error so the CV-model breakdown on `jump_01` is visible (~neutral improvement, by design — CV models can't predict acceleration).

### B2. "Describe your testbench."

Three independent ground-truth rigs:
1. **Ball-static GT** — ball placed at 36 known AprilTag corner positions; per-trial 3D estimate vs. known position. Reports mean / median / P95 / per-axis bias / precision (std).
2. **Joint-touch GT** — operator touches their wrist (or other joint) to known AprilTag corners; same metrics.
3. **GT zone CSV** — per-joint operating bounding boxes, used at runtime as the L1 safety gate.

All three are checked into `arena_fixed/` with the corresponding extrinsics, so the metrics are reproducible bit-for-bit.

### B3. "What's your dataset composition?"

- **Ball detection (`y26s_v1_garage.pt`)** — fine-tuned YOLO on the lab arena. Inherits the bachelor team's ProxiBall augmentation (~11 000 added frames), specifically biased toward small and fast-ball recall (which jumped from 48 → 89 % and 68 → 99 % respectively).
- **Pose detection** — YOLO11m-Pose pretrained on COCO, no fine-tune, validated on lab-recorded sequences (5 mm jitter parity with MMPose at 6.2× the speed).
- **3D evaluation set** — the three GT rigs above, ~140 trials total.

### B4. "Why YOLO-Pose over MMPose? Did you measure the trade?"

Yes — full ablation in `Parallel_working/output/ablation_results/`. YOLO-Pose: 6.2 ms/image on TRT FP16 vs. MMPose 38.5 ms (RTMDet-m + RTMPose-m). 3D jitter difference < 5 mm across all three motion classes. Slight detection-rate drop on oblique camera views (94 % vs. 100 %), accepted because we have four cameras and only need three for triangulation. **Decision: speed wins**, since the perception loop budget is the binding constraint on closed-loop reaction time.

### B5. "How did you validate the Kalman filter parameters?"

Grid search over process-noise and measurement-noise on the three recorded sequences. Best params: PN=500 mm²/s⁴, MN=10 mm². Predict-ahead horizon: 200–400 ms. Per-sequence improvement vs. naïve "hold current position": walk 47 %, jog 34–39 %, jump ≈ 0 % (CV-model limitation, documented). Results in `Parallel_working/output/prediction_results/`.

### B6. "What is your end-to-end latency and where does it come from?"

| Stage | Latency |
|---|---|
| Frame capture (per camera, threaded) | masked behind inference |
| YOLO ball (TRT FP16) | 8 ms |
| YOLO-Pose (TRT FP16) | 6 ms |
| 4-cam SVD triangulation | < 2 ms |
| EMA + Kalman update + UDP pack/send | < 1 ms |
| UDP RX + safety gates + ballistic solve | < 1 ms |
| USB-serial command transmit @921 600 | < 2 ms |
| ESP32 parser + STEP/DIR pulse generation | varies (motion-bound) |
| **Total perception+command path** | **~120 ms** |

Mechanical settling adds ~80 ms depending on the angle delta. The Kalman 400 ms predict-ahead absorbs both.

### B7. "How do you handle the systematic bias in your 3D estimates?"

Measured against arena_fixed extrinsics: X +83 mm, Z −125 mm (joint-touch). Precision (std) is excellent at 4.4 mm — meaning the bias is **correctable**, not noise. Two correction modes are implemented in `launcher_runtime_from_udp.py`: `bias` (per-axis offset) and `linear` (per-axis y = ax + b regression fit from GT data). Linear is the production setting.

### B8. "Why four cameras? Could you do this with stereo?"

Stereo would work for triangulation alone but has two failure modes the four-camera array eliminates:
1. **Self-occlusion** — when the operator's body blocks one camera's view of a joint, four cameras almost always have a clean line-of-sight from at least three.
2. **Graceful degradation** — the L2 confidence gate requires ≥3 cameras. With four installed, one can fail and the system still operates.

The cost is modest: USB 3.0 hub bandwidth at 1280×720 × 15 fps × 4 cameras is well within the bus budget.

### B9. "How is the 3D world frame defined?"

Origin at one arena corner. X = arena length (6230 mm), Y = arena width (3050 mm), Z = vertical up (2950 mm). Defined by the AprilTag-wall corner positions in `Dimensions_fixed.txt`. The `arena_fixed` extrinsics are calibrated to this exact frame; mixing them with a differently-oriented set silently breaks aim. This is documented as a guardrail in `CLAUDE.md`.

### B10. "Walk me through your calibration pipeline."

1. **Intrinsics** — `calibrate_intrinsics_charuco_garage.py` — ChArUco 10×7 board, 29.7 mm squares, 22.275 mm markers. `cv2.aruco.calibrateCameraCharuco` minimises sum-of-squared reprojection residuals. RMS reproj ~0.73 px at 1280×720. Fine for our error budget.
2. **Extrinsics** — `calibrate_extrinsics_apriltag_robust.py` — 24 AprilTags on the wall at known positions. Per-camera: collect ≥4 tag-corner correspondences, solve PnP-RANSAC (EPNP seed), then iterative refinement using MAD-based outlier rejection (sigma_scale=2.5, tag_median_thresh=45 px), re-solve `SOLVEPNP_ITERATIVE` on the surviving inlier set until stable. Output: rvec/tvec per camera in meters.
3. The ChArUco→AprilTag migration was a structural decision: the arena is too large for any single ChArUco board to span, but the AprilTag-wall scales arbitrarily.

### B11. "What are the failure modes of your perception pipeline?"

- **Bright sunlight on one camera** — exposure saturates, joint detection drops below the L2 threshold, that camera is excluded. System keeps working with three.
- **Operator very close to a single camera** — viewing angle becomes oblique, YOLO-Pose detection rate drops on that view. Same mitigation.
- **Fast jump motion** — Kalman CV model's prediction accuracy degrades. Documented; would require a constant-acceleration model to fix, which adds tuning complexity for marginal gain.
- **Calibration drift** — physical bump to a camera invalidates its extrinsics. Detected at the validation overlay step (`validate_extrinsics_overlay.py`) before runtime.

### B12. "Does the launcher know about the prediction, or does it just react to current position?"

It uses the prediction. The UDP packet contains both `joints` (current EMA-smoothed) and `predicted` (Kalman-extrapolated). The launcher runtime defaults to the predicted point because the actuation chain has ~300 ms of latency that we have to lead the target by.

### B13. "How do you choose the predict-ahead horizon?"

It's tuned to match the actuation latency. We measured: serial transmit + parse + stepper motion + flywheel pinch + ball flight. The sum is in the 200–400 ms band depending on shot range and angle delta. So predict-ahead is set in that window. Validated empirically on the three motion sequences.

---

## Part C — Defence Tactics (How to Hold the Room)

### C1. Slide ordering
1. **Engineering first** — chassis, electronics, FSM, safety stack. Establish ECE credibility before the panel can dismiss CV.
2. **Calibration second** — intrinsics, extrinsics, world frame. Concrete artefacts.
3. **Perception third** — detection, triangulation, Kalman. Now the panel sees CV as a *sensor* feeding the control loop.
4. **Closed loop fourth** — ballistic solve, supervisor↔MCU, end-to-end latency.
5. **Evaluation fifth** — the GT rigs, the numbers, the per-bucket breakdown.
6. **Safety + standards last, before Q&A** — leaves the panel with the impression that this is a *responsible* engineering project.

### C2. One-slide answers to memorise
- **"What did you contribute electrically?"** → six bullets in §A15.
- **"What's your latency budget?"** → table in §B6.
- **"What's your safety stack?"** → 10-row table in §A10.
- **"Show me your state machine."** → §A2 diagram.

### C3. Pivots when challenged
- Panel says *"CV is just a tool"* → "Agreed — and the engineering question is how that tool is integrated as a sensor in a real-time control loop. Let me show you the latency budget." (jump to §B6 slide).
- Panel says *"the circuit is elementary"* → "The schematic is intentionally minimal because the design effort went into the firmware FSM and the safety interlock layering. Let me walk through the 10-layer interlock stack." (jump to §A10).
- PhD examiner asks something niche about CV → answer crisply with numbers from §B; if unsure, fall back to "I can show you the validation script in [exact file path]" — concreteness defeats vagueness.

### C4. Things to *not* say
- "I just used YOLO." (you tuned it, exported it to TRT, evaluated it on three GT rigs)
- "The CV is the main contribution." (the engineering integration is the contribution; CV is a component)
- "We didn't measure that." (always have a number, even if it's "out of scope, see §10 future work")

---

*End of Q&A pack. Cross-reference: [thesis_engineering_chapter.md](thesis_engineering_chapter.md), [new_complete.md](new_complete.md).*
