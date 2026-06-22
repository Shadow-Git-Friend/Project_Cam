"""Synthetic-rig tests for multi-view triangulation.

A known 3D world point is projected into several calibrated pinhole cameras; the
geometry helpers must recover it to sub-millimetre accuracy and reject a camera
fed a corrupted observation.
"""

import numpy as np

from project_cam.geometry import (
    project_ray_to_z_plane,
    robust_triangulate_ball,
    triangulate_multi,
)

K = np.array([[1000.0, 0.0, 640.0], [0.0, 1000.0, 360.0], [0.0, 0.0, 1.0]])
D = np.zeros(5)

TARGET = np.array([1500.0, 800.0, 900.0])


def look_at(center, target, up=(0.0, 0.0, 1.0)):
    """World->camera (R, t) for a pinhole camera centered at ``center``."""
    center = np.asarray(center, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    z = target - center
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    if np.linalg.norm(x) < 1e-9:
        x = np.cross(np.array([0.0, 1.0, 0.0]), z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.column_stack([x, y, z]).T  # rows are camera axes in world frame
    t = -R @ center
    return {"R": R, "tvec": t.reshape(3, 1)}


def to_norm(X, cam):
    Xc = cam["R"] @ X + cam["tvec"].reshape(3)
    return (Xc[0] / Xc[2], Xc[1] / Xc[2])


def to_px(X, cam):
    Xc = cam["R"] @ X + cam["tvec"].reshape(3)
    uv = K @ (Xc / Xc[2])
    return uv[:2]


def proj_mat(cam):
    return np.hstack([cam["R"], cam["tvec"].reshape(3, 1)])


_CENTERS = {
    "camA": [0.0, 0.0, 1500.0],
    "camB": [3000.0, 0.0, 1500.0],
    "camC": [0.0, 3000.0, 1400.0],
    "camD": [3000.0, 3000.0, 1600.0],
    "camE": [1500.0, -800.0, 1800.0],
    "camF": [1500.0, 3500.0, 1700.0],
}
CAMS = {name: look_at(c, TARGET) for name, c in _CENTERS.items()}


def test_triangulate_multi_recovers_point():
    obs = {c: to_norm(TARGET, cam) for c, cam in CAMS.items()}
    proj = {c: proj_mat(cam) for c, cam in CAMS.items()}
    X = triangulate_multi(obs, proj)
    assert X is not None
    assert np.allclose(X, TARGET, atol=1e-6)


def test_triangulate_multi_recovers_from_two_views():
    pair = {k: CAMS[k] for k in ("camA", "camB")}
    obs = {c: to_norm(TARGET, cam) for c, cam in pair.items()}
    proj = {c: proj_mat(cam) for c, cam in pair.items()}
    X = triangulate_multi(obs, proj)
    assert np.allclose(X, TARGET, atol=1e-6)


def test_triangulate_multi_needs_two_views():
    obs = {"camA": to_norm(TARGET, CAMS["camA"])}
    proj = {"camA": proj_mat(CAMS["camA"])}
    assert triangulate_multi(obs, proj) is None


def test_robust_triangulate_rejects_outlier_camera():
    intr = {c: {"K": K, "D": D} for c in CAMS}
    proj = {c: proj_mat(cam) for c, cam in CAMS.items()}
    obs_norm = {c: to_norm(TARGET, cam) for c, cam in CAMS.items()}
    obs_px = {c: to_px(TARGET, cam) for c, cam in CAMS.items()}

    # camD "sees" a point well away from the true target (e.g. a cone mislabelled
    # as the ball). It must be dropped, and the remaining cameras must agree.
    decoy = TARGET + np.array([1500.0, -1200.0, 800.0])
    obs_norm["camD"] = to_norm(decoy, CAMS["camD"])
    obs_px["camD"] = to_px(decoy, CAMS["camD"])

    X, inliers, mean_reproj = robust_triangulate_ball(
        obs_norm, obs_px, proj, CAMS, intr, min_cams=2, max_reproj_px=5.0
    )
    assert X is not None
    assert "camD" not in inliers
    assert mean_reproj < 5.0
    assert np.linalg.norm(X - TARGET) < 1e-3


def test_robust_triangulate_keeps_all_cameras_when_clean():
    intr = {c: {"K": K, "D": D} for c in CAMS}
    proj = {c: proj_mat(cam) for c, cam in CAMS.items()}
    obs_norm = {c: to_norm(TARGET, cam) for c, cam in CAMS.items()}
    obs_px = {c: to_px(TARGET, cam) for c, cam in CAMS.items()}
    X, inliers, _ = robust_triangulate_ball(obs_norm, obs_px, proj, CAMS, intr)
    assert sorted(inliers) == sorted(CAMS.keys())
    assert np.allclose(X, TARGET, atol=1e-6)


def test_robust_triangulate_fails_below_min_cams():
    intr = {c: {"K": K, "D": D} for c in CAMS}
    proj = {c: proj_mat(cam) for c, cam in CAMS.items()}
    single = {"camA": to_norm(TARGET, CAMS["camA"])}
    single_px = {"camA": to_px(TARGET, CAMS["camA"])}
    X, inliers, _ = robust_triangulate_ball(single, single_px, proj, CAMS, intr)
    assert X is None
    assert inliers == []


def test_project_ray_to_z_plane_hits_known_point():
    cam = CAMS["camA"]
    obs = to_norm(TARGET, cam)
    X = project_ray_to_z_plane(obs, cam["R"], cam["tvec"], target_z=TARGET[2])
    assert X is not None
    assert np.allclose(X, TARGET, atol=1e-6)


def test_project_ray_to_z_plane_none_when_plane_behind():
    # camA sits at z=1500 looking down at z=900; the ray descends, so a plane at
    # z=3000 lies behind the camera along the ray (s <= 0) and yields no hit.
    cam = CAMS["camA"]
    obs = to_norm(TARGET, cam)
    assert project_ray_to_z_plane(obs, cam["R"], cam["tvec"], target_z=3000.0) is None
