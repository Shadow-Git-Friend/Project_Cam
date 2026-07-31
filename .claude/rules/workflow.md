# Workflow Rules

## Read-First Strategy
- Always read the relevant script/config before proposing changes
- Never modify code you haven't read in the current session
- For BLM/firmware work: read `control_12_full.ino` to understand state machine before changing serial logic

## Change Process
- Plan before coding; propose approach and get approval for non-trivial changes
- Prefer incremental, testable steps with rollback paths
- Report assumptions, risks, and validation checks
- When firmware version changes (e.g., control_11 → control_12), update ALL Python serial scripts in lockstep (baud, command format, limit logic)

## Pose / Vision Testing Order
1. Dry-run / offline first (`process_4cam_to_3d.py` with recorded clips)
2. Ablation / evaluation on recorded sequences (`record_test_sequence.py` → `ablation_ema_adaptive.py` for pose; `ball_detection_analyzer.py` for ball conf/imgsz sweeps — accepts `mosaic2d_*.mp4` directly via `--mosaic`)
3. Live viewer without BLM (visual verification — `run_live_parallel_yolopose.sh`)
4. Live viewer + BLM aim overlay, no actuation (`run_live_blm.sh` with `--demo-blm`)

## BLM Hardware Testing Order (S0–S4 + Integrated)
S0–S4 already PASSED 2026-04-09 — re-run only after firmware/hardware changes.
1. **S0 — Serial connectivity**: `blm_interactive.py`, send `info`, verify response @ 921600 baud
2. **S1 — Manual commands**: `set 10 10 0 0`, `center`, `jv500`, `jh500`, verify physical movement
3. **S2 — Live aim-only**: `run_live_blm.sh` (Terminal 1) + `live_aim_test.py` (Terminal 2), aim at joints with `--no-shoot-enabled`, verify launcher tracks pose
4. **S3 — RPM gate**: spin wheels at 300 RPM, send `shoot`, verify firmware blocks; then 800 RPM, observe but do not shoot
5. **S4 — Controlled fire**: low pitch (15°), moderate RPM (500), single shot, observe trajectory; escalate
6. **Integrated**: full reload→aim→shoot cycle on chosen joint

## BLM Tools (current)
- `Parallel_working/run_live_blm.sh` — combined viewer (yolopose + Kalman + UDP) + BLM demo overlay
- `garage_lab_combined/scripts/live_aim_test.py` — interactive aim/reload/shoot with safety gates, background `SerialReader` thread
- `garage_lab_combined/scripts/blm_follow.py` — continuous follow mode, BLM tracks chosen joint live (aim-only by default), hot-swap target by typing
- `garage_lab_combined/scripts/blm_interactive.py` — raw serial terminal for ESP32, filters boot noise + telemetry
- `garage_lab_combined/scripts/launcher_runtime_from_udp.py` — production launcher runtime (UDP-driven)
- `garage_lab_combined/scripts/manual_aim_test.py` — non-interactive aim sweep

All five serial scripts use **baud 921600** as of 2026-04-09. Do not introduce new serial code without matching this.

## Serial Connection Pattern (mandatory)
- Use background reader thread (`SerialReader` in `live_aim_test.py`, `reader_thread` in `blm_interactive.py`) — never block on `ser.readline()` from main thread
- Always `time.sleep(2)` after `serial.Serial(...)` (ESP32 reset on DTR), then `ser.reset_input_buffer()`
- Apply output filters (see safety.md "Output Filtering")
- On exit: `stop` → `center` → close (KeyboardInterrupt-safe)

## Git Hygiene
- Commit with clear, descriptive messages
- Keep `Parallel_working/` changes in separate commits from `garage_lab_combined/`
- Keep firmware (`control_*_full.ino`) commits separate from Python script updates that follow
- Never force-push without explicit approval

## Thesis Documentation Files
- `new_complete.md` — full pipeline + per-script reference (math, CLI flags, classes, functions)
- `thesis_engineering_chapter.md` — engineering chapter draft (chassis/electronics/firmware FSM/comm/safety/integration/ECE-curriculum map)
- `thesis_defense_qa.md` — defense Q&A prep pack (ECE panel + PhD CV examiner)
- `thesis_draft.md` — pre-existing draft (do not touch unless asked)
- `thesis_report_bachelors.md`, `yessimkhan_thesis.md` — reference summaries (read-only)
- When thesis content changes, update the relevant .md and the "Documentation Files" section in CLAUDE.md

## Recording 3D Arena Videos
- Use `./Parallel_working/run_record_3d.sh` for combined 3D + 2D mosaic capture
- Always stop with `q` in the cv2 window or single Ctrl+C — never SIGKILL (unplayable MP4)
- If an old recording shows "moov atom not found" in ffmpeg, it cannot be recovered — re-record cleanly

## Folder Boundaries
- `garage_lab_combined/` — production runtime (live viewer, launcher, BLM scripts)
- `Parallel_working/` — perf experiments, isolated, do not merge to production without approval
- `arena_fixed/` — owns Y-axis fix and current extrinsics (do not override)
- `archive/` — historical, read-only unless explicitly needed
- `/home/hanush/Desktop/Aldiyar/` — colleague's joint-angle project (separate, has its own copy of needed assets)
- `project-cam-desktop/` — native desktop Control Center (Tauri 2 + React). Spawns the pipeline/face scripts; never touches BLM hardware directly. See "Desktop Control Center" below.

## Do Not Auto-Read
- `venv/`
- Large raw outputs and captures
- Old archives unless needed for a specific task
- `*.pt`, `*.engine` model binaries
- `project-cam-desktop/node_modules/` and `project-cam-desktop/src-tauri/target/` (build output)

## Projector goal-game fix sequence (2026-05-29)
Root cause of the goal game barely scoring is software, not broken calibration (see `.claude/rules/geometry.md`). Fix order, geometry-protected functions untouched:
1. **Phase 0 (prove first):** static-ball validator — triangulate a ball seen by ≥2 cams with correct pairing (normalized obs + `[R|t]`), gate **< 25 px**. Confirms calibration is healthy before changing anything.
2. **Phase 1:** one-line fix in `proxiball_3d-main/projector/goal_target_game_multicam.py` — `proj_mats[cam] = K @ e["P"]` → `proj_mats[cam] = e["P"]`. Gate: debug-log `tri_reproj_err_px` drops ~1400 → <25 px.
3. **Phase 2:** rewire hit detection from per-cam wall-projection consensus to **3D triangulation → KF → X=6230 plane-crossing → zone**; keep consensus as fallback; **exclude camSouth from wall voting** (keep it in 3D). camSouth does NOT move.
4. **Phase 3:** re-shoot `homography.json` with projector locked at **1920×1080** (current file says proj_h=1200 = the monitor's height → display-only grid misalignment).
5. **Phase 4:** acceptance — reproj <25 px, `no-consensus` drops, real shots register; replay the `--debug-log-jsonl`.

## Camera swap → mandatory recalibration (2026-05-29)
- Any camera replacement (e.g. global-shutter upgrade) = new sensor + new lens → **regenerate intrinsics at runtime resolution, then extrinsics, then projector homography**, and pass the static-ball <25 px gate before trusting geometry. Mount new cameras as close to the current calibrated XYZ positions as possible (keep geometry; camSouth stays).

## Evaluating a third-party model or SDK (2026-07-30)
New releases arrive framed as solutions to problems we may not have. Check in this order and stop at the first failure — it saves days:
1. **Which layer is it actually?** Name the file in this repo it would replace. A tracker (MV3DT → `src/project_cam/tracking/multi_person.py`) is not a pose estimator; a motion *generator* (ARDY) cannot see our cameras at all; a detector cannot fix a geometric occlusion. Most announcements do not state the layer, and the wrong layer is the most common reason an exciting release is irrelevant.
2. **Throughput against our real budget** — 6 cameras × 15 fps = 90 inferences/s on an 11 GB 2080 Ti already running the ball and pose engines. See perf.md "Third-party model throughput math". Quantisation does not close an order of magnitude.
3. **Licence has THREE layers and they routinely differ — code, weights, training data.** Check all three; the third is invisible in the repository badge and is where every trap so far has been.
   - *Code:* ARDY is Apache-2.0, LocateAnything-3B is Apache-2.0 — tells you nothing on its own.
   - *Weights:* ARDY ships **NVIDIA Open Model** (commercial-permitting); LocateAnything-3B ships the **NVIDIA License** (non-commercial). Same code licence, opposite outcome.
   - *Training data:* **this is the one that bit us.** MMPose is Apache-2.0, but every published RTMPose checkpoint is `pt-aic-coco` — pretrained on **AI Challenger**, which is research-only — so the backend we had written down as our AGPL escape was not clean. Known non-commercial datasets to grep for in a checkpoint name or config: **AI Challenger (`aic`), MPII, CrowdPose, Halpe, and any `body7`/`body8` merged set**. COCO (CC-BY-4.0) and Objects365 are commercially usable.
   - **Read the training config, not the model-zoo table.** `rtmo-s_8xb32-600e_coco-640x640.py` was settled by reading `train_dataloader` (`CocoDataset`/`person_keypoints_train2017`) and the backbone `init_cfg` (`yolox_s_..._coco`, MMDetection Apache-2.0). The metafile for the same model lists `Dataset: CrowdPose` as an *evaluation* row, which reads like contamination and is not.
   - Also check for a **transitive SMPL dependency** — anything reintroducing SMPL undoes a decision already taken for the pilot.
   - The alternative to auditing three layers yourself is a vendor that warrants them: NVIDIA TAO models state "ready for commercial use" explicitly (PeopleNet), which is worth more than a permissive badge on an unwarranted checkpoint.
4. **Read the licence in the repo, never from the announcement.** Blog posts say "open source"; the weights file says otherwise. And re-check relicensings in both directions — DINOv2 moved *from* CC-BY-NC-4.0 *to* Apache-2.0 in Aug 2023 (which is what makes RF-DETR's Apache claim hold), while SAM went the other way, from SAM 1's Apache-2.0 to a custom Meta licence for SAM 2/3.
5. **What accuracy does it claim, and against what?** "No numbers stated" (AutoMagicCalib) means it is a bake-off candidate, never a plan. When a bake-off happens, gate it on the SAME criterion we already trust — for calibration that is static-ball reprojection < 25 px plus recovered positions against measured mounts.
6. **Host requirements against this box:** Ubuntu 22.04, kernel 6.8, driver **580.173.02**, CUDA 11.5 toolchain, 2080 Ti (Turing) 11 GB + Quadro P400 2 GB. Read the requirement precisely — DeepStream 9.1 wants driver ≥580 (we pass) and Ubuntu 24.04 (we do not, so container, which uses the host driver anyway). A version number recorded wrong becomes a phantom blocker; correct the log when it happens.
7. **Then ask what it would displace.** Adopting nothing is the default and usually right. A **benchmark** against a component of ours is often the whole value of a release — it produces a number we can show a stakeholder without taking on a dependency.

## When the User Hits an Issue
- Diagnose root cause before bypassing (e.g., port held by zombie → find PID, don't blindly retry)
- Filter problems (MMMM noise, boot output, RPM spam) → add filter, don't disable serial reads
- Hangs on `readline()` → confirm timeout is set AND use background thread, not bounded loops

## Reproducing public CI failures (2026-06-30, learned the hard way)
When GitHub Actions is red but local is green, do NOT trust the working tree — reproduce the runner:
1. **Fresh `git clone` of the exact pushed commit** into a temp dir (CI checks out only committed files). The working tree can contain gitignored fixtures/configs that exist on disk but were never committed.
2. **Clean `python3.11 -m venv` with `--no-cache-dir`** install matching `ci.yml` exactly (the pip cache can serve older, working wheels while the runner resolves newer ones).
3. **Run the bare `pytest` console script, NOT `python -m pytest`.** `python -m pytest` silently prepends the CWD to `sys.path`; bare `pytest` does not. CI uses bare `pytest`, so `from services.api.app.main import app` (repo-root package outside `src/`) fails collection (exit code 2) on the runner but passes under `-m` locally. Fix was `pythonpath = ["src", "."]` in `pyproject [tool.pytest.ini_options]`.
- **pytest exit codes:** `1` = test assertion failures; `2` = collection/import error or interrupted; `5` = no tests collected. Exit 2 means look at module-level imports, not test bodies.
- **Blanket `*.json` in `.gitignore`** silently dropped every `tests/fixtures/*.json` (and `docs/openapi.json`, the Grafana dashboard) from all checkouts → fresh-checkout `FileNotFoundError`. Curated JSON needs explicit `!` negations; generated/output JSON stays ignored.
- Actions logs need repo auth (no token on this box; push is SSH-only) — diagnose by local reproduction or a diagnostic CI commit, not by reading the runner log.
- **Never merge a fix to `main` without first seeing the branch go green on the real runner** — local green is necessary, not sufficient.

## Desktop Control Center (project-cam-desktop/, 2026-07-14)
- Tauri 2 + React app that spawns the pipeline / face scripts and streams their output to a MISSION LOG. It **NEVER actuates the BLM directly** — START TRAINING launches the view-only cinematic viewer (UDP target broadcast only); only `garage_lab_combined/scripts/live_aim_test.py` (Terminal 2) touches hardware, with the S0–S4 gates.
- **Launch:** the `Project Cam Control Center` desktop icon or `./project-cam-desktop/run.sh` — both run the COMPILED release binary (opens <1 s). Browser-only UI preview: `cd project-cam-desktop && npm run dev`. First-time system deps: `sudo ./project-cam-desktop/install-system-deps.sh` (WebKitGTK etc.).
- **The `.desktop` icon `Exec`s the compiled binary directly, so a stale binary silently ships stale behaviour** (bitten 2026-07-29: the icon ran a 16 July build while P0B sources were 29 July, hiding the entire session-evidence layer). After any `src/` or `src-tauri/` change, `rebuild.sh` then verify: `ls -l src-tauri/target/release/project-cam` must be NEWER than the newest source, and `strings` on it should show symbols you just added/removed.
- **One bounded evidence reader only.** All desktop evidence goes through `evidence::load_session_evidence` -> `read_jsonl_tail` (byte-capped, typed `SessionRow`/`ShotRow`, per-source rejection accounting). Do not add a view-specific command that reads a log with `read_to_string` and hands raw JSONL to the UI — that was `training_sessions`, removed 2026-07-29.
- **Any cap on evidence discovery must traverse NEWEST FIRST.** Both scan loops `break` at `MAX_SOURCE_FILES`, and session ids are fixed-width timestamps, so an ascending sort keeps the oldest and silently drops every newer session. Sorting/truncating the rows afterwards cannot recover data that was never read (`directory_entries_newest_first`).
- **After editing `src/` (UI) or `src-tauri/` (Rust), run `./project-cam-desktop/rebuild.sh`** — the icon/run.sh launch the compiled binary, NOT live code. Editing a spawned Python script (`face_enroll.py`, run scripts) needs NO rebuild (spawned fresh each click).
- **Named launch profiles are the launch boundary (2026-07-30, replaces generic `spawn_process`).** The frontend names a `profile_id` and supplies semantic parameters; `src-tauri/src/launch_profiles.rs` resolves program, argv and cwd. There is no way to express a program path, an argument vector or a working directory from the UI — that is the entire point. `ResolvedLaunch` keeps its fields private so nothing can substitute a program after resolution. Contract-tested in `tests/test_desktop_launch_profiles.py`.
  - **Every new profile must be a struct variant, never a unit variant.** `deny_unknown_fields` is NOT applied to unit variants of an internally-tagged serde enum, so `{"profile_id":"free_view_usb6","program":"/bin/sh"}` would be accepted with the extra key silently dropped. Empty struct variants (`FreeViewUsb6 {}`) make it a hard error. This is the enforcement, not the type name.
  - **Paths are backend-owned.** `AppPaths::discover()` derives the repo root from `CARGO_MANIFEST_DIR` and verifies `REPO_SENTINELS` exist before trusting it; `script()` canonicalizes a repo-relative path FIRST and then checks containment, so a symlink pointing outside the repo is caught by the containment check rather than by textual path inspection. `REPO_ROOT`/`PYTHON` no longer live in `src/data.ts`.
- **Explicit supervisor states (LC-1, 2026-07-30).** `ProcessState` in `main.rs`: `Idle / Starting / Running / Stopping / Faulted`, advanced by `ProcessFact` transitions, with `blocks_launch()` = `Starting | Running | Stopping` as the single interlock (one running child at a time, mirrors the Python control center). Two deliberate asymmetries to preserve: `Exited(0)` while already `Faulted` stays `Faulted` (a clean exit does not retroactively excuse a failed launch), and `StopFailed` while `Stopping` returns to `Running` — **a stop that failed must never read as stopped.** STOP still sends graduated SIGINT→SIGTERM→SIGKILL to the child's process group; `CloseRequested`/`ExitRequested` route through `terminate_process_group` so closing the window cannot orphan a viewer.
- Two desktop apps now exist: this Tauri one (good UI + working commands) and the legacy `desktop/arena_control_center.py` (Tkinter). The old Python `.desktop` launchers were removed; only the Tauri shortcut remains (WM_CLASS `project-cam`).
- **Scroll + name flow (2026-07-15):** only the MISSION LOG box scrolls — CONTROL is `h-full overflow-hidden` and auto-follow sets the log container's `scrollTop` (gated on already-at-bottom). Never use `scrollIntoView` for log auto-follow: it scrolls every scrollable ancestor and drags the whole page. The typed athlete name resolves case-insensitively to the gallery's canonical spelling before `--primary-person`/`--name` (no case-variant duplicate identities); enrolled names render as tap-to-fill chips. Athlete-name text in cv2 overlays must go through `project_cam.viz.text` (`put_text`/`text_size`) — plain `cv2.putText` draws one `?` per non-ASCII UTF-8 byte (see perf.md "Unicode name labels").

## Training drills (TRAINING view, 2026-07-16)
- **Stack (mirrors the validated reaction_arena pattern):** `src/project_cam/training/drills.py` (pure stdlib state machines, clock-injected, unit-tested in `tests/test_training_drills.py`) ← `garage_lab_combined/scripts/training_drill.py` (UDP :5005 consumer + cv2 scoreboard; VIEW-ONLY, no serial imports) ← `Parallel_working/run_training_drill.sh` (starts the mirrored-skeleton viewer in background WITH `--udp-target-*` flags appended via its `"$@"` passthrough + the drill board in foreground; one process group so the desktop STOP reaps both; viewer gets a smaller `--viz-width 960` so the board is the hero window).
- **Catalog — 9 drills (ids are contract-tested against `drills.ts` in `tests/test_desktop_training_contracts.py`):** field = `balance` (FIFA 11+ single-leg stance, pelvis sway RMS mm), `shuttle` (garage-scaled 5-10-5, sub-frame line-crossing splits), `line_hops` (FIFA 11+ lateral jumps, hysteresis-counted crossings); GK = `gk_save` (four-corner reaction matrix; HIGH/LOW bands self-calibrate from the keeper's own shoulder/hip height at set; enforced save→recover→set re-arm; random cue delay), `gk_updown` (down-up conditioning, per-rep recovery timing, thresholds from standing pelvis height); projector = `reaction_zones` (LEFT/CENTER/RIGHT zone reaction, reuses the validated `zone_of`); added 2026-07-30 = `cmj` (countermovement jump), `hop_symmetry` (single-leg hop Limb Symmetry Index), `reactive_cut` (cue-at-commitment change of direction, the one thing photocells structurally cannot measure).
- **Metric-honesty rules for any new drill** (these are why the catalog is credible, not decoration): report what the sensor measures, not the metric a coach expects — `cmj` reports `pelvis_rise_mm` against the athlete's own standing height, never "jump height" and never a force-plate conversion. Show a screening metric together with the raw values it hides — `hop_symmetry` shows the LSI **and both absolute distances**, and labels itself screening, not clearance, because symmetry can be satisfied with both limbs weak. Record failure modes rather than discarding them — a wrong-way commit in `reactive_cut` is an `error` (error rate under pressure is the measure), while a tracking loss is `void` and does not consume a rep. Separate what trains differently — `decision_s` (cue → first committed lateral movement) apart from `execution_s`.
- **Constructors must refuse impossible protocols, not clamp them.** `reactive_cut` raises when `gate_mm >= arena_y_mm / 2`; `validate_workload` rejects out-of-range workloads before the drill is built (`--rounds 0` used to silently run 4). Any parameter that defines the protocol enters `protocol_parameters_fingerprint`.
- **The walk-back lesson (2026-07-30):** `hop_symmetry` measured hop distance from wherever the athlete last stood, so walking back to the line registered as a hop of the other limb — both limbs came out equal and the LSI was structurally incapable of ever finding asymmetry. It passed code review and died on the first realistic smoke run. **Any drill that measures displacement needs a fixed reference and an arming gate that requires returning to it** (`start_x` + `start_band_mm`). Run a scripted athlete trace through every new state machine and read the numbers, not just the states.
- **Design rules learned:** every drill must tolerate tracking dropouts (arming requires POSITIVE presence; armed states must NOT reset on a missed packet — only on positive evidence of leaving); countdowns loop until the athlete is actually tracked (autostart-safe when the operator is the athlete); all thresholds are constructor params so machines stay unit-testable; timing honesty — quote ±0.07 s resolution at 15 Hz, never combine-official times.
- **Logs:** per-round events `garage_lab_combined/output/training_logs/<drill>_<ts>.jsonl`, session summary `<..>_summary.json`, rolling `sessions_index.jsonl` (appended once per session; the Rust `training_sessions` command tails it for the RECENT SESSIONS panel — read-only, [] when absent). Event lines also print to stdout → MISSION LOG.
- Athlete name state is lifted to `App.tsx` and shared CONTROL↔TRAINING; TRAINING passes `--face-id` to the wrapper only when the name canonicalizes to an enrolled gallery entry.
- **Pose quality for drills (2026-07-16, after two live sessions):** the wrapper appends an anti-lag/no-avatar viewer profile — `--no-avatar-body --no-avatar-markers` (SMPL capsule mangles on one-leg poses), `--max-frame-age-ms 250`, `--ema-alpha 0.65`, `--kalman-measured-dt`, `--pose-latency-comp-ms 120`, `PROJECT_CAM_FPS` default 10 (drop to 5 if a camera fails to open) — see perf.md "Training-drill viewer profile". Leg label integrity = chain L/R relabeling (perf.md) + geometric pair split `--pose-lr-split` (geometry.md "Geometric L/R pair split"); live-tune `--pose-lr-split-trigger-px` 8–16. BalanceDrill itself debounces (median dz 0.35 s, touch-down needs ≥0.4 s raised). cv2 board strings must stay ASCII (`·` renders as `??`); athlete names go through `project_cam.viz.text`.

## Garage demonstrator -> academy pilot (2026-07-15)
- Product direction: one coach-facing system with two honestly labelled modes — **Operational Zone Drill** (reliability anchor) and **Pose-Guided Validation** (aim-only until live gates pass). Full design: `docs/superpowers/specs/2026-07-15-garage-pilot-product-design.md`.
- Immediate work order: RPM/speed + placement calibration -> default-on session logging/summary -> cold-start/stop reliability baseline -> recorded multi-person validation -> Face ID quality routing -> coach-first Tauri flow -> hardware enable/E-stop + controlled pose-guided trials -> commercial-license/pilot package.
- Do not use 4.4 mm reconstruction repeatability as end-to-end shot accuracy. Report localization, exit-speed, aiming, and target-plane placement separately.
- Preserve the current viewer and protected geometry. Add small manifests, structured health/events, and adapters around it; no ROS2, broker, or large refactor for the garage phase.
- Garage firing: any secondary person blocks during the first operational phase. Multi-person corridor behavior is demonstrated aim-only until live acceptance passes. A clear result is one-shot and never cached.
- The Tauri production path must use named allowlisted launch profiles, active readiness, explicit process states, and app-close containment. Static green fallback readiness is not acceptable for actuation decisions.
- Face enrollment is athlete administration, not a required per-session step. Use manual athlete selection as the reliable fallback; Face ID may label a stable track but never select firing authority.
