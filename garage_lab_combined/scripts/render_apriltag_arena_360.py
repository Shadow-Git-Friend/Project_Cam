import argparse
import json
import re
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def parse_dimensions(path):
    dims = {"X": 0.0, "Y": 0.0, "Z": 0.0}
    tags = {}

    with open(path, "r") as f:
        content = f.read()

    m = re.search(r"X\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
    if m:
        dims["X"] = float(m.group(1)) * 10.0
    m = re.search(r"Y\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
    if m:
        dims["Y"] = float(m.group(1)) * 10.0
    m = re.search(r"Z\s*=\s*(\d+(?:\.\d+)?)\s*cm", content)
    if m:
        dims["Z"] = float(m.group(1)) * 10.0

    parts = re.split(r"ID=(\d+):", content)
    for i in range(1, len(parts), 2):
        tag_id = int(parts[i])
        sec = parts[i + 1]
        hits = re.findall(
            r"c\d\s*\(\s*([\d\.]+)\s*,\s*([\d\.]+)\s*,\s*([\d\.]+)\s*\)", sec
        )
        if len(hits) != 4:
            continue
        corners = []
        for x, y, z in hits:
            corners.append([float(x) * 10.0, float(y) * 10.0, float(z) * 10.0])
        tags[tag_id] = np.array(corners, dtype=np.float32)

    return dims, tags


def parse_extrinsics(path):
    with open(path, "r") as f:
        data = json.load(f)

    cameras = {}
    for name, cam in data.items():
        pos = np.array(cam.get("camera_position", [0.0, 0.0, 0.0]), dtype=np.float32) * 1000.0
        rvec = np.array(cam.get("rvec", [0.0, 0.0, 0.0]), dtype=np.float32)
        cameras[name] = {"pos": pos, "rvec": rvec}
    return cameras


def draw_room(ax, dims, floor_alpha=0.08):
    x_max, y_max, z_max = dims["X"], dims["Y"], dims["Z"]
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
        dtype=np.float32,
    )

    floor = Poly3DCollection(
        [[corners[0], corners[1], corners[2], corners[3]]],
        alpha=floor_alpha,
        facecolors="#d7e1e8",
        edgecolors="none",
    )
    ax.add_collection3d(floor)

    edges = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 0),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 4),
        (0, 4),
        (1, 5),
        (2, 6),
        (3, 7),
    ]
    for a, b in edges:
        ax.plot(*zip(corners[a], corners[b]), color="#6b6b6b", linewidth=1.0, alpha=0.7)


def draw_tags(ax, tags, show_ids=True):
    for tag_id, corners in tags.items():
        poly = Poly3DCollection([corners], alpha=0.30, facecolors="#53c4f5", edgecolors="#0c74a8")
        ax.add_collection3d(poly)
        if show_ids:
            c = corners.mean(axis=0)
            ax.text(c[0], c[1], c[2], str(tag_id), color="#0c74a8", fontsize=7)


def draw_cameras(ax, cameras):
    import cv2

    colors = {"camNorth": "red", "camEast": "green", "camSouth": "blue", "camWest": "orange"}
    for name, cam in cameras.items():
        pos = cam["pos"]
        rvec = cam["rvec"].reshape(3, 1)
        rmat, _ = cv2.Rodrigues(rvec)
        forward = rmat.T[:, 2]

        col = colors.get(name, "black")
        ax.scatter(pos[0], pos[1], pos[2], c=col, s=70, marker="^")
        ax.quiver(pos[0], pos[1], pos[2], forward[0], forward[1], forward[2], length=500, color=col)
        ax.text(pos[0], pos[1], pos[2], name, color=col, fontsize=9, fontweight="bold")


def frame_image(dims, tags, cameras, azim, elev, args, out_path):
    x_max, y_max, z_max = dims["X"], dims["Y"], dims["Z"]

    fig = plt.figure(figsize=(args.figsize[0], args.figsize[1]), facecolor=args.bg_color)
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor(args.bg_color)
    ax.grid(True, color=args.grid_color, linewidth=0.6, alpha=0.6)
    ax.set_box_aspect([x_max, y_max, z_max])

    draw_room(ax, dims, floor_alpha=args.floor_alpha)
    draw_tags(ax, tags, show_ids=not args.hide_tag_ids)
    draw_cameras(ax, cameras)

    ax.set_xlim(0, x_max)
    ax.set_ylim(0, y_max)
    ax.set_zlim(0, z_max)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title(args.title)
    ax.view_init(elev=elev, azim=azim)
    ax.tick_params(axis="both", which="major", labelsize=10)

    plt.savefig(out_path, dpi=args.dpi)
    plt.close(fig)


def encode_video(frames_dir, out_video, fps, crf, preset):
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        str(out_video),
    ]
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(description="Render AprilTag garage arena (static + 360 orbit).")
    ap.add_argument("--dimensions", default="garage_lab_combined/cal/extrinsics/Dimensions.txt")
    ap.add_argument("--extrinsics", default="garage_lab_combined/cal/extrinsics/extrinsics_main.json")
    ap.add_argument("--out-image", default="garage_lab_combined/output/arena_apriltag_static_v2.png")
    ap.add_argument("--out-video", default="garage_lab_combined/output/arena_apriltag_360_v2.mp4")
    ap.add_argument("--frames-dir", default="garage_lab_combined/output/frames_arena_apriltag_360_v2")
    ap.add_argument("--mode", choices=["static", "orbit", "both"], default="both")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--frames", type=int, default=180, help="Orbit frame count")
    ap.add_argument("--elev", type=float, default=22.0)
    ap.add_argument("--start-azim", type=float, default=-60.0)
    ap.add_argument("--azim-span", type=float, default=360.0)
    ap.add_argument("--title", default="Garage Arena AprilTags + Camera Poses")
    ap.add_argument("--hide-tag-ids", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--figsize", type=float, nargs=2, default=[12.0, 9.0])
    ap.add_argument("--dpi", type=int, default=160)
    ap.add_argument("--bg-color", default="#f7f7f7")
    ap.add_argument("--grid-color", default="#c0c0c0")
    ap.add_argument("--floor-alpha", type=float, default=0.08)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--clean-frames", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    dims, tags = parse_dimensions(args.dimensions)
    cameras = parse_extrinsics(args.extrinsics)

    out_image = Path(args.out_image)
    out_video = Path(args.out_video)
    frames_dir = Path(args.frames_dir)
    out_image.parent.mkdir(parents=True, exist_ok=True)
    out_video.parent.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    if args.mode in ("static", "both"):
        frame_image(
            dims=dims,
            tags=tags,
            cameras=cameras,
            azim=args.start_azim,
            elev=args.elev,
            args=args,
            out_path=out_image,
        )
        print(f"[OK] Static arena image: {out_image}")

    if args.mode in ("orbit", "both"):
        if args.clean_frames:
            for p in frames_dir.glob("frame_*.png"):
                p.unlink()

        for i in range(args.frames):
            azim = args.start_azim + args.azim_span * (i / max(1, args.frames))
            frame_path = frames_dir / f"frame_{i:04d}.png"
            frame_image(
                dims=dims,
                tags=tags,
                cameras=cameras,
                azim=azim,
                elev=args.elev,
                args=args,
                out_path=frame_path,
            )
            if i % 20 == 0:
                print(f"Rendered frame {i}/{args.frames}")

        encode_video(frames_dir, out_video, fps=args.fps, crf=args.crf, preset=args.preset)
        print(f"[OK] Orbit arena video: {out_video}")


if __name__ == "__main__":
    main()
