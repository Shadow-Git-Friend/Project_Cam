"""Ground-truth tests for project_cam.metrics (Academy KPI package).

Every test builds a synthetic signal with a known analytic answer, so these
gate correctness, not plausibility.
"""

from datetime import datetime, timezone

import numpy as np
import pytest

from project_cam.metrics import (
    acwr,
    asymmetry_index,
    compute_xt,
    convex_hull_area,
    kick_foot_speed,
    pass_network,
    physical_load,
    ppda,
    render_session_report,
    stride_metrics,
    team_shape,
    voronoi_control,
    xt_of_action,
)

FPS = 30.0


def straight_run(speed_mps: float, duration_s: float, fps: float = FPS):
    t = np.arange(0.0, duration_s, 1.0 / fps)
    pos = np.stack([speed_mps * t, np.zeros_like(t)], axis=1)
    return pos, t


# ---------------------------------------------------------------- physical

def test_constant_walk_distance_exact():
    pos, t = straight_run(1.5, 60.0)  # 1.5 m/s for 60 s -> ~90 m
    out = physical_load(pos, t, position_sigma_m=0.0, smooth_window=1)
    assert out.total_distance_m == pytest.approx(1.5 * (t[-1] - t[0]), rel=1e-6)
    assert out.sprint_count == 0
    assert out.hsr_distance_m == 0.0
    assert out.max_speed_kmh == pytest.approx(5.4, rel=1e-6)


def test_sprint_detected_with_correct_zone_distance():
    # 10 s walk at 2 m/s, 3 s sprint at 8 m/s (28.8 km/h), 10 s walk.
    fps = FPS
    t = np.arange(0.0, 23.0, 1.0 / fps)
    speed = np.where((t >= 10.0) & (t < 13.0), 8.0, 2.0)
    x = np.concatenate(([0.0], np.cumsum(speed[:-1] * np.diff(t))))
    pos = np.stack([x, np.zeros_like(x)], axis=1)
    out = physical_load(pos, t, position_sigma_m=0.0, smooth_window=1)
    assert out.sprint_count == 1
    assert out.sprints[0].duration_s == pytest.approx(3.0, abs=0.2)
    assert out.sprint_distance_m == pytest.approx(24.0, rel=0.05)
    assert out.hsr_distance_m == pytest.approx(24.0, rel=0.05)  # 28.8 > 19.8 too
    assert out.max_speed_kmh == pytest.approx(28.8, rel=0.02)
    assert out.mean_sprint_length_m == pytest.approx(24.0, rel=0.05)


def test_acceleration_events_counted():
    # 0 -> 6 m/s at 3 m/s^2 (2 s), hold, 6 -> 0 at -3 m/s^2.
    fps = FPS
    t = np.arange(0.0, 10.0, 1.0 / fps)
    speed = np.clip(3.0 * t, 0.0, 6.0) - np.clip(3.0 * (t - 8.0), 0.0, 6.0)
    x = np.concatenate(([0.0], np.cumsum(speed[:-1] * np.diff(t))))
    pos = np.stack([x, np.zeros_like(x)], axis=1)
    out = physical_load(pos, t, position_sigma_m=0.0, smooth_window=1)
    assert len(out.accelerations) == 1
    assert len(out.decelerations) == 1
    assert out.max_accel_mps2 == pytest.approx(3.0, abs=0.3)
    assert out.max_decel_mps2 == pytest.approx(-3.0, abs=0.3)


def test_uncertainty_scales_with_position_sigma():
    pos, t = straight_run(2.0, 30.0)
    lo = physical_load(pos, t, position_sigma_m=0.05, smooth_window=1)
    hi = physical_load(pos, t, position_sigma_m=0.50, smooth_window=1)
    assert hi.total_distance_sigma_m == pytest.approx(10 * lo.total_distance_sigma_m, rel=1e-6)
    assert hi.speed_sigma_kmh > lo.speed_sigma_kmh


def test_metabolic_power_steady_state_matches_running_cost():
    # At zero acceleration the Osgnach cost is 3.6 J/kg/m -> P = 3.6 * v.
    pos, t = straight_run(4.0, 30.0)
    out = physical_load(pos, t, position_sigma_m=0.0, smooth_window=1)
    assert out.metabolic_power_mean_wkg == pytest.approx(3.6 * 4.0, rel=0.02)


def test_low_fps_flagged_lower_confidence():
    pos, t = straight_run(2.0, 30.0, fps=8.0)
    out = physical_load(pos, t, position_sigma_m=0.0, smooth_window=1)
    assert out.confidence == "low"


def test_too_short_trajectory_is_low_confidence_zeros():
    out = physical_load(np.zeros((2, 2)), np.array([0.0, 0.1]))
    assert out.confidence == "low"
    assert out.total_distance_m == 0.0


def test_non_monotonic_timestamps_rejected():
    with pytest.raises(ValueError):
        physical_load(np.zeros((4, 2)), np.array([0.0, 0.1, 0.1, 0.2]))


# ---------------------------------------------------------------- ACWR

def test_acwr_steady_load_is_sweet_spot():
    out = acwr([300.0] * 28)
    assert out.ratio == pytest.approx(1.0)
    assert out.band == "sweet_spot"
    assert out.confidence == "high"


def test_acwr_spike_is_danger():
    out = acwr([200.0] * 21 + [600.0] * 7)
    assert out.ratio > 1.5
    assert out.band == "danger"


def test_acwr_short_history_low_confidence():
    out = acwr([300.0] * 10)
    assert out.confidence == "low"


def test_acwr_zero_history_no_ratio():
    out = acwr([0.0] * 28)
    assert out.ratio is None
    assert out.band == "no_data"


# ---------------------------------------------------------------- biomech

def test_asymmetry_index_symmetric_zero():
    assert asymmetry_index(2.0, 2.0) == pytest.approx(0.0)
    assert asymmetry_index(2.2, 1.8) == pytest.approx(20.0)
    assert asymmetry_index(0.0, 0.0) is None


def test_stride_metrics_on_synthetic_gait():
    # One foot strikes every 0.8 s, advancing 1.6 m per stride; ankle height
    # follows a |sin| arc (zero at each strike).
    fps = 60.0
    t = np.arange(0.0, 8.0, 1.0 / fps)
    stride_t, stride_len = 0.8, 1.6
    x = stride_len * (t // stride_t) + np.where(
        (t % stride_t) > 0.4, stride_len * ((t % stride_t) - 0.4) / 0.4, 0.0
    )
    z = 0.15 * np.abs(np.sin(np.pi * t / stride_t))
    pos = np.stack([x, np.zeros_like(x), z], axis=1)
    out = stride_metrics(pos, t)
    assert out.stride_count >= 8
    assert out.stride_length_m == pytest.approx(stride_len, rel=0.1)
    assert out.cadence_hz == pytest.approx(1.0 / stride_t, rel=0.1)
    assert out.ground_contact_time_s is not None


def test_kick_foot_speed_peak():
    # Foot accelerates to 15 m/s at t ~ 1.0 s along +X.
    fps = 120.0
    t = np.arange(0.0, 2.0, 1.0 / fps)
    speed = 15.0 * np.exp(-((t - 1.0) ** 2) / (2 * 0.05**2))
    x = np.concatenate(([0.0], np.cumsum(speed[:-1] * np.diff(t))))
    pos = np.stack([x, np.zeros_like(x), np.zeros_like(x)], axis=1)
    out = kick_foot_speed(pos, t)
    assert out["peak_speed_mps"] == pytest.approx(15.0, rel=0.05)
    assert out["peak_time_s"] == pytest.approx(1.0, abs=0.05)
    assert abs(out["approach_angle_deg"]) < 1.0


# ---------------------------------------------------------------- tactical

def test_voronoi_control_symmetric_split():
    a = np.array([[30.0, 34.0]])
    b = np.array([[75.0, 34.0]])
    out = voronoi_control(a, b, grid_step=1.0)
    assert out["team_a"] == pytest.approx(0.5, abs=0.02)
    assert out["team_a"] + out["team_b"] == pytest.approx(1.0)


def test_voronoi_control_outnumbered_side():
    a = np.array([[20.0, 20.0], [20.0, 48.0], [50.0, 34.0]])
    b = np.array([[90.0, 34.0]])
    out = voronoi_control(a, b)
    assert out["team_a"] > 0.6


def test_convex_hull_area_unit_square():
    square = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]])
    assert convex_hull_area(square) == pytest.approx(1.0)
    assert convex_hull_area(np.array([[0, 0], [1, 1]])) == 0.0


def test_team_shape_descriptors():
    pts = np.array([[10.0, 10.0], [10.0, 58.0], [40.0, 10.0], [40.0, 58.0]])
    out = team_shape(pts)
    assert out["hull_area_m2"] == pytest.approx(30.0 * 48.0)
    assert out["depth_m"] == pytest.approx(30.0)
    assert out["width_m"] == pytest.approx(48.0)
    assert out["line_height_m"] == pytest.approx(10.0)


def test_ppda():
    assert ppda(120, 20) == pytest.approx(6.0)
    assert ppda(120, 0) is None


def test_xt_value_iteration_monotone_towards_goal():
    # 1-D 3-cell toy pitch: only the last cell has shot danger; moves push
    # right with p=1. xT must increase towards the goal cell.
    shoot = np.array([0.0, 0.0, 1.0])
    goal = np.array([0.0, 0.0, 0.3])
    tr = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 0.0]])
    xt = compute_xt(shoot, goal, tr)
    assert xt[2] == pytest.approx(0.3)
    assert xt[1] == pytest.approx(0.3)  # certain move into the shooting cell
    assert xt[0] == pytest.approx(0.3)
    assert xt_of_action(xt, 0, 2) == pytest.approx(0.0, abs=1e-9)
    # With lossy moves the gradient appears.
    tr_lossy = tr * 0.5
    xt2 = compute_xt(shoot, goal, tr_lossy)
    assert xt2[0] < xt2[1] < xt2[2]
    assert xt_of_action(xt2, 0, 2) > 0.0


def test_pass_network_centrality():
    passes = [("A", "B"), ("B", "C"), ("A", "B"), ("C", "A")]
    out = pass_network(passes)
    assert out["players"] == ["A", "B", "C"]
    assert out["edge_count"] == 4
    # B involved in 3 passes, normalised by (n-1)=2.
    assert out["degree_centrality"]["B"] == pytest.approx(1.5)


# ---------------------------------------------------------------- report

def test_report_renders_all_langs_with_uncertainty():
    pos, t = straight_run(2.0, 30.0)
    phys = physical_load(pos, t).to_dict()
    load = acwr([300.0] * 28).to_dict()
    when = datetime(2026, 7, 2, 6, 0, tzinfo=timezone.utc)
    for lang in ("en", "ru", "kk"):
        text = render_session_report("07", phys, load, session_start_utc=when, lang=lang)
        assert "±" in text
        assert "Asia/Almaty" in text
        assert "2026-07-02 11:00" in text  # UTC+5


def test_report_refuses_metrics_without_confidence():
    pos, t = straight_run(2.0, 30.0)
    phys = physical_load(pos, t).to_dict()
    phys.pop("confidence")
    with pytest.raises(ValueError, match="confidence"):
        render_session_report("07", phys)
