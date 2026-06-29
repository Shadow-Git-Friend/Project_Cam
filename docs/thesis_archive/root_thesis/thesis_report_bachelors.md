Here is a comprehensive, structured Markdown (.md) file designed to give Claude (or any AI/human) an instant, deep understanding of the 60+ page capstone report without needing to parse the original document. 

It prioritizes architectural clarity, exact metrics, design rationale, and requirements traceability.

```markdown
# ECE Capstone Project: Ball-Launching System Architecture & Performance Summary

## 🎯 1. Project Overview (TL;DR)
**Project:** Ball-Launching System: Architecture, Prototyping, and Performance Evaluation (Footbonaut-style AI Trainer)
**Team:** Aldiyar Mukhamediya (Motor/HW), Azamat Shmitov (3D/Reconstruction), Altay Kairat (CV/Integration)
**Supervisor:** Prof. Sultangali Arzykulov | **Term:** Spring 2026

**Core Function:** An autonomous, AI-driven soccer ball launching system that uses a 4-camera array to detect a player, estimate their 3D pose, identify a target body part, and command a motorized gimbal launcher to deliver the ball accurately—removing the need for a human operator.

---

## 🏗️ 2. Final System Architecture
The system uses a **Centralized Single-PC Architecture** (migrated from distributed edge nodes in CHG-4). It is divided into three subsystems linked via wired USB and wireless BLE.

### Subsystem 1: Central Perception & Analysis PC
- **Hardware:** Ryzen 5 5600H + RTX 3050 (4 GB) [Inference]; RTX 5000 Ada (32 GB) [Training]
- **Cameras:** 4× Hikvision DS-E12 (1080p @ 30 FPS over USB 3.0)
- **Pipeline:** 
  1. Async multi-threaded VideoLoader
  2. YOLOv26s (Ball) + YOLO-Pose (Player) via TensorRT FP16
  3. PersistentTrackerV3/V4 (Hungarian matching, Kalman prediction)
  4. N-view DLT/SVD 3D Triangulation
  5. Command Generation → BLE Dispatch

### Subsystem 2: BLE Launcher Control
- **Compute:** ESP32 (BLE GATT Server) + Arduino UNO (Motor Control)
- **Actuation:** 2× BLDC Motors (Hobbywing Xrotor Pro 50A ESC, DSHOT) + 2× NEMA-23 Steppers (Worm-gear 2-DOF Gimbal)
- **Feedback:** AS5047P Absolute Magnetic Encoders (14-bit)

### Subsystem 3: Human Interaction Layer
- **Interfaces:** Android/Kotlin BLE App + Voice Command Module (Vosk STT with 100ms debounce).

### ⏱️ Latency Budget
`CV Inference (17.91ms) + Tracker (0.02ms) + 3D Triangulation (<2ms) + BLE Dispatch (≤20ms) + Arduino Parsing (≈80ms) = ~120ms Total Loop` (Well within 300ms TLR-7 threshold).

---

## 📊 3. Key Performance Metrics & Requirements Compliance

### Requirements Status: 7 Met / 2 Partial / 1 Not Met
| ID | Requirement | Threshold | Achieved Result | Status |
|:---|:------------|:----------|:----------------|:-------|
| **TLR-1** | Player Detection (YOLO-Pose) | mAP ≥ 95% | mAP ≈ 96% | ✅ MET |
| **TLR-2** | Pose/Readiness Estimation | PCK ≥ 85% | PCK ≈ 92% | ✅ MET |
| **TLR-3** | Ball Detection (YOLOv26s) | mAP@50 ≥ 0.85 | mAP@50 = 0.9786 | ✅ MET |
| **TLR-4** | Real-time Tracking Throughput | ≥ 20 FPS | >2000 FPS (1 cam), ≈100 FPS (Stereo+3D) | ✅ MET |
| **TLR-5** | Ball Exit Speed Control | ±2.0 m/s of target | Functional, but no radar gun to verify | 🟡 PARTIAL |
| **TLR-6** | Gimbal Aim Accuracy | ±3° | Consistent ±3° (Encoder verified) | ✅ MET |
| **TLR-7** | Autonomous CV-to-Launch | End-to-end ≤ 300 ms | Subsystem chain verified; Full Stage 5 live trial pending | 🟡 PARTIAL |
| **TLR-8** | Adaptive Difficulty Engine | Change ≤ 1 cycle | De-scoped in W12 for integration/safety time | ❌ NOT MET |
| **TLR-9** | BLE Comms Reliability | ≥ 95% packet success | Reliable, ≤ 20ms latency | ✅ MET |
| **TLR-10** | Shot Repeatability | SD ≤ 8°, ≤ 2.5 m/s | Consistent within thresholds | ✅ MET |

### Computer Vision & 3D Benchmarks
- **Ball Detection (ProxiBall Dataset):** Small-ball recall jumped from 47.96% → 89.12%; Fast-ball recall from 68.18% → 99.24%.
- **3D Localization (4-cam DLT):** Mean ball error = 95.17 mm (P95 = 166.51 mm). Joint mean error = 143.38 mm.
- **Inference Latency:** YOLOv26s TRT FP16 mean = 17.91 ms (P95 = 21.37 ms).

---

## 🔄 4. Critical Design Evolutions (The "Why")

| Change ID | What Changed | Rationale |
|:----------|:-------------|:----------|
| **CHG-1** | Added ~11,000 frames to ProxiBall dataset | Original small/fast ball recall was abysmal. Retraining brought mAP@50 to 0.9786. |
| **CHG-2** | Extrinsic Calibration: ChArUco → AprilTag 24-tag wall | Garage arena was too large for ChArUco board; AprilTag restored metric 3D consistency (reduced baseline error from 12.25m to 7.08m). |
| **CHG-3** | Comms: Bluetooth SPP → BLE (Nordic UART Service) | SPP buffer caused dropped/stale commands. BLE resolved buffering and achieved ≥95% delivery. |
| **CHG-4** | Architecture: Distributed Edge (Jetsons) → Centralized PC | Jetson procurement delays + sync overhead. Centralizing worked because TensorRT FP16 yielded >2000 FPS on RTX 3050. |

---

## ⚙️ 5. Technical Deep Dive

### Software & Algorithms
- **Ball Detection:** YOLOv26s (Custom trained on ProxiBall). Exports to TensorRT FP16 (19.4 MB engine). Uses Adaptive Frame Skipping (predicts via Kalman during ballistic flight) and Dynamic ROI Recovery for re-detection.
- **Pose Estimation:** YOLO-Pose + RTMPose (COCO 17-keypoint). Gating logic ensures `FIRE` command only triggers if player is in ready posture (SAFE-1).
- **3D Reconstruction:** N-view DLT triangulation via SVD. Applies linear axis-correction model to remove Z-axis bias.
- **Tracking:** PersistentTrackerV3/V4 utilizing Hungarian matching, EMA velocity smoothing, and Kalman prediction.

### Hardware & Mechanical
- **Frame:** Aluminium 6061 (30×30 mm profiles). Survived 10-consecutive impact tests.
- **Gimbal:** 2-DOF (Pitch ±30°, Yaw ±45°). NEMA-23 steppers with worm-gears (prevents back-driving on power loss).
- **Propulsion:** 2× Counter-rotating BLDC wheels (25cm go-kart wheels). Differential speeds create Magnus-effect spin (Re ≈ 70k–500k).
- **Encoders:** AS5047P (14-bit, ±0.2° accuracy) for closed-loop aim feedback.

### Communication Protocol (BLE)
- **Service UUID:** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`
- **Write UUID:** `6E400002...` | **Notify UUID:** `6E400003...`
- **Master Command Format:** `set {v:.1f} {h:.1f} {wl:.2f} {wr:.2f}\n` *(v=vertical deg, h=horizontal deg, wl/wr=wheel RPM)*
- **Other Commands:** `shoot\n`, `reload\n`, `stop\n`, `center\n`, `setzero\n`
- **Telemetry Format:** `T: L_RPM:{set}/{actual} | R_RPM:{set}/{actual} | H:{h:.2f}`

---

## 🛡️ 6. Safety, Constraints & Standards

### Critical Safety Requirements (Firmware/Hardware Interlocks)
1. **SAFE-1:** No launch if player is undetected or not in ready pose.
2. **SAFE-2:** Firmware hard-limits: RPM ≤ 4,500 | Yaw ≤ ±45° | Pitch ≤ ±30°.
3. **SAFE-3:** Normally-closed E-STOP physically cuts 24V power rail (< 100 ms latch time).
4. **SAFE-4:** Ball-feeder interlocked; requires wheel speed ≥ 400 RPM to prevent jamming.

### Key Engineering Standards Applied
- **ISO 12100 / ISO 13849-1:** Machinery safety & fail-safe stop paths.
- **IEC 60204-1:** Control circuit wiring / 24V 50A fuse sizing.
- **ISO 10218-1:** Robot/human interaction (exclusion zones enforced).
- **Bluetooth Core Spec 5.0:** LE PHY / GATT profiles.

### Project Constraints
- **Budget:** ≤ 724,375 KZT (Archived core HW BOM: 477,963 KZT).
- **Compute:** Air-gapped system; no cloud compute allowed due to latency/privacy.
- **Schedule:** 14 weeks forced TLR-8 (Adaptive Engine) de-scoping.

---

## 🧪 7. Integration Stages & Verification Status
System integration followed a strict 6-stage incremental checklist:
- [x] **Stage 0:** Components powered individually.
- [x] **Stage 1:** Gimbal open-loop command test.
- [x] **Stage 2:** BLDC spin-up test (no ball).
- [x] **Stage 3:** BLE end-to-end command test.
- [x] **Stage 4:** Aim-only mode with CV in the loop.
- [ ] **Stage 5:** Full autonomous fire sequence with moving player. *(Pending: Post-capstone continuation item)*

---

## 🚀 8. Known Limitations & Next Steps
1. **Missing Formal Speed Verification (TLR-5):** Ball exit speed (5-30 m/s range) is mathematically modeled and adjustable, but could not be formally verified due to lack of a Doppler radar gun.
2. **Incomplete Closed-Loop Timing (TLR-7):** Subsystem latencies are verified, but a live Stage 5 end-to-end CV→Fire trial with a moving player needs to be executed.
3. **Next Steps:** Procure radar gun for 10-shot exit-speed test, execute Stage 5 live trial, and revisit the de-scoped Adaptive Difficulty Engine (TLR-8) for future iterations.
```