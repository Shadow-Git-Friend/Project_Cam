"""Contracts for the uncommissioned control_15 closed-loop RPM candidate.

The deployed control_12/13/14 sketches are immutable evidence.  control_15 may
change only its identity, the parsed updateMotorPWM() body, and an explicit set
of controller blocks.  These are source contracts; the deterministic plant
simulation and the pinned Arduino compile are separate gates.
"""

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
    "set ",
    "jsset",
    "jfspeedset",
    "jfaccelset",
    "jv",
    "jh",
    "js",
    "jf",
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

MARKER = re.compile(
    r"^[ \t]*// --- CONTROL_15 (?P<name>[A-Z_]+) "
    r"(?P<edge>BEGIN|END) ---[ \t]*$",
    re.MULTILINE,
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def control_15_source() -> str:
    assert CONTROL_15.exists(), "control_15_full.ino is intentionally absent in RED"
    return text(CONTROL_15)


def firmware_commands(source: str) -> tuple[set[str], set[str]]:
    exact = set(re.findall(r'equalsIgnoreCase\("([^"]+)"\)', source))
    prefixes = set(re.findall(r'startsWith\("([^"]+)"\)', source))
    return exact, prefixes


def function_body_span(source: str, name: str) -> tuple[int, int]:
    matches = list(
        re.finditer(rf"\bvoid\s+{re.escape(name)}\s*\(\s*\)\s*\{{", source)
    )
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
            continue
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
        remove_controller_blocks(
            candidate.replace(
                "CONTROL_15 RPM_CONTROLLER_STATE BEGIN",
                "CONTROL_15 UNKNOWN_BLOCK BEGIN",
                1,
            )
        )
    with pytest.raises(AssertionError):
        remove_controller_blocks(
            candidate.replace(
                "// --- CONTROL_15 RPM_CONTROLLER_STATE END ---\n", "", 1
            )
        )


def test_each_wheel_has_independent_state_error_base_trim_and_output():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    body = update_body(source)
    for token in (
        "WheelControllerState leftController",
        "WheelControllerState rightController",
        "errorRPM",
        "basePWM",
        "integralUs",
        "trimUs",
        "desiredPWM_Left",
        "desiredPWM_Right",
        "currentPWM_Left",
        "currentPWM_Right",
    ):
        assert token in state + body
    assert "currentRPM_Left" in body
    assert "currentRPM_Right" in body


def test_integrator_freezes_until_ramp_catches_but_p_stays_live():
    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    assert "fabs(desiredPWM - currentPWM) <= RAMP_STEP_US" in state
    assert "proportionalUs = kp * state.errorRPM" in state
    caught = state.index("fabs(desiredPWM - currentPWM) <= RAMP_STEP_US")
    integrate = state.index("state.integralUs = candidateIntegral", caught)
    assert caught < integrate


def test_target_reset_policy_is_strictly_greater_than_five_percent():
    state = block(control_15_source(), "RPM_CONTROLLER_STATE")
    assert "oldTarget == 0.0" in state
    assert "newTarget == 0.0" in state
    assert "fabs(newTarget - oldTarget) > 0.05 * oldTarget" in state
    assert "fabs(newTarget - oldTarget) >= 0.05 * oldTarget" not in state
    assert "if (reset)" in state
    assert "state.integralUs = 0.0" in state


def test_trim_pwm_startup_stall_and_overspeed_bounds_are_pinned():
    source = control_15_source()
    state = block(source, "RPM_CONTROLLER_STATE")
    body = update_body(source)
    for token in (
        "MAX_TRIM_US = 30.0",
        "PWM_MIN_US = 1000",
        "PWM_MAX_US = 1800",
        "OVERSPEED_RPM = 1300.0",
        "NO_START_TIMEOUT_MS = 15000",
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
    assert (
        'sprintf(buffer, "L:%.0f R:%.0f", currentRPM_Left, currentRPM_Right);'
        in source
    )
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
