# Measuring ball exit speed v(RPM) — operator procedure

**Roadmap item A6** (the desk half of blocker **B1**). One operator, one session,
no assistant required. Read it once end to end before firing anything.

Everything below was re-checked against the code and the connected five-camera
rig on 2026-08-06; the tools named here exist in the tree and their flags are
quoted verbatim.

---

## 1. Why this is a safety procedure, not an accuracy chore

The launcher aims by solving a ballistic arc, and that solver needs the ball's
exit speed. It currently **assumes 10 m/s** (`--v-base-mps 10.0` in
`live_aim_test.py`). The same assumed number reaches
`project_cam.closed_loop.firing_line`, which samples the commanded arc to decide
whether the corridor is clear of people. So an unmeasured speed is not only why
shots land short or long — it is an unmeasured input to a clearance decision.

**Until this procedure has been completed, treat the nominal 10 m/s arc as
uncommissioned geometry.** Keep the physical exclusion zone, keep the low-energy
presets, and do not run pose-guided firing at a person.

## 1b. RESOLVED 2026-08-17 — independent video cleared the prerequisite

The previous STOP extrapolated one low-range point across the whole setpoint
map: because a command of 300 plateaued at L=392/R=402, it predicted that 500
would produce roughly 655 and could never pass the arm band. That extrapolation
was wrong. The bottom of the range is nonlinear; it is not a global scale error.

The independent phone-video tachometer established the time scale from the
known slow-motion section and measured:

- **IMG_2536, command 400:** firmware L=392/R=509; video L=395.5/R=511.6.
  Reported/true is 0.991/0.995, validating `PPR_LEFT = 1000` and
  `PPR_RIGHT = 2000` rather than suggesting a common encoder error.
- **IMG_2544, command 500:** firmware L=456/R=502. The left video's
  autocorrelation was about 456 but its independent crossing count was noisy,
  so that side is supporting evidence rather than a standalone accepted reading;
  the right video was accepted at about 510. The firmware pair is inside the
  commanded 500 ±50 band and differs by 46 RPM, below the 75 RPM spread limit.
- **IMG_2545, slowed 120-fps section:** true L/R were 685.3/719.5 at command
  700, 796.7/804.5 at 800, 898.8/906.7 at 900, and 1026.3/1029.9 at 1000.
  Every value is within about 3% of its command. The 600 step was in the 30-fps
  real-time head and had only about three frames per revolution, so it is not an
  independent reading and is not claimed as one.

**B1 therefore has no setpoint-refit or `control_15` prerequisite.** Continue
with commissioned `control_14` and §2. The 500 plateau has demonstrated that the
numeric arm window is reachable, but the next session must still prove the
whole live predicate: fresh readings, at least three separate in-band arrivals
spanning two seconds, no gap over two seconds, and wheel spread no more than
75 RPM within the protocol's spin-up deadline. Yesterday's plateau is never an
arm for today's shot.

**Do not widen or bypass that predicate.** A future out-of-band plateau means
stop and investigate. `scripts/fit_rpm_setpoint.py` remains the contingency
tool: any real refit still needs at least three independent video measurements,
must verify reported/true before fitting, and must be followed by a new firmware
identity plus a complete no-fire ladder. Refitting against firmware RPM alone
would still make a bad encoder and a bad map agree with each other.

The lower-band observations remain valid and define where not to operate:
command 250 did not turn either wheel, command 300 produced 392/402, and command
400 produced 392/509. Do not use commands below 500 for B1. A command being
accepted is not evidence of rotation, and either wheel merely crossing the
firmware's 400 RPM fire threshold is not evidence of a stable pair.

The 30- and 45-second holds used in the diagnostic ladders were measurement
windows, not a replacement for the readiness gate. For a shot, §5's explicit
arrival window and deadline are authoritative. After `stop`, wait for the fresh
`safe_to_approach` verdict; measured runs have taken roughly 20–30 seconds to
coast to true zero.

The v(RPM) model remains indexed by the **commanded RPM stored with the confirmed
shot**, because that is the input the launcher can reproduce. Preserve
`rpm_left_pre_fire`, `rpm_right_pre_fire`, and their sample age alongside it as
the audit evidence that the wheels actually satisfied the command before fire.

### Measuring true RPM without a tachometer (2026-08-13)

There is no tachometer on site, so the independent reading comes from a phone.
`scripts/measure_rpm_from_video.py` does the counting — do not count frames by
eye.

1. One high-contrast mark on the tyre. **One**, not two: the tool measures the
   period between pulses, so a second mark halves the answer.
2. Phone on something solid, framing the mark's path. Slow motion, the highest
   rate the phone offers.
3. Film 3-5 s at a steady plateau, per wheel, per ladder step.
4. `--dump-frame` to grab a still, pick a small box the mark sweeps through,
   pass it as `--roi x,y,w,h`. **The ROI is not optional**: a mark that stays in
   frame changes only its position, not the total brightness, so whole-frame
   analysis has no signal at all.
5. Pass `--fps` with the TRUE capture rate if the clip is slow motion — the
   container usually stores the playback rate, and every number scales with it.
6. Pass `--expect-rpm` with the firmware's own reading for that step.

That last one is a precondition, not a cross-check, and it is the reason the
tool can be trusted. **Aliasing cannot be detected from a clip.** A wheel past
half the frame rate folds down to a lower rate: 1500 RPM filmed at 30 fps
reports 300 RPM with a 0.95 repeat strength, and every internal quality signal
looks excellent. Since folding pushes the answer DOWN, "comfortably below
Nyquist" is exactly what a badly aliased clip looks like. Given the expected
rate the frame rate can be judged BEFORE the answer is believed.

If a step still looks wrong, re-film it at a different frame rate. A true rate
is unchanged; an alias moves.

## 2. Preconditions

- [ ] S0–S4 passed (they did, 2026-04-09). If firmware or wheels changed since,
      re-run S0–S3 first — see `.claude/rules/workflow.md`.
- [ ] Room clear of people for the whole measurement. Nobody downrange, ever,
      including you. The controlled landing area must terminate in a wall, net
      or other rated backstop.
- [ ] Computer, cameras and cables removed from the predicted first-contact and
      rebound area, or protected by a rigid barrier. Method A is invalid if the
      first floor contact cannot be seen and measured safely; "being careful"
      is not a substitute for clearing the physical trajectory.
- [ ] ESTOP reachable from where you stand. `stop` latches until `clear`.
- [ ] Same ball for every shot, and the same one you will train with. Ball mass
      and surface change the exit speed; a mixed set makes the fit meaningless.
- [ ] Barrel exit height above the floor measured once with a tape, in metres.
      Write it down — method A is proportional to `sqrt(1/H)`, so a 2 cm error in
      H is about a 2 % error in every speed.
- [ ] **Before opening the console, check that the barrel is horizontal with a
      level.** Opening the serial link resets the ESP32 and adopts the barrel's
      current physical position as logical `0/0`. A tilt biases method A directly
      and is its single largest error source.

### No-fire commissioning gate after any zero/limit change

Complete this once before enabling fire control. It proves the operator tool and
the declared mechanical envelope without spinning the flywheels:

1. Open the desktop **LAUNCHER** view. Leave **ENABLE FIRE CONTROL** unchecked,
   confirm the detected CP2102/by-id device, and press **OPEN CONSOLE**.
2. Press **POLL FIRMWARE**. Require wheels `0/0`, feeder `IDLE`, and visually
   confirm the barrel is in the intended zero position. Telemetry angles are
   commanded values, not position feedback.
   On `control_12` this single poll is also what proves the console can read the
   machine at all: `MEASURED` and `BALL SWITCH` must both populate from the
   reply. If they stay `— / —` and `NOT POLLED`, stop — the console is not
   seeing the firmware, and every later verdict would be built on nothing.
   That snapshot is a snapshot: the stopped verdict correctly goes back to
   `DO NOT APPROACH` once it ages past two seconds, because `control_12` sends
   its continuous `L:/R:` stream only to a connected BLE client and therefore
   nothing arrives over USB unless you poll again. A **spin-only** check — commanding
   RPM and watching the stream follow the wheels down through coast-down to a
   fresh zero — is not possible on this firmware and waits for `control_13`.
3. Press **SET ZERO**. If the barrel was moved by hand, do not reuse stale travel
   numbers: with drive power removed, measure the unobstructed pitch travel from
   this zero, restore the mechanism, and enter it as **TRAVEL DOWN / UP → APPLY
   TRAVEL**. Never force a powered open-loop axis by hand.
4. With RPM still `0`, command only `+5°`, `0°`, and (only if the declared lower
   limit permits it) `−5°`; visually verify each move. Repeat YAW at `±5°`.
5. Press **CENTER** and visually require return to the position adopted by
   **SET ZERO**. Close the console and require **no aim movement**: shutdown sends
   `stop` only and deliberately does not center.

Any unexpected motion, no motion, contact with the feeder, or flywheel movement
is a failed gate. Press **STOP**, remove drive power, and do not continue to a
normal aiming shot matrix.

The 2026-08-18 no-fire check did fail this generic YAW-return gate: after a real
`0 -> +5°` move, the reverse `+5° -> 0` command produced motor noise but no
physical return while the open-loop firmware still acknowledged `H=0.0`. The
previously estimated 6--7 degrees is therefore recorded as unlocalised **lost
motion**, not normal worm-gear backlash. It must not be compensated in software
before the mechanical cause is found and the residual is remeasured.

That result keeps ordinary aiming uncommissioned. The separately scoped fixed-YAW
speed-only pass below is a narrow exception, not a reinterpretation of the failed
gate: close the no-fire console, remove drive power, restore the physical reference
marks, and let the next boot adopt that fixed pose as logical `0/0`. On the
operator's 2026-08-18 decision, the mechanical diagnosis is deferred until after
this fixed-direction measurement. Any subsequent YAW-mark movement still ends the
pass immediately.

## 3. Two methods, and why you run both

| | Method A — landing distance | Method B — camera-tracked speed |
|---|---|---|
| Tool | `scripts/fit_rpm_speed.py` | `garage_lab_combined/scripts/calibrate_ball_rpm.py` |
| Measures | where the ball first hits the floor | 3D ball displacement between frames |
| Needs | tape measure, level | at least 5 live calibrated cameras; `run_live_lowlag.sh` with `--ball-log-jsonl` |
| Blind to | aerodynamic drag; biased by any tilt at pitch 0 | nothing about the launcher — but see below |
| Fails when | the floor is not flat, or the first bounce is missed | the ball is not detected in **consecutive** frames |

They fail in unrelated ways, which is the entire reason for doing both. If they
agree within ~10 %, the number is trustworthy. If they disagree, **do not average
them** — find out why (tilt for A, detection dropouts for B) and re-measure.

### Method B has a known sampling limit — plan for it

At 15 fps a 10 m/s ball travels **667 mm per frame** and crosses the 6.23 m room
in ~0.62 s, i.e. **~9 frames total**. `calibrate_ball_rpm.py` needs *consecutive*
detected pairs, and the measured detection rate on fast recordings is only
**46–52 %** at the default settings. So a single shot can easily yield one usable
pair or none.

Use the ball-critical live profile. These values are constraints of the current
rig, not optional quality tuning:

```
TRACK_BALL=1              # stock mirrored-skeleton wrapper disables the detector
BALL_EVERY=1              # run ball inference every loop for the short flight
BALL_IMGSZ=672            # must match yolo26m-672.engine export size
--min-active-cameras 5    # current rig has 5 live cameras, not 6
--ball-single-cam-fallback
```

Do **not** substitute `--ball-imgsz 960` while using
`models/ball/yolo26m-672.engine`: the TensorRT optimization profile is dynamic in
batch, but its spatial decode must match the 672 export. Off-size inference can
produce garbage detections instead of extra detail.

Fire **at least 5 shots per RPM** for method B and check the per-shot pair count
in the tool's output before trusting the p95.

## 4. Shot matrix

Do it in this order. Stop at the first row that misbehaves.

| Pass | RPM | Shots | Purpose |
|---|---|---|---|
| 1 | 500 | 5 | Lowest energy above the 400 RPM firmware gate. Proves the whole procedure with the least stored energy. |
| 2 | 800 | 5 | The RPM actually used in training, and the one every current accuracy claim depends on. |
| 3 | 650 | 3 | A midpoint, so the fit is a line rather than two ends. |
| 4 | 950 | 3 | Only if you intend to train above 800. Otherwise skip — the model **clamps to the measured range and refuses to extrapolate**, which is the behaviour you want. |

A first pass of pass 2 alone is legitimate: `fit_rpm_speed.py` will emit a
`constant_mps` model from a single RPM, and that is already a large improvement
over an assumed 10 m/s. Do not skip pass 1 to get there faster — it is the pass
that catches a mistake cheaply.

## 5. Running it

### Method A, per RPM

Use the desktop **LAUNCHER** view rather than the raw serial terminal. The app
passively identifies the CP2102 launcher and selects its stable `/dev/serial/by-id`
link, so USB re-enumeration from `ttyUSB0` to `ttyUSB1` does not change the choice.

#### Fixed-YAW 500 RPM speed-only pass

This temporary pass is allowed while the unlocalised horizontal lost motion is
deferred only because YAW is physically fixed before the serial link opens. With
drive power removed, restore matching marks on the fixed base and rotating
platform; then keep the observed flight corridor clear by at least ±25 cm and do not use **YAW**, **CENTER**, or **SET ZERO** during the session. This pass does not validate aiming accuracy and cannot authorize pose-guided, human-adjacent, or automatic firing at a person.

Complete every non-YAW part of the no-fire gate above. Keep the failed YAW return
recorded rather than repeating it or calling it a pass; close the aim-only console,
restore the physical YAW marks with drive power removed, enable **ENABLE FIRE
CONTROL**, reopen it, and confirm logical pitch/yaw `0/0` without moving either aim
control.

For each of five shots with the same ball:

1. Press **RELOAD** with wheel command zero and the ball in the vertical lift.
   RELOAD is not optional bookkeeping: it zeroes the wheel targets, sends
   `horzStepper.moveTo(0)`, and the console refuses to **ARM** without one since
   the last shot. YAW stays physically fixed only because boot adopted the aligned
   marks as logical zero and no later YAW command has broken that relationship.
   PITCH is not commanded to exact zero: `vertStepper.moveTo(7)` is 7 steps, or
   about `+0.042°` at `STEPS_PER_DEG_VERT = 166.67`. Keep that known offset in the
   measurement notes. `NEXT` names the required reload.
2. Press **POLL FIRMWARE**. Require feeder `IDLE`, `Ball=LOW`, logical aim `0/0`,
   and unchanged physical YAW marks. Any visible aim motion fails the session. The
   console parses the ball switch into `BALL SWITCH` and warns when it disagrees
   with `CHAMBER` — that mismatch is the only visible sign of the firmware's 10 s
   dispense timeout finishing with an empty chamber. The switch informs; it does
   not gate, because its polarity is inferred from the wiring rather than measured.
   Each poll now starts its own block with its own age, so three identical replies
   read as three replies.
3. Command **500 RPM**. Allow at most 15 seconds for spin-up. Once both measured
   wheels are between 450 and 550 RPM, require three polls spanning at least two seconds;
   both wheels must remain in that band and within 75 RPM of each other.
   Do not arm during spin-up. Since 2026-08-07 this is a gate rather than
   discipline: **ARM** and the shot itself both require the MEASURED `L:/R:`
   telemetry to be fresh, inside the band and held for two seconds, and the panel
   shows the countdown. Before that the gates read only the COMMANDED value, so a
   shot the firmware refused for low RPM was still recorded as fired.
   Since 2026-08-11 the window is made of ARRIVALS, and the panel shows both
   halves — `samples n/3` and `span x/2.0 s`. They fail for different reasons: a
   short count means poll again, a short span means wait. A gap longer than two
   seconds restarts the window rather than spanning across it, so three polls
   taken in quick succession and then left to age do **not** satisfy it, and a
   single fresh poll arriving after a silence *clears* an existing ARM. On
   `control_12` this matters directly, because nothing arrives unless you poll:
   the firmware's continuous `L:/R:` stream is sent only to a connected BLE
   client, never over USB.
4. Start side-view slow-motion video with the barrel exit, ruler scale, flight
   region, and first floor contact visible. Recheck the empty controlled area and
   YAW marks, tick room-clear, press **ARM**, then deliberately hold **HOLD TO
   FIRE**. One arm permits one shot.
   **`shoot` is only a request.** The panel goes to `AWAITING FIRMWARE ACK`, and
   the shot counter and the distance field appear only after the firmware reports
   `SYS: SHOT FIRED - FRONT LIMIT HIT`. Nothing else creates a shot record.
   If that acknowledgement does not arrive, the console latches STOP and records
   the outcome as unknown — never as a shot. This is the *expected* outcome of the
   firmware's below-400-RPM refusal, which sends no message at all: `STATE_SHOOTING`
   simply holds the pusher, so a refused shot and a fired one look identical to
   anything watching the command. Treat `SHOT OUTCOME UNKNOWN` as a session ender:
   close the console, confirm spin-down, inspect the chamber, start a new session.
   It is not a fault in the panel and the latch is not clearable from it.
5. After the feeder returns to `IDLE`, command wheel RPM zero. Nobody enters the
   controlled area until both measured values are below 50 RPM. Read this off the
   console's own verdict, which turns from `DO NOT APPROACH` to `WHEELS CONFIRMED
   STOPPED` only when the command is zero, the reading is FRESH, and both wheels
   are under the threshold. A measured value is blanked once its reading goes
   stale, because a frozen `0 / 0` is exactly what would be misread as permission
   here — absent telemetry is never a confirmation of a stopped machine.
6. Measure from the point directly below the barrel exit to the first floor
   contact. The distance field names the shot it will attach to and the RPM that
   shot was fired at — confirm it reads `SHOT <n> @ 500 rpm` before recording, and
   press **RECORD SHOT**. Retain the video filename, the three stable left/right
   RPM polls, the YAW-mark check, and any anomaly note. Record each shot before
   firing the next: the console now **refuses** the second shot until the first
   has its distance, so every ball on the floor keeps exactly one place to attach
   its measurement. `UNDO` is refused for the same reason while a newer confirmed
   shot is waiting.
   The record's `pre-fire L/R` is the last fresh sample that passed the gate
   *before* `shoot`, and the age beside it is measured at request time. It is
   **not** RPM sampled at the front-limit event: the firmware suppresses telemetry
   outside `STATE_IDLE`, so no reading contemporaneous with the shot can exist.
   The model stays indexed by the COMMANDED RPM, which is the only value a
   launcher can be told to reproduce.

Press **STOP** and reject the shot if a person enters, a YAW mark moves, `RELOAD`
causes any YAW movement or visible PITCH movement beyond its known 7-step settle,
spin-up misses its deadline or stability window, `Ball=LOW` or feeder `IDLE` is
absent, the video misses first contact, or any unexpected contact, motion, noise or
smell occurs. Repeat only after understanding the cause and rerunning every gate.

Five valid 500 RPM shots establish only the fixed-direction speed sample and its
spread; do not press **WRITE v(RPM) MODEL** yet.

After the required 500/800/650 passes, enter the measured barrel height, leave
the model kind at `linear`, and press **WRITE v(RPM) MODEL**. The console appends
every measurement to
`garage_lab_combined/cal/blm/rpm_speed_shots.jsonl` and calls the same tested
fitter that writes `garage_lab_combined/cal/blm/rpm_speed_model.json`.

The command-line fitter remains a reproducible cross-check, entering every
individual shot (same-RPM shots are averaged for you):

```bash
./venv/bin/python scripts/fit_rpm_speed.py \
    --height-m <H> --points "500:<d1>,500:<d2>,...,800:<d1>,..." \
    --out garage_lab_combined/cal/blm/rpm_speed_model.json
```

### Method B, per RPM

```bash
# Terminal 1 — viewer, view-only, writing the ball log.
TRACK_BALL=1 BALL_EVERY=1 BALL_IMGSZ=672 \
./Parallel_working/run_live_lowlag.sh \
    --min-active-cameras 5 \
    --ball-log-jsonl Parallel_working/output/ball_logs/rpm800.jsonl
# In the desktop LAUNCHER view, run the same 800 RPM pass and fire 5 shots.
# Then quit the viewer with `q` (never SIGKILL — see .claude/rules/perf.md on
# MP4 finalisation).

./venv/bin/python garage_lab_combined/scripts/calibrate_ball_rpm.py \
    --log Parallel_working/output/ball_logs/rpm800.jsonl --rpm 800
```

## 6. What to record

Keep a plain text log beside the model file. One line per shot, and the four
context facts that make a re-measurement comparable:

```
date  rpm  method  raw_measurement  ball_id  barrel_height_m  pitch_zero_checked  notes
2026-08-05  800  A  3.94 m   ball-01  0.52  yes  -
2026-08-05  800  A  3.88 m   ball-01  0.52  yes  -
2026-08-05  800  B  9.7 m/s  ball-01  0.52  yes  3 usable frame pairs
```

`fit_rpm_speed.py` writes `fit_rmse_mps` and `n_shots` into the model JSON — that
residual **is the deliverable**, not a footnote. A speed without a stated spread
cannot inform a clearance margin.

## 7. Acceptance

- [ ] Ordinary aiming remains blocked until the generic no-fire commissioning gate
      passes, including a physical YAW return to its reference mark. For the
      fixed-YAW speed-only exception, the failed return is recorded, the reference
      marks are restored with drive power removed before the new serial session,
      and the marks remain unchanged through every `RELOAD` and shot.
- [ ] `garage_lab_combined/cal/blm/rpm_speed_model.json` exists and contains
      `fit_rmse_mps` and `n_shots`.
- [ ] Method A and method B agree within 10 % at 800 RPM.
- [ ] Shot-to-shot spread at a single RPM is stated. If the RMSE exceeds ~1 m/s,
      the model is not yet good enough to tighten a clearance margin with — say
      so rather than shipping the number.
- [ ] `live_aim_test.py` picks the model up automatically (its
      `--rpm-speed-model` default is already this path) and reports a derived
      speed instead of `--v-base-mps`.
- [ ] A non-human target test at the calibrated RPM lands where the solver
      predicts, within the accuracy you are willing to state.

## 8. The gap this procedure does NOT close

`build_firing_line_safety_snapshot` / `evaluate_*` in
`src/project_cam/closed_loop/firing_line.py` take **a single scalar
`speed_mps`**. There is no parameter for its uncertainty, so once the model
exists the corridor will still be sampled at the point estimate, with `±rmse`
recorded in a JSON file that no safety code reads.

Closing it is a software change: accept a speed uncertainty and evaluate
clearance over the band `[v − kσ, v + kσ]` rather than at `v`. That is a widening
of the corridor, never a narrowing, and it belongs in the same review as the
first real measurement — it is deliberately **not** implemented ahead of B1,
because there is no σ to feed it yet and safety code should not gain an untested
parameter on speculation. Recorded as a follow-up rather than done quietly.
