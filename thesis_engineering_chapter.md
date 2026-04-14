# Engineering and Hardware Design of the Ball-Launching System

**Author:** Hanush
**Programme:** MSc Electrical and Computer Engineering, Nazarbayev University
**Supervisor:** Prof. Sultangali Arzykulov
**Draft date:** 2026-04-13

> This chapter foregrounds the **engineering construction** of the ball-launching machine (BLM) — the mechanical chassis, the power and signal electronics, the embedded firmware, the communication stack, the safety interlocks, and the integration procedure — and only secondarily references the computer-vision front-end (which is treated fully in Chapter X). The objective is to make transparent the ECE design decisions that the vision pipeline rests on: why each motor, driver, connector, protocol, and firmware state was chosen, and how the pieces compose into a hard-real-time closed loop. The chapter is structured so that a reader from any ECE sub-discipline (power, control, embedded, communications, mechatronics) can locate their own competency in the system.

---

## 1. Scope and Engineering Thesis

### 1.1 Statement
The BLM is an electro-mechanical actuator driven by a real-time embedded controller, receiving high-level aim commands from a vision-based supervisor over a serial link, and producing a ballistic projectile whose trajectory must converge on a moving 3D target point. The engineering contribution of this thesis is **the construction, characterisation, and real-time safety-gated operation of that actuator chain**, not the detection of the person — detection is a *sensor* in the control loop, and the loop itself is what is being engineered.

### 1.2 Contributions specific to this thesis
Relative to the bachelor-team baseline (Mukhamediya–Shmitov–Kairat, Spring 2026) and to the omnidirectional MSc thesis of Yessimkhan Orynbay (2025), this work contributes:

1. **Replacement of BLE (Nordic UART GATT) with direct USB-serial at 921 600 baud** for the primary supervisor-to-MCU command channel, eliminating the ~80 ms Arduino-parsing tail measured in CHG-3 and removing the stacked BLE buffer hazard.
2. **Migration from Arduino UNO + ESP32 (two-MCU stack) to a single ESP32** running the entire launcher state machine (`control_12_full.ino`), removing the inter-MCU serial bridge.
3. **Feeder reload FSM with closed limit-switch verification** (front, back, ball limits, all `INPUT_PULLUP`-active-LOW) and a 10 s dispense timeout, replacing open-loop feeder timing.
4. **Software angle clamp in the supervisor** (±30° yaw and pitch, applied *before* the command reaches the MCU) as a hard safety pre-check that also documents an empirically discovered firmware crash at travel extremes.
5. **Python-side RPM gate verification** via real-time telemetry parsing, complementing the firmware-side RPM gate so the loop is safe even if one interlock is bypassed during bring-up.
6. **Live tuning commands in firmware** (`jsset`, `jfspeedset`, `jfaccelset`) that allow stepper parameters to be reconfigured without reflashing, shortening the experimental iteration cycle from minutes to seconds.

The mechanical chassis, 2-DOF gimbal topology, and counter-rotating flywheel pair are inherited from the shared lab platform; the engineering originality of *this* thesis is in the electronics, embedded firmware, communication stack, and safety architecture described below.

---

## 2. Mechanical Architecture

### 2.1 Chassis and structure
- **Profile:** 30 × 30 mm aluminium 6061 extrusion, bolted corner brackets.
- **Rationale:** aluminium was chosen over the wood prototype of the MSc precursor because (a) recoil from the pusher-solenoid stroke and the reaction torque of the flywheels at > 800 RPM set up a vibration spectrum that wood damps poorly, (b) 6061 holds machined holes to tolerance across thermal cycles, (c) the extrusion system makes the chassis re-configurable during iterative bring-up.
- **Static load path:** flywheel reaction torque → motor mount plate → vertical upright → base → floor. The pitch-axis worm-gear reducer sits on the base plate; the yaw-axis reducer sits above the pitch bracket. This ordering keeps the largest inertia (the flywheel pair) on the fastest stepper (pitch) and the slowest stepper (yaw) carrying less.
- **Validation:** ten consecutive impact tests (repeated fire events) showed no measurable fastener loosening; a 3-axis accelerometer logged the peak chassis vibration during firing at the flywheel fundamental and its second harmonic, confirming no structural resonance in the 0–500 Hz band.

### 2.2 Two-degree-of-freedom gimbal
- **Actuators:** two NEMA-23 stepper motors.
- **Reducers:** 1 : 50 worm-gear reducers on both axes.
- **Key engineering property:** worm-gears are **self-locking** — external torque at the output cannot back-drive the input. This property means that on power loss the gimbal holds its aim without any electrical holding current, which is a significant safety property (a ball in the feeder cannot flop out at an unsafe angle because the barrel cannot drop).
- **Backlash:** approximately 2° of mechanical play is present in the horizontal reducer, consistent with the MSc precursor's finding. Compensation is performed in software: the supervisor tracks the last-commanded direction per axis and adds a one-sided dead-band offset on direction reversal. This moves the compensation out of the firmware (where it would compete with the stepper step-generation ISR) into the supervisor (where double-precision arithmetic and target history are cheap).
- **Working range:** pitch [0°, +30°], yaw [−30°, +30°]. These limits are enforced both in the Python supervisor (primary) and the firmware command parser (secondary). Empirically, `set` commands with magnitudes > 30° cause the ESP32 to reboot (likely a stack-protection fault in the stepper library under extreme step counts); the supervisor-side clamp therefore also functions as a crash-prevention interlock.

### 2.3 Flywheel pair (propulsion)
- **Topology:** two counter-rotating wheels with the ball squeezed between them at the pinch point.
- **Aerodynamics:** differential wheel RPMs produce a net spin vector on the ball, yielding a Magnus-effect lateral force in flight. At the Reynolds numbers of interest (Re ≈ 7 × 10⁴ to 5 × 10⁵ for a size-5 football at 5–30 m/s), drag and lift coefficients vary with Re and spin-parameter S; these are captured in the supervisor's ballistic model (see §5).
- **Safety-limited exit regime:** controlled fire has been qualified at 500–800 RPM (qualification report, 2026-04-09). Higher RPMs remain untuned, and the ball-exit speed curve vs. RPM is a pending TLR item.

### 2.4 Feeder and pusher
- **Driver:** DRV8825 stepper driver for the pusher axis.
- **DRV8825 choice rationale:** compared with A4988 (the typical bachelor-project default), the DRV8825 supplies up to 2.5 A/phase, supports 1/32 micro-stepping, and has integrated thermal shut-down and current-limit potentiometer — all necessary for the pusher because (a) the pusher's peak torque demand coincides with the moment the ball contacts the flywheels, which is also the highest back-EMF event in the system, and (b) the coil must be held energised only while motion is commanded to avoid cooking the motor between shots.
- **Enable-pin thermal management:** the firmware drives the DRV8825 `nENABLE` line **HIGH (disabled) while the FSM is IDLE** and **LOW (enabled) only during RETRACTING, DISPENSING, or SHOOTING**. This keeps the pusher coil cold between shots, extends motor life, and drops the chassis thermal load by an order of magnitude compared with an always-enabled configuration. It is the single most important firmware detail on the actuation side.
- **Limit switches:** three mechanical limit switches — **front** (ball released), **back** (pusher retracted home), **ball** (magazine has a ball in position). All three are wired with the ESP32's internal `INPUT_PULLUP` and triggered on LOW (closed-contact-to-GND). This polarity was chosen over PULLDOWN-HIGH (the control_11 configuration) because (a) a broken wire fails to an "unpressed" (HIGH) state, which is the safe default for motion interlocks, (b) `INPUT_PULLUP` removes the need for external resistors, reducing the wiring harness by three discrete components.
- **Servo:** a hobby servo on `js` controls the dispense flap; its angle is tunable at runtime via `jsset<v>` without reflashing.

### 2.5 Power architecture
- **Logic rail:** 5 V USB (from the supervisor PC) powers the ESP32. USB also carries the command/telemetry serial stream — a single cable, single failure mode.
- **Motor rail:** a 24 V, fused (50 A, consistent with IEC 60204-1 sizing for this class of equipment) supply feeds the flywheel ESCs and the stepper drivers through separate breakers.
- **Grounding:** logic ground (USB GND) is tied to motor ground at a single star point on the base plate to prevent ground loops. The ESP32's input pins are not tied to the motor-rail ground directly; limit-switch returns are via a short harness to the ESP32's own GND.
- **E-STOP:** a normally-closed mushroom switch on the 24 V rail latches the motor supply off in < 100 ms. The ESP32 remains powered via USB so that the supervisor can read `info` and log the event post-latch. Release requires a manual `clear` command at the supervisor *and* physical reset of the E-STOP, enforcing the ISO 13849-1 "two-action" release.

---

## 3. Electronics

### 3.1 Control board: ESP32
The previous project generation used a two-MCU stack (ESP32 as a BLE front-end, Arduino UNO as the motor controller, cross-connected by a TTL serial link). That architecture was justified when the ESP32's real-time story was unclear; it is no longer justified. This thesis consolidates to a single ESP32 running **both** the BLE/serial command parser and the stepper step-pulse generation on the same MCU.

**Why ESP32, not Arduino UNO:**
- Two physical cores — one can handle the command parser and telemetry, the other the ISRs.
- 240 MHz clock, sufficient for the pusher's 1/32 micro-step pulse cadence with head-room.
- Hardware UART configurable up to > 1 Mbaud (enables the 921 600 baud choice).
- Native USB-UART bridge on the dev-kit board (CP2102 or CH340), removing the need for an FTDI adapter.
- BLE radio on-chip (used as backup channel, name `RoboLauncher`) — means the USB→BLE migration if ever needed is a single `#define`.

**Why not Arduino UNO:**
- 16 MHz, 8-bit, single-core: cannot simultaneously service the stepper ISR, a limit-switch debounce ISR, the BLDC ESC pulse generator, and a 921 600 baud UART RX without dropping bytes.
- No native serial above 115 200 baud without tight timing.

### 3.2 Motor drivers
- **Flywheels:** 3-phase BLDC motors driven by commodity ESCs. The supervisor does not see the ESC protocol; it sees only the `wl`, `wr` fields of the `set` command, which the firmware translates to PWM duty cycles. This abstraction means the flywheel driver could be swapped (ODrive, VESC, hobby ESC) without changing the supervisor.
- **Gimbal steppers:** NEMA-23 drivers on the standard STEP/DIR/ENABLE interface. Micro-stepping ratio matches the worm-gear reduction so that a single logical "step" at the supervisor maps to a predictable angular delta at the output.
- **Pusher:** DRV8825 as discussed in §2.4, with enable-pin thermal management.

### 3.3 Signal conditioning and isolation
- **Limit switches:** debounced in firmware (software debounce, 5 ms minimum-stable window) rather than with RC hardware, to avoid adding components and to allow the debounce window to be tuned during bring-up.
- **Serial:** USB is galvanically isolated at the host PC end by the laptop's USB hub. Motor-side signals (STEP/DIR) use short, twisted pairs to the driver screw terminals; long-run analog signals are not used.
- **Telemetry suppression:** during pusher motion (`STATE != IDLE`), the firmware **suppresses the `L:xxx R:xxx` RPM telemetry** because the current draw on the USB rail during stepping briefly couples into the logic ground and corrupts the UART. Suppression is conditional on the FSM state, not a blind throttle, so telemetry resumes the moment motion ends.

### 3.4 Encoder integration (optional, inherited)
The MSc platform uses AS5047P 14-bit absolute magnetic encoders for closed-loop gimbal feedback. For this thesis, the encoder readings are *available* but the supervisor's control law is **open-loop on the stepper count** with vision-side correction (because the camera sees where the ball went and re-aims on the next shot, which is already a closed loop at a higher level). This is an explicit design decision: adding a fast inner encoder loop does not improve vision-converged accuracy but does add wiring, ISRs, and failure modes.

---

## 4. Firmware: `control_12_full.ino`

### 4.1 Architecture
The firmware is a cooperative state machine running on ESP32 core 1, with stepper step-pulse generation in a timer ISR, and UART command parsing in the main `loop()`. There is no operating system — no FreeRTOS tasks are spawned by the sketch — because the real-time guarantees required (pulse-jitter < 50 µs) are easier to meet in a bare-loop design with known critical sections.

### 4.2 State machine
```
IDLE ──reload──► RETRACTING ──back_LOW──► DISPENSING ──ball_LOW / 10 s──► IDLE
IDLE ──shoot───► SHOOTING (RPM ≥ 400) ──pusher_fwd──► front_LOW──► IDLE
```

Each arrow is a transition guarded by a **sensor event** (a limit switch reading) or a **timer** (the 10 s dispense fallback). No transition is triggered solely by a command; commands set *desired* states, the sensors confirm actual states. This discipline is what allows the system to recover from a jammed ball: the FSM stays in DISPENSING until the ball-limit switch confirms a ball is present, and if the timer expires it returns to IDLE rather than hanging.

### 4.3 Command interface
The parser uses `cmd.toLowerCase()` and matches exact tokens. The command set is:

| Category | Commands |
|---|---|
| Aim/fire | `set v h wl wr`, `shoot`, `reload`, `stop`, `center`, `setzero` |
| Manual jog | `jv<n>`, `jh<n>`, `jf<n>`, `js<0-180>` |
| Live tuning | `jsset<v>`, `jfspeedset<v>`, `jfaccelset<v>` |
| Diagnostic | `info` |

The `info` response is the single-source-of-truth diagnostic: angles, RPMs, feeder state, all three limit-switch states, and the live-tuning values. It is what the operator reads during bring-up and what the supervisor reads as a health-check before arming.

### 4.4 Interlocks in firmware
- **RPM gate**: `shoot` is *rejected inside the firmware* if either flywheel is below 400 RPM. This is a second line of defence behind the supervisor-side RPM check. If the operator issues `shoot` from a raw terminal with cold flywheels, the firmware refuses.
- **Angle clamp**: while the supervisor is the authoritative clamp, the firmware additionally clips to ±30° to survive supervisor bugs.
- **Pusher enable**: `nENABLE` is asserted LOW only in the three non-IDLE states; otherwise HIGH.

### 4.5 Telemetry format
`L:<rpm_L> R:<rpm_R>` lines are streamed only in IDLE. The supervisor's `read_rpm_from_lines` parses the most recent value seen and uses it for the RPM gate.

---

## 5. Supervisor ↔ MCU Communication

### 5.1 Physical layer
USB 2.0 Full-Speed, CP2102/CH340 UART bridge, TTL-level logic, 5 V bus power.

### 5.2 Link layer
- **Baud:** **921 600**.
- **Rationale:** at this rate a full telemetry-plus-command exchange fits inside a 1 ms window, which matters because the supervisor's perception loop runs at 15 fps (66 ms cycle) and we want serial round-trip to be negligible compared with the vision pipeline. At the previous 115 200 baud the `info` response (≈ 200 bytes) consumed ~17 ms, a measurable fraction of the perception cycle; at 921 600 it consumes ~2 ms.
- **Framing:** newline-terminated ASCII. Chosen over a binary framing because (a) the supervisor is in Python, which parses text line-by-line idiomatically, (b) the command set is small enough that binary compaction saves nothing meaningful at 921 600 baud, (c) human-readable on a serial terminal during bring-up is a large debuggability win.
- **Flow control:** none. The command cadence is supervisor-paced (deadband + rate-limit) and the telemetry cadence is firmware-paced and state-gated, so there is no scenario in which either side overruns the other's UART FIFO.

### 5.3 Supervisor-side protocol stack
1. **Open:** `serial.Serial(port, 921600, timeout=0.1)`. Then `time.sleep(2)` to absorb the ESP32's DTR-induced reboot, then `reset_input_buffer()` to discard boot-ROM noise.
2. **Filter (every RX line) — mandatory across all five BLM scripts:**
   - Drop ESP32 boot-ROM preamble: lines starting with `ets `, `rst:`, `configsip:`, `clk_drv:`, `mode:`, `load:`, `entry`.
   - Drop baud-transition garbage: lines ≥ 20 chars whose character-diversity is ≤ 2 unique characters (e.g. `MMMMMMM…`). This pattern arises when the host opens the port at a different baud than the firmware booted with.
   - In interactive contexts, drop telemetry lines (`L:…R:…`).
   - Deduplicate consecutive identical lines.
3. **Read:** always from a **background thread** with a bounded queue. Never call `ser.readline()` from the main thread — the UART can stall and block the aim loop.
4. **Close (always):** send `stop` → `center` → close port, even on `KeyboardInterrupt`.

### 5.4 Why not BLE for the primary link?
The precursor bachelor project used BLE (Nordic UART Service) as the primary command link after an earlier migration from Bluetooth SPP (CHG-3). BLE solved the SPP buffering problem and achieved ≥ 95 % packet delivery at ~20 ms latency. This thesis still went to **USB-serial as primary** because:

1. **Latency determinism.** BLE connection interval is negotiated; a slow peer can extend it to 30 ms. USB-serial's interrupt-driven UART on ESP32 delivers consistent sub-1 ms RX latency.
2. **Telemetry bandwidth.** BLE MTU (~244 bytes after ATT overhead) and the 7.5 ms minimum connection interval put a ceiling on telemetry rate that is awkward for the `info` string. USB-serial has no such ceiling.
3. **Single failure mode.** USB is one cable — power, ground, D+, D−. No pairing state machine, no bond-storage corruption, no radio interference from the lab Wi-Fi.
4. **Supervisor simplicity.** `pyserial` is stdlib-adjacent; `bleak` is a larger dependency with a different failure grammar.

BLE remains compiled-in as a backup channel (advertising name `RoboLauncher`) for the mobile-app use case, which is not part of this thesis.

---

## 6. Safety Architecture

The safety design follows a defence-in-depth pattern. No single interlock is trusted alone; a command that would cause unsafe motion must defeat **all** of the following gates to reach the actuator.

### 6.1 Layered interlocks (supervisor → firmware)

| Layer | Interlock | Enforced by | Failure behaviour |
|---|---|---|---|
| L1 | **Zone gate** — target 3D position inside GT-derived joint zone | Python supervisor | Aim rejected, `LOW_CONFIDENCE` logged |
| L2 | **Confidence gate** — ≥ 3 cameras, confidence ≥ 0.45 | Python supervisor | Aim rejected |
| L3 | **Stability gate** — sliding-window std ≤ threshold | Python supervisor | Aim rejected |
| L4 | **Angle clamp** — pitch ∈ [0°, 30°], yaw ∈ [−30°, 30°] | Python supervisor *and* firmware (double) | Command clipped before transmit; firmware clips again |
| L5 | **RPM gate** — both flywheels ≥ 400 RPM before `shoot` | Python supervisor *and* firmware (double) | `shoot` rejected |
| L6 | **Arm state** — operator must type `reload` before first aim in follow mode | Python supervisor (`blm_follow.py`) | Aim suppressed until armed |
| L7 | **Confirmation** — typed "yes" required before fire in test mode | Python supervisor (`live_aim_test.py`) | Fire blocked |
| L8 | **E-STOP** — N/C switch cuts 24 V rail, latched | Hardware | All motion halts in < 100 ms |
| L9 | **Link loss** — UDP timeout or serial disconnect | Python supervisor | Auto `stop` + `set 0 0 0 0` |
| L10 | **Exception path** — any uncaught Python exception | Python supervisor | Same as link-loss behaviour |

### 6.2 Standards compliance (reference frame)
- **ISO 12100** — general machinery safety principles, applied to the hazard analysis that motivates L1–L10.
- **ISO 13849-1** — fail-safe stop paths: the E-STOP (L8) implements a Category 1 stop (energy removal via contactor).
- **IEC 60204-1** — control-circuit wiring, 24 V / 50 A fuse sizing, separation of logic and power grounds.
- **ISO 10218-1** — exclusion zone discipline during controlled fire (operator behind the launcher, no person downrange unless the operator is the target).

### 6.3 Known hazards (documented, not fixed)
1. Commands beyond ±30° → ESP32 reboot. Mitigation: supervisor-side clamp (L4).
2. Horizontal stepper backlash ≈ 2° → small-angle oscillations are absorbed before motion starts. Mitigation: software backlash compensation.
3. Ball exit velocity uncalibrated above 800 RPM → ballistic solver assumes fixed 10 m/s, accuracy degrades at high RPM. Mitigation: pending TLR work (radar-gun curve RPM → m/s).

---

## 7. System Integration Procedure

Integration followed a strict, sequenced bring-up to ensure that each interlock was verified **before** the next failure mode could be excited. All stages passed on 2026-04-09.

### 7.1 Stage S0 — Serial connectivity
- Tool: `blm_interactive.py`.
- Check: open `/dev/ttyUSB0` at 921 600 baud; verify `dialout` group membership; send `info`, parse response.
- Pass criterion: `info` returns a well-formed response within 500 ms.

### 7.2 Stage S1 — Manual command verification
- Tool: `blm_interactive.py`.
- Checks: `set 10 10 0 0`, `center`, `jv500`, `jh500`, `setzero`. Each command is observed to produce the correct physical motion and the `info` response reflects the new state.
- Pass criterion: all five commands produce the expected physical outcome with no firmware resets.

### 7.3 Stage S2 — Live aim-only
- Tools: `run_live_blm.sh` (Terminal 1: viewer + Kalman + UDP broadcast) + `live_aim_test.py --no-shoot-enabled` (Terminal 2: aim consumer).
- Check: aim the launcher at the operator's chosen joint; verify visual tracking in the viewer and physical gimbal pointing.
- Pass criterion: yaw/pitch follow the joint with < 1° steady-state error at stand-still, < 3° during slow walk.

### 7.4 Stage S3 — RPM gate verification
- Tool: `blm_interactive.py`.
- Check: command flywheels at 300 RPM, issue `shoot`, verify firmware rejects it. Then command 800 RPM and observe (do not fire).
- Pass criterion: `shoot` rejected below 400 RPM, accepted above.

### 7.5 Stage S4 — Controlled fire
- Tool: `live_aim_test.py --shoot-enabled --wheel-rpm 500`.
- Check: low pitch (15°), moderate RPM (500), single shot with operator behind the launcher. Escalate stepwise to 600, 800 RPM.
- Pass criterion: ball trajectory reaches the intended zone; no mechanical anomalies.

### 7.6 Integrated live test
- Tool: `blm_follow.py --shoot-enabled`.
- Check: full reload → aim → shoot cycle on multiple joints (left_shoulder, right_knee, nose), with typed-command target hot-swap.
- Pass criterion: closed-loop operation with no safety-gate false negatives.

All six stages are replayable and must be re-run after any firmware or hardware change.

---

## 8. ECE Curriculum Mapping

This section exists to answer the ECE-panel question *"where does each course in the Nazarbayev University ECE curriculum appear in this work?"*, which is the question that drove the bachelor-team defense feedback. Each bullet is a specific, testable engineering artefact traceable to coursework.

| ECE subject | Artefact in this thesis |
|---|---|
| **Embedded Systems** | `control_12_full.ino` cooperative FSM on ESP32, timer-ISR stepper pulse generator, UART RX parser on `loop()`. |
| **Digital Design / Logic** | Limit-switch polarity design (PULLUP-LOW fail-safe), DRV8825 enable logic, E-STOP latch behaviour. |
| **Control Systems** | Two-axis stepper position control with software backlash compensation; RPM set-point with firmware-side gate; Kalman-filtered supervisor acting as a high-level outer loop (covered in Ch. X). |
| **Signals & Systems** | Telemetry suppression under state-dependent coupling, serial line filtering (boot-noise band-stop, baud-garbage discrimination by character-diversity metric). |
| **Communication Systems** | USB-serial link budget, framing choice, BLE-vs-serial latency trade study (§5.4), packet-delivery reasoning. |
| **Power Electronics** | 24 V rail sizing per IEC 60204-1, ESC selection for BLDC flywheels, DRV8825 current-limit setting, ground-loop star-point topology. |
| **Mechatronics / Robotics** | Worm-gear self-locking rationale, NEMA-23 sizing vs. gimbal inertia, pusher feeder FSM. |
| **Computer Vision** (supporting role, not primary) | Multi-camera triangulation as the supervisor's position sensor; treated as a *measurement system* feeding the control loop. |
| **Machine Learning** (supporting role) | YOLO/YOLO-Pose as a detection front-end; evaluated with held-out stratified buckets (walk/jog/jump sequences at different distances). |
| **Engineering Ethics & Safety** | Defence-in-depth interlock design, E-STOP compliance with ISO 13849-1 Cat. 1, explicit hazard log. |

---

## 9. Component Selection Rationale (Summary Table)

| Component | Chosen part | Rejected alternative | Decisive reason |
|---|---|---|---|
| MCU | ESP32 | Arduino UNO, STM32 Nucleo | Dual-core + on-chip BLE backup + > 1 Mbaud UART |
| Pusher driver | DRV8825 | A4988, TMC2208 | 2.5 A/phase, integrated thermal shut-down, current-limit pot |
| Flywheel motor | 3-phase BLDC + ESC | PMDC, AC washing-machine | Efficient, smooth, accurate speed control |
| Gimbal actuator | NEMA-23 + 1:50 worm | Servo, NEMA-17 + planetary | Torque, resolution, self-locking on power loss |
| Chassis | Al 6061 30×30 extrusion | Wood, welded steel | Stiffness + reconfigurability + low mass |
| Supervisor link | USB-serial @ 921 600 | BLE (Nordic UART) | Latency determinism, telemetry bandwidth, single failure mode |
| Limit-switch bias | INPUT_PULLUP, active LOW | PULLDOWN, active HIGH | Wire-break fails to "unpressed" (safe default) |
| Telemetry format | Newline ASCII | Binary frames with CRC | Human-debuggable, small command set, 921 600 baud is plenty |
| Camera count | 4 | 2 (stereo), 3 | Self-occlusion robustness; 4th camera allows one to drop and still triangulate |
| Calibration method | AprilTag 24-tag wall + robust PnP | ChArUco board | Arena too large for a single board; AprilTag wall reduces baseline error (CHG-2) |

---

## 10. Open Items and Next Steps

The following are deliberately out of scope for this thesis's engineering chapter and are logged as future work:

1. **Ball-exit speed calibration.** A Doppler radar (or high-speed camera + tracked fiducial) run to build the RPM → m/s lookup, closing TLR-5. Estimated effort: 1 day of data collection + half-day of fitting.
2. **Encoder-closed inner loop.** Integrate AS5047P feedback into the firmware for a ±0.2° aim accuracy band, replacing the current open-loop stepper + vision-outer-loop scheme. Estimated effort: 1 week (firmware), 2 days (validation).
3. **Adaptive difficulty (TLR-8 of the bachelor project).** De-scoped from the precursor work and not re-introduced here; left as a future application-layer feature.

---

*End of Chapter. Cross-references to the vision pipeline (multi-view triangulation, Kalman prediction, GT correction) are in Chapter X (Perception) and to end-to-end performance metrics in Chapter Y (Evaluation).*
