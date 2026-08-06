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
shot matrix.

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

This temporary pass is allowed with the current horizontal backlash only because
YAW is physically fixed before the serial link opens. Mark the fixed base and
rotating platform, keep the observed flight corridor clear by at least ±25 cm,
and do not use **YAW**, **CENTER**, or **SET ZERO** during the session. This pass
does not validate aiming accuracy and cannot authorize pose-guided, human-adjacent,
or automatic firing at a person.

Complete the no-fire gate above. Close the aim-only console, enable **ENABLE FIRE
CONTROL**, reopen it, and confirm logical pitch/yaw `0/0` without moving either
aim control.

For each of five shots with the same ball:

1. Press **RELOAD** with wheel command zero and the ball in the vertical lift.
2. Press **POLL FIRMWARE**. Require feeder `IDLE`, `Ball=LOW`, logical aim `0/0`,
   and unchanged physical YAW marks. Any visible aim motion fails the session.
3. Command **500 RPM**. Allow at most 15 seconds for spin-up. Once both measured
   wheels are between 450 and 550 RPM, require three polls spanning at least two seconds;
   both wheels must remain in that band and within 75 RPM of each other.
   Do not arm during spin-up.
4. Start side-view slow-motion video with the barrel exit, ruler scale, flight
   region, and first floor contact visible. Recheck the empty controlled area and
   YAW marks, tick room-clear, press **ARM**, then deliberately hold **HOLD TO
   FIRE**. One arm permits one shot.
5. After the feeder returns to `IDLE`, command wheel RPM zero. Nobody enters the
   controlled area until both measured values are below 50 RPM.
6. Measure from the point directly below the barrel exit to the first floor
   contact. Enter the distance and press **RECORD SHOT**. Retain the video filename,
   the three stable left/right RPM polls, the YAW-mark check, and any anomaly note.

Press **STOP** and reject the shot if a person enters, a YAW mark moves, `RELOAD`
moves an aim axis, spin-up misses its deadline or stability window, `Ball=LOW` or
feeder `IDLE` is absent, the video misses first contact, or any unexpected contact,
motion, noise, or smell occurs. Repeat only after understanding the cause and
rerunning every gate.

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

- [ ] The no-fire commissioning gate passes: small PITCH/YAW moves are visible,
      CENTER returns to the new SET ZERO position, wheels remain at zero, and
      closing the console produces no aim movement.
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
