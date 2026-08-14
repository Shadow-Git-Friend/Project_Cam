"""Static contracts for the BLM firmware revision boundary.

These tests do not claim the Arduino sketch compiles or that hardware behaves.
They prevent a silent edit of deployed control_12 and pin the narrow source
changes required before control_13 may reach the compile/flash gate.
"""

import ast
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


def opens_serial(path: Path) -> bool:
    """Whether Python syntax in this file constructs a Serial link."""
    tree = ast.parse(text(path))
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Serial"
        for node in ast.walk(tree)
    )


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


def test_control_13_command_grammar_is_the_control_12_grammar():
    """Pin the public command set independently of the equality comparison.

    If both sketches accidentally gain or lose the same command they still match
    each other; this explicit vocabulary makes that drift fail as well.
    """
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
        # Reporting the BLE link is not decoration. The library compiles at
        # CORE_DEBUG_LEVEL=0, so every failure path inside notify() — no client,
        # CCCD zero, GATT error — is SILENT. Without these three values on the
        # USB channel, a subscribed phone receiving nothing is indistinguishable
        # from a phone that never connected, which is what cost a whole S0 pass.
        "INFO | BLE:",
    ):
        assert field in source


def test_control_13_reports_notify_outcomes_without_changing_tx_pacing():
    """Diagnose the failed 4 Hz notification before changing transport timing.

    A single nine-byte ``L:0 R:0`` packet every 250 ms also failed to arrive, so
    burst pacing cannot explain the observed fault. The diagnostic firmware must
    expose the BLE library's own status callback while leaving ``sendMsg`` on the
    established immediate-notify path. Otherwise the diagnostic flash changes
    two variables at once and can hide the original cause.
    """
    source = text(CONTROL_13)
    assert "class MyTxCallbacks" in source
    assert "void onStatus(" in source
    assert "SUCCESS_NOTIFY" in source
    assert "ERROR_NOTIFY_DISABLED" in source
    assert "ERROR_GATT" in source
    assert 'pTxCharacteristic->setCallbacks(new MyTxCallbacks())' in source
    assert "notify=%s" in source
    assert "volatile bool deviceConnected" in source
    assert "BLE_TX_QUEUE" not in source
    assert "BLE_TX_MIN_GAP_MS" not in source
    assert "bleTxDropped" not in source
    assert "pTxCharacteristic->notify();" in source


def test_control_13_does_not_restart_advertising_inside_on_connect():
    """Keep the BLE connection lifecycle identical to Espressif's UART example.

    On the bench the phone remained connected while the firmware reported
    ``deviceConnected=1`` but Bluedroid reported zero clients and rejected every
    notification as ``ERROR_NO_CLIENT``.  The inherited control_12 callback
    restarted advertising *inside* ``onConnect``; the reference lifecycle starts
    advertising once at setup and restarts it only after a disconnect.  Pin that
    single-variable experiment so the problematic call cannot creep back in.
    """
    source = text(CONTROL_13)
    on_connect = source.split("void onConnect", 1)[1].split("void onDisconnect", 1)[0]
    assert "startAdvertising" not in on_connect
    assert 'pServer->getAdvertising()->start();' in source
    disconnected = source.split("if (!deviceConnected && oldDeviceConnected)", 1)[1]
    assert "pServer->startAdvertising();" in disconnected


def test_exactly_seven_python_files_open_serial_and_five_are_active():
    scripts_dir = ROOT / "garage_lab_combined/scripts"
    scripts = sorted(
        path.relative_to(ROOT).as_posix()
        for path in scripts_dir.glob("*.py")
        if opens_serial(path)
    )
    expected = sorted(ACTIVE_SERIAL_CLIENTS + LEGACY_SERIAL_CLIENTS)
    assert scripts == expected
    for relative in ACTIVE_SERIAL_CLIENTS:
        assert "921600" in text(ROOT / relative), relative
    assert "921600" in text(ROOT / "garage_lab_combined/scripts/blm_interactive.py")
    assert "BAUD_RATE = 115200" in text(
        ROOT / "garage_lab_combined/scripts/version1.1.py"
    )
