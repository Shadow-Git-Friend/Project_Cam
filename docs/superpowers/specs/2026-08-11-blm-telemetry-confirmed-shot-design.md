# BLM USB telemetry and confirmed-shot evidence

**Status:** operator-approved, review-corrected design, 2026-08-11

**Scope:** repair the desktop BLM evidence/safety path before any further
flywheel or firing test

**Firmware policy:** preserve `control_12_full.ino` byte-for-byte; introduce a
separately identifiable `control_13_full.ino`

## Problem observed on the stand

The 2026-08-11 no-fire check opened the CP2102 link at 921600 baud and obtained
real firmware replies:

```text
INFO | RPM: L=22/0, R=8/0
INFO | FDR: IDLE, PUSH_POS: 0
INFO | LMT: Front=HIGH, Back=LOW, Ball=HIGH
```

The desktop panel nevertheless showed no measured RPM, `DO NOT APPROACH`, and
`BALL SWITCH: NOT POLLED`. This is a protocol mismatch, not missing hardware:

- `blm_bridge.py` accepts only compact `L:<actual> R:<actual>` telemetry;
- its ball parser accepts only numeric `Ball:0/1`;
- `control_12_full.ino` emits `INFO | RPM: L=<actual>/<target>, ...` and
  `Ball=HIGH/LOW` for an `info` request.

The same inspection found two independent evidence defects:

- the bridge currently writes `shot_fired` immediately after the serial write of
  `shoot`, although the firmware confirms physical travel later with
  `SYS: SHOT FIRED - FRONT LIMIT HIT`;
- the RPM stability timer can pass from too few readings, or across a stale gap,
  because it stores only the time of first in-band observation.

No RPM, ARM, or firing test proceeds until the relevant slice below passes.

## Goals

1. Make the current `control_12` `info` reply visible and testable without a
   firmware flash.
2. Treat only the front-limit firmware event as evidence that a shot physically
   occurred.
3. Require a real sampled stability window: at least three separate arrivals,
   at least two seconds of span, and no stale gap.
4. Preserve the ball-switch rule: display and warn, but never block firing,
   because its polarity is inferred from INPUT_PULLUP wiring rather than
   commissioned on the stand.
5. Add a new firmware revision whose USB telemetry observes both spin-up and
   spin-down, including a fresh zero.
6. Keep all physical validation staged and fail-closed.

## Non-goals

- No change to the 400 RPM firmware firing threshold, pitch/yaw bounds, limit
  polarity, baud rate, or command grammar.
- No automatic firing, human-adjacent firing, or occupied-goal serving.
- No `SAVE THE CORNERS` work in this change. That drill remains a separate audit
  after the BLM evidence path is commissioned.
- No rewriting or deletion of existing calibration JSONL.

## Delivery strategy

The work is split at the firmware-flash boundary.

### Slice 1 — host software only

This slice is implemented and fully tested without opening the serial port.
Order matters: the confirmed-shot gate is implemented first because it prevents
false calibration evidence using an event the current firmware already emits.

#### 1. Confirmed-shot state machine

Sending `shoot` is a request, not a shot:

```text
ARMED
  -> write `shoot`
  -> AWAITING_FIRMWARE_ACK
  -> exact `SYS: SHOT FIRED - FRONT LIMIT HIT`
  -> CONFIRMED SHOT / awaiting distance
```

On a successful serial write, the bridge:

- consumes ARM immediately;
- conservatively marks the chamber bookkeeping as not loaded;
- captures commanded RPM, the last confirmed **pre-fire** left/right RPM sample,
  that sample's age at the instant `shoot` is sent, aim, timestamp, and a request
  identifier in `fire_request`;
- records `shot_requested`, which states only that the command reached the serial
  writer;
- does **not** increment `shots_fired`, create `pending_shot`, accept a distance,
  or write `shot_fired`.

While an acknowledgement is outstanding, all commands which could change the
physical outcome are refused. `STOP` and process shutdown remain available at
all times. In particular, `info` is not auto-polled during this interval: the
current firmware spends 250 ms inside five `delay(50)` calls, during which the
cooperative stepper state machine does not run.

The exact front-limit line finalizes the request once:

- increment `shots_fired`;
- create the one `pending_shot` which may receive a distance;
- append `shot_fired` linked to the request and carrying both commanded and
  explicitly named pre-fire measured RPM plus its age at request time;
- expose the confirmed state to the UI.

A duplicate acknowledgement is idempotent. An acknowledgement with no matching
request is an `orphan_shot_ack`: the bridge latches STOP because it proves
physical motion outside the evidence state it can explain.

The evidence must never call the captured pair "RPM at firing". Both firmware
revisions intentionally suppress the compact telemetry stream outside IDLE, so
no fresh sample can arrive while the firmware is in `STATE_SHOOTING` awaiting the
front limit. The v2 field names therefore state their provenance, for example
`rpm_left_pre_fire`, `rpm_right_pre_fire`, and
`rpm_pre_fire_sample_age_s`. The UI uses the same wording. These values prove the
last sample which satisfied the bridge gate before the request; they do not claim
to observe wheel speed at the later physical front-limit event.

#### 2. Acknowledgement timeout

The existing bridge heartbeat checks a bounded, configurable acknowledgement
deadline. The initial default is 5 seconds. S0--S2 do not exercise the physical
shot path, so they cannot validate or tighten this number; any later adjustment
must use measured command-to-front-limit latency from a separately authorized
non-human backstop test after all preceding gates pass.

On the first timeout, atomically and in this order:

1. latch ESTOP and disarm in bridge state;
2. mark the request outcome unknown;
3. append one `shot_confirmation_timeout` record;
4. send `stop` once.

The latch and evidence transition happen before the serial write, so a failed
write cannot leave the console looking live. The request context remains long
enough to recognize a late exact acknowledgement, but the latch remains set and
the session remains diagnostically failed. Without an acknowledgement, no
physical shot or measurement is asserted. Recovery requires closing the console,
physically inspecting the chamber after confirmed spin-down, and starting a new
session; `CLEAR` cannot turn an unresolved request back into a fire-ready state.

This timeout is also the expected detector for the firmware's silent RPM refusal.
In `STATE_SHOOTING`, if either measured wheel falls below 400 RPM, `control_12`
holds the pusher at zero and emits neither a refusal nor a completion event. The
bridge's pre-fire RPM window makes that outcome rare but cannot make it
impossible: RPM can fall after `shoot`. Therefore the timeout log and UI explicitly
say that a below-400 firmware refusal is one possible cause of the missing ACK.
It remains an outcome-unknown ESTOP and invalid session, not a recoverable warning
and not a proven `shot_refused`, because missing ACK can also mean link loss or a
front-limit failure.

#### 3. Real `control_12` parsers

One normalization path accepts both forms:

```text
L:812 R:798
INFO | RPM: L=812/800, R=798/800
```

For the `INFO` form, the values before `/` are measured RPM; targets remain
diagnostic fields because the bridge already owns the commanded target. Compact
telemetry stays out of the mission log, while a solicited `INFO` line remains
visible in its poll block even though it also contributes a sample.

The ball parser accepts numeric and level forms:

```text
Ball:0       Ball=0       Ball=LOW       Ball=HIGH
```

LOW maps to the existing inferred present level and HIGH to absent. This only
updates `ball_present` and warnings. It must not enter `arm`, `fire`, or
`fireBlockers` as a gate.

There is no periodic `info` polling in Slice 1. A manual poll is safe for the
no-fire check while the feeder and aim are at rest. It must not be used as an
ersatz high-rate telemetry stream during motion.

#### 4. Sample-window contract

The bridge tracks, for the current commanded RPM only:

- first in-band sample time;
- last in-band sample time;
- number of separately received in-band samples.

ARM requires all of:

- the latest telemetry age is at most the freshness limit;
- both measured wheels are inside `max(10%, 50 RPM)` of command;
- left/right spread is at most 75 RPM;
- at least three separate sample arrivals exist;
- last minus first sample time is at least 2.0 seconds;
- no inter-sample gap exceeded the telemetry freshness threshold.

Identical RPM values count when they arrived as separate readings; a stable
machine should not need numerical noise to pass. Multiple lines received at the
same monotonic instant do not manufacture multiple samples.

The whole window resets on target change, any out-of-band/spread failure, or a
gap over the freshness threshold. Therefore neither three lines in 30 ms nor one
new line after a long silence can inherit a two-second pass.

The UI displays sample count and elapsed span from bridge status. It does not
reimplement the gate.

#### 5. One outstanding physical shot

The bridge refuses a new fire request while either a firmware acknowledgement or
a landing distance is outstanding. Every physical ball therefore has exactly one
place to attach its measurement.

`UNDO` is allowed only when no newer `pending_shot` exists. Otherwise it refuses
instead of replacing that newer shot with an older retracted measurement. The UI
uses the same bridge-published state to disable the button, while the bridge
remains authoritative.

#### 6. Evidence versions and existing records

Shot evidence receives its own v2 schema so the meaning of `shot_fired` is
unambiguous. New records distinguish:

- `shot_requested` — serial command accepted by the writer;
- `shot_fired` — exact firmware front-limit acknowledgement observed;
- `shot_confirmation_timeout` — outcome unknown, STOP latched;
- `orphan_shot_ack` — physical acknowledgement with no explainable request;
- `measurement` / `retracted_measurement` — linked to a confirmed shot only.

Both `shot_requested` and `shot_fired` carry the same explicitly named
`rpm_left_pre_fire`, `rpm_right_pre_fire`, and
`rpm_pre_fire_sample_age_s` captured at request time. A later reader can therefore
audit the independent variable without mistaking it for telemetry sampled during
`STATE_SHOOTING`.

The status transport may remain `project_cam.blm_console.v1`; changing its fields
is additive. The evidence file already contains four v1 `shot_fired` rows from
2026-08-07. Under the old implementation those rows prove command writes, not
front-limit acknowledgements. They are preserved byte-for-byte and excluded from
confirmed-shot calibration unless independent session/video evidence resolves
them.

#### Slice 1 acceptance

Software acceptance includes focused regression tests followed by the full
Python, Rust, TypeScript, lint, build, and binary-freshness checks. Required
negative tests include:

- the three real stand lines parse exactly;
- ball HIGH/LOW never becomes a fire blocker;
- a serial write without ACK produces no `shot_fired` or measurable shot;
- an unrelated or duplicate firmware line cannot confirm a shot;
- timeout latches before attempting STOP and remains latched if that write fails;
- a no-ACK path is described as outcome-unknown and explicitly includes the
  firmware's silent below-400 RPM refusal; it never creates `shot_fired`;
- pre-fire RPM and sample age survive unchanged from request to confirmed-shot
  evidence, and no field claims an at-fire measurement;
- one sample aged two seconds, three samples in 30 ms, and a sample after a stale
  gap all fail stability;
- three separate samples spanning two seconds with no gap pass;
- target changes and out-of-band readings reset count and span;
- `UNDO` cannot overwrite a newer pending shot.

After software verification, repeat only the no-fire console check on
`control_12`: level before opening, fire control disabled, one manual `POLL`, and
confirm measured L/R plus Ball appear. Because `control_12` has no continuous USB
zero stream, a fresh stopped verdict from that poll is temporary and must become
unsafe again when stale. Do not run spin-only or ARM in Slice 1.

### Slice 2 — explicit `control_13` firmware

`control_12_full.ino` remains unchanged. `control_13_full.ino` starts as a copy
and makes only the protocol/runtime changes below.

#### 1. Observable firmware identity

`control_13` emits an explicit identity at boot and in `info`. The bridge displays
the parsed identity, so a test report can name the firmware actually connected
rather than infer it from a filename on disk.

The baud rate (921600), commands, limit polarity, BLE name, and mechanical state
machine remain compatible. Repository inspection found seven Python files which
open `serial.Serial(...)`: five active launcher/operator paths
(`blm_bridge.py`, `blm_follow.py`, `launcher_runtime_from_udp.py`,
`live_aim_test.py`, `manual_aim_test.py`) and two legacy utilities
(`blm_interactive.py`, `version1.1.py`). Their command compatibility is checked;
no active profile silently changes firmware expectations.

#### 2. Continuous USB telemetry that includes coast-down and zero

While the feeder state is IDLE, every 250 ms `control_13` calls the existing
`sendMsg` with measured values:

```text
L:<actual-left-rpm> R:<actual-right-rpm>
```

The emission is independent of:

- BLE connection state;
- desired or current PWM;
- target RPM;
- measured RPM being zero.

`sendMsg` already prints to USB unconditionally and notifies BLE only when BLE is
connected. Keeping the IDLE condition avoids telemetry work during pusher
motion. Removing the PWM condition is essential: setting target zero must not
hide wheels which are still coasting. The safety threshold is applied by the
bridge to measured RPM (`<50` for approach), never by a firmware PWM proxy.

#### 3. Non-blocking `info`

Remove all five `delay(50)` calls from the `info` handler. The response remains a
snapshot with the same existing fields plus firmware identity. No command handler
may deliberately stall `vertStepper.run()`, `horzStepper.run()`, or
`pusherStepper.run()` for 250 ms.

#### Slice 2 acceptance and hardware order

Before flashing:

- compile `control_13` with the repository-supported ESP32 toolchain if present;
- source-contract tests prove `control_12` is unchanged, identity is present,
  telemetry is not BLE/PWM/zero-gated, and `info` contains no delay;
- rerun all host verification from Slice 1 and rebuild the desktop binary.

After flashing, the operator repeats hardware commissioning for the new firmware:

1. **S0 — identity and serial:** level the barrel before opening; verify
   `control_13`, 921600 baud, current info fields, and a continuous fresh zero-RPM
   stream with fire control disabled.
2. **S1 — no-fire/manual safety:** verify STOP/latch, limit and ball display, and
   only the already-approved manual movements with clear travel. Do not simulate
   a front-limit shot acknowledgement or tune the ACK deadline in this stage.
3. **S2 — aim-only:** repeat the measured pitch/yaw travel and fixed-zero checks;
   no RPM, ARM, or ball is used.
4. Only after S0-S2 pass, run a separately announced **spin-only** check: command
   the lowest test RPM, observe at least three samples spanning two seconds,
   command zero, and verify the stream continues through coast-down until both
   measured wheels remain below 50 RPM. No ARM or fire.

Any missing/stale stream, firmware-identity mismatch, unexpected motion, limit
disagreement, or STOP failure ends the test. Physical firing remains blocked
until the confirmed-shot gate, timeout path, and spin-down verdict are all proven
without a ball.

## Final acceptance

This design is complete when:

- Slice 1 makes current `control_12` info visible and prevents command writes from
  becoming physical-shot evidence;
- Slice 2 provides continuous actual-RPM USB telemetry through coast-down to a
  fresh zero under an explicit `control_13` identity;
- stability requires sample count, time span, and continuity;
- timeout and orphan acknowledgement paths fail closed;
- ball state remains advisory;
- existing v1 evidence is preserved and not silently upgraded;
- no firing or `SAVE THE CORNERS` work occurs as part of implementation.
