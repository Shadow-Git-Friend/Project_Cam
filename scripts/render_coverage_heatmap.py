#!/usr/bin/env python3
"""
render_coverage_heatmap.py — top-down heatmaps of how many cameras see each spot.

Two slices: torso height (Z=1000 mm, standing/squats) and floor height
(Z=400 mm, push-ups). Colour = number of cameras whose frustum contains that
point. Reuses the 6-USB cable-aware cameras + real FOV from coverage_breakdown.py.

Output: scripts/coverage_out/coverage_heatmap_six_usb.png
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from coverage_breakdown import CAMS, in_frustum, ARENA

OUT = Path(__file__).resolve().parent / "coverage_out"
OUT.mkdir(parents=True, exist_ok=True)
STEP = 50.0
NCAM = len(CAMS)


def count_slice(z):
    xs = np.arange(0, ARENA[0] + 1, STEP)
    ys = np.arange(0, ARENA[1] + 1, STEP)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    pts = np.stack([X, Y, np.full_like(X, z)], -1).reshape(-1, 3)
    c = np.zeros(len(pts), int)
    for cam in CAMS:
        c += in_frustum(cam, pts).astype(int)
    return xs, ys, c.reshape(len(xs), len(ys))


def panel(ax, z, title):
    xs, ys, C = count_slice(z)
    Xc, Yc = np.meshgrid(xs, ys, indexing="ij")
    cmap = plt.get_cmap("turbo", NCAM + 1)
    im = ax.pcolormesh(Yc, Xc, C, cmap=cmap, vmin=0, vmax=NCAM, shading="auto")
    # >=2 and >=3 contour lines
    ax.contour(Yc, Xc, C, levels=[1.5, 2.5], colors=["white", "black"],
               linewidths=[1.0, 1.3], linestyles=["--", "-"])
    # cameras + aim arrows
    for name, pos, aim, hf, vf in CAMS:
        ax.scatter(pos[1], pos[0], s=90, color="white", edgecolor="black", zorder=6)
        d = np.array([aim[1]-pos[1], aim[0]-pos[0]], float)
        n = np.linalg.norm(d)
        if n > 1: d = d/n*900
        ax.annotate("", xy=(pos[1]+d[0], pos[0]+d[1]), xytext=(pos[1], pos[0]),
                    arrowprops=dict(arrowstyle="-|>", color="white", lw=1.8))
        ax.annotate(name.replace("cam", ""), (pos[1], pos[0]),
                    textcoords="offset points", xytext=(6, 6),
                    fontsize=7, color="white", weight="bold")
    # south wall + bounce strip
    ax.axhline(ARENA[0], color="red", lw=3, alpha=0.6)
    ax.add_patch(plt.Rectangle((0, 5600), ARENA[1], ARENA[0]-5600,
                               fill=False, ec="red", ls=":", lw=1.2))
    ax.text(ARENA[1]/2, ARENA[0]+170, "SOUTH wall (goal)", color="red",
            ha="center", fontsize=9, weight="bold")
    ax.text(ARENA[1]/2, -150, "NORTH", ha="center", fontsize=9)
    ax.set_xlim(-200, ARENA[1]+200); ax.set_ylim(-300, ARENA[0]+320)
    ax.invert_yaxis(); ax.set_aspect("equal")
    ax.set_title(title, fontsize=11, weight="bold")
    ax.set_xlabel("Y  East → West (mm)"); ax.set_ylabel("X  North → South (mm)")
    return im


# slices from floor to head height, each labelled with what lives at that height
SLICES = [
    (200.0,  "Z = 200 mm  (ankles / ball on floor)"),
    (400.0,  "Z = 400 mm  (push-up body)"),
    (700.0,  "Z = 700 mm  (knees / hips, low squat)"),
    (1000.0, "Z = 1000 mm  (torso, standing)"),
    (1500.0, "Z = 1500 mm  (chest / shoulders)"),
    (2000.0, "Z = 2000 mm  (head / jump / high ball)"),
]

fig, axes = plt.subplots(2, 3, figsize=(20, 13))
im = None
for ax, (z, title) in zip(axes.ravel(), SLICES):
    im = panel(ax, z, title)
cbar = fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, ticks=range(NCAM + 1))
cbar.set_label("# cameras seeing this spot")
fig.suptitle("Camera coverage at different heights — 6-USB cable-aware layout "
             "(white dashed = ≥2 cams,  black = ≥3 cams)", fontsize=14, weight="bold")
out = OUT / "coverage_heatmap_slices_six_usb.png"
fig.savefig(out, dpi=130, bbox_inches="tight")
print("saved:", out)
