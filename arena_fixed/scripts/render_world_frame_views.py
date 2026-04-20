#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def load_live_module(repo_root: Path):
    mod_path = repo_root / "garage_lab_combined" / "scripts" / "live_4cam_arena_view.py"
    spec = importlib.util.spec_from_file_location("live_4cam_arena_view", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from: {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Render arena world-coordinate snapshots using the exact draw logic of live_4cam_arena_view."
    )
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--extrinsics", default="arena_fixed/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--dimensions", default="arena_fixed/cal/extrinsics/Dimensions_fixed.txt")
    ap.add_argument("--launcher-x-mm", type=float, default=600.0)
    ap.add_argument("--launcher-y-mm", type=float, default=1560.0)
    ap.add_argument("--launcher-z-mm", type=float, default=500.0)
    ap.add_argument(
        "--invert-y-axis-display",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Match run_live_visual_invert_quality.sh default (ON).",
    )
    ap.add_argument(
        "--world-y-mirror",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Should stay OFF to match run_live_visual_invert_quality.sh.",
    )
    ap.add_argument("--out", default="arena_fixed/output/world_frame_views_live_quality.png")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    mod = load_live_module(repo_root)

    extr = mod.load_extrinsics(str(repo_root / args.extrinsics))
    dims, tags = mod.parse_dimensions(str(repo_root / args.dimensions))

    out = repo_root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    views = [
        ("Iso", 24, 135),
        ("Front", 10, -90),
        ("Right", 10, 0),
        ("Back", 10, 90),
        ("Left", 10, 180),
        ("Top", 88, -90),
    ]

    fig = plt.figure(figsize=(18, 10), facecolor="#f7f7f7")
    blm_pt = np.array([args.launcher_x_mm, args.launcher_y_mm, args.launcher_z_mm], dtype=np.float32)

    for i, (name, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(2, 3, i, projection="3d")
        mod.draw_live_scene(
            ax=ax,
            dims=dims,
            tags=tags,
            extr=extr,
            ball_pt=blm_pt,
            ball_traj=[],
            joints=None,
            frame_idx=0,
            fps_est=0.0,
            world_y_mirror=bool(args.world_y_mirror),
            invert_y_axis_display=bool(args.invert_y_axis_display),
            draw_global_axes_flag=True,
            global_axis_len_mm=900.0,
            view_elev=elev,
            view_azim=azim,
        )
        ax.set_title(name)

    fig.suptitle(
        "World Frame Views (live_visual_invert_quality mode)\n"
        f"BLM point = ({int(args.launcher_x_mm)}, {int(args.launcher_y_mm)}, {int(args.launcher_z_mm)}) mm",
        fontsize=14,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    print(out)


if __name__ == "__main__":
    main()
