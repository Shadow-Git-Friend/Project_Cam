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

## Do Not Auto-Read
- `venv/`
- Large raw outputs and captures
- Old archives unless needed for a specific task
- `*.pt`, `*.engine` model binaries

## Projector goal-game fix sequence (2026-05-29)
Root cause of the goal game barely scoring is software, not broken calibration (see `.claude/rules/geometry.md`). Fix order, geometry-protected functions untouched:
1. **Phase 0 (prove first):** static-ball validator — triangulate a ball seen by ≥2 cams with correct pairing (normalized obs + `[R|t]`), gate **< 25 px**. Confirms calibration is healthy before changing anything.
2. **Phase 1:** one-line fix in `proxiball_3d-main/projector/goal_target_game_multicam.py` — `proj_mats[cam] = K @ e["P"]` → `proj_mats[cam] = e["P"]`. Gate: debug-log `tri_reproj_err_px` drops ~1400 → <25 px.
3. **Phase 2:** rewire hit detection from per-cam wall-projection consensus to **3D triangulation → KF → X=6230 plane-crossing → zone**; keep consensus as fallback; **exclude camSouth from wall voting** (keep it in 3D). camSouth does NOT move.
4. **Phase 3:** re-shoot `homography.json` with projector locked at **1920×1080** (current file says proj_h=1200 = the monitor's height → display-only grid misalignment).
5. **Phase 4:** acceptance — reproj <25 px, `no-consensus` drops, real shots register; replay the `--debug-log-jsonl`.

## Camera swap → mandatory recalibration (2026-05-29)
- Any camera replacement (e.g. global-shutter upgrade) = new sensor + new lens → **regenerate intrinsics at runtime resolution, then extrinsics, then projector homography**, and pass the static-ball <25 px gate before trusting geometry. Mount new cameras as close to the current calibrated XYZ positions as possible (keep geometry; camSouth stays).

## When the User Hits an Issue
- Diagnose root cause before bypassing (e.g., port held by zombie → find PID, don't blindly retry)
- Filter problems (MMMM noise, boot output, RPM spam) → add filter, don't disable serial reads
- Hangs on `readline()` → confirm timeout is set AND use background thread, not bounded loops
