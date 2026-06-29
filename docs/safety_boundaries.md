# Safety Boundaries

This project controls a physical ball-launching machine (BLM). Safety is enforced
by **architecture**, not just convention: the only software path that can actuate
the launcher is the dedicated, safety-gated launcher runtime.

## What can and cannot fire

| Component | Can it send `shoot`? |
|---|---|
| `garage_lab_combined/scripts/launcher_runtime_from_udp.py` | Yes — gated |
| `garage_lab_combined/scripts/live_aim_test.py` / `blm_follow.py` | Yes — gated, operator-confirmed |
| **FastAPI service** (`services/api/...`) | **No** — no actuation path exists |
| **Edge stream demo** (`project_cam.streaming`) | **No** — BLM disabled by design |
| **Leg-raise mode** (`assessment.live_trainer.leg_raise_mode`) | **No** — analysis only |
| Live viewers (`Parallel_working/`) | **No** — they only triangulate + broadcast UDP |

The API enforces this in two visible ways: `/v1/system/info` reports
`"shooting_enabled": false`, and there is no route whose path contains `shoot` or
`fire` (asserted by `tests/test_api_health.py`). The streaming module exposes no
`shoot`/`fire` symbol (asserted by `tests/test_rtsp_source_config.py`) and its
config's `shoot_enabled` is a non-settable `False`.

## Safety gates in the launcher runtime

Enforced by [`safety_gates.py`](../src/project_cam/closed_loop/safety_gates.py) and
the launcher scripts:

- **Zone check** — target must be inside the valid arena zone.
- **Confidence gate** — `--udp-target-conf-min` (default 0.45).
- **Camera-count gate** — `--udp-target-cams-min` (default 3).
- **Stability gate** — jittering targets rejected as low-confidence.
- **Angle clamp** — pitch `[0°, 30°]`, yaw `[-30°, 30°]`, clamped in Python
  **before** sending (firmware reboots beyond ±30°).
- **RPM gate** — `shoot` blocked unless both flywheels ≥ 400 RPM (firmware-enforced).
- **ESTOP** — immediate `stop`, latched until `clear`. Link loss → automatic safe stop.

## Hardware test order (S0–S4)
S0 serial → S1 manual commands → S2 live aim-only → S3 RPM gate → S4 controlled
fire → integrated. S0–S4 passed 2026-04-09; re-run after any firmware/hardware
change. The 6-camera path is **aim-only** until its geometry is re-validated
(S2 first), and `--shoot-enabled` is never used on it before that.

## Rules for changes
- Never remove or weaken a safety gate without explicit approval.
- Never enable `--shoot-enabled` outside the launcher runtime, and never on the
  6-camera path before S2 re-validation.
- The API/edge/demo layers must remain physically incapable of firing.
- On any launcher error/exception: default to `stop` + `set 0 0 0 0`.
