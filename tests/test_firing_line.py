"""Fail-closed tests for the all-person launcher clearance interlock."""

from __future__ import annotations

import json

import numpy as np
import pytest

import project_cam.closed_loop.firing_line as firing_line_module
from project_cam.closed_loop.firing_line import (
    FIRING_LINE_SCHEMA,
    evaluate_firing_line,
    evaluate_shot_clearance,
    sample_ballistic_path_mm,
    segment_distance_3d,
)

NOW = 1_800_000_000.0


def _joint(x, y, z=1000.0, *, conf=0.9, cams=3, last_seen=100):
    return {
        "x_mm": float(x),
        "y_mm": float(y),
        "z_mm": float(z),
        "conf": float(conf),
        "cams": int(cams),
        "last_seen_frame": int(last_seen),
    }


def _person(track_id, *, primary=False, joints=None):
    return {
        "track_id": int(track_id),
        "primary": bool(primary),
        "track_last_seen_frame": 100,
        "joints": joints or {},
    }


def _snapshot(*people, **overrides):
    data = {
        "schema": FIRING_LINE_SCHEMA,
        "snapshot_ts": NOW,
        "frame": 100,
        "geometry_id": "world_mm",
        "y_mirrored": False,
        "mode": "multi_person",
        "primary_track_id": 1,
        "primary_epoch": 4,
        "observed_person_count": len(people),
        "ambiguous_detections": False,
        "unassigned_candidate_count": 0,
        "people": list(people),
    }
    data.update(overrides)
    return data


def _clear_people():
    primary = _person(1, primary=True, joints={"nose": _joint(4000, 0, 1400)})
    bystander = _person(
        2,
        joints={
            "left_shoulder": _joint(1000, 2200, 1400),
            "right_shoulder": _joint(1200, 2200, 1400),
            "left_hip": _joint(1050, 2200, 900),
            "right_hip": _joint(1150, 2200, 900),
        },
    )
    return primary, bystander


def _straight_path():
    return np.array([[0.0, 0.0, 1000.0], [4000.0, 0.0, 1000.0]])


def _evaluate(snapshot, path=None, **kwargs):
    kwargs.setdefault("expected_primary_track_id", 1)
    kwargs.setdefault("expected_primary_epoch", 4)
    kwargs.setdefault("expected_y_mirrored", False)
    return evaluate_firing_line(
        snapshot,
        _straight_path() if path is None else path,
        **kwargs,
    )


def test_ballistic_path_uses_launcher_yaw_and_relative_horizontal_angle():
    path = sample_ballistic_path_mm(
        launcher_xyz_mm=[100.0, 200.0, 500.0],
        launcher_yaw_deg=90.0,
        pitch_deg=0.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        horizontal_distance_mm=1000.0,
        extension_mm=0.0,
        samples=3,
    )

    assert path.shape == (3, 3)
    np.testing.assert_allclose(path[0], [100.0, 200.0, 500.0], atol=1e-6)
    np.testing.assert_allclose(path[-1, :2], [100.0, 1200.0], atol=1e-6)
    assert path[-1, 2] < 500.0  # gravity applies even at zero pitch


@pytest.mark.parametrize(
    "kwargs",
    [
        {"speed_mps": 0.0},
        {"horizontal_distance_mm": 0.0},
        {"samples": 1},
        {"launcher_xyz_mm": [0.0, float("nan"), 0.0]},
    ],
)
def test_ballistic_path_rejects_invalid_inputs(kwargs):
    base = dict(
        launcher_xyz_mm=[0.0, 0.0, 0.0],
        launcher_yaw_deg=0.0,
        pitch_deg=5.0,
        yaw_deg=0.0,
        speed_mps=10.0,
        horizontal_distance_mm=1000.0,
        samples=8,
    )
    base.update(kwargs)
    with pytest.raises(ValueError):
        sample_ballistic_path_mm(**base)


def test_ballistic_path_extension_and_non_default_gravity_are_applied():
    normal = sample_ballistic_path_mm(
        launcher_xyz_mm=[0, 0, 1000],
        launcher_yaw_deg=0,
        pitch_deg=0,
        yaw_deg=0,
        speed_mps=10,
        horizontal_distance_mm=1000,
        extension_mm=500,
        samples=4,
        gravity_m_s2=9.81,
    )
    low_gravity = sample_ballistic_path_mm(
        launcher_xyz_mm=[0, 0, 1000],
        launcher_yaw_deg=0,
        pitch_deg=0,
        yaw_deg=0,
        speed_mps=10,
        horizontal_distance_mm=1000,
        extension_mm=500,
        samples=4,
        gravity_m_s2=1.0,
    )

    assert normal[-1, 0] == pytest.approx(1500.0)
    assert low_gravity[-1, 2] > normal[-1, 2]


def test_segment_distance_handles_crossing_and_parallel_segments():
    assert segment_distance_3d([0, 0, 0], [2, 0, 0], [1, -1, 0], [1, 1, 0]) == pytest.approx(0.0)
    assert segment_distance_3d([0, 0, 0], [2, 0, 0], [0, 3, 0], [2, 3, 0]) == pytest.approx(3.0)


def test_segment_distance_handles_degenerate_and_skew_segments():
    assert segment_distance_3d([0, 0, 0], [0, 0, 0], [1, 0, 0], [3, 0, 0]) == pytest.approx(1.0)
    assert segment_distance_3d([0, 0, 0], [1, 0, 0], [0.5, 1, 1], [0.5, 2, 1]) == pytest.approx(2**0.5)


def test_clear_bystander_allows_shot_and_reports_distance():
    result = _evaluate(
        _snapshot(*_clear_people()),
        _straight_path(),
        now=NOW + 0.05,
        corridor_radius_mm=500.0,
    )

    assert result.ok is True
    assert result.reason is None
    assert result.detail["closest_track_id"] == 2
    assert result.detail["closest_distance_mm"] > 500.0


def test_crossing_body_segment_blocks_shot():
    primary, _ = _clear_people()
    crossing = _person(
        2,
        joints={
            "left_shoulder": _joint(1800, -400, 1000),
            "right_shoulder": _joint(1800, 400, 1000),
            "left_hip": _joint(1800, -250, 700),
            "right_hip": _joint(1800, 250, 700),
        },
    )
    result = _evaluate(
        _snapshot(primary, crossing),
        _straight_path(),
        now=NOW,
        corridor_radius_mm=500.0,
    )

    assert result.ok is False
    assert result.reason == "firing_line_blocked"
    assert result.detail["closest_track_id"] == 2
    assert result.detail["closest_distance_mm"] == pytest.approx(0.0)


def test_near_isolated_usable_joints_are_also_checked():
    primary, _ = _clear_people()
    disconnected = _person(
        2,
        joints={
            "nose": _joint(2000, 100, 1000),
            "left_wrist": _joint(2400, 2000, 1300),
            "right_ankle": _joint(2500, 2200, 100),
        },
    )
    result = _evaluate(
        _snapshot(primary, disconnected),
        _straight_path(),
        now=NOW,
        corridor_radius_mm=300.0,
    )

    assert result.ok is False
    assert result.reason == "firing_line_blocked"
    assert result.detail["closest_joint"] == "nose"


@pytest.mark.parametrize(
    ("snapshot", "reason"),
    [
        (None, "clearance_missing"),
        (_snapshot(*_clear_people(), schema="wrong"), "schema_mismatch"),
        (_snapshot(*_clear_people(), geometry_id="camera_px"), "geometry_mismatch"),
        (_snapshot(*_clear_people(), mode="single_person"), "multi_person_required"),
        (_snapshot(*_clear_people(), snapshot_ts=NOW - 5), "clearance_stale"),
        (_snapshot(*_clear_people(), ambiguous_detections=True), "ambiguous_detections"),
        (_snapshot(*_clear_people(), unassigned_candidate_count=1), "ambiguous_detections"),
    ],
)
def test_snapshot_level_fail_closed_reasons(snapshot, reason):
    result = _evaluate(snapshot, now=NOW, max_staleness_s=0.5)

    assert result.ok is False
    assert result.reason == reason


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"expected_primary_track_id": 9}, "primary_changed"),
        ({"expected_primary_epoch": 5}, "primary_changed"),
    ],
)
def test_primary_identity_or_epoch_change_blocks(kwargs, reason):
    result = _evaluate(_snapshot(*_clear_people()), now=NOW, **kwargs)
    assert result.ok is False
    assert result.reason == reason


@pytest.mark.parametrize(
    "people",
    [
        (_person(2, primary=False, joints={}),),
        (_person(1, primary=True), _person(1, primary=False)),
        (_person(1, primary=False), _person(2, primary=False)),
        (_person(1, primary=True), _person(2, primary=True)),
    ],
)
def test_missing_or_ambiguous_primary_geometry_blocks(people):
    snapshot = _snapshot(*people, observed_person_count=len(people))
    result = _evaluate(snapshot, now=NOW)

    assert result.ok is False
    assert result.reason in {"primary_invalid", "duplicate_track_id"}


def test_unlocalized_or_incomplete_secondary_blocks():
    primary, _ = _clear_people()
    secondary = _person(2, joints={"nose": _joint(2000, 3000, 1200)})
    result = _evaluate(
        _snapshot(primary, secondary), now=NOW, min_person_joints=3
    )

    assert result.ok is False
    assert result.reason == "person_unlocalized"
    assert result.detail["track_id"] == 2


@pytest.mark.parametrize(
    "bad_joint",
    [
        _joint(float("nan"), 0, 0),
        {"x_mm": 1, "y_mm": 2, "z_mm": 3, "conf": "bad", "cams": 3, "last_seen_frame": 100},
    ],
)
def test_invalid_secondary_numeric_data_blocks_as_malformed(bad_joint):
    primary, _ = _clear_people()
    secondary = _person(
        2,
        joints={
            "nose": bad_joint,
            "left_shoulder": _joint(2000, 2000),
            "right_shoulder": _joint(2200, 2000),
        },
    )
    result = _evaluate(_snapshot(primary, secondary), now=NOW)

    assert result.ok is False
    assert result.reason == "malformed_snapshot"


def test_stale_low_confidence_or_single_camera_joints_do_not_localize_person():
    primary, _ = _clear_people()
    secondary = _person(
        2,
        joints={
            "nose": _joint(2000, 2000, conf=0.1),
            "left_shoulder": _joint(2000, 2000, cams=1),
            "right_shoulder": _joint(2200, 2000, last_seen=80),
        },
    )
    result = _evaluate(
        _snapshot(primary, secondary),
        now=NOW,
        min_person_joints=1,
        max_joint_age_frames=6,
    )

    assert result.ok is False
    assert result.reason == "person_unlocalized"


def test_observed_person_count_must_match_people_array():
    result = _evaluate(
        _snapshot(*_clear_people(), observed_person_count=3), now=NOW
    )
    assert result.ok is False
    assert result.reason == "person_count_mismatch"


def test_evaluate_shot_clearance_builds_ballistic_path_and_fails_closed_on_bad_aim():
    primary, bystander = _clear_people()
    snapshot = _snapshot(primary, bystander)
    result = evaluate_shot_clearance(
        snapshot,
        launcher_xyz_mm=[0, 0, 1000],
        launcher_yaw_deg=0,
        pitch_deg=0,
        yaw_deg=0,
        speed_mps=0,
        target_xyz_mm=[4000, 0, 1000],
        now=NOW,
    )

    assert result.ok is False
    assert result.reason == "invalid_trajectory"


@pytest.mark.parametrize(
    "missing",
    ["expected_primary_track_id", "expected_primary_epoch", "expected_y_mirrored"],
)
def test_aim_context_is_required(missing):
    kwargs = {
        "expected_primary_track_id": 1,
        "expected_primary_epoch": 4,
        "expected_y_mirrored": False,
    }
    kwargs[missing] = None
    result = evaluate_firing_line(
        _snapshot(*_clear_people()), _straight_path(), now=NOW, **kwargs
    )
    assert result.ok is False
    assert result.reason == "aim_context_missing"


def test_decision_detail_is_immutable():
    result = _evaluate(_snapshot(*_clear_people()), now=NOW)
    with pytest.raises(TypeError):
        result.detail["closest_track_id"] = 99


def test_decision_has_json_safe_copy_and_nested_detail_is_immutable():
    snapshot = _snapshot(*_clear_people(), schema={"bad": []})
    result = _evaluate(snapshot, now=NOW)

    with pytest.raises((AttributeError, TypeError)):
        result.detail["actual"]["bad"].append("mutated")
    encoded = json.dumps(result.to_dict())
    assert "schema_mismatch" in encoded


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"unassigned_candidate_count": -1}, "malformed_snapshot"),
        ({"frame": -1}, "malformed_snapshot"),
        ({"primary_epoch": -1}, "malformed_snapshot"),
    ],
)
def test_snapshot_integer_ranges_are_validated(overrides, reason):
    result = _evaluate(_snapshot(*_clear_people(), **overrides), now=NOW)
    assert result.ok is False
    assert result.reason == reason


@pytest.mark.parametrize("conf", [-0.1, 1.1])
def test_joint_confidence_outside_probability_range_is_malformed(conf):
    primary, secondary = _clear_people()
    secondary["joints"]["nose"] = _joint(2000, 2000, conf=conf)
    result = _evaluate(_snapshot(primary, secondary), now=NOW)
    assert result.ok is False
    assert result.reason == "malformed_snapshot"


def test_missing_or_stale_track_freshness_blocks():
    primary, secondary = _clear_people()
    secondary.pop("track_last_seen_frame")
    missing = _evaluate(_snapshot(primary, secondary), now=NOW)
    assert missing.reason == "malformed_snapshot"

    secondary["track_last_seen_frame"] = 80
    stale = _evaluate(_snapshot(primary, secondary), now=NOW, max_track_age_frames=6)
    assert stale.reason == "track_stale"


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("left_eye", "right_eye"),
        ("left_ear", "left_shoulder"),
        ("right_ear", "right_shoulder"),
    ],
)
def test_all_coco_head_and_neck_edges_block_when_the_bone_crosses(first, second):
    primary, _ = _clear_people()
    joints = {
        first: _joint(2000, -700, 1000),
        second: _joint(2000, 700, 1000),
        "left_ankle": _joint(3000, 2000, 0),
    }
    secondary = _person(2, joints=joints)
    result = _evaluate(
        _snapshot(primary, secondary),
        now=NOW,
        corridor_radius_mm=600,
        min_person_joints=3,
    )
    assert result.reason == "firing_line_blocked"


def test_evaluate_shot_clearance_accepts_non_default_gravity():
    result = evaluate_shot_clearance(
        _snapshot(*_clear_people()),
        launcher_xyz_mm=[0, 0, 1000],
        launcher_yaw_deg=0,
        pitch_deg=0,
        yaw_deg=0,
        speed_mps=10,
        target_xyz_mm=[4000, 0, 1000],
        gravity_m_s2=1.0,
        extension_mm=0,
        expected_primary_track_id=1,
        expected_primary_epoch=4,
        expected_y_mirrored=False,
        now=NOW,
        corridor_radius_mm=500,
    )
    assert result.ok is True


def test_unknown_joint_names_cannot_satisfy_localization():
    primary, _ = _clear_people()
    secondary = _person(
        2,
        joints={
            "foo": _joint(2000, 2000),
            "bar": _joint(2100, 2000),
            "baz": _joint(2200, 2000),
        },
    )
    result = _evaluate(_snapshot(primary, secondary), now=NOW)
    assert result.ok is False
    assert result.reason == "malformed_snapshot"


def test_boolean_joint_scalars_are_rejected_instead_of_coerced():
    primary, secondary = _clear_people()
    secondary["joints"]["nose"] = {
        "x_mm": True,
        "y_mm": 2000.0,
        "z_mm": 1000.0,
        "conf": True,
        "cams": 3,
        "last_seen_frame": 100,
    }
    result = _evaluate(_snapshot(primary, secondary), now=NOW)
    assert result.reason == "malformed_snapshot"


def test_mirror_context_mismatch_blocks():
    result = _evaluate(
        _snapshot(*_clear_people(), y_mirrored=True),
        now=NOW,
        expected_y_mirrored=False,
    )
    assert result.reason == "geometry_mismatch"


def test_adaptive_ballistic_sampling_cannot_miss_mid_arc_person():
    primary = _person(1, primary=True, joints={"nose": _joint(10_000, 0, 0)})
    # True 45-degree, 10 m/s parabola height at x=5 m from z=0.
    arc_z_mm = (5.0 - 0.5 * 9.81 * (5.0 / (10.0 / 2**0.5)) ** 2) * 1000.0
    crossing = _person(
        2,
        joints={
            "nose": _joint(5000, 0, arc_z_mm),
            "left_eye": _joint(5000, 20, arc_z_mm),
            "right_eye": _joint(5000, -20, arc_z_mm),
        },
    )
    result = evaluate_shot_clearance(
        _snapshot(primary, crossing),
        launcher_xyz_mm=[0, 0, 0],
        launcher_yaw_deg=0,
        pitch_deg=45,
        yaw_deg=0,
        speed_mps=10,
        target_xyz_mm=[10_000, 0, 0],
        extension_mm=0,
        trajectory_samples=2,
        expected_primary_track_id=1,
        expected_primary_epoch=4,
        expected_y_mirrored=False,
        now=NOW,
        corridor_radius_mm=100,
    )
    assert result.reason == "firing_line_blocked"


def test_snapshot_freshness_is_rechecked_before_allow(monkeypatch):
    ticks = iter([NOW, NOW + 1.0])
    monkeypatch.setattr(firing_line_module.time, "time", lambda: next(ticks))
    result = _evaluate(
        _snapshot(*_clear_people()),
        max_staleness_s=0.5,
    )
    assert result.reason == "clearance_stale"


def test_people_and_trajectory_capacity_are_bounded():
    primary, bystander = _clear_people()
    people = [primary]
    for track_id in range(2, 11):
        person = {
            **bystander,
            "track_id": track_id,
            "joints": dict(bystander["joints"]),
        }
        people.append(person)
    too_many_people = _evaluate(
        _snapshot(*people, observed_person_count=len(people)), now=NOW
    )
    assert too_many_people.reason == "capacity_exceeded"

    long_path = np.repeat(_straight_path()[:1], 300, axis=0)
    long_path[:, 0] = np.arange(300)
    too_many_points = _evaluate(_snapshot(primary), path=long_path, now=NOW)
    assert too_many_points.reason == "capacity_exceeded"


def test_ballistic_chord_error_inflates_corridor_conservatively():
    primary = _person(1, primary=True, joints={"nose": _joint(10_000, 0, 0)})
    x_m = 4.5
    elapsed = x_m / (10.0 / 2**0.5)
    true_z_mm = (x_m - 0.5 * 9.81 * elapsed**2) * 1000.0
    # 590 mm above the continuous curve is inside a 600 mm swept corridor,
    # even though the approximating chord lies another ~25 mm below it.
    person_z = true_z_mm + 590.0
    crossing = _person(
        2,
        joints={
            "nose": _joint(4500, 0, person_z),
            "left_eye": _joint(4500, 10, person_z),
            "right_eye": _joint(4500, -10, person_z),
        },
    )
    result = evaluate_shot_clearance(
        _snapshot(primary, crossing),
        launcher_xyz_mm=[0, 0, 0],
        launcher_yaw_deg=0,
        pitch_deg=45,
        yaw_deg=0,
        speed_mps=10,
        target_xyz_mm=[10_000, 0, 0],
        extension_mm=0,
        trajectory_samples=2,
        expected_primary_track_id=1,
        expected_primary_epoch=4,
        expected_y_mirrored=False,
        now=NOW,
        corridor_radius_mm=600,
    )
    assert result.reason == "firing_line_blocked"
    assert result.detail["effective_corridor_radius_mm"] == pytest.approx(625.0)


@pytest.mark.parametrize(
    "context",
    [
        {"expected_primary_track_id": True},
        {"expected_primary_epoch": 4.0},
        {"expected_y_mirrored": "False"},
    ],
)
def test_aim_context_types_are_strict(context):
    kwargs = {
        "expected_primary_track_id": 1,
        "expected_primary_epoch": 4,
        "expected_y_mirrored": False,
    }
    kwargs.update(context)
    result = evaluate_firing_line(
        _snapshot(*_clear_people()), _straight_path(), now=NOW, **kwargs
    )
    assert result.ok is False
    assert result.reason == "aim_context_invalid"


def test_huge_json_integers_block_instead_of_raising_overflow():
    huge = 10**10_000
    timestamp = _evaluate(
        _snapshot(*_clear_people(), snapshot_ts=huge), now=NOW
    )
    assert timestamp.reason == "malformed_snapshot"

    primary, secondary = _clear_people()
    secondary["joints"]["left_shoulder"]["x_mm"] = huge
    coordinate = _evaluate(_snapshot(primary, secondary), now=NOW)
    assert coordinate.reason == "malformed_snapshot"


def test_extreme_finite_ballistic_inputs_block_instead_of_overflowing():
    result = evaluate_shot_clearance(
        _snapshot(*_clear_people()),
        launcher_xyz_mm=[0, 0, 0],
        launcher_yaw_deg=0,
        pitch_deg=0,
        yaw_deg=0,
        speed_mps=2e-6,
        target_xyz_mm=[1000, 0, 0],
        extension_mm=1e308,
        expected_primary_track_id=1,
        expected_primary_epoch=4,
        expected_y_mirrored=False,
        now=NOW,
    )
    assert result.reason == "invalid_trajectory"
