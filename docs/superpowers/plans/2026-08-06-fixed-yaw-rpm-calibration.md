# Fixed-YAW 500 RPM Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the approved fixed-YAW design into a regression-protected operator procedure, then collect and report five valid Method A landing-distance measurements at 500 RPM without claiming aiming validation.

**Architecture:** The Markdown protocol remains the operator-facing source of truth, while pytest contracts pin its safety-critical order and scope. The existing typed desktop LAUNCHER, Rust renderer, and Python BLM bridge remain the only control path; the operator alone performs the final hold-to-fire gesture. The append-only shot JSONL supplies distance evidence, and a dated report joins it to the measured wheel snapshots and side-video references without writing a one-RPM result as the final linear model.

**Tech Stack:** Markdown, Python 3.10+, pytest, Ruff, the existing React/Tauri desktop LAUNCHER, `garage_lab_combined/scripts/blm_bridge.py`, CP2102 serial link, tape measure, and side-view slow-motion video.

---

## Safety invariants for every task

- [ ] Use only a rigid non-human backstop and an empty controlled corridor.
- [ ] Treat this as exit-speed calibration only. It does not validate aim, compensate YAW backlash, or authorize automatic or human-directed firing.
- [ ] Keep physical YAW fixed. Do not use the YAW slider, `CENTER`, or `SET ZERO` after opening the serial link.
- [ ] Keep PITCH at logical zero and abort on any visible aim movement during `RELOAD`.
- [ ] Never send `fire` from a shell, test helper, or agent tool. The operator must tick room-clear, press `ARM`, and physically hold `HOLD TO FIRE` in the desktop UI.
- [ ] Press `STOP` on any failed gate, unexpected movement, person entry, contact, noise, smell, or uncertain video. Do not record an uncertain shot.
- [ ] Preserve the unrelated untracked `docs/ml_ds_interview_qa_ru.md`; do not stage or modify it.

## Task 1: Pin the reload-first fixed-YAW procedure with failing tests

**Files:**

- Modify: `tests/test_desktop_launcher_console.py`
- Modify: `tests/test_rpm_speed_fit.py`
- Read: `docs/protocols/2026-08-03-rpm-speed-measurement.md`
- Read: `scripts/fit_rpm_speed.py`

- [ ] **Step 1: Add a contract for the fixed-YAW Method A subsection.**

Append this test to `tests/test_desktop_launcher_console.py`:

```python
def fixed_yaw_500_section() -> str:
    protocol = RPM_PROTOCOL.read_text(encoding="utf-8")
    heading = "#### Fixed-YAW 500 RPM speed-only pass"
    assert heading in protocol
    return protocol[
        protocol.index(heading):protocol.index("### Method B, per RPM")
    ]


def test_the_fixed_yaw_500_rpm_pass_is_reload_first():
    section = fixed_yaw_500_section()
    # Firmware RELOAD zeros the wheel targets, so spinning first is not merely
    # inefficient: it leaves the UI, bridge state and physical sequence apart.
    assert section.index("Press **RELOAD**") < section.index("Command **500 RPM**")


def test_the_fixed_yaw_500_rpm_pass_pins_gates_and_claim_boundary():
    section = fixed_yaw_500_section()
    for required in (
        "`Ball=LOW`",
        "three polls spanning at least two seconds",
        "within 75 RPM",
        "below 50 RPM",
        "±25 cm",
        "do not use **YAW**, **CENTER**, or **SET ZERO**",
        "does not validate aiming accuracy",
        "automatic firing at a person",
    ):
        assert required in section, required
```

- [ ] **Step 2: Add a contract for the command-line fitter's operator help.**

Append this test to `tests/test_rpm_speed_fit.py`:

```python
def test_operator_facing_fit_help_is_reload_first():
    source = FIT.read_text(encoding="utf-8")
    procedure = source[source.index("MEASUREMENT (per RPM"):source.index("Usage:")]
    assert procedure.index("reload") < procedure.index("set 0 0 <rpm> <rpm>")
    assert "reload stops the wheel targets" in procedure
    assert "set 0 0 <rpm> <rpm>; reload; shoot" not in source
```

- [ ] **Step 3: Run the two new tests and confirm RED for the intended reasons.**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_desktop_launcher_console.py::test_the_fixed_yaw_500_rpm_pass_is_reload_first \
  tests/test_desktop_launcher_console.py::test_the_fixed_yaw_500_rpm_pass_pins_gates_and_claim_boundary \
  tests/test_rpm_speed_fit.py::test_operator_facing_fit_help_is_reload_first \
  -q -p no:cacheprovider -o addopts=
```

Expected: three failures. The protocol lacks the fixed-YAW subsection and the fitter still documents wheel spin-up before reload. Any import, collection, or unrelated failure must be diagnosed before continuing.

## Task 2: Make the protocol and CLI help executable and frame-correct

**Files:**

- Modify: `docs/protocols/2026-08-03-rpm-speed-measurement.md`
- Modify: `scripts/fit_rpm_speed.py`
- Test: `tests/test_desktop_launcher_console.py`
- Test: `tests/test_rpm_speed_fit.py`

- [ ] **Step 1: Replace the current five-step Method A instructions with the approved fixed-YAW pass.**

Under `### Method A, per RPM`, retain the desktop serial-link introduction and replace the numbered block with this subsection:

```markdown
#### Fixed-YAW 500 RPM speed-only pass

This temporary pass is allowed with the current horizontal backlash only because
YAW is physically fixed before the serial link opens. Mark the fixed base and
rotating platform, keep the observed flight corridor clear by at least ±25 cm,
and do not use **YAW**, **CENTER**, or **SET ZERO** during the session. This pass
does not validate aiming accuracy and cannot authorize pose-guided, human-adjacent,
or automatic firing at a person.

For each of five shots with the same ball:

1. With wheel command zero, place the ball in the vertical lift and press
   **RELOAD**.
2. Press **POLL FIRMWARE**. Require feeder `IDLE`, `Ball=LOW`, logical aim `0/0`,
   and unchanged physical YAW marks. Any visible aim motion fails the session.
3. Command **500 RPM**. Allow at most 15 seconds for spin-up. Once both measured
   wheels are between 450 and 550 RPM, require three polls spanning at least two
   seconds; both wheels must remain in that band and within 75 RPM of each other.
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
```

Keep the existing paragraph about writing a model after the required 500/800/650 passes. Add one sentence immediately before it:

```markdown
Five valid 500 RPM shots establish only the fixed-direction speed sample and its
spread; do not press **WRITE v(RPM) MODEL** yet.
```

- [ ] **Step 2: Correct both operator-facing sequences in `scripts/fit_rpm_speed.py`.**

Replace measurement steps 2–3 in the module docstring with:

```text
  2. With wheel command zero, `reload` and verify feeder IDLE / ball loaded.
     Firmware reload stops the wheel targets, so reload must happen before spin-up.
  3. Aim horizontal, command `set 0 0 <rpm> <rpm>`, wait for stable measured
     wheel RPM, then arm/shoot through the gated desktop LAUNCHER.
```

Replace the interactive prompt that currently says `set ...; reload; shoot` with:

```python
print("\nRELOAD with wheels stopped, then command horizontal RPM, wait for stable telemetry, and shoot through LAUNCHER.")
```

Do not reintroduce `blm_interactive.py` as a firing path.

- [ ] **Step 3: Run the focused tests and confirm GREEN.**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_desktop_launcher_console.py::test_the_fixed_yaw_500_rpm_pass_is_reload_first \
  tests/test_desktop_launcher_console.py::test_the_fixed_yaw_500_rpm_pass_pins_gates_and_claim_boundary \
  tests/test_desktop_launcher_console.py::test_the_rpm_protocol_uses_the_live_ball_profile_that_matches_this_rig \
  tests/test_rpm_speed_fit.py::test_operator_facing_fit_help_is_reload_first \
  -q -p no:cacheprovider -o addopts=
```

Expected: `4 passed`.

- [ ] **Step 4: Run the relevant test files and lint.**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_desktop_launcher_console.py tests/test_rpm_speed_fit.py \
  -q -p no:cacheprovider -o addopts=
venv/bin/python -m ruff check \
  scripts/fit_rpm_speed.py \
  tests/test_desktop_launcher_console.py tests/test_rpm_speed_fit.py
git diff --check
```

Expected: all tests pass, Ruff prints `All checks passed!`, and `git diff --check` is silent.

- [ ] **Step 5: Review and commit only the protocol correction.**

Run:

```bash
git diff -- docs/protocols/2026-08-03-rpm-speed-measurement.md \
  scripts/fit_rpm_speed.py tests/test_desktop_launcher_console.py \
  tests/test_rpm_speed_fit.py
git status --short
git add docs/protocols/2026-08-03-rpm-speed-measurement.md \
  scripts/fit_rpm_speed.py tests/test_desktop_launcher_console.py \
  tests/test_rpm_speed_fit.py
git commit -m "docs(launcher): make fixed-yaw calibration reload-first"
```

Expected: the unrelated `docs/ml_ds_interview_qa_ru.md` remains untracked and unstaged.

## Task 3: Establish the pre-shot evidence baseline

**Files:**

- Read: `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl` if present
- Read: `garage_lab_combined/cal/blm/rpm_speed_model.json` if present
- Read: `garage_lab_combined/output/sessions/*/manifest.json`
- Read: `garage_lab_combined/output/sessions/*/lifecycle.jsonl`
- Do not modify the launcher model in this task.

- [ ] **Step 1: Verify the desktop binary and software gates before touching fire control.**

Run:

```bash
bash project-cam-desktop/check-binary-fresh.sh
venv/bin/python -m pytest tests/test_blm_bridge.py \
  tests/test_desktop_launcher_console.py tests/test_rpm_speed_fit.py \
  -q -p no:cacheprovider -o addopts=
```

Expected: freshness exit `0` and all selected tests pass.

- [ ] **Step 2: Record the model's pre-run state without changing it.**

Run:

```bash
test -f garage_lab_combined/cal/blm/rpm_speed_model.json \
  && sha256sum garage_lab_combined/cal/blm/rpm_speed_model.json \
  || echo "rpm_speed_model.json absent before 500 RPM pass"
test -f garage_lab_combined/cal/blm/rpm_speed_shots.jsonl \
  && wc -l garage_lab_combined/cal/blm/rpm_speed_shots.jsonl \
  || echo "rpm_speed_shots.jsonl absent before 500 RPM pass"
```

Copy these exact results into the final report. Do not click **WRITE v(RPM) MODEL** during the 500 RPM pass.

- [ ] **Step 3: Resolve the launcher identity read-only.**

Run:

```bash
ls -l /dev/serial/by-id/ /dev/ttyUSB* 2>/dev/null
lsusb | grep -i "10c4:ea60"
```

Expected: the CP2102 stable by-id link resolves to one `ttyUSB` node. Do not open the port from a second process after the desktop console owns it.

- [ ] **Step 4: Establish the physical fixed-YAW reference before opening serial.**

Operator actions:

1. Wheels stopped and launcher power state understood.
2. Barrel exit height confirmed as `H = 0.50 m`.
3. Barrel level and aimed at the center of the non-human backstop.
4. Base/platform YAW marks aligned and photographed.
5. At least ±25 cm around the observed flight line clear of computer, cameras, cables, and people.
6. Tape/ruler and side-view phone frame show barrel exit and first floor contact.
7. Same ball ready in the vertical lift.

If any item is missing, stop before opening a fire-enabled console.

## Task 4: Execute the five-shot 500 RPM pass with manual fire only

**Control surface:** desktop `LAUNCHER` view only.

**Evidence generated:**

- `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl`
- the newest launcher session under `garage_lab_combined/output/sessions/`
- five external side-view video files
- operator-read stable RPM snapshots for the dated report

- [ ] **Step 1: Open the console and establish the baseline.**

Operator actions:

1. Open the desktop app and enter `LAUNCHER`.
2. Confirm the automatically selected device is the CP2102 stable by-id launcher.
3. Enable **ENABLE FIRE CONTROL** and press **OPEN CONSOLE**.
4. Press **POLL FIRMWARE** only. Require logical aim `0/0`, measured RPM `0/0`, and feeder `IDLE`.
5. Visually confirm the YAW marks did not move when the serial link opened.

Do not touch the YAW, PITCH, `CENTER`, or `SET ZERO` controls.

- [ ] **Step 2: Run this gate separately for shot 1.**

1. At wheel command zero, press **RELOAD**.
2. Poll: require `IDLE`, `Ball=LOW`, logical `0/0`, measured RPM `0/0`, and unchanged YAW marks.
3. Select **500 RPM**.
4. Within 15 seconds obtain three polls over at least two seconds where L/R are each 450–550 and differ by no more than 75 RPM. Write the three L/R pairs down.
5. Start video and state its filename/reference.
6. Recheck empty corridor and YAW marks.
7. The operator ticks room-clear, presses **ARM**, and physically holds **HOLD TO FIRE**. The agent does not issue a fire command.
8. Wait for feeder `IDLE`, command wheel RPM zero, and poll until L/R are both below 50.
9. Review video, measure first-contact distance, enter it in **LANDING DISTANCE**, and press **RECORD SHOT**.

Abort with **STOP** and do not record if any check fails.

- [ ] **Step 3: Repeat the complete gate for shots 2–5.**

Each repetition starts again at `RELOAD` with wheel command zero and requires a new room-clear acknowledgement, a new arm, a new video, three new stable RPM polls, and a new post-shot `<50 RPM` entry gate. Never infer later shots from shot 1.

- [ ] **Step 4: Close safely.**

After shot 5 is recorded and wheels are measured below 50 RPM:

1. Press **STOP**.
2. Close the console/app.
3. Confirm the barrel does not move on shutdown; the default shutdown path sends `stop` only.
4. Keep the YAW marks and apparatus unchanged until the evidence audit in Task 5 is complete.

## Task 5: Audit the evidence and compute speed spread without writing a model

**Files:**

- Create: `docs/reports/2026-08-06-fixed-yaw-500rpm-calibration.md`
- Read: `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl`
- Read: newest launcher session `manifest.json` and `lifecycle.jsonl`
- Read: five side-view videos supplied by the operator
- Do not create or update: `garage_lab_combined/cal/blm/rpm_speed_model.json`

- [ ] **Step 1: Resolve the exact session and audit command order.**

Select the newest session whose manifest label is `BLM CONSOLE · FIRE ENABLED` and record its explicit session ID. Inspect its lifecycle and require:

- five `fire` intents if every attempt was valid; any additional attempt must be
  explicitly documented as rejected and must have no corresponding measurement;
- a fresh `reload` before each wheel-spin/arm/fire cycle;
- no `aim` with non-zero PITCH or YAW;
- no `center` or `set_zero` intent;
- `stop` at shutdown.

If lifecycle evidence contradicts the operator record, mark the pass invalid rather than editing the log.

- [ ] **Step 2: Audit append-only measurements.**

Filter `rpm_speed_shots.jsonl` by the resolved session ID. Require exactly five non-retracted `measurement` records, each with `rpm = 500` and a positive landing distance. Cross-check all five distances against the UI entries and the videos.

- [ ] **Step 3: Compute per-shot speed and spread read-only.**

Use the existing tested function `scripts.fit_rpm_speed.speed_from_drop` with `H = 0.50 m` and `g = 9.81 m/s²`. Report for every shot:

```text
v_i = distance_i * sqrt(9.81 / (2 * 0.50))
```

Then report `n = 5`, mean speed, population standard deviation (the same definition used by the constant-model branch), min/max, and range. Do not call the CLI fitter because it writes a model file. A standard deviation above `1.0 m/s` is a diagnostic failure requiring investigation, matching the existing bridge warning; it is not to be hidden by averaging.

- [ ] **Step 4: Write the dated report with explicit claim boundaries.**

Create `docs/reports/2026-08-06-fixed-yaw-500rpm-calibration.md` with:

```markdown
# Fixed-YAW 500 RPM Calibration Report — 2026-08-06

**Status:** valid / invalid (state why)
**Session ID:** exact launcher session ID
**Scope:** exit-speed repeatability at one fixed physical direction only
**Height:** 0.50 m
**Model before/after:** exact absence or SHA-256; must be unchanged

| Shot | Stable L/R polls (RPM) | Distance (m) | Speed (m/s) | Video | YAW mark | Notes |
|---:|---|---:|---:|---|---|---|
| 1 | ... | ... | ... | ... | unchanged | ... |
| 2 | ... | ... | ... | ... | unchanged | ... |
| 3 | ... | ... | ... | ... | unchanged | ... |
| 4 | ... | ... | ... | ... | unchanged | ... |
| 5 | ... | ... | ... | ... | unchanged | ... |

## Result

- Mean: ... m/s
- Population standard deviation: ... m/s
- Min / max / range: ... m/s

## Claim boundary

This pass does not validate aiming accuracy, YAW repeatability, human clearance,
pose-guided firing, human-adjacent firing, or automatic firing at a person. The
final v(RPM) model remains blocked on the 800 and 650 RPM passes and the independent
Method B cross-check at 800 RPM.
```

Replace every ellipsis with observed evidence. Do not publish a report containing placeholders.

- [ ] **Step 5: Verify the model was not written.**

Repeat the exact pre-run absence/checksum command from Task 3. Expected: the model remains absent or has the identical SHA-256.

- [ ] **Step 6: Commit the auditable evidence only after review.**

Run:

```bash
git diff --check
git status --short
git add docs/reports/2026-08-06-fixed-yaw-500rpm-calibration.md \
  garage_lab_combined/cal/blm/rpm_speed_shots.jsonl
git commit -m "docs(launcher): record fixed-yaw 500 rpm calibration"
```

If the shot log contains pre-existing unrelated sessions, stage it only after reviewing every added line. Do not stage videos or `docs/ml_ds_interview_qa_ru.md`.

## Task 6: Final verification and branch handoff

**Files:** all files changed on `feature/fixed-yaw-rpm-calibration`.

- [ ] **Step 1: Run the complete verification surface.**

Run:

```bash
venv/bin/python -m ruff check \
  scripts/fit_rpm_speed.py tests/test_desktop_launcher_console.py \
  tests/test_rpm_speed_fit.py
venv/bin/python -m pytest -q -p no:cacheprovider -o addopts=
cd project-cam-desktop
./node_modules/.bin/tsc --noEmit
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test -q
cd ../..
bash project-cam-desktop/check-binary-fresh.sh
git diff --check
```

Expected: Ruff clean, complete Python suite green, TypeScript clean, Rust fmt/clippy/tests green, release binary fresh, and no whitespace errors.

- [ ] **Step 2: Review the branch boundary.**

Run:

```bash
git log --oneline master..HEAD
git diff --stat master...HEAD
git status --short
```

Expected: the branch contains the approved design, the reload-first protocol/test commit, and—only if the physical pass was valid—the evidence commit. The unrelated ML/DS document remains outside the branch commits.

- [ ] **Step 3: Use `superpowers:verification-before-completion` and then `superpowers:finishing-a-development-branch`.**

Do not merge or claim completion until the fresh outputs above have been inspected. Present the valid choices (fast-forward local `master`, keep the branch, or publish a PR if a remote is later configured) to the user; do not infer permission to publish externally.
