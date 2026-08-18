# Fixed-YAW Speed Measurement Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the YAW/reload evidence, then collect five valid horizontal first-contact distances at 500 RPM and calculate the ball's exit-speed sample without claiming YAW calibration or writing a final multi-RPM model.

**Architecture:** Keep the existing fixed-YAW isolation: adopt the aligned physical pose as logical `0/0` at boot and issue no YAW, `CENTER`, or `SET ZERO` intent during the firing session. The 6--7 degree direction-reversal lost motion is deferred as a mechanical diagnosis and is never software-compensated. The existing confirmed-shot bridge remains the only serial writer and the existing landing-distance fitter remains the only speed calculation.

**Tech Stack:** Markdown safety contracts, pytest source-contract tests, Python 3 bridge/fitter, `control_14` firmware, CP2102 serial link.

---

### Task 1: Pin the corrected fixed-YAW evidence

**Files:**
- Modify: `tests/test_desktop_launcher_console.py`
- Read: `control_14_full.ino:307-322`
- Test: `tests/test_desktop_launcher_console.py`

- [ ] **Step 1: Write the failing documentation contract**

Add a design-path constant and a test that requires all four corrected facts:

```python
FIXED_YAW_DESIGN = ROOT / "docs/superpowers/specs/2026-08-06-fixed-yaw-rpm-calibration-design.md"


def test_fixed_yaw_speed_pass_records_lost_motion_without_software_compensation():
    design = FIXED_YAW_DESIGN.read_text(encoding="utf-8")
    section = fixed_yaw_500_section()
    for required in (
        "6--7 degrees",
        "lost motion",
        "must not be compensated in software",
        "mechanical diagnosis is deferred",
        "7 steps",
        "0.042",
    ):
        assert required in design + section, required
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
./venv/bin/python -m pytest \
  tests/test_desktop_launcher_console.py::test_fixed_yaw_speed_pass_records_lost_motion_without_software_compensation \
  -q -p no:cacheprovider -o addopts=
```

Expected: `FAIL`, first on wording that the current documents do not contain.

### Task 2: Correct the operator-facing evidence

**Files:**
- Modify: `docs/superpowers/specs/2026-08-06-fixed-yaw-rpm-calibration-design.md`
- Modify: `docs/protocols/2026-08-03-rpm-speed-measurement.md`
- Modify: `.claude/rules/safety.md`
- Modify: `CLAUDE.md`
- Test: `tests/test_desktop_launcher_console.py`

- [ ] **Step 1: Replace the unsupported backlash diagnosis**

Record the observed quantity as direction-reversal **lost motion**, not normal worm-gear backlash. State that software compensation is prohibited until the mechanical chain is inspected and the residual is remeasured after repair. Record the operator decision on 2026-08-18 to defer that mechanical diagnosis while performing only a fixed-direction, non-human speed measurement.

- [ ] **Step 2: Document what `reload` actually commands**

Record the exact firmware behavior:

```text
horzStepper.moveTo(0) leaves YAW stationary only while boot zero and the physical
reference mark still agree. vertStepper.moveTo(7) is not exact PITCH zero: at
STEPS_PER_DEG_VERT = 166.67 it is about +0.042 degrees on every reload.
```

Do not call the 7-step offset zero and do not claim it is position feedback.

- [ ] **Step 3: Preserve the narrow fixed-YAW boundary**

Require physical marks aligned before serial open; prohibit YAW, `CENTER`, and `SET ZERO`; abort on any mark movement, including during `reload`; retain the non-human backstop and cleared corridor. State explicitly that the pass measures speed only and leaves ordinary aiming uncommissioned.

- [ ] **Step 4: Run the new test and verify GREEN**

Run:

```bash
./venv/bin/python -m pytest \
  tests/test_desktop_launcher_console.py::test_fixed_yaw_speed_pass_records_lost_motion_without_software_compensation \
  -q -p no:cacheprovider -o addopts=
```

Expected: `1 passed`.

- [ ] **Step 5: Run the complete documentation/bridge regression set**

Run:

```bash
./venv/bin/python -m pytest \
  tests/test_blm_bridge.py \
  tests/test_desktop_launcher_console.py \
  tests/test_rpm_speed_fit.py \
  -q -p no:cacheprovider -o addopts=
git diff --check
```

Expected: all selected tests pass; `git diff --check` exits `0`.

- [ ] **Step 6: Commit the documentation correction**

```bash
git add tests/test_desktop_launcher_console.py \
  docs/superpowers/specs/2026-08-06-fixed-yaw-rpm-calibration-design.md \
  docs/protocols/2026-08-03-rpm-speed-measurement.md \
  .claude/rules/safety.md CLAUDE.md \
  docs/superpowers/plans/2026-08-18-fixed-yaw-speed-measurement-resume.md
git commit -m "docs(blm): defer yaw repair during fixed-speed pass"
```

### Task 3: Establish the read-only pre-run evidence

**Files:**
- Read: `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl`
- Read: `garage_lab_combined/cal/blm/rpm_speed_model.json` if it exists
- Read: `project-cam-desktop/check-binary-fresh.sh`

- [ ] **Step 1: Verify the software baseline**

Run:

```bash
bash project-cam-desktop/check-binary-fresh.sh
./venv/bin/python -m pytest \
  tests/test_blm_bridge.py tests/test_desktop_launcher_console.py \
  tests/test_rpm_speed_fit.py \
  -q -p no:cacheprovider -o addopts=
```

Expected: freshness exits `0`; all focused tests pass.

- [ ] **Step 2: Record the calibration-artifact baseline**

Run:

```bash
test -f garage_lab_combined/cal/blm/rpm_speed_model.json \
  && sha256sum garage_lab_combined/cal/blm/rpm_speed_model.json \
  || echo "rpm_speed_model.json absent before 500 RPM pass"
wc -l garage_lab_combined/cal/blm/rpm_speed_shots.jsonl
```

Expected from the 2026-08-18 inspection: no model file and four legacy fire-only lines. Re-read rather than relying on that prior snapshot.

- [ ] **Step 3: Resolve exclusive serial ownership**

Run:

```bash
readlink -f /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
fuser /dev/ttyUSB* 2>/dev/null || true
```

Expected: the by-id link resolves to one node and no other serial writer owns it.

### Task 4: Re-establish fixed-YAW before enabling fire

**Files:**
- Execute: `garage_lab_combined/scripts/blm_bridge.py`
- Record: `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl`

- [ ] **Step 1: Obtain fresh physical confirmations**

Require the operator to confirm all of: motor is silent; the launcher is empty; the barrel is physically level; YAW marks are aligned; the rigid non-human backstop and first-contact floor region are clear; ESTOP is reachable; launch height is measured; the same marked ball and side-view slow-motion camera are ready.

- [ ] **Step 2: Open one fire-enabled bridge session**

Run only after Step 1:

```bash
./venv/bin/python -u garage_lab_combined/scripts/blm_bridge.py \
  --serial-port /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0 \
  --baud 921600 --allow-fire
```

Do not pass `--center-on-exit`. Confirm `control_14`, logical `0/0`, wheel `0/0`, feeder `IDLE`, and no physical aim movement at boot. Do not send YAW, `center`, or `set_zero`.

### Task 5: Collect five confirmed 500-RPM distances

**Files:**
- Execute: `garage_lab_combined/scripts/blm_bridge.py`
- Append: `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl`

- [ ] **Step 1: Reload one ball at wheel command zero**

Send `reload` only after the operator places the ball in the vertical lift. Poll and require feeder `IDLE`, loaded ball indication, logical `0/0`, and unchanged YAW marks. Abort if either aim axis visibly moves.

- [ ] **Step 2: Spin to the lowest calibrated pass**

Send `wheels 500`. Require three separate fresh samples spanning at least two seconds, both wheels in `450..550`, and left/right spread at most `75`. Abort if stability is absent after 15 seconds.

- [ ] **Step 3: Confirm the shot deliberately**

Require side-view slow motion recording, an empty controlled area, visible unchanged YAW marks, and an explicit per-shot operator confirmation. Send `arm`, then `fire`. Accept only `SYS: SHOT FIRED - FRONT LIMIT HIT` as a shot.

- [ ] **Step 4: Stop and wait for safe approach**

Send `wheels 0`. Nobody enters until `safe_to_approach=true` from fresh telemetry; do not put hands near flywheels until both reach true zero.

- [ ] **Step 5: Record first-contact distance**

Measure from the floor point directly below the barrel exit to the first floor contact and send `measure <distance_m>`. Retain video filename, launch height, stable pre-fire L/R pair, and YAW-mark result.

- [ ] **Step 6: Repeat Steps 1--5 four more times**

Each shot requires a new `reload`, stability window, room-clear confirmation, arm, fire acknowledgement, spin-down, and distance. Never batch-authorize the five shots.

### Task 6: Calculate the 500-RPM speed sample without writing the final model

**Files:**
- Read: `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl`
- Execute: `scripts/fit_rpm_speed.py`
- Do not create: `garage_lab_combined/cal/blm/rpm_speed_model.json`

- [ ] **Step 1: Calculate every shot with the measured launch height**

For each valid distance `d` and measured height `H`, calculate:

```text
v_mps = d * sqrt(9.81 / (2 * H))
v_kmh = 3.6 * v_mps
```

Use `scripts.fit_rpm_speed.speed_from_drop` for the executable calculation; do not duplicate a different formula.

- [ ] **Step 2: Report mean and shot-to-shot spread**

Report all five `m/s` and `km/h` values, their mean, population standard deviation, exact launch height, and the five pre-fire L/R snapshots. Do not create the final model after only the 500-RPM pass.

- [ ] **Step 3: Close the session safely**

Send `stop`, wait for fresh true-zero telemetry, then `quit`. Confirm no aim movement on shutdown. Record whether the five-shot pass is accepted or rejected and why.

### Task 7: Defer the remaining curve and km/h desktop control explicitly

**Files:**
- Read: `docs/protocols/2026-08-03-rpm-speed-measurement.md`
- Future spec: `docs/superpowers/specs/2026-08-18-calibrated-kmh-launcher-control-design.md`

- [ ] **Step 1: Preserve the required later evidence**

Do not call the 500-RPM constant a full operating curve. The next live passes remain five shots at 800 RPM and three at 650 RPM, plus Method B cross-check at 800 RPM.

- [ ] **Step 2: Design km/h control only after a valid model exists**

The later desktop design makes calibrated km/h the primary operator control while retaining commanded/measured RPM as technical safety telemetry and shot evidence. Missing, invalid, non-monotonic, or out-of-range models must refuse a km/h command rather than fall back to guessed RPM.
