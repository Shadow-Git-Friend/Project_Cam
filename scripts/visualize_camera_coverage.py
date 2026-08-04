#!/usr/bin/env python3
"""
visualize_camera_coverage.py — arena camera-coverage simulator for Project_Cam.

Draws each camera's FOV frustum in 3D over the garage arena and computes how many
cameras see every point in the play volume (>=1 / >=2 / >=3), with a dedicated
report for the floor-near-south-wall BOUNCE strip. It also plots a top-down
triangulation-quality heatmap based on the best visible camera-pair angle.

Use it to validate the planned 6-camera layout BEFORE drilling any mounts.

Real lens FOV is read from the intrinsics JSONs when available
(`Remounted_West_East/cal/intrinsics/<cam>_intrinsics.json`). New cameras use a
representative machine-vision FOV until you have their datasheet.

Standalone — does NOT import or modify any protected pipeline function.

Examples
--------
  ./venv/bin/python scripts/visualize_camera_coverage.py --layout six
  ./venv/bin/python scripts/visualize_camera_coverage.py --layout four --show
  ./venv/bin/python scripts/visualize_camera_coverage.py --layout six_manual
  ./venv/bin/python scripts/visualize_camera_coverage.py --layout six_claude
  ./venv/bin/python scripts/visualize_camera_coverage.py --layout six_usb_cable_aware
  ./venv/bin/python scripts/visualize_camera_coverage.py --layout six --step-mm 75
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Headless-safe: pick Agg unless the user asks to display interactively.
import matplotlib
_ARGS_SHOW = "--show" in __import__("sys").argv
if not _ARGS_SHOW:
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# ── Arena (mm) — authoritative dims from Dimensions_fixed.txt ──────────────────
ARENA = np.array([6230.0, 3050.0, 2950.0])   # X=length(N->S), Y=width(E->W), Z=up
PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTRINSICS_DIR = PROJECT_ROOT / "Remounted_West_East" / "cal" / "intrinsics"


@dataclass
class Cam:
    name: str
    pos: np.ndarray            # (3,) mm
    look_at: np.ndarray        # (3,) mm
    hfov_deg: float = 82.0
    vfov_deg: float = 52.0
    near_mm: float = 150.0
    far_mm: float = 7000.0
    color: str = "C0"
    role: str = ""


def fov_from_intrinsics(cam_name: str, dh: float = 82.0, dv: float = 52.0):
    """Real HFOV/VFOV from a camera's K, or defaults for cameras not yet bought."""
    p = INTRINSICS_DIR / f"{cam_name}_intrinsics.json"
    try:
        d = json.loads(p.read_text())
        K = d["camera_matrix"]
        w, h = float(d["image_width"]), float(d["image_height"])
        fx, fy = float(K[0][0]), float(K[1][1])
        return (2 * math.degrees(math.atan(w / 2 / fx)),
                2 * math.degrees(math.atan(h / 2 / fy)))
    except Exception:
        return dh, dv


def basis(cam: Cam):
    """Right/up/forward unit vectors for a camera looking at `look_at`."""
    up_world = np.array([0.0, 0.0, 1.0])
    fwd = cam.look_at - cam.pos
    fwd = fwd / np.linalg.norm(fwd)
    right = np.cross(fwd, up_world)
    if np.linalg.norm(right) < 1e-6:           # looking straight up/down
        up_world = np.array([0.0, 1.0, 0.0])
        right = np.cross(fwd, up_world)
    right = right / np.linalg.norm(right)
    up = np.cross(right, fwd)
    up = up / np.linalg.norm(up)
    return right, up, fwd


def in_frustum(cam: Cam, pts: np.ndarray) -> np.ndarray:
    """Boolean mask: which world points fall inside this camera's view frustum."""
    right, up, fwd = basis(cam)
    rel = pts - cam.pos[None, :]
    xc = rel @ right
    yc = rel @ up
    zc = rel @ fwd                              # depth along optical axis
    th = math.tan(math.radians(cam.hfov_deg) / 2.0)
    tv = math.tan(math.radians(cam.vfov_deg) / 2.0)
    return ((zc >= cam.near_mm) & (zc <= cam.far_mm)
            & (np.abs(xc) <= zc * th) & (np.abs(yc) <= zc * tv))


def frustum_corners(cam: Cam):
    right, up, fwd = basis(cam)
    th = math.tan(math.radians(cam.hfov_deg) / 2.0)
    tv = math.tan(math.radians(cam.vfov_deg) / 2.0)

    def plane(depth):
        c = cam.pos + fwd * depth
        hw, hh = th * depth, tv * depth
        return [c - right * hw - up * hh, c + right * hw - up * hh,
                c + right * hw + up * hh, c - right * hw + up * hh]

    return np.array(plane(cam.near_mm) + plane(cam.far_mm))


def draw_box(ax, p0, p1, **kw):
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    c = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    for i, j in [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                 (0, 4), (1, 5), (2, 6), (3, 7)]:
        ax.plot(*zip(c[i], c[j]), **kw)


def draw_frustum(ax, cam: Cam):
    c = cam.pos
    cn = frustum_corners(cam)
    near, far = cn[:4], cn[4:]
    for quad in (near, far):
        q = np.vstack([quad, quad[0]])
        ax.plot(q[:, 0], q[:, 1], q[:, 2], color=cam.color, lw=0.8, alpha=0.7)
    for i in range(4):
        ax.plot(*zip(c, far[i]), color=cam.color, lw=0.6, alpha=0.5)
    ax.scatter(*c, color=cam.color, s=45)
    ax.text(c[0], c[1], c[2] + 90, cam.name, color=cam.color, fontsize=8)
    # short arrow showing where it points
    _, _, fwd = basis(cam)
    a = c + fwd * 900
    ax.plot(*zip(c, a), color=cam.color, lw=2.0)


def best_visible_pair_angles(cams: list[Cam], pts: np.ndarray) -> np.ndarray:
    """Best triangulation angle among visible camera pairs at each point."""
    masks = [in_frustum(c, pts) for c in cams]
    best = np.zeros(len(pts), dtype=np.float64)
    for i, a in enumerate(cams):
        for j in range(i + 1, len(cams)):
            b = cams[j]
            both = masks[i] & masks[j]
            if not np.any(both):
                continue
            va = a.pos[None, :] - pts[both]
            vb = b.pos[None, :] - pts[both]
            va /= np.linalg.norm(va, axis=1)[:, None]
            vb /= np.linalg.norm(vb, axis=1)[:, None]
            dots = np.clip(np.sum(va * vb, axis=1), -1.0, 1.0)
            ang = np.degrees(np.arccos(dots))
            ang = np.minimum(ang, 180.0 - ang)
            best[both] = np.maximum(best[both], ang)
    return best


# ── Layouts ────────────────────────────────────────────────────────────────
def layout_four():
    return [
        Cam("camNorth", np.array([50, 1100, 2260]),  np.array([6230, 1525, 1200]),
            color="C0", role="high N — face-on wall + body"),
        Cam("camSouth", np.array([6180, 1530, 2270]), np.array([0, 1525, 1200]),
            color="C1", role="high S — ball approach + depth"),
        Cam("camEast",  np.array([1620, 50, 450]),    np.array([4000, 1525, 800]),
            color="C2", role="low E — legs/feet + low flight"),
        Cam("camWest",  np.array([1600, 2970, 450]),  np.array([4000, 1525, 800]),
            color="C3", role="low W — legs/feet + low flight"),
    ]


def layout_six():
    """Optimized 6-camera layout for the garage.

    Generated by scripts/optimize_camera_geometry.py using the real projector
    target allocation from homography.json.
    """
    return [
        Cam("camNorth_A", np.array([80, 450, 1650]), np.array([6230, 1525, 1100]),
            color="C0", role="N-east/mid — wall target + body"),
        Cam("camNorth_B", np.array([80, 2650, 2350]), np.array([6230, 1525, 1100]),
            color="C4", role="N-west/high — second wall view"),
        Cam("camSouth", np.array([6150, 2450, 2500]), np.array([2200, 1525, 950]),
            color="C1", role="S-west/high — approach + pose depth"),
        Cam("camEast_low", np.array([3300, 70, 350]), np.array([4400, 1525, 850]),
            color="C2", role="E-mid/low — push-up/feet + low ball"),
        Cam("camWest_low", np.array([3300, 2980, 1050]), np.array([4400, 1525, 850]),
            color="C3", role="W-mid/mid — side body + low ball"),
        Cam("camBounce", np.array([4500, 70, 250]), np.array([6120, 1525, 300]),
            color="C5", role="low S-east — wall/floor bounce strip"),
    ]


def layout_six_manual():
    """Previous hand-picked 6-camera layout retained for comparison."""
    return [
        Cam("camNorth_A", np.array([80, 750, 2350]), np.array([6230, 1525, 1100]),
            color="C0", role="high N-east — wall + full body"),
        Cam("camNorth_B", np.array([80, 2300, 1650]), np.array([6230, 1525, 1100]),
            color="C4", role="mid N-west — second wall view"),
        Cam("camSouth", np.array([6180, 1530, 2350]), np.array([1800, 1525, 1000]),
            color="C1", role="high S — approach + pose depth"),
        Cam("camEast_low", np.array([3000, 70, 550]), np.array([4300, 1525, 850]),
            color="C2", role="low E-mid — feet/push-ups + low ball"),
        Cam("camWest_low", np.array([3000, 2980, 550]), np.array([4300, 1525, 850]),
            color="C3", role="low W-mid — feet/push-ups + low ball"),
        Cam("camBounce", np.array([5050, 80, 350]), np.array([6120, 1525, 300]),
            color="C5", role="low S-east — wall/floor bounce strip"),
    ]


def layout_six_claude():
    """Older Claude-style 6-camera layout retained for comparison."""
    cams = layout_four()
    cams += [
        Cam("cam5_WallB", np.array([300, 2300, 1100]), np.array([6230, 1525, 1200]),
            color="C4", role="mid near-N — wall stereo w/ camNorth"),
        Cam("cam6_Bounce", np.array([4800, 2970, 300]), np.array([6100, 1500, 250]),
            color="C5", role="low near-S — bounce strip"),
    ]
    return cams


def layout_six_usb_cable_aware():
    """Audited cable-aware layout for the current 6 USB-webcam setup.

    This is the practical remount plan for 4x long-cable 1080P USB cameras plus
    2x short-cable Logitech C920 cameras. It prioritizes BLM aiming, whole-body
    pose, squats, push-ups, and soft/projector target testing. It is not a
    replacement for hardware-synced global-shutter cameras for fast-ball work.
    """
    c920_hfov, c920_vfov = 70.0, 43.0
    usb_hfov, usb_vfov = 82.0, 52.0
    return [
        Cam("camNorth_EastHigh", np.array([80, 550, 2200]), np.array([3600, 1500, 1100]),
            hfov_deg=usb_hfov, vfov_deg=usb_vfov, color="C0",
            role="1080P USB long — high N/E: BLM corridor + whole body"),
        Cam("camNorth_WestHigh", np.array([80, 2500, 2200]), np.array([3600, 1500, 1100]),
            hfov_deg=usb_hfov, vfov_deg=usb_vfov, color="C4",
            role="1080P USB long — high N/W: second high angle + redundancy"),
        Cam("camEast_Low", np.array([3100, 80, 450]), np.array([3400, 1500, 450]),
            hfov_deg=c920_hfov, vfov_deg=c920_vfov, color="C2",
            role="Logitech C920 short — low E: push-ups, feet, squat side view"),
        Cam("camWest_Low", np.array([3100, 2970, 450]), np.array([3400, 1500, 450]),
            hfov_deg=c920_hfov, vfov_deg=c920_vfov, color="C3",
            role="Logitech C920 short — low W: mirror low side + occlusion"),
        Cam("camSouth_High", np.array([6150, 2300, 2300]), np.array([2800, 1500, 1000]),
            hfov_deg=usb_hfov, vfov_deg=usb_vfov, color="C1",
            role="1080P USB long — high S: reverse body view + ball approach"),
        Cam("camBounce_TargetLow", np.array([5000, 80, 350]), np.array([6230, 1600, 850]),
            hfov_deg=usb_hfov, vfov_deg=usb_vfov, color="C5",
            role="1080P USB long — low target: bounce + projector region"),
    ]


def apply_real_fov(cams):
    for c in cams:
        if "c920" in c.role.lower():
            continue
        base = c.name.split("_")[0]            # camNorth_A -> camNorth
        if not (INTRINSICS_DIR / f"{base}_intrinsics.json").exists():
            continue
        h, v = fov_from_intrinsics(base, c.hfov_deg, c.vfov_deg)
        c.hfov_deg, c.vfov_deg = h, v
    return cams


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    layouts = {
        "four": layout_four,
        "six": layout_six,
        "six_final": layout_six,
        "six_manual": layout_six_manual,
        "six_claude": layout_six_claude,
        "six_usb": layout_six_usb_cable_aware,
        "six_usb_cable": layout_six_usb_cable_aware,
        "six_usb_cable_aware": layout_six_usb_cable_aware,
    }
    ap.add_argument("--layout", choices=sorted(layouts), default="six")
    ap.add_argument("--step-mm", type=float, default=100.0)
    ap.add_argument("--bounce-x-min", type=float, default=5600.0,
                    help="south-wall bounce strip starts at this X (mm)")
    ap.add_argument("--bounce-z-max", type=float, default=400.0)
    ap.add_argument("--play-z-max", type=float, default=2200.0,
                    help="ignore voxels above this Z for the body-coverage stat")
    ap.add_argument("--show", action="store_true", help="open interactive windows")
    ap.add_argument("--out-dir", default=str(PROJECT_ROOT / "scripts" / "coverage_out"))
    args = ap.parse_args()

    cams = layouts[args.layout]()
    cams = apply_real_fov(cams)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Voxel grid over the arena.
    xs = np.arange(0, ARENA[0] + 1, args.step_mm)
    ys = np.arange(0, ARENA[1] + 1, args.step_mm)
    zs = np.arange(0, ARENA[2] + 1, args.step_mm)
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    pts = np.stack([X, Y, Z], -1).reshape(-1, 3)

    counts = np.zeros(len(pts), dtype=int)
    for c in cams:
        counts += in_frustum(c, pts).astype(int)
    best_angles = best_visible_pair_angles(cams, pts)

    body = pts[:, 2] <= args.play_z_max
    bounce = (pts[:, 0] >= args.bounce_x_min) & (pts[:, 2] <= args.bounce_z_max)

    def pct(mask, k):
        n = int(mask.sum())
        return 100.0 * int(((counts >= k) & mask).sum()) / max(n, 1)

    def angle_pct(mask, deg):
        n = int(mask.sum())
        return 100.0 * int(((best_angles >= deg) & mask).sum()) / max(n, 1)

    print(f"\n=== Camera coverage — layout '{args.layout}' "
          f"({len(cams)} cams, {args.step_mm:.0f} mm voxels) ===")
    for c in cams:
        print(f"  {c.name:12s} pos={tuple(int(v) for v in c.pos)} "
              f"FOV={c.hfov_deg:.0f}x{c.vfov_deg:.0f}°  {c.role}")
    print(f"\n  PLAY VOLUME (Z<= {args.play_z_max:.0f}mm):")
    print(f"    >=1 cam: {pct(body,1):5.1f}%   >=2 cams: {pct(body,2):5.1f}%"
          f"   >=3 cams: {pct(body,3):5.1f}%")
    print(f"    best pair angle >=30°: {angle_pct(body,30):5.1f}%"
          f"   >=45°: {angle_pct(body,45):5.1f}%")
    print(f"  BOUNCE STRIP (X>= {args.bounce_x_min:.0f}, Z<= {args.bounce_z_max:.0f}):")
    print(f"    >=1 cam: {pct(bounce,1):5.1f}%   >=2 cams: {pct(bounce,2):5.1f}%"
          f"   >=3 cams: {pct(bounce,3):5.1f}%")
    print(f"    best pair angle >=30°: {angle_pct(bounce,30):5.1f}%"
          f"   >=45°: {angle_pct(bounce,45):5.1f}%")
    print("  (>=2 cams everywhere = triangulation works; bounce >=2 = blind-spot fixed)\n")

    # ── 3D frustum plot ───────────────────────────────────────────────────────
    fig = plt.figure(figsize=(13, 9))
    ax = fig.add_subplot(111, projection="3d")
    draw_box(ax, np.zeros(3), ARENA, color="black", lw=1.2)
    draw_box(ax, np.array([args.bounce_x_min, 0, 0]),
             np.array([ARENA[0], ARENA[1], args.bounce_z_max]),
             color="red", lw=1.0, linestyle="--")
    # mark the south (impact/projection) wall
    ax.text(ARENA[0], ARENA[1] / 2, ARENA[2] / 2, "SOUTH WALL\n(impact/grid)",
            color="red", fontsize=8)
    for c in cams:
        draw_frustum(ax, c)
    ge2 = pts[(counts >= 2) & body]
    if len(ge2):
        s = ge2[:: max(1, len(ge2) // 4000)]
        ax.scatter(s[:, 0], s[:, 1], s[:, 2], s=2, alpha=0.12, color="green")
    gap = pts[bounce & (counts < 2)]
    if len(gap):
        s = gap[:: max(1, len(gap) // 2000)]
        ax.scatter(s[:, 0], s[:, 1], s[:, 2], s=10, alpha=0.5, color="red")
    ax.set_xlabel("X  N→S (mm)")
    ax.set_ylabel("Y  E→W (mm)")
    ax.set_zlabel("Z up (mm)")
    ax.set_xlim(-300, ARENA[0] + 300)
    ax.set_ylim(-300, ARENA[1] + 300)
    ax.set_zlim(0, ARENA[2])
    ax.set_box_aspect(tuple(ARENA))
    ax.view_init(elev=32, azim=-58)
    ax.set_title(f"Project_Cam coverage — {args.layout} "
                 f"(green=≥2 cams, red dots=bounce gap)")
    p3d = out / f"coverage_3d_{args.layout}.png"
    fig.savefig(p3d, dpi=130, bbox_inches="tight")

    # ── 2D top-down coverage heatmap at body mid-height ──────────────────────
    zc = float(zs[np.argmin(np.abs(zs - 900))])    # ~0.9 m slice
    sl = np.isclose(pts[:, 2], zc)
    gx = pts[sl][:, 0].reshape(len(xs), len(ys))
    gy = pts[sl][:, 1].reshape(len(xs), len(ys))
    gc = counts[sl].reshape(len(xs), len(ys))
    ga = best_angles[sl].reshape(len(xs), len(ys))
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    im = ax2.pcolormesh(gy, gx, gc, cmap="viridis", shading="auto", vmin=0, vmax=len(cams))
    ax2.invert_yaxis()           # X=0 (North) at top
    ax2.set_xlabel("Y  East(0) → West (mm)")
    ax2.set_ylabel("X  North(0) → South (mm)")
    ax2.set_title(f"Top-down # cameras seeing each spot @ Z={zc:.0f}mm ({args.layout})")
    for c in cams:
        ax2.scatter(c.pos[1], c.pos[0], color=c.color, s=60, edgecolor="white")
        ax2.text(c.pos[1], c.pos[0], "  " + c.name, color="white", fontsize=7)
    fig2.colorbar(im, ax=ax2, label="# cameras")
    p2d = out / f"coverage_topdown_{args.layout}.png"
    fig2.savefig(p2d, dpi=130, bbox_inches="tight")

    # ── 2D top-down triangulation-quality heatmap at body mid-height ─────────
    fig3, ax3 = plt.subplots(figsize=(9, 6))
    im3 = ax3.pcolormesh(gy, gx, ga, cmap="magma", shading="auto", vmin=0, vmax=90)
    ax3.invert_yaxis()
    ax3.set_xlabel("Y  East(0) → West (mm)")
    ax3.set_ylabel("X  North(0) → South (mm)")
    ax3.set_title(f"Top-down best visible pair angle @ Z={zc:.0f}mm ({args.layout})")
    ax3.contour(gy, gx, ga, levels=[30, 45], colors=["white", "cyan"], linewidths=[0.8, 1.0])
    for c in cams:
        ax3.scatter(c.pos[1], c.pos[0], color=c.color, s=60, edgecolor="white")
        ax3.text(c.pos[1], c.pos[0], "  " + c.name, color="white", fontsize=7)
    fig3.colorbar(im3, ax=ax3, label="best camera-pair angle (degrees)")
    pqa = out / f"coverage_quality_topdown_{args.layout}.png"
    fig3.savefig(pqa, dpi=130, bbox_inches="tight")

    # ── Side view: X/Z heights and pointing directions ──────────────────────
    fig4, ax4 = plt.subplots(figsize=(10, 4.8))
    ax4.add_patch(plt.Rectangle((0, 0), ARENA[0], ARENA[2],
                                fill=False, edgecolor="black", linewidth=1.2))
    ax4.axvspan(args.bounce_x_min, ARENA[0], 0, args.bounce_z_max / ARENA[2],
                color="red", alpha=0.08, label="bounce strip")
    for c in cams:
        ax4.scatter(c.pos[0], c.pos[2], color=c.color, s=70, edgecolor="white", zorder=3)
        vec = c.look_at - c.pos
        norm = np.linalg.norm([vec[0], vec[2]])
        if norm > 1e-6:
            ax4.arrow(c.pos[0], c.pos[2], 650 * vec[0] / norm, 650 * vec[2] / norm,
                      color=c.color, width=12, head_width=90, length_includes_head=True, alpha=0.8)
        ax4.text(c.pos[0] + 55, c.pos[2] + 45, c.name, color=c.color, fontsize=8)
    ax4.set_xlim(-200, ARENA[0] + 200)
    ax4.set_ylim(-50, ARENA[2] + 150)
    ax4.set_xlabel("X  North(0) → South wall (mm)")
    ax4.set_ylabel("Z height (mm)")
    ax4.set_title(f"Side view: camera heights and pitch directions ({args.layout})")
    pside = out / f"coverage_side_{args.layout}.png"
    fig4.savefig(pside, dpi=130, bbox_inches="tight")

    print(f"  saved: {p3d}")
    print(f"  saved: {p2d}")
    print(f"  saved: {pqa}")
    print(f"  saved: {pside}")
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
