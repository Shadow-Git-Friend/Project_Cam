# Measuring ball exit speed v(RPM) — operator procedure

**Roadmap item A6** (the desk half of blocker **B1**). One operator, one session,
no assistant required. Read it once end to end before firing anything.

Everything below was checked against the code on 2026-08-03; the tools named
here exist in the main tree and their flags are quoted verbatim.

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
      including you: every shot in this procedure is fired at a wall or net.
- [ ] ESTOP reachable from where you stand. `stop` latches until `clear`.
- [ ] Same ball for every shot, and the same one you will train with. Ball mass
      and surface change the exit speed; a mixed set makes the fit meaningless.
- [ ] Barrel exit height above the floor measured once with a tape, in metres.
      Write it down — method A is proportional to `sqrt(1/H)`, so a 2 cm error in
      H is about a 2 % error in every speed.
- [ ] **Check that pitch 0 is truly horizontal with a level.** A mechanical tilt
      at the zero position biases method A directly, and it is the single largest
      error source in it.

## 3. Two methods, and why you run both

| | Method A — landing distance | Method B — camera-tracked speed |
|---|---|---|
| Tool | `scripts/fit_rpm_speed.py` | `garage_lab_combined/scripts/calibrate_ball_rpm.py` |
| Measures | where the ball first hits the floor | 3D ball displacement between frames |
| Needs | tape measure, level | the 6-camera viewer running with `--ball-log-jsonl` |
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

Mitigations, all already available:

```
--ball-imgsz 960          # the dominant lever: camNorth bounce 58% -> 98%
--ball-conf 0.25          # safe with the KF gate on (default 150 px)
--ball-single-cam-fallback
```

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

```bash
# Terminal 1 — raw serial, no cameras needed.
./venv/bin/python garage_lab_combined/scripts/blm_interactive.py --port /dev/ttyUSB0
#   set 0 0 800 800      -> horizontal, wheels to 800 RPM (firmware gates <400)
#   reload
#   shoot
# Measure d = floor distance from the point directly BELOW the barrel to the
# FIRST floor contact. Repeat 5x without changing anything.
```

Then fit, entering every individual shot (same-RPM shots are averaged for you):

```bash
./venv/bin/python scripts/fit_rpm_speed.py \
    --height-m <H> --points "500:<d1>,500:<d2>,...,800:<d1>,..." \
    --out garage_lab_combined/cal/blm/rpm_speed_model.json
```

### Method B, per RPM

```bash
# Terminal 1 — viewer, view-only, writing the ball log.
./Parallel_working/run_live_usb6_mirrored_skeleton.sh \
    --ball-imgsz 960 --ball-conf 0.25 --ball-single-cam-fallback \
    --ball-log-jsonl Parallel_working/output/ball_logs/rpm800.jsonl
# Terminal 2 — blm_interactive.py as above. Fire 5 shots. Then quit the viewer
# with `q` (never SIGKILL — see .claude/rules/perf.md on MP4 finalisation).

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
