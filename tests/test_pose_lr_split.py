"""Tests for geometric L/R pair splitting (split_merged_lr_pair) and the
transient whole-pair rename guard (rename_crossed_lr_pair).

The single-leg-stance artifact: some cameras mirror YOLO's left/right leg
labels; triangulating each label separately then lands BOTH 3D ankles on
their average, so the lifted leg drags the stance leg up ("the second leg
rises too"). The split distrusts labels entirely and lets multi-view
geometry decide which detection belongs to which leg.
"""

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


def lookat(cam_pos, target, up=(0.0, 0.0, 1.0)):
    """R, tvec for a camera at cam_pos looking at target (z_cam = forward)."""
    cam_pos = np.asarray(cam_pos, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    z = target - cam_pos
    z /= np.linalg.norm(z)
    x = np.cross(z, np.asarray(up, dtype=np.float64))
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])
    tvec = -R @ cam_pos
    return R, tvec


K = np.array([[500.0, 0.0, 320.0], [0.0, 500.0, 180.0], [0.0, 0.0, 1.0]])
D = np.zeros(5)

# True single-leg pose: left ankle planted, right ankle lifted ~320 mm.
TRUE_L = np.array([-150.0, 0.0, 100.0])
TRUE_R = np.array([150.0, 30.0, 420.0])
KNEE_L = np.array([-160.0, 10.0, 520.0])
KNEE_R = np.array([140.0, 60.0, 700.0])


def make_rig():
    """Four cameras around the athlete, all seeing the ankles."""
    cams = {}
    positions = {
        "camN": (0.0, -3000.0, 1200.0),
        "camE": (3000.0, 0.0, 1200.0),
        "camS": (0.0, 3000.0, 1200.0),
        "camW": (-3000.0, 0.0, 1200.0),
    }
    extr, intr, proj = {}, {}, {}
    for name, pos in positions.items():
        R, tvec = lookat(pos, (0.0, 0.0, 500.0))
        extr[name] = {"R": R, "tvec": tvec, "P": np.hstack([R, tvec.reshape(3, 1)])}
        intr[name] = {"K": K, "D": D}
        proj[name] = extr[name]["P"]
        cams[name] = (R, tvec)
    return cams, extr, intr, proj


def obs_of(live, cams, point):
    """(normalized, pixel) observations of a world point in every camera."""
    norm, px = {}, {}
    for name, (R, tvec) in cams.items():
        xc = R @ np.asarray(point, dtype=np.float64) + tvec
        norm[name] = (xc[0] / xc[2], xc[1] / xc[2])
        px[name] = np.asarray(
            live.project_world_to_pixel(point, R, tvec, K, D), dtype=np.float64)
    return norm, px


def mislabeled_pair(live, cams, mirrored, order):
    """Per-label observation dicts where `mirrored` cams swapped L and R."""
    nl, pl = obs_of(live, cams, TRUE_L)
    nr, pr = obs_of(live, cams, TRUE_R)
    obs_l, opx_l, obs_r, opx_r = {}, {}, {}, {}
    for cam in order:
        if cam in mirrored:
            obs_l[cam], opx_l[cam] = nr[cam], pr[cam]
            obs_r[cam], opx_r[cam] = nl[cam], pl[cam]
        else:
            obs_l[cam], opx_l[cam] = nl[cam], pl[cam]
            obs_r[cam], opx_r[cam] = nr[cam], pr[cam]
    return obs_l, opx_l, obs_r, opx_r


def test_label_trusting_triangulation_raises_both_ankles():
    """Control: with half the cameras mirrored, trusting the labels lands BOTH
    'ankles' at mid-height — the 'lift one leg, the second rises too'
    artifact seen live. (The pair does NOT merge in 3D, which is why the
    split trigger is residual-based, not distance-only.)"""
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    obs_l, _, obs_r, _ = mislabeled_pair(
        live, cams, mirrored={"camE", "camW"}, order=["camN", "camE", "camS", "camW"])
    xl = np.asarray(live.triangulate_multi(obs_l, proj))
    xr = np.asarray(live.triangulate_multi(obs_r, proj))
    true_dz = abs(TRUE_L[2] - TRUE_R[2])                  # 320 mm lift
    assert abs(xl[2] - xr[2]) < 0.2 * true_dz             # heights merged
    assert min(xl[2], xr[2]) > TRUE_L[2] + 100.0          # stance foot rose
    # ...and the mixed result leaves the cameras in strong disagreement,
    # which is exactly what the split trigger keys on:
    resid = max(live._pair_norm_cost_px(xl, obs_l, extr, intr),
                live._pair_norm_cost_px(xr, obs_r, extr, intr))
    assert resid > 12.0


def test_split_recovers_both_ankles_from_mixed_labels():
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    obs_l, opx_l, obs_r, opx_r = mislabeled_pair(
        live, cams, mirrored={"camE", "camW"}, order=["camN", "camE", "camS", "camW"])
    result = live.split_merged_lr_pair(
        obs_l, opx_l, obs_r, opx_r, proj, extr, intr,
        prev_l=TRUE_L + 20.0, prev_r=TRUE_R + 20.0)
    assert result is not None
    pt_l, pt_r, used_l, used_r, flipped, renamed = result
    assert np.linalg.norm(pt_l - TRUE_L) < 5.0
    assert np.linalg.norm(pt_r - TRUE_R) < 5.0
    assert renamed is False
    assert set(flipped) == {"camE", "camW"}
    assert len(used_l) >= 2 and len(used_r) >= 2


def test_split_renames_when_reference_camera_is_the_mirrored_one():
    """If the reference (first) camera is itself mirrored, the clusters come
    out name-swapped — temporal continuity must rename them."""
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    obs_l, opx_l, obs_r, opx_r = mislabeled_pair(
        live, cams, mirrored={"camE", "camW"}, order=["camE", "camN", "camS", "camW"])
    result = live.split_merged_lr_pair(
        obs_l, opx_l, obs_r, opx_r, proj, extr, intr,
        prev_l=TRUE_L + 15.0, prev_r=TRUE_R + 15.0)
    assert result is not None
    pt_l, pt_r, _, _, _, renamed = result
    assert renamed is True
    assert np.linalg.norm(pt_l - TRUE_L) < 5.0
    assert np.linalg.norm(pt_r - TRUE_R) < 5.0


def test_split_names_by_parent_anchor_when_prev_state_is_merged():
    """A collapsed previous state cannot name the clusters — the same-side
    knees (parent anchors) must."""
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    obs_l, opx_l, obs_r, opx_r = mislabeled_pair(
        live, cams, mirrored={"camE"}, order=["camE", "camN", "camS", "camW"])
    merged_prev = np.array([0.0, 10.0, 250.0])
    result = live.split_merged_lr_pair(
        obs_l, opx_l, obs_r, opx_r, proj, extr, intr,
        prev_l=merged_prev, prev_r=merged_prev + 5.0,
        anchor_l=KNEE_L, anchor_r=KNEE_R)
    assert result is not None
    pt_l, pt_r, _, _, _, _ = result
    assert np.linalg.norm(pt_l - TRUE_L) < 5.0
    assert np.linalg.norm(pt_r - TRUE_R) < 5.0


def test_split_declines_when_feet_are_genuinely_together():
    """Feet side by side is not an error: the best split stays under the
    separation threshold, so the pair is left alone."""
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    together_l = np.array([-40.0, 0.0, 100.0])
    together_r = np.array([40.0, 0.0, 100.0])
    nl, pl = obs_of(live, cams, together_l)
    nr, pr = obs_of(live, cams, together_r)
    result = live.split_merged_lr_pair(
        nl, pl, nr, pr, proj, extr, intr,
        prev_l=together_l, prev_r=together_r, min_sep_mm=100.0)
    assert result is None


def test_split_needs_at_least_two_shared_cameras():
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    nl, pl = obs_of(live, cams, TRUE_L)
    nr, pr = obs_of(live, cams, TRUE_R)
    one_l = {"camN": nl["camN"]}
    one_r = {"camN": nr["camN"]}
    assert live.split_merged_lr_pair(
        one_l, {"camN": pl["camN"]}, one_r, {"camN": pr["camN"]},
        proj, extr, intr) is None


def test_rename_crossed_pair_detects_a_clear_swap():
    live = load_live_module()
    prev_l, prev_r = TRUE_L, TRUE_R
    # fresh triangulation came out with the names exchanged
    assert live.rename_crossed_lr_pair(TRUE_R, TRUE_L, prev_l, prev_r) is True
    # correct names stay
    assert live.rename_crossed_lr_pair(TRUE_L, TRUE_R, prev_l, prev_r) is False


def test_rename_crossed_pair_is_conservative():
    live = load_live_module()
    merged = np.array([0.0, 0.0, 200.0])
    # merged previous state cannot vote
    assert live.rename_crossed_lr_pair(TRUE_R, TRUE_L, merged, merged + 1.0) is False
    # orthogonal displacement (pair rotated 90° vs previous) is genuinely
    # ambiguous — keep and cross cost the same, so names must not flip
    prev_l = np.array([-60.0, 0.0, 200.0])
    prev_r = np.array([60.0, 0.0, 200.0])
    rot_l = np.array([0.0, -60.0, 200.0])
    rot_r = np.array([0.0, 60.0, 200.0])
    assert live.rename_crossed_lr_pair(rot_l, rot_r, prev_l, prev_r,
                                       min_sep_mm=100.0) is False

def noisy_pair_obs(live, cams, point_l, point_r, seed, noise_px):
    """Both joints observed in every camera with independent per-camera noise.

    Noise is added in NORMALIZED coordinates (and mirrored into pixels) so the
    two observation dicts stay mutually consistent, exactly as the live
    undistort path produces them.
    """
    rng = np.random.default_rng(seed)
    nz = noise_px / K[0, 0]
    out = []
    for point in (point_l, point_r):
        norm, px = {}, {}
        for name, (R, tvec) in cams.items():
            xc = R @ np.asarray(point, dtype=np.float64) + tvec
            u = xc[0] / xc[2] + rng.normal(0.0, nz)
            v = xc[1] / xc[2] + rng.normal(0.0, nz)
            norm[name] = (u, v)
            px[name] = np.array([K[0, 0] * u + K[0, 2], K[1, 1] * v + K[1, 2]])
        out.append((norm, px))
    return out


def test_near_tie_flip_is_declined_by_the_anti_churn_margin():
    """A label flip must win CLEARLY, not by a hair.

    When the two joints are close together, a few px of keypoint noise makes
    the flipped and label-trusting hypotheses nearly equal in residual, so the
    argmin alternates frame to frame and the legs churn at the update rate.
    Every other test in this file is a landslide (residual gaps of 14-27 px
    vs ~1e-13), so the guard was never once exercised: it could be deleted
    outright with the suite still green.

    This is a measured near-tie — flip residual within ~0.1% of the direct
    one — where relaxing the margin to 1.0 visibly changes the outcome.
    """
    live = load_live_module()
    cams, extr, intr, proj = make_rig()
    left = np.array([-110.0, 0.0, 300.0])
    right = np.array([110.0, 0.0, 300.0])
    (nl, pl), (nr, pr) = noisy_pair_obs(live, cams, left, right,
                                        seed=26, noise_px=6.0)

    kw = dict(prev_l=left, prev_r=right, min_sep_mm=100.0)
    declined = live.split_merged_lr_pair(nl, pl, nr, pr, proj, extr, intr, **kw)
    assert declined is not None
    assert sorted(declined[4]) == []         # anti-churn kept the labels

    # Same inputs, margin relaxed to "accept any improvement": the flip wins,
    # which is what would happen every other frame without the guard.
    churned = live.split_merged_lr_pair(nl, pl, nr, pr, proj, extr, intr,
                                        flip_margin=1.0, **kw)
    assert churned is not None
    assert sorted(churned[4]) == ["camW"]
