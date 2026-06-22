#!/usr/bin/env python3
"""Position-gated + winding-voting AprilTag extrinsics solver for the 6-USB rig.

Two problems break naive per-camera PnP against wall tags:
  1) Pose reflection ambiguity: a reflected pose reprojects with low error but
     places the camera outside the room. -> fixed by POSITION GATING (keep only
     solutions whose recovered position lands inside the arena).
  2) Inconsistent tag corner winding in Dimensions.txt: a tag's 4 world corners
     may be ordered so its normal points the wrong way, so the camera lands
     behind the wall. -> fixed by GLOBAL PERMUTATION VOTING across all cameras
     (each tag gets one consistent corner permutation, chosen by majority of the
     cameras that see it, weighted by reprojection error).

Output matches calibrate_extrinsics_apriltag_robust.py (rvec, tvec in meters,
camera_position in meters) so the live viewer loads it unchanged.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

PERMUTATIONS = [
    [0, 1, 2, 3], [1, 2, 3, 0], [2, 3, 0, 1], [3, 0, 1, 2],
    [0, 3, 2, 1], [3, 2, 1, 0], [2, 1, 0, 3], [1, 0, 3, 2],
]


def parse_dimensions(path: Path):
    tags, coords, arena, cur = {}, {}, {}, None
    for raw in open(path):
        line = raw.strip()
        m = re.match(r"([XYZ])\s*=\s*([\d.]+)\s*cm", line)
        if m:
            arena[m.group(1)] = float(m.group(2)) / 100.0
        t = re.match(r"ID=(\d+):", line)
        if t:
            cur = int(t.group(1)); coords[cur] = {}; continue
        c = re.match(r"c(\d+)\s*\(([^,]+),\s*([^,]+),\s*([^)]+)\)", line)
        if c and cur is not None:
            coords[cur][int(c.group(1))] = np.array(
                [float(c.group(2)), float(c.group(3)), float(c.group(4))],
                dtype=np.float32) / 100.0
    for tid, cs in coords.items():
        if len(cs) == 4:
            tags[tid] = np.stack([cs[i] for i in range(4)], axis=0)
    return tags, arena


def load_intrinsics(path: Path):
    d = json.load(open(path))
    K = np.array(d["camera_matrix"], dtype=np.float64)
    D = np.array(d.get("distortion_coefficients", d.get("dist_coeffs", [0]*5)),
                 dtype=np.float64).reshape(-1)
    return K, D, d.get("image_width"), d.get("image_height")


def collect_obs(cam_dir: Path, world_tags, detector, max_images, target=None):
    obs = []
    files = sorted(list(cam_dir.glob("*.jpg")) + list(cam_dir.glob("*.png")))
    if max_images > 0:
        files = files[:max_images]
    for fp in files:
        im = cv2.imread(str(fp))
        if im is None:
            continue
        if target and (im.shape[1], im.shape[0]) != target:
            im = cv2.resize(im, target)
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        if ids is None:
            continue
        for i, ta in enumerate(ids):
            tid = int(ta[0])
            if tid in world_tags:
                obs.append((tid, corners[i][0].astype(np.float32)))
    return obs


def cam_pos(rvec, tvec):
    R, _ = cv2.Rodrigues(rvec)
    return (-(R.T @ tvec.reshape(3, 1))).reshape(3)


def reproj(obj, img, rvec, tvec, K, D):
    p, _ = cv2.projectPoints(obj, rvec, tvec, K, D)
    e = np.linalg.norm(p.reshape(-1, 2) - img, axis=1)
    return float(np.sqrt(np.mean(e ** 2))), e


def lookat(S, target):
    z = target - S; z /= np.linalg.norm(z) + 1e-9
    up = np.array([0, 0, 1.0])
    if abs(np.dot(up, z)) > 0.97:
        up = np.array([0, 1.0, 0])
    x = np.cross(up, z); x /= np.linalg.norm(x) + 1e-9
    y = np.cross(z, x)
    R_wc = np.stack([x, y, z], axis=1).T
    rvec, _ = cv2.Rodrigues(R_wc)
    tvec = (-R_wc @ S.reshape(3, 1)).astype(np.float64)
    return rvec, tvec


def refine(obj, img, rvec, tvec, K, D, iters=10, min_pts=16):
    mask = np.ones(len(obj), bool)
    for _ in range(iters):
        if mask.sum() < min_pts:
            break
        ok, rvec, tvec = cv2.solvePnP(obj[mask], img[mask], K, D, rvec, tvec,
                                      True, cv2.SOLVEPNP_ITERATIVE)
        if not ok:
            break
        _, e = reproj(obj[mask], img[mask], rvec, tvec, K, D)
        med = np.median(e); thr = max(6.0, med + 2.5 * 1.4826 * np.median(np.abs(e - med)))
        idx = np.where(mask)[0]
        new = np.zeros(len(obj), bool); new[idx[e <= thr]] = True
        if new.sum() == mask.sum():
            break
        mask = new
    r, _ = reproj(obj[mask], img[mask], rvec, tvec, K, D)
    return rvec, tvec, r, int(mask.sum())


def solve_gated(obj, img, K, D, seeds, centroid, lo, hi):
    """Generate candidate poses (plain PnP + look-at seeds + RANSAC), refine,
    return the in-arena candidate with lowest rmse (else lowest rmse overall)."""
    cands = []
    ok, rv, tv = cv2.solvePnP(obj, img, K, D, flags=cv2.SOLVEPNP_ITERATIVE)
    if ok:
        cands.append(refine(obj, img, rv, tv, K, D))
    okr, rvr, tvr, inl = cv2.solvePnPRansac(obj, img, K, D, reprojectionError=8.0,
                                            iterationsCount=2000, flags=cv2.SOLVEPNP_ITERATIVE)
    if okr:
        cands.append(refine(obj, img, rvr, tvr, K, D))
    for S in seeds:
        rv0, tv0 = lookat(S, centroid)
        ok2, rv2, tv2 = cv2.solvePnP(obj, img, K, D, rv0.copy(), tv0.copy(),
                                     True, cv2.SOLVEPNP_ITERATIVE)
        if ok2:
            cands.append(refine(obj, img, rv2, tv2, K, D))
    if not cands:
        return None
    inside = [c for c in cands
              if np.all(cam_pos(c[0], c[1]) >= lo) and np.all(cam_pos(c[0], c[1]) <= hi)]
    pool = inside if inside else cands
    rvec, tvec, r, n = min(pool, key=lambda c: c[2])
    return rvec, tvec, r, n, bool(inside)


def build_corr(obs, world_tags, perm_map):
    o, i = [], []
    for tid, c2d in obs:
        perm = PERMUTATIONS[perm_map.get(tid, 0)]
        o.append(world_tags[tid][perm]); i.append(c2d)
    return (np.concatenate(o).astype(np.float32), np.concatenate(i).astype(np.float32)) if o else (None, None)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images-root", required=True)
    ap.add_argument("--dimensions", default="arena_fixed/cal/extrinsics/Dimensions_fixed.txt")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics_usb6_1280x720")
    ap.add_argument("--cameras", nargs="+", default=[
        "camUsb01_C920", "camUsb02_1080P", "camUsb03_C920",
        "camUsb04_1080P", "camUsb05_1080P", "camUsb06_1080P"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-images", type=int, default=50)
    ap.add_argument("--margin-m", type=float, default=0.6)
    ap.add_argument("--iters", type=int, default=6)
    args = ap.parse_args()

    world_tags, arena = parse_dimensions(Path(args.dimensions))
    X, Y, Z = arena.get("X", 6.23), arena.get("Y", 3.05), arena.get("Z", 2.95)
    m = args.margin_m
    lo, hi = np.array([-m, -m, -m]), np.array([X+m, Y+m, Z+m])
    print(f"Arena {X:.2f} x {Y:.2f} x {Z:.2f} m | margin {m} m\n")

    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11),
        cv2.aruco.DetectorParameters())
    seeds = [np.array([X/2, Y/2, Z/2])]
    for sx in (0.2, 0.5, 0.8):
        for sy in (0.2, 0.5, 0.8):
            for sz in (0.4, 0.85):
                seeds.append(np.array([X*sx, Y*sy, Z*sz]))

    root = Path(args.images_root)
    obs_by_cam, intr, pose = {}, {}, {}
    for cam in args.cameras:
        cd = root / cam
        if not cd.exists():
            print(f"  {cam}: NO DIR"); continue
        K, D, iw, ih = load_intrinsics(Path(args.intrinsics_dir) / f"{cam}_intrinsics.json")
        intr[cam] = (K, D)
        obs_by_cam[cam] = collect_obs(cd, world_tags, detector, args.max_images,
                                      (iw, ih) if iw and ih else None)

    perm_map = {tid: 0 for tid in world_tags}

    # bootstrap poses with default perms
    for cam, obs in obs_by_cam.items():
        if not obs:
            continue
        o, i = build_corr(obs, world_tags, perm_map)
        cen = o.reshape(-1, 4, 3).mean(axis=(0, 1)) if len(o) else np.array([X/2, Y/2, Z/2])
        res = solve_gated(o, i, *intr[cam], seeds, cen, lo, hi)
        if res:
            pose[cam] = res[:2]

    # iterate: vote tag permutations across cameras, then re-solve each camera
    for it in range(args.iters):
        votes = defaultdict(lambda: np.zeros(len(PERMUTATIONS)))
        for cam, obs in obs_by_cam.items():
            if cam not in pose:
                continue
            K, D = intr[cam]; rvec, tvec = pose[cam]
            for tid, c2d in obs:
                errs = [reproj(world_tags[tid][p], c2d, rvec, tvec, K, D)[0] for p in PERMUTATIONS]
                votes[tid][int(np.argmin(errs))] += 1.0 / max(0.5, min(errs))
        changed = 0
        for tid, v in votes.items():
            b = int(np.argmax(v))
            if perm_map[tid] != b:
                perm_map[tid] = b; changed += 1
        for cam, obs in obs_by_cam.items():
            if not obs:
                continue
            o, i = build_corr(obs, world_tags, perm_map)
            cen = o.reshape(-1, 4, 3).mean(axis=(0, 1))
            res = solve_gated(o, i, *intr[cam], seeds, cen, lo, hi)
            if res:
                pose[cam] = res[:2]
        print(f"[iter {it+1}] perm_changed={changed}")

    out = {}
    print()
    for cam, obs in obs_by_cam.items():
        if cam not in pose or not obs:
            print(f"  {cam:16s} UNSOLVED"); continue
        o, i = build_corr(obs, world_tags, perm_map)
        cen = o.reshape(-1, 4, 3).mean(axis=(0, 1))
        rvec, tvec, r, n, ok_in = solve_gated(o, i, *intr[cam], seeds, cen, lo, hi)
        p = cam_pos(rvec, tvec)
        out[cam] = {"rvec": rvec.reshape(3).tolist(), "tvec": tvec.reshape(3).tolist(),
                    "camera_position": p.tolist(), "reprojection_error_rmse": r,
                    "num_tags_inlier": len(set(t for t, _ in obs)), "in_arena": ok_in}
        print(f"  {cam:16s} pos={np.round(p,2)}  rmse={r:6.2f}px  "
              f"tags={sorted(set(t for t,_ in obs))}  {'OK' if ok_in else '<<< OUT'}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(args.out, "w"), indent=2)
    n_ok = sum(1 for v in out.values() if v["in_arena"])
    print(f"\n[DONE] {n_ok}/{len(out)} in-arena -> {args.out}")


if __name__ == "__main__":
    main()
