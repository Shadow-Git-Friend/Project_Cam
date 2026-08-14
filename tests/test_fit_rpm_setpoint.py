"""Tests for the RPM setpoint refit.

The tool exists because commanding 300 RPM delivered a plateau near 370 on
2026-08-13, which puts a 500 command outside `blm_bridge`'s +/-10% arm band and
blocks B1 entirely. Its most important behaviour is what it REFUSES: refitting
against the firmware's own RPM would make command, report and model agree while
all three were wrong, if the encoder PPR is off.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "control_14_full.ino"


def load():
    spec = importlib.util.spec_from_file_location(
        "fit_rpm_setpoint", ROOT / "scripts" / "fit_rpm_setpoint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fit_mod():
    return load()


@pytest.fixture(scope="module")
def constants(fit_mod):
    return fit_mod.read_firmware_constants(FIRMWARE)


def ladder(scale_left=1.0, scale_right=1.0, true_at=None, commanded=(250, 300, 350, 400, 450)):
    """A ladder where the machine delivers `true_at(cmd)` and the encoder
    reports `true * scale`."""
    true_at = true_at or (lambda c: c * 1.233)
    rows = []
    for c in commanded:
        t = true_at(c)
        rows.append({"commanded_rpm": c,
                     "reported_left": t * scale_left,
                     "reported_right": t * scale_right,
                     "true_left": t, "true_right": t})
    return rows


def test_constants_come_from_the_sketch_not_a_copy(fit_mod, constants):
    """A duplicated constant is a constant that will drift."""
    assert constants["left"] == (0.1763, 1101.0)
    assert constants["right"] == (0.1670, 1088.0)
    assert constants["min_rpm_threshold"] == 200.0
    source = FIRMWARE.read_text()
    assert "LEFT_SLOPE  = 0.1763" in source
    assert "MIN_RPM_THRESHOLD  = 200" in source


def test_commanded_pwm_reproduces_the_firmware(fit_mod, constants):
    slope, offset = constants["left"]
    threshold = constants["min_rpm_threshold"]
    # Below the threshold the firmware forces idle whatever the command says.
    assert fit_mod.commanded_pwm(199, slope, offset, threshold) == 1000
    assert fit_mod.commanded_pwm(0, slope, offset, threshold) == 1000
    # The 300 command whose plateau started all this: 300*0.1763 + 1101.
    assert fit_mod.commanded_pwm(300, slope, offset, threshold) == 1153
    # Truncation, not rounding -- `(int)` in C++.
    assert fit_mod.commanded_pwm(250, slope, offset, threshold) == 1145
    # And the firmware's own upper clamp.
    assert fit_mod.commanded_pwm(9000, slope, offset, threshold) == 1800


def test_it_refuses_without_a_tachometer(fit_mod, constants):
    rows = ladder()
    for row in rows:
        row["true_left"] = row["true_right"] = None
    result = fit_mod.fit(rows, constants)
    for side in ("left", "right"):
        assert "cannot validate itself" in result["sides"][side]["refused"]
        assert "new_slope" not in result["sides"][side]


def test_it_refuses_when_the_encoder_scale_is_off(fit_mod, constants):
    """The whole point. A 2x PPR error must stop the refit, not be absorbed."""
    result = fit_mod.fit(ladder(scale_left=2.0), constants)
    left = result["sides"]["left"]
    assert not left["encoder_scale"]["within_tolerance"]
    assert "PPR_LEFT" in left["refused"]
    assert "new_slope" not in left
    # The good wheel is still fitted: one bad encoder does not void the other.
    assert "new_slope" in result["sides"]["right"]


def test_a_small_scale_error_is_tolerated(fit_mod, constants):
    """Tachometer noise is not a PPR bug. 2% must pass, 8% must not."""
    assert "new_slope" in fit_mod.fit(ladder(scale_left=1.02), constants)["sides"]["left"]
    assert "refused" in fit_mod.fit(ladder(scale_left=1.08), constants)["sides"]["left"]


def test_the_refit_makes_the_command_mean_what_it_says(fit_mod, constants):
    """End to end: feed it the measured 23% overshoot, apply the new constants,
    and a 500 command must land inside the +/-10% arm band it used to miss."""
    result = fit_mod.fit(ladder(), constants)
    left = result["sides"]["left"]
    assert left["r_squared"] > 0.99

    new_pwm = fit_mod.commanded_pwm(500, left["new_slope"], left["new_offset"],
                                    constants["min_rpm_threshold"])
    old_slope, old_offset = constants["left"]
    # Invert the machine's behaviour: it delivered true = cmd*1.233 at the OLD
    # pwm, i.e. true = (pwm - old_offset)/old_slope / 1.233 * ... -- simpler to
    # state as: the delivered RPM for a given PWM is linear, so recover it.
    delivered = (new_pwm - old_offset) / old_slope * 1.233
    assert abs(delivered - 500) <= 50, f"500 commanded still delivers {delivered:.0f}"


def test_steps_below_the_firmware_threshold_are_dropped(fit_mod, constants):
    """PWM is 1000 for any command under 200, so such a step constrains nothing."""
    rows = ladder(commanded=(100, 150, 300, 350, 400))
    result = fit_mod.fit(rows, constants)
    assert result["sides"]["left"]["n_points"] == 3


def test_too_few_steps_is_refused(fit_mod, constants):
    with pytest.raises(fit_mod.LadderError, match="at least 3"):
        fit_mod.fit(ladder(commanded=(300, 400)), constants)


def test_a_non_linear_machine_is_flagged_not_silently_fitted(fit_mod, constants):
    result = fit_mod.fit(
        ladder(true_at=lambda c: 200 + (c / 100.0) ** 3.5 * 30), constants)
    left = result["sides"]["left"]
    assert left["r_squared"] < 0.98
    assert "not linear" in left["warning"]


def test_the_cli_runs_end_to_end(fit_mod, constants, tmp_path, capsys):
    path = tmp_path / "ladder.json"
    path.write_text(json.dumps(ladder()))
    out = tmp_path / "out.json"
    assert fit_mod.main([str(path), "--firmware", str(FIRMWARE),
                         "--json-out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "LEFT_SLOPE" in printed and "control_15" in printed
    assert json.loads(out.read_text())["n_steps"] == 5
