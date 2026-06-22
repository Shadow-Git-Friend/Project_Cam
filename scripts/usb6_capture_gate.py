#!/usr/bin/env python3
"""USB/controller and capture-health gate for the temporary 6-USB camera rig.

This script is intentionally calibration-independent. It verifies that the
capture-only config opens, records basic per-camera freshness/stall metrics, and
fails early when all cameras still sit on one USB controller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml


def run_text(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    return proc.returncode, proc.stdout


def load_camera_config(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text())
    cams = data.get("cameras", {}) if data else {}
    if isinstance(cams, dict):
        return {name: str(info["device"]) for name, info in cams.items()}
    return {str(c["name"]): str(c["device"]) for c in cams}


def parse_v4l2_info(text: str) -> dict[str, str]:
    out = {"card": "", "bus_info": ""}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Card type"):
            out["card"] = line.split(":", 1)[1].strip()
        elif line.startswith("Bus info"):
            out["bus_info"] = line.split(":", 1)[1].strip()
    return out


def extract_usb_controller(bus_info: str) -> str:
    """Return PCI controller id from strings like usb-0000:00:14.0-13."""
    if not bus_info.startswith("usb-"):
        return ""
    tail = bus_info[4:]
    return tail.split("-", 1)[0]


def is_c920(card: str, name: str) -> bool:
    s = f"{card} {name}".lower()
    return "c920" in s or "logitech" in s


def apply_c920_low_latency_controls(device: str) -> list[str]:
    if not shutil.which("v4l2-ctl"):
        return ["v4l2-ctl missing"]
    controls = [
        "power_line_frequency=1",
        "exposure_dynamic_framerate=0",
        "auto_exposure=1",
        "exposure_time_absolute=200",
        "gain=160",
        "focus_automatic_continuous=0",
        "focus_absolute=0",
    ]
    failed: list[str] = []
    for ctrl in controls:
        code, _ = run_text(["v4l2-ctl", "-d", device, f"--set-ctrl={ctrl}"])
        if code != 0:
            failed.append(ctrl.split("=", 1)[0])
    return failed


class Reader:
    def __init__(self, name: str, device: str, width: int, height: int, fps: int, fourcc: str):
        self.name = name
        self.device = device
        self.frame = None
        self.frame_ts = 0.0
        self.lock = threading.Lock()
        self.running = True
        self.frames = 0
        self.bad_reads = 0
        self.first_ts = None
        self.last_ts = None
        self.max_gap_ms = 0.0
        self.gaps_gt_100ms = 0
        self.exact_small_frame_repeats = 0
        self._last_hash = None

        self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.opened = self.cap.isOpened()
        self.effective = {}
        if self.opened:
            eff_fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
            self.effective = {
                "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps_prop": float(self.cap.get(cv2.CAP_PROP_FPS)),
                "fourcc": "".join(chr((eff_fourcc >> (8 * i)) & 0xFF) for i in range(4)),
            }
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        if self.opened:
            self.thread.start()

    def _loop(self) -> None:
        while self.running:
            ok, frame = self.cap.read()
            now = time.perf_counter()
            if not ok or frame is None:
                self.bad_reads += 1
                time.sleep(0.002)
                continue
            if self.first_ts is None:
                self.first_ts = now
            if self.last_ts is not None:
                gap_ms = (now - self.last_ts) * 1000.0
                self.max_gap_ms = max(self.max_gap_ms, gap_ms)
                if gap_ms > 100.0:
                    self.gaps_gt_100ms += 1
            self.last_ts = now
            self.frames += 1

            small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
            digest = hashlib.md5(small.tobytes()).hexdigest()
            if digest == self._last_hash:
                self.exact_small_frame_repeats += 1
            self._last_hash = digest

            with self.lock:
                self.frame = frame.copy()
                self.frame_ts = now

    def latest(self):
        with self.lock:
            if self.frame is None:
                return None, self.frame_ts
            return self.frame.copy(), self.frame_ts

    def stop(self) -> None:
        self.running = False
        if self.opened:
            self.thread.join(timeout=2.0)
        self.cap.release()

    def report(self) -> dict:
        duration = 0.0
        if self.first_ts is not None and self.last_ts is not None and self.last_ts > self.first_ts:
            duration = self.last_ts - self.first_ts
        return {
            "device": self.device,
            "opened": bool(self.opened),
            "effective": self.effective,
            "frames": int(self.frames),
            "bad_reads": int(self.bad_reads),
            "fresh_fps": float(self.frames / duration) if duration > 0 else 0.0,
            "max_gap_ms": float(self.max_gap_ms),
            "gaps_gt_100ms": int(self.gaps_gt_100ms),
            "exact_small_frame_repeats": int(self.exact_small_frame_repeats),
        }


def make_mosaic(readers: list[Reader], tile_w: int = 480, tile_h: int = 270) -> np.ndarray:
    tiles = []
    now = time.perf_counter()
    for r in readers:
        frame, ts = r.latest()
        if frame is None:
            tile = np.zeros((tile_h, tile_w, 3), dtype=np.uint8)
            label = f"{r.name} NO FRAME"
        else:
            tile = cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
            label = f"{r.name} age={(now - ts) * 1000.0:.0f}ms"
        cv2.rectangle(tile, (0, 0), (tile_w, 34), (0, 0, 0), -1)
        cv2.putText(tile, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
        tiles.append(tile)
    while len(tiles) < 6:
        tiles.append(np.zeros((tile_h, tile_w, 3), dtype=np.uint8))
    cols = 3 if len(tiles) > 4 else 2
    rows = int(np.ceil(len(tiles) / cols))
    while len(tiles) < rows * cols:
        tiles.append(np.zeros((tile_h, tile_w, 3), dtype=np.uint8))
    return np.vstack([np.hstack(tiles[i * cols:(i + 1) * cols]) for i in range(rows)])


def evaluate_usb_split(camera_info: dict[str, dict]) -> dict:
    controllers = sorted({v.get("controller", "") for v in camera_info.values() if v.get("controller")})
    c920_controllers = sorted({
        v.get("controller", "")
        for k, v in camera_info.items()
        if is_c920(v.get("card", ""), k) and v.get("controller")
    })
    return {
        "controllers": controllers,
        "c920_controllers": c920_controllers,
        "all_on_one_controller": len(controllers) <= 1 and len(camera_info) > 1,
        "controller_count": len(controllers),
    }


def capture_passed(capture: dict[str, dict], min_fps: float, max_gap_ms: float) -> bool:
    for rep in capture.values():
        if not rep["opened"]:
            return False
        if rep["fresh_fps"] < min_fps:
            return False
        if rep["max_gap_ms"] > max_gap_ms:
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate the temporary 6-USB camera setup.")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras_6usb_test.yaml")
    ap.add_argument("--output-dir", default="")
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--min-fresh-fps", type=float, default=15.0)
    ap.add_argument("--max-gap-ms", type=float, default=100.0)
    ap.add_argument("--allow-single-controller", action="store_true",
                    help="Do not fail when all cameras are still on one USB controller.")
    ap.add_argument("--mosaic-video", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else Path("Parallel_working/output") / time.strftime("usb6_gate_%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    cam_devs = load_camera_config(Path(args.config))
    camera_info: dict[str, dict] = {}
    for name, device in cam_devs.items():
        code, text = run_text(["v4l2-ctl", "-d", device, "--info"])
        info = parse_v4l2_info(text if code == 0 else "")
        info.update({
            "device": device,
            "v4l2_info_ok": code == 0,
            "controller": extract_usb_controller(info.get("bus_info", "")),
        })
        if is_c920(info.get("card", ""), name):
            info["uvc_control_failures"] = apply_c920_low_latency_controls(device)
        camera_info[name] = info

    usb_split = evaluate_usb_split(camera_info)

    readers = [Reader(name, dev, args.width, args.height, args.fps, args.fourcc) for name, dev in cam_devs.items()]
    for r in readers:
        r.start()

    writer = None
    if args.mosaic_video:
        first = make_mosaic(readers)
        writer = cv2.VideoWriter(str(out_dir / "mosaic.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), min(args.fps, 15), (first.shape[1], first.shape[0]))
        if writer.isOpened():
            writer.write(first)

    start = time.perf_counter()
    next_video = start
    while time.perf_counter() - start < args.duration:
        if writer is not None and writer.isOpened() and time.perf_counter() >= next_video:
            writer.write(make_mosaic(readers))
            next_video += 1.0 / min(args.fps, 15)
        time.sleep(0.01)

    mosaic = make_mosaic(readers)
    cv2.imwrite(str(out_dir / "mosaic_last.jpg"), mosaic)
    if writer is not None:
        writer.release()
    for r in readers:
        r.stop()

    capture = {r.name: r.report() for r in readers}
    capture_ok = capture_passed(capture, args.min_fresh_fps, args.max_gap_ms)
    usb_ok = (not usb_split["all_on_one_controller"]) or args.allow_single_controller
    passed = bool(usb_ok and capture_ok)

    code, lsusb_tree = run_text(["lsusb", "-t"])
    report = {
        "passed": passed,
        "config": args.config,
        "requested": {"width": args.width, "height": args.height, "fps": args.fps, "fourcc": args.fourcc},
        "duration_s": args.duration,
        "usb_split": usb_split,
        "camera_info": camera_info,
        "capture": capture,
        "gates": {
            "usb_controller_split_ok": usb_ok,
            "capture_ok": capture_ok,
            "min_fresh_fps": args.min_fresh_fps,
            "max_gap_ms": args.max_gap_ms,
        },
        "artifacts": {
            "mosaic_last": str(out_dir / "mosaic_last.jpg"),
            "mosaic_video": str(out_dir / "mosaic.mp4") if args.mosaic_video else "",
        },
        "lsusb_tree": lsusb_tree if code == 0 else "",
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2))

    print(json.dumps(report["gates"], indent=2))
    print(f"[INFO] report: {out_dir / 'report.json'}")
    print(f"[INFO] mosaic: {out_dir / 'mosaic_last.jpg'}")
    if not passed:
        print("[FAIL] 6-camera gate failed; inspect report.json for the failing gate.")
        return 1
    print("[OK] 6-camera gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
