# BLM Safety Rules

## Core Principle
This project controls a physical ball launching machine. Incorrect commands can cause injury or equipment damage. **As of 2026-04-09, S0-S4 + integrated live test PASSED — controlled fire is authorized under operator supervision only.**

## Firmware Version (control_12_full.ino, current)
- **Serial baud: 921600** (was 115200 in control_11) — all Python serial scripts must match
- **Limit switches: INPUT_PULLUP, triggered on LOW** (was PULLDOWN+HIGH) — inverted polarity vs control_11
- Pusher DRV8825 enable: HIGH=rest/cool, LOW=move (auto-managed by firmware)
- Telemetry (`L:xxx R:xxx`) suppressed during pusher motion (STATE != IDLE)
- New live tuning commands (no reflash): `jsset<val>`, `jfspeedset<val>`, `jfaccelset<val>`
- New manual jog: `jf<steps>` (pusher), `js<0-180>` (servo angle)
- `info` extended with limit switch states + live config
- Strict command matching via `cmd.toLowerCase()` — exact tokens only

## Safety Gates (enforced by launcher_runtime_from_udp.py + live_aim_test.py)
- Zone check: target must be within valid arena zone (from GT CSV bounds)
- Confidence gate: minimum cameras (`--udp-target-cams-min 3`) and confidence (`--udp-target-conf-min 0.45`)
- Stability gate: noisy/jittering targets rejected as LOW_CONFIDENCE
- Angle clamp: pitch [0°, 30°], yaw [-30°, 30°] — Python clamps BEFORE sending (firmware crashes/reboots beyond ±30°)
- RPM gate: shoot blocked unless both flywheels ≥ 400 RPM (firmware-enforced)
- ESTOP: immediate `stop`, latched until `clear` issued
- `live_aim_test.py`: requires prior successful aim before shoot, requires typed "yes" (full word) to confirm fire

## Rules for Code Changes
- Never remove or weaken safety gates without explicit approval
- Never enable `--shoot-enabled` before completing BLM checklist stages S0-S4 (DONE 2026-04-09)
- Always test with `--no-shoot-enabled` and `--dry-run-log-jsonl` first when changing aim logic
- Never send `shoot` without prior successful `set` and RPM gate confirmation
- On any error/exception in launcher runtime: default to `stop` + `set 0 0 0 0`
- Python `set` command must clamp values to ±30 BEFORE sending to firmware

## ESTOP Behavior
- `estop` command → immediate `stop` → latch active → no further actuation
- Only `clear` command releases the latch
- Link loss (UDP timeout or serial disconnect) → automatic safe stop
- KeyboardInterrupt in `live_aim_test.py` and `blm_interactive.py` → `stop` + `center` + close

## Serial Protocol
- **Baud: 921600** (control_12)
- Aim: `set v h wl wr` — vertical, horizontal, wheelLeft RPM, wheelRight RPM
- Action: `shoot`, `reload`, `stop`, `center`, `setzero`
- Manual jog: `jv<steps>` (vertical), `jh<steps>` (horizontal), `jf<steps>` (pusher), `js<0-180>` (servo)
- Live tuning: `jsset<val>`, `jfspeedset<val>`, `jfaccelset<val>`
- Diagnostic: `info` (state, limits, live config)
- Always flush serial buffer after `stop` or `estop`
- Home position: `set 0 0 0 0` on startup and graceful exit

## Output Filtering (boot/noise resilience)
All scripts that read serial MUST filter:
- ESP32 boot ROM: lines starting with `ets `, `rst:`, `configsip:`, `clk_drv:`, `mode:`, `load:`, `entry`
- Baud-transition garbage: lines >20 chars with ≤2 unique characters (e.g., `MMMMMMM...`)
- RPM telemetry during interactive use: lines starting with `L:` containing ` R:`
- Deduplicate consecutive identical lines

## BLM Preflight Status (2026-04-09)
- **S0 PASS**: Serial /dev/ttyUSB0 @ 921600, dialout group
- **S1 PASS**: set/center/stop/info/jv/jh verified with physical movement
- **S2 PASS**: Live aim-only with cameras + correction model
- **S3 PASS**: RPM gate verified (shoot blocked below 400 RPM)
- **S4 PASS**: Controlled fire at 15°/20° pitch, 500/600/800 RPM
- **Integrated PASS**: pose→aim→fire on left_shoulder, right_knee, nose

## Camera hardware-sync trigger (planned, 2026-05-29)
- The planned global-shutter upgrade syncs cameras via a hardware trigger pulse from the ESP32. **This must NOT disturb BLM timing.** Generate the pulse on a dedicated pin via a hardware timer / LEDC / RMT peripheral — never with blocking `delay()` in the main loop, and never on a pin shared with stepper/serial/limit-switch logic.
- Camera trigger lines are opto-isolated; drive 3.3 V ESP32 GPIO → opto/level-shift → 4 camera Line0 inputs (rising edge, 30–60 Hz). Isolation keeps the industrial I/O domain off the ESP32 logic domain.
- Treat camera sync as a sideband peripheral clock. If adding it to `control_12_full.ino`, re-run S0–S2 to confirm serial/aim timing is unaffected before any S3/S4.

## Known Hazards
- `set` beyond ±30 → ESP32 reboot (mitigated by Python-side clamp)
- Horizontal stepper backlash on small `set→0→set` sequences (no movement until threshold exceeded)
- Ball exit velocity at 800 RPM uncalibrated — pitch accuracy degrades at higher RPMs (ballistic solver assumes fixed 10 m/s)
- **Multi-person firing-line gate (implemented 2026-07-13, NOT live-commissioned):** the viewer now publishes `project_cam.firing_line.v1` all-person snapshots and the pose-driven launcher paths re-evaluate a fail-closed ballistic-corridor gate immediately before `shoot`. Missing/stale/malformed/ambiguous data, an unlocalized secondary, or a primary ID/epoch change blocks and disarms. Unit tests are green; this is not permission for multi-person firing. Keep multi-person actuation disabled until the staged live gates in `docs/superpowers/specs/2026-07-15-garage-pilot-product-design.md` pass.
- **Primary-person hazard remains separate:** the corridor gate deliberately ignores the primary athlete. Pose-guided firing additionally requires an approved target/catch-envelope policy, prohibited body regions, minimum range, and energy limits. Face ID labels are identification hints only — never a fire-authorization signal.
- **RPM→m/s calibration is safety-critical:** the current trajectory evaluator uses the commanded/assumed speed. Until speed and uncertainty are measured, use fixed low-energy presets plus a conservative physical exclusion zone; do not treat the nominal 10 m/s arc as commissioned clearance geometry.
  - **The measurement procedure is now written: `docs/protocols/2026-08-03-rpm-speed-measurement.md`** (roadmap A6). Two independent methods with unrelated failure modes, cross-checked at 10 % and never averaged; the shot matrix starts at 500 RPM, the lowest energy above the firmware gate; every shot is fired horizontally at a wall or net with nobody downrange.
  - **`fit_rmse_mps` is the deliverable, not a footnote.** A speed without its spread cannot inform a clearance margin. `scripts/fit_rpm_speed.py` now writes `n_shots` in every model branch, and reports the pooled within-RPM spread for the interpolating model — which otherwise passed exactly through its points and would have read as certainty.
  - **Known gap, deliberately open:** `evaluate_*` / `build_firing_line_safety_snapshot` in `src/project_cam/closed_loop/firing_line.py` take a **scalar `speed_mps`**. Once a model exists the corridor is still sampled at the point estimate while `±rmse` sits in a JSON file no safety code reads. The fix is to evaluate clearance over `[v−kσ, v+kσ]` — a widening of the corridor, never a narrowing — and it must land in the same review as the first real measurement. Do not add the parameter to safety code before there is a measured σ to feed it.
- **Garage firing policy (2026-07-15):** zone-drill firing is the reliability anchor; any detected secondary person blocks firing during the first operational phase. Demonstrate multi-person corridor selectivity aim-only. Every shot requires fresh clearance and deliberate operator enable; no autonomous repeated fire.
- **Desktop Control Center:** `project-cam-desktop/` remains orchestration/view/capture only and does not write launcher serial commands. Face enrollment only captures embeddings. Hardware actuation stays behind the launcher fire-control boundary and S0–S4 gates.
- **The desktop launch allowlist is now a structural safety property (2026-07-30), not a convention.** `spawn_process(program, args, cwd)` is gone: the frontend names a `profile_id` and the Rust resolver in `launch_profiles.rs` produces program/argv/cwd. **No profile actuates the launcher**, and the UI has no way to express one — adding an actuating profile would be a deliberate, reviewable change to that file, which is exactly the property we want. Two mechanisms must not be weakened: profiles are struct variants so `deny_unknown_fields` really rejects injected keys (serde does not apply it to unit variants), and `AppPaths::script()` canonicalizes before checking repo containment so a symlink cannot escape the checkout.
- **The supervisor state machine fails toward "not stopped" (2026-07-30).** In `main.rs`, `ProcessFact::StopFailed` while `Stopping` returns to `Running`, and `Exited(0)` while `Faulted` stays `Faulted`. Preserve both directions: a failed stop that displayed as `Idle` would invite a second launch against a live child, and a clean exit must not retroactively clear a failed launch. `blocks_launch()` (`Starting | Running | Stopping`) is the single interlock; app close routes through `terminate_process_group` so no viewer is orphaned holding cameras.
- **All 9 training drills are view-only by construction (2026-07-16, extended 2026-07-30):** the TRAINING view launches `run_training_drill.sh` = viewer (UDP joint broadcast) + `training_drill.py` scoreboard, both pure pose consumers with no serial code (contract-tested: no `--shoot-enabled`/`live_aim_test`/`/dev/ttyUSB` references allowed in the wrapper; the wrapper's `case` allowlist exits **exactly 2** on an unknown drill and never starts the viewer). This covers the projector drills (`reaction_zones`, `reactive_cut`) and the 2026-07-30 additions (`cmj`, `hop_symmetry`) — a projector cue is a light on a wall, not an actuator. No drill involves launcher fire; any future ball-served drill goes through the operator Terminal-2 path and the garage firing policy above, never through the desktop app.
- **Movement-drill hazard in a 6.23 × 3.05 m room (2026-07-30):** `reactive_cut`, `shuttle` and `line_hops` are near-maximal-effort with a deliberately unpredictable cue, so the athlete cannot plan a stopping distance. Two consequences. (1) The drills are scored on **zone entry** (`zone_of(...) == target`), not on reaching a wall — in `reactive_cut` the athlete stops ~1017 mm short of the wall by design, and `outer_centre_clearance = arena_y_mm / 6.0` raises rather than clamps if a geometry change would erase that margin. Never "improve" a drill by scoring proximity to a wall. (2) The 3.05 m width is shared between the athlete's movement envelope and any future firing corridor, so **a reactive movement drill and BLM delivery cannot occupy this room at the same time**. That is a physical constraint, not a software gate — no clearance evaluator makes it safe.
- **Face ID is not commercially licensable as shipped (2026-08-03), and the data-protection obligations are unimplemented.** Both models in the live path since 2026-07-12 are `blocked` in the registry at the **training-data** layer while their code and weights are permissive: YuNet (MIT) trains on WIDER FACE (CC BY-NC-ND 4.0), SFace (Apache-2.0) trains on CASIA-WebFace / VGGFace2 / MS-Celeb-1M (research-only, MS-Celeb-1M retracted). Separately and independently of the licence: there is **no consent record and no deletion path**. Enrollment can only be overwritten (`face_enroll.py --replace`); nothing removes one athlete's embeddings, session rows and video on request. Consent, separate retention windows for embeddings vs video vs derived metrics, and deletion are specified at `docs/superpowers/specs/2026-07-15-garage-pilot-product-design.md` lines 171/438/443 and are Block D of `docs/roadmap_2026-08_mvp.md`. **Do not run Face ID with academy athletes — least of all minors — before D1 and D2 land.** Manual athlete selection is the supported path meanwhile.
- **Medical-adjacent metrics must not read as clearance.** `hop_symmetry` computes the Limb Symmetry Index, which is used clinically as a return-to-play criterion. It is presented as **screening**, showing the index together with both absolute distances, because symmetry can be satisfied with both limbs weak and because fewer than half of young athletes reach the conventional 90%. Do not add a pass/fail badge, a "cleared" state, or a percentage compared against anything other than the athlete's own history. The same rule that keeps Face ID out of fire authorization keeps this system out of injury clearance.
