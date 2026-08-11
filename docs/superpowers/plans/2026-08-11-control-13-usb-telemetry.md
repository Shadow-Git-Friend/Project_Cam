# Control 13 USB Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create an explicitly identifiable `control_13` firmware candidate which continuously reports actual flywheel RPM over USB through coast-down to zero without blocking the cooperative state machine.

**Architecture:** `control_12_full.ino` remains immutable and deployed until a separate flash checkpoint. `control_13_full.ino` preserves its command grammar, limits, and 921600-baud transport, but removes BLE/PWM suppression from the IDLE telemetry emitter and removes all `info` delays. Source-contract tests pin the old firmware hash and the new protocol before any hardware interaction.

**Tech Stack:** ESP32 Arduino C++, Python 3.10 source-contract tests, pytest, existing Python serial consumers, React/TypeScript identity display.

---

## Execution boundaries

- Prerequisite: complete `docs/superpowers/plans/2026-08-11-blm-confirmed-shot-host.md` through its no-fire handoff.
- Design authority: `docs/superpowers/specs/2026-08-11-blm-telemetry-confirmed-shot-design.md` at commit `c25273e`.
- Never edit `control_12_full.ino`; its pinned SHA-256 is `eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e`.
- Tasks 1–5 are software-only. Do not open serial, flash the ESP32, move axes, spin wheels, ARM, or fire.
- Task 6 is an operator checkpoint, not an autonomous agent action. Stop and obtain explicit confirmation immediately before opening the firmware tool or serial port.
- `arduino-cli`, PlatformIO, and the Arduino CLI compiler are not currently installed on PATH. Source tests are not a compile substitute; no flash is allowed until the existing Arduino IDE successfully compiles the exact candidate with the deployed board settings.

## File map

- `control_12_full.ino` — immutable deployed firmware reference.
- `control_13_full.ino` — new candidate with observable identity and non-blocking USB telemetry.
- `tests/test_blm_firmware_contract.py` — immutable-hash, protocol, telemetry, delay, and serial-consumer contracts.
- `garage_lab_combined/scripts/blm_bridge.py` — parse and publish firmware identity.
- `tests/test_blm_bridge.py` — identity parser/status behavior.
- `project-cam-desktop/src/blm.ts` — additive `firmware_id` status field.
- `project-cam-desktop/src/views/LauncherView.tsx` — visible firmware identity.
- `tests/test_desktop_launcher_console.py` — identity parity and visible-label contract.
- `CLAUDE.md` — document `control_13` as a candidate, not current firmware, until S0 passes.

### Task 1: Pin the immutable firmware and write red `control_13` contracts

**Files:**
- Create: `tests/test_blm_firmware_contract.py`
- Test: `control_12_full.ino`
- Expected missing file: `control_13_full.ino`

- [ ] **Step 1: Create the complete source-contract test module**

```python
"""Static contracts for the BLM firmware revision boundary.

These tests do not claim the Arduino sketch compiles or that hardware behaves.
They prevent a silent edit of deployed control_12 and pin the narrow source
changes required before control_13 may reach the compile/flash gate.
"""

import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROL_12 = ROOT / "control_12_full.ino"
CONTROL_13 = ROOT / "control_13_full.ino"
CONTROL_12_SHA256 = (
    "eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e"
)

ACTIVE_SERIAL_CLIENTS = (
    "garage_lab_combined/scripts/blm_bridge.py",
    "garage_lab_combined/scripts/blm_follow.py",
    "garage_lab_combined/scripts/launcher_runtime_from_udp.py",
    "garage_lab_combined/scripts/live_aim_test.py",
    "garage_lab_combined/scripts/manual_aim_test.py",
)
LEGACY_SERIAL_CLIENTS = (
    "garage_lab_combined/scripts/blm_interactive.py",
    "garage_lab_combined/scripts/version1.1.py",
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def firmware_commands(source: str) -> tuple[set[str], set[str]]:
    exact = set(re.findall(r'equalsIgnoreCase\("([^"]+)"\)', source))
    prefixes = set(re.findall(r'startsWith\("([^"]+)"\)', source))
    return exact, prefixes


def test_control_12_is_the_byte_identical_deployed_reference():
    digest = hashlib.sha256(CONTROL_12.read_bytes()).hexdigest()
    assert digest == CONTROL_12_SHA256


def test_control_13_is_explicitly_identifiable_and_protocol_compatible():
    old = text(CONTROL_12)
    new = text(CONTROL_13)
    assert 'const char* FIRMWARE_ID = "control_13";' in new
    assert 'INFO | FW: %s' in new
    assert 'SYS: FW control_13 READY' in new
    assert firmware_commands(new) == firmware_commands(old)
    for invariant in (
        "Serial.begin(921600);",
        "const float MIN_FEED_RPM       = 400.0;",
        "pinMode(LIMIT_FRONT_PIN, INPUT_PULLUP);",
        "pinMode(LIMIT_BACK_PIN, INPUT_PULLUP);",
        "pinMode(LIMIT_BALL_PIN, INPUT_PULLUP);",
    ):
        assert invariant in old and invariant in new


def test_control_13_idle_telemetry_is_not_ble_pwm_or_zero_gated():
    source = text(CONTROL_13)
    telemetry = source.split("// --- TELEMETRY ---", 1)[1]
    assert "currentState == STATE_IDLE" in telemetry
    assert "millis() - lastTelem > 250" in telemetry
    assert 'sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);' in telemetry
    assert "if (deviceConnected)" not in telemetry
    assert "currentPWM_Left >" not in telemetry
    assert "currentPWM_Right >" not in telemetry
    assert "desiredPWM_Left" not in telemetry
    assert "desiredPWM_Right" not in telemetry


def test_control_13_info_has_no_cooperative_loop_stall():
    source = text(CONTROL_13)
    assert "delay(50)" not in source
    assert source.count('cmd.equalsIgnoreCase("info")') == 1
    for field in ("INFO | FW:", "INFO | Ang:", "INFO | RPM:",
                  "INFO | FDR:", "INFO | LMT:", "INFO | CFG:"):
        assert field in source


def test_exactly_seven_python_files_open_serial_and_five_are_active():
    scripts_dir = ROOT / "garage_lab_combined/scripts"
    scripts = sorted(
        path.relative_to(ROOT).as_posix()
        for path in scripts_dir.glob("*.py")
        if "serial.Serial(" in text(path)
    )
    expected = sorted(ACTIVE_SERIAL_CLIENTS + LEGACY_SERIAL_CLIENTS)
    assert scripts == expected
    for relative in ACTIVE_SERIAL_CLIENTS:
        assert "921600" in text(ROOT / relative), relative
    assert "921600" in text(ROOT / "garage_lab_combined/scripts/blm_interactive.py")
    assert "BAUD_RATE = 115200" in text(
        ROOT / "garage_lab_combined/scripts/version1.1.py")
```

- [ ] **Step 2: Run the firmware contracts and verify the missing candidate fails**

```bash
venv/bin/python -m pytest tests/test_blm_firmware_contract.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: `test_control_12_is_the_byte_identical_deployed_reference` passes; tests which read `control_13_full.ino` fail with `FileNotFoundError`.

- [ ] **Step 3: Commit the red contract alone**

```bash
git add tests/test_blm_firmware_contract.py
git diff --cached --name-status
git diff --cached --check
git commit -m "test(blm): pin control 13 telemetry contract"
```

### Task 2: Create the minimal `control_13` candidate

**Files:**
- Create: `control_13_full.ino`
- Test: `tests/test_blm_firmware_contract.py`

- [ ] **Step 1: Make a mechanical no-clobber copy**

```bash
cp --no-clobber control_12_full.ino control_13_full.ino
```

Expected: one new file; `sha256sum control_12_full.ino` still prints the pinned digest.

- [ ] **Step 2: Add observable identity**

Using `apply_patch`, add beside the safety/configuration constants:

```cpp
const char* FIRMWARE_ID = "control_13";
```

Immediately after `Serial.begin(921600);`, add:

```cpp
Serial.println("SYS: FW control_13 READY");
```

At the start of the `info` response, declare a firmware buffer and emit identity:

```cpp
char buf0[40], buf1[60], buf2[60], buf3[60], buf4[60], buf5[60];

sprintf(buf0, "INFO | FW: %s", FIRMWARE_ID);
sendMsg(String(buf0));
```

Replace the old five-buffer declaration rather than declaring the same names twice.

- [ ] **Step 3: Remove the five `delay(50)` calls from `info`**

Delete only the five delays between `sendMsg` calls in the `info` branch. Preserve every field and its order after the new firmware identity line.

- [ ] **Step 4: Replace the telemetry block exactly**

```cpp
// --- TELEMETRY ---
static unsigned long lastTelem = 0;

// USB telemetry is evidence for both coast-down and a fresh zero. BLE notify
// remains conditional inside sendMsg(); USB Serial.println() is unconditional.
// Keep this out of pusher motion so the cooperative feeder loop stays primary.
if (millis() - lastTelem > 250 && currentState == STATE_IDLE) {
    lastTelem = millis();
    char buffer[50];
    sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);
    sendMsg(buffer);
}
```

There must be no `deviceConnected`, PWM, target-RPM, actual-RPM, or movement threshold around this block.

- [ ] **Step 5: Run source contracts**

```bash
venv/bin/python -m pytest tests/test_blm_firmware_contract.py -q \
  -p no:cacheprovider -o addopts=
sha256sum control_12_full.ino
```

Expected: all firmware contracts pass and the control12 digest remains
`eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e`.

- [ ] **Step 6: Run diff review focused on firmware invariants**

```bash
git diff --no-index -- control_12_full.ino control_13_full.ino
```

Expected differences only: identity constant/messages, one extra INFO line, removal of five 50 ms delays, and replacement of telemetry gates. No command, pin, state transition, RPM threshold, motor calibration, baud, or limit-polarity difference.
Because the files are intentionally different, `git diff --no-index` exits `1`;
that status means "differences found" here and is expected. Review the diff
contents rather than treating this one command as a failed verification.

- [ ] **Step 7: Commit candidate and green contract**

```bash
git add control_13_full.ino tests/test_blm_firmware_contract.py
git diff --cached --name-status
git diff --cached --check
git commit -m "feat(firmware): add control 13 USB telemetry"
```

### Task 3: Parse and display firmware identity

**Files:**
- Modify: `tests/test_blm_bridge.py`
- Modify: `garage_lab_combined/scripts/blm_bridge.py`
- Modify: `project-cam-desktop/src/blm.ts`
- Modify: `project-cam-desktop/src/views/LauncherView.tsx`
- Modify: `tests/test_desktop_launcher_console.py`

- [ ] **Step 1: Add failing bridge identity tests**

```python
@pytest.mark.parametrize(("line", "firmware_id"), [
    ("SYS: FW control_13 READY", "control_13"),
    ("INFO | FW: control_13", "control_13"),
])
def test_firmware_identity_is_parsed_from_boot_and_info(
        bridge, line, firmware_id):
    controller, _, _, _ = make(bridge, allow_fire=False)
    controller.note_serial_line(line)
    assert controller.state.firmware_id == firmware_id
    assert controller.status()["firmware_id"] == firmware_id


def test_unrecognised_text_cannot_claim_a_firmware_identity(bridge):
    controller, _, _, _ = make(bridge, allow_fire=False)
    for line in ("control_13", "INFO | FW: custom", "SYS: FW control_12 READY"):
        controller.note_serial_line(line)
    assert controller.state.firmware_id == ""
```

- [ ] **Step 2: Run and verify missing state fails**

Expected: FAIL because `ConsoleState` has no `firmware_id`.

- [ ] **Step 3: Implement the strict parser and published field**

```python
FIRMWARE_ID_LINE = re.compile(
    r"^(?:SYS: FW\s+|INFO \| FW:\s*)(control_13)(?:\s+READY)?$"
)


def parse_firmware_id(line: str) -> Optional[str]:
    match = FIRMWARE_ID_LINE.match(line)
    return None if match is None else match.group(1)
```

Add `firmware_id: str = ""` to `ConsoleState`. In `note_serial_line`, parse and store it before deduplication. Add `"firmware_id": state.firmware_id` to `status()`.

- [ ] **Step 4: Add failing desktop identity contract**

```python
def test_the_connected_firmware_identity_is_visible_not_inferred():
    blm = BLM_TS.read_text(encoding="utf-8")
    view = LAUNCHER_VIEW.read_text(encoding="utf-8")
    assert re.search(r"\bfirmware_id\s*:\s*string", blm)
    assert 'label="FIRMWARE"' in view
    assert "status?.firmware_id" in view
```

- [ ] **Step 5: Add the type and metric**

Add `firmware_id: string;` to `ConsoleStatus`. In the telemetry grid render:

```tsx
<Metric
  label="FIRMWARE"
  value={status?.firmware_id || "UNVERIFIED"}
/>
```

Do not treat an empty identity as a fire blocker in Slice 2: `control_12` compatibility is still required for the Slice 1 no-fire test. Identity is visible evidence and the operator's S0 gate.

- [ ] **Step 6: Run identity, type, and build checks**

```bash
venv/bin/python -m pytest \
  tests/test_blm_bridge.py tests/test_desktop_launcher_console.py \
  -q -p no:cacheprovider -o addopts=
cd project-cam-desktop
./node_modules/.bin/tsc --noEmit
npm run build
```

Expected: all exit 0.

- [ ] **Step 7: Commit exact identity paths**

```bash
git add garage_lab_combined/scripts/blm_bridge.py tests/test_blm_bridge.py \
  project-cam-desktop/src/blm.ts \
  project-cam-desktop/src/views/LauncherView.tsx \
  tests/test_desktop_launcher_console.py
git diff --cached --name-status
git diff --cached --check
git commit -m "feat(launcher): report connected firmware identity"
```

### Task 4: Record the consumer compatibility boundary

**Files:**
- Modify: `tests/test_blm_firmware_contract.py`
- Modify: `CLAUDE.md:40-58`

- [ ] **Step 1: Strengthen command compatibility tests**

Add the exact expected command grammar:

```python
def test_control_13_command_grammar_is_the_control_12_grammar():
    expected_exact = {
        "shoot", "reload", "setzero", "center", "stop", "info",
    }
    expected_prefixes = {
        "set ", "jsset", "jfspeedset", "jfaccelset",
        "jv", "jh", "js", "jf",
    }
    assert firmware_commands(text(CONTROL_12)) == (
        expected_exact, expected_prefixes)
    assert firmware_commands(text(CONTROL_13)) == (
        expected_exact, expected_prefixes)
```

This catches a command added or removed from either revision even if both were accidentally edited together; the control12 hash independently prevents that edit.

- [ ] **Step 2: Run firmware contracts**

```bash
venv/bin/python -m pytest tests/test_blm_firmware_contract.py -q \
  -p no:cacheprovider -o addopts=
```

Expected: PASS with seven serial clients, five active 921600-baud paths, `blm_interactive.py` as a 921600 legacy terminal, and `version1.1.py` explicitly retained as a 115200 control11-era utility.

- [ ] **Step 3: Document candidate status without claiming deployment**

Directly below `## BLM Firmware (control_12_full.ino — current)` in `CLAUDE.md`, add:

```markdown
### Candidate: control_13_full.ino (not deployed until S0)
- Command grammar, 921600 baud, pins, limits and state machine remain control12-compatible.
- Adds `INFO | FW: control_13` identity and unconditional 4 Hz USB actual-RPM telemetry while IDLE, including coast-down and zero.
- Removes the five blocking `delay(50)` calls from `info`.
- Do not call it current until it compiles, is flashed deliberately, and passes S0 identity/serial.
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_blm_firmware_contract.py CLAUDE.md
git diff --cached --name-status
git diff --cached --check
git commit -m "docs(firmware): define control 13 compatibility boundary"
```

### Task 5: Complete the software-only pre-flash gate

**Files:**
- Test: `control_12_full.ino`
- Test: `control_13_full.ino`
- Test: `tests/test_blm_firmware_contract.py`
- Test: host Slice 1 files

- [ ] **Step 1: Prove the local compile-tool limitation explicitly**

```bash
command -v arduino-cli
command -v pio
command -v platformio
```

Expected in the current environment: all three produce no path. Record this as `firmware_compile: blocked — toolchain absent`, not as a pass.

- [ ] **Step 2: Run all firmware and host tests**

```bash
cd /home/hanush/Desktop/ProjectCam
venv/bin/python -m ruff check \
  garage_lab_combined/scripts/blm_bridge.py \
  tests/test_blm_bridge.py tests/test_blm_firmware_contract.py \
  tests/test_desktop_launcher_console.py
venv/bin/python -m pytest \
  tests/test_blm_bridge.py tests/test_blm_firmware_contract.py \
  tests/test_desktop_launcher_console.py tests/test_rpm_speed_fit.py \
  -q -p no:cacheprovider -o addopts=
venv/bin/pytest tests/ -p no:cacheprovider
```

Expected: all tests pass; report the actual counts.

- [ ] **Step 3: Verify frontend/Rust and rebuild**

```bash
cd /home/hanush/Desktop/ProjectCam/project-cam-desktop
./node_modules/.bin/tsc --noEmit
npm run build
cd src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test -q
cd /home/hanush/Desktop/ProjectCam
./project-cam-desktop/rebuild.sh
./project-cam-desktop/check-binary-fresh.sh
```

Expected: every command exits 0.

- [ ] **Step 4: Verify immutable artifacts and dirty-tree boundaries**

```bash
sha256sum control_12_full.ino
wc -l garage_lab_combined/cal/blm/rpm_speed_shots.jsonl
git diff --check
git status --short
```

Expected: control12 hash is pinned; JSONL still contains exactly four legacy v1 lines; `rpm_speed_model.json` is absent unless it pre-existed before this plan; no serial device was opened.

- [ ] **Step 5: Produce the pre-flash handoff**

Report separately:

```text
source contracts: PASS
host tests/build: PASS with actual counts
control_12 immutable hash: PASS
control_13 compile: BLOCKED — Arduino CLI/PlatformIO absent
flash: NOT ATTEMPTED
hardware S0-S2: NOT ATTEMPTED
```

Stop here. Do not convert the compile block into an installation or GUI action without explicit operator approval.

### Task 6: Operator-controlled compile, flash, and S0–S2

**Files:**
- Candidate: `control_13_full.ino`
- Hardware: ESP32/CP2102 launcher controller

- [ ] **Step 1: Establish the physical precondition before opening any port**

Operator levels the barrel, clears the travel envelope, removes the ball, confirms nobody is downrange, and closes every console/process holding the CP2102 port.

- [ ] **Step 2: Compile without flashing**

Open `control_13_full.ino` in the same Arduino IDE installation and with the exact ESP32 board configuration previously used to deploy control12. Press **Verify** only. Save the complete compiler output and board-selection screenshot.

Expected: compile succeeds. If board identity/settings cannot be recovered or compile fails, stop; do not guess an FQBN and do not upload.

- [ ] **Step 3: Obtain explicit upload confirmation, then flash once**

Only after the operator approves the compiled artifact, select the stable CP2102 by-id device and upload `control_13`. Do not have the desktop console open at the same time.

- [ ] **Step 4: Run S0 with fire control disabled**

Re-level before opening the console because DTR resets the ESP32 and adopts the physical pose as logical zero. Open the rebuilt console without fire control. Require:

```text
FIRMWARE = control_13
fresh L/R readings continue near zero without POLL
POLL shows INFO | FW, Ang, RPM, FDR, LMT, CFG
Ball HIGH/LOW appears as advisory BALL/EMPTY
```

Wait more than two seconds and confirm zero telemetry remains fresh. Any identity mismatch, stale stream, unexpected movement, or parsing error fails S0.

- [ ] **Step 5: Run S1 no-fire/manual safety**

Verify STOP latches, CLEAR releases only the ordinary latch, limit displays match physical switches, and only previously approved manual movements occur inside measured travel. Do not simulate a front-limit shot ACK and do not tune the 5 s ACK deadline.

- [ ] **Step 6: Run S2 aim-only**

With flywheel command zero and no ball, repeat visual `+5°/0°/-5°` pitch and `±5°` yaw checks, physical travel declaration, SET ZERO rules, and STOP. Any uncommanded or invisible-to-software stall fails S2.

- [ ] **Step 7: Run separately announced spin-only telemetry validation**

Only after S0–S2 pass, command the lowest approved test RPM without ARM or ball. Require at least three separate samples spanning at least two seconds. Command zero and observe the continuous stream through nonzero coast-down until both readings remain below 50 RPM and the bridge says `WHEELS CONFIRMED STOPPED`.

- [ ] **Step 8: Stop before any physical shot**

Record S0–S2 and spin-only evidence. Do not ARM or fire. The first front-limit ACK/timeout hardware test requires a separate empty-backstop protocol and explicit operator approval.
