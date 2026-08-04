#!/usr/bin/env python3
"""
optimize_camera_geometry.py — search camera placements for Project_Cam.

This script uses the real projector target allocation from
`proxiball_3d-main/projector/homography.json` and scores candidate camera layouts
against three regions:

1. South-wall 3x3 target cells (highest weight)
2. Floor/south-wall bounce strip
3. Human pose volume, including low push-up points

It is intentionally a discrete mount-grid optimizer, not a continuous optimizer:
the garage only has practical wall/side mounting positions. Every candidate in
that mount grid is evaluated; a beam search keeps the best partial layouts while
combining six camera roles.

Outputs:
  scripts/coverage_out/optimized_camera_layout.json
  scripts/coverage_out/optimized_camera_layout.csv
  scripts/coverage_out/optimized_layout_topdown.png
  scripts/coverage_out/optimized_layout_3d.png

Run:
  ./venv/bin/python scripts/optimize_camera_geometry.py
  ./venv/bin/python scripts/optimize_camera_geometry.py --beam 800 --step 150
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

import matplotlib

if "--show" not in sys.argv:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PROJECTOR_DIR = ROOT / "proxiball_3d-main" / "projector"
sys.path.insert(0, str(PROJECTOR_DIR))

from static_grid_goal_logic import (  # noqa: E402
    target_grid_rectangles,
    wall_bounds_from_homography,
)


ARENA = np.array([6230.0, 3050.0, 2950.0])  # X north->south, Y east->west, Z up
SOUTH_X = ARENA[0]
OUT_DIR = ROOT / "scripts" / "coverage_out"


@dataclass(frozen=True)
class Candidate:
    role: str
    name: str
    pos: tuple[float, float, float]
    look_at: tuple[float, float, float]
    hfov_deg: float = 82.0
    vfov_deg: float = 52.0
    far_mm: float = 7000.0


@dataclass
class ScoreBreakdown:
    total: float
    target_mean: float
    target_min: float
    bounce_mean: float
    pose_mean: float
    play_ge2_pct: float
    play_ge3_pct: float
    play_angle45_pct: float
    bounce_ge2_pct: float
    bounce_angle45_pct: float


def unit_basis(cam: Candidate):
    pos = np.array(cam.pos, dtype=np.float64)
    look = np.array(cam.look_at, dtype=np.float64)
    fwd = look - pos
    fwd /= np.linalg.norm(fwd)
    up_world = np.array([0.0, 0.0, 1.0])
    right = np.cross(fwd, up_world)
    if np.linalg.norm(right) < 1e-8:
        up_world = np.array([0.0, 1.0, 0.0])
        right = np.cross(fwd, up_world)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    up /= np.linalg.norm(up)
    return right, up, fwd


def visible_mask(cam: Candidate, pts: np.ndarray) -> np.ndarray:
    pos = np.array(cam.pos, dtype=np.float64)
    right, up, fwd = unit_basis(cam)
    rel = pts - pos[None, :]
    xc = rel @ right
    yc = rel @ up
    zc = rel @ fwd
    th = math.tan(math.radians(cam.hfov_deg) / 2.0)
    tv = math.tan(math.radians(cam.vfov_deg) / 2.0)
    return (
        (zc >= 120.0)
        & (zc <= cam.far_mm)
        & (np.abs(xc) <= zc * th)
        & (np.abs(yc) <= zc * tv)
    )


def best_pair_angles(cams: list[Candidate], pts: np.ndarray, masks: np.ndarray) -> np.ndarray:
    best = np.zeros(len(pts), dtype=np.float64)
    positions = [np.array(c.pos, dtype=np.float64) for c in cams]
    for i in range(len(cams)):
        for j in range(i + 1, len(cams)):
            both = masks[i] & masks[j]
            if not np.any(both):
                continue
            va = positions[i][None, :] - pts[both]
            vb = positions[j][None, :] - pts[both]
            va /= np.linalg.norm(va, axis=1)[:, None]
            vb /= np.linalg.norm(vb, axis=1)[:, None]
            dots = np.clip(np.sum(va * vb, axis=1), -1.0, 1.0)
            ang = np.degrees(np.arccos(dots))
            ang = np.minimum(ang, 180.0 - ang)
            best[both] = np.maximum(best[both], ang)
    return best


def point_quality(cams: list[Candidate], pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not cams:
        return np.zeros(len(pts)), np.zeros(len(pts), dtype=int), np.zeros(len(pts))
    masks = np.vstack([visible_mask(c, pts) for c in cams])
    counts = masks.sum(axis=0)
    angles = best_pair_angles(cams, pts, masks)

    # Partial reward for a single visible camera makes beam search stable while
    # building a layout; final layouts still need >=2 for high score.
    q = np.zeros(len(pts), dtype=np.float64)
    q[counts == 1] = 0.10
    multi = counts >= 2
    angle_q = np.clip(angles / 60.0, 0.0, 1.0)
    count_q = 1.0 + 0.12 * np.clip(counts - 2, 0, 3)
    q[multi] = np.clip(angle_q[multi] * count_q[multi], 0.0, 1.25)
    return q, counts, angles


def load_target_points() -> tuple[np.ndarray, list[dict]]:
    hpath = PROJECTOR_DIR / "homography.json"
    bounds = wall_bounds_from_homography(hpath)
    if bounds is None:
        raise RuntimeError(f"No wall_mm calibration points found in {hpath}")

    rects = target_grid_rectangles(
        u_min=bounds.u_min,
        u_max=bounds.u_max,
        v_min=bounds.v_min,
        v_max=bounds.v_max,
    )
    pts: list[list[float]] = []
    meta: list[dict] = []
    for r in rects:
        us = [r.u_min, (r.u_min + r.u_max) / 2.0, r.u_max]
        vs = [r.v_min, (r.v_min + r.v_max) / 2.0, r.v_max]
        for u in us:
            for v in vs:
                pts.append([SOUTH_X, u, v])
                meta.append({"label": r.label, "u": u, "v": v})
    return np.array(pts, dtype=np.float64), meta


def sample_bounce_points() -> np.ndarray:
    xs = np.linspace(5600.0, SOUTH_X, 5)
    ys = np.linspace(600.0, 2630.0, 7)
    zs = np.array([120.0, 250.0, 400.0])
    return np.array(list(itertools.product(xs, ys, zs)), dtype=np.float64)


def sample_pose_points() -> np.ndarray:
    standing = list(itertools.product(
        [1700.0, 3000.0, 4300.0, 5400.0],
        [650.0, 1525.0, 2400.0],
        [350.0, 900.0, 1500.0, 2100.0],
    ))
    pushups = list(itertools.product(
        [2200.0, 3300.0, 4400.0, 5400.0],
        [700.0, 1525.0, 2350.0],
        [120.0, 300.0, 550.0],
    ))
    return np.array(standing + pushups, dtype=np.float64)


def sample_play_volume(step: float) -> np.ndarray:
    xs = np.arange(0.0, SOUTH_X + 1.0, step)
    ys = np.arange(0.0, ARENA[1] + 1.0, step)
    zs = np.arange(0.0, 2200.0 + 1.0, step)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    return np.stack([X, Y, Z], axis=-1).reshape(-1, 3)


def make_candidates() -> dict[str, list[Candidate]]:
    roles: dict[str, list[Candidate]] = {}

    def add(role: str, pos: tuple[float, float, float], look: tuple[float, float, float]):
        roles.setdefault(role, []).append(
            Candidate(role=role, name=f"{role}_{len(roles.get(role, [])):03d}", pos=pos, look_at=look)
        )

    # Two north-wall cameras: one high, one mid/high. Both can see the real
    # projector target cells face-on without being coplanar with the south wall.
    for y in np.arange(450.0, 2651.0, 275.0):
        for z in [1650.0, 2000.0, 2350.0, 2600.0]:
            add("north_wall", (80.0, y, z), (SOUTH_X, 1525.0, 1100.0))

    # South camera: kept for ball approach and pose depth; it is not expected to
    # score the wall directly because it is close to the target plane.
    for y in np.arange(650.0, 2451.0, 300.0):
        for z in [1950.0, 2250.0, 2500.0]:
            add("south_wall", (6150.0, y, z), (2200.0, 1525.0, 950.0))

    # Low side cameras for feet, push-ups, squats, and low ball flight.
    for x in np.arange(2100.0, 5401.0, 300.0):
        for z in [350.0, 550.0, 800.0, 1050.0]:
            add("east_low", (x, 70.0, z), (4400.0, 1525.0, 850.0))
            add("west_low", (x, 2980.0, z), (4400.0, 1525.0, 850.0))

    # Dedicated bounce camera can live on either side near the south end.
    for side, y in [("E", 70.0), ("W", 2980.0)]:
        for x in np.arange(4500.0, 5701.0, 300.0):
            for z in [250.0, 400.0, 650.0, 900.0]:
                role = f"bounce_{side}"
                add(role, (x, y, z), (6120.0, 1525.0, 300.0))

    return roles


def score_layout(
    cams: list[Candidate],
    target_pts: np.ndarray,
    bounce_pts: np.ndarray,
    pose_pts: np.ndarray,
    play_pts: np.ndarray | None,
) -> ScoreBreakdown:
    target_q, target_counts, target_angles = point_quality(cams, target_pts)
    bounce_q, bounce_counts, bounce_angles = point_quality(cams, bounce_pts)
    pose_q, _, _ = point_quality(cams, pose_pts)
    if play_pts is None:
        play_counts = np.zeros(1, dtype=int)
        play_angles = np.zeros(1, dtype=np.float64)
    else:
        _, play_counts, play_angles = point_quality(cams, play_pts)

    target_mean = float(target_q.mean())
    target_min = float(target_q.min())
    bounce_mean = float(bounce_q.mean())
    pose_mean = float(pose_q.mean())

    play_ge2 = float(np.mean(play_counts >= 2) * 100.0)
    play_ge3 = float(np.mean(play_counts >= 3) * 100.0)
    play_angle45 = float(np.mean(play_angles >= 45.0) * 100.0)
    bounce_ge2 = float(np.mean(bounce_counts >= 2) * 100.0)
    bounce_angle45 = float(np.mean(bounce_angles >= 45.0) * 100.0)

    # Penalize layouts where any target samples are not strongly triangulable.
    target_hard_fail = float(np.mean((target_counts < 2) | (target_angles < 30.0)))
    bounce_hard_fail = float(np.mean((bounce_counts < 2) | (bounce_angles < 30.0)))

    total = (
        4.0 * target_mean
        + 1.4 * target_min
        + 2.0 * bounce_mean
        + 1.5 * pose_mean
        - 2.0 * target_hard_fail
        - 1.0 * bounce_hard_fail
    )
    if play_pts is not None:
        total += 0.010 * play_ge3 + 0.006 * play_angle45

    # Small preference for physical spread: avoid two cameras almost stacked.
    for a, b in itertools.combinations(cams, 2):
        d = np.linalg.norm(np.array(a.pos) - np.array(b.pos))
        if d < 550.0:
            total -= (550.0 - d) / 550.0

    return ScoreBreakdown(
        total=float(total),
        target_mean=target_mean,
        target_min=target_min,
        bounce_mean=bounce_mean,
        pose_mean=pose_mean,
        play_ge2_pct=play_ge2,
        play_ge3_pct=play_ge3,
        play_angle45_pct=play_angle45,
        bounce_ge2_pct=bounce_ge2,
        bounce_angle45_pct=bounce_angle45,
    )


def search(args) -> tuple[list[Candidate], ScoreBreakdown, list[tuple[ScoreBreakdown, list[Candidate]]]]:
    target_pts, _target_meta = load_target_points()
    bounce_pts = sample_bounce_points()
    pose_pts = sample_pose_points()

    roles = make_candidates()
    role_order = [
        "north_wall",
        "north_wall",
        "south_wall",
        "east_low",
        "west_low",
        "bounce_E",
        "bounce_W",
    ]
    # The last two roles are alternatives; choose exactly one bounce role by
    # expanding both pools into a single final role.
    roles["bounce_any"] = roles["bounce_E"] + roles["bounce_W"]
    role_order = ["north_wall", "north_wall", "south_wall", "east_low", "west_low", "bounce_any"]

    beam: list[tuple[ScoreBreakdown, list[Candidate]]] = [
        (ScoreBreakdown(0, 0, 0, 0, 0, 0, 0, 0, 0, 0), [])
    ]
    for role_idx, role in enumerate(role_order, start=1):
        next_beam: list[tuple[ScoreBreakdown, list[Candidate]]] = []
        for _score, partial in beam:
            used_names = {c.name for c in partial}
            for cand in roles[role]:
                if cand.name in used_names:
                    continue
                if any(np.linalg.norm(np.array(cand.pos) - np.array(c.pos)) < 350.0 for c in partial):
                    continue
                cams = partial + [cand]
                score = score_layout(cams, target_pts, bounce_pts, pose_pts, None)
                next_beam.append((score, cams))
        next_beam.sort(key=lambda item: item[0].total, reverse=True)
        beam = next_beam[: args.beam]
        print(
            f"[search] role {role_idx}/6 {role}: "
            f"kept {len(beam)} layouts; best={beam[0][0].total:.4f}",
            flush=True,
        )

    play_pts = sample_play_volume(args.step)
    rescored = [
        (score_layout(cams, target_pts, bounce_pts, pose_pts, play_pts), cams)
        for _score, cams in beam[: max(args.top, 100)]
    ]
    rescored.sort(key=lambda item: item[0].total, reverse=True)
    best_score, best_cams = rescored[0]
    return best_cams, best_score, rescored[: args.top]


def write_outputs(best_cams: list[Candidate], best_score: ScoreBreakdown, top: list[tuple[ScoreBreakdown, list[Candidate]]]):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "arena_mm": ARENA.tolist(),
        "score": asdict(best_score),
        "cameras": [asdict(c) for c in best_cams],
    }
    (OUT_DIR / "optimized_camera_layout.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with (OUT_DIR / "optimized_camera_layout.csv").open("w", newline="", encoding="utf-8") as fp:
        wr = csv.writer(fp)
        wr.writerow(["rank", "score", "role", "name", "x", "y", "z", "look_x", "look_y", "look_z"])
        for rank, (score, cams) in enumerate(top, start=1):
            for c in cams:
                wr.writerow([rank, f"{score.total:.6f}", c.role, c.name, *c.pos, *c.look_at])


def draw_outputs(cams: list[Candidate], score: ScoreBreakdown, args):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target_pts, _ = load_target_points()
    bounce_pts = sample_bounce_points()
    play_pts = sample_play_volume(args.step)

    # Top-down: best pair angle at Z=900mm.
    xs = np.arange(0.0, SOUTH_X + 1.0, args.step)
    ys = np.arange(0.0, ARENA[1] + 1.0, args.step)
    z = np.array([900.0])
    X, Y, Z = np.meshgrid(xs, ys, z, indexing="ij")
    pts = np.stack([X, Y, Z], axis=-1).reshape(-1, 3)
    masks = np.vstack([visible_mask(c, pts) for c in cams])
    counts = masks.sum(axis=0).reshape(len(xs), len(ys))
    angles = best_pair_angles(cams, pts, masks).reshape(len(xs), len(ys))
    gx = pts[:, 0].reshape(len(xs), len(ys))
    gy = pts[:, 1].reshape(len(xs), len(ys))

    fig, ax = plt.subplots(figsize=(9, 6))
    im = ax.pcolormesh(gy, gx, angles, cmap="magma", shading="auto", vmin=0, vmax=90)
    ax.contour(gy, gx, counts, levels=[2.0, 3.0], colors=["white", "cyan"], linewidths=[0.8, 1.0])
    ax.invert_yaxis()
    ax.set_xlabel("Y East(0) -> West (mm)")
    ax.set_ylabel("X North(0) -> South wall (mm)")
    ax.set_title(f"Optimized layout: best pair angle @ Z=900mm (score={score.total:.2f})")
    for c in cams:
        ax.scatter(c.pos[1], c.pos[0], s=70, edgecolor="white", label=c.role)
        ax.text(c.pos[1] + 35, c.pos[0] + 35, c.role, color="white", fontsize=7)
    fig.colorbar(im, ax=ax, label="best visible pair angle (deg)")
    fig.savefig(OUT_DIR / "optimized_layout_topdown.png", dpi=140, bbox_inches="tight")

    # 3D plot: arena, target samples, bounce samples, frustum center rays.
    fig3 = plt.figure(figsize=(12, 8))
    ax3 = fig3.add_subplot(111, projection="3d")
    corners = np.array([
        [0, 0, 0], [SOUTH_X, 0, 0], [SOUTH_X, ARENA[1], 0], [0, ARENA[1], 0],
        [0, 0, ARENA[2]], [SOUTH_X, 0, ARENA[2]], [SOUTH_X, ARENA[1], ARENA[2]], [0, ARENA[1], ARENA[2]],
    ])
    for i, j in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7)]:
        ax3.plot(*zip(corners[i], corners[j]), color="black", lw=1.0)
    ax3.scatter(target_pts[:, 0], target_pts[:, 1], target_pts[:, 2], s=20, color="lime", label="3x3 target samples")
    ax3.scatter(bounce_pts[:, 0], bounce_pts[:, 1], bounce_pts[:, 2], s=8, color="red", alpha=0.35, label="bounce samples")
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for idx, c in enumerate(cams):
        pos = np.array(c.pos)
        look = np.array(c.look_at)
        ax3.scatter(*pos, s=60, color=colors[idx % len(colors)])
        ax3.text(pos[0], pos[1], pos[2] + 80, c.role, color=colors[idx % len(colors)], fontsize=8)
        end = pos + (look - pos) / np.linalg.norm(look - pos) * 1100
        ax3.plot(*zip(pos, end), color=colors[idx % len(colors)], lw=2.0)
    ax3.set_xlabel("X North->South (mm)")
    ax3.set_ylabel("Y East->West (mm)")
    ax3.set_zlabel("Z up (mm)")
    ax3.set_xlim(-200, SOUTH_X + 200)
    ax3.set_ylim(-200, ARENA[1] + 200)
    ax3.set_zlim(0, ARENA[2])
    ax3.set_box_aspect(tuple(ARENA))
    ax3.view_init(elev=30, azim=-58)
    ax3.legend(loc="upper left")
    ax3.set_title("Optimized 6-camera layout: target wall + bounce geometry")
    fig3.savefig(OUT_DIR / "optimized_layout_3d.png", dpi=140, bbox_inches="tight")

    if args.show:
        plt.show()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--beam", type=int, default=600, help="Beam width retained after each role")
    ap.add_argument("--top", type=int, default=25, help="How many top layouts to write to CSV")
    ap.add_argument("--step", type=float, default=200.0, help="Play-volume voxel step in mm")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    best_cams, best_score, top = search(args)
    write_outputs(best_cams, best_score, top)
    draw_outputs(best_cams, best_score, args)

    target_pts, meta = load_target_points()
    print("\n=== Real projector target allocation ===")
    print(f"  samples: {len(target_pts)} from 9 grid cells")
    print(f"  wall hit U range: {target_pts[:,1].min():.0f}..{target_pts[:,1].max():.0f} mm")
    print(f"  wall hit V range: {target_pts[:,2].min():.0f}..{target_pts[:,2].max():.0f} mm")

    print("\n=== Best layout ===")
    print(json.dumps(asdict(best_score), indent=2))
    for c in best_cams:
        print(
            f"  {c.role:10s} pos=({c.pos[0]:.0f},{c.pos[1]:.0f},{c.pos[2]:.0f}) "
            f"look=({c.look_at[0]:.0f},{c.look_at[1]:.0f},{c.look_at[2]:.0f})"
        )
    print(f"\nWrote: {OUT_DIR / 'optimized_camera_layout.json'}")
    print(f"Wrote: {OUT_DIR / 'optimized_camera_layout.csv'}")
    print(f"Wrote: {OUT_DIR / 'optimized_layout_topdown.png'}")
    print(f"Wrote: {OUT_DIR / 'optimized_layout_3d.png'}")


if __name__ == "__main__":
    main()
