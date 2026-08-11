# BLM Confirmed-Shot Host Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current `control_12` console parse its real `info` output, require a genuine sampled RPM window, and record a physical shot only after the firmware front-limit acknowledgement.

**Architecture:** `BlmController` remains the single authority for gates and evidence. Serial input is normalized into one controller path, controller state transitions are serialized with an `RLock`, and `shoot` creates a request which only the exact firmware ACK can promote into a measurable shot. The React view consumes additive bridge status; it never recreates safety predicates.

**Tech Stack:** Python 3.10, pytest, JSONL evidence, React/TypeScript, Tauri/Rust command transport, ruff, npm/Vite, Cargo.

---

## Execution boundaries

- Design authority: `docs/superpowers/specs/2026-08-11-blm-telemetry-confirmed-shot-design.md` at commit `c25273e`.
- Execute in the existing `feature/fixed-yaw-rpm-calibration` checkout. A fresh worktree would omit the uncommitted BLM base already verified on the stand.
- The worktree is dirty. Never run `git add -A`, `git add .`, reset, checkout, clean, or stash. Stage only paths named in each task and inspect `git diff --cached --name-status` before every commit.
- Do not open `/dev/ttyUSB*`, launch the desktop console, flash firmware, spin wheels, ARM, or fire while executing Tasks 1–7.
- Preserve `garage_lab_combined/cal/blm/rpm_speed_shots.jsonl` byte-for-byte. Tests use `tmp_path` only.

## File map

- `garage_lab_combined/scripts/blm_bridge.py` — serial normalization, controller state machine, RPM window, ACK timeout, JSONL evidence, published status.
- `tests/test_blm_bridge.py` — hardware-free behavior tests driven by injected clock and wire.
- `project-cam-desktop/src/blm.ts` — additive status types and operator-step projection.
- `project-cam-desktop/src/views/LauncherView.tsx` — display and disablement driven by bridge status.
- `tests/test_desktop_launcher_console.py` — Python/TypeScript status parity and source-level safety contracts.
- `docs/protocols/2026-08-03-rpm-speed-measurement.md` — operator meaning of ACK, pre-fire RPM, and temporary `control_12` polling.
- `.claude/rules/safety.md` — safety wording only; keep unstaged because the file contains pre-existing served-drill edits.

### Task 1: Replace command-sent evidence with exact ACK evidence

**Files:**
- Modify: `tests/test_blm_bridge.py:53-137,346-492,729-846,1016-1043`
- Modify: `garage_lab_combined/scripts/blm_bridge.py:79-142,280-358,359-438,531-567,814-887,948-1003`

- [ ] **Step 1: Write failing ACK and provenance tests**

Add this constant and helper near the existing test helpers:

```python
SHOT_ACK = "SYS: SHOT FIRED - FRONT LIMIT HIT"


def confirm_shot(controller):
    assert controller.note_serial_line(SHOT_ACK)
```

Add tests which pin request/confirmation semantics and field names:

```python
def test_shoot_is_only_a_request_until_the_front_limit_ack(
        bridge, fitter, tmp_path):
    controller, wire, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")

    assert wire.sent[-1] == "shoot"
    assert controller.state.fire_request is not None
    assert controller.state.shots_fired == 0
    assert controller.state.pending_shot is None
    with pytest.raises(bridge.CommandError, match="confirmed shot"):
        send(bridge, controller, "measure 3.94")

    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in records] == ["shot_requested"]

    confirm_shot(controller)
    assert controller.state.fire_request is None
    assert controller.state.shots_fired == 1
    assert controller.state.pending_shot is not None
    records = [json.loads(line) for line in
               (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in records] == [
        "shot_requested", "shot_fired"]


def test_confirmed_evidence_names_the_last_pre_fire_sample_and_its_age(
        bridge, fitter, tmp_path):
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    clock.advance(0.4)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    confirm_shot(controller)

    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    for row in rows:
        assert row["schema"] == "project_cam.blm_shot_evidence.v2"
        assert row["rpm_left_pre_fire"] == 500.0
        assert row["rpm_right_pre_fire"] == 500.0
        assert row["rpm_pre_fire_sample_age_s"] == pytest.approx(0.4)
        assert "rpm_left_measured" not in row
        assert "rpm_right_measured" not in row
    assert rows[0]["request_seq"] == rows[1]["request_seq"] == 1


def test_duplicate_front_limit_ack_is_idempotent(bridge, fitter, tmp_path):
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    confirm_shot(controller)
    controller.note_serial_line(SHOT_ACK)
    assert controller.state.shots_fired == 1
    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows].count("shot_fired") == 1


def test_outstanding_request_refuses_every_competing_command(bridge):
    controller, wire, _, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    for command in (
        "aim 0 0 500", "wheels 0", "reload", "center", "set_zero",
        "info", "measure 3.0", "undo", "arm", "fire",
    ):
        with pytest.raises(bridge.CommandError, match="awaiting firmware"):
            send(bridge, controller, command)
    assert wire.sent[-1] == "shoot"
```

- [ ] **Step 2: Run the new tests and verify the old behavior fails**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_blm_bridge.py::test_shoot_is_only_a_request_until_the_front_limit_ack \
  tests/test_blm_bridge.py::test_confirmed_evidence_names_the_last_pre_fire_sample_and_its_age \
  tests/test_blm_bridge.py::test_duplicate_front_limit_ack_is_idempotent \
  tests/test_blm_bridge.py::test_outstanding_request_refuses_every_competing_command \
  -q -p no:cacheprovider -o addopts=
```

Expected: FAIL because `_do_fire` immediately increments `shots_fired`, creates `pending_shot`, and writes v1 `shot_fired`.

- [ ] **Step 3: Introduce separate status/evidence schemas and request types**

In `blm_bridge.py`, keep the status schema and add exact evidence constants:

```python
STATUS_SCHEMA = "project_cam.blm_console.v1"
SHOT_EVIDENCE_SCHEMA = "project_cam.blm_shot_evidence.v2"
SHOT_FIRED_ACK = "SYS: SHOT FIRED - FRONT LIMIT HIT"
```

Replace the shot dataclasses with provenance-explicit fields:

```python
@dataclass
class FireRequest:
    request_seq: int
    rpm: float
    requested_at: str
    requested_monotonic: float
    rpm_left_pre_fire: float
    rpm_right_pre_fire: float
    rpm_pre_fire_sample_age_s: float
    pitch_deg: float
    yaw_deg: float
    timed_out: bool = False


@dataclass
class PendingShot:
    rpm: float
    seq: int
    request_seq: int
    confirmed_at: str
    rpm_left_pre_fire: float
    rpm_right_pre_fire: float
    rpm_pre_fire_sample_age_s: float


@dataclass
class Measurement:
    rpm: float
    distance_m: float
    at: str
    shot_seq: int
    request_seq: int
    rpm_left_pre_fire: float
    rpm_right_pre_fire: float
    rpm_pre_fire_sample_age_s: float
```

Add these `ConsoleState` fields:

```python
fire_requests_sent: int = 0
fire_request: Optional[FireRequest] = None
last_confirmed_request_seq: int = 0
```

- [ ] **Step 4: Serialize controller transitions**

Create `self._state_lock = threading.RLock()` in `BlmController.__init__`. Wrap the bodies of `handle`, `note_telemetry`, `note_serial_line`, and `status` in `with self._state_lock:`. Keep internal calls on the same controller; `RLock` is required because `handle()` calls helpers which also read controller state.

This lock must remain held across `_send("shoot")`. The serial reader then cannot process a fast ACK until the request has been installed and the successful write has been recorded.

At the start of locked `handle()`, preserve STOP/disarm and route CLEAR to its
own refusal, while blocking every competing operation:

```python
if (self.state.fire_request is not None
        and intent.kind not in ("stop", "disarm", "clear")):
    self._refuse(
        "no confirmed shot — shoot request is awaiting firmware confirmation"
    )
```

- [ ] **Step 5: Implement request creation and exact ACK promotion**

Replace the evidence part of `_do_fire` with this transition:

```python
if self.state.fire_request is not None:
    self._refuse("a shoot request is still awaiting firmware confirmation")
if self.state.pending_shot is not None:
    self._refuse("record the confirmed shot distance before firing again")

self.state.armed = False
self.state.arm_expires_at = 0.0
sample_age = self.telemetry_age_s()
left, right = self.state.rpm_left, self.state.rpm_right
if sample_age is None or left is None or right is None:
    self._refuse("the pre-fire RPM sample disappeared before shoot")
request = FireRequest(
    request_seq=self.state.fire_requests_sent + 1,
    rpm=self.state.wheel_rpm,
    requested_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    requested_monotonic=self._now(),
    rpm_left_pre_fire=left,
    rpm_right_pre_fire=right,
    rpm_pre_fire_sample_age_s=sample_age,
    pitch_deg=self.state.pitch_deg or 0.0,
    yaw_deg=self.state.yaw_deg or 0.0,
)
self.state.fire_request = request
try:
    self._send("shoot")
except Exception:
    self.state.fire_request = None
    raise
self.state.fire_requests_sent = request.request_seq
self.state.loaded = False
self._append_fire_event("shot_requested", request)
self._log(
    f"shoot request {request.request_seq} sent — awaiting firmware front-limit ACK"
)
```

Handle the exact ACK before ordinary serial deduplication:

```python
def _confirm_fire_request(self) -> bool:
    request = self.state.fire_request
    if request is None:
        if self.state.last_confirmed_request_seq:
            return False
        self._handle_orphan_shot_ack()
        return True
    self.state.shots_fired += 1
    confirmed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    shot = PendingShot(
        rpm=request.rpm,
        seq=self.state.shots_fired,
        request_seq=request.request_seq,
        confirmed_at=confirmed_at,
        rpm_left_pre_fire=request.rpm_left_pre_fire,
        rpm_right_pre_fire=request.rpm_right_pre_fire,
        rpm_pre_fire_sample_age_s=request.rpm_pre_fire_sample_age_s,
    )
    self.state.pending_shot = shot
    self.state.fire_request = None
    self.state.last_confirmed_request_seq = request.request_seq
    self._append_shot_fired(shot)
    self._log(
        f"shot {shot.seq} confirmed by firmware front limit — awaiting distance"
    )
    return True
```

At the start of the locked `note_serial_line` body:

```python
if raw == SHOT_FIRED_ACK:
    return self._confirm_fire_request()
```

Write `shot_requested` and `shot_fired` with `SHOT_EVIDENCE_SCHEMA`, `request_seq`, `rpm`, `rpm_left_pre_fire`, `rpm_right_pre_fire`, and `rpm_pre_fire_sample_age_s`. `shot_fired` additionally carries `shot_seq` and `confirmed_at`.

Use one complete request-event writer so timeout records carry the same
provenance:

```python
def _append_fire_event(self, event: str, request: FireRequest) -> None:
    self._write_shot_record({
        "schema": SHOT_EVIDENCE_SCHEMA,
        "event": event,
        "method": "A_landing_distance",
        "request_seq": request.request_seq,
        "rpm": request.rpm,
        "rpm_left_pre_fire": request.rpm_left_pre_fire,
        "rpm_right_pre_fire": request.rpm_right_pre_fire,
        "rpm_pre_fire_sample_age_s": request.rpm_pre_fire_sample_age_s,
        "requested_at": request.requested_at,
        "session_id": self._session_id,
    })
```

- [ ] **Step 6: Update measurement helpers and existing shot tests**

Change the shared `fire_at` helper to confirm the physical event:

```python
def fire_at(bridge, controller, clock, rpm=500):
    ready_to_arm(bridge, controller, clock, rpm=rpm)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    confirm_shot(controller)
```

Update `Measurement` construction, retraction, status, and JSONL writes to copy the new pre-fire fields and `request_seq`. Rewrite assertions which expected `rpm_left_measured`/`rpm_right_measured` to expect the explicit pre-fire names.

- [ ] **Step 7: Run the bridge suite**

Run:

```bash
venv/bin/python -m pytest tests/test_blm_bridge.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: PASS; no test may create a measurable shot without `confirm_shot()`.

- [ ] **Step 8: Commit only the bridge and bridge tests**

```bash
git add garage_lab_combined/scripts/blm_bridge.py tests/test_blm_bridge.py
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(blm): bind shot evidence to firmware ack"
```

Expected staged paths: exactly the two listed files.

### Task 2: Fail closed on ACK timeout and orphan ACK

**Files:**
- Modify: `tests/test_blm_bridge.py`
- Modify: `garage_lab_combined/scripts/blm_bridge.py:359-438,531-567,751-781,1005-1085,1270-1278`

- [ ] **Step 1: Write failing timeout, silent-refusal, and orphan tests**

```python
def test_missing_ack_times_out_to_latched_stop_without_a_shot(
        bridge, fitter, tmp_path):
    controller, wire, logs, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, shot_ack_timeout_s=5.0)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    clock.advance(5.0)
    controller.refresh_safety()

    assert controller.state.estop_latched
    assert controller.state.fire_request is not None
    assert controller.state.fire_request.timed_out
    assert controller.state.shots_fired == 0
    assert controller.state.pending_shot is None
    assert wire.sent[-1] == "stop"
    assert any("below 400 RPM" in line and "outcome unknown" in line
               for line in logs)
    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == [
        "shot_requested", "shot_confirmation_timeout"]


def test_timeout_latches_before_a_failed_stop_write(bridge, fitter, tmp_path):
    wire = Wire(fail_on="stop")
    controller, _, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, wire=wire,
        shot_ack_timeout_s=5.0)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    clock.advance(5.0)
    controller.refresh_safety()
    assert controller.state.estop_latched
    assert controller.state.fire_request.timed_out
    assert controller.state.shots_fired == 0


def test_orphan_front_limit_ack_latches_and_stops(bridge, fitter, tmp_path):
    controller, wire, _, _ = make(bridge, fitter=fitter, tmp_path=tmp_path)
    controller.note_serial_line(SHOT_ACK)
    assert controller.state.estop_latched
    assert wire.sent == ["stop"]
    rows = [json.loads(line) for line in
            (tmp_path / "shots.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == ["orphan_shot_ack"]


def test_clear_cannot_recover_an_unknown_shot_outcome(bridge, fitter, tmp_path):
    controller, _, _, clock = make(
        bridge, fitter=fitter, tmp_path=tmp_path, shot_ack_timeout_s=5.0)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    send(bridge, controller, "fire")
    clock.advance(5.0)
    controller.refresh_safety()
    with pytest.raises(bridge.CommandError, match="outcome is unresolved"):
        send(bridge, controller, "clear")
```

- [ ] **Step 2: Run tests and verify missing APIs fail**

Run:

```bash
venv/bin/python -m pytest \
  tests/test_blm_bridge.py::test_missing_ack_times_out_to_latched_stop_without_a_shot \
  tests/test_blm_bridge.py::test_timeout_latches_before_a_failed_stop_write \
  tests/test_blm_bridge.py::test_orphan_front_limit_ack_latches_and_stops \
  tests/test_blm_bridge.py::test_clear_cannot_recover_an_unknown_shot_outcome \
  -q -p no:cacheprovider -o addopts=
```

Expected: FAIL because `shot_ack_timeout_s`, `refresh_safety`, timeout evidence, and orphan handling do not exist.

- [ ] **Step 3: Add the bounded timeout and idempotent fail-closed transition**

Add `SHOT_ACK_TIMEOUT_S = 5.0`, accept `shot_ack_timeout_s` in `BlmController.__init__`, and store it as `_shot_ack_timeout_s` after checking it is finite and positive.

Extend the test `make()` helper explicitly:

```python
def make(bridge, *, allow_fire=True, clock=None, wire=None, fitter=None,
         tmp_path=None, arm_timeout_s=30.0, shot_ack_timeout_s=5.0,
         pitch_min_deg=None, pitch_max_deg=None):
    clock = clock or Clock()
    wire = wire or Wire()
    logs: list[str] = []
    controller = bridge.BlmController(
        wire,
        logs.append,
        allow_fire=allow_fire,
        now=clock,
        arm_timeout_s=arm_timeout_s,
        shot_ack_timeout_s=shot_ack_timeout_s,
        shot_log=(tmp_path / "shots.jsonl") if tmp_path else None,
        model_out=(tmp_path / "model.json") if tmp_path else None,
        fitter=fitter,
        **({} if pitch_min_deg is None else {"pitch_min_deg": pitch_min_deg}),
        **({} if pitch_max_deg is None else {"pitch_max_deg": pitch_max_deg}),
    )
    return controller, wire, logs, clock
```

Implement:

```python
def refresh_safety(self) -> None:
    with self._state_lock:
        self.refresh_arm()
        request = self.state.fire_request
        if request is None or request.timed_out:
            return
        if self._now() - request.requested_monotonic < self._shot_ack_timeout_s:
            return
        self.state.estop_latched = True
        self.state.armed = False
        self.state.arm_expires_at = 0.0
        self.state.wheel_rpm = 0.0
        self._reset_wheel_band()
        request.timed_out = True
        self._append_fire_event("shot_confirmation_timeout", request)
        self._log(
            "shot outcome unknown — no front-limit ACK; this includes the "
            "firmware's silent below 400 RPM refusal. STOP latched by design."
        )
        try:
            self._send("stop")
        except Exception as error:
            self._log(f"STOP write failed after ACK timeout: {error}")
```

Call `controller.refresh_safety()` instead of `refresh_arm()` in the bridge heartbeat.

- [ ] **Step 4: Implement orphan handling and block CLEAR**

```python
def _handle_orphan_shot_ack(self) -> None:
    self.state.estop_latched = True
    self.state.armed = False
    self.state.arm_expires_at = 0.0
    self.state.wheel_rpm = 0.0
    self._reset_wheel_band()
    self._write_shot_record({
        "schema": SHOT_EVIDENCE_SCHEMA,
        "event": "orphan_shot_ack",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": self._session_id,
    })
    self._log("orphan firmware shot ACK — STOP latched; session invalid")
    try:
        self._send("stop")
    except Exception as error:
        self._log(f"STOP write failed after orphan ACK: {error}")
```

At the start of `_do_clear`, refuse when `fire_request` exists and is timed out. Do not clear or delete its context. A late exact ACK may still promote it to a confirmed shot, but ESTOP remains latched.

- [ ] **Step 5: Publish request/timeout state**

Add to `status()`:

```python
"shot_ack_timeout_s": self._shot_ack_timeout_s,
"fire_request": (
    None if state.fire_request is None else {
        "request_seq": state.fire_request.request_seq,
        "rpm": state.fire_request.rpm,
        "rpm_left_pre_fire": state.fire_request.rpm_left_pre_fire,
        "rpm_right_pre_fire": state.fire_request.rpm_right_pre_fire,
        "rpm_pre_fire_sample_age_s": state.fire_request.rpm_pre_fire_sample_age_s,
        "confirmation_age_s": round(
            self._now() - state.fire_request.requested_monotonic, 1),
        "timed_out": state.fire_request.timed_out,
    }
),
```

- [ ] **Step 6: Run focused and full bridge tests**

```bash
venv/bin/python -m pytest tests/test_blm_bridge.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: PASS, including stop-write failure without an exception escaping the heartbeat path.

- [ ] **Step 7: Commit**

```bash
git add garage_lab_combined/scripts/blm_bridge.py tests/test_blm_bridge.py
git diff --cached --check
git commit -m "fix(blm): latch on unconfirmed shot outcomes"
```

### Task 3: Parse the recorded `control_12` INFO formats

**Files:**
- Modify: `tests/test_blm_bridge.py:930-1015`
- Modify: `garage_lab_combined/scripts/blm_bridge.py:1108-1143,1248-1268`

- [ ] **Step 1: Add exact stand-line parser tests**

```python
def test_the_recorded_control_12_info_rpm_line_is_telemetry(bridge):
    assert bridge.parse_telemetry(
        "INFO | RPM: L=22/0, R=8/0") == (22.0, 8.0)
    assert bridge.parse_telemetry(
        "INFO | RPM: L=500/500, R=493/500") == (500.0, 493.0)


@pytest.mark.parametrize(("line", "present"), [
    ("INFO | LMT: Front=HIGH, Back=LOW, Ball=HIGH", False),
    ("INFO | LMT: Front=HIGH, Back=LOW, Ball=LOW", True),
    ("Front:1 Back:0 Ball:1", False),
    ("Front:1 Back:0 Ball:0", True),
])
def test_ball_parser_accepts_control_12_levels_and_legacy_digits(
        bridge, line, present):
    assert bridge.parse_ball_state(line) is present


def test_info_rpm_updates_telemetry_and_stays_in_the_poll_block(bridge):
    controller, _, _, _ = make(bridge, allow_fire=False)
    echoed = bridge.consume_serial_line(
        controller, "INFO | RPM: L=22/0, R=8/0")
    assert echoed
    assert (controller.state.rpm_left, controller.state.rpm_right) == (22.0, 8.0)
    assert controller.state.info_lines[-1] == "INFO | RPM: L=22/0, R=8/0"


def test_compact_telemetry_updates_state_without_flooding_the_log(bridge):
    controller, _, _, _ = make(bridge, allow_fire=False)
    echoed = bridge.consume_serial_line(controller, "L:22 R:8")
    assert not echoed
    assert (controller.state.rpm_left, controller.state.rpm_right) == (22.0, 8.0)
    assert controller.state.info_lines == []
```

- [ ] **Step 2: Run the four tests and verify failure**

Expected: INFO RPM returns `None`, HIGH/LOW returns `None`, and `consume_serial_line` is undefined.

- [ ] **Step 3: Implement strict dual-format parsing**

```python
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
COMPACT_RPM = re.compile(
    rf"^L:\s*(?P<left>{NUMBER})\s+R:\s*(?P<right>{NUMBER})(?:\s|$)")
INFO_RPM = re.compile(
    rf"^INFO \| RPM:\s*L=(?P<left>{NUMBER})/{NUMBER},\s*"
    rf"R=(?P<right>{NUMBER})/{NUMBER}\s*$")


def parse_telemetry(line: str) -> Optional[Tuple[float, float]]:
    match = COMPACT_RPM.match(line) or INFO_RPM.match(line)
    if match is None:
        return None
    try:
        return float(match.group("left")), float(match.group("right"))
    except ValueError:
        return None


BALL_FIELD = re.compile(
    r"\bBall\s*[:=]\s*(?P<value>\d+|HIGH|LOW)\b", re.IGNORECASE)


def parse_ball_state(line: str) -> Optional[bool]:
    match = BALL_FIELD.search(line)
    if match is None:
        return None
    raw = match.group("value").upper()
    level = 0 if raw == "LOW" else 1 if raw == "HIGH" else int(raw)
    return level == BALL_PRESENT_LEVEL
```

Add the shared reader router:

```python
def consume_serial_line(controller: BlmController, raw: str) -> bool:
    telemetry = parse_telemetry(raw)
    if telemetry is not None:
        controller.note_telemetry(*telemetry)
        if raw.startswith("L:"):
            return False
    return controller.note_serial_line(raw)
```

Replace the reader's separate telemetry branch with `if not consume_serial_line(controller, raw): continue`.

- [ ] **Step 4: Prove Ball remains advisory**

Extend `test_the_ball_switch_is_parsed_and_warns_but_never_gates` with HIGH/LOW lines and assert `arm` behavior is unchanged for both values.

- [ ] **Step 5: Run parser and full bridge tests**

```bash
venv/bin/python -m pytest tests/test_blm_bridge.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add garage_lab_combined/scripts/blm_bridge.py tests/test_blm_bridge.py
git diff --cached --check
git commit -m "fix(blm): parse control 12 info telemetry"
```

### Task 4: Require three samples, two seconds of sample span, and no stale gap

**Files:**
- Modify: `tests/test_blm_bridge.py:113-133,411-529,1045-1090`
- Modify: `garage_lab_combined/scripts/blm_bridge.py:313-358,439-530,790-813,1005-1085`

- [ ] **Step 1: Replace the firing-test spin helper with three arrivals**

```python
def spin_up(controller, clock, rpm, *, hold_s=2.5, spread=0.0):
    controller.note_telemetry(rpm, rpm + spread)
    clock.advance(hold_s / 2.0)
    controller.note_telemetry(rpm, rpm + spread)
    clock.advance(hold_s / 2.0)
    controller.note_telemetry(rpm, rpm + spread)
```

- [ ] **Step 2: Add failing edge tests**

```python
def test_waiting_after_one_sample_never_manufactures_a_stability_window(bridge):
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    controller.note_telemetry(500, 500)
    clock.advance(2.0)
    with pytest.raises(bridge.CommandError, match="1/3 samples"):
        send(bridge, controller, "arm")


def test_three_samples_in_30ms_do_not_satisfy_two_seconds(bridge):
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    for _ in range(3):
        controller.note_telemetry(500, 500)
        clock.advance(0.01)
    with pytest.raises(bridge.CommandError, match="0.0/2.0 s"):
        send(bridge, controller, "arm")


def test_a_gap_over_the_freshness_limit_restarts_count_and_span(bridge):
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    controller.note_telemetry(500, 500)
    clock.advance(bridge.TELEMETRY_MAX_AGE_S + 0.1)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 1
    assert controller.wheels_in_band_s() == 0.0


def test_three_samples_spanning_two_seconds_pass(bridge):
    controller, _, _, clock = make(bridge)
    ready_to_arm(bridge, controller, clock, rpm=500)
    send(bridge, controller, "arm")
    assert controller.state.armed
    assert controller.state.rpm_band_sample_count == 3
    assert controller.wheels_in_band_s() >= 2.0


def test_identical_values_count_when_they_are_separate_arrivals(bridge):
    controller, _, _, clock = make(bridge)
    send(bridge, controller, "aim 0 0 500")
    controller.note_telemetry(500, 500)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 1
    clock.advance(0.1)
    controller.note_telemetry(500, 500)
    assert controller.state.rpm_band_sample_count == 2
```

- [ ] **Step 3: Run edge tests and verify old timer fails them**

Expected: old code either arms from elapsed wall time or lacks sample-count fields/messages.

- [ ] **Step 4: Implement the sample window**

Add state fields:

```python
rpm_band_last_sample_at: Optional[float] = None
rpm_band_sample_count: int = 0
```

Make `_reset_wheel_band()` clear all three window fields. In `note_telemetry`, calculate the gap before updating `telemetry_at`:

```python
now = self._now()
last = self.state.rpm_band_last_sample_at
if self._rpm_in_band(left, right):
    if (self.state.rpm_band_since is None or last is None
            or now - last > TELEMETRY_MAX_AGE_S):
        self.state.rpm_band_since = now
        self.state.rpm_band_last_sample_at = now
        self.state.rpm_band_sample_count = 1
    elif now > last:
        self.state.rpm_band_last_sample_at = now
        self.state.rpm_band_sample_count += 1
else:
    self._reset_wheel_band()
self.state.rpm_left = left
self.state.rpm_right = right
self.state.telemetry_at = now
```

Compute sample span, not time since first observation:

```python
def wheels_in_band_s(self) -> float:
    first = self.state.rpm_band_since
    last = self.state.rpm_band_last_sample_at
    if first is None or last is None:
        return 0.0
    return max(0.0, last - first)
```

Add `wheels_stable_reason()` which first calls `wheels_unconfirmed_reason()`, then requires `rpm_band_sample_count >= 3`, then `wheels_in_band_s() >= WHEELS_STABLE_S`:

```python
def wheels_stable_reason(self) -> Optional[str]:
    reason = self.wheels_unconfirmed_reason()
    if reason is not None:
        return reason
    count = self.state.rpm_band_sample_count
    if count < 3:
        return f"only {count}/3 separate in-band samples have arrived"
    span = self.wheels_in_band_s()
    if span < WHEELS_STABLE_S:
        return (
            f"the in-band samples span {span:.1f}/{WHEELS_STABLE_S:.1f} s"
        )
    return None
```

Use this full predicate in `_do_arm`, the redundant pre-send check in `_do_fire`,
and `refresh_arm`. Therefore a new sample after a stale gap clears an existing
ARM instead of preserving it on one fresh-but-unproven value. Publish
`wheels_stable`, `rpm_band_sample_count`, and the sample span.

- [ ] **Step 5: Run bridge tests**

```bash
venv/bin/python -m pytest tests/test_blm_bridge.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: PASS. In particular, advancing the fake clock without a new sample never increases `wheels_in_band_s()`.

- [ ] **Step 6: Commit**

```bash
git add garage_lab_combined/scripts/blm_bridge.py tests/test_blm_bridge.py
git diff --cached --check
git commit -m "fix(blm): require a sampled RPM stability window"
```

### Task 5: Enforce one outstanding shot and protect UNDO

**Files:**
- Modify: `tests/test_blm_bridge.py:474-495,729-846,891-909`
- Modify: `garage_lab_combined/scripts/blm_bridge.py:814-927`

- [ ] **Step 1: Add failing outstanding-shot tests**

```python
def test_a_confirmed_unmeasured_shot_blocks_the_next_fire(
        bridge, fitter, tmp_path):
    controller, wire, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    send(bridge, controller, "reload")
    send(bridge, controller, "aim 0 0 500")
    spin_up(controller, clock, 500)
    send(bridge, controller, "arm")
    with pytest.raises(bridge.CommandError, match="record.*distance"):
        send(bridge, controller, "fire")
    assert wire.sent.count("shoot") == 1


def test_undo_refuses_to_overwrite_a_newer_pending_shot(
        bridge, fitter, tmp_path):
    controller, _, _, clock = make(bridge, fitter=fitter, tmp_path=tmp_path)
    fire_at(bridge, controller, clock, rpm=500)
    send(bridge, controller, "measure 3.0")
    fire_at(bridge, controller, clock, rpm=650)
    with pytest.raises(bridge.CommandError, match="newer confirmed shot"):
        send(bridge, controller, "undo")
    assert controller.state.pending_shot.rpm == 650
    assert [m.rpm for m in controller.state.measurements] == [500]
```

- [ ] **Step 2: Run and verify the overwrite behavior fails**

Expected: the old bridge either overwrites `pending_shot` or allows a second `shoot`.

- [ ] **Step 3: Add authoritative bridge refusals**

At the start of `_do_fire`, before `_send`, refuse both outstanding states. At the start of `_do_undo`, add:

```python
if self.state.pending_shot is not None:
    self._refuse(
        "a newer confirmed shot is awaiting its distance — UNDO would overwrite it"
    )
```

Keep the existing behavior when there is no pending shot: a retracted measurement returns its own shot to awaiting-distance state.

- [ ] **Step 4: Run the bridge suite and commit**

```bash
venv/bin/python -m pytest tests/test_blm_bridge.py -q \
  -p no:cacheprovider -o addopts=
git add garage_lab_combined/scripts/blm_bridge.py tests/test_blm_bridge.py
git diff --cached --check
git commit -m "fix(blm): preserve one-to-one shot measurements"
```

### Task 6: Expose the state without recreating gates in React

**Files:**
- Modify: `project-cam-desktop/src/blm.ts:87-154,175-333`
- Modify: `project-cam-desktop/src/views/LauncherView.tsx:127-176,426-540,830-980`
- Modify: `tests/test_desktop_launcher_console.py:142-239,342-365,544-556`

- [ ] **Step 1: Add failing status/UI contract tests**

Extend the status-parity test with:

```python
for field in (
    "fire_request", "shot_ack_timeout_s", "wheels_stable",
    "rpm_band_sample_count",
):
    assert f'"{field}"' in bridge_source
    assert re.search(rf"\b{field}\??\s*:", ts_source)
```

Add source contracts:

```python
def test_the_ui_names_pre_fire_rpm_and_never_claims_at_fire_measurement():
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert "pre-fire L=" in view
    assert "rpm_pre_fire_sample_age_s" in view
    assert "measured L={fmt(pendingShot.rpm_left)}" not in view


def test_pending_ack_blocks_poll_arm_fire_and_undo_overwrite():
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    blm = BLM_TS.read_text(encoding="utf-8")
    assert "status.fire_request" in blm
    assert "status?.fire_request" in view
    assert "AWAITING FIRMWARE ACK" in blm
    assert "SHOT OUTCOME UNKNOWN" in blm
    assert "status?.pending_shot !== null" in view
    assert "rpm_band_sample_count" in view
```

- [ ] **Step 2: Run the desktop contract tests and verify failure**

```bash
venv/bin/python -m pytest tests/test_desktop_launcher_console.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: FAIL on missing status members and wording.

- [ ] **Step 3: Extend `ConsoleStatus` with bridge-owned facts**

```typescript
wheels_stable: boolean;
rpm_band_sample_count: number;
shot_ack_timeout_s: number;
fire_request: {
  request_seq: number;
  rpm: number;
  rpm_left_pre_fire: number;
  rpm_right_pre_fire: number;
  rpm_pre_fire_sample_age_s: number;
  confirmation_age_s: number;
  timed_out: boolean;
} | null;
pending_shot: {
  rpm: number;
  seq: number;
  request_seq: number;
  rpm_left_pre_fire: number;
  rpm_right_pre_fire: number;
  rpm_pre_fire_sample_age_s: number;
} | null;
```

In `fireBlockers`, add a blocker for any `fire_request` and for any `pending_shot`. In `cycleStep`, place request handling before pending-shot handling:

```typescript
if (status.fire_request) {
  return status.fire_request.timed_out
    ? {
        key: "shot_unknown",
        title: "SHOT OUTCOME UNKNOWN",
        detail:
          "No front-limit ACK. This includes the firmware's silent below-400 RPM refusal. STOP is latched by design; close and inspect after confirmed spin-down.",
        tone: "danger",
      }
    : {
        key: "awaiting_ack",
        title: "AWAITING FIRMWARE ACK",
        detail: `Shoot request ${status.fire_request.request_seq}; only the front-limit event creates a shot record.`,
        tone: "wait",
      };
}
```

- [ ] **Step 4: Make controls consume the published verdicts**

Set `canArm` to require `status.wheels_stable`, `status.fire_request === null`, and `status.pending_shot === null`. Set ordinary actuation to `live && !latched && status?.fire_request === null`; STOP remains on its existing independent path. Disable `POLL FIRMWARE` while `fire_request` exists. Disable `UNDO` when a pending shot exists:

```tsx
disabled={
  !live ||
  (status?.measurements.length ?? 0) === 0 ||
  status?.pending_shot !== null
}
```

Render stability as `samples {rpm_band_sample_count}/3 · span {wheels_in_band_s}/2.0 s`. Render the shot provenance as:

```tsx
<span className="font-mono text-[11px] text-white/45 pb-2.5">
  pre-fire L={fmt(pendingShot.rpm_left_pre_fire)} R=
  {fmt(pendingShot.rpm_right_pre_fire)} · sample age at request {" "}
  {pendingShot.rpm_pre_fire_sample_age_s.toFixed(2)} s
</span>
```

- [ ] **Step 5: Run TypeScript and parity verification**

```bash
venv/bin/python -m pytest tests/test_desktop_launcher_console.py -q \
  -p no:cacheprovider -o addopts=
cd project-cam-desktop
./node_modules/.bin/tsc --noEmit
npm run build
```

Expected: all commands exit 0. The Rust command enum is unchanged because no new operator command is introduced.

- [ ] **Step 6: Commit exact UI paths**

```bash
git add project-cam-desktop/src/blm.ts \
  project-cam-desktop/src/views/LauncherView.tsx \
  tests/test_desktop_launcher_console.py
git diff --cached --name-status
git diff --cached --check
git commit -m "fix(launcher): show confirmed shot lifecycle"
```

### Task 7: Align operator documentation and verify Slice 1

**Files:**
- Modify: `docs/protocols/2026-08-03-rpm-speed-measurement.md:149-191`
- Modify but do not stage: `.claude/rules/safety.md:88-94`
- Test: `tests/test_blm_bridge.py`
- Test: `tests/test_desktop_launcher_console.py`

- [ ] **Step 1: Correct evidence wording in the protocol**

State all of the following explicitly:

```markdown
- `shoot` is only a request; the shot counter and distance field appear only after
  `SYS: SHOT FIRED - FRONT LIMIT HIT`.
- `pre-fire L/R` is the final fresh sample which passed the gate before `shoot`,
  and its recorded age is measured at request time. It is not RPM sampled at the
  later front-limit event because telemetry is suppressed during `STATE_SHOOTING`.
- Missing ACK includes the firmware's silent below-400 RPM refusal and therefore
  produces outcome-unknown ESTOP, never a shot record.
- On `control_12`, one manual `POLL` can prove the parser but the stopped verdict
  must become unsafe when that snapshot ages past two seconds. Spin-only waits for
  `control_13`.
```

Apply the same semantic correction to the existing BLM paragraph in `.claude/rules/safety.md`, but leave that file unstaged because its current diff contains unrelated served-drill rule changes.

- [ ] **Step 2: Run focused quality checks**

```bash
venv/bin/python -m ruff check \
  garage_lab_combined/scripts/blm_bridge.py \
  tests/test_blm_bridge.py tests/test_desktop_launcher_console.py
venv/bin/python -m pytest \
  tests/test_blm_bridge.py tests/test_desktop_launcher_console.py \
  tests/test_rpm_speed_fit.py \
  -q -p no:cacheprovider -o addopts=
cd project-cam-desktop/src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test -q
```

Expected: all exit 0.

- [ ] **Step 3: Run the full software suite**

```bash
cd /home/hanush/Desktop/ProjectCam
venv/bin/pytest tests/ -p no:cacheprovider
```

Expected: all tests pass; the only allowed non-pass is the existing single skip and the known Starlette deprecation warning. Record the actual count rather than copying the previous `1114` count.

- [ ] **Step 4: Rebuild and prove binary freshness**

```bash
cd /home/hanush/Desktop/ProjectCam
./project-cam-desktop/rebuild.sh
./project-cam-desktop/check-binary-fresh.sh
```

Expected: rebuild exits 0 and freshness exits 0. Do not launch the application.

- [ ] **Step 5: Check evidence preservation and diff hygiene**

```bash
sha256sum garage_lab_combined/cal/blm/rpm_speed_shots.jsonl
git diff --check
git status --short
```

Expected: the JSONL still has four pre-existing v1 rows, its SHA-256 is
`8d03b211d2245eb684deac4ee212ec33eae9506e2bbe218a9bc098d525dd6a45`, no new
line exists, no `rpm_speed_model.json` is created, and only intended source/doc
changes appear.

- [ ] **Step 6: Commit the protocol only**

```bash
git add docs/protocols/2026-08-03-rpm-speed-measurement.md
git diff --cached --name-status
git diff --cached --check
git commit -m "docs(blm): define confirmed-shot calibration evidence"
```

Do not stage `.claude/rules/safety.md`, `docs/ml_ds_interview_qa_ru.md`, `garage_lab_combined/cal/blm/`, or served-drill files.

- [ ] **Step 7: Stop at the no-fire handoff**

Report the software evidence and ask the operator to reopen the rebuilt console with fire control disabled. The next physical action is one manual `POLL` on `control_12`; it is not part of automated execution and must begin with the barrel physically level before the port is opened.
