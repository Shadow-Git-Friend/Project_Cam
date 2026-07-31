"""Tests for display-only pose latency compensation in the live viewer."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def load_live_module():
    path = Path("Parallel_working/scripts/live_4cam_arena_view_parallel.py")
    spec = importlib.util.spec_from_file_location("live_4cam_arena_view_parallel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tracking_kf(live, velocity_mm_s=(500.0, 0.0, 0.0), dt=1.0 / 15.0, steps=30):
    """KF fed a constant-velocity target long enough to converge."""
    kf = live.JointKalmanFilter(process_noise=500.0, measurement_noise=10.0, dt=dt)
    vel = np.asarray(velocity_mm_s)
    pos = np.array([1000.0, 2000.0, 900.0])
    for i in range(steps):
        if i > 0:
            kf.predict_step()
        kf.update_step(pos + vel * dt * i)
    return kf, pos + vel * dt * (steps - 1), vel


def test_compensation_leads_along_velocity():
    live = load_live_module()
    kf, last_pos, vel = make_tracking_kf(live)
    comp_s = 0.130
    state_pt = last_pos.astype(np.float32)
    out = live.latency_compensated_point(kf, state_pt, comp_s, max_uncertainty_mm=500.0)
    expected = last_pos + vel * comp_s
    assert out == pytest.approx(expected, abs=15.0)  # within KF convergence noise
    # And it must lead the state, not trail it.
    assert out[0] > state_pt[0]


def test_uninitialized_or_disabled_returns_state():
    live = load_live_module()
    kf = live.JointKalmanFilter()
    state_pt = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert live.latency_compensated_point(kf, state_pt, 0.13, 500.0) is state_pt
    assert live.latency_compensated_point(None, state_pt, 0.13, 500.0) is state_pt
    kf.update_step([1.0, 2.0, 3.0])
    assert live.latency_compensated_point(kf, state_pt, 0.0, 500.0) is state_pt


def test_high_uncertainty_falls_back_to_state():
    live = load_live_module()
    kf, last_pos, _ = make_tracking_kf(live, steps=2)  # barely initialized -> big P
    state_pt = last_pos.astype(np.float32)
    out = live.latency_compensated_point(kf, state_pt, 0.4, max_uncertainty_mm=1.0)
    assert out is state_pt


def test_measured_dt_predict_step_matches_elapsed_time():
    """predict_step(dt) must propagate position by v*dt — the property the
    --kalman-measured-dt flag relies on when the loop runs slower than --fps."""
    live = load_live_module()
    kf, last_pos, vel = make_tracking_kf(live)
    v_est = kf.get_velocity()
    p0 = kf.get_position()
    kf.predict_step(0.2)
    assert kf.get_position() == pytest.approx(p0 + v_est * 0.2, rel=1e-9)


# ---- rigid-core latency leads (compute_display_leads) ----
#
# Per-joint independent KF prediction makes displayed bone lengths breathe
# (each bone end gets its own noisy velocity lead). The display loop now uses
# ONE rigid common-mode lead = component-wise median over the core joints
# (shoulders/hips), with per-joint leads only blended back via
# --pose-latency-comp-joint-frac.


def make_scene(live, core_vel=(600.0, 0.0, 0.0), n_joints=17):
    """17 KFs tracking a rigidly-moving body; fresh finite state everywhere."""
    joint_kfs = []
    joints_state = np.zeros((n_joints, 3), dtype=np.float32)
    for j in range(n_joints):
        kf, last_pos, _ = make_tracking_kf(live, velocity_mm_s=core_vel)
        joint_kfs.append(kf)
        joints_state[j] = last_pos
    joint_fresh = np.ones(n_joints, dtype=bool)
    return joint_kfs, joints_state, joint_fresh


def test_rigid_lead_matches_common_motion():
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(600.0, 0.0, 0.0))
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert set(leads) == set(range(17))
    assert rigid == pytest.approx([600.0 * 0.12, 0.0, 0.0], abs=8.0)


def test_rigid_lead_survives_one_corrupt_core_joint():
    """A physically impossible hip velocity is dropped by the sanity gate."""
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(600.0, 0.0, 0.0))
    bad = live.LATENCY_CORE_JOINTS[-1]
    joint_kfs[bad].x[3:] = (50_000.0, 0.0, 0.0)  # 50 m/s: a diverged filter
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert bad not in leads                      # velocity sanity gate dropped it
    assert rigid == pytest.approx([600.0 * 0.12, 0.0, 0.0], abs=8.0)


def test_rigid_lead_median_resists_in_gate_outlier():
    """The MEDIAN, not the gate, is what must absorb a merely-wrong core joint.

    The test above proves only the velocity gate: its 50 m/s joint never
    reaches the aggregator, so median and mean agree exactly and the choice of
    aggregator is unverified. The case that matters is a hip whose velocity is
    wrong but physically possible, so it passes every gate and lands in the
    stack. Here three core joints run at 600 mm/s and one at 6 m/s (a sprint,
    well inside the 20 m/s garbage filter): the median holds the honest 72 mm
    lead, while a mean would apply 234 mm — a 162 mm coherent lurch of the
    entire rendered skeleton, which is exactly what the rigid lead exists to
    prevent.
    """
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(600.0, 0.0, 0.0))
    bad = live.LATENCY_CORE_JOINTS[-1]
    joint_kfs[bad].x[3:] = (6_000.0, 0.0, 0.0)
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert bad in leads                          # in-gate: it DOES reach the median
    assert leads[bad][0] == pytest.approx(6_000.0 * 0.12, abs=8.0)
    assert rigid == pytest.approx([600.0 * 0.12, 0.0, 0.0], abs=8.0)
    # A mean over the same four leads would be far outside that tolerance.
    mean_x = (3 * 600.0 + 6_000.0) / 4 * 0.12
    assert abs(mean_x - 600.0 * 0.12) > 100.0


def test_rigid_lead_zero_when_core_quorum_lost():
    """<3 valid core joints -> no rigid lead (a corrupted median would lurch
    the whole skeleton coherently)."""
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live)
    for j in live.LATENCY_CORE_JOINTS[:2]:
        fresh[j] = False                          # stale: covariance frozen
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert all(j not in leads for j in live.LATENCY_CORE_JOINTS[:2])
    assert rigid == pytest.approx([0.0, 0.0, 0.0])


def test_rigid_lead_magnitude_capped():
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(1900.0, 0.0, 0.0))
    _, rigid = live.compute_display_leads(
        joint_kfs, joints_state, fresh, 0.5, max_lead_mm=250.0)
    assert float(np.linalg.norm(rigid)) <= 250.0 + 1e-6


def test_rigid_lead_cap_applies_without_being_asked():
    """The live caller passes positional args only, so the CAP that bounds a
    large-but-real lead is the signature default — pin it here, or raising the
    default to infinity would leave the suite green while a 3 m/s sprint
    rendered the skeleton 1.5 m ahead of itself."""
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(3000.0, 0.0, 0.0))
    _, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.5)
    uncapped = 3000.0 * 0.5
    assert uncapped > 1000.0                       # the lead really is large
    assert 0.0 < float(np.linalg.norm(rigid)) <= 250.0 + 1e-6
    assert rigid[0] > 0.0                          # direction preserved, not zeroed


def test_uninitialized_kfs_produce_no_leads():
    live = load_live_module()
    joint_kfs = [live.JointKalmanFilter() for _ in range(17)]
    joints_state = np.zeros((17, 3), dtype=np.float32)
    fresh = np.ones(17, dtype=bool)
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert leads == {}
    assert rigid == pytest.approx([0.0, 0.0, 0.0])


def test_rigid_lead_survives_running_speed():
    """The velocity gate is a GARBAGE filter, not a motion filter.

    At 2000 mm/s it sat at brisk-walking speed, so the rigid lead collapsed to
    exactly zero for the whole body during any running drill (the shuttle
    sprint reaches ~3 m/s) — and each crossing of the threshold translated the
    entire displayed skeleton in a single frame, the very artifact the rigid
    lead exists to prevent. Large-but-real leads are the max_lead_mm cap's job.
    """
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(3000.0, 0.0, 0.0))
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert set(leads) == set(range(17))            # nothing gated out
    assert float(np.linalg.norm(rigid)) > 0.0      # was exactly zero at 2000
    assert rigid[0] > 0.0                          # and it leads the motion


def test_velocity_gate_uses_speed_not_per_axis():
    """Gate on the velocity NORM. The per-component max was anisotropic: it
    passed (1900,1900,0) (norm 2687) while rejecting the slower (2100,0,0)."""
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(800.0, 800.0, 0.0))
    _, gated = live.compute_display_leads(
        joint_kfs, joints_state, fresh, 0.12, max_vel_mm_s=1000.0)
    assert gated == pytest.approx([0.0, 0.0, 0.0])  # norm 1131 > 1000
    _, allowed = live.compute_display_leads(
        joint_kfs, joints_state, fresh, 0.12, max_vel_mm_s=1200.0)
    assert float(np.linalg.norm(allowed)) > 0.0     # same speed, limit above it


def test_diverged_kf_velocity_still_rejected():
    """Raising the gate must not stop it doing its actual job: a KF that has
    diverged to a physically impossible speed carries no usable lead."""
    live = load_live_module()
    joint_kfs, joints_state, fresh = make_scene(live, core_vel=(600.0, 0.0, 0.0))
    for j in live.LATENCY_CORE_JOINTS:
        joint_kfs[j].x[3:] = (60_000.0, 0.0, 0.0)   # 60 m/s
    leads, rigid = live.compute_display_leads(joint_kfs, joints_state, fresh, 0.12)
    assert all(j not in leads for j in live.LATENCY_CORE_JOINTS)
    assert rigid == pytest.approx([0.0, 0.0, 0.0])
