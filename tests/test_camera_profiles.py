"""Camera-profile loading + the dependency-free triangulation/predict adapter.

These exercise the API's pure core (no FastAPI/pydantic), so they run on the
minimal install. The synthetic rig mirrors tests/test_triangulation.py.
"""

import numpy as np
import pytest

from project_cam.api.pipeline_adapter import (
    list_profiles,
    load_camera_profile,
    run_kalman_track,
    triangulate_observations,
)

K = np.array([[1000.0, 0.0, 640.0], [0.0, 1000.0, 360.0], [0.0, 0.0, 1.0]])
TARGET = np.array([1500.0, 800.0, 900.0])


def look_at(center, target, up=(0.0, 0.0, 1.0)):
    center = np.asarray(center, float)
    target = np.asarray(target, float)
    up = np.asarray(up, float)
    z = target - center
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    if np.linalg.norm(x) < 1e-9:
        x = np.cross(np.array([0.0, 1.0, 0.0]), z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.column_stack([x, y, z]).T
    t = -R @ center
    return R, t


def _rig(centers):
    proj, obs = {}, {}
    for name, c in centers.items():
        R, t = look_at(c, TARGET)
        proj[name] = np.hstack([R, t.reshape(3, 1)])
        Xc = R @ TARGET + t
        obs[name] = (Xc[0] / Xc[2], Xc[1] / Xc[2])
    return proj, obs


def test_four_cam_profile_parses():
    prof = load_camera_profile("4cam")
    assert prof.camera_count == 4
    assert prof.profile == "arena_fixed_4cam"
    assert prof.validated is True
    assert set(prof.cameras) == {"camNorth", "camEast", "camSouth", "camWest"}


def test_six_cam_profile_parses():
    prof = load_camera_profile("usb6")
    assert prof.camera_count == 6
    assert prof.status == "prototype"
    assert prof.validated is False
    assert len(prof.camera_ids()) == 6


def test_unknown_profile_raises():
    with pytest.raises(KeyError):
        load_camera_profile("camera_does_not_exist")


def test_list_profiles_has_both():
    profiles = list_profiles()
    assert "usb6" in profiles
    assert "arena_fixed_4cam" in profiles


def test_adapter_triangulates_six_cameras():
    centers = {
        "c1": [0, 0, 1500], "c2": [3000, 0, 1500], "c3": [0, 3000, 1400],
        "c4": [3000, 3000, 1600], "c5": [1500, -800, 1800], "c6": [1500, 3500, 1700],
    }
    proj, obs = _rig(centers)
    point, contributing = triangulate_observations(obs, proj)
    assert point is not None
    assert len(contributing) == 6
    assert np.allclose(point, TARGET, atol=1e-6)


def test_adapter_triangulates_arbitrary_four_cameras():
    centers = {"a": [0, 0, 1500], "b": [3000, 0, 1500], "c": [0, 3000, 1400],
               "d": [3000, 3000, 1600]}
    proj, obs = _rig(centers)
    point, contributing = triangulate_observations(obs, proj)
    assert np.allclose(point, TARGET, atol=1e-6)
    assert len(contributing) == 4


def test_adapter_requires_two_cameras():
    centers = {"a": [0, 0, 1500]}
    proj, obs = _rig(centers)
    point, contributing = triangulate_observations(obs, proj)
    assert point is None


def test_adapter_only_uses_cameras_with_projection():
    centers = {"a": [0, 0, 1500], "b": [3000, 0, 1500]}
    proj, obs = _rig(centers)
    obs["ghost"] = (0.1, 0.1)  # observation without a projection matrix
    point, contributing = triangulate_observations(obs, proj)
    assert contributing == ["a", "b"]
    assert np.allclose(point, TARGET, atol=1e-6)


def test_kalman_adapter_predicts_forward():
    # constant-velocity track: 100 mm/frame in +x at dt=1/15 s.
    dt = 1.0 / 15.0
    track = [[float(i) * 100.0, 0.0, 1000.0] for i in range(10)]
    out = run_kalman_track(track, dt=dt, predict_ahead_ms=400.0)
    assert out["samples"] == 10
    # velocity ~ 100 mm / dt ~ 1500 mm/s in x.
    assert out["velocity_mm_s"][0] > 1000.0
    # lead prediction should be ahead of the last observed x (=900).
    assert out["predicted_position_mm"][0] > 900.0
