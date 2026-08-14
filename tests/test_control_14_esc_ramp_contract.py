"""Static contracts for the control_14 ESC-ramp pacing change.

control_14 exists for one reason: the control_13 idle loop measured 40.0 ms
(2026-08-13, 19 intervals, stdev 0.108 ms), so the 25 ms ramp gate was satisfied
on every iteration and a cooperative AccelStepper was capped at 25 steps/s.
These tests do not claim the sketch compiles or that hardware behaves; they pin
that the fix changed the ramp's PACING and nothing else, and that control_12 and
control_13 were not edited while it was written.

Lives in its own file so it can be reviewed and reverted independently of the
control_12/control_13 boundary contracts.
"""

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL_12 = ROOT / "control_12_full.ino"
CONTROL_13 = ROOT / "control_13_full.ino"
CONTROL_14 = ROOT / "control_14_full.ino"

CONTROL_12_SHA256 = (
    "eefb35acce89f5f1467dab26865b90394e4f880127718c2697cd4924c51b660e"
)
# Pinned once control_13 was deployed and measured. control_14 is derived from
# exactly this text.
CONTROL_13_SHA256 = (
    "54367d26e9dee54283beba08f0d41297ddacaae2538b296349f0b00eb946049f"
)

PACING_BLOCK = re.compile(
    r"\n// --- ESC RAMP PACING \(control_14\) ---\n"
    r"(?:.*\n)*?"
    r"const int RAMP_STEP_US = \d+;\n"
)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def firmware_commands(source: str) -> tuple[set[str], set[str]]:
    exact = set(re.findall(r'equalsIgnoreCase\("([^"]+)"\)', source))
    prefixes = set(re.findall(r'startsWith\("([^"]+)"\)', source))
    return exact, prefixes


def ramp_block(source: str) -> str:
    """The whole ESC ramping section, up to the stepper execution section."""
    start = source.index("  // --- ESC RAMPING ---")
    end = source.index("  // --- STEPPER EXECUTION ---")
    return source[start:end]


def project_to_control_13(source: str) -> str:
    """Undo every control_14 change, so what remains must be control_13."""
    source, removed = PACING_BLOCK.subn("", source, count=1)
    assert removed == 1, "the control_14 pacing constants block is missing"
    source = source.replace(ramp_block(source), ramp_block(text(CONTROL_13)), 1)
    return source.replace("control_14", "control_13")


def test_the_deployed_firmware_files_were_not_edited():
    assert hashlib.sha256(CONTROL_12.read_bytes()).hexdigest() == CONTROL_12_SHA256
    assert hashlib.sha256(CONTROL_13.read_bytes()).hexdigest() == CONTROL_13_SHA256


def test_control_14_changes_only_the_ramp_pacing_and_its_own_identity():
    """The strongest guard: everything else is control_13 byte-for-byte.

    Motion, feeder, limit, BLE, serial and command behaviour cannot have drifted
    if reverting the three intended edits reproduces the deployed file exactly.
    """
    assert project_to_control_13(text(CONTROL_14)) == text(CONTROL_13)


def test_control_14_never_claims_to_be_control_13():
    source = text(CONTROL_14)
    assert 'const char* FIRMWARE_ID = "control_14";' in source
    assert 'SYS: FW control_14 READY' in source
    # Comments are free to explain what control_13 did -- that is why the fix is
    # legible. What must not survive is an identity the board could emit.
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', source)
    assert literals, "no string literals found - the extraction is wrong"
    assert not [lit for lit in literals if "control_13" in lit], (
        "changed behaviour must not report an older identity"
    )


def test_control_14_keeps_the_control_13_command_grammar():
    assert firmware_commands(text(CONTROL_14)) == firmware_commands(text(CONTROL_13))
    exact, prefixes = firmware_commands(text(CONTROL_14))
    assert exact == {"shoot", "reload", "setzero", "center", "stop", "info"}
    assert prefixes == {
        "set ", "jsset", "jfspeedset", "jfaccelset", "jv", "jh", "js", "jf",
    }


def test_control_14_holds_the_ramp_rate_control_13_actually_produced():
    """25 us/s, not the 40 us/s control_13 nominally asked for.

    control_13's `> 25` gate never ran at 25 ms: the loop was 40.0 ms, so one
    1 us step happened per 40 ms. Restoring the nominal rate would spin the
    wheels up faster than the operator has ever seen, which is a separate
    decision from removing the stall, so the measured rate is what is preserved.
    """
    source = text(CONTROL_14)
    interval = int(re.search(r"RAMP_INTERVAL_MS = (\d+);", source).group(1))
    step = int(re.search(r"RAMP_STEP_US = (\d+);", source).group(1))

    measured_control_13_us_per_s = 1 / 0.040
    assert step / (interval / 1000) == measured_control_13_us_per_s

    # The stall is two blocking duty updates of one 50 Hz PWM period each.
    # It must stay a minority of the interval or the steppers starve again.
    assert 2 * 20 < interval / 2


def test_control_14_writes_a_duty_only_when_it_changed():
    """The idle cost of the fix is zero writes, hence zero blocking."""
    block = ramp_block(text(CONTROL_14))
    for side, delta in (("Left", "deltaLeft"), ("Right", "deltaRight")):
        assert f"int {delta} = desiredPWM_{side} - currentPWM_{side};" in block
        guard = block.index(f"if ({delta} != 0) {{")
        write = block.index(f"esc{side}.writeMicroseconds(currentPWM_{side});")
        assert guard < write, f"esc{side} write is not guarded by a real change"


def test_control_14_keeps_both_esc_writes_once_each_in_the_original_order():
    block = ramp_block(text(CONTROL_14))
    assert block.count("escLeft.writeMicroseconds(currentPWM_Left);") == 1
    assert block.count("escRight.writeMicroseconds(currentPWM_Right);") == 1
    assert block.index("escLeft.write") < block.index("escRight.write")
    # No third writer, and no write outside the ramp and the setup rest value.
    source = text(CONTROL_14)
    assert source.count("escLeft.writeMicroseconds") == 2
    assert source.count("escRight.writeMicroseconds") == 2
    assert source.count("escLeft.writeMicroseconds(1000);") == 1
    assert source.count("escRight.writeMicroseconds(1000);") == 1


def test_control_14_cannot_overshoot_the_commanded_duty():
    """A 5 us step must never step past a delta smaller than 5 us."""
    block = ramp_block(text(CONTROL_14))
    for side, delta in (("Left", "deltaLeft"), ("Right", "deltaRight")):
        assert (
            f"currentPWM_{side} += constrain({delta}, -RAMP_STEP_US, RAMP_STEP_US);"
            in block
        )


def test_control_14_still_runs_all_three_steppers_after_the_ramp():
    source = text(CONTROL_14)
    ramp = source.index("  // --- ESC RAMPING ---")
    for call in ("vertStepper.run();", "horzStepper.run();", "pusherStepper.run();"):
        assert source.count(call) == 1
        assert source.index(call) > ramp


def test_control_14_preserves_the_safety_invariants():
    source = text(CONTROL_14)
    for invariant in (
        "Serial.begin(921600);",
        "const float MIN_FEED_RPM       = 400.0;",
        "const int   MIN_RPM_THRESHOLD  = 200;",
        "pinMode(LIMIT_FRONT_PIN, INPUT_PULLUP);",
        "pinMode(LIMIT_BACK_PIN, INPUT_PULLUP);",
        "pinMode(LIMIT_BALL_PIN, INPUT_PULLUP);",
        "constrain(vDeg, -30.0, 30.0)",
    ):
        assert invariant in source
