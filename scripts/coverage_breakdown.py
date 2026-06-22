#!/usr/bin/env python3
"""
coverage_breakdown.py — how much of the garage is seen by >=2..>=6 cameras.

Uses the 6-USB cable-aware layout with REAL per-camera FOV:
  - 4x DS-E12 (1080P USB): HFOV ~83 deg, VFOV ~53 deg (measured from intrinsics)
  - 2x Logitech C920:      HFOV ~70 deg, VFOV ~43 deg (narrower)

Pure geometric frustum coverage (necessary condition to triangulate). Does NOT
model occlusion by the body, motion blur, sync, or detection — so treat it as an
upper bound on "could be seen", not a detection guarantee.
"""
from __future__ import annotations
import math
import numpy as np

ARENA = np.array([6230.0, 3050.0, 2950.0])   # X N->S, Y E->W, Z up
NEAR, FAR = 150.0, 7000.0

# name, pos(x,y,z), aim(x,y,z), hfov, vfov
CAMS = [
    ("camNorth_EastHigh",  (80, 550, 2200),  (3600, 1500, 1100), 83, 53),  # DS-E12
    ("camNorth_WestHigh",  (80, 2500, 2200), (3600, 1500, 1100), 83, 53),  # DS-E12
    ("camEast_Low",        (3100, 80, 450),  (3400, 1500, 450),  70, 43),  # C920
    ("camWest_Low",        (3100, 2970, 450),(3400, 1500, 450),  70, 43),  # C920
    ("camSouth_High",      (6150, 2300, 2300),(2800, 1500, 1000),83, 53),  # DS-E12
    ("camBounce_TargetLow",(5000, 80, 350),  (6230, 1600, 850),  83, 53),  # DS-E12
]


def basis(pos, aim):
    pos = np.array(pos, float); aim = np.array(aim, float)
    f = aim - pos; f /= np.linalg.norm(f)
    up = np.array([0, 0, 1.0])
    r = np.cross(f, up)
    if np.linalg.norm(r) < 1e-6:
        up = np.array([0, 1.0, 0]); r = np.cross(f, up)
    r /= np.linalg.norm(r); u = np.cross(r, f); u /= np.linalg.norm(u)
    return pos, r, u, f


def in_frustum(cam, pts):
    _, pos, aim, hf, vf = cam[0], cam[1], cam[2], cam[3], cam[4]
    p, r, u, f = basis(pos, aim)
    rel = pts - p[None, :]
    xc = rel @ r; yc = rel @ u; zc = rel @ f
    th = math.tan(math.radians(hf) / 2); tv = math.tan(math.radians(vf) / 2)
    return (zc >= NEAR) & (zc <= FAR) & (np.abs(xc) <= zc * th) & (np.abs(yc) <= zc * tv)


def grid(xr, yr, zr, step=100.0):
    xs = np.arange(xr[0], xr[1] + 1, step)
    ys = np.arange(yr[0], yr[1] + 1, step)
    zs = np.arange(zr[0], zr[1] + 1, step)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.stack([X, Y, Z], -1).reshape(-1, 3)


def counts_for(pts):
    c = np.zeros(len(pts), int)
    for cam in CAMS:
        c += in_frustum(cam, pts).astype(int)
    return c


def report(title, pts):
    c = counts_for(pts)
    n = len(pts)
    print(f"\n=== {title}  ({n} voxels) ===")
    print("  cumulative (seen by AT LEAST k cameras):")
    for k in range(2, 7):
        print(f"    >={k} cams: {100.0*np.mean(c>=k):5.1f}%")
    print("  exactly k cameras:")
    for k in range(0, 7):
        pct = 100.0*np.mean(c == k)
        bar = "#" * int(pct/2)
        print(f"    {k} cams: {pct:5.1f}%  {bar}")


if __name__ == "__main__":
    # whole play volume (body height up to 2.2 m)
    report("FULL PLAY VOLUME  (X0-6230, Y0-3050, Z0-2200)",
           grid((0, 6230), (0, 3050), (0, 2200)))
    # central working zone (where the player actually trains — away from walls/corners)
    report("CENTRAL WORKING ZONE  (X1200-5200, Y500-2550, Z200-2000)",
           grid((1200, 5200), (500, 2550), (200, 2000)))
    # floor / push-up layer
    report("FLOOR / PUSH-UP LAYER  (X1500-5200, Y500-2550, Z100-600)",
           grid((1500, 5200), (500, 2550), (100, 600)))
    # bounce strip near the south wall
    report("BOUNCE STRIP  (X5600-6230, Y0-3050, Z0-400)",
           grid((5600, 6230), (0, 3050), (0, 400)))
