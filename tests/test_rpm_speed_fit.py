"""The v(RPM) fit, whose output is a SAFETY input.

`src/project_cam/closed_loop/firing_line.py` samples the commanded arc using an
exit speed to decide whether a person is in the corridor. That speed comes from
this model file, so the tests below are about the properties a clearance decision
depends on: the model never extrapolates past what was measured, and it always
carries the sample count and residual that make its uncertainty visible.

Measurement procedure: docs/protocols/2026-08-03-rpm-speed-measurement.md
"""

import importlib.util
import math
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIT = ROOT / "scripts" / "fit_rpm_speed.py"
G = 9.80665


@pytest.fixture(scope="module")
def fitter():
    spec = importlib.util.spec_from_file_location("fit_rpm_speed", FIT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shots(pairs, module, height_m=0.52):
    """(rpm, landing_distance_m) pairs -> the (rpm, v) points the fitter takes."""
    return [(rpm, module.speed_from_drop(distance, height_m, G))
            for rpm, distance in pairs]


def test_horizontal_drop_speed_matches_the_closed_form(fitter):
    # v = d * sqrt(g / 2H): a 4 m carry from 0.5 m up is a shade under 12.5 m/s.
    v = fitter.speed_from_drop(4.0, 0.5, G)
    assert v == pytest.approx(4.0 * math.sqrt(G / 1.0), rel=1e-9)
    # Halving the launch height lengthens the fall, so the same carry means a
    # faster ball — get this backwards and every speed is wrong by sqrt(2).
    assert fitter.speed_from_drop(4.0, 0.25, G) > v


def test_every_model_branch_carries_its_sample_count_and_residual(fitter):
    """A speed without n_shots and a residual cannot inform a clearance margin."""
    cases = {
        "constant": shots([(800, 3.94), (800, 3.88), (800, 3.99)], fitter),
        "linear": shots([(500, 2.40), (500, 2.46), (800, 3.94), (800, 3.88)],
                        fitter),
        "interp": shots([(500, 2.40), (650, 3.10), (800, 3.94)], fitter),
    }
    kinds = {"constant": "linear", "linear": "linear", "interp": "interp"}
    for name, points in cases.items():
        model = fitter.fit(points, G, 0.52, kinds[name])
        assert "n_shots" in model, name
        assert model["n_shots"] == len(points), name
        assert "fit_rmse_mps" in model, name
        assert math.isfinite(model["fit_rmse_mps"]), name


def test_a_single_rpm_becomes_a_constant_model_not_a_singular_fit(fitter):
    points = shots([(800, 3.94), (800, 3.88), (800, 3.99), (800, 3.91),
                    (800, 3.96)], fitter)
    model = fitter.fit(points, G, 0.52, "linear")
    assert model["model"] == "constant_mps"
    assert model["n_shots"] == 5
    # The residual is the shot-to-shot spread, and it must be non-zero: five
    # different landing distances cannot produce a perfectly certain speed.
    assert model["fit_rmse_mps"] > 0.0
    assert model["rpm_min"] == model["rpm_max"] == 800.0


def test_an_interpolating_model_does_not_claim_zero_uncertainty(fitter):
    """Passing exactly through the points is not the same as being certain."""
    repeated = shots([(500, 2.40), (500, 2.52), (800, 3.94), (800, 3.80)],
                     fitter)
    model = fitter.fit(repeated, G, 0.52, "interp")
    assert model["model"] == "interp_rpm_to_mps"
    assert model["fit_rmse_mps"] > 0.0, "within-RPM spread must be reported"

    # One shot per RPM has no measured repeatability, and reporting 0.0 there is
    # a statement about the sample size, not about precision — which is why
    # n_shots travels with it.
    single = shots([(500, 2.40), (650, 3.10), (800, 3.94)], fitter)
    lonely = fitter.fit(single, G, 0.52, "interp")
    assert lonely["fit_rmse_mps"] == 0.0
    assert lonely["n_shots"] == 3


def test_the_model_records_the_range_it_was_measured_over(fitter):
    """The consumer clamps to this range; a wrong range is an extrapolated shot."""
    points = shots([(500, 2.40), (800, 3.94)], fitter)
    model = fitter.fit(points, G, 0.52, "linear")
    assert model["rpm_min"] == 500.0
    assert model["rpm_max"] == 800.0
    assert model["launch_height_m"] == 0.52


def test_faster_wheels_must_fit_to_a_faster_ball(fitter):
    """A negative slope would aim high for a hard shot — check the sign."""
    points = shots([(500, 2.40), (650, 3.10), (800, 3.94)], fitter)
    model = fitter.fit(points, G, 0.52, "linear")
    assert model["model"] == "linear_rpm_to_mps"
    assert model["a"] > 0.0
