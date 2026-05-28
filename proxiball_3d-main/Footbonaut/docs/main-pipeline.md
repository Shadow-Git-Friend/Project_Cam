# Production Service Integration & Footbonaut Garage Architecture

This file archives the extensive roadmap, structural architecture designs, decision engines, and networking schematics necessary to complete the transition from static code processing into the live 4-camera "Garage" robotics deployment (`Footbonaut_v6_frozen`).

---

## 1. Repo Structure & Modules
The future structural architecture distributes monolithic files cleanly into node-based responsibilities:
* `camera_node/` - Deployed on individual edge hardware (per-camera app execution natively running YOLO/tracking).
* `central_node/` - High-tier compute orchestrating fusion sequences and driving robotic decision systems. 
* `shared/` - Synchronized definitions across environments (JSON schemas, global networking config loops).
* `calibration/` - Static intrinsics/extrinsics loaders defining topological projection matrix math. 

## 2. Geometric & Calibration Architecture
* **Intrinsics Loader**: Applies strictly undistorted `K`, `D` coefficients actively rectifying streams prior to analysis.
* **Extrinsics Loader**: Pulls `R`, `t` rotations indexing 3D camera arrays locally into uniform world conventions. 
* **3D Vectors**: Undistorted pixels are reversed sequentially into standard Ray Backprojections mapping spatial target points resolving via computational Multi-Ray Least-Squares intersections (crossing 2 to 4 camera rays mathematically).
* **Launch Forecasting**: Trajectories explicitly compute linear plane intersections tracking paths matching standard impact collision times directly against the target wall planes.

## 3. Hardware Deployment & The Per-Camera Node (Edge)
* Frame capture enforces strict fixed-FPS locking dynamically freezing exposure and white-balance automatically explicitly preventing YOLO decay tracking environments. 
* Executes highly quantized TensorRT outputs locally passing the Custom `PersistentTrackerV3/V4` outputs routing sequential bounds. 
* Capable of overlapping standard YOLO instances with native YOLO-Pose components structurally extracting physical player positioning relative to trajectories. 

## 4. Networking & Data Flow 
* Structured UDP/TCP transports rigidly defined by strictly versioned **JSON schemas** routing standard sequence numbers blocking dropped payload sequences natively. 
* Pushes Edge Camera logic into Publisher domains targeting highly decoupled Central Receiver APIs actively handling per-camera ring buffers dynamically aligning nearest spatial payload captures against time-frames. 

## 5. Time Synchronization (Critical Safety Constraint)
* Clocks executing across internal LAN connections mandate NTP/PTP level accuracy, physically verifying latency drift boundaries. 
* Timestamping architectures explicitly delineate `capture-time` bounds vs explicit network `send-time` to eliminate multi-ray intersection collisions blocking spatial convergence logic inside the Central Node Fusion loops.

## 6. The Central Node Decision Engine
- Takes the isolated time-syncd boundaries generating high-fidelity Kinematics arrays evaluating live speed derivations, trajectory apexes, and exact Time Of Flight (TOF) boundaries natively.
- Passes coordinates directly into the structural Difficulty Engine modifying subsequent ball launch profiles manipulating the environment autonomously ensuring statistical player variation mapping. 
- Estimates impact predictions calculating 3D box-hit error margins matching player proximity to spatial targets. 

## 7. Launcher Controls & Physical Interlocks
- Central APIs distribute actionable Mechanical bounds routing JSON bounds specifying direct hardware `[yaw, pitch, mechanical wheel RPM speed, fire constraints]`. 
- Heavily embedded software safety watchdogs lock mechanical systems verifying active ARM/DISARM conditions blocking execution mapping against calibration outputs natively translating simple `target speeds m/s` seamlessly directly into physical RPM configurations dynamically. 

---

## Explicit Final "Action Plan" / Next Steps 
These exact 14 roadmap items are mandatory inclusions mapping towards completing `Footbonaut_v6_frozen`:

1.  **Output Export Naming**: Save video outputs with dynamically distinct names defining localized phases implicitly without overwriting structures.
2.  **Explicit Metrics Output Streams**: 
    - 2D ball speed from camA & camB (px/frame)
    - 3D ball speed ($m/s$)
    - 2D ball position mapping camA & B ($px$)
    - 3D ball spatial position ($m$)
    - 2D ball acceleration (px/frame²)
    - 3D ball acceleration ($m/s^2$)
3.  **Variable Skipping Rules**: Adaptive frame skipping strictly dependent on active 3D ball speed thresholds. (If zero = skip; If massive = execute frame 1). 
4.  **Aesthetic Trajectories**: Modifying tracking lines natively rendered directly upon the Isometric 3D field views imposing 2-second vanishing intervals bypassing overlapping visual trace messes.
5.  **Target Code Audits**: Actively execute the deletion of all redundant/temporary scripts. 
6.  **Pipeline Terminal Versioning**: Execute freeze commands producing `Footbonaut_v6_frozen`. Do not duplicate multi-GB network structures natively mapping dependencies solely tracking internal scripts. Update target standard readme. 
7.  **Bottleneck Tracking**: Diagnose explicit output structures determining exactly why native streams hard-cap against local 50FPS limit blocks. 
8.  **Frame Skipping Experiments**: Refine execution structures isolating faster performance capabilities strictly quantitatively analyzing bounding parameters.
9. **Semaphore Experimentation**: Evaluate robust threading mutex limits replacing rudimentary queues. 
10. **Thread Constraints Validation**: Extend thread structures to isolated domains dynamically mapping. 
11. **Batch Validation Tests**: Compile experimental execution models pushing tensor workloads via synchronized structures.
12. **UX Visual Transition**: Terminate the standard quad-grid rendering topology migrating fully natively producing sole 3D topological Isometric rendering grids enforcing spatial 10x10 metric arenas instead of generic legacy 10x20 sizes. 
13. **Central JSON Metadata Telemetry**: Structurally export rigid traces dictating natively `[3d_x, 3d_y, 3d_z, vx, vy, ax_y_z, timestamp, ball_id]`.
14. **2D Trajectory Optimization**: Conclude and deprecate unreliable 3D direct-predictions natively leveraging 2D predictions scaling explicitly tracking targets mathematically.

### Critical Safety Principles
* Hard restrict Out-Of-Memory (OOM) leaks. 
* Avoid overheating parameters and executing over-stresses across local device/Jetson GPUs dynamically mapping hardware bounds.
* Restrict execution loops causing terminal space flooding deleting temporary videos and generic trace bounds instantly when rendered correctly natively mapping logs efficiently. 
* Render execution data tracing explicitly exporting findings generating comprehensive `report.md` analytics mapping specific architectural impacts and findings.
