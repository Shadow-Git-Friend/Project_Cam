#!/usr/bin/env python3
"""Record a single V4L2 camera with ffmpeg for quick testing."""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record one webcam using ffmpeg.")
    p.add_argument("--dev", default="/dev/video0", help="Device path, e.g. /dev/video0")
    p.add_argument("--resolution", default="1920x1080", help="Video resolution, e.g. 1920x1080")
    p.add_argument("--framerate", type=int, default=30, help="Frames per second")
    p.add_argument("--input-format", default="mjpeg", help="V4L2 input format, e.g. mjpeg")
    p.add_argument("--no-copy", action="store_true", help="Re-encode instead of stream copy")
    p.add_argument("--thread-queue-size", type=int, default=512, help="Input thread queue size (0 to disable)")
    p.add_argument("--rtbufsize", default="256M", help="V4L2 input buffer size, e.g. 256M (set 0 to disable)")
    p.add_argument("--use-wallclock-timestamps", dest="use_wallclock_timestamps", action="store_true", default=True, help="Use wallclock timestamps (default: on)")
    p.add_argument("--no-wallclock-timestamps", dest="use_wallclock_timestamps", action="store_false", help="Disable wallclock timestamps")
    p.add_argument("--genpts", dest="genpts", action="store_true", default=True, help="Generate missing PTS (default: on)")
    p.add_argument("--no-genpts", dest="genpts", action="store_false", help="Disable PTS generation")
    p.add_argument("--out-dir", default=None, help="Output directory (default: recordings/YYYYMMDD_HHMMSS)")
    p.add_argument("--loglevel", default="error", choices=["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug"], help="ffmpeg log level")
    p.add_argument("--dry-run", action="store_true", help="Print command without starting ffmpeg")
    return p.parse_args()


def build_cmd(args: argparse.Namespace, out_path: Path) -> list[str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        args.loglevel,
    ]
    if args.genpts:
        cmd += ["-fflags", "+genpts"]
    if args.rtbufsize and args.rtbufsize != "0":
        cmd += ["-rtbufsize", args.rtbufsize]
    if args.thread_queue_size and args.thread_queue_size > 0:
        cmd += ["-thread_queue_size", str(args.thread_queue_size)]
    if args.use_wallclock_timestamps:
        cmd += ["-use_wallclock_as_timestamps", "1"]
    cmd += [
        "-f",
        "v4l2",
        "-input_format",
        args.input_format,
        "-video_size",
        args.resolution,
        "-framerate",
        str(args.framerate),
        "-i",
        args.dev,
        "-an",
    ]
    if args.no_copy:
        cmd += ["-c:v", "mjpeg", "-q:v", "3"]
    else:
        cmd += ["-c:v", "copy"]
    cmd.append(str(out_path))
    return cmd


def main() -> int:
    args = parse_args()

    if not shutil.which("ffmpeg"):
        print("ERROR: ffmpeg not found in PATH.", file=sys.stderr)
        return 1
    if args.thread_queue_size < 0:
        print("ERROR: --thread-queue-size must be >= 0.")
        return 1
    if not args.rtbufsize:
        print("ERROR: --rtbufsize cannot be empty (use 0 to disable).")
        return 1

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else Path("recordings") / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "single_cam.mkv"

    cmd = build_cmd(args, out_path)
    if args.dry_run:
        print(" ".join(cmd))
        return 0

    print(f"Recording {args.dev} -> {out_path}")
    print("Press Ctrl+C to stop recording.")
    try:
        proc = subprocess.Popen(cmd)
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
