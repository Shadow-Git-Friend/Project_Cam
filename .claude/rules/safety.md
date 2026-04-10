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

## Known Hazards
- `set` beyond ±30 → ESP32 reboot (mitigated by Python-side clamp)
- Horizontal stepper backlash on small `set→0→set` sequences (no movement until threshold exceeded)
- Ball exit velocity at 800 RPM uncalibrated — pitch accuracy degrades at higher RPMs (ballistic solver assumes fixed 10 m/s)
