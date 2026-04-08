# BLM Safety Rules

## Core Principle
This project controls a physical ball launching machine. Incorrect commands can cause injury or equipment damage.

## Safety Gates (enforced by launcher_runtime_from_udp.py)
- Zone check: target must be within valid arena zone (from GT CSV bounds)
- Confidence gate: minimum cameras and confidence threshold
- Stability gate: noisy/jittering targets rejected as LOW_CONFIDENCE
- Angle clamp: pitch/yaw clamped to firmware limits (+-30 deg)
- ESTOP: immediate `stop`, latched until `clear` issued

## Rules for Code Changes
- Never remove or weaken safety gates without explicit approval
- Never enable `--shoot-enabled` before completing BLM checklist stages S0-S4
- Always test with `--no-shoot-enabled` and `--dry-run-log-jsonl` first
- Never send `shoot` without prior successful `set` and RPM gate confirmation
- On any error/exception in launcher runtime: default to `stop` + `set 0 0 0 0`

## ESTOP Behavior
- `estop` command → immediate `stop` → latch active → no further actuation
- Only `clear` command releases the latch
- Link loss (UDP timeout or serial disconnect) → automatic safe stop

## Serial Protocol
- Commands: `set v h wl wr`, `shoot`, `reload`, `stop`, `center`, `setzero`
- Always flush serial buffer after `stop` or `estop`
- Home position: `set 0 0 0 0` on startup and graceful exit
