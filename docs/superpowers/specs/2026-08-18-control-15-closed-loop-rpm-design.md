# control_15 Closed-Loop Flywheel RPM Design

**Date:** 2026-08-18  
**Status:** direction approved; implementation not started
**Branch:** `feature/fixed-yaw-rpm-calibration`

## Problem

`control_14` does not regulate wheel speed. A command is converted once through
two linear maps:

```text
left PWM  = int(commanded RPM * 0.1763 + 1101)
right PWM = int(commanded RPM * 0.1670 + 1088)
```

The firmware then ramps each ESC to that fixed PWM. Encoder RPM is reported and
used by the host's ARM/FIRE gates, but it never feeds back into PWM. Supply,
temperature, bearing load, ESC behaviour, and wheel condition can therefore
move the plateau while the command remains unchanged.

This failure was reproduced on 2026-08-18. Commanded 500 RPM produced roughly
L=443..452/R=502..517 with a loaded chamber. Repeating with the ball removed
produced roughly L=447..457/R=510..517, disproving ball contact as the cause.
The earlier accepted L=456/R=502 plateau had only 6 RPM of left-side margin
above the host's 450 RPM refusal boundary. The independent phone tachometer had
already validated the encoder scale, so changing the command to 600 or widening
the gate would conceal the open-loop error rather than correct it.

## Goal

Ship a new `control_15` firmware in which each flywheel independently uses its
own encoder to hold the commanded speed.

For every command in the operational firing range 400..1200 RPM:

- the mean measured speed of each wheel over an accepted 10-second plateau is
  within 1% of the command;
- neither wheel has a sustained deviation greater than 2% during that plateau;
- changing electrical or mechanical conditions is corrected by feedback rather
  than by substituting a different command;
- a zero command still produces a confirmed physical 0/0 RPM stop.

The algorithm applies to every value in the range, including the desktop
slider's 10 RPM increments. Core hardware commissioning samples 400, 500, 600,
..., 1000 RPM in both directions and repeats 500 RPM after the hot ladder.
The machine has never been operated above 1000 RPM, so 1100 and 1200 are not
routine ladder steps: each is a separately authorised escalation after the
complete core ladder passes. Commands below 400 remain outside the commissioned
firing range. A zero target means stop; 1..199 retains the existing forced-idle
behaviour; 200..399 uses the same
controller but remains no-fire and uncommissioned until a separate physical
minimum-speed study proves that the ESCs can sustain it. Closed-loop behaviour
at 250 RPM is nevertheless predictable enough to test: the measured dead
command maps to L/R PWM `1145/1129`, while the first observed spinning command
at 300 maps to `1153/1138`. With `MAX_TRIM_US = 30`, a persistent positive error
can raise the 250 destinations to `1175/1159`, above both observed spinning
PWMs. The prediction is therefore that 250 will now start; 250 and 300 are
explicit low-range prediction checks, not silently undefined inputs. If a wheel
starts, the result establishes a candidate lower sustainable boundary; if it
does not, `NO_START` is the required result. Neither outcome commissions firing
below 400. The existing 400 RPM feeder gate remains unchanged. A raw target
outside 0..1200 is rejected without changing the current target and emits
`ERR: RPM RANGE` rather than being silently clamped into a different command.

## Non-goals

- Do not weaken the host's freshness, stability, spread, reload, ARM, or FIRE
  refusals. In particular, retain the commanded +/-10% band with its 50 RPM
  floor, the 75 RPM left/right spread limit, and the 400 RPM ARM/FIRE gate in
  `blm_bridge.py`.
- Do not use a higher command as a substitute for a failed lower command.
- Do not change encoder PPR constants; independent video measured reported/true
  ratios of 0.991/0.995 on 2026-08-17.
- Do not fire a ball while controller gains are being commissioned.
- Do not repair or compensate YAW lost motion in this change.
- Do not create the RPM-to-km/h ball model until wheel regulation is accepted.
- Do not edit deployed `control_12_full.ino`, `control_13_full.ino`, or
  `control_14_full.ino`; they are immutable rollback artifacts.

## Considered approaches

### A. Existing feed-forward map plus per-wheel PI trim — selected

The current map supplies a safe, already-characterised starting PWM. Each fresh
encoder sample then adjusts a bounded correction independently for the left and
right wheels. This gives fast startup, eliminates steady-state error, and keeps
the required correction small enough to bound an encoder-failure response.

### B. Pure PID from the 1000 us idle duty

This removes dependence on the map, but the integrator must discover the ESC
start threshold on every command. It creates slower startup, more windup, and a
larger overshoot risk without solving a demonstrated derivative-control need.

### C. Host-side correction through USB

This would avoid a firmware controller, but serial latency, process stalls, USB
disconnects, and host scheduling would sit inside the motor-control loop. The
launcher must regulate and fail safe without a desktop process, so this option
is rejected.

## Firmware architecture

`control_15_full.ino` starts as an exact copy of `control_14_full.ino` with a new
identity. Its public command grammar remains exactly equal to `control_14`;
closed-loop regulation adds no exact token or prefix. The feeder state machine,
stepper behaviour, encoder PPR, BLE/USB transport, continuous
`L:<rpm> R:<rpm>` telemetry, 1000 us idle duty, and mechanical limits remain
unchanged.

Each wheel owns the following controller state:

- commanded RPM;
- current encoder RPM and last fresh sample time;
- feed-forward base PWM from the existing slope/offset;
- integral correction in microseconds;
- current requested PWM;
- startup/encoder-health state;
- latched controller-fault reason.

The left and right states are never averaged. A slow left wheel increases only
left PWM; a fast right wheel decreases only right PWM.

### Control update

The controller runs only when a new 200 ms encoder measurement is available.
For wheel `w`:

```text
ramp_caught_w  = abs(desiredPWM_w - currentPWM_w) <= RAMP_STEP_US
base_w         = int(target_w * slope_w + offset_w)
error_w        = target_w - measured_w
proportional_w = Kp_w * error_w
if ramp_caught_w and saturation_allows_integration_w:
    integral_w += Ki_w * error_w * dt
trim_w         = clamp(proportional_w + integral_w,
                       -MAX_TRIM_US, +MAX_TRIM_US)
desiredPWM_w   = clamp(base_w + trim_w, 1000, 1800)
```

Initial candidate constants are deliberately conservative and independently
named so hardware evidence can tune one wheel without changing the other:

```text
LEFT_KP = RIGHT_KP = 0.12 us/RPM
LEFT_KI = RIGHT_KI = 0.08 us/(RPM*s)
MAX_TRIM_US = 30 us
```

The trim bound has measured numerical margin; it is not a placeholder for
trial-and-error increases. Using the existing feed-forward slopes as the local
plant inverse, 30 us corresponds to approximately:

```text
left authority  = 30 / 0.1763 = 170.2 RPM
right authority = 30 / 0.1670 = 179.6 RPM
```

The largest observed setpoint error was the right wheel at command 400,
measured 509: 109 RPM error requires approximately
`109 * 0.1670 = 18.203 us` correction. The 30 us limit therefore has
`30 / 18.203 = 1.65x` authority over the worst measured error. A failed
candidate is not permission to raise `MAX_TRIM_US`: increasing it requires a
trace that shows intact encoder feedback, trim saturation in the correcting
direction, and insufficient authority rather than unstable gains or a wrong
plant model.

The existing output slew limit remains 5 us every 200 ms. The PI controller
selects the destination duty; the ramp controls how quickly hardware reaches
it. Derivative action is omitted because the measured defect is steady-state
offset and the 200 ms RPM samples already contain quantisation/noise.

The ramp is transport delay inside the loop, not an instantaneous actuator.
Its rate is `5 us / 0.2 s = 25 us/s`, so delivering an 18 us correction takes
`18 / 25 = 0.72 s`. At 100 RPM error, an unconstrained integrator with the
candidate Ki would add `0.08 * 100 * 0.72 = 5.76 us` while the actuator was
still travelling toward the previous request. Output saturation anti-windup
does not catch this case because neither the PI destination nor the ESC range
is saturated.

### Anti-windup and state transitions

The proportional term is recomputed on every fresh RPM sample. `desiredPWM_w`
and `currentPWM_w` in `ramp_caught_w` are the destination and delivered output
carried into that sample, before the new proportional destination is computed.
The integral is updated only when the output ramp has caught that destination:

```text
ramp_caught_w = abs(desiredPWM_w - currentPWM_w) <= RAMP_STEP_US
```

When `ramp_caught_w` is false, the integral for that wheel is frozen while the
proportional term remains active. Once caught, ordinary saturation anti-windup
also applies: the integral is clamped so the combined trim cannot exceed
`MAX_TRIM_US`, pauses when a saturated output would be driven farther outward,
and resumes when the error drives it back toward the valid range.

Target-change reset is evaluated independently for each wheel and is defined
exactly as:

```text
large_change_w = (old_target_w > 0) and (new_target_w > 0) and
                 (abs(new_target_w - old_target_w) > 0.05 * old_target_w)
```

The integral resets only when:

- that wheel's target transitions between zero and nonzero;
- `large_change_w` is true;
- `reload` or `stop` is received;
- a controller fault is latched;
- the ESP32 boots.

For a nonzero change of 5% or less, the integral is preserved because it models
the current hardware/supply bias, not one exact setpoint. The desktop slider
therefore retains the learned correction through each 10 RPM step from 500 to
600, while a direct 500-to-600 command resets it. Startup/encoder-health timing
uses the same small-change/large-change distinction, so a stream of slider
updates neither restarts convergence nor postpones a no-start fault forever.

## Firmware safety behaviour

Closed-loop correction creates a new failure mode: a missing encoder could look
like a slow wheel and request more PWM. Four limits contain it:

1. Feed-forward remains the primary output and PI trim is bounded to +/-30 us.
2. Overall PWM remains clamped to the existing 1000..1800 us range.
3. If a commanded wheel with an active controller target of at least 200 RPM
   fails to produce 100 RPM within 15 seconds, both wheel targets are forced to
   zero and a controller fault is latched. This applies to the 250/300
   prediction checks as well as the firing range.
4. After a wheel has exceeded 200 RPM, falling below 50 RPM for one second while
   its target remains at least 400 is treated as encoder loss or a mechanical
   stall. Both wheel targets are forced to zero and a fault is latched.

A measured value above 1300 RPM is an absolute overspeed fault. This leaves
headroom for the commissioned 1200 RPM point while preventing an unchecked
rise. Any controller fault:

- forces both desired duties toward 1000 us through the existing controlled
  ramp;
- clears both integrators;
- prevents the firmware's `shoot` state from moving the pusher;
- emits one exact `SYS: RPM CTRL FAULT - <reason>` record over USB/BLE;
- remains latched until `stop` is received and fresh telemetry confirms both
  wheels below 50 RPM.

Fault codes are finite and testable: `NO_START_L`, `NO_START_R`,
`ENCODER_LOSS_L`, `ENCODER_LOSS_R`, `OVERSPEED_L`, and `OVERSPEED_R`. When both
wheels violate a condition in the same update, the left/right codes are joined
with `+`; no free-form fault text is used as machine state.

`stop` always remains available. It cannot be blocked by controller state.
`reload` continues to command zero RPM before feeder motion. The existing
`MIN_FEED_RPM = 400` check remains, and the host continues to require its
stricter fresh/stable/spread predicate before ARM and again before FIRE.

## Telemetry and evidence

The existing compact RPM record remains byte-compatible:

```text
L:<measured-left> R:<measured-right>
```

The solicited `info` block gains one USB diagnostic record:

```text
INFO | CTRL: PL=<pwm> PR=<pwm> IL=<trim> IR=<trim> FAULT=<code>
```

The record exposes actual controller authority during commissioning without
changing the host's RPM parser. Existing long INFO records already exceed the
default BLE notification payload; USB is the authoritative commissioning
channel, and BLE truncation is not used as evidence.

Every hardware trace records firmware source hash, compiled binary hash,
command, measured L/R, controller PWM/trim, elapsed time, and anomaly notes.
Gain changes are compile-time source changes: there is no unlogged live-tuning
command.

## Host commissioning boundary

`control_15` must not be added to `COMMISSIONED_FIRMWARE` merely because it
compiles. During candidate testing, the bridge may display its exact raw boot
record while fire control stays disabled. Host recognition is promoted only
after the complete no-fire ladder, reverse ladder, hot-repeat, coast-down, and
independent-video checks pass for the exact flashed source/binary hashes.

If the candidate fails, flash the pinned `control_14` rollback artifact and
require its exact boot identity plus fresh 0/0 telemetry before any further
work.

## Software verification

Implementation is test-first. A dedicated `control_15` contract suite must
first fail against the absent candidate and then pin:

- `control_12`, `control_13`, and `control_14` hashes remain unchanged;
- `control_15` has a unique identity and its extracted exact-token/prefix command
  sets equal `control_14` and the existing explicitly pinned vocabulary;
- both wheels use independent errors, integrals, base PWM, trim, and outputs;
- control updates consume fresh 200 ms samples rather than loop iterations;
- trim, integral, PWM, and overspeed limits cannot be bypassed;
- zero transitions, nonzero changes greater than 5%, reload, stop, and faults
  reset controller state, while changes of 5% or less preserve the integral;
- stop and reload still target 1000 us idle duty;
- feeder motion remains impossible under a controller fault;
- compact telemetry remains parser-compatible;
- the INFO controller record exposes both PWM values, both trims, and fault;
- the source projection normalises only the firmware identity, replaces exactly
  the parsed body of `updateMotorPWM()` with its `control_14` body, and removes
  only explicitly delimited, test-whitelisted `control_15` blocks for controller
  state/constants, target-transition hooks, fresh-sample updates, fault hooks,
  and INFO diagnostics; the result must equal `control_14` byte for byte;
- the projection requires exactly one `updateMotorPWM()` definition and rejects
  a missing, duplicated, nested, or unknown controller-block marker. There is no
  exemption based on a filename, a function-name substring, or the phrase
  "controller work": any byte outside the normalised identity, the exactly
  parsed function body, and the named blocks fails the projection.

A deterministic plant simulation uses the measured approximate gains implied
by the existing maps, adds per-wheel bias and supply disturbance, and verifies
that feed-forward alone retains steady-state error while the selected PI form
converges without violating trim/PWM bounds. Simulation supports the hardware
gate; it does not substitute for it.

The exact candidate must compile with Arduino-ESP32 core 3.3.7 for
`esp32:esp32:esp32`, using the Arduino IDE 2.3.8 bundled CLI already used for
`control_14`. Compiler output, size, source hash, and binary hash are retained.

## Tuning iteration budget and evidence

Controller tuning is limited to four flashed candidates. One iteration begins
when a new `control_15` source hash is flashed and includes compilation, flash,
boot/zero verification, the complete required no-fire ladder for that stage,
and true-zero shutdown. A compile failure that never reaches the board is a
software failure but does not consume a hardware iteration; any changed source
that is flashed consumes one, even if it faults at the first step.

Every iteration is appended as one structured record to
`garage_lab_combined/cal/blm/control_15_tuning.jsonl`. Each record contains:

- iteration number 1..4 and wall-clock timestamp;
- `LEFT_KP`, `LEFT_KI`, `RIGHT_KP`, `RIGHT_KI`, `MAX_TRIM_US`,
  `RAMP_STEP_US`, and `RAMP_INTERVAL_MS`;
- SHA-256 of the exact firmware source and flashed binary;
- Arduino CLI, Arduino-ESP32 core, FQBN, compile result, and binary size;
- for every step: command, ascending/descending/low-range/hot-repeat stage,
  10-second mean L/R, maximum absolute L/R deviation in RPM and percent,
  time-to-band for each wheel and for the pair, controller PWM/trim extrema,
  fault code, and anomaly note;
- confirmation that the ball was absent, fire control was disabled, no YAW,
  `aim`, `center`, or `setzero` operator intent was issued, logical YAW remained
  at the session baseline, marks stayed aligned, and shutdown reached fresh 0/0.

`time_to_band_s` is measured from the serial command write to the first sample
that begins at least two continuous seconds with both wheels inside the +/-2%
commissioning band. A transient crossing does not count.

After any gain or algorithm change, the next flashed hash starts again at S0
and the low-range/core ladder; prior steps cannot be carried forward. Upper
1100/1200 evidence is collected only after that iteration's complete core
ladder passes and the required operator confirmations are obtained.

After four unsuccessful flashed candidates, stop. Do not compile or flash a
fifth tuning candidate, do not widen any acceptance band, and do not increase
trim authority by guesswork. Return the four iteration records, exact failure
patterns, and rollback state to the user. Four consecutive failures mean the
controller/plant model must be reconsidered before further hardware authority
is granted.

## Hardware commissioning

All controller commissioning is no-fire: ball removed, non-human corridor
clear, YAW physically fixed at matching marks, fire control disabled, ESTOP
reachable, and no `reload`, `arm`, `fire`, `center`, or `setzero` command.
Every planned RPM change uses the existing host `wheels <rpm>` intent and its
unchanged combined `set <pitch> <yaw> <rpm> <rpm>` serial mapping. Commissioning
begins with the aligned physical YAW mark adopted as logical zero; because no
later intent changes that zero, each combined set repeats
`horzStepper.moveTo(0)` with zero distance to go and emits no step. This is the
same boundary exercised by the 2026-08-18 ladders. Any nonzero stored YAW,
YAW/aim intent, or visible mark movement aborts the session. A stronger
session-baseline YAW gate belongs in the host serial writer as a separate task,
not in `control_15` firmware. `stop` remains available as the safety action and
is also the only command used to clear a recorded controller fault after the
wheels are below its reset threshold. Serial traces are checked for these
invariants before acceptance.

For every candidate flash:

1. Confirm exact `SYS: FW control_15 READY`, logical aim 0/0, feeder IDLE,
   `Ball=HIGH`, and fresh wheel 0/0 without physical aim movement.
2. Run 250 RPM as a low-range prediction check. If both wheels start, retain a
   10-second trace without treating it as fire-range acceptance. If either does
   not reach 100 RPM in 15 seconds, require the corresponding `NO_START` fault.
   After a successful trace, send the existing host `wheels 0` intent and wait
   for true 0/0. After a fault, retain its record, allow the forced ramp-down to
   reach the reset threshold, send `stop` to clear the latch, and verify fresh
   true 0/0 before continuing.
3. Repeat the same prediction check at 300 RPM, again returning to true 0/0.
   Record whether 250 and 300 start, sustain their commands, or fault; this
   evidence fixes the new lower physical boundary instead of assuming it.
4. Run commanded 400, 500, 600, 700, 800, 900, and 1000 RPM.
5. At each operational step, reject after 15 seconds if the controller has not
   entered the +/-2% band. Once inside, retain at least 10 seconds of fresh
   samples.
6. Command the same operational ladder in reverse to expose hysteresis and
   accumulated heat.
7. Repeat 500 RPM after the reverse ladder; it must meet the same acceptance as
   the cold point.
8. Command zero and wait for true encoder 0/0 before approach or port closure.
9. Review the complete 400..1000 ascending/reverse ladder and hot 500 repeat.
   If any core point fails, do not command above 1000 RPM.
10. Obtain a new explicit operator confirmation for the 1100 RPM escalation.
    Test only 1100 with the same 15-second entry and 10-second plateau criteria,
    then command zero and wait for true 0/0. A failed 1100 point blocks 1200.
11. After 1100 passes, obtain a separate explicit operator confirmation for the
    1200 RPM escalation. Test only 1200 with the same criteria, then command zero
    and wait for true 0/0. The 1100 confirmation does not authorise 1200.
12. Independently measure 500, 800, and 1100 RPM from the slowed section of
   phone video. Reported/true must remain within 5% on each wheel, and the video
   estimate must agree with the command within 2%.

At every plateau, each wheel's 10-second mean must be within 1% of command and
no deviation beyond 2% may persist for more than one second. Any controller
fault, unexpected motion, smell, sound, visible YAW-mark movement, stale
telemetry, hard-limit crossing, or failed video scale check ends the session.

Only the exact source/binary pair that passes all steps can be promoted in the
host and used for the ball-speed measurement. No ball is loaded and no shot is
fired during this design's acceptance work.

## Completion criterion

The work is complete only when the same flashed `control_15` artifact:

- passes all software contracts and the pinned toolchain compile;
- records the predicted start-or-`NO_START` outcome at 250 and 300 RPM;
- passes the ascending/descending 400..1000 core ladder plus the hot 500 repeat;
- passes the separately authorised 1100 and then 1200 RPM escalations;
- passes independent video checks at 500/800/1100;
- returns both wheels to true zero after STOP;
- is then explicitly promoted as commissioned in the host with all focused and
  regression tests green.

Passing only the existing +/-10% ARM window, changing the requested setpoint,
or obtaining one transient exact sample is not completion.
