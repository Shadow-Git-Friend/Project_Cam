# Runtime Safety Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` or `superpowers:executing-plans`.
> Every behavior change follows RED → GREEN → REFACTOR. Do not run hardware.

**Goal:** Make desktop shutdown robust, make corrupt Face ID assets non-fatal,
and fail closed at every pose-driven serial fire site unless a fresh all-person
snapshot proves the actual ballistic corridor is clear.

**Architecture:** Preserve the existing primary joint UDP schema and append an
all-person safety snapshot. Evaluate that snapshot with a shared pure geometry
module at the launcher boundary immediately before `shoot`. Keep aim-only as the
default and treat missing or ambiguous data as unsafe.

**Tech stack:** Python 3.10+, NumPy, OpenCV, tkinter, UDP JSON, pytest.

---

### Task 1: Harden desktop decoding, input, and shutdown lifecycle

**Files:**
- Modify: `tests/test_desktop_control_center.py`
- Modify: `desktop/arena_control_center.py`

- [ ] Add failing tests for people-count parsing (`disabled`, empty, non-numeric,
  out of 2..6), explicit UTF-8 replacement decoding, generation-safe exit events,
  staged INT→TERM→KILL shutdown, repeated STOP escalation, and delayed close.
- [ ] Run the focused tests and record the expected failures.
- [ ] Add `parse_multi_people`, change the Tk variable to `StringVar`, and log
  validation errors without launching.
- [ ] Configure `Popen(..., encoding="utf-8", errors="replace")`.
- [ ] Implement process generation and a timer-driven shutdown state machine;
  keep output pumping while closing and destroy only after child exit.
- [ ] Re-run desktop tests and compile the application.

### Task 2: Contain corrupt Face ID gallery/model failures

**Files:**
- Modify: `tests/test_face_id.py`
- Modify: `tests/test_face_cli.py`
- Modify: `src/project_cam/tracking/face_id.py`
- Modify: `Parallel_working/scripts/face_enroll.py`

- [ ] Add failing tests for zero-byte and truncated NPZ galleries, YuNet and SFace
  constructor errors, and CLI list/remove against a corrupt gallery.
- [ ] Run focused tests and record the expected failures.
- [ ] Translate only known gallery/archive failures to a chained `ValueError`.
- [ ] Wrap each OpenCV constructor and identify its model path in the error.
- [ ] Catch expected gallery errors at every CLI operation and return code 1.
- [ ] Re-run Face ID and CLI tests.

### Task 3: Define the pure firing-line geometry and fail-closed policy

**Files:**
- Create: `tests/test_firing_line.py`
- Create: `src/project_cam/closed_loop/firing_line.py`
- Modify: `src/project_cam/closed_loop/__init__.py`

- [ ] Write failing tests for ballistic sampling, clear/crossing bodies, isolated
  joints, unlocalized secondaries, stale/missing snapshots, wrong schema/frame,
  primary ID/epoch changes, and invalid numeric data.
- [ ] Run the test to confirm the module/API is absent.
- [ ] Implement a structured immutable decision type, snapshot validation,
  ballistic polyline sampling, robust 3D segment distance, and conservative body
  corridor evaluation.
- [ ] Export the API and re-run focused geometry/safety tests.

### Task 4: Publish an additive all-person safety snapshot

**Files:**
- Modify: `tests/test_live_multi_person_face_id.py`
- Modify: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

- [ ] Add failing helper/contract tests for packet schema, same-axis transform,
  primary epoch increments, primary plus secondary tracks, and representation of
  unlocalized active tracks.
- [ ] Run the focused viewer test and record failures.
- [ ] Add a pure snapshot builder and primary epoch state without touching
  `triangulate_multi`, `transform_world_point_y`, `ema_update`, or existing
  `joints` construction.
- [ ] Attach `safety` to the existing packet and keep all legacy fields unchanged.
- [ ] Re-run viewer-focused and protected-function regression tests.

### Task 5: Enforce clearance in interactive and follow launchers

**Files:**
- Create/modify: launcher script contract tests under `tests/`
- Modify: `garage_lab_combined/scripts/live_aim_test.py`
- Modify: `garage_lab_combined/scripts/blm_follow.py`

- [ ] Add failing tests around pure request/decision helpers proving missing,
  stale, blocked, and primary-changed snapshots never call serial `shoot`.
- [ ] Store the latest safety snapshot in each UDP listener and capture primary
  ID/epoch with every accepted aim.
- [ ] Re-evaluate immediately before fire using the actual commanded trajectory;
  on block send `stop`, invalidate aim, and log diagnostics.
- [ ] Re-run script tests and AST/help smoke checks.

### Task 6: Enforce clearance in production runtime operator and auto paths

**Files:**
- Create/modify: runtime contract tests under `tests/`
- Modify: `garage_lab_combined/scripts/launcher_runtime_from_udp.py`

- [ ] Add failing tests proving the operator path respects `--shoot-enabled`, both
  operator and auto paths require the interlock, and primary changes invalidate aim.
- [ ] Store the latest safety snapshot and aim context in runtime state.
- [ ] Route both fire sites through one request helper that logs the decision and
  transmits `shoot` only on allow; block sends `stop` and clears arming state.
- [ ] Re-run runtime tests and CLI help smoke checks.

### Task 7: Verify and review

- [ ] Run focused desktop, Face ID, firing-line, viewer, and launcher tests.
- [ ] Run the repository regression suite with documented API incompatibility
  exclusions only if still necessary; record exact counts.
- [ ] Compile every modified Python file and verify all CLI `--help` commands.
- [ ] Diff protected viewer functions against the parent commit.
- [ ] Independently review safety failure defaults and all literal serial `shoot`
  call sites.
- [ ] Update the implementation report with verified behavior and remaining lab
  gates. Do not claim hardware validation.
