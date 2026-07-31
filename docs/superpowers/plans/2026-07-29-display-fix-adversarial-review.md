# Display-Fix Adversarial Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the four interrupted adversarial-review lenses, lock the verified display/state and per-athlete lifecycle contracts with tests, fact-check the technical report, and regenerate its DOCX.

**Architecture:** Keep runtime behavior in the existing live viewer and the focused `project_cam.viz.skeleton_stabilize` module; add narrow behavioral and structural contracts instead of refactoring the camera loop. Treat the Markdown report as the source of truth, record claim provenance in a separate fact-check ledger, and generate the DOCX through the existing builder.

**Tech Stack:** Python 3.10, NumPy, pytest, pathlib/regular expressions for inline-main wiring contracts, Pandoc, python-docx, Pillow.

---

## Working-Tree Constraint

Execute this plan in `/home/hanush/Desktop/Project_Cam` on
`feature/multi-person-face-id-desktop-20260712`. Do not create a clean
worktree: the reviewed display, training, desktop, and report work exists only
in the current dirty tree. Preserve unrelated changes.

Do not run `git commit`. The project session record says commits are performed
by the user. Each task ends with a scoped diff/status checkpoint instead.

## File Map

- Create `tests/test_display_state_isolation.py`: behavioral copy/alias check
  plus structural contracts for coach, UDP, BLM, and safety consumers.
- Modify `tests/test_skeleton_stabilize.py`: mathematical convergence,
  degenerate-bone, root-outward, and rigid-transform invariants.
- Create `tests/test_skeleton_stabilize_integration.py`: primary handoff,
  bank-reset, filtered/display-buffer, and secondary-state wiring contracts.
- Modify `Parallel_working/scripts/live_4cam_arena_view_parallel.py` only if
  one of the new contracts produces a concrete failure.
- Modify `src/project_cam/viz/skeleton_stabilize.py` only if a mathematical
  reproducer fails.
- Create
  `docs/reports/project_cam_technical_system_report_fact_check_2026-07-29.md`:
  claim-to-source ledger and disposition.
- Modify `docs/reports/project_cam_technical_system_report_en.md`: correct
  stale snapshot/test evidence and any other claim contradicted by the ledger.
- Modify `scripts/build_project_cam_technical_system_report.py`: update the
  generated document evidence date.
- Modify `tests/test_project_cam_report_builder.py`: guard the evidence date,
  completed suite result, and fact-check ledger.
- Regenerate `docs/Project_Cam_Technical_System_Report_EN.docx`.
- Modify `CLAUDE.md`: append the completed review outcome and exact evidence.

### Task 1: Lock the display/state isolation boundary

**Files:**
- Create: `tests/test_display_state_isolation.py`
- Read/conditionally modify:
  `Parallel_working/scripts/live_4cam_arena_view_parallel.py:5250-5565`
- Test: `tests/test_display_state_isolation.py`

- [ ] **Step 1: Add the two isolation contract tests**

Create `tests/test_display_state_isolation.py` with:

```python
import re
from pathlib import Path

import numpy as np

from project_cam.viz.skeleton_stabilize import (
    BoneLengthBank,
    stabilize_display_skeleton,
)


LIVE = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")


def _section(source, start, end):
    assert start in source, f"missing start marker: {start}"
    assert end in source, f"missing end marker: {end}"
    return source.split(start, 1)[1].split(end, 1)[0]


def _pose():
    joints = np.full((17, 3), np.nan, dtype=np.float32)
    joints[5] = (-180.0, 0.0, 1450.0)
    joints[6] = (180.0, 0.0, 1450.0)
    joints[7] = (-210.0, 0.0, 1160.0)
    joints[8] = (210.0, 0.0, 1160.0)
    joints[9] = (-230.0, 0.0, 890.0)
    joints[10] = (230.0, 0.0, 890.0)
    joints[11] = (-95.0, 0.0, 950.0)
    joints[12] = (95.0, 0.0, 950.0)
    joints[13] = (-100.0, 0.0, 530.0)
    joints[14] = (100.0, 0.0, 530.0)
    joints[15] = (-105.0, 0.0, 90.0)
    joints[16] = (105.0, 0.0, 90.0)
    return joints


def test_display_transform_cannot_mutate_state_through_aliasing():
    state = _pose()
    state_before = state.copy()
    bank = BoneLengthBank(min_samples=1)
    bank.observe(state)

    filtered = state.copy()
    filtered += np.float32([120.0, -40.0, 10.0])
    filtered[15] = filtered[13] + 1.8 * (filtered[15] - filtered[13])
    display = filtered.copy()
    stabilize_display_skeleton(display, bank, tol=0.12, soft=0.45)

    assert not np.shares_memory(state, filtered)
    assert not np.shares_memory(state, display)
    np.testing.assert_array_equal(state, state_before)
    assert not np.array_equal(display, filtered)


def test_measurement_and_safety_consumers_are_wired_to_state():
    source = LIVE.read_text(encoding="utf-8")
    frame_inputs = re.findall(
        r"joints_array_to_frame\(\s*(joints_[a-z_]+)", source
    )
    assert frame_inputs
    assert set(frame_inputs) == {"joints_state"}

    udp = _section(source, 'timer.start("udp")', 'timer.stop("udp")')
    assert "joints_display" not in udp
    assert "joints_filtered" not in udp
    assert "pt = joints_state[idx]" in udp
    assert '"joints": joints_state' in udp

    blm = _section(
        source,
        "# --- BLM Demo: compute aim from current joints ---",
        "# update cinematic motion trails",
    )
    assert "j_pos = joints_state[j_idx]" in blm
    assert "joints_display[j_idx]" not in blm
    assert "joints=joints_display.copy()" in source
```

- [ ] **Step 2: Run the new tests**

Run:

```bash
venv/bin/python -m pytest -o addopts='' tests/test_display_state_isolation.py -v
```

Expected: `2 passed`. A failure is a confirmed isolation defect, not a reason
to weaken the assertion.

- [ ] **Step 3: Correct only a reproduced wiring or alias defect**

If the alias test fails, ensure every presentation stage starts from an
independent buffer:

```python
joints_display[:] = joints_filtered
```

and keep `stabilize_display_skeleton(joints_display, ...)` after that copy.
Never pass `joints_state` or `joints_filtered` to the in-place clamp.

If a sink test fails, replace only the offending display-buffer input with
`joints_state`. The required forms are:

```python
coach_frame = joints_array_to_frame(
    joints_state, joints_conf_state, joints_cam_state, frame_idx, args.fps
)
pt = joints_state[idx]
primary_state={
    "joints": joints_state,
    "conf": joints_conf_state,
    "cams": joints_cam_state,
    "last_seen": joint_last_seen_frame,
}
j_pos = joints_state[j_idx] if joints_state is not None else None
```

Do not change rendering or Face-ID association, which may legitimately use
display coordinates.

- [ ] **Step 4: Re-run the isolation tests and inspect the scoped diff**

Run:

```bash
venv/bin/python -m pytest -o addopts='' tests/test_display_state_isolation.py -v
git diff --check -- tests/test_display_state_isolation.py Parallel_working/scripts/live_4cam_arena_view_parallel.py
git diff -- tests/test_display_state_isolation.py Parallel_working/scripts/live_4cam_arena_view_parallel.py
```

Expected: `2 passed`, no whitespace errors, and no changes to UDP/safety
semantics beyond restoring `joints_state` if a failure was found.

### Task 2: Complete the skeleton-clamp mathematical review

**Files:**
- Modify: `tests/test_skeleton_stabilize.py`
- Read/conditionally modify: `src/project_cam/viz/skeleton_stabilize.py`
- Test: `tests/test_skeleton_stabilize.py`

- [ ] **Step 1: Add convergence and degenerate-input tests**

Append:

```python
def test_soft_clamp_converges_geometrically_without_overshoot():
    pose = make_pose()
    bank = locked_bank(pose)
    learned = bone_len(pose, 13, 15)
    upper = learned * 1.12
    joints = pose.copy()
    direction = (joints[15] - joints[13]).astype(np.float64)
    joints[15] = joints[13] + (
        direction / np.linalg.norm(direction) * learned * 1.8
    ).astype(np.float32)

    overflow = []
    for _ in range(6):
        stabilize_display_skeleton(joints, bank, tol=0.12, soft=0.45)
        overflow.append(max(0.0, bone_len(joints, 13, 15) - upper))

    assert all(b < a for a, b in zip(overflow, overflow[1:]))
    for previous, current in zip(overflow, overflow[1:]):
        assert current == pytest.approx(previous * 0.45, rel=2e-4)
    assert all(value >= 0.0 for value in overflow)


def test_zero_length_bone_is_skipped_without_nan_spread():
    pose = make_pose()
    bank = locked_bank(pose)
    joints = pose.copy()
    joints[9] = joints[7]
    before_elbow = joints[7].copy()

    stabilize_display_skeleton(joints, bank, tol=0.12, soft=0.45)

    np.testing.assert_array_equal(joints[7], before_elbow)
    np.testing.assert_array_equal(joints[9], before_elbow)
    assert np.isfinite(joints[[5, 7, 9]]).all()
```

- [ ] **Step 2: Add root-outward and rigid-transform tests**

Append:

```python
def test_hard_clamp_solves_shared_joint_chain_root_outward():
    pose = make_pose()
    bank = locked_bank(pose)
    femur = bone_len(pose, 11, 13)
    tibia = bone_len(pose, 13, 15)
    femur_dir = (pose[13] - pose[11]).astype(np.float64)
    tibia_dir = (pose[15] - pose[13]).astype(np.float64)
    joints = pose.copy()
    joints[13] = joints[11] + (
        femur_dir / np.linalg.norm(femur_dir) * femur * 1.5
    ).astype(np.float32)
    joints[15] = joints[13] + (
        tibia_dir / np.linalg.norm(tibia_dir) * tibia * 1.5
    ).astype(np.float32)

    stabilize_display_skeleton(joints, bank, tol=0.10, soft=0.0)

    assert bone_len(joints, 11, 13) == pytest.approx(femur * 1.10, rel=1e-4)
    assert bone_len(joints, 13, 15) == pytest.approx(tibia * 1.10, rel=1e-4)


def test_clamp_is_equivariant_under_rigid_world_transform():
    pose = make_pose()
    bank = locked_bank(pose)
    theta = np.deg2rad(37.0)
    rotation = np.array(
        [
            [np.cos(theta), -np.sin(theta), 0.0],
            [np.sin(theta), np.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    translation = np.array([700.0, -230.0, 90.0])

    for dtype in (np.float32, np.float64):
        distorted = pose.astype(dtype)
        distorted[15] = distorted[13] + 1.6 * (
            distorted[15] - distorted[13]
        )
        corrected = distorted.copy()
        stabilize_display_skeleton(corrected, bank, tol=0.12, soft=0.45)
        transformed = (
            distorted.astype(np.float64) @ rotation.T + translation
        ).astype(dtype)
        stabilize_display_skeleton(transformed, bank, tol=0.12, soft=0.45)
        expected = (
            corrected.astype(np.float64) @ rotation.T + translation
        ).astype(dtype)

        np.testing.assert_allclose(
            transformed, expected, atol=2e-3, equal_nan=True
        )
```

- [ ] **Step 3: Run the four tests in isolation**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_skeleton_stabilize.py::test_soft_clamp_converges_geometrically_without_overshoot \
  tests/test_skeleton_stabilize.py::test_zero_length_bone_is_skipped_without_nan_spread \
  tests/test_skeleton_stabilize.py::test_hard_clamp_solves_shared_joint_chain_root_outward \
  tests/test_skeleton_stabilize.py::test_clamp_is_equivariant_under_rigid_world_transform -v
```

Expected: `4 passed`. If they pass, the suspected order dependence is the
documented root-outward algorithm and needs no runtime change.

- [ ] **Step 4: Apply the only allowed fixes if a mathematical contract fails**

For a zero-length failure, keep the existing explicit skip before division:

```python
length = float(np.linalg.norm(vec))
if length <= 1e-6:
    continue
```

For a root-order failure, retain the current outer-to-inner traversal and
always re-read endpoints after the parent was corrected:

```python
for chain in LIMB_CHAINS:
    for a, b in zip(chain[:-1], chain[1:]):
        pa, pb = joints[a], joints[b]
```

For a convergence failure, keep `_soft_clamp_len` as the affine contraction:

```python
if length > hi:
    return hi + soft * (length - hi)
if length < lo:
    return lo - soft * (lo - length)
```

Do not add an iterative solver; one soft pass per rendered frame is the
designed behavior.

- [ ] **Step 5: Run the full stabilization file and inspect the scoped diff**

Run:

```bash
venv/bin/python -m pytest -o addopts='' tests/test_skeleton_stabilize.py -v
git diff --check -- tests/test_skeleton_stabilize.py src/project_cam/viz/skeleton_stabilize.py
git diff -- tests/test_skeleton_stabilize.py src/project_cam/viz/skeleton_stabilize.py
```

Expected: `17 passed`, no whitespace errors.

### Task 3: Lock primary-athlete and multi-person lifecycle wiring

**Files:**
- Create: `tests/test_skeleton_stabilize_integration.py`
- Read/conditionally modify:
  `Parallel_working/scripts/live_4cam_arena_view_parallel.py:4394-4450`
- Test: `tests/test_skeleton_stabilize_integration.py`

- [ ] **Step 1: Add primary-switch and secondary-isolation contracts**

Create:

```python
from pathlib import Path


LIVE = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")


def _section(source, start, end):
    assert start in source
    assert end in source
    return source.split(start, 1)[1].split(end, 1)[0]


def test_primary_handoff_resets_every_per_athlete_display_history():
    source = LIVE.read_text(encoding="utf-8")
    handoff = _section(
        source,
        "if next_primary_tid != mp_primary_tid:",
        "primary_selection = mp_assignments.get(mp_primary_tid, {})",
    )

    required = (
        "joints_filtered.fill(np.nan)",
        "joints_display.fill(np.nan)",
        'joints_filtered[:] = target_state["display"]',
        'joints_display[:] = target_state["display"]',
        "oneeuro_filters = [",
        "latency_rigid_lead = np.zeros(3, dtype=np.float64)",
        "bone_bank.reset()",
        "joint_kfs = [",
        "joint_kf_last_update_t = [None] * 17",
        "prev_speed_pos.fill(np.nan)",
    )
    for contract in required:
        assert contract in handoff


def test_secondary_tracks_cannot_share_the_primary_bone_bank():
    source = LIVE.read_text(encoding="utf-8")
    secondary_factory = _section(
        source, "def make_secondary_pose_state():", "def update_secondary_pose_state("
    )
    secondary_update = _section(
        source, "def update_secondary_pose_state(", "def triangulate_person_assignment("
    )
    primary_clamp = _section(
        source,
        "# Final render buffer: filtered joints + display-only bone-length",
        "if (",
    )

    assert '"joints"' in secondary_factory
    assert '"display"' in secondary_factory
    assert "bone_bank" not in secondary_factory
    assert "bone_bank" not in secondary_update
    assert "stabilize_display_skeleton(" in primary_clamp
    assert "joints_display, bone_bank" in primary_clamp

    learning = _section(
        source,
        "# Bone-length learning (display-only rigidity",
        "if mp_tracker is not None:",
    )
    assert "if j in lr_split_replaced:" in learning
    assert "np.linalg.norm(pt - prev)) > 50.0" in learning
    assert "bone_bank.observe(_bone_obs, conf=joints_conf_state" in learning
    assert "cams=joints_cam_state" in learning
```

- [ ] **Step 2: Run the integration contracts**

Run:

```bash
venv/bin/python -m pytest -o addopts='' tests/test_skeleton_stabilize_integration.py -v
```

Expected: `2 passed`.

- [ ] **Step 3: Correct only a reproduced lifecycle omission**

If a primary-handoff assertion fails, add the missing reset inside
`if next_primary_tid != mp_primary_tid:` before `mp_primary_tid` is assigned.
The required reset sequence is:

```python
oneeuro_filters = [
    OneEuroVec(args.oneeuro_mincutoff, args.oneeuro_beta)
    for _ in range(17)
]
latency_rigid_lead = np.zeros(3, dtype=np.float64)
if bone_bank is not None:
    bone_bank.reset()
joint_kf_last_update_t = [None] * 17
joint_speeds.fill(0.0)
prev_speed_pos.fill(np.nan)
prev_speed_t = None
```

Do not add the primary `bone_bank` to `secondary_states`. Secondary people are
render-only and currently use their own `joints`/`display` arrays; the
documented limitation is preferable to silently sharing body proportions.

- [ ] **Step 4: Run the display review set**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_display_state_isolation.py \
  tests/test_skeleton_stabilize.py \
  tests/test_skeleton_stabilize_integration.py \
  tests/test_display_fix_defaults.py \
  tests/test_pose_latency_comp.py \
  tests/test_pose_lr_fix.py \
  tests/test_pose_lr_split.py -v
```

Expected: `67 passed` (the current 59 tests in these files plus eight new
display/clamp/integration tests), with no failure.

- [ ] **Step 5: Inspect the scoped lifecycle diff**

Run:

```bash
git diff --check -- tests/test_skeleton_stabilize_integration.py Parallel_working/scripts/live_4cam_arena_view_parallel.py
git diff -- tests/test_skeleton_stabilize_integration.py Parallel_working/scripts/live_4cam_arena_view_parallel.py
```

Expected: no whitespace errors and no secondary-track bone bank.

### Task 4: Create a fact-check ledger and make stale-report tests fail

**Files:**
- Create:
  `docs/reports/project_cam_technical_system_report_fact_check_2026-07-29.md`
- Modify: `tests/test_project_cam_report_builder.py`
- Test: `tests/test_project_cam_report_builder.py`

- [ ] **Step 1: Add report freshness and ledger tests**

Add this constant next to the existing `ASSET_DIR`, `OUTPUT`, and `SOURCE`
imports:

```python
FACT_CHECK = (
    SOURCE.parent
    / "project_cam_technical_system_report_fact_check_2026-07-29.md"
)
```

Append:

```python
def test_report_records_the_completed_29_july_verification():
    text = SOURCE.read_text(encoding="utf-8")
    assert 'date: "Evidence snapshot: 29 July 2026"' in text
    assert "Run interrupted/inconclusive" not in text
    assert "full suite remains explicitly inconclusive" not in text
    assert "`669` tests passed across `59` files" in text
    assert "`239` tests passed across `11` files" in text


def test_fact_check_ledger_resolves_every_material_claim():
    text = FACT_CHECK.read_text(encoding="utf-8")
    required_sections = (
        "## Repository and Runtime Claims",
        "## Quantitative Evidence",
        "## Safety and Maturity Claims",
        "## External Licensing Claims",
    )
    for heading in required_sections:
        assert heading in text
    assert "| unresolved |" not in text.lower()
    assert (
        "garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/"
        in text
    )
    assert "configs/calibration/usb6_manifest.yaml" in text
```

- [ ] **Step 2: Run the two tests and verify the expected failure**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_project_cam_report_builder.py::test_report_records_the_completed_29_july_verification \
  tests/test_project_cam_report_builder.py::test_fact_check_ledger_resolves_every_material_claim -v
```

Expected: `2 failed`; the report still says 17 July/inconclusive, and the
fact-check ledger does not exist.

- [ ] **Step 3: Create the ledger with resolved dispositions**

Create
`docs/reports/project_cam_technical_system_report_fact_check_2026-07-29.md`
with these sections and rows:

```markdown
# Project_Cam Technical Report Fact Check — 2026-07-29

## Repository and Runtime Claims

| Claim | Source | Result | Disposition |
|---|---|---|---|
| Branch and committed snapshot | `git branch --show-current`; `git rev-parse --short HEAD` | `feature/multi-person-face-id-desktop-20260712`; `7f937dbc` | verified |
| Bone consistency is display-only and default-on | `live_4cam_arena_view_parallel.py`; `tests/test_display_state_isolation.py`; `tests/test_display_fix_defaults.py` | render buffer only; default `True` | verified |
| Left/right repair uses conclusive per-pair verdicts with chain fallback only for ambiguous pairs | `fix_lr_swaps_for_cam`; `tests/test_pose_lr_fix.py` | current code and regression tests agree | verified |
| Secondary tracks do not share the primary bone bank | primary-handoff and secondary-state blocks; `tests/test_skeleton_stabilize_integration.py` | secondaries have independent render state and no bank | verified limitation |

## Quantitative Evidence

| Claim | Source | Result | Disposition |
|---|---|---|---|
| Four-camera ball ground truth | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_ball/summary_metrics.json` | 36/36; mean 156.90 mm; P95 288.34 mm; repeatability 3.09 mm | verified and scope retained |
| Four-camera joint ground truth | `garage_lab_combined/gt_eval/reeval_arena_fixed_20260406/reports_joint/summary_metrics.json` | 62/81; mean 178.98 mm; P95 243.77 mm; repeatability 4.39 mm | verified with missing-trial caveat |
| Six-camera calibration/capture status | `configs/calibration/usb6_manifest.yaml` | calibration-fit values recorded; one-controller and missing-static-GT limitations retained | verified and qualified |
| Full Python suite | `venv/bin/python -m pytest -o addopts=''` | 669 passed across 59 test files; two pre-existing warnings | replaces stale inconclusive row |
| Critical targeted set | exact 11-file command in the report | 239 passed | replaces the older 234 count |

## Safety and Maturity Claims

| Claim | Source | Result | Disposition |
|---|---|---|---|
| UDP and firing-line snapshot use measured state, not display state | live UDP block; `tests/test_display_state_isolation.py` | both consume `joints_state` | verified software contract |
| Fire control is fail-closed in software | `src/project_cam/safety`; launcher runtime; fire-control tests | malformed, stale, or inconsistent state blocks | verified in software only |
| Launcher is commissioned for athlete use | repository evidence | no hardware commissioning artifact exists | claim remains explicitly rejected |
| RPM-to-m/s relationship is calibrated | runtime and calibration helper | speed remains assumed/unverified | retained as P0 blocker |

## External Licensing Claims

| Claim | Source | Result | Disposition |
|---|---|---|---|
| Ultralytics commercial redistribution is resolved | current official Ultralytics licensing page and repository license, checked 2026-07-29 | repository does not contain evidence of a commercial license decision | retain as open P0; do not state legal entitlement |
| OpenCV YuNet/SFace model redistribution is resolved | current official OpenCV Zoo repository/model documentation, checked 2026-07-29 | implementation source is identifiable; product redistribution review remains required | qualify; do not claim full product clearance |
```

- [ ] **Step 4: Verify external rows against authoritative current sources**

Browse only official Ultralytics and OpenCV sources. Record the exact page
links under the licensing table as Markdown bullets, with access date
2026-07-29. Do not turn the engineering report into legal advice; if an
official page is ambiguous, keep the disposition as an open review item.

- [ ] **Step 5: Run the ledger test alone**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_project_cam_report_builder.py::test_fact_check_ledger_resolves_every_material_claim -v
```

Expected: `1 passed`.

### Task 5: Correct the technical report and generator metadata

**Files:**
- Modify: `docs/reports/project_cam_technical_system_report_en.md`
- Modify: `scripts/build_project_cam_technical_system_report.py`
- Modify: `tests/test_project_cam_report_builder.py`
- Test: `tests/test_project_cam_report_builder.py`

- [ ] **Step 1: Update the evidence date**

In the report YAML and snapshot table, make the exact replacements:

```markdown
date: "Evidence snapshot: 29 July 2026"
```

and:

```markdown
| Evidence date | 29 July 2026 |
```

In `style_document`, change:

```python
doc.core_properties.subject = (
    "Technical system report, evidence snapshot 29 July 2026"
)
run = footer_paragraph.add_run("Evidence snapshot 29 July 2026   ·   ")
```

- [ ] **Step 2: Replace the three stale test-evidence rows**

Use:

```markdown
| Current test discovery | 29 July working tree | `669` tests collected across `59` files | Fresh inventory after the display-fix review; no hardware implication |
| Critical targeted software check | 29 July working tree | `239` tests passed across `11` files | Fresh bounded software verification; no hardware implication |
| Full local suite | 29 July working tree | `669` tests passed; two pre-existing warnings | Fresh full software verification; no camera or launcher commissioning implication |
```

Replace the paragraph beginning “The two test counts in the matrix” and the
sentence saying the full suite remains inconclusive with:

```markdown
The test counts are local observations from the 29 July dirty working tree,
not durable CI artifacts. Discovery and the full run were executed with
`venv/bin/python -m pytest`; the focused 11-file command below passed 239
tests. The full suite passed 669 tests with two pre-existing warnings: one
Starlette/httpx deprecation warning and one CUDA-forward-compatibility warning
inside a CPU-valid SMPL test. These results verify software behavior under the
test inputs; they do not establish camera, biometric, trajectory, or launcher
commissioning evidence.
```

- [ ] **Step 3: Add the 29 July adversarial-review outcome**

After the skeleton-stabilizer discussion, add:

```markdown
The 29 July adversarial pass completed the previously interrupted review. It
confirmed that coach/drill frames, UDP serialization, the BLM aim overlay, and
the firing-line snapshot consume `joints_state`, while latency compensation
and bone clamping remain confined to copied render buffers. Mathematical
tests also confirmed geometric soft-clamp convergence, root-outward shared
joint handling, degenerate-bone safety, and rigid-world-transform invariance.
Primary-athlete handoff resets the learned bone bank, filter state, Kalman
state, and rigid lead; secondary tracks do not share that bank and therefore
remain unstabilized render-only tracks. These are software contracts, not live
commissioning evidence.
```

- [ ] **Step 4: Update tests to inspect generated document metadata**

Append to `test_cover_date_ends_with_a_page_break_before_the_toc`:

```python
    assert "29 July 2026" in document.core_properties.subject
```

- [ ] **Step 5: Run report source/metadata tests**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_project_cam_report_builder.py::test_report_records_the_completed_29_july_verification \
  tests/test_project_cam_report_builder.py::test_fact_check_ledger_resolves_every_material_claim -v
```

Expected: `2 passed`.

- [ ] **Step 6: Inspect the report diff for unsupported scope changes**

Run:

```bash
git diff --check -- \
  docs/reports/project_cam_technical_system_report_en.md \
  docs/reports/project_cam_technical_system_report_fact_check_2026-07-29.md \
  scripts/build_project_cam_technical_system_report.py \
  tests/test_project_cam_report_builder.py
git diff --word-diff=plain -- docs/reports/project_cam_technical_system_report_en.md
```

Expected: changes are limited to evidence date, verified review outcome,
current test evidence, and any claim explicitly corrected by the ledger.

### Task 6: Regenerate and inspect the DOCX

**Files:**
- Regenerate: `docs/Project_Cam_Technical_System_Report_EN.docx`
- Regenerate as needed: `docs/assets/project_cam_report/*.png`
- Test: `tests/test_project_cam_report_builder.py`

- [ ] **Step 1: Prove the generated DOCX is stale before regeneration**

Run:

```bash
venv/bin/python -m pytest -o addopts='' tests/test_project_cam_report_builder.py -v
```

Expected: `10 passed, 1 failed`. The single failure is
`test_cover_date_ends_with_a_page_break_before_the_toc` because the existing
DOCX still carries the 17 July core-property subject. Any other failure must
be fixed before generation.

- [ ] **Step 2: Build the report**

Run:

```bash
venv/bin/python scripts/build_project_cam_technical_system_report.py
```

Expected output begins with:

```text
Built docs/Project_Cam_Technical_System_Report_EN.docx
```

and every Markdown-referenced figure is reported as `Generated`, never
missing.

- [ ] **Step 3: Re-run the builder tests against the generated DOCX**

Run:

```bash
venv/bin/python -m pytest -o addopts='' tests/test_project_cam_report_builder.py -v
```

Expected: `11 passed`, including the 29 July core-property assertion and
figure resolution.

- [ ] **Step 4: Render a PDF preview and inspect representative pages**

Run:

```bash
report_preview_dir=$(mktemp -d)
libreoffice --headless --convert-to pdf \
  --outdir "$report_preview_dir" \
  docs/Project_Cam_Technical_System_Report_EN.docx
pdfinfo "$report_preview_dir/Project_Cam_Technical_System_Report_EN.pdf" | sed -n '1,20p'
pdftoppm -f 1 -singlefile -png \
  "$report_preview_dir/Project_Cam_Technical_System_Report_EN.pdf" \
  "$report_preview_dir/cover"
pdftoppm -f 25 -singlefile -png \
  "$report_preview_dir/Project_Cam_Technical_System_Report_EN.pdf" \
  "$report_preview_dir/evidence"
```

Inspect `cover.png` and `evidence.png` with the local image viewer. Expected:
no clipped headings/tables, correct 29 July evidence date, and readable
evidence matrix. If the report has fewer than 25 pages, use the final page
number reported by `pdfinfo`.

- [ ] **Step 5: Inspect generated-file scope**

Run:

```bash
git status --short -- docs/Project_Cam_Technical_System_Report_EN.docx docs/assets/project_cam_report
```

Expected: only the technical report DOCX and intentionally regenerated report
assets are listed; the separate pose-estimation guide is untouched.

### Task 7: Record the completed review and run final verification

**Files:**
- Modify: `CLAUDE.md`
- Verify: all files in this plan

- [ ] **Step 1: Append the 29 July completion record**

Add a session-log subsection after the existing 29 July adversarial-review
entry:

```markdown
### 2026-07-29 — Display-fix adversarial review completed
- Finished the four interrupted lenses: display/state isolation, clamp math,
  integration lifecycle, and technical-report fact-check.
- Display isolation verified: coach/drill metrics, UDP, BLM aim, and the
  firing-line snapshot consume `joints_state`; lead/clamp work on copied render
  buffers. No display-to-safety leak reproduced.
- Clamp math verified: soft convergence, degenerate-bone handling,
  root-outward shared-joint order, and rigid-transform invariance. No
  order-instability defect reproduced.
- Lifecycle verified: primary handoff clears the bone bank, filter/KF state,
  and rigid lead. Secondary tracks have independent render arrays and no
  shared bank; their lack of bone clamping remains an explicit prototype
  limitation.
- Technical report fact-checked against the ground-truth summaries, USB6
  manifest, runtime source, tests, and current official licensing sources.
  Snapshot/test evidence updated to 29 July and the DOCX regenerated.
- Verification: 669 passed across 59 test files; focused 11-file safety/runtime
  set 239 passed; report-builder 11 passed. Two pre-existing warnings remain.
  No camera or launcher hardware validation was performed. Not committed
  (user owns commits).
```

If a runtime defect was actually reproduced and fixed in Tasks 1–3, replace
the corresponding “No ... defect reproduced” sentence with the exact failing
scenario and correction before saving.

- [ ] **Step 2: Run the focused safety/runtime set**

Run:

```bash
venv/bin/python -m pytest -o addopts='' \
  tests/test_triangulation.py \
  tests/test_live_parallel_usb6.py \
  tests/test_multi_person_tracking.py \
  tests/test_face_id.py \
  tests/test_firing_line.py \
  tests/test_fire_control.py \
  tests/test_launcher_runtime_fire_control.py \
  tests/test_pose_lr_fix.py \
  tests/test_pose_lr_split.py \
  tests/test_training_drills.py \
  tests/test_desktop_training_contracts.py
```

Expected: `239 passed`.

- [ ] **Step 3: Run the complete suite**

Run:

```bash
venv/bin/python -m pytest -o addopts=''
```

Expected: `669 passed`, with only the two pre-existing warnings documented in
the design.

- [ ] **Step 4: Verify collection count and test-file count**

Run:

```bash
venv/bin/python -m pytest -o addopts='' --collect-only
rg --files tests -g 'test_*.py' | wc -l
```

Expected: `669 tests collected` and `59`.

- [ ] **Step 5: Run repository hygiene checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Status must retain all pre-existing unrelated
user changes and show the new spec, plan, tests, fact-check ledger, corrected
report sources, and regenerated technical-report DOCX. Do not commit.

- [ ] **Step 6: Prepare the evidence handoff**

Report:

- which findings reproduced and which were rejected;
- exact focused, builder, and full-suite results;
- whether any runtime source changed;
- which report claims changed and their evidence sources;
- that live balance-drill validation and RPM-to-m/s calibration remain open;
- that no commit was created.
