# `control_13` LEDC/loop timing diagnostic

**Status:** conversational design approved; written review pending, 2026-08-13

**Scope:** identify the source of the yaw step-rate regression without commanding
any axis, flywheel, feeder, reload, arm, or fire action

**Firmware policy:** preserve `control_12_full.ino` and
`control_13_full.ino` byte-for-byte; build a separately identifiable diagnostic
image named `control_13_diag_ledc_v1`

## Safety boundary

The launcher power is on, but this diagnostic is passive after reset. Building,
reading flash, flashing, and opening the serial port are authorized by the
operator's “давай диагностику”; no motion command is included in that
authorization.

The diagnostic run must not send `set`, `aim`, `center`, `jv`, `jh`, `reload`,
`shoot`, wheel RPM, or any other actuation command. It also does not run the
proposed vertical `+2°` comparison: the passive telemetry timing already proved
that the common cooperative loop is slow.

Every reset adopts the barrel's current physical pose as logical `0/0`. Flashing
therefore changes the logical reference even though it does not move either aim
axis. During this procedure the barrel remains where it is; no automatic
`center` is allowed. The operator must separately re-establish and declare the
physical zero and pitch limits before any later aiming session.

The diagnostic is valid only while all of these remain true:

- feeder state is `IDLE` and all three steppers have zero commanded distance;
- left and right target RPM are zero;
- left and right current and desired ESC PWM are all 1000 microseconds;
- no BLE client is connected;
- USB compact telemetry remains `L:0 R:0` apart from encoder rounding noise at
  rest;
- no physical motion, abnormal noise, heat, or smell is observed.

Any violation invalidates the timing window. Unexpected physical actuation is an
immediate physical power-off condition, followed by inspection; it is not a
reason to continue collecting data.

## Evidence already established

The regression is before the stepper driver:

- `aim 0 5 0` advanced the firmware's horizontal
  `horzStepper.currentPosition()` by about 694 steps in roughly 37 seconds,
  approximately 19 steps/s;
- `AccelStepper::currentPosition()` changes here only when `run()` actually
  emits a step, so backlash, coupling, and barrel motion cannot explain that
  slow internal count;
- the configured 12,000 step/s maximum and 8,000 step/s² acceleration predict
  roughly 0.59 seconds for the same 694-step profile.

Passive USB telemetry supplied a second independent clue. With telemetry gated
by `millis() - lastTelem > 250`, 39 measured intervals averaged 279.851 ms and,
after the first interval, clustered at about 279.65–280.31 ms. That is consistent
with a loop taking tens of milliseconds (for example seven roughly 40 ms loops
or five roughly 56 ms loops), rather than a fast loop servicing the gate
immediately after 250 ms. The passive gate cannot distinguish those divisors;
the direct diagnostic will. A cooperative stepper can emit at most one step per
call to `run()`, so either range is already consistent with the observed severe
step-rate ceiling.

The exact installed toolchain is Arduino-ESP32 3.3.7 on ESP-IDF
`v5.5.2-729-g87912cd291`. In that version the classic ESP32 LEDC low-level path
used by `ESP32Servo::writeMicroseconds()` actively waits for `duty_start` to
self-clear before the next duty update. That classic-ESP32 wait was introduced
by Espressif commit `723a926b26760832241e19896a582b9043ffecd9`. The current
firmware calls both ESC writers every ramp interval even when both PWM values
are unchanged at 1000.

This makes the leading hypothesis precise: the two redundant 50 Hz ESC duty
writes consume most of each loop, starving all three `AccelStepper::run()` calls.
The evidence is strong but not yet direct attribution; the diagnostic below is
designed to confirm or falsify it.

## Options considered

### 1. Continue passive timestamp inference

This has already shown common-loop starvation but cannot attribute the time
inside the loop. Repeating it adds little evidence.

### 2. Flash `control_12` under the current toolchain

Rejected as a discriminator. `control_12` contains the same 25 ms ramp gate and
the same unconditional pair of ESC writes. Rebuilding it with Arduino-ESP32
3.3.7 changes source revision and firmware revision together without isolating
the LEDC path. A historical binary built with the old core would be useful, but
its exact toolchain and binary were not preserved.

### 3. Instrument the exact deployed `control_13` logic

Chosen. A separate image measures the loop and the two existing ESC calls while
leaving their order, conditions, arguments, and control behavior unchanged. It
directly tests the hypothesis in one idle, no-motion run.

## Diagnostic image architecture

### Isolation and identity

The diagnostic sketch lives at:

```text
diagnostics/control_13_diag_ledc_v1/control_13_diag_ledc_v1.ino
```

It starts as an exact copy of the deployed `control_13_full.ino`, whose current
source SHA-256 is:

```text
54367d26e9dee54283beba08f0d41297ddacaae2538b296349f0b00eb946049f
```

Only marker-delimited instrumentation blocks and the two identity literals may
differ. Its constant, boot line, and `info` reply identify it as
`control_13_diag_ledc_v1`; it must never claim to be `control_13`.

The production files remain untouched. A source-contract test removes the
marker-delimited diagnostic blocks, normalizes the two diagnostic identity
literals back to `control_13`, and requires the result to equal
`control_13_full.ino` byte-for-byte. This proves that the diagnostic did not
quietly change motion, feeder, ESC, BLE, or serial command behavior.

### Measurements

The sketch uses `micros()` with unsigned subtraction and fixed-size integer
accumulators. No dynamic allocation, task, interrupt, timer, delay, or new
library is introduced.

It records four distributions:

1. `loop_us`: time between consecutive entries to `loop()`;
2. `esc_left_us`: duration of the existing
   `escLeft.writeMicroseconds(currentPWM_Left)` call;
3. `esc_right_us`: duration of the existing
   `escRight.writeMicroseconds(currentPWM_Right)` call;
4. `ramp_us`: duration of the complete existing 25 ms ramp block, including the
   two calls.

Each distribution keeps count, minimum, integer mean, and maximum over a
two-second window. Samples accumulate only while the stationary conditions in
the safety boundary hold. Losing eligibility resets the window rather than
mixing moving and idle timing.

The diagnostic prints one USB-only line every two seconds, for example:

```text
DIAG | fw=control_13_diag_ledc_v1 safe_idle=1 ble=0 loop_us[n/min/avg/max]=... ramp_us[n/min/avg/max]=... esc_left_us[n/min/avg/max]=... esc_right_us[n/min/avg/max]=...
```

It uses `Serial.printf`, not `sendMsg`, so the diagnostic line can never create a
BLE notification. The existing compact telemetry remains unchanged. The loop
interval immediately following a diagnostic print is deliberately skipped so
the report's own serial transmission is not counted in the next window.

No diagnostic command is added to `processCommand`; reporting starts
automatically after boot. This preserves the closed serial grammar and avoids a
command being mistaken for motion authorization.

## Static and build verification

A new isolated contract file,
`tests/test_control_13_ledc_diag_contract.py`, verifies at least:

- both production firmware files retain their pinned hashes;
- the diagnostic projection equals `control_13_full.ino` byte-for-byte;
- the diagnostic constant, boot identity, and report identity agree exactly;
- the original ramp gate and both `writeMicroseconds` statements remain once,
  in the original order, with their original arguments;
- instrumentation brackets those exact calls;
- `DIAG |` output uses USB `Serial` only and is absent from `sendMsg`;
- no new command branch or actuation token exists.

The sketch is then compiled with Arduino CLI 1.5.1, board
`esp32:esp32:esp32`, and the already installed ESP32 core 3.3.7. Resolved build
properties are captured; the core is not upgraded. The source SHA-256,
application-bin SHA-256, size, and compile command form the diagnostic manifest.
Before any write, the operator is told the exact diagnostic firmware ID and
application-bin hash.

## Exact rollback before diagnostic flash

The production source is pinned, but the current Arduino cache application
binary has SHA-256
`e83f541c7443f78a30542d45a991db4c7c43c564357e16bd7e659479d79bdba2`,
which does not match the previously recorded deployed application-bin hash
`fa353af950c653e5a9d62ba7e5dab644de9db24c5e7cefc40afb37e0e2677300`.
The cache is therefore not accepted as an exact rollback artifact.

Before replacing anything, the procedure will:

1. verify the resolved CP2102 port and that no bridge or other process owns it;
2. read and decode the board's partition table;
3. read back the currently booted application flash range, plus every auxiliary
   flash range the chosen uploader would overwrite;
4. store the bytes, offsets, lengths, and SHA-256 values under the ignored local
   `garage_lab_combined/output/firmware_backups/` directory;
5. validate the application as an ESP32 image and confirm that it contains the
   production `control_13` identity;
6. stop if any readback, layout, image, identity, or hash check is ambiguous.

The diagnostic write is limited to the resolved application range whenever the
toolchain permits, leaving NVS and filesystems untouched. After capture, the
exact read-back ranges are restored at the same validated offsets. A reboot must
then report `SYS: FW control_13 READY` and stable idle `L:0 R:0`. No cache binary
is substituted for that backup.

## Physical run and evidence

After build and rollback verification:

1. announce that the next operation is a reset/flash only and sends no movement
   command;
2. flash `control_13_diag_ledc_v1` and open USB serial at 921600 baud;
3. require the exact diagnostic boot identity before accepting any metric;
4. require `safe_idle=1`, `ble=0`, and idle compact telemetry;
5. capture at least 30 seconds of raw serial output to a timestamped ignored log;
6. close serial without sending `center`, aim, wheel, feeder, reload, arm, or fire;
7. restore the exact pre-flash readback and verify the production boot identity
   and idle telemetry.

Opening serial and both flashes reset the ESP32 and logical aim zero. They do not
authorize or request physical movement.

## Decision rule

For each valid two-second window compute:

```text
ESC share = (mean esc_left_us + mean esc_right_us) / mean loop_us
ramp share = mean ramp_us / mean loop_us
```

The LEDC/ESC hypothesis is considered directly confirmed when valid stationary
windows consistently show the existing ramp block consuming at least 80% of the
loop period, with the two measured ESC calls accounting for essentially that
ramp duration. The min/max values must also explain the observed loop range; one
isolated maximum is not enough.

If the ramp share is below 80%, if there are too few eligible samples, or if the
timings do not align across windows, the hypothesis is not declared proven. The
captured residual time then determines the next instrumentation target. No ESC
rewrite is made on an inconclusive result.

## Follow-up boundary

This image diagnoses only; it contains no performance fix. Once the cause is
measured, a separate reviewed change may avoid rewriting an unchanged ESC duty
while preserving actual spin-up and coast-down ramp behavior. That change must
be tested at idle first and then during a separately authorized wheel-ramp test.

No later yaw, pitch, wheel, feeder, reload, arm, or fire test inherits permission
from this diagnostic run. Every physical-motion step must be announced and
receive its own explicit operator “давай”.
