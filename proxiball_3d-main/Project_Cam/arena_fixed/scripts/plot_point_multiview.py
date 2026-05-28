#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def parse_dims(dim_file: Path) -> tuple[float, float, float]:
    txt = dim_file.read_text(encoding="utf-8", errors="ignore")
    x = y = z = 0.0
    import re

    m = re.search(r"X\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*cm", txt)
    if m:
        x = float(m.group(1)) * 10.0
    m = re.search(r"Y\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*cm", txt)
    if m:
        y = float(m.group(1)) * 10.0
    m = re.search(r"Z\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*cm", txt)
    if m:
        z = float(m.group(1)) * 10.0
    return x, y, z


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot one arena point from multiple 3D viewpoints.")
    ap.add_argument("--dimensions", default="arena_fixed/cal/extrinsics/Dimensions_fixed.txt")
    ap.add_argument("--x-mm", type=float, required=True)
    ap.add_argument("--y-mm", type=float, required=True)
    ap.add_argument("--z-mm", type=float, required=True)
    ap.add_argument("--out", default="arena_fixed/output/point_multiview.png")
    args = ap.parse_args()

    x_max, y_max, z_max = parse_dims(Path(args.dimensions))
    pt = np.array([args.x_mm, args.y_mm, args.z_mm], dtype=float)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(16, 10))
    views = [
        ("Iso", 22, -60),
        ("Front (North)", 10, -90),
        ("Right (East)", 10, 0),
        ("Back (South)", 10, 90),
        ("Left (West)", 10, 180),
        ("Top", 88, -90),
    ]
    corners = np.array(
        [
            [0, 0, 0],
            [x_max, 0, 0],
            [x_max, y_max, 0],
            [0, y_max, 0],
            [0, 0, z_max],
            [x_max, 0, z_max],
            [x_max, y_max, z_max],
            [0, y_max, z_max],
        ],
        dtype=float,
    )
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]

    for i, (title, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(2, 3, i, projection="3d")
        for a, b in edges:
            ax.plot(
                [corners[a, 0], corners[b, 0]],
                [corners[a, 1], corners[b, 1]],
                [corners[a, 2], corners[b, 2]],
                color="gray",
                lw=1,
            )

        ax.scatter([pt[0]], [pt[1]], [pt[2]], c="crimson", s=70)
        ax.text(pt[0], pt[1], pt[2] + 40, f"P({int(pt[0])},{int(pt[1])},{int(pt[2])})", color="crimson", fontsize=8)
        ax.plot([pt[0], pt[0]], [pt[1], pt[1]], [0, pt[2]], "k--", lw=1)
        ax.plot([0, pt[0]], [pt[1], pt[1]], [0, 0], "k:", lw=0.8)
        ax.plot([pt[0], pt[0]], [0, pt[1]], [0, 0], "k:", lw=0.8)

        ax.set_xlim(0, x_max)
        ax.set_ylim(0, y_max)
        ax.set_zlim(0, z_max)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.set_title(title)
        ax.view_init(elev=elev, azim=azim)

    fig.suptitle(f"Arena point debug: ({int(pt[0])}, {int(pt[1])}, {int(pt[2])}) mm", fontsize=14)
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    print(out)


if __name__ == "__main__":
    main()
