# Fixed-YAW 500 RPM calibration under known horizontal backlash

**Status:** operator-approved design, 2026-08-06
**Scope:** method A speed measurement at one commanded setpoint, using a non-human backstop

## Problem

The current BLM has direction-dependent horizontal backlash of roughly 2 degrees.
The YAW axis is open-loop: the firmware reports its internal step position, not the
barrel's achieved physical direction. In the no-fire gate, `+5 -> CENTER` appeared
to return correctly while `-5 -> CENTER` left a small visible offset. The current
LAUNCHER path sends the firmware's ordinary `center` command and does not compensate
that mechanical hysteresis.

This prevents the session from validating aiming accuracy. It does not prevent a
speed-only measurement if YAW never moves: horizontal landing distance under a
level shot depends on exit speed and launch height, while a fixed small YAW offset
only rotates the cleared trajectory within the floor plane.

## Goals and non-goals

The session will:

- record five valid first-contact distances at a commanded 500 RPM;
- keep the physical YAW direction fixed for the entire session;
- use a measured launch height of `H = 0.50 m`;
- use a tape measure and side-view slow-motion video;
- produce shot-level evidence suitable for the later `v(RPM)` fit.

The session will **not**:

- validate aiming accuracy or YAW repeatability;
- compensate or characterize the backlash;
- authorize pose-guided firing, human-adjacent firing, or automatic firing at a
  person;
- produce the final linear RPM model from one RPM alone.

## Fixed-YAW isolation

Before opening the serial link, the operator levels the barrel and physically
points it into the center of the rigid backstop. Aligned marks on the fixed base
and rotating platform define the session's YAW reference. The cleared corridor is
at least 25 cm wide on either side of the observed flight line.

Opening the serial link resets the ESP32 and adopts that physical pose as logical
`0/0`. From then until shutdown:

- do not use the YAW slider, `CENTER`, or `SET ZERO`;
- do not change PITCH from zero;
- check the physical YAW marks before every arm;
- abort on any visible mark displacement.

Firmware `reload` internally commands both aim axes to zero. This is acceptable
only while their logical targets and internal positions are already zero; any
visible aim movement during reload is an immediate failed session.

## Per-shot sequence

The order is deliberately `RELOAD -> RPM`, not the reverse. Firmware `reload`
sets both wheel targets to zero, so the previous protocol order could leave the
interface and physical wheels out of sequence.

For each of five shots using the same ball:

1. With wheel command zero, place the ball in the vertical lift and press
   `RELOAD`.
2. Poll firmware. Require feeder `IDLE`, `Ball=LOW` (loaded), logical aim `0/0`,
   and no visible movement of the YAW reference marks.
3. Command 500 RPM and allow at most 15 seconds for spin-up. Once both measured
   wheels enter 450--550 RPM, collect at least three polls spanning at least two
   seconds; both wheels must remain in that band and within 75 RPM of each other.
   Never arm during spin-up. If the stability window is not achieved by the
   deadline, command zero and abort the pass for wheel diagnosis.
4. Start side-view slow-motion recording. Require the ruler scale, barrel exit,
   flight region and first floor contact to be visible.
5. Re-check the empty controlled area and the YAW marks. Tick room-clear, press
   `ARM`, then deliberately hold `HOLD TO FIRE`. One arm permits one shot only.
6. After the firmware returns the feeder to `IDLE`, command wheel RPM zero. Nobody
   enters the controlled area until both measured wheel values are below 50 RPM.
7. Review the video, measure the horizontal distance from the point directly
   below the barrel exit to the first floor contact, and record the shot at
   commanded 500 RPM. Retain the video filename and the stable measured wheel
   snapshot as notes.

Repeat from step 1. Do not reuse an arm, and do not leave the flywheels spinning
while measuring or retrieving the ball.

## Abort and shutdown

Press `STOP` immediately for any of the following:

- a person enters the controlled area;
- a YAW reference mark moves;
- `RELOAD` moves either aim axis;
- after the 15-second spin-up deadline, either measured wheel remains below 400
  RPM, outside the stability band, or keeps trending rather than settling;
- the ball input does not reach its loaded state;
- the feeder does not return to `IDLE`;
- the phone fails to capture the first contact;
- any contact, unexpected motion, noise or smell occurs.

Shutdown sends `stop` only and must not move the aim. A failed or uncertain shot
is not recorded; it is repeated only after the cause is understood and the full
pre-shot gate is re-run.

## Evidence and acceptance

A valid pass contains five individual distances with:

- commanded RPM `500`;
- stable measured left/right RPM snapshot;
- `H = 0.50 m`;
- `pitch_zero_checked = yes`;
- `yaw_fixed_mark_checked = yes`;
- video filename and any anomaly note.

After five shots, compute the five per-shot speeds, mean and shot-to-shot spread.
Do not write the final linear model until the 800 and 650 RPM passes exist. Method
B must still cross-check the 800 RPM result before the speed model can inform a
safety claim.

Passing this design establishes only repeatable exit speed at a fixed physical
direction. Aiming validation requires a separate non-human target-grid protocol
that explicitly includes approach direction, measured backlash, miss envelope
and worst-case speed uncertainty.
