# `control_13` loop timing: diagnosis and fix

**Status: FIXED, 2026-08-13.** The `control_13` idle loop was 40.0 ms;
`control_14` is 2.8 ms, and the yaw axis now runs its configured profile —
694 steps in **585.8 ms** against the 37 000 ms it used to take. No diagnostic
firmware was ever flashed, and none was needed.

**Scope:** find why the yaw axis crawls. Diagnosis was carried out without
commanding any axis, flywheel, feeder, reload, arm or fire action; the two
yaw-only moves that verified the fix were each separately authorized.

**Firmware policy:** `control_12_full.ino` and `control_13_full.ino` stay
byte-for-byte as they are. Any behaviour change ships as `control_14` with its
own honest identity — changed behaviour must never keep reporting `control_13`.

## Safety boundary

The launcher power is on. Everything below is passive after reset. No `set`,
`aim`, `center`, `jv`, `jh`, `reload`, `shoot`, or wheel RPM command is included
in any authorization here, and none was sent.

Every reset adopts the barrel's current physical pose as logical `0/0`. There is
no absolute encoder and no home switch on either aim axis, so **before any later
reset or flash the operator marks the base and the rotating platform with a
line and photographs it.** The 2026-08-13 measurement ran without that mark by
the operator's explicit decision: it commands no motion, so the barrel could not
move, and the only thing given up was the ability to recover the pre-reset yaw
reference — which was an eyeball estimate, never a measurement. That trade is
not available to any step that does move an axis.

`info`'s `Ang:` is the firmware's own `AccelStepper::currentPosition()`. It is
never a measurement of where the barrel physically is.

## Evidence

### The regression is before the stepper driver

- `aim 0 5 0` advanced `horzStepper.currentPosition()` by about 694 steps in
  roughly 37 s — about 18.8 steps/s.
- `currentPosition()` changes only when `run()` actually emits a step, so
  backlash, coupling, and a jammed barrel cannot explain the slow internal
  count. **Backlash remains unmeasured and is a separate question.**
- `setMaxSpeed(12000)` / `setAcceleration(8000)` predict about 0.59 s for that
  same 694-step profile.

### Passive telemetry bracketed the loop period

Telemetry is gated by `millis() - lastTelem > 250`, so it fires on the first
iteration past 250 ms and the observed period is `n · P` with
`n = floor(250/P) + 1`. 39 intervals averaged 279.851 ms (stdev 0.877 ms), which
admits only `n ≤ 9`:

| n | P (ms) | self-consistent | step ceiling (1/P) |
|---|--------|-----------------|--------------------|
| 10 | 27.99 | no — implies n=9 | — |
| 9 | 31.09 | yes | 32.2/s |
| 8 | 34.98 | yes | 28.6/s |
| **7** | **39.98** | **yes** | **25.0/s** |
| 6 | 46.64 | yes | 21.4/s |
| 5 | 55.97 | yes | 17.9/s |

So `P ≥ 31 ms` was already established. The gate could not pick the divisor.

### Option 0 picked the divisor without flashing anything

`loop()` consumes at most one command per iteration, and `HardwareSerial`'s RX
ring is 256 bytes on core 3.3.7, so a single 100-byte write of `20 × "info\n"`
is buffered whole and drained one command per iteration. The interval between
consecutive `INFO | FW: control_13` lines is therefore one loop period.

Measured 2026-08-13, 19 intervals:

```text
39.892 40.030 40.135 39.868 39.983 39.848 40.182 39.914 40.114 40.065
39.990 39.941 39.835 40.173 40.019 39.967 40.000 39.904 40.090
```

- min 39.835, max 40.182, mean **39.997**, median 39.990, stdev **0.108**, MAD 0.086
- buckets: `<10 ms` 0, `10–25 ms` 0, `25–35 ms` 0, `>35 ms` **19**
- 20/20 response blocks; 7 lines and ~294 bytes per block; theoretical wire time
  3.195 ms at 921600 baud
- **0** intervals merged by CP2102 batching, so no interval is a host artefact
- `INFO | BLE: conn=0, cccd=0x0000, clients=0` throughout — no notify load

The active result (39.997 ms) lands on the passive `n=7` candidate (39.98 ms) to
within 0.04%. Two unrelated measurements agree.

### What this proves, and what it does not

Proven directly:

- the idle loop period is 40.0 ms, tightly locked (stdev 0.108 ms);
- a 25 ms gate inside a 40 ms loop is satisfied on **every** iteration, so
  `lastRampTime = millis()` at the top of the ramp block self-locks and "once
  per 25 ms" is really "every iteration";
- a cooperative `AccelStepper` emits at most one step per `run()`, so the step
  ceiling is 25/s. The observed 18.8/s sits just under it.

Inferred, not directly measured: **where** the 40 ms goes. The ESCs are attached
at 50 Hz, so one PWM period is 20 ms and the two `writeMicroseconds` calls are
exactly `2 × 20 ms`. In Arduino-ESP32 3.3.7 / ESP-IDF `v5.5.2-729-g87912cd291`
the classic-ESP32 LEDC path reached by
`ESP32Servo::writeMicroseconds → writeTicks → ESP32PWM::write → ledcWrite →
ledc_set_duty → ledc_update_duty` actively waits on `conf1.duty_start`
(Espressif commit `723a926b26760832241e19896a582b9043ffecd9`). A 0.108 ms
spread is what a hardware-period-locked wait looks like; software work of that
size would jitter far more. The arithmetic is exact and the mechanism is
present, but no timer was placed inside the call itself.

Ruled out along the way:

- `getRPM` only reads the encoder behind a 200 ms gate, no delay;
- `Serial.readStringUntil` runs only under `Serial.available()`;
- the BLE `delay(500)` runs only on a disconnect transition;
- the telemetry block cannot account for a continuous ceiling;
- the nine `gpio_pullup_en(78)` / `gpio_pulldown_en(116)` errors all occur
  inside `setup()` at 690–701 ms and never repeat in `loop()`, so per-iteration
  `ESP_LOGE` output is not a competing cause.

**Correction to an earlier reading of those errors.** They are *not* about the
limit switches. `LIMIT_FRONT/BACK/BALL` are pins 18, 14 and 16 — ordinary GPIO
whose internal pull-ups work. The failing pins are `ENC_BLDC1_A` = 34 and
`ENC_BLDC1_B` = 35, which are input-only pads with no internal pull at all, so
the `INPUT_PULLUP` and the encoder library's pull configuration are both
silently refused on the **left flywheel encoder**. `ENC_BLDC2` on 32/33 is fine.
It evidently works today — idle telemetry reads a steady `L:0 R:0`, so the
encoder must be actively driven rather than open-collector — but `currentRPM_Left`
feeds the ≥400 RPM fire gate, so this is worth an external pull-up and a note
rather than being left as boot noise. Separate from the timing work.

### Operational gotchas found while measuring

Three things broke the first two attempts and belong in any repeat:

1. **The boot identity arrives glued to baud-transition garbage.** The boot ROM
   talks at its own baud, producing bytes with no clean newline, so
   `SYS: FW control_13 READY` is a **substring** of a longer line and an
   equality test misses it.
2. **A stale CP2102 tail survives `reset_input_buffer()` under EN low.** 56–65
   lines of the previous session's telemetry arrived within ~1 ms of the reader
   starting, before any boot output. Anchor the analysis on the index of the
   boot-identity line and discard everything before it.
3. **`setup()` ends with `delay(3000)`** to arm the ESCs, so `loop()` and the
   first telemetry line cannot appear until ~3 s after the identity. A 4 s wait
   for "fresh telemetry" times out for a healthy board.

## Options considered

**0. Queue 20 `info` commands, no flash — chosen, and it settled the question.**
Costs one reset, sends only read-only commands, and measures the loop period
directly. This is the first thing to try for any future timing question.

**1. Continue passive timestamp inference.** Already bracketed `P ≥ 31 ms` but
cannot pick the divisor. Superseded by option 0.

**2. Flash `control_12` under the current toolchain.** Rejected as a
discriminator because **`control_12` contains the same 25 ms ramp gate and the
same unconditional pair of ESC writes** — the relevant path is identical, so the
comparison cannot separate source from toolchain. (The `control_13` diff is not
loop-free: it also made the telemetry block unconditional in IDLE. That change
is one short line per ~280 ms and cannot produce a 40 ms period.) The
historically fast binary and its exact toolchain were not preserved.

**3. Instrument a separate `control_13_diag_ledc_v1` image.** Held in reserve.
Option 0 satisfied the decision rule, so nothing is flashed for diagnosis alone.
If a future question does need it: identity must be `control_13_diag_ledc_v1`
and never `control_13`; control logic unchanged; measure `loop_us`, `ramp_us`,
`esc_left_us`, `esc_right_us`, and **the number of consecutive iterations in
which the ramp block executed**; no motion; its own explicit "давай" before any
flash.

## Rollback

There is no flash readback or partition restore in this procedure, and none is
needed. An ESP32 clean build is **not byte-reproducible** — `esp_app_desc_t`
carries compile date/time and `app_elf_sha256`, and build-time strings land in
the image — so the cache `.bin` differing from a previously recorded deployed
hash does not imply unknown firmware.

Rollback is defined by **pinned source SHA-256 + toolchain + live identity**:

- `control_13_full.ino` = `54367d26e9dee54283beba08f0d41297ddacaae2538b296349f0b00eb946049f`
- `control_12_full.ino` = `eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e`
- Arduino CLI 1.5.1, board `esp32:esp32:esp32`, Arduino-ESP32 core 3.3.7,
  ESP-IDF `v5.5.2-729-g87912cd291`
- after flashing, require `SYS: FW control_13 READY` and stable idle `L:0 R:0`

## Fix: `control_14`, A + F

**Built 2026-08-13, not yet flashed.** `control_14_full.ino` SHA-256
`a43b2ef809e20b9b7860e0211b82e74fafb52f3a9d4af9c84f98af3ec6377477`.

Options A and F below were taken together, because A alone fixes only idle and
the case that matters is aiming *while* the wheels ramp. Neither changes the
ramp rate, its endpoints, or the 1000 µs rest value — both only change how
**often** a duty is written:

- a write happens only when `desiredPWM != currentPWM`, so idle costs zero
  writes and the loop should collapse to sub-millisecond;
- the interval becomes `RAMP_INTERVAL_MS = 200` with `RAMP_STEP_US = 5`, so the
  40 ms stall occupies 40 ms of every 200 ms instead of all of it and the
  steppers get ~80% of the time even during a ramp.

**5 µs / 200 ms = 25 µs/s is deliberately the rate `control_13` *actually*
produced**, not its nominal 1 µs / 25 ms = 40 µs/s. The nominal rate was never
achieved because the gate fired every 40 ms, so restoring it would spin the
wheels up about 1.6× faster than the operator has ever seen. That is a separate
decision from removing the stall and is not bundled into this change.

**The residual this section originally warned about did not materialise.** It
predicted a 40 ms pause five times a second during a wheel ramp, and therefore
visibly stepped yaw. Measured on hardware, yaw during a real ramp took 586.2 ms
against 585.8 ms idle — no penalty. See "Acceptance results" for why: the LEDC
wait is for the *previous* update to latch, so spacing the writes out removes
the stall rather than rationing it. Options C and D are not needed.

Verification done so far: 10 contract tests, all 9 mutations caught by the
intended test; `control_12` and `control_13` hashes re-pinned and unchanged;
compiled against core 3.3.7 with no sketch-level warnings — 1123186 bytes vs
`control_13`'s 1123198, identical globals. **Compiled with the arduino-cli
1.4.1 bundled in the Arduino IDE 2.3.8 AppImage, not the 1.5.1 recorded
earlier.** The core, which determines the generated code, is the pinned 3.3.7.

The options as they were costed:

**A. Do not rewrite an unchanged duty. — taken.** Fixes idle completely and
nothing else: during a real `set v h wl wr` the ramp changes `currentPWM` every
tick, so the writes come back exactly when the machine is aiming and spinning up
at the same time. On its own it is not the fix.

It is also the missing measurement: if skipping unchanged writes collapses the
idle loop from 40 ms to sub-millisecond, the 40 ms is **proven** to be inside
`writeMicroseconds`, with no diagnostic image and no extra flash cycle. Reading
that number is acceptance step 4 and it is what converts the remaining inference
into a measurement.

**F. Write less often, in bigger steps, at the same rate. — taken.** Covers the
ramp case A cannot: 8× fewer duty updates for the same µs/s. Costs granularity
(5 µs out of an 800 µs span) and leaves a periodic 40 ms pause.

**B. Interleave `run()` around each ESC write.** Cheap, raises the ceiling by
roughly the number of extra calls, still nowhere near the 12000 step/s profile.
Insufficient alone.

**C. Take the duty update off the main loop** (hardware timer or a task on the
other core) so `run()` never waits behind it. Introduces concurrency into a
path that is currently single-threaded; `ESP32Servo` is not thread-safe.

**D. Drive the ESCs from MCPWM instead of the LEDC-backed `ESP32Servo`,** whose
duty update has no `duty_start` handshake to wait on. Removes the wait rather
than scheduling around it.

C and D remain available if the residual 40 ms pause proves unacceptable. Decide
after acceptance step 4 reports the idle number.

Required properties of whatever ships:

- `control_12` and `control_13` preserved; the change is `control_14`
- ESCs still safely at 1000 µs at boot and on `stop`
- real spin-up and coast-down ramp behaviour preserved
- command grammar and safety gates not weakened; feeder/limit logic untouched
- `stepper.run()` no longer waits behind an ESC update
- the BLE/USB identity evidence from 2026-08-11 still holds
- no fire

## Acceptance results, 2026-08-13

Steps 1–5 passed. `control_14` is flashed and live.

**Step 4, idle loop timing.** The same 20 × `info` method, now against
`control_14`: median **2.800 ms**, min 2.588, max 5.677, and all 19 intervals
under 10 ms where `control_13` had all 19 above 35 ms. Zero intervals hidden by
USB batching, `conn=0, clients=0`.

This is the measurement that converts the attribution from inference to fact.
The only thing changed in that path was *not writing an unchanged duty*, and the
40 ms vanished — so the 40 ms was inside `writeMicroseconds`. Note the median
2.800 ms is **below** the 3.179 ms theoretical wire time for one `info` reply:
the loop is now bounded by the serial transmission of the test's own output, not
by firmware work. No 40 ms outlier survives, confirming zero ESC writes at idle.

**Step 5, yaw-only move.** `set 0 -5 0 0`, wheels commanded 0 so no duty is ever
written. 694 steps reached **585.8 ms** after the command, 1185 steps/s average.
`control_13` needed ~37 000 ms for the same move.

The profile predicts this exactly. 694 steps cannot reach `setMaxSpeed(12000)`
under `setAcceleration(8000)`, so the profile is triangular:
`694 = 8000·t²` → `t = 0.2945 s` half-move → **0.589 s** total, against 0.586 s
measured, 0.5% apart. Peak observed rate ~2315 steps/s against a predicted 2357.
The axis is not merely faster; it now runs at its configured profile, which
means the bottleneck is gone rather than reduced. The operator confirmed the
barrel turned sharply, in a fraction of a second, with no strain or noise.

**One unexplained observation, recorded rather than resolved.** The first
(interrupted) yaw run reported a single `L=48/0, R=17/0` sample during
deceleration, with both target RPMs at 0 and therefore no ESC write possible.
The identical-magnitude reverse move produced **0 non-zero RPM samples out of
20**, so it did not reproduce. It is a one-off, not a systematic consequence of
yaw motion, which argues against stepper EMI (that would repeat) without
establishing what it was. Candidates remain flywheel inertia during
deceleration and pickup on the unpulled left encoder pins 34/35. It matters
because `currentRPM_Left` feeds the ≥400 RPM fire gate and the v(RPM)
calibration; it does not block the timing work.

**Steps 6–8, yaw during a real wheel ramp — PASSED, and the predicted residual
does not exist.** `set 0 5 300 300`, machine empty and zone confirmed clear by
the operator, no `shoot` and no `reload` written. 300 RPM was chosen because
`MIN_RPM_THRESHOLD` is 200 (below it no PWM is produced and the ramp is not
exercised) while `MIN_FEED_RPM` is 400, so the firmware refuses to fire for the
whole test regardless of what else happens.

Yaw reached +5° in **586.2 ms**, against 585.8 ms with the wheels idle. A 0.4 ms
difference — no measurable penalty at all.

**The prediction was wrong, and why matters.** This document predicted ~706 ms
(586 ms of stepping plus three 40 ms ramp-tick stalls). The stalls did not
happen. The `while (conf1.duty_start)` wait is a wait for the *previous* duty
update to latch: in `control_13` the two writes ran back to back inside one
iteration, so each found the hardware still busy and spun a full PWM period,
whereas at a 200 ms interval `duty_start` has long since cleared and the call
returns immediately. **Spacing the writes out does not reduce the stall, it
removes it.** That is inferred from this measurement rather than from reading
the IDF source — but if each write cost a fixed 20 ms the move would have taken
706 ms, and it took 586.

**Consequence: options C and D are not needed.** No second task, no MCPWM port.
Delete the "known residual" warning above from any plan built on it.

### Two findings from the same run, both feeding roadmap A6

**The RPM command mapping is about 23% high.** Commanding 300 RPM produced a
plateau of L≈368, R≈372 with a peak of 399 — against a fire gate of 400, which
the test was designed to stay under. `PWM = RPM·LEFT_SLOPE + LEFT_OFFSET`
(0.1763 / 1101) does not describe this machine. Commanding 400 to satisfy the
gate would deliver roughly 530, and the trajectory evaluator uses the commanded
number. So before v(RPM) can mean anything, the **RPM setpoint itself** needs
recalibrating, not just its conversion to m/s.

**Left and right diverge during spin-up and converge at plateau.** At 6.2 s the
readings were L=3, R=125; the right wheel leads by roughly two seconds before
they match within 2%. A shot taken during spin-up therefore leaves with
mismatched wheel speeds, which imparts spin. Firing must wait for the plateau,
not merely for the gate.

**`stop` needs about 20 s to bring the wheels to rest** (measured: +3 s
281/307, +10 s 81/152, +14 s 1/86, +19 s 1/1). `.claude/rules/safety.md` says
`stop` "kills the flywheels"; it releases them and they coast for twenty
seconds. The left wheel stops around 15 s and the right around 19 s, so their
friction differs markedly as well.

**Resolved:** the unexplained `L=48/0` sample was flywheel inertia, not encoder
pickup — the operator observed the wheels move slightly during the yaw
rotation. The missing pull-up on pins 34/35 remains a separate open item.

## Acceptance, in order

1. static/source-contract tests;
2. compile with the exact core 3.3.7;
3. idle boot, no motion: identity, `IDLE`, `L:0 R:0`;
4. idle loop timing by the same 20 × `info` method — expect a large drop from
   40.0 ms;
5. separately authorized small yaw-only move;
6. separately authorized no-fire wheel ramp, machine empty and zone clear;
7. **the acceptance that matters: yaw moves at normal speed *during* a real
   wheel ramp.** 694 horizontal steps should take about 0.6 s by profile, not
   37 s — confirmed by the operator's eye and the physical mark, never by
   `info Ang`;
8. coast-down back to `L/R ≈ 0`;
9. no `reload`, no `arm`, no `fire`.

Steps 5–8 each: announce the exact command and the expected movement, wait for
its own explicit "давай", then stop and ask the operator what physically
happened. Nothing here inherits permission from anything above it.

Backlash is measured only after normal speed is restored: approach one point
from both directions against a mark or tape, and record commanded deadband and
physical offset separately. `info Ang` is not an encoder.

## Artifacts

Raw log, per-line timestamps with host-read chunk ids, and the summary are under
the ignored `garage_lab_combined/output/blm_logs/`:
`loop_period_info_burst_20260813T142539.{log,lines.jsonl,summary.json}`.
