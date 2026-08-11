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
    assert (
        'sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);'
        in telemetry
    )
    assert "if (deviceConnected)" not in telemetry
    assert "currentPWM_Left >" not in telemetry
    assert "currentPWM_Right >" not in telemetry
    assert "desiredPWM_Left" not in telemetry
    assert "desiredPWM_Right" not in telemetry


def test_control_13_info_has_no_cooperative_loop_stall():
    source = text(CONTROL_13)
    assert "delay(50)" not in source
    assert source.count('cmd.equalsIgnoreCase("info")') == 1
    for field in (
        "INFO | FW:",
        "INFO | Ang:",
        "INFO | RPM:",
        "INFO | FDR:",
        "INFO | LMT:",
        "INFO | CFG:",
    ):
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
        ROOT / "garage_lab_combined/scripts/version1.1.py"
    )
