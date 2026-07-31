from pathlib import Path


LIVE = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")


def _section(source, start, end):
    assert start in source
    assert end in source
    return source.split(start, 1)[1].split(end, 1)[0]


def test_primary_handoff_resets_every_per_athlete_display_history():
    source = LIVE.read_text(encoding="utf-8")
    handoff = _section(
        source,
        "if next_primary_tid != mp_primary_tid:",
        "primary_selection = mp_assignments.get(mp_primary_tid, {})",
    )

    required = (
        "joints_filtered.fill(np.nan)",
        "joints_display.fill(np.nan)",
        'joints_filtered[:] = target_state["display"]',
        'joints_display[:] = target_state["display"]',
        "oneeuro_filters = [",
        "latency_rigid_lead = np.zeros(3, dtype=np.float64)",
        "bone_bank.reset()",
        "joint_kfs = [",
        "joint_kf_last_update_t = [None] * 17",
        "prev_speed_pos.fill(np.nan)",
    )
    for contract in required:
        assert contract in handoff


def test_secondary_tracks_cannot_share_the_primary_bone_bank():
    source = LIVE.read_text(encoding="utf-8")
    secondary_factory = _section(
        source,
        "def make_secondary_pose_state():",
        "def update_secondary_pose_state(",
    )
    secondary_update = _section(
        source,
        "def update_secondary_pose_state(",
        "def triangulate_person_assignment(",
    )
    primary_clamp = _section(
        source,
        "# Final render buffer: filtered joints + display-only bone-length",
        "if (",
    )

    assert '"joints"' in secondary_factory
    assert '"display"' in secondary_factory
    assert "bone_bank" not in secondary_factory
    assert "bone_bank" not in secondary_update
    assert "stabilize_display_skeleton(" in primary_clamp
    assert "joints_display, bone_bank" in primary_clamp

    learning = _section(
        source,
        "# Bone-length learning (display-only rigidity",
        "if mp_tracker is not None:",
    )
    assert "if j in lr_split_replaced:" in learning
    assert "np.linalg.norm(pt - prev)) > 50.0" in learning
    assert "bone_bank.observe(_bone_obs, conf=joints_conf_state" in learning
    assert "cams=joints_cam_state" in learning
