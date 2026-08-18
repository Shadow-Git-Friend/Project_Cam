# control_15 Closed-Loop Flywheel RPM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and compile, but do not flash, a `control_15` firmware that independently holds both commanded flywheel speeds with bounded PI correction while preserving the complete `control_14` command and safety boundary.

**Architecture:** `control_15_full.ino` is derived byte-for-byte from `control_14_full.ino` except for identity, the exactly parsed `updateMotorPWM()` body, and an enumerated set of marked controller blocks. The existing feed-forward maps remain primary; each fresh 200 ms encoder sample updates an independent bounded PI trim, while the existing 5 us/200 ms actuator ramp remains unchanged. Static projection contracts protect the deployed firmware boundary, and a deterministic first-order plant simulation checks the control hypothesis without pretending to replace hardware acceptance.

**Tech Stack:** Arduino/C++ on ESP32, Arduino-ESP32 core 3.3.7, Arduino CLI 1.4.1 bundled in Arduino IDE 2.3.8, Python 3/pytest, deterministic pure-Python plant simulation.

---

## Execution boundary

This plan is executed inline in the current branch. No subagent is used. It ends
after a successful compile and recorded source/binary hashes. It does not open a
serial port, upload, add `control_15` to `COMMISSIONED_FIRMWARE`, fire, or issue
an aim/YAW command.

Before adding any mechanism, retain evidence that the direct path lacks the
required behaviour:

- `control_14::updateMotorPWM()` reads targets and feed-forward maps only; it
  never reads `currentRPM_Left` or `currentRPM_Right`;
- on 2026-08-18, command 500 produced about L=447..457/R=510..517 after the ball
  was removed, so the static error is not a chamber-contact artefact;
- independent video already validated the encoder scale, so changing PPR or the
  requested RPM is not a correction;
- `_do_wheels` already holds boot-zero YAW stationary through the existing
  `set 0 0 N N` path, so no firmware command or YAW bypass is justified;
- direct Arduino CLI compilation of the root file was measured to fail with
  `main file missing from sketch: ProjectCam.ino`; copying the unchanged file
  into a temporary same-name sketch directory compiled `control_14` successfully
  at 1,123,186 program bytes. Therefore use a temporary sketch directory, not a
  repository build wrapper.

## File map

- Create `control_15_full.ino`: the candidate firmware and nothing else.
- Create `tests/test_control_15_closed_loop_rpm.py`: immutable-source,
  grammar, projection, controller, fault, host-boundary, and parser contracts.
- Create `scripts/simulate_control_15_rpm.py`: deterministic controller/plant
  model used only as software evidence.
- Modify `tests/test_control_15_closed_loop_rpm.py`: add simulation acceptance
  after the firmware contracts are green.
- Create `garage_lab_combined/cal/blm/control_15_tuning.jsonl`: one pre-flash
  build record with `hardware_iteration: null`; flashed iterations are added
  only after separate operator approval.
- Never modify `control_12_full.ino`, `control_13_full.ino`,
  `control_14_full.ino`, or the bridge/UI safety constants.

## Task 1: Pin the entire absent-candidate contract in RED

**Files:**
- Create: `tests/test_control_15_closed_loop_rpm.py`
- Read only: `control_12_full.ino`
- Read only: `control_13_full.ino`
- Read only: `control_14_full.ino`
- Read only: `garage_lab_combined/scripts/blm_bridge.py`

- [ ] **Step 1: Write the source helpers and immutable boundary**

Start the test file with these exact paths, hashes, grammar extractor, balanced
function parser, and candidate loader. Every contract calls `control_15_source()`
first, so the complete suite is red against the absent file rather than partly
green for unrelated reasons.

```python
import hashlib
import importlib.util
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROL_12 = ROOT / "control_12_full.ino"
CONTROL_13 = ROOT / "control_13_full.ino"
CONTROL_14 = ROOT / "control_14_full.ino"
CONTROL_15 = ROOT / "control_15_full.ino"
BRIDGE = ROOT / "garage_lab_combined/scripts/blm_bridge.py"

PINNED = {
    CONTROL_12: "eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e",
    CONTROL_13: "54367d26e9dee54283beba08f0d41297ddacaae2538b296349f0b00eb946049f",
    CONTROL_14: "a43b2ef809e20b9b7860e0211b82e74fafb52f3a9d4af9c84f98af3ec6377477",
}

EXPECTED_EXACT = {"shoot", "reload", "setzero", "center", "stop", "info"}
EXPECTED_PREFIXES = {
    "set ", "jsset", "jfspeedset", "jfaccelset", "jv", "jh", "js", "jf",
}

BLOCK_NAMES = (
    "RPM_CONTROLLER_STATE",
    "SET_TARGET_VALIDATION",
    "SET_TARGET_TRANSITION",
    "RELOAD_TARGET_TRANSITION",
    "STOP_TARGET_TRANSITION",
    "SHOOT_FAULT_GATE",
    "INFO_CONTROLLER_DIAGNOSTIC",
    "RPM_FRESH_SAMPLE_UPDATE",
    "SHOOTING_FAULT_GATE",
)

def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def control_15_source() -> str:
    assert CONTROL_15.exists(), "control_15_full.ino must be absent for the RED run"
    return text(CONTROL_15)

def firmware_commands(source: str) -> tuple[set[str], set[str]]:
    exact = set(re.findall(r'equalsIgnoreCase\("([^"]+)"\)', source))
    prefixes = set(re.findall(r'startsWith\("([^"]+)"\)', source))
    return exact, prefixes

def function_body_span(source: str, name: str) -> tuple[int, int]:
    matches = list(re.finditer(rf"\bvoid\s+{re.escape(name)}\s*\(\s*\)\s*\{{", source))
    assert len(matches) == 1, f"expected exactly one {name}() definition"
    opening = source.index("{", matches[0].start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return opening + 1, index
    raise AssertionError(f"unclosed {name}() body")
```

- [ ] **Step 2: Write the strict projection before the firmware exists**

The projection accepts only the exact `updateMotorPWM()` body, identity, and
the named blocks. Marker parsing is stack-based so nested, reordered,
duplicated, missing, or unknown markers cannot silently widen the exemption.

```python
MARKER = re.compile(
    r"^[ \t]*// --- CONTROL_15 (?P<name>[A-Z_]+) (?P<edge>BEGIN|END) ---[ \t]*$",
    re.MULTILINE,
)

def remove_controller_blocks(source: str) -> str:
    markers = list(MARKER.finditer(source))
    pairs: list[tuple[int, int, str]] = []
    stack: list[re.Match[str]] = []
    for marker in markers:
        name, edge = marker.group("name"), marker.group("edge")
        assert name in BLOCK_NAMES, f"unknown controller block {name}"
        if edge == "BEGIN":
            assert not stack, "controller blocks must not nest"
            stack.append(marker)
        else:
            assert stack, f"orphan END for {name}"
            begin = stack.pop()
            assert begin.group("name") == name, "mismatched controller block"
            end = marker.end()
            if end < len(source) and source[end] == "\n":
                end += 1
            pairs.append((begin.start(), end, name))
    assert not stack, "unclosed controller block"
    counts = Counter(name for _, _, name in pairs)
    assert counts == Counter(BLOCK_NAMES), f"controller block set drifted: {counts}"
    for start, end, _ in reversed(pairs):
        source = source[:start] + source[end:]
    return source

def project_to_control_14(candidate: str) -> str:
    projected = remove_controller_blocks(candidate)
    old = text(CONTROL_14)
    new_start, new_end = function_body_span(projected, "updateMotorPWM")
    old_start, old_end = function_body_span(old, "updateMotorPWM")
    projected = projected[:new_start] + old[old_start:old_end] + projected[new_end:]
    return projected.replace("control_15", "control_14")
```

- [ ] **Step 3: Write all firmware contracts before creating `control_15`**

Add these tests. Assertions inspect the controller function/marked blocks rather
than accepting matching words anywhere in comments.

```python
def block(source: str, name: str) -> str:
    pattern = re.compile(
        rf"// --- CONTROL_15 {name} BEGIN ---\n(.*?)"
        rf"// --- CONTROL_15 {name} END ---",
        re.DOTALL,
    )
    matches = pattern.findall(source)
    assert len(matches) == 1
    return matches[0]

def update_body(source: str) -> str:
    start, end = function_body_span(source, "updateMotorPWM")
    return source[start:end]

def load_bridge():
    spec = importlib.util.spec_from_file_location("control15_bridge", BRIDGE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_deployed_firmware_hashes_are_immutable():
    control_15_source()
    for path, digest in PINNED.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest

def test_control_15_grammar_equals_control_14_by_name():
    candidate = control_15_source()
    assert firmware_commands(candidate) == firmware_commands(text(CONTROL_14))
    assert firmware_commands(candidate) == (EXPECTED_EXACT, EXPECTED_PREFIXES)
    assert "wheels <" not in candidate

def test_control_15_projects_to_control_14_byte_for_byte():
    candidate = control_15_source()
    assert project_to_control_14(candidate) == text(CONTROL_14)

def test_projection_rejects_marker_drift():
    candidate = control_15_source()
    with pytest.raises(AssertionError):
        remove_controller_blocks(candidate.replace(
            "CONTROL_15 RPM_CONTROLLER_STATE BEGIN",
            "CONTROL_15 UNKNOWN_BLOCK BEGIN", 1))
    with pytest.raises(AssertionError):
        remove_controller_blocks(candidate.replace(
            "// --- CONTROL_15 RPM_CONTROLLER_STATE END ---\n", "", 1))

def test_each_wheel_has_independent_state_error_base_trim_and_output():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    body = update_body(source)
    for token in (
        "WheelControllerState leftController", "WheelControllerState rightController",
        "errorRPM", "basePWM", "integralUs", "trimUs",
        "desiredPWM_Left", "desiredPWM_Right", "currentPWM_Left", "currentPWM_Right",
    ):
        assert token in state + body
    assert "(currentRPM_Left" in body and "(currentRPM_Right" in body

def test_integrator_freezes_until_ramp_catches_but_p_stays_live():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    assert "fabs(desiredPWM - currentPWM) <= RAMP_STEP_US" in state
    assert "proportionalUs = kp * errorRPM" in state
    caught = state.index("fabs(desiredPWM - currentPWM) <= RAMP_STEP_US")
    integrate = state.index("state.integralUs = candidateIntegral", caught)
    assert caught < integrate

def test_target_reset_policy_is_strictly_greater_than_five_percent():
    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    assert "oldTarget == 0.0" in state and "newTarget == 0.0" in state
    assert "fabs(newTarget - oldTarget) > 0.05 * oldTarget" in state
    assert "fabs(newTarget - oldTarget) >= 0.05 * oldTarget" not in state
    assert "if (reset)" in state and "integralUs = 0.0" in state

def test_trim_pwm_startup_stall_and_overspeed_bounds_are_pinned():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    body = update_body(source)
    for token in (
        "MAX_TRIM_US = 30.0", "PWM_MIN_US = 1000", "PWM_MAX_US = 1800",
        "OVERSPEED_RPM = 1300.0", "NO_START_TIMEOUT_MS = 15000",
        "ENCODER_LOSS_TIMEOUT_MS = 1000",
    ):
        assert token in state
    assert "constrain(state.proportionalUs + state.integralUs," in state
    assert "constrain(state.basePWM +" in state
    assert "OVERSPEED_RPM" in state + body

def test_fault_latch_blocks_pusher_and_needs_stop_plus_fresh_zero():
    source = control_15_source()
    shoot_command = block(source, "SHOOT_FAULT_GATE")
    shoot_state = block(source, "SHOOTING_FAULT_GATE")
    state = block(source, "RPM_CONTROLLER_STATE")
    assert "rpmControllerFault != RPM_FAULT_NONE" in shoot_command
    assert "return;" in shoot_command
    assert "rpmControllerFault != RPM_FAULT_NONE" in shoot_state
    assert "pusherStepper.moveTo(0)" in shoot_state
    assert "rpmFaultStopRequested" in state
    assert "freshLeft && freshRight" in state
    assert "currentRPM_Left < 50.0" in state
    assert "currentRPM_Right < 50.0" in state

def test_compact_telemetry_stays_parser_compatible():
    source = control_15_source()
    assert 'sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);' in source
    bridge = load_bridge()
    assert bridge.parse_telemetry("L:500 R:500") == (500.0, 500.0)

def test_candidate_is_not_commissioned_and_host_gates_are_unchanged():
    control_15_source()
    bridge = text(BRIDGE)
    assert 'COMMISSIONED_FIRMWARE = ("control_13", "control_14")' in bridge
    assert "RPM_BAND_FRAC = 0.10" in bridge
    assert "RPM_BAND_FLOOR = 50.0" in bridge
    assert "RPM_SPREAD_MAX = 75.0" in bridge
    assert "RPM_MIN_FIRE = 400" in bridge
```

- [ ] **Step 4: Run the complete contract and verify RED**

Run:

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py -q
```

Expected: 11 failed tests. Every failure is rooted in the explicit absence of
`control_15_full.ino`; collection itself succeeds.

- [ ] **Step 5: Commit the RED contract**

```bash
git add tests/test_control_15_closed_loop_rpm.py
git diff --cached --check
git commit -m "test(firmware): define control 15 RPM controller contract"
```

## Task 2: Establish identity, grammar, and byte projection

**Files:**
- Create: `control_15_full.ino`
- Test: `tests/test_control_15_closed_loop_rpm.py`

- [ ] **Step 1: Re-run the identity/grammar/projection slice while absent**

Run:

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'immutable or grammar or projects or projection' -q
```

Expected: RED because `control_15_full.ino` does not exist.

- [ ] **Step 2: Copy only the deployed rollback source and change identity**

Copy `control_14_full.ino` byte-for-byte to `control_15_full.ino`, then use
`apply_patch` to change only these two executable identity literals:

```cpp
const char* FIRMWARE_ID = "control_15";
```

```cpp
Serial.println("SYS: FW control_15 READY");
```

Do not change command parsing, `set`, ramp constants, stepper behaviour, feeder,
or compact telemetry.

- [ ] **Step 3: Verify the measured direct behaviours before adding controller code**

Run:

```bash
rg -n 'void updateMotorPWM|currentRPM_Left|currentRPM_Right|horzStepper.moveTo' \
  control_15_full.ino
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'immutable or grammar' -q
```

Expected: immutable hashes and grammar pass. Controller/projection tests remain
red because the marked controller is still absent. This is the checkpoint that
prevents adding a protocol workaround for behaviour the direct path already has.

## Task 3: Implement independent PI state and target-transition policy

**Files:**
- Modify: `control_15_full.ino`
- Test: `tests/test_control_15_closed_loop_rpm.py`

- [ ] **Step 1: Run the controller-math slice and verify RED**

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'independent or integrator or target_reset or bounds' -q
```

Expected: RED because the state block and PI logic do not exist.

- [ ] **Step 2: Add the marked controller state block**

Immediately after the existing feeder state variables, add one
`RPM_CONTROLLER_STATE` block containing:

```cpp
// --- CONTROL_15 RPM_CONTROLLER_STATE BEGIN ---
const double LEFT_KP = 0.12;
const double RIGHT_KP = 0.12;
const double LEFT_KI = 0.08;
const double RIGHT_KI = 0.08;
const double MAX_TRIM_US = 30.0;
const int PWM_MIN_US = 1000;
const int PWM_MAX_US = 1800;
const double OVERSPEED_RPM = 1300.0;
const unsigned long NO_START_TIMEOUT_MS = 15000;
const unsigned long ENCODER_LOSS_TIMEOUT_MS = 1000;

struct WheelControllerState {
  double lastTarget = 0.0;
  double errorRPM = 0.0;
  int basePWM = PWM_MIN_US;
  double proportionalUs = 0.0;
  double integralUs = 0.0;
  double trimUs = 0.0;
  unsigned long lastSampleMs = 0;
  unsigned long activeSinceMs = 0;
  unsigned long belowFiftySinceMs = 0;
  bool started = false;
  bool exceeded200 = false;
};

WheelControllerState leftController;
WheelControllerState rightController;

enum RpmFault : uint8_t {
  RPM_FAULT_NONE = 0,
  RPM_FAULT_NO_START_L = 1 << 0,
  RPM_FAULT_NO_START_R = 1 << 1,
  RPM_FAULT_ENCODER_LOSS_L = 1 << 2,
  RPM_FAULT_ENCODER_LOSS_R = 1 << 3,
  RPM_FAULT_OVERSPEED_L = 1 << 4,
  RPM_FAULT_OVERSPEED_R = 1 << 5,
};

uint8_t rpmControllerFault = RPM_FAULT_NONE;
bool rpmFaultStopRequested = false;
bool rpmFreshLeft = false;
bool rpmFreshRight = false;

bool targetChangeResets(double oldTarget, double newTarget) {
  if ((oldTarget == 0.0) != (newTarget == 0.0)) return true;
  return oldTarget > 0.0 && newTarget > 0.0
      && fabs(newTarget - oldTarget) > 0.05 * oldTarget;
}

void resetWheelController(WheelControllerState &state, unsigned long now) {
  state.errorRPM = 0.0;
  state.proportionalUs = 0.0;
  state.integralUs = 0.0;
  state.trimUs = 0.0;
  state.lastSampleMs = 0;
  state.activeSinceMs = now;
  state.belowFiftySinceMs = 0;
  state.started = false;
  state.exceeded200 = false;
}

void noteTargetTransition(WheelControllerState &state,
                          double newTarget,
                          unsigned long now) {
  bool reset = targetChangeResets(state.lastTarget, newTarget);
  if (reset) resetWheelController(state, now);
  state.lastTarget = newTarget;
}

void updateWheelController(WheelControllerState &state,
                           double targetRPM,
                           double measuredRPM,
                           double slope,
                           int offset,
                           double kp,
                           double ki,
                           int currentPWM,
                           int &desiredPWM,
                           bool fresh,
                           unsigned long now) {
  if (targetRPM < MIN_RPM_THRESHOLD) {
    state.basePWM = PWM_MIN_US;
    state.errorRPM = 0.0;
    state.proportionalUs = 0.0;
    state.trimUs = 0.0;
    desiredPWM = PWM_MIN_US;
    return;
  }

  state.basePWM = constrain((int)(targetRPM * slope + offset),
                            PWM_MIN_US, PWM_MAX_US);
  if (!fresh) {
    // A command changes the feed-forward destination immediately, but P is
    // evidence from a fresh sample only. Preserve learned I on <=5% changes.
    state.errorRPM = 0.0;
    state.proportionalUs = 0.0;
  } else {
    double dt = state.lastSampleMs == 0 ? 0.2 : (now - state.lastSampleMs) / 1000.0;
    state.lastSampleMs = now;
    state.errorRPM = targetRPM - measuredRPM;
    state.proportionalUs = kp * state.errorRPM;
    bool rampCaught = fabs(desiredPWM - currentPWM) <= RAMP_STEP_US;
    if (rampCaught) {
      double candidateIntegral = constrain(
          state.integralUs + ki * state.errorRPM * dt,
          -MAX_TRIM_US, MAX_TRIM_US);
      double candidateTrim = state.proportionalUs + candidateIntegral;
      double candidatePWM = state.basePWM + candidateTrim;
      bool pushesHigh = candidateTrim > MAX_TRIM_US && state.errorRPM > 0.0;
      bool pushesLow = candidateTrim < -MAX_TRIM_US && state.errorRPM < 0.0;
      bool pushesPwmHigh = candidatePWM > PWM_MAX_US && state.errorRPM > 0.0;
      bool pushesPwmLow = candidatePWM < PWM_MIN_US && state.errorRPM < 0.0;
      if (!pushesHigh && !pushesLow && !pushesPwmHigh && !pushesPwmLow) {
        state.integralUs = candidateIntegral;
      }
    }
  }
  state.trimUs = constrain(state.proportionalUs + state.integralUs,
                           -MAX_TRIM_US, MAX_TRIM_US);
  desiredPWM = constrain(state.basePWM + (int)lround(state.trimUs),
                         PWM_MIN_US, PWM_MAX_US);
}
// --- CONTROL_15 RPM_CONTROLLER_STATE END ---
```

This preserves P updates while the ramp is travelling and freezes only I. The
existing ramp remains the sole writer of `currentPWM_*`.

- [ ] **Step 3: Replace exactly the parsed `updateMotorPWM()` body**

Keep the signature and surrounding bytes unchanged. Its new body calls the same
helper independently for left and right and consumes fresh flags exactly once:

```cpp
  unsigned long now = millis();
  updateWheelController(leftController, targetRPM_Left, currentRPM_Left,
                        LEFT_SLOPE, LEFT_OFFSET, LEFT_KP, LEFT_KI,
                        currentPWM_Left, desiredPWM_Left, rpmFreshLeft, now);
  updateWheelController(rightController, targetRPM_Right, currentRPM_Right,
                        RIGHT_SLOPE, RIGHT_OFFSET, RIGHT_KP, RIGHT_KI,
                        currentPWM_Right, desiredPWM_Right, rpmFreshRight, now);
  rpmFreshLeft = false;
  rpmFreshRight = false;
```

- [ ] **Step 4: Add only marked target hooks around the unchanged grammar**

Before the existing target assignments in `set`, add `SET_TARGET_VALIDATION`.
It parses both strings with `strtod`, requires complete finite values in
0..1200, emits `ERR: RPM RANGE`, and returns without changing either target on
failure. After the original assignments add:

```cpp
// --- CONTROL_15 SET_TARGET_TRANSITION BEGIN ---
noteTargetTransition(leftController, targetRPM_Left, millis());
noteTargetTransition(rightController, targetRPM_Right, millis());
// --- CONTROL_15 SET_TARGET_TRANSITION END ---
```

After the unchanged zero assignments in `reload` and `stop`, add single-purpose
`RELOAD_TARGET_TRANSITION` and `STOP_TARGET_TRANSITION` blocks. Both reset the
two controller states unconditionally and set both remembered targets to zero,
even if the command arrived while targets were already zero. The stop block also
sets `rpmFaultStopRequested = true` when a fault is latched. No token, prefix,
angle, or wheel-argument shape changes.

- [ ] **Step 5: Add the marked fresh-sample hook**

After both existing `getRPM` assignments in `loop()`, add:

```cpp
// --- CONTROL_15 RPM_FRESH_SAMPLE_UPDATE BEGIN ---
rpmFreshLeft = tempL != -1;
rpmFreshRight = tempR != -1;
if (rpmFreshLeft || rpmFreshRight) updateMotorPWM();
// --- CONTROL_15 RPM_FRESH_SAMPLE_UPDATE END ---
```

- [ ] **Step 6: Run the controller slice and keep unrelated fault tests RED**

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'independent or integrator or target_reset or bounds' -q
```

Expected: independent state, ramp freeze, reset threshold, and numeric-bound
contracts pass. Fault/projection tests remain red until Task 4.

## Task 4: Add bounded faults, pusher interlock, diagnostics, and projection GREEN

**Files:**
- Modify: `control_15_full.ino`
- Test: `tests/test_control_15_closed_loop_rpm.py`

- [ ] **Step 1: Run the fault/parser/projection slice and verify RED**

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'fault or telemetry or projects or projection or commissioned' -q
```

Expected: RED for missing fault hooks/markers; host safety constants remain
unchanged.

- [ ] **Step 2: Add fault evaluation inside the state block**

Implement finite bitmask construction per fresh sample:

- measured RPM above 1300 immediately adds the side's overspeed bit;
- target at least 200 that has not reached 100 within 15 seconds adds NO_START;
- after exceeding 200, target at least 400 and measured below 50 continuously
  for one second adds ENCODER_LOSS;
- left/right bits found in the same update are latched and reported together;
- latching once forces both targets and desired duties to zero/1000, clears both
  integrators, stops feeder motion, and emits one
  `SYS: RPM CTRL FAULT - <finite-code>` line;
- while latched, `updateMotorPWM()` holds both destinations at 1000;
- clear only after `stop` was received and one later update has fresh left and
  right samples both below 50.

Use a finite formatter whose only components are `NO_START_L/R`,
`ENCODER_LOSS_L/R`, and `OVERSPEED_L/R`; join simultaneous bits with `+`.

The implementation added inside `RPM_CONTROLLER_STATE` is:

```cpp
void appendRpmFaultName(String &name, uint8_t faults,
                        uint8_t bit, const char *label) {
  if ((faults & bit) == 0) return;
  if (name.length() > 0) name += "+";
  name += label;
}

String formatRpmFault(uint8_t faults) {
  if (faults == RPM_FAULT_NONE) return "NONE";
  String name;
  appendRpmFaultName(name, faults, RPM_FAULT_NO_START_L, "NO_START_L");
  appendRpmFaultName(name, faults, RPM_FAULT_NO_START_R, "NO_START_R");
  appendRpmFaultName(name, faults, RPM_FAULT_ENCODER_LOSS_L, "ENCODER_LOSS_L");
  appendRpmFaultName(name, faults, RPM_FAULT_ENCODER_LOSS_R, "ENCODER_LOSS_R");
  appendRpmFaultName(name, faults, RPM_FAULT_OVERSPEED_L, "OVERSPEED_L");
  appendRpmFaultName(name, faults, RPM_FAULT_OVERSPEED_R, "OVERSPEED_R");
  return name;
}

uint8_t evaluateWheelFault(WheelControllerState &state,
                           double targetRPM,
                           double measuredRPM,
                           bool fresh,
                           unsigned long now,
                           uint8_t noStartBit,
                           uint8_t encoderLossBit,
                           uint8_t overspeedBit) {
  if (!fresh) return RPM_FAULT_NONE;
  uint8_t faults = RPM_FAULT_NONE;
  if (measuredRPM > OVERSPEED_RPM) faults |= overspeedBit;
  if (targetRPM < MIN_RPM_THRESHOLD) {
    state.belowFiftySinceMs = 0;
    return faults;
  }
  if (measuredRPM >= 100.0) state.started = true;
  if (measuredRPM > 200.0) state.exceeded200 = true;
  if (!state.started && now - state.activeSinceMs >= NO_START_TIMEOUT_MS) {
    faults |= noStartBit;
  }
  if (targetRPM >= MIN_FEED_RPM && state.exceeded200 && measuredRPM < 50.0) {
    if (state.belowFiftySinceMs == 0) state.belowFiftySinceMs = now;
    else if (now - state.belowFiftySinceMs >= ENCODER_LOSS_TIMEOUT_MS) {
      faults |= encoderLossBit;
    }
  } else {
    state.belowFiftySinceMs = 0;
  }
  return faults;
}

void latchRpmFault(uint8_t faults, unsigned long now) {
  if (faults == RPM_FAULT_NONE || rpmControllerFault != RPM_FAULT_NONE) return;
  rpmControllerFault = faults;
  rpmFaultStopRequested = false;
  targetRPM_Left = 0.0;
  targetRPM_Right = 0.0;
  desiredPWM_Left = PWM_MIN_US;
  desiredPWM_Right = PWM_MIN_US;
  resetWheelController(leftController, now);
  resetWheelController(rightController, now);
  leftController.lastTarget = 0.0;
  rightController.lastTarget = 0.0;
  pusherStepper.setCurrentPosition(0);
  pusherStepper.moveTo(0);
  currentState = STATE_IDLE;
  feederServo.write(STOP_SPEED);
  sendMsg("SYS: RPM CTRL FAULT - " + formatRpmFault(faults));
}

bool clearRpmFaultIfSafe(bool freshLeft, bool freshRight,
                         unsigned long now) {
  if (rpmControllerFault == RPM_FAULT_NONE || !rpmFaultStopRequested) return false;
  if (!(freshLeft && freshRight)) return false;
  if (!(currentRPM_Left < 50.0 && currentRPM_Right < 50.0)) return false;
  rpmControllerFault = RPM_FAULT_NONE;
  rpmFaultStopRequested = false;
  resetWheelController(leftController, now);
  resetWheelController(rightController, now);
  leftController.lastTarget = targetRPM_Left;
  rightController.lastTarget = targetRPM_Right;
  return true;
}
```

In the new `updateMotorPWM()` body, replace Task 3's two final fresh-flag reset
lines with this fault evaluation; its own final lines consume those flags only
after fault construction and safe-clear evaluation:

```cpp
  uint8_t faults = RPM_FAULT_NONE;
  faults |= evaluateWheelFault(leftController, targetRPM_Left, currentRPM_Left,
                               rpmFreshLeft, now, RPM_FAULT_NO_START_L,
                               RPM_FAULT_ENCODER_LOSS_L, RPM_FAULT_OVERSPEED_L);
  faults |= evaluateWheelFault(rightController, targetRPM_Right, currentRPM_Right,
                               rpmFreshRight, now, RPM_FAULT_NO_START_R,
                               RPM_FAULT_ENCODER_LOSS_R, RPM_FAULT_OVERSPEED_R);
  if (rpmControllerFault == RPM_FAULT_NONE) latchRpmFault(faults, now);
  else {
    desiredPWM_Left = PWM_MIN_US;
    desiredPWM_Right = PWM_MIN_US;
    clearRpmFaultIfSafe(rpmFreshLeft, rpmFreshRight, now);
  }
  rpmFreshLeft = false;
  rpmFreshRight = false;
```

- [ ] **Step 3: Add two explicit pusher guards**

At the start of the existing `shoot` command branch:

```cpp
// --- CONTROL_15 SHOOT_FAULT_GATE BEGIN ---
if (rpmControllerFault != RPM_FAULT_NONE) {
  sendMsg("CMD: SHOOT BLOCKED - RPM CTRL FAULT");
  return;
}
// --- CONTROL_15 SHOOT_FAULT_GATE END ---
```

At the start of `case STATE_SHOOTING`:

```cpp
// --- CONTROL_15 SHOOTING_FAULT_GATE BEGIN ---
if (rpmControllerFault != RPM_FAULT_NONE) {
  pusherStepper.setCurrentPosition(0);
  pusherStepper.moveTo(0);
  currentState = STATE_IDLE;
  break;
}
// --- CONTROL_15 SHOOTING_FAULT_GATE END ---
```

The first prevents entry; the second is defence in depth if a fault arrives
after the state was entered.

- [ ] **Step 4: Add one USB-authoritative INFO diagnostic record**

Inside `info`, after the existing BLE diagnostic, add only this marked block:

```cpp
// --- CONTROL_15 INFO_CONTROLLER_DIAGNOSTIC BEGIN ---
char buf7[120];
String rpmFaultName = formatRpmFault(rpmControllerFault);
snprintf(buf7, sizeof(buf7),
         "INFO | CTRL: PL=%d PR=%d IL=%.2f IR=%.2f FAULT=%s",
         currentPWM_Left, currentPWM_Right,
         leftController.integralUs, rightController.integralUs,
         rpmFaultName.c_str());
sendMsg(String(buf7));
// --- CONTROL_15 INFO_CONTROLLER_DIAGNOSTIC END ---
```

Do not alter the compact `L:<rpm> R:<rpm>` line.

- [ ] **Step 5: Run all 11 firmware contracts GREEN**

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py -q
```

Expected: 11 passed. If projection fails, narrow or relocate the marked change;
never widen `project_to_control_14()` to make an unexplained byte disappear.

- [ ] **Step 6: Commit the candidate and green contract**

```bash
git add control_15_full.ino tests/test_control_15_closed_loop_rpm.py
git diff --cached --check
git commit -m "feat(firmware): add bounded closed-loop wheel RPM"
```

## Task 5: Prove the control hypothesis in a deterministic simulation

**Files:**
- Create: `scripts/simulate_control_15_rpm.py`
- Modify: `tests/test_control_15_closed_loop_rpm.py`

- [ ] **Step 1: Add simulation tests before the simulator exists**

Append tests importing `simulate_pair` and require:

```python
def test_feed_forward_alone_retains_measured_static_error():
    from scripts.simulate_control_15_rpm import simulate_pair

    result = simulate_pair(target_rpm=500.0, closed_loop=False, duration_s=35.0)
    assert abs(result.left.final_rpm - 500.0) >= 25.0
    assert abs(result.right.final_rpm - 500.0) >= 25.0

def test_pi_converges_without_crossing_trim_pwm_or_overspeed_bounds():
    from scripts.simulate_control_15_rpm import simulate_pair

    result = simulate_pair(target_rpm=500.0, closed_loop=True, duration_s=45.0)
    for wheel in (result.left, result.right):
        assert abs(wheel.final_rpm - 500.0) <= 5.0
        assert wheel.max_abs_trim_us <= 30.0
        assert 1000 <= wheel.min_pwm <= wheel.max_pwm <= 1800
        assert wheel.max_rpm < 1300.0
        assert wheel.integrated_while_ramping == 0
```

Import through `scripts.simulate_control_15_rpm`. Run:

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'feed_forward_alone or pi_converges' -q
```

Expected: two failures with `ModuleNotFoundError` because the simulator is
absent. Firmware contract tests remain green.

- [ ] **Step 2: Implement the smallest deterministic plant/model**

Create a pure-Python model with:

- sample/ramp period 0.2 s and step 5 us;
- feed-forward slopes/offsets copied from firmware;
- independent fixed disturbances of -60 RPM left and +70 RPM right, both below
  the measured worst-case 109 RPM;
- first-order plant time constant 0.8 s;
- the same Kp/Ki, ramp-caught integration gate, trim clamp, and PWM clamp as the
  firmware;
- a counter incremented if integral changes while
  `abs(desired_pwm-current_pwm) > 5`;
- immutable result dataclasses reporting final/max RPM, PWM extrema, trim
  extrema, and forbidden integration count.

The open-loop run uses the same plant and feed-forward but forces trim to zero.
No random numbers, fitted gains, or hardware claims are allowed.

- [ ] **Step 3: Run the simulation RED/GREEN acceptance**

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py \
  -k 'feed_forward_alone or pi_converges' -q
./venv/bin/python scripts/simulate_control_15_rpm.py --target-rpm 500
```

Expected: two tests pass; CLI prints the open-loop residual, PI final L/R,
trim/PWM extrema, and `integrated_while_ramping=0` for both wheels.

- [ ] **Step 4: Commit simulation evidence code**

```bash
git add scripts/simulate_control_15_rpm.py tests/test_control_15_closed_loop_rpm.py
git diff --cached --check
git commit -m "test(firmware): simulate control 15 RPM convergence"
```

## Task 6: Run the complete software gate and compile the exact artifact

**Files:**
- Test: `control_15_full.ino`
- Test: `tests/test_control_15_closed_loop_rpm.py`
- Test: existing firmware/bridge tests
- Create: `garage_lab_combined/cal/blm/control_15_tuning.jsonl`
- Local ignored artifact: `artifacts_local/control_15/${source_sha256}/`

- [ ] **Step 1: Run focused and regression tests**

```bash
./venv/bin/python -m pytest \
  tests/test_control_15_closed_loop_rpm.py \
  tests/test_control_14_esc_ramp_contract.py \
  tests/test_blm_firmware_contract.py \
  tests/test_blm_bridge.py -q
```

Expected: all pass with an actual count reported. Any change to the three pinned
hashes, grammar, host bands, spread, gate, compact parser, or fire interlock
blocks compilation.

- [ ] **Step 2: Re-extract the exact bundled CLI and verify versions**

Use `/home/hanush/Arduino/arduino-ide_2.3.8_Linux_64bit.AppImage`. Determine its
offset with `--appimage-offset`, extract only
`resources/app/lib/backend/resources/arduino-cli` through `unsquashfs`, then run:

```bash
arduino-cli version
arduino-cli core list
```

Require CLI `1.4.1` and `esp32:esp32 3.3.7`. Do not install or update anything.

- [ ] **Step 3: Compile without upload and retain the exact binary locally**

Compute the source SHA-256 first. Under ignored
`artifacts_local/control_15/${source_sha256}/`, create `sketch/control_15_full/`
and `build/`; copy the exact source to
`sketch/control_15_full/control_15_full.ino`. Compile with:

```bash
arduino-cli compile \
  --fqbn esp32:esp32:esp32 \
  --build-path "$artifact_dir/build" \
  "$artifact_dir/sketch/control_15_full"
```

Capture complete output in `compile.log` with `set -o pipefail`. Require exit 0,
record sketch program/global sizes, and calculate SHA-256/byte size for
`build/control_15_full.ino.bin`. Do not invoke `upload`, name a port, or open
pyserial.

- [ ] **Step 4: Generate and append one unambiguous pre-flash journal record**

Derive every dynamic field from the retained files and compiler log, then print
the exact JSON line without writing it through a shell redirection:

```bash
source_sha256=$(sha256sum control_15_full.ino | awk '{print $1}')
artifact_dir="artifacts_local/control_15/${source_sha256}"
binary_path="$artifact_dir/build/control_15_full.ino.bin"
binary_sha256=$(sha256sum "$binary_path" | awk '{print $1}')
binary_bytes=$(stat -c %s "$binary_path")
program_bytes=$(sed -nE 's/^Sketch uses ([0-9]+) bytes.*/\1/p' \
  "$artifact_dir/compile.log" | tail -n 1)
global_bytes=$(sed -nE 's/^Global variables use ([0-9]+) bytes.*/\1/p' \
  "$artifact_dir/compile.log" | tail -n 1)
recorded_at=$(date --iso-8601=seconds)
./venv/bin/python - "$recorded_at" "$source_sha256" "$binary_sha256" \
  "$binary_bytes" "$program_bytes" "$global_bytes" "$artifact_dir" <<'PY'
import json
import sys

recorded_at, source_sha, binary_sha, binary_bytes, program_bytes, global_bytes, artifact_dir = sys.argv[1:]
print(json.dumps({
    "record_type": "preflash_build",
    "recorded_at": recorded_at,
    "hardware_iteration": None,
    "flashed": False,
    "source_sha256": source_sha,
    "binary_sha256": binary_sha,
    "binary_bytes": int(binary_bytes),
    "program_bytes": int(program_bytes),
    "global_bytes": int(global_bytes),
    "arduino_ide": "2.3.8",
    "arduino_cli": "1.4.1",
    "arduino_esp32_core": "3.3.7",
    "fqbn": "esp32:esp32:esp32",
    "compile_exit": 0,
    "artifact_dir": artifact_dir,
}, separators=(",", ":"), sort_keys=True))
PY
```

Insert that printed line with `apply_patch`, then validate every line with
`json.loads()`. This pre-flash record does not consume one of the four hardware
iterations.

- [ ] **Step 5: Verify and commit build evidence**

```bash
./venv/bin/python -m pytest tests/test_control_15_closed_loop_rpm.py -q
sha256sum control_12_full.ino control_13_full.ino control_14_full.ino \
  control_15_full.ino
git diff --check
git status --short
git add garage_lab_combined/cal/blm/control_15_tuning.jsonl
git commit -m "docs(firmware): record control 15 preflash build"
```

Expected: only the JSONL record is committed in this step; the binary and log
remain under ignored `artifacts_local/`.

## Task 7: Stop at the pre-flash handoff

**Files:**
- Read only: all files from Tasks 1-6

- [ ] **Step 1: Run final verification from the committed tree**

```bash
git status --short --branch
git diff --check HEAD^
./venv/bin/python -m pytest \
  tests/test_control_15_closed_loop_rpm.py \
  tests/test_control_14_esc_ramp_contract.py \
  tests/test_blm_firmware_contract.py \
  tests/test_blm_bridge.py -q
```

Report exact test count, source/binary hashes, program/global sizes, artifact
path, and that no serial device was opened.

- [ ] **Step 2: Stop without flashing**

Do not flash after green tests. The next action requires a new explicit operator
message.

Before requesting that permission, remind the operator that the unpowered
mechanical localisation test for the observed 6--7 degree YAW reversal lost
motion is still outstanding. A flash resets the board's logical zero; if a hub,
coupler, or key is loose, the assumption that physical YAW stays fixed is not
established.

If later authorised, hardware commissioning starts with 400..1000 only. Review
and accept that complete ladder before asking separately for 1100, then
separately for 1200. No fire and no YAW command are allowed. At most four changed
source hashes may be flashed for tuning; after the fourth unsuccessful hardware
iteration, stop and return the four records because the model, not merely the
coefficients, must be reconsidered.
