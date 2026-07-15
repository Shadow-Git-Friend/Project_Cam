# Project Cam Garage Demonstrator and Academy Pilot Design

**Date:** 2026-07-15

**Status:** Approved direction; detailed design awaiting user review

**Owner:** Single developer

**Scope:** Architecture, desktop UX, Face ID, multi-person validation, firing safety, analytics, and the path from the garage to an FC Kairat pilot

**Protected boundary:** Do not modify `triangulate_multi`, `transform_world_point_y`, `ema_update`, or UDP axis semantics.

## 1. Decision

Project Cam will support two use cases through one product surface, but it will not pretend that they have the same readiness.

1. **Operational Zone Drill** — coach-triggered shots to calibrated safe zones. This is the reliability anchor and the first pilot-capable mode.
2. **Pose-Guided Validation** — athlete tracking, identity labels, pose-relative aiming, multi-person safety blocking, and controlled low-energy trials. This remains clearly labelled as validation until it passes the live gates in this document.

The garage is an evidence lab, not a miniature academy. Its job is to produce repeatable proof that the system starts reliably, delivers measurable shots, records useful athlete outcomes, and fails closed when conditions are unsafe.

## 2. Verified Current State

- The Tauri 2 + React desktop application builds successfully, and its Rust backend can spawn one process group, stream stdout/stderr, and perform timed SIGINT -> SIGTERM -> SIGKILL shutdown.
- The current branch is newer than the July 12 report. It contains an additive all-person safety snapshot, a pure fail-closed ballistic-corridor evaluator, and enforcement at pose-driven serial `shoot` boundaries.
- The current firing-line implementation is heavily unit-tested but has not been validated with real people and hardware. It must be described as **implemented, not commissioned**.
- The face gallery is private and local, but arena enrollment can finish after four seconds with samples from one camera. It does not yet prove pose, camera, lighting, or embedding diversity.
- The existing `EventLogger` already defines the useful session chain: `session_start`, `target_chosen`, `aim_command_sent`, `ball_launched`, `athlete_reacted`, `outcome_scored`, `safety_gate_blocked`, and `session_end`.
- Analytics and Matches in the Tauri application are still static demo data. The legacy Tk application has parsing code, but no producer creates a trustworthy athlete profile.
- RPM-to-exit-speed calibration is open. This is both an accuracy blocker and a safety-model blocker because the clearance gate currently samples a trajectory using an assumed speed.
- Multi-person tracking and arena Face ID remain unvalidated on real 2–6-person scenarios.

## 3. Product Promise

The first credible promise is:

> A coach can run a repeatable goalkeeper reaction session, deliver balls to known zones under explicit supervision, and receive an honest shot-by-shot report. The vision layer identifies the active athlete, measures their response, and blocks operation when the scene is ambiguous.

Do not claim that the launcher has 4.4 mm shot accuracy. The documented 4.4 mm figure is reconstruction repeatability/precision. Commercial material must separately report:

- 3D localization precision;
- corrected 3D localization error;
- launcher angular repeatability;
- ball exit-speed error;
- end-to-end ball-placement error at the goal or target plane.

## 4. Garage Demonstration

A complete investor or coach demonstration should take 8–10 minutes:

1. Run an active preflight and show required cameras, calibration binding, models, storage, launcher connection, and safety input status.
2. Select an existing athlete and the Operational Zone Drill.
3. Run 8–12 coach-triggered shots using validated zone and speed presets.
4. Show the real session summary: commanded zone, measured delivery, outcome, reaction initiation, side, height, and safety blocks.
5. Switch to Pose-Guided Validation with two or three people and no actuation.
6. Show stable IDs through a crossing and partial occlusion.
7. Show an intentional safety block when a secondary person enters the corridor.
8. Optionally perform one low-energy pose-relative shot with one adult athlete after explicit arming and a fresh clearance result.

Use visible status labels throughout:

- `OPERATIONAL - ZONE DRILL`
- `VALIDATION - POSE GUIDED`
- `AIM ONLY`
- `ARMED - OPERATOR HOLD REQUIRED`
- `BLOCKED - <REASON>`

## 5. Evolutionary Architecture

Do not rewrite the 5,000-line viewer or move geometry into Rust. Wrap the proven pipeline with small, testable interfaces.

```text
Tauri coach UI
    |
    | named profile + session manifest
    v
Rust supervisor --------------------> session directory
    |                                      |
    | starts/stops + health                | JSONL events + summary JSON
    v                                      v
Python perception/viewer ----------> session aggregator ------> Sessions UI
    |
    | versioned pose + safety packet
    v
launcher owner / fire-control boundary ---> ESP32 / BLM
```

### 5.1 Tauri coach UI

The UI owns coach intent: athlete, drill, preset, session start/stop, and explicit arming. It does not construct arbitrary shell commands and never writes serial commands.

### 5.2 Rust supervisor

Replace the generic frontend-supplied `program + args + cwd` command with an allowlisted registry of named launch profiles. The supervisor owns:

- `Idle`, `Starting`, `Running`, `Stopping`, and `Faulted` states;
- a monotonically increasing process generation;
- structured health and exit events;
- stop escalation with one timer chain rather than multiple concurrent STOP threads;
- app-close cleanup;
- detection and containment of an orphaned previous session;
- runtime configuration discovery instead of hardcoded repository paths.

### 5.3 Session manifest

Every run receives one immutable manifest containing:

- `session_id` and timestamps;
- athlete UUID and display name;
- drill and operating mode;
- camera-rig/calibration identifiers;
- launcher preset and ball type;
- expected participants;
- enabled experimental features;
- event-log and recording paths;
- software/model versions.

Pass a manifest path to Python instead of growing UI-generated argument lists. Existing shell presets remain as rollback paths during migration.

### 5.4 Structured process contract

Human-readable logs remain available, but lifecycle and health must not be inferred from prose. Python should emit versioned JSON status records for:

- camera opened and first fresh frame;
- model loaded;
- calibration loaded and resolution matched;
- perception heartbeat and snapshot age;
- UDP safety stream active;
- launcher connected/disconnected;
- session started/stopped;
- fault reason.

For the garage, newline-delimited JSON over stdout is sufficient. Do not add ROS2, a message broker, or a database service.

### 5.5 Hardware ownership

The current separate launcher scripts remain during P0. Before an external pilot, converge serial ownership into one launcher process. The UI and perception pipeline send intent and telemetry; only that process may emit `set`, `shoot`, `reload`, or `stop`.

This removes disagreement between several scripts about arming state, speed, safety age, and the last commanded trajectory.

### 5.6 Session storage

Use the existing append-only event schema as the source of truth. Add a small deterministic aggregator that produces:

- `session.json` — metadata and final status;
- `shots.json` — one joined record per attempted shot;
- `summary.json` — derived metrics for the UI.

Do not introduce SQLite until there is more than one installation or concurrent data access. Never edit source JSONL to fix a report; regenerate derived files.

## 6. Desktop UX

The current name -> face scan -> start flow is understandable for a technology demo, but it is not the correct coach workflow. Enrollment is an occasional administrative action, not a step before every session.

### 6.1 Coach flow

1. **Home:** current rig status, last session, and one `NEW SESSION` action.
2. **Session setup:** select athlete, drill, zone/speed preset, and operating mode.
3. **Preflight:** run active checks and show blocking versus advisory failures.
4. **Live session:** large safety state, current target, shot count, outcome buttons, and a prominent stop action.
5. **Review:** shot table, zone split, reaction metrics, notes, and export.

### 6.2 Athlete management

Move enrollment to an `ATHLETES` screen:

- create/select an athlete record;
- enroll or re-enroll Face ID;
- show enrollment quality and date;
- remove biometric data;
- record consent and retention expiry;
- allow manual athlete selection when Face ID is unavailable.

Face ID is optional convenience. The system must remain fully usable through manual selection.

### 6.3 Live screen

The coach sees decisions, not terminal output:

- `READY`, `AIM ONLY`, `ARMED`, `BLOCKED`, or `FAULT`;
- block reason in plain language;
- primary athlete and confidence of tracking, not biometric score;
- required operator action;
- delivered shots and outcomes;
- launcher and E-stop status.

Keep the mission log collapsed under Diagnostics. Rename `MATCHES` to `SESSIONS` or `SHOTS`; remove fake athlete ratings from the production build. A separate explicit `DEMO DATA` switch can retain the visual preview.

### 6.4 Readiness semantics

File presence is not readiness. Required checks are:

- device path exists **and a fresh frame was acquired**;
- runtime resolution matches calibrated intrinsics or verified scaling;
- extrinsics and dimensions load and identify the intended rig;
- models load and pass a small inference smoke test;
- required disk space is available and event log is writable;
- GPU memory/driver state is usable;
- serial port, firmware identity, limit inputs, E-stop, and launcher state are safe;
- perception heartbeat and safety-snapshot age remain within limits.

On check failure, readiness must be `UNKNOWN` or `BLOCKED`, never a static green fallback.

## 7. Face ID and Enrollment

### 7.1 Recommended enrollment model

Use two stages:

1. **Anchor enrollment:** a short close-range capture with good face size, lighting, and guided yaw/pitch. This creates a clean reference identity.
2. **Arena enrichment:** capture domain examples only from normal athlete positions and only when they agree with the clean anchor.

This is safer than building the entire identity from small, oblique arena faces. In the limited garage, use two or three marked positions and guided head directions instead of asking the athlete to walk a full circle.

### 7.2 Fix the current arena completion rule

The current defaults can finish after four seconds with 24 samples from one camera. Replace sample-count completion with coverage requirements:

- minimum capture duration;
- minimum number of approved cameras, normally both C920s;
- minimum yaw bins such as front, left oblique, and right oblique;
- minimum unique-frame spacing;
- no completion while quality guidance still reports a missing view.

### 7.3 Quality gates

Gate each sample on:

- face box size;
- detector confidence;
- blur/sharpness;
- under/over-exposure;
- landmark completeness and face pose;
- edge clipping/occlusion;
- near-duplicate distance;
- similarity to the anchor identity;
- outlier distance from the new identity centroid;
- margin from the nearest other enrolled identity.

Save per-camera and per-pose quality metadata. Keep several representative exemplars rather than an uncontrolled pile of embeddings.

### 7.4 Recognition routing

Do not round-robin equally across cameras that cannot produce useful faces. Rank candidate views using projected head location, current face size, angle, and camera quality. Prefer the two C920s at high resolution and skip Face ID work on generic cameras when the projected face is too small.

Face ID should label an already-stable track and then coast with that track. `UNKNOWN` is a correct outcome; a false label is worse than no label.

### 7.5 Face validation metrics

Measure at actual operating distances:

- correct identification rate;
- false identification rate;
- unknown/reject rate;
- time to first stable label;
- label persistence through occlusion;
- results by camera, distance, face-pixel size, and head angle.

For the garage gate, require zero false labels in controlled negative trials. Tune for rejection, not maximum recognition rate.

## 8. Multi-Person Validation

Validate with recorded fixtures before tuning live thresholds. Record all camera streams and a synchronized ground-truth reference.

### 8.1 Scenario matrix

- two people standing apart;
- parallel walking;
- head-on crossing;
- one person passing behind another;
- crouching and bending near each other;
- primary exits and re-enters;
- secondary enters near the launcher;
- two, four, and six people at the garage's safe capacity;
- partial camera failure and stale frames;
- false pose candidates from clutter.

### 8.2 Metrics

- person-count recall and false-count rate;
- track coverage while visible to at least two cameras;
- ID switches and fragments;
- spawn and reacquisition latency;
- false primary switches;
- unassigned-candidate duration;
- primary safety-snapshot availability;
- P50/P95/P99 snapshot age;
- effective pose update rate and GPU/CPU load.

### 8.3 Garage acceptance gate

- zero unintended primary switches in 30 staged crossing/occlusion trials;
- every persistent secondary is either tracked or marks the snapshot ambiguous;
- no false track remains active for more than one second;
- no failed pose inference produces an allowable stale snapshot;
- 30/30 staged corridor intrusions block the fire request;
- every primary change requires a fresh aim and re-arm.

Four-to-six-person results are research evidence. The first firing-capable product mode should not depend on reliable six-person identity continuity.

## 9. Safety Design

The software corridor evaluator is valuable, but it cannot be the only safety function. The same camera and ML system cannot both create the target and serve as the sole proof that nobody is in danger; common-cause failure remains possible.

### 9.1 Hierarchy of controls

1. **Physical layout:** fixed launcher, net/backstop, taped no-go corridor, protected coach position, and no spectators in the firing volume.
2. **Energy control:** speed caps, approved ball type, minimum range, guarded pusher/flywheels, and mechanical angle limits.
3. **Hardware safety:** hardwired mushroom E-stop and a hold-to-run or keyed enable that removes actuator energy independently of the PC.
4. **Software safety:** active preflight, explicit arming, fresh all-person telemetry, trajectory clearance, approved target policy, and watchdog timeouts.
5. **Operational controls:** trained operator, checklist, incident log, and supervised adult-only testing before any academy use.

Maintain an ISO 12100-style hazard/risk register and have the safety-related control design reviewed against the methodology of ISO 13849-1 before external deployment. Do not describe the prototype as certified.

### 9.2 Garage firing policy

- Multi-person firing remains disabled until the live gates pass.
- In the first reliable mode, the presence of any secondary person blocks firing, even if they are outside the computed corridor.
- Demonstrate corridor selectivity in aim-only mode.
- No automatic repeated fire; every shot needs a fresh clearance and operator enable.
- Primary switching, ambiguous detections, lost heartbeat, stale pose, serial fault, or E-stop causes disarm and stop.

### 9.3 Protect the primary athlete

The current corridor gate skips the primary by design. Add a separate target policy before pose-guided firing:

- prohibit head, face, neck, groin, and other disallowed body regions;
- enforce minimum range and speed/energy limits;
- prefer a **catch envelope relative to the athlete** rather than impact at a joint;
- keep target points inside a validated reachable volume and outside the face/torso exclusion volume;
- block if the athlete is not in a ready stance or leaves the marked athlete zone.

This preserves pose-guided differentiation while producing football-relevant balls rather than treating the athlete as a geometric target.

### 9.4 Trajectory uncertainty

RPM-to-speed calibration is safety-critical. Until it exists, a single 10 m/s arc is not a trustworthy clearance model. The gate should eventually evaluate a swept family of trajectories covering:

- calibrated speed uncertainty;
- ball type/pressure and wheel warm-up;
- left/right RPM difference and spin;
- aiming and localization error;
- actuation delay and ball flight time;
- plausible secondary-person motion during that interval.

P0 may use a conservative physical exclusion zone and fixed low-energy presets. Do not enable broader autonomous firing merely by increasing the software corridor radius.

### 9.5 Safety state machine

Use one visible state machine:

```text
DISARMED -> PREFLIGHT -> READY -> ARMED -> FIRE_PENDING -> FIRED
     ^          |          |        |            |
     +----------+----------+--------+------------+
                      any fault/block
```

`ARMED` requires the physical enable, the coach's deliberate action, a valid preset, and a current primary. A clear result is valid for one immediate fire decision and is never cached.

## 10. Minimum Lovable Product

### 10.1 Keep

- one goalkeeper-oriented zone/reaction drill;
- one pose-guided catch-envelope validation drill;
- athlete selection with optional Face ID;
- active preflight and visible safety state;
- coach trigger and physical enable;
- shot-by-shot session record;
- left/right and low/high comparison;
- session history and simple trend view;
- clean stop/recovery and a one-page operating procedure.

### 10.2 Cut or defer

- generic `LEVEL`, `RATING`, and radar scores without validated definitions;
- required Face ID before every session;
- SMPL avatar in the pilot build;
- voice firing and auto-reload as product features;
- six-person firing;
- cloud accounts, calendars, team management, and PDF polish;
- new sports;
- ROS2, distributed services, and large geometry refactors;
- further webcam purchases.

Keep the legacy Tk application only as a rollback tool until the Tauri application reaches feature parity, then freeze it.

## 11. Metrics Coaches Can Use

Separate machine delivery from athlete performance.

### 11.1 Delivery metrics

- commanded versus measured zone;
- ball speed and uncertainty;
- placement error at the target/goal plane;
- repeatability by zone and speed preset;
- launch interval and successful cycle time;
- blocked, aborted, or mechanically failed shots.

### 11.2 Athlete metrics

- catch, parry, touch, miss, or invalid trial;
- movement-initiation time after launch;
- first-step direction and correctness;
- time to ball contact when observable;
- lateral reach/dive distance;
- recovery time to ready stance;
- results by left/right and low/mid/high zones;
- within-session consistency and fatigue trend.

Use within-athlete trends before normative scores. Goalkeeper research supports side- and height-specific reaction/action testing and the importance of lateral push-off mechanics; it does not justify the current synthetic rating cards.

## 12. Commercial and Privacy Gates

### 12.1 Model licensing

Treat licensing as a P0 business decision, not post-pilot cleanup.

- Obtain an Ultralytics enterprise quote and compare it with the engineering cost of replacement.
- The MMPose framework is Apache-2.0, but a pose swap alone does not remove the ball detector's Ultralytics dependency.
- If replacing Ultralytics, retrain both the pose and ball paths using a permissively licensed framework/architecture and audit checkpoint/dataset terms.
- Remove SMPL from the pilot build unless a commercial license is obtained.
- Create a machine-readable inventory of code licenses, model licenses, weight provenance, and dataset rights.

References:

- Ultralytics licensing: https://www.ultralytics.com/license
- MMPose repository/license: https://github.com/open-mmlab/mmpose
- SMPL model license: https://smpl.is.tue.mpg.de/modellicense.html

### 12.2 Biometric and video data

Face embeddings remain biometric personal data even when no source images are stored. For an academy pilot, especially with minors:

- obtain confirmable consent from the athlete or legal representative;
- state purpose, data list, retention period, transfer policy, and deletion process;
- make Face ID optional;
- provide deletion from the Tauri athlete screen;
- store the database in Kazakhstan and keep it local by default;
- avoid names in recording filenames and safety logs;
- define retention for embeddings, session video, and derived metrics separately;
- document access and deletion events.

Reference: Kazakhstan Law on Personal Data and their Protection, including consent and local database storage requirements: https://adilet.zan.kz/eng/docs/Z1300000094

## 13. Prioritized Roadmap

### P0 — Evidence and safety foundation (next 3–5 working days)

1. Tag/freeze the current working demonstration and preserve a rollback launcher.
2. Map and tape the garage: launcher, athlete zone, catch/goal plane, coach zone, no-go corridor, and backstop.
3. Calibrate RPM to exit speed across the intended low-energy range with repeated shots, ball-condition notes, and uncertainty bands.
4. Measure end-to-end placement at the target plane; stop using localization precision as shot accuracy.
5. Enable a unique session ID and default-on `EventLogger` output for every desktop-started run.
6. Build the deterministic JSONL-to-session-summary aggregator and connect the Tauri Sessions/Shots views to real files.
7. Correct desktop readiness so failures are unknown/blocked, not static green.
8. Run 10 cold-start/stop cycles and log camera-open time, first-pose time, forced kills, orphan processes, and recovery.

**P0 exit:** one 10-shot zone session starts, runs, stops, and produces a complete honest report with measured delivery data.

### P1 — Vision validation and coach workflow (1–2 weeks)

1. Record the multi-person scenario matrix and annotate primary identity and visibility.
2. Add tracker metrics and tune thresholds from recorded evidence.
3. Replace arena Face ID round-robin with quality-ranked C920 routing.
4. Implement anchor enrollment plus arena enrichment and coverage/quality gates.
5. Replace the current guided UI with athlete -> drill -> preflight -> live -> review.
6. Add allowlisted launch profiles, explicit supervisor state, app-close cleanup, and Tauri backend/frontend tests.
7. Demonstrate all multi-person safety intrusions aim-only; keep actuation disabled.

**P1 exit:** 30 staged tracker/safety trials meet the garage acceptance gate, and a nontechnical coach can run the zone drill from one screen.

### P2 — Controlled pose-guided firing (2–4 weeks)

1. Install and verify hardwired E-stop and hold-to-run/keyed enable.
2. Add primary-athlete target policy and pose-relative catch envelopes.
3. Extend clearance from one nominal arc to a conservative trajectory/occupancy envelope.
4. Consolidate serial hardware ownership into one launcher process.
5. Validate first against fixtures/dummies and aim-only human scenarios, then adult low-energy supervised trials.
6. Perform a documented hazard review and failure-injection test.

**P2 exit:** controlled single-athlete pose-guided trials have zero uncommanded shots, every staged fault disarms, and placement/safety results are documented.

### P3 — Academy pilot preparation (4–8 weeks, procurement-dependent)

1. Resolve Ultralytics/SMPL commercial licensing or complete replacements.
2. Prepare consent, retention, operating, incident, maintenance, and emergency procedures.
3. Use GigE global-shutter hardware only after software acceptance and budget approval; recalibrate the entire rig after the swap.
4. Run a coach-observation session in the garage and revise the workflow from their feedback.
5. Offer FC Kairat one goalkeeper drill, not the full research platform.
6. Define the pilot as supervised, time-limited, and instrumented with agreed success criteria.

**P3 exit:** a coach can run the approved drill, the system creates useful reports, commercial rights are clear, and the installation has documented safety ownership.

## 14. Acceptance Dashboard

Track these before adding features:

| Area | Garage gate |
|---|---|
| Reliability | 20 consecutive complete sessions without a hang, orphan, or lost report |
| Startup | Required cameras and first valid pose become ready within a recorded, repeatable bound |
| Shutdown | Clean stop succeeds; forced-kill rate is visible and trends to zero |
| Logging | Every attempted shot has target, aim, launch/block, outcome, and session linkage |
| Delivery | At least 8/10 shots land in the declared target zone for each enabled preset |
| Tracking | Zero unintended primary switches in 30 staged crossing/occlusion trials |
| Safety | 30/30 staged intrusions block; primary change and stale telemetry always disarm |
| Face ID | Zero false labels in controlled negatives; unknown is allowed and measured |
| UX | A coach can start and finish a session from a one-page instruction without terminal use |

Absolute timing and placement thresholds should be set from P0 measurements and coach feedback rather than invented in advance.

## 15. Immediate Work Order

The next implementation sequence is:

1. RPM/speed and placement calibration.
2. Default-on session logging and real session summaries.
3. Garage reliability baseline and active preflight.
4. Multi-person recorded validation.
5. Face enrollment/recognition quality routing.
6. Coach-first Tauri flow and lifecycle hardening.
7. Hardware enable/E-stop and pose-guided firing validation.
8. Commercial-license resolution and academy pilot packaging.

This order protects the working demo, leaves geometry untouched, and turns each week into evidence that can be shown to a coach, professor, or investor.

## 16. Implementation Planning Boundary

This is a master product design, not one monolithic implementation ticket. Execute it through separate reviewed plans:

1. **P0A — Garage calibration and reliability protocol:** RPM/speed, target-plane placement, mapped safety zones, and cold-start/stop baseline.
2. **P0B — Session evidence pipeline:** default-on event logging, deterministic aggregation, active readiness, and real Tauri Sessions/Shots views.
3. **P1A — Multi-person validation harness:** recorded fixtures, annotations, metrics, threshold reports, and aim-only safety trials.
4. **P1B — Athlete identity and coach UX:** anchor/enrichment enrollment, quality-ranked recognition, athlete administration, and coach session flow.
5. **P2 — Controlled pose-guided operation:** hardware enable/E-stop, primary target policy, uncertainty envelope, single launcher owner, and supervised acceptance.
6. **P3 — Pilot packaging:** licensing, consent/retention, operating procedures, coach trial, and installation acceptance.

The next implementation plan after this design is approved should cover **P0A only**. P0B can run next without waiting for P1/P2, but it should consume the measurement fields established by P0A.
