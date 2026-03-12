#!/usr/bin/env python3
"""Record multiple V4L2 cameras simultaneously with ffmpeg.

- Detects /dev/video* devices
- Lets you exclude the built-in webcam by na`me or device path
- Starts one ffmpeg process per camera
- Optional 2x2 preview grid in a single ffmpeg process
- Stops all recordings cleanly on exit (Ctrl+C / SIGTERM)
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path
from typing import List, Optional, Tuple


def _run(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"


def _device_sort_key(dev_path: str) -> Tuple[int, str]:
    m = re.search(r"(\d+)$", dev_path)
    return (int(m.group(1)) if m else 9999, dev_path)


def _name_from_v4l2ctl(dev_path: str) -> Optional[str]:
    if not shutil.which("v4l2-ctl"):
        return None
    rc, out, _ = _run(["v4l2-ctl", "--device", dev_path, "--all"])
    if rc != 0:
        return None
    for line in out.splitlines():
        if "Card type" in line:
            return line.split(":", 1)[1].strip()
    return None


def _is_capture_device_v4l2(dev_path: str) -> Optional[bool]:
    if not shutil.which("v4l2-ctl"):
        return None
    rc, out, _ = _run(["v4l2-ctl", "--device", dev_path, "--all"])
    if rc != 0:
        return None
    # If V4L2 output lists Video Capture, treat as capture device
    if "Video Capture" in out or "Video Capture Multiplanar" in out:
        return True
    return False


def _name_from_udev(dev_path: str) -> Optional[str]:
    if not shutil.which("udevadm"):
        return None
    rc, out, _ = _run(["udevadm", "info", "--query=all", "--name", dev_path])
    if rc != 0:
        return None
    for line in out.splitlines():
        if line.startswith("E: ID_V4L_PRODUCT="):
            return line.split("=", 1)[1].strip()
        if line.startswith("E: ID_MODEL="):
            return line.split("=", 1)[1].strip()
    return None


def _sanitize_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    return name or "camera"


def list_video_devices() -> List[dict]:
    devs = sorted(glob.glob("/dev/video*"), key=_device_sort_key)
    results = []
    for dev in devs:
        if not os.path.exists(dev):
            continue
        capture = _is_capture_device_v4l2(dev)
        name = _name_from_v4l2ctl(dev) or _name_from_udev(dev) or "Unknown"
        results.append({"dev": dev, "name": name, "capture": capture})
    # Prefer capture devices; keep unknowns too
    results = [r for r in results if r["capture"] is not False]
    return results


def build_input_args(
    dev: str,
    fmt: str,
    res: str,
    fps: int,
    thread_queue_size: int,
    rtbufsize: str,
    use_wallclock: bool,
) -> List[str]:
    args: List[str] = []
    if rtbufsize and rtbufsize != "0":
        args += ["-rtbufsize", rtbufsize]
    if thread_queue_size and thread_queue_size > 0:
        args += ["-thread_queue_size", str(thread_queue_size)]
    if use_wallclock:
        args += ["-use_wallclock_as_timestamps", "1"]
    args += [
        "-f",
        "v4l2",
        "-input_format",
        fmt,
        "-video_size",
        res,
        "-framerate",
        str(fps),
        "-i",
        dev,
    ]
    return args


def build_ffmpeg_cmd(
    dev: str,
    out_path: Path,
    fmt: str,
    res: str,
    fps: int,
    copy: bool,
    loglevel: str,
    thread_queue_size: int,
    rtbufsize: str,
    use_wallclock: bool,
    genpts: bool,
) -> List[str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        loglevel,
    ]
    if genpts:
        cmd += ["-fflags", "+genpts"]
    cmd += build_input_args(dev, fmt, res, fps, thread_queue_size, rtbufsize, use_wallclock)
    cmd += ["-an"]
    if copy:
        cmd += ["-c:v", "copy"]
    else:
        # Re-encode to MJPEG with reasonable quality if copy is disabled
        cmd += ["-c:v", "mjpeg", "-q:v", "3"]
    cmd.append(str(out_path))
    return cmd


def build_ffmpeg_grid_cmd(
    devs: List[dict],
    out_paths: List[Path],
    fmt: str,
    res: str,
    fps: int,
    copy: bool,
    loglevel: str,
    preview_scale: float,
    thread_queue_size: int,
    rtbufsize: str,
    use_wallclock: bool,
    genpts: bool,
) -> List[str]:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", loglevel]
    if genpts:
        cmd += ["-fflags", "+genpts"]
    for d in devs:
        cmd += build_input_args(d["dev"], fmt, res, fps, thread_queue_size, rtbufsize, use_wallclock)
    cmd += ["-an"]

    filter_str = "[0:v][1:v][2:v][3:v]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0"
    if preview_scale and preview_scale != 1.0:
        filter_str += f",scale=iw*{preview_scale}:ih*{preview_scale}"
    filter_str += "[v]"
    cmd += ["-filter_complex", filter_str]

    for idx, out_path in enumerate(out_paths):
        cmd += ["-map", f"{idx}:v"]
        if copy:
            cmd += ["-c:v", "copy"]
        else:
            cmd += ["-c:v", "mjpeg", "-q:v", "3"]
        cmd.append(str(out_path))

    # Preview output (SDL window)
    cmd += ["-map", "[v]", "-c:v", "rawvideo", "-pix_fmt", "yuv420p", "-f", "sdl", "multicam_preview"]
    return cmd


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Record multiple webcams simultaneously using ffmpeg.")
    p.add_argument("--list", action="store_true", help="List detected video devices and exit")
    p.add_argument("--include-dev", action="append", default=[], help="Device path to include, e.g. /dev/video0 (can be used multiple times)")
    p.add_argument("--exclude-name", action="append", default=[], help="Regex to exclude device names (can be used multiple times)")
    p.add_argument("--exclude-dev", action="append", default=[], help="Device path to exclude, e.g. /dev/video0 (can be used multiple times)")
    p.add_argument("--max-cams", type=int, default=4, help="Maximum number of cameras to record")
    p.add_argument("--resolution", default="1920x1080", help="Video resolution, e.g. 1920x1080")
    p.add_argument("--framerate", type=int, default=30, help="Frames per second")
    p.add_argument("--input-format", default="mjpeg", help="V4L2 input format, e.g. mjpeg")
    p.add_argument("--no-copy", action="store_true", help="Re-encode instead of stream copy")
    p.add_argument("--preview-grid", action="store_true", help="Show a live 2x2 preview grid while recording (requires 4 cameras)")
    p.add_argument("--preview-scale", type=float, default=0.5, help="Scale factor for the preview window (default: 0.5)")
    p.add_argument("--thread-queue-size", type=int, default=512, help="Input thread queue size (0 to disable)")
    p.add_argument("--rtbufsize", default="256M", help="V4L2 input buffer size, e.g. 256M (set 0 to disable)")
    p.add_argument("--use-wallclock-timestamps", dest="use_wallclock_timestamps", action="store_true", default=True, help="Use wallclock timestamps (default: on)")
    p.add_argument("--no-wallclock-timestamps", dest="use_wallclock_timestamps", action="store_false", help="Disable wallclock timestamps")
    p.add_argument("--genpts", dest="genpts", action="store_true", default=True, help="Generate missing PTS (default: on)")
    p.add_argument("--no-genpts", dest="genpts", action="store_false", help="Disable PTS generation")
    p.add_argument("--duration", type=float, default=0.0, help="Auto-stop after N seconds (0 = no auto-stop)")
    p.add_argument("--out-dir", default=None, help="Output directory (default: recordings/YYYYMMDD_HHMMSS)")
    p.add_argument("--loglevel", default="error", choices=["quiet", "panic", "fatal", "error", "warning", "info", "verbose", "debug"], help="ffmpeg log level")
    p.add_argument("--dry-run", action="store_true", help="Print commands without starting ffmpeg")
    return p.parse_args()


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

    if args.preview_scale <= 0:
        print("ERROR: --preview-scale must be > 0.")
        return 1

    devices = list_video_devices()
    if not devices:
        print("No /dev/video* devices found.")
        return 1

    if args.list:
        print("Detected devices:")
        for i, d in enumerate(devices, start=1):
            cap = "capture" if d["capture"] else "unknown"
            print(f"  {i}. {d['dev']}  |  {d['name']}  |  {cap}")
        return 0

    # Apply exclusions
    exclude_dev = set(args.exclude_dev or [])
    exclude_patterns = [re.compile(p, re.IGNORECASE) for p in (args.exclude_name or [])]
    include_dev = [d for d in (args.include_dev or []) if d]

    def is_excluded(d: dict) -> bool:
        if d["dev"] in exclude_dev:
            return True
        for pat in exclude_patterns:
            if pat.search(d["name"]):
                return True
        return False

    if include_dev:
        # Preserve the order of --include-dev arguments
        dev_map = {d["dev"]: d for d in devices}
        filtered = [dev_map[d] for d in include_dev if d in dev_map and not is_excluded(dev_map[d])]
    else:
        filtered = [d for d in devices if not is_excluded(d)]

    if not filtered:
        print("No devices left after exclusions.")
        return 1

    selected = filtered[: max(1, args.max_cams)]

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else Path("recordings") / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_procs: List[subprocess.Popen] = []

    def _stop_all(signum=None, frame=None):
        for p in ffmpeg_procs:
            if p.poll() is None:
                p.terminate()
        # Give ffmpeg some time to close files cleanly
        t_end = time.time() + 5
        for p in ffmpeg_procs:
            while p.poll() is None and time.time() < t_end:
                time.sleep(0.1)
            if p.poll() is None:
                p.kill()
        if signum is not None:
            print(f"\nStopped (signal {signum}).")
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop_all)
    signal.signal(signal.SIGTERM, _stop_all)

    if args.duration and args.duration > 0:
        def _auto_stop():
            try:
                os.kill(os.getpid(), signal.SIGINT)
            except Exception:
                pass
        threading.Timer(args.duration, _auto_stop).start()

    out_paths: List[Path] = []
    for idx, d in enumerate(selected, start=1):
        safe_name = _sanitize_name(d["name"])
        out_path = out_dir / f"cam{idx:02d}_{safe_name}.mkv"
        out_paths.append(out_path)

    if args.preview_grid:
        if len(selected) != 4:
            print("ERROR: --preview-grid requires exactly 4 cameras (2x2 grid).")
            return 1
        print("Recording cameras (2x2 preview grid):")
        for idx, d in enumerate(selected, start=1):
            print(f"  {d['dev']}  |  {d['name']}  ->  {out_paths[idx - 1]}")
        cmd = build_ffmpeg_grid_cmd(
            selected,
            out_paths,
            args.input_format,
            args.resolution,
            args.framerate,
            copy=(not args.no_copy),
            loglevel=args.loglevel,
            preview_scale=args.preview_scale,
            thread_queue_size=args.thread_queue_size,
            rtbufsize=args.rtbufsize,
            use_wallclock=args.use_wallclock_timestamps,
            genpts=args.genpts,
        )
        if args.dry_run:
            print("    ", " ".join(cmd))
            print("Dry run complete. No recording started.")
            return 0
        try:
            p = subprocess.Popen(cmd)
        except FileNotFoundError:
            print("ERROR: ffmpeg not found in PATH.", file=sys.stderr)
            _stop_all()
        ffmpeg_procs.append(p)
    else:
        print("Recording cameras:")
        for idx, d in enumerate(selected, start=1):
            out_path = out_paths[idx - 1]
            cmd = build_ffmpeg_cmd(
                d["dev"],
                out_path,
                args.input_format,
                args.resolution,
                args.framerate,
                copy=(not args.no_copy),
                loglevel=args.loglevel,
                thread_queue_size=args.thread_queue_size,
                rtbufsize=args.rtbufsize,
                use_wallclock=args.use_wallclock_timestamps,
                genpts=args.genpts,
            )
            print(f"  {d['dev']}  |  {d['name']}  ->  {out_path}")
            if args.dry_run:
                print("    ", " ".join(cmd))
                continue
            try:
                p = subprocess.Popen(cmd)
            except FileNotFoundError:
                print("ERROR: ffmpeg not found in PATH.", file=sys.stderr)
                _stop_all()
            ffmpeg_procs.append(p)

        if args.dry_run:
            print("Dry run complete. No recording started.")
            return 0

    print("\nPress Ctrl+C to stop recording.")
    # Wait for any child to exit; if one dies, stop all
    try:
        while True:
            for p in ffmpeg_procs:
                if p.poll() is not None:
                    print("A recording process ended unexpectedly. Stopping all.")
                    _stop_all()
            time.sleep(0.2)
    except KeyboardInterrupt:
        _stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
