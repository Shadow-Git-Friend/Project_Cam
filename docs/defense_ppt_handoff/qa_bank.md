# Defense Q&A Bank

All answers are grounded in [`thesis_defense_qa.md`](../thesis_archive/root_thesis/thesis_defense_qa.md), [`thesis_engineering_chapter.md`](../thesis_archive/root_thesis/thesis_engineering_chapter.md), [`new_complete.md`](../archive/legacy_notes/new_complete.md), [`CLAUDE.md`](../../CLAUDE.md), and the repo's GT evaluation results. Each answer is ≤ 120 words, structured as **Answer → Evidence → (Optional pivot)**. Mark any fact not directly traceable to those sources as `[VERIFY]` before rehearsing.

---

## 1. Problem & Motivation (3)

**Q1.1 — Why not use off-the-shelf motion capture (OptiTrack, Vicon)?**
Cost and markers. OptiTrack/Vicon rigs run USD 50k–200k and require reflective markers attached to the athlete. For sports training and rehabilitation — our target markets — neither the budget nor the markered setup is acceptable. The MSc contribution is a USD ~200 perception BOM using four commodity USB cameras, markerless, with sub-200 mm joint accuracy and a closed control loop. We do not claim MoCap-grade precision; we claim *enough* precision for joint-aware ball delivery at one to two orders of magnitude lower cost.

**Q1.2 — Why sports and rehabilitation, specifically?**
Both domains require adaptive, repeatable delivery to a specific body part. A coach cannot personally throw every ball to a trainee's weak side; a physiotherapist cannot reset a patient's trajectory on every rep. Open-loop launchers already exist for both, but none of them react to the athlete. Closing that loop — cheaply — is the thesis contribution. The perception layer is deliberately modular so downstream coaches or therapists can swap targeting strategies without firmware changes.

**Q1.3 — What counts as success for this thesis?**
Four measurable objectives (see slide 3). O1: sub-200 mm mean joint error (achieved: 179 mm). O2: ≤400 ms end-to-end latency, ≥15 FPS (achieved: ~120 ms perception+command, 15 FPS sustained). O3: perception BOM under USD 500 (achieved: ~USD 200). O4: ECE-grade safety via multi-layer interlocks and ISO-aligned stop paths (achieved: 10-layer safety stack, S0–S4 bring-up PASSED). Each objective has recorded numerical evidence in the ablation/GT directories. The thesis succeeds if and only if all four are demonstrably met; all four are.

---

## 2. Methodology (5)

**Q2.1 — Why four cameras? Why not two, or eight?**
Two is the geometric minimum for triangulation but drops to single-camera fallback the instant a joint is occluded. Eight quadruples calibration cost and cabling without proportional accuracy gain — the marginal new view geometry is already covered. Four gives redundancy (any single camera can fail and triangulation still runs on three), frustum coverage of a 4×5 m arena from all four compass directions, and a BOM that stays under USD 200. Ablation supports this: 3-cam triangulation is within a few millimetres of 4-cam on joint-touch data.

**Q2.2 — Why YOLO-Pose over MMPose?**
MMPose (RTMDet-m + RTMPose-m) is slightly more accurate but runs at 38.5 ms/image on an RTX 2080 Ti. YOLO11m-Pose with TensorRT FP16 runs at 6.2 ms/image — 6.2× faster. Our EMA ablation shows the 3D jitter delta between the two is under 5 mm, well inside the calibration-limited error budget of 179 mm. For a 15 FPS real-time system, the speed trade-off dominates. MMPose remains available as `--pose-backend mmpose` for offline evaluation — we are not throwing away optionality.

**Q2.3 — Why a constant-velocity Kalman filter, not constant-acceleration?**
CV is simpler (6-state vs 9-state), tuned successfully for walk and jog, and the failure mode is well-understood: it is ~neutral on jump motion. Going to CA would complicate tuning, increase process-noise sensitivity, and the measured improvement on non-jump motion is already 34–47%. A CA model is explicit future work (slide 15). The engineering trade-off was: ship a reliable CV filter now, pick up CA when we have regression fixtures for jump motion. This is documented in `CLAUDE.md` Kalman section.

**Q2.4 — Why SVD-DLT triangulation and not bundle adjustment?**
Bundle adjustment is iterative and non-linear; SVD-DLT is closed-form and runs in under 2 ms for four views. Our calibration is static (4 fixed cameras, world frame frozen in `arena_fixed`), so the non-linearity of BA buys little: the cameras' extrinsics do not drift frame-to-frame. SVD-DLT fits the 15 FPS real-time budget; BA would force us off single-shot triangulation into a sliding window that costs latency without meaningful accuracy gain. Robustness comes from `robust_triangulate_ball()` — iterative per-camera reprojection-error rejection — not from BA.

**Q2.5 — Why USB serial at 921 600 baud instead of BLE?**
BLE's Nordic UART service adds ~80 ms of parsing tail and has unpredictable ACK latency. A wired USB serial link at 921 600 baud completes a 200-byte `set v h wl wr` round-trip in under 2 ms, deterministic, and cannot desync from Wi-Fi congestion. BLE is retained as a hardware backup path in the ESP32 firmware but not used in the closed loop. The migration from BLE-primary (control_11) to USB-primary (control_12) is one of the six named MSc contributions — it is not a trivial protocol swap.

---

## 3. Results Interpretation (5)

**Q3.1 — Is 179 mm mean joint error good enough?**
For the target use case — delivering a ball to a specific body joint — yes. A volleyball, basketball, or tennis ball has a diameter of 65–300 mm, so a 179 mm positioning error is *inside the ball*. The metric that matters for this system is precision (std), which is 4.4 mm — the sensor is *consistent*, just offset. The 179 mm mean is dominated by a correctable systematic bias (X+83, Z-125 mm). The linear GT correction model already in `launcher_runtime_from_udp.py` reduces that bias at inference time.

**Q3.2 — How does bias correction generalize outside the GT set?**
The bias is systematic because the arena extrinsic calibration has a fixed pose offset inherited from the AprilTag-wall mount geometry. Any point in the working volume experiences the same offset, within the precision noise of 4 mm. We fit a per-axis linear model on GT trials and validated it on a held-out subset; the correction reduced mean joint error without changing precision. Generalization outside the working volume (extrapolation) is not claimed and is explicit future work: re-measure the GT grid with the launcher in its final installed pose.

**Q3.3 — Why does the Kalman filter fail on jump motion?**
Because jump motion has high vertical acceleration that a constant-velocity model cannot predict. Between peak and apex the true velocity flips sign, and a CV filter will overshoot by exactly the acceleration × dt². At 15 FPS and a 400 ms prediction horizon, that's a real effect. Our ablation shows walk +47%, jog +34–39%, jump ~neutral — meaning the prediction neither helps nor hurts. An acceleration-aware model is explicit future work; the current Kalman is tuned to not *degrade* jump motion, which it achieves.

**Q3.4 — P95 vs mean — which matters more for safety?**
P95 matters more for safety. A safety-critical system cannot have a tail that lands the ball in a bystander's face. P95 for joint-touch is 243.77 mm, which is still within the operator-exclusion zone and within the launcher's own angular tolerance (±30° clamp). Mean is useful for communicating typical behaviour to a non-technical audience, but every safety gate in the supervisor and firmware is tuned to P95, not mean. If an outlier beyond P95 arrives, the zone/confidence/stability gates reject it before the launcher ever fires.

**Q3.5 — How can YOLO-Pose match MMPose at 6× speed with <5 mm 3D jitter delta?**
Because 3D jitter is dominated by *triangulation* noise and the Kalman filter, not by 2D keypoint noise. YOLO-Pose's per-keypoint 2D error is slightly larger than MMPose's, but multi-view SVD-DLT averages out uncorrelated 2D noise, and the Kalman filter smooths remaining jitter to its measurement-noise floor. The net 3D jitter difference is inside the calibration-limited error budget. The speed gap, by contrast, is a fixed 6.2× across every frame. Our ablation on recorded walk/jog/jump sequences confirmed the trade-off empirically.

---

## 4. Hardware / ECE (5)

**Q4.1 — Why DRV8825 and not TMC2209 or a closed-loop servo driver?**
The pusher moves <30 mm at open-loop step accuracy already inside mechanical tolerance. DRV8825 is cheap, robust, has integrated current limiting and thermal shutdown, and is compatible with the AccelStepper library. TMC2209 would add silent operation but buys no precision we need. A closed-loop servo driver would require encoder integration on the pusher shaft — no benefit at this travel distance. The DRV8825's `nENABLE` HIGH-in-IDLE / LOW-in-MOTION convention is used explicitly for thermal management. This is a conscious ECE cost/performance choice.

**Q4.2 — Why ESP32 and not Teensy 4.x or RP2040?**
ESP32 has native UART ≥ 1 Mbaud, dual-core for separating stepper ISRs from command parsing, onboard BLE as a hardware backup path, and costs ~USD 15. Teensy 4.x is faster but four times the cost and lacks onboard BLE. RP2040 is cheaper but its single-core PIO model complicates the stepper+serial+encoder mix we already have running on the ESP32. The control_12 firmware's cooperative FSM is tuned to the ESP32's dual-core scheduling; migrating would cost weeks of bring-up. The choice is BOM- and feature-driven, not inertia.

**Q4.3 — How is the 24 V rail fused and grounded?**
24 V is supplied from a fused bench supply rated at 50 A. Logic ground (ESP32, 5 V USB) and power ground (24 V, steppers, ESCs) meet at a single star point at the power-distribution block, per IEC 60204-1. The steppers and flywheels share the 24 V rail through separate fuses so a motor fault cannot cascade to logic. The E-STOP switch, normally-closed, interrupts the 24 V rail before any motor controller — logic stays powered to log the stop event. Wire gauges and fuse ratings are in the BOM section of `thesis_engineering_chapter.md`.

**Q4.4 — How does the E-STOP meet ISO 13849-1?**
The E-STOP is a normally-closed mushroom switch in series with the 24 V rail feeding the motor drivers. Opening it cuts motor power in <100 ms (measured via serial latch-event logs), then the ESP32 enters `STATE_IDLE` and logs the event. Reset requires a manual `clear` command plus a physical re-arming of the switch — a two-action release, matching ISO 13849-1 Category 1. We do not claim Category 3 (single-fault tolerance) because we have one channel; that is explicit future work. Logic power remains up so the operator can observe the stop.

**Q4.5 — How is the ground star wired?**
Single-point at the power-distribution block. ESP32 logic ground, DRV8825 logic ground, ESC logic ground, and all signal returns land on one copper pad. 24 V power ground from each motor driver lands on a separate pad, and the two pads are bridged by a single short strap. This avoids motor-current transients coupling into logic via shared-impedance ground loops. Camera USB grounds are isolated through the USB cable's hub — they do not see the 24 V ground at all. The layout is photographed in [PLACEHOLDER_SCREENSHOT_3: hardware close-up] on slide 7.

---

## 5. Safety & Ethics (3)

**Q5.1 — What happens if the UDP link or serial link drops mid-shot?**
Both paths have automatic safe-stop. The Python supervisor monitors UDP receive timestamps; on a >500 ms gap `[VERIFY]`, it sends `stop` + `set 0 0 0 0` and moves to IDLE. The serial path has a similar timeout inside `launcher_runtime_from_udp.py`. If serial itself disconnects, the ESP32 firmware falls back to its last commanded state and refuses new `shoot` commands until `reload` is issued. Additionally, any Python exception triggers the same stop path. This is Layer L9 and L10 of the 10-layer safety stack in appendix A2.

**Q5.2 — What standards apply to this system?**
Four directly: ISO 12100 (general machinery safety principles — hazard analysis), ISO 13849-1 Cat. 1 (safety-related control parts — our E-STOP channel), IEC 60204-1 (electrical equipment of machines — wiring, fusing, ground separation), and ISO 10218-1 (robot/human exclusion — operator position behind the launcher). We document compliance in `thesis_engineering_chapter.md` §Safety. We do not claim full certification — that would require third-party audit — but the architecture is *compliant by construction*.

**Q5.3 — Is the system compliant with ISO 12100?**
The *architecture* is aligned with ISO 12100: we performed a hazard analysis (ball energy, pinch points, trip hazards), identified mitigations (exclusion zone, E-STOP, interlocks), and ranked residual risks. What we do not claim is third-party certification, which is out of scope for an MSc thesis. The thesis reports ISO 12100 as a *design reference*, not a certification. For deployment outside the lab, a notified body audit would be required — this is explicit in the future-work slide.

---

## 6. Limitations & Future Work (4)

**Q6.1 — When will the acceleration-aware Kalman filter arrive?**
It's the next filter iteration. The plan is a 9-state [x, y, z, vx, vy, vz, ax, ay, az] constant-acceleration model with an adaptive process-noise term that senses jump onset via vertical velocity sign-change. The challenge is tuning on jump data: we need more recorded jump sequences (we have one, `jump_01`) before a CA filter can be validated. Expected timeline: after the RPM→m/s calibration closes out Phase 0. A CA filter is scaffolded in the codebase but not wired into the live viewer pending regression fixtures.

**Q6.2 — What is the plan for RPM→m/s calibration?**
A radar-gun sweep: chronograph the exit velocity across 400, 500, 600, 700, 800 RPM in 100 RPM steps, fit a linear or quadratic curve, and feed that into the ballistic solver in place of the fixed 10 m/s assumption. Equipment: a commercial radar chronograph (~USD 150) or a dual-photogate timer (~USD 60). Planned duration: one afternoon of recording plus an hour of curve-fitting. This is the only remaining Phase 0 item before sub-200 mm ball delivery can be validated end-to-end at 800 RPM. Currently tagged `[MISSING EVIDENCE]` on slide 13.

**Q6.3 — What's the cost of migrating to ROS2?**
Non-trivial. ROS2 would replace the UDP-over-loopback supervisor with a `rclpy` node graph, add deterministic QoS guarantees, and open the system to ROS2-compatible tooling (rviz, rosbag). The cost is: containerized build, rewrite of the supervisor + launcher runtime as nodes, retime-validation of the serial path against ROS2 executor latency, and CI integration. Estimated two developer-months for a first working version. Currently deferred to Phase 5 in `docs/archive/legacy_notes/suggestions.md` because the existing UDP stack meets the real-time budget.

**Q6.4 — Why does the system need HMAC link authentication?**
Because today the UDP supervisor accepts any packet on its port. In the lab this is fine. For public or multi-tenant deployment — a physiotherapy clinic with multiple launchers on the same subnet — an attacker could inject targeting packets. Adding HMAC-SHA256 with a shared pre-shared key inside each UDP packet closes that vector at ~10 µs per packet. This is straightforward engineering work scoped in `docs/archive/legacy_notes/suggestions.md`; it was deferred to keep the MSc scope bounded but is the first security hardening we would add for a real product.

---

## Defense rehearsal notes

- Rehearse answers **at the length shown**. A 120-word answer takes ~45–50 seconds; anything longer dilutes the response and invites follow-ups.
- If a question comes that is *not* in this bank, pivot to one of these three: "that is explicit future work, I can show you the scaffolding", "that is in the appendix, slide A[2/3/4]", or "I do not have data for that — I can outline the experimental design I would run".
- Never argue with the committee. If pushed on a number, offer to show the source file — every number here has a path in `assets_checklist.md`.
- For results-critical numbers (179 mm, 156.9 mm, 6.2×, USD 200, ~120 ms, 15 FPS), memorize exactly. Guessing loses the rubric's "clearly understood the question / concise answer" points.
