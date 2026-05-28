import argparse
import subprocess
from pathlib import Path


def run(cmd):
    print("[RUN]", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser(description="Render fixed multiview videos (top/bottom/left/right)")
    ap.add_argument("--motion", default="garage_lab_combined/output/motion_capture_data_garage.json")
    ap.add_argument("--renderer", default="garage_lab_combined/scripts/render_arena_ball_skeleton.py")
    ap.add_argument("--out-dir", default="garage_lab_combined/output/multiview")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--smooth-window", type=int, default=3)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--no-auto-center", action="store_true")
    ap.add_argument("--no-auto-floor", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    views = [
        ("top", 90, -90),
        ("bottom", -90, -90),
        ("left", 20, 180),
        ("right", 20, 0),
    ]

    for name, elev, azim in views:
        view_frames_dir = out_dir / f"frames_{name}"
        out_video = out_dir / f"garage_{name}.mp4"
        cmd = [
            "./venv/bin/python",
            args.renderer,
            "--motion", args.motion,
            "--out-dir", str(view_frames_dir),
            "--out-video", str(out_video),
            "--fps", str(args.fps),
            "--elev", str(elev),
            "--azim", str(azim),
            "--smooth-window", str(args.smooth_window),
        ]

        if args.max_frames > 0:
            cmd += ["--max-frames", str(args.max_frames)]
        if args.no_auto_center:
            cmd += ["--no-auto-center"]
        if args.no_auto_floor:
            cmd += ["--no-auto-floor"]

        run(cmd)

    print("[DONE] Multiview videos saved in", out_dir)


if __name__ == "__main__":
    main()
