"""Default-pins for the 2026-07-17 "liquid skeleton" display fixes.

Every one of those fixes ships as an argparse DEFAULT, not as a code path with
its own behavioural test — so an adversarial review found that all three could
be reverted to their pre-fix values with the entire suite still green. These
tests make the defaults themselves the contract: flipping any of them back is
a failing test, not a silent regression on the next live session.

argparse lives inline in main(), which cannot be invoked without starting the
capture pipeline, so the defaults are asserted against the source literal.
That is deliberately a text check — its only job is to fail loudly if someone
edits the default without also updating this file.
"""

import re
from pathlib import Path

import pytest

LIVE = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")
DRILL = Path("Parallel_working/run_training_drill.sh")


@pytest.fixture(scope="module")
def source():
    return LIVE.read_text()


def arg_default(source, flag):
    """The literal `default=` of one add_argument call, as text."""
    m = re.search(
        r'add_argument\(\s*"' + re.escape(flag) + r'".*?default=([^,)\s]+)',
        source, re.S)
    assert m, f"{flag} not found in {LIVE}"
    return m.group(1)


# --- fix 1: rigid-core latency compensation (per-joint leads made bones breathe)
def test_latency_comp_is_rigid_by_default(source):
    assert arg_default(source, "--pose-latency-comp-joint-frac") == "0.0"


def test_joint_frac_help_does_not_promise_legacy_equivalence(source):
    """1.0 leads from the EMA'd joints_state, not the KF position, and gated
    joints keep the rigid lead — it under-states the old breathing ~2x, so the
    help must not sell it as a faithful rollback."""
    m = re.search(r'add_argument\(\s*"--pose-latency-comp-joint-frac".*?\)\n',
                  source, re.S)
    # NB: this is the raw source of the call, so the help string is still split
    # across concatenated literals — match a fragment inside ONE literal.
    help_text = m.group(0)
    assert "byte-exact restoration" in help_text
    assert "legacy per-joint prediction (A/B only)." not in help_text


# --- fix 2: One-Euro beta was mis-scaled ~1000x (mm vs m)
def test_oneeuro_beta_is_mm_scaled(source):
    """beta 0.3 assumes metres; in mm/s it opened the filter (alpha > 0.95)
    above ~100-140 mm/s, i.e. above the noise floor -> no display smoothing."""
    assert arg_default(source, "--oneeuro-beta") == "0.015"


# --- fix 3: bone-length consistency clamp
def test_bone_consistency_on_by_default(source):
    assert arg_default(source, "--pose-bone-consistency") == "True"
    assert arg_default(source, "--pose-bone-tol") == "0.13"


# --- the velocity gate is a garbage filter, not a motion filter
def test_display_lead_velocity_gate_above_athletic_speed(source):
    """2000 mm/s sat at brisk-walking speed, so the rigid lead collapsed to
    zero for every running drill. Keep it far above real athletic motion; the
    max_lead_mm cap is what bounds a large-but-real lead."""
    m = re.search(r"max_uncertainty_mm=150\.0,\s*max_vel_mm_s=([0-9_.]+)", source)
    assert m, "compute_display_leads signature not found"
    assert float(m.group(1)) >= 10_000.0


# --- the A/B knobs the operator is told to use must actually exist
@pytest.mark.parametrize("flag", [
    "--pose-latency-comp-joint-frac",
    "--pose-bone-consistency",
    "--oneeuro-beta",
])
def test_documented_ab_knobs_exist(source, flag):
    assert f'"{flag}"' in source


def test_drill_launcher_ab_comment_matches_reality():
    text = DRILL.read_text()
    assert "--pose-latency-comp-joint-frac 1.0" in text
    assert "NOT a byte-exact restoration" in text
