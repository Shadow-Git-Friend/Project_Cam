# control_15 Closed-Loop Flywheel RPM Design

**Date:** 2026-08-18  
**Status:** approved design, implementation not started  
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
slider's 10 RPM increments. Hardware commissioning samples 400, 500, 600, ...,
1200 RPM in both directions and repeats 500 RPM after the hot ladder. Commands
below 400 remain outside the commissioned firing range. A zero target means
stop; 1..199 retains the existing forced-idle behaviour; 200..399 uses the same
controller but remains no-fire and uncommissioned until a separate physical
minimum-speed study proves that the ESCs can sustain it. The existing 400 RPM
feeder gate remains unchanged. A raw target outside 0..1200 is rejected without
changing the current target and emits `ERR: RPM RANGE` rather than being
silently clamped into a different command.

## Non-goals

- Do not weaken the host's freshness, stability, spread, reload, ARM, or FIRE
  refusals.
- Do not use a higher command as a substitute for a failed lower command.
- Do not change encoder PPR constants; independent video measured reported/true
  ratios of 0.991/0.995 on 2026-08-17.
- Do not fire a ball while controller gains are being commissioned.
- Do not repair or compensate YAW lost motion in this change.
- Do not create the RPM-to-km/h ball model until wheel regulation is accepted.
- Do not edit the deployed `control_14_full.ino`; it is the rollback artifact.

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
identity. The command grammar, feeder state machine, stepper behaviour, encoder
PPR, BLE/USB transport, continuous `L:<rpm> R:<rpm>` telemetry, 1000 us idle
duty, and mechanical limits remain unchanged.

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
base_w       = int(target_w * slope_w + offset_w)
error_w      = target_w - measured_w
integral_w  += Ki_w * error_w * dt
trim_w       = clamp(Kp_w * error_w + integral_w,
                     -MAX_TRIM_US, +MAX_TRIM_US)
desiredPWM_w = clamp(base_w + trim_w, 1000, 1800)
```

Initial candidate constants are deliberately conservative and independently
named so hardware evidence can tune one wheel without changing the other:

```text
LEFT_KP = RIGHT_KP = 0.12 us/RPM
LEFT_KI = RIGHT_KI = 0.08 us/(RPM*s)
MAX_TRIM_US = 30 us
```

The existing output slew limit remains 5 us every 200 ms. The PI controller
selects the destination duty; the ramp controls how quickly hardware reaches
it. Derivative action is omitted because the measured defect is steady-state
offset and the 200 ms RPM samples already contain quantisation/noise.

### Anti-windup and state transitions

The integral is clamped so the combined trim cannot exceed
`MAX_TRIM_US`. Integration pauses when an output is saturated and the current
error would drive it farther into saturation; it resumes when the error drives
back toward the valid range.

The integral and startup state reset whenever:

- a different target RPM is received;
- target RPM becomes zero;
- `reload` or `stop` is received;
- a controller fault is latched;
- the ESP32 boots.

This prevents correction learned at one speed or supply condition from being
replayed at another. A new nonzero target always begins from its feed-forward
base, not from a stale integral.

## Firmware safety behaviour

Closed-loop correction creates a new failure mode: a missing encoder could look
like a slow wheel and request more PWM. Four limits contain it:

1. Feed-forward remains the primary output and PI trim is bounded to +/-30 us.
2. Overall PWM remains clamped to the existing 1000..1800 us range.
3. If a commanded wheel in the firing range fails to produce 100 RPM within
   15 seconds, both wheel targets are forced to zero and a controller fault is
   latched.
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
- `control_15` has a unique identity and unchanged command grammar;
- both wheels use independent errors, integrals, base PWM, trim, and outputs;
- control updates consume fresh 200 ms samples rather than loop iterations;
- trim, integral, PWM, and overspeed limits cannot be bypassed;
- target changes, zero, reload, stop, and faults reset controller state;
- stop and reload still target 1000 us idle duty;
- feeder motion remains impossible under a controller fault;
- compact telemetry remains parser-compatible;
- the INFO controller record exposes both PWM values, both trims, and fault;
- reverting the closed-loop additions and identity reproduces `control_14`
  except where the new controller necessarily replaces `updateMotorPWM`.

A deterministic plant simulation uses the measured approximate gains implied
by the existing maps, adds per-wheel bias and supply disturbance, and verifies
that feed-forward alone retains steady-state error while the selected PI form
converges without violating trim/PWM bounds. Simulation supports the hardware
gate; it does not substitute for it.

The exact candidate must compile with Arduino-ESP32 core 3.3.7 for
`esp32:esp32:esp32`, using the Arduino IDE 2.3.8 bundled CLI already used for
`control_14`. Compiler output, size, source hash, and binary hash are retained.

## Hardware commissioning

All controller commissioning is no-fire: ball removed, non-human corridor
clear, YAW physically fixed at matching marks, fire control disabled, ESTOP
reachable, and no `reload`, `arm`, `fire`, `center`, or `setzero` command.

For every candidate flash:

1. Confirm exact `SYS: FW control_15 READY`, logical aim 0/0, feeder IDLE,
   `Ball=HIGH`, and fresh wheel 0/0 without physical aim movement.
2. Run commanded 400, 500, 600, 700, 800, 900, 1000, 1100, and 1200 RPM.
3. At each step, reject after 15 seconds if the controller has not entered the
   +/-2% band. Once inside, retain at least 10 seconds of fresh samples.
4. Command the same ladder in reverse to expose hysteresis and accumulated heat.
5. Repeat 500 RPM after the reverse ladder; it must meet the same acceptance as
   the cold point.
6. Command zero and wait for true encoder 0/0 before approach or port closure.
7. Independently measure 500, 800, and 1100 RPM from the slowed section of
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
- passes ascending and descending 400..1200 RPM ladders plus the hot 500 repeat;
- passes independent video checks at 500/800/1100;
- returns both wheels to true zero after STOP;
- is then explicitly promoted as commissioned in the host with all focused and
  regression tests green.

Passing only the existing +/-10% ARM window, changing the requested setpoint,
or obtaining one transient exact sample is not completion.
