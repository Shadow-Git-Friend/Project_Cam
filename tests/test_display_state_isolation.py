import re
from pathlib import Path

import numpy as np

from project_cam.viz.skeleton_stabilize import (
    BoneLengthBank,
    stabilize_display_skeleton,
)


LIVE = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")


def _section(source, start, end):
    assert start in source, f"missing start marker: {start}"
    assert end in source, f"missing end marker: {end}"
    return source.split(start, 1)[1].split(end, 1)[0]


def _pose():
    joints = np.full((17, 3), np.nan, dtype=np.float32)
    joints[5] = (-180.0, 0.0, 1450.0)
    joints[6] = (180.0, 0.0, 1450.0)
    joints[7] = (-210.0, 0.0, 1160.0)
    joints[8] = (210.0, 0.0, 1160.0)
    joints[9] = (-230.0, 0.0, 890.0)
    joints[10] = (230.0, 0.0, 890.0)
    joints[11] = (-95.0, 0.0, 950.0)
    joints[12] = (95.0, 0.0, 950.0)
    joints[13] = (-100.0, 0.0, 530.0)
    joints[14] = (100.0, 0.0, 530.0)
    joints[15] = (-105.0, 0.0, 90.0)
    joints[16] = (105.0, 0.0, 90.0)
    return joints


def test_display_transform_cannot_mutate_state_through_aliasing():
    state = _pose()
    state_before = state.copy()
    bank = BoneLengthBank(min_samples=1)
    bank.observe(state)

    filtered = state.copy()
    filtered += np.float32([120.0, -40.0, 10.0])
    filtered[15] = filtered[13] + 1.8 * (filtered[15] - filtered[13])
    display = filtered.copy()
    stabilize_display_skeleton(display, bank, tol=0.12, soft=0.45)

    assert not np.shares_memory(state, filtered)
    assert not np.shares_memory(state, display)
    np.testing.assert_array_equal(state, state_before)
    assert not np.array_equal(display, filtered)


def test_measurement_and_safety_consumers_are_wired_to_state():
    source = LIVE.read_text(encoding="utf-8")
    frame_inputs = re.findall(
        r"joints_array_to_frame\(\s*(joints_[a-z_]+)", source
    )
    assert frame_inputs
    assert set(frame_inputs) == {"joints_state"}

    udp = _section(source, 'timer.start("udp")', 'timer.stop("udp")')
    assert "joints_display" not in udp
    assert "joints_filtered" not in udp
    assert "pt = joints_state[idx]" in udp
    assert '"joints": joints_state' in udp

    blm = _section(
        source,
        "# --- BLM Demo: compute aim from current joints ---",
        "# update cinematic motion trails",
    )
    assert "j_pos = joints_state[j_idx]" in blm
    assert "joints_display[j_idx]" not in blm
    assert "joints=joints_display.copy()" in source
