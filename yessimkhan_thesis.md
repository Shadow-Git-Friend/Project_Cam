Here is a comprehensive, structured Markdown (.md) file designed to give Claude (or any AI/human) an instant, deep understanding of the Master's thesis without needing to parse the entire document. It logically organizes the mechanical iterations, aerodynamic modeling, and AI control strategies.

```markdown
# MS Thesis: Designing of Omni Directional, Autonomous and AI Controlled Ball Launcher

## 🎯 1. Project Overview (TL;DR)
**Title:** Designing of Omni Directional, Autonomous and AI Controlled Ball Launcher
**Author:** Yessimkhan Orynbay (ID: 201713885)
**Degree:** Master of Electrical and Computer Engineering
**Institution:** Nazarbayev University | **Date:** June 2025
**Supervisors:** Sultangali Arzukylov (Main), Mohammad Hashmi (Co-supervisor)

**Core Objective:** To design an omnidirectional, AI-driven soccer ball launcher that replaces inconsistent human passing during training. The system integrates a custom aluminum chassis, 2-DOF gimbal aiming, physics-based aerodynamic flight modeling, and Reinforcement Learning (PPO/DDPG) to create a closed-loop system that autonomously adjusts its aim based on visual feedback of shot outcomes.

---

## ⚙️ 2. Mechanical Design & Hardware Evolution

### Chassis Evolution
1. **Phase 1 (Wood):** Used for rapid prototyping, motor placement testing, and primitive design. *Rejected due to lack of rigidity and severe vibration at high speeds.*
2. **Phase 2 (Aluminum 6061):** Final design using 30×30 mm aluminum construction profiles with corner connections. Provides high strength-to-weight ratio, vibration dissipation, and mobility.

### Motor Selection & Testing
The project experimented with several motor types before finalizing the design:
- **PMDC (MY1016, 350W, 2700 RPM):** Used in early prototyping. Cheap and easy to control, but suffered from noise, brush wear, and poor speed control at high RPMs.
- **AC Washing Machine Motor:** Extremely cheap and accessible, but rejected due to severe power and speed-control integration difficulties.
- **DC Pump Motor:** Rejected; lacked sufficient torque and power.
- **3-Phase BLDC (Final Choice):** Selected for the production design. Offers efficient, smooth rotation and highly accurate closed-loop speed control via the **ODrive v3.6** controller. Both 350W and 2500W variants were tested.

### Wheel Selection & Balancing
- **Rejected Wheels:** Construction wheels (too heavy, slow acceleration), Scooter wheels (too small), Hoverboard wheels (too large/heavy).
- **Selected Wheels:** Aluminum alloy wheels (lightweight, high load-bearing).
- **Future Upgrade:** Custom wheels with polyurethane coatings for better ball friction/grip.
- **Balancing:** Small counter-weights added to offset center of mass; successfully tested up to 2500 RPM to eliminate dangerous vibrations.

### Omnidirectional Aiming Platform (2-DOF Gimbal)
- **Actuators:** NEMA 23 stepper motors.
- **Gearbox:** 1:50 worm gear reducers (increases torque, angular resolution, and prevents back-driving).
- **Backlash Issue:** Horizontal reducer had ~2° of mechanical play, causing aiming inaccuracies. 
  - *Failed Fix:* Magnetic encoder feedback caused jittery, unstable micro-adjustments.
  - *Successful Fix:* Software-based backlash compensation in the control logic.
- **Friction Reduction:** Mini rollers attached to 4 sides of the moving platform to prevent jamming and reduce actuator load.

---

## 🌬️ 3. Ball Aerodynamics & Flight Simulation

### Governing Physics Model
The system moves beyond simple 2D projectile motion by incorporating 3D aerodynamic forces (Drag, Lift/Magnus Effect). 

**Equations of Motion:**
`m(dv/dt) = mg + F_D + F_L`

**Force Definitions:**
- **Drag Force:** `F_D = -0.5 * ρ * C_D * A * ||v|| * v` (Opposes velocity)
- **Lift Force (Magnus):** `F_L = 0.5 * ρ * C_L * A * ||v||^2 * n̂` (Perpendicular to velocity/spin plane)

**Dynamic Coefficients:**
Aerodynamic coefficients are *not* constant. They are modeled as functions of Reynolds Number ($Re$) and Spin Parameter ($S$) to account for drag crisis and knuckleball effects at soccer speeds ($Re \approx 70,000 - 500,000$):
- $C_D = C_D(Re)$
- $C_L = C_L(Re, S)$

### Simulation Tools (MATLAB)
- **Solver:** `ode45` (Runge-Kutta) for nonlinear ODE integration.
- **Inputs:** Initial position, launch speed, elevation angle, azimuth angle, spin (derived from differential wheel speeds).
- **Features:** 
  - Models side-spin (curved passes) and topspin/backspin (dipping/rising shots).
  - Includes exponential spin decay over time.
  - Event-based termination (stops sim if ball hits ground, exceeds max altitude, or leaves the pitch).
  - Full 3D football pitch visualization.

---

## 🧠 4. Control Architecture & AI Implementation

### Hierarchical Control Structure
The system mirrors professional robot-soccer architectures:
1. **High-Level (Embedded GPU/Jetson):** Computer vision (object detection, state estimation), trajectory prediction, decision-making, and RL policy execution.
2. **Low-Level (Dedicated Controllers):** Real-time motor control, closed-loop PI tuning, and time-critical actuator commands (ODrive for BLDCs, stepper drivers for gimbal).

### Computer Vision & Visual Servoing
- **Hardware:** Omnidirectional/monocular cameras.
- **Software:** Deep learning detectors (e.g., SSD-MobileNet) for robust ball, player, and goal detection despite lighting changes.
- **Visual Servoing:** Uses geometric error between observed landing point and target to calculate yaw/pitch adjustments for the next shot.

### Reinforcement Learning for Self-Improving Aim
Static calibration fails due to nonlinear real-world dynamics (friction, slip, wind, motor lag). RL is used to learn corrective mappings.

**Algorithms Applied:**
1. **PPO (Proximal Policy Optimization):** Used for stable tuning via a clipped objective function.
2. **DDPG (Deep Deterministic Policy Gradient):** Used for continuous control optimization of wheel speeds and angles.

**RL Formulation:**
- **State:** Target position, current launcher pose, wheel speeds, observed miss distance.
- **Action:** Changes to launch parameters (wheel RPMs, yaw, pitch).
- **Reward:** Penalizes miss distance; encourages repeatability.

---

## 🧪 5. System Testing & Integration Scope

Based on the thesis structure, the testing and validation phase covers:
1. **Experimental Environment & 3D Projection:** Calibrating the camera array and mapping 2D pixels to 3D world coordinates.
2. **Ball & Pose Detection:** Validating YOLO/deep-learning models for tracking the ball in flight and the player's readiness.
3. **User Interface & Voice Control:** Integrating Speech-to-Text (SST) and LLMs for hands-free drill configuration.
4. **Low-Level Hardware Control:** Tuning the ODrive/Stepper responses and validating software backlash compensation.
5. **RL Training Loop:** Training the PPO/DDPG agents in simulation and deploying them for live, iterative accuracy improvement.

---

## 📌 6. Key Distinctions & Engineering Takeaways

- **From Open-Loop to Closed-Loop:** Existing commercial systems (Footbonaut) rely on pre-planned trajectories and human operators. This thesis introduces a *closed-loop, self-correcting* system using visual feedback and RL.
- **Software > Hardware Fixes:** Instead of forcing hardware perfection (expensive zero-backlash gearboxes), the author successfully used software compensation to mitigate a 2° mechanical backlash in the worm gears.
- **Physics-Informed RL:** The RL agent does not start from zero; it is bootstrapped by the MATLAB aerodynamic simulation model, drastically reducing real-world training time and physical wear-and-tear.
```