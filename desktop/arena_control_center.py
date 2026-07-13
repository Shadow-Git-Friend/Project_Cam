#!/usr/bin/env python3
"""Project Cam Arena Control Center — Kairat-styled desktop app for the live rig.

Design language follows fckairat.com: black stage, club yellow accents,
uppercase condensed headings, card grid, structured tables.

Three views (sidebar navigation, mirroring the planned athlete dashboard):
- CONTROL   — launch pipelines, tracking options, local face gallery, mission log
- ANALYTICS — athlete KPI cards (Level / Exactness / Quickness / Progress /
              Rating), rating trend and performance radar
- MATCHES   — per-shot table (gun, target, speed, angle, spin, result, time)

ANALYTICS and MATCHES read live artifacts when the pipelines produce them
(`output/analytics/athlete_profile.json`, `garage_lab_combined/output/blm_logs/
*.jsonl`) and fall back to clearly labelled DEMO data until then.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import shlex
import signal
import subprocess
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import font as tkfont
from tkinter import ttk

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_venv_python(repo_root=REPO_ROOT, fallback=sys.executable) -> str:
    root = Path(repo_root)
    for relative in ("venv/bin/python", ".venv/bin/python"):
        candidate = root / relative
        if candidate.exists():
            return str(candidate)
    return str(fallback)


def parse_multi_people(raw, enabled):
    if not enabled:
        return 1
    try:
        people = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ValueError("People count must be an integer from 2 to 6") from None
    if not 2 <= people <= 6:
        raise ValueError("People count must be from 2 to 6")
    return people


def process_group_alive(pgid):
    if pgid is None:
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def build_live_command(
    *,
    repo_root,
    script,
    multi_people=1,
    face_id=False,
    auto_orbit=False,
    limb_heat=False,
    primary_person="",
):
    command = ["bash", str(Path(repo_root) / script)]
    if int(multi_people) > 1:
        command += ["--multi-person", str(int(multi_people))]
    if face_id:
        command.append("--face-id")
        if str(primary_person).strip():
            command += ["--primary-person", str(primary_person).strip()]
    if auto_orbit:
        command.append("--auto-orbit")
    if limb_heat:
        command.append("--limb-heat")
    return command


def build_face_enroll_command(*, repo_root, python, name, camera="0"):
    return [
        str(python),
        str(Path(repo_root) / "Parallel_working/scripts/face_enroll.py"),
        "--camera",
        str(camera),
        "--name",
        str(name),
    ]


def build_model_setup_command(repo_root, python):
    return [
        str(python),
        str(Path(repo_root) / "Parallel_working/scripts/download_face_models.py"),
    ]


# ---------------------------------------------------------------------------
# Kairat palette — black stage, club yellow, white type, red reserved for stop
# ---------------------------------------------------------------------------

YELLOW = "#FFDE00"
YELLOW_HOVER = "#FFE94D"
YELLOW_SHADE = "#8C7A00"
BG = "#0A0A0B"
SIDEBAR = "#0E0E10"
PANEL = "#141416"
CARD = "#19191C"
CARD_HOVER = "#222226"
EDGE = "#26262B"
TEXT = "#F7F7F4"
DIM = "#9C9CA3"
FAINT = "#5F5F66"
RED = "#FF4B44"
RED_BG = "#33110F"
GREEN = "#42C86A"
LOG_BG = "#060607"

# Backwards-friendly aliases (older sessions referenced these names).
ORANGE = YELLOW
CYAN = YELLOW


@dataclass(frozen=True)
class LaunchSpec:
    title: str
    description: str
    script: str
    accent: str


LAUNCHES = (
    LaunchSpec(
        "6-CAMERA CINEMATIC ARENA",
        "Fast mirrored skeleton · multi-person ready",
        "Parallel_working/run_live_usb6_mirrored_skeleton.sh",
        YELLOW,
    ),
    LaunchSpec(
        "6-CAMERA + BLM AIM OVERLAY",
        "Pose + UDP target + aim visualization; no direct firing",
        "Parallel_working/run_live_usb6_blm.sh",
        YELLOW,
    ),
    LaunchSpec(
        "4-CAMERA YOLO-POSE",
        "Classic calibrated arena fallback",
        "Parallel_working/run_live_parallel_yolopose.sh",
        YELLOW,
    ),
    LaunchSpec(
        "RECORD 3D SESSION",
        "Clean SIGINT stop preserves MP4 finalization",
        "Parallel_working/run_record_3d.sh",
        RED,
    ),
)


# ---------------------------------------------------------------------------
# Data layer — pure, headless-testable loaders with honest demo fallbacks
# ---------------------------------------------------------------------------

ANALYTICS_SOURCES = (
    "output/analytics/athlete_profile.json",
    "garage_lab_combined/output/analytics/athlete_profile.json",
)

ANALYTICS_NUMERIC_FIELDS = (
    "level",
    "exactness_pct",
    "quickness_s",
    "progress_pct",
    "rating",
    "rating_delta_pct",
)

FACE_MODEL_FILES = (
    "face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx",
)

READINESS_CALIBRATION_FILES = (
    "garage_lab_combined/config/cameras_6usb_test.yaml",
    "garage_lab_combined/cal/extrinsics_usb6/extrinsics_usb6.json",
    "garage_lab_combined/cal/extrinsics_usb6/Dimensions_mirrored_y.txt",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb01_C920_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb02_1080P_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb03_C920_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb04_1080P_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb05_1080P_intrinsics.json",
    "garage_lab_combined/cal/intrinsics_usb6_1280x720/camUsb06_1080P_intrinsics.json",
)

MATCH_LOG_DIRS = (
    "garage_lab_combined/output/blm_logs",
    "output/blm_logs",
)

DEMO_ANALYTICS = {
    "athlete": "DEMO ATHLETE",
    "date_range": "PREVIEW SEASON",
    "level": 4,
    "exactness_pct": 78.0,
    "quickness_s": 3.45,
    "progress_pct": 70.0,
    "rating": 5.0,
    "rating_delta_pct": 8.0,
    "trend": [
        {"label": "06.07", "value": 52},
        {"label": "07.07", "value": 61},
        {"label": "08.07", "value": 58},
        {"label": "09.07", "value": 66},
        {"label": "10.07", "value": 71},
        {"label": "11.07", "value": 69},
        {"label": "12.07", "value": 78},
    ],
    "radar": {
        "LEVEL": 0.80,
        "EXACTNESS": 0.78,
        "QUICKNESS": 0.62,
        "PROGRESS": 0.70,
        "REACTION": 0.74,
    },
}

DEMO_MATCHES = [
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 1 (LOWER)", "speed": "51 km/h", "angle": "0°", "spin": "0", "result": "✓", "time": "3.410 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 2 (UPPER)", "speed": "50 km/h", "angle": "4°", "spin": "-1", "result": "✓", "time": "3.553 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 2 (UPPER)", "speed": "49 km/h", "angle": "10°", "spin": "2", "result": "✓", "time": "3.119 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 2 (UPPER)", "speed": "49 km/h", "angle": "5°", "spin": "-3", "result": "✓", "time": "4.107 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 3 (LOWER)", "speed": "51 km/h", "angle": "9°", "spin": "1", "result": "✓", "time": "3.698 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 2 (UPPER)", "speed": "53 km/h", "angle": "10°", "spin": "-1", "result": "✓", "time": "4.347 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 4 (UPPER)", "speed": "53 km/h", "angle": "3°", "spin": "1", "result": "✓", "time": "4.158 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 2 (UPPER)", "speed": "31 km/h", "angle": "1°", "spin": "2", "result": "✗", "time": "3.890 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 1 (LOWER)", "speed": "49 km/h", "angle": "5°", "spin": "0", "result": "✓", "time": "2.574 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 3 (LOWER)", "speed": "51 km/h", "angle": "3°", "spin": "0", "result": "✓", "time": "3.646 s"},
    {"gun": "BLM-1", "target": "WALL 1 / TARGET 3 (LOWER)", "speed": "50 km/h", "angle": "7°", "spin": "-1", "result": "✓", "time": "4.101 s"},
]


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def format_metric(value, pattern):
    """Format one KPI without letting malformed/missing live data crash Tk."""
    number = _finite_number(value)
    return "—" if number is None else pattern.format(number)


def _source_updated_at(path):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_mtime))
    except OSError:
        return "UNKNOWN"


def _demo_analytics():
    data = dict(DEMO_ANALYTICS)
    data["trend"] = [dict(point) for point in DEMO_ANALYTICS["trend"]]
    data["radar"] = dict(DEMO_ANALYTICS["radar"])
    data.update(
        demo=True,
        source="built-in preview (no output/analytics/athlete_profile.json yet)",
        updated_at="PREVIEW",
    )
    return data


def load_analytics(repo_root=REPO_ROOT):
    """Load athlete analytics from the first live profile found, else demo.

    Live format (produced by a future analytics pipeline):
    {"athlete": str, "date_range": str, "level": int, "exactness_pct": float,
     "quickness_s": float, "progress_pct": float, "rating": float,
     "rating_delta_pct": float, "trend": [{"label": str, "value": float}],
     "radar": {axis: 0..1}}
    """
    root = Path(repo_root)
    for relative in ANALYTICS_SOURCES:
        path = root / relative
        try:
            raw = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        data = {
            "athlete": raw.get("athlete")
            if isinstance(raw.get("athlete"), str) and raw["athlete"].strip()
            else "UNNAMED ATHLETE",
            "date_range": raw.get("date_range")
            if isinstance(raw.get("date_range"), str) and raw["date_range"].strip()
            else "LIVE PROFILE",
        }
        for key in ANALYTICS_NUMERIC_FIELDS:
            data[key] = _finite_number(raw.get(key))
        raw_trend = raw.get("trend")
        if not isinstance(raw_trend, list):
            raw_trend = []
        trend = [
            {"label": str(p.get("label", "?")), "value": float(p["value"])}
            for p in raw_trend
            if isinstance(p, dict) and _finite_number(p.get("value")) is not None
        ]
        data["trend"] = trend
        raw_radar = raw.get("radar")
        if not isinstance(raw_radar, dict):
            raw_radar = {}
        radar = {
            str(k).upper(): min(1.0, max(0.0, float(v)))
            for k, v in raw_radar.items()
            if _finite_number(v) is not None
        }
        data["radar"] = radar if len(radar) >= 3 else {}
        data["demo"] = False
        data["source"] = str(path)
        data["updated_at"] = _source_updated_at(path)
        return data
    return _demo_analytics()


def _extract_shot(record):
    """Map one tolerant JSONL record to a match row, or None if not a shot."""
    if not isinstance(record, dict):
        return None
    marker = " ".join(
        str(record.get(key, "")) for key in ("event", "action", "type", "cmd", "sent")
    ).lower()
    if not any(word in marker for word in ("shoot", "shot", "fire")):
        return None

    target = None
    for key in (
        "target", "joint", "target_joint", "aim_joint", "input_joint_name", "zone"
    ):
        value = record.get(key)
        if value:
            target = str(value).upper()
            break

    speed = None
    if isinstance(record.get("speed_kmh"), (int, float)):
        speed = f"{record['speed_kmh']:.0f} km/h"
    elif isinstance(record.get("speed_mps"), (int, float)):
        speed = f"{record['speed_mps'] * 3.6:.0f} km/h"
    else:
        rpm = None
        for key in ("rpm", "wheel_rpm", "wl", "wheel_left_rpm"):
            if isinstance(record.get(key), (int, float)):
                rpm = float(record[key])
                break
        if rpm is not None:
            speed = f"{rpm:.0f} RPM"

    angle = None
    for key in ("pitch", "v", "vertical_deg", "pitch_deg"):
        if isinstance(record.get(key), (int, float)):
            angle = f"{record[key]:.0f}°"
            break
    if angle is None and isinstance(record.get("angles_clamped"), dict):
        pitch = _finite_number(record["angles_clamped"].get("pitch_deg"))
        if pitch is not None:
            angle = f"{pitch:.0f}°"
    if angle is None and isinstance(record.get("calculated_pitch_yaw_v"), dict):
        pitch = _finite_number(record["calculated_pitch_yaw_v"].get("pitch_deg"))
        if pitch is not None:
            angle = f"{pitch:.0f}°"

    spin = None
    for key in ("spin", "spin_rps", "ball_spin"):
        value = _finite_number(record.get(key))
        if value is not None:
            spin = f"{value:g}"
            break

    result = "FIRED"
    for key in ("hit", "success", "result"):
        if key in record:
            value = record[key]
            if isinstance(value, bool):
                result = "✓" if value else "✗"
            elif str(value).lower() in ("hit", "ok", "true", "success"):
                result = "✓"
            elif str(value).lower() in ("miss", "fail", "false"):
                result = "✗"
            break
    if result == "FIRED":
        visual = str(record.get("visual_check", "")).strip().lower()
        if visual in ("y", "yes", "hit", "ok"):
            result = "✓"
        elif visual in ("n", "no", "miss", "fail"):
            result = "✗"

    stamp = None
    for key in ("shoot_timestamp", "t", "ts", "time", "timestamp"):
        if isinstance(record.get(key), (int, float)):
            stamp = time.strftime("%H:%M:%S", time.localtime(float(record[key])))
            break
        if isinstance(record.get(key), str):
            stamp = record[key]
            break

    return {
        "gun": str(record.get("gun", "BLM-1")).upper(),
        "target": target or "—",
        "speed": speed or "—",
        "angle": angle or "—",
        "spin": spin or "—",
        "result": result,
        "time": stamp or "—",
    }


def _tail_text_lines(path, max_bytes):
    """Read a bounded UTF-8 tail so a large engineering log cannot freeze Tk."""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        start = max(0, size - max(1, int(max_bytes)))
        handle.seek(start)
        payload = handle.read()
    if start > 0:
        newline = payload.find(b"\n")
        payload = payload[newline + 1:] if newline >= 0 else b""
    return payload.decode("utf-8", errors="replace").splitlines()


def load_matches(repo_root=REPO_ROOT, limit=200, max_bytes=2_000_000):
    """Rows from the newest BLM shot log; demo table when no log has shots."""
    root = Path(repo_root)
    logs = []
    for relative in MATCH_LOG_DIRS:
        directory = root / relative
        if directory.is_dir():
            logs.extend(directory.glob("*.jsonl"))
    for path in sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True):
        rows = []
        try:
            lines = _tail_text_lines(path, max_bytes)
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                row = _extract_shot(json.loads(line))
            except ValueError:
                continue
            if row is not None:
                rows.append(row)
        rows = rows[-max(1, int(limit)):]
        if rows:
            return {
                "rows": rows,
                "demo": False,
                "source": str(path),
                "updated_at": _source_updated_at(path),
            }
    return {
        "rows": [dict(row) for row in DEMO_MATCHES],
        "demo": True,
        "source": "built-in preview (no shot logs under blm_logs/ yet)",
        "updated_at": "PREVIEW",
    }


def _configured_camera_devices(repo_root):
    config = Path(repo_root) / "garage_lab_combined/config/cameras_6usb_test.yaml"
    try:
        lines = config.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    devices = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("device:"):
            devices.append(Path(stripped.split(":", 1)[1].strip()))
    return devices


def _default_gallery_path():
    data_home = Path(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
    )
    return data_home / "project-cam/face_gallery.npz"


def load_readiness(repo_root=REPO_ROOT, device_paths=None, gallery_path=None):
    """Inspect local files/devices without opening cameras or loading ML models."""
    root = Path(repo_root)
    explicit_devices = device_paths is not None
    expected_devices = (
        [Path(path) for path in device_paths]
        if explicit_devices
        else _configured_camera_devices(root)
    )
    connected = [path for path in expected_devices if path.exists()]
    if not connected:
        camera = {"ready": False, "status": "NOT CONNECTED"}
    elif explicit_devices:
        count = len(connected)
        camera = {
            "ready": True,
            "status": f"{count} DEVICE" if count == 1 else f"{count} DEVICES",
        }
    else:
        count, expected = len(connected), len(expected_devices)
        camera = {
            "ready": bool(expected) and count == expected,
            "status": f"{count}/{expected} ONLINE",
        }

    calibration_ready = all(
        (root / relative).is_file() for relative in READINESS_CALIBRATION_FILES
    )
    models_dir = root / "models/face"
    models_ready = all((models_dir / filename).is_file() for filename in FACE_MODEL_FILES)
    gallery = Path(gallery_path) if gallery_path is not None else _default_gallery_path()
    gallery_ready = gallery.is_file()
    return {
        "cameras": camera,
        "calibration": {
            "ready": calibration_ready,
            "status": "AVAILABLE" if calibration_ready else "NOT FOUND",
        },
        "face_models": {
            "ready": models_ready,
            "status": "READY" if models_ready else "NOT FOUND",
        },
        "gallery": {
            "ready": gallery_ready,
            "status": "AVAILABLE" if gallery_ready else "EMPTY",
        },
    }


# ---------------------------------------------------------------------------
# Canvas charts — no matplotlib, just yellow ink on black
# ---------------------------------------------------------------------------

def draw_trend_chart(canvas, trend, *, width, height, font):
    canvas.delete("all")
    if not trend:
        canvas.create_text(
            width / 2, height / 2, text="NOT AVAILABLE",
            fill=FAINT, font=font,
        )
        return
    left, right, top, bottom = 46, 18, 16, 34
    plot_w = max(1, width - left - right)
    plot_h = max(1, height - top - bottom)
    values = [float(p["value"]) for p in trend]
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        lo, hi = lo - 1.0, hi + 1.0
    pad = (hi - lo) * 0.15
    lo, hi = lo - pad, hi + pad

    for i in range(5):
        y = top + plot_h * i / 4
        value = hi - (hi - lo) * i / 4
        canvas.create_line(left, y, left + plot_w, y, fill=EDGE)
        canvas.create_text(left - 8, y, text=f"{value:.0f}", anchor="e",
                           fill=FAINT, font=font)

    points = []
    for i, entry in enumerate(trend):
        x = left + plot_w * (i / max(1, len(trend) - 1))
        y = top + plot_h * (1 - (float(entry["value"]) - lo) / (hi - lo))
        points.append((x, y))
        canvas.create_text(x, height - 14, text=str(entry["label"]),
                           fill=FAINT, font=font)

    if len(points) > 1:
        area = points + [(points[-1][0], top + plot_h), (points[0][0], top + plot_h)]
        canvas.create_polygon(area, fill=YELLOW_SHADE, outline="", stipple="gray25")
        canvas.create_line(points, fill=YELLOW, width=2, smooth=True)
    for x, y in points:
        canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=BG, outline=YELLOW, width=2)


def draw_radar_chart(canvas, radar, *, width, height, font):
    canvas.delete("all")
    axes = list(radar.items())
    if len(axes) < 3:
        canvas.create_text(
            width / 2, height / 2, text="NOT AVAILABLE",
            fill=FAINT, font=font,
        )
        return
    cx, cy = width / 2, height / 2 + 6
    radius = min(width, height) / 2 - 34
    count = len(axes)

    def point(idx, scale):
        angle = -math.pi / 2 + 2 * math.pi * idx / count
        return cx + radius * scale * math.cos(angle), cy + radius * scale * math.sin(angle)

    for ring in (0.25, 0.5, 0.75, 1.0):
        ring_pts = [point(i, ring) for i in range(count)]
        canvas.create_polygon(ring_pts, fill="", outline=EDGE)
    for i, (label, _) in enumerate(axes):
        x, y = point(i, 1.0)
        canvas.create_line(cx, cy, x, y, fill=EDGE)
        lx, ly = point(i, 1.24)
        canvas.create_text(lx, ly, text=label, fill=DIM, font=font)

    value_pts = [point(i, min(1.0, max(0.0, float(v)))) for i, (_, v) in enumerate(axes)]
    canvas.create_polygon(value_pts, fill=YELLOW_SHADE, outline=YELLOW,
                          width=2, stipple="gray25")
    for x, y in value_pts:
        canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=YELLOW, outline="")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class ArenaControlCenter:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.python = resolve_venv_python()
        self.proc = None
        self.proc_pgid = None
        self.proc_exit_code = None
        self.proc_title = ""
        self.proc_generation = 0
        self.shutdown_stage = 0
        self.shutdown_timer = None
        self.messages = queue.Queue()
        self.closing = False

        root.title("Project Cam — Arena Control Center")
        root.geometry("1280x820")
        root.minsize(1120, 720)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)

        head_family = self._family(("Ubuntu Condensed", "Liberation Sans Narrow",
                                    "Ubuntu", "DejaVu Sans"))
        body_family = self._family(("Inter", "Ubuntu", "DejaVu Sans"))
        mono_family = self._family(("JetBrains Mono", "Fira Code", "DejaVu Sans Mono"))
        self.title_font = (head_family, 21, "bold")
        self.nav_font = (head_family, 12, "bold")
        self.section_font = (head_family, 10, "bold")
        self.card_font = (head_family, 12, "bold")
        self.kpi_font = (head_family, 26, "bold")
        self.body_font = (body_family, 9)
        self.small_font = (body_family, 8)
        self.meta_font = (mono_family, 8)
        self.table_font = (mono_family, 9)
        self.log_font = (mono_family, 10)

        self.multi_enabled = tk.BooleanVar(root, value=True)
        self.multi_people = tk.StringVar(root, value="4")
        self.face_id = tk.BooleanVar(root, value=False)
        self.auto_orbit = tk.BooleanVar(root, value=False)
        self.limb_heat = tk.BooleanVar(root, value=False)
        self.primary_person = tk.StringVar(root, value="")
        self.enroll_name = tk.StringVar(root, value="")
        self.camera_source = tk.StringVar(root, value="0")
        self.status = tk.StringVar(root, value="IDLE")
        self.command = tk.StringVar(root, value="")
        self.launch_buttons = []
        self.nav_items = {}
        self.views = {}
        self.view_builders = {}
        self.built_views = set()
        self.active_view = "CONTROL"
        self.analytics_paint_job = None

        self._style_ttk()
        self._build()
        self._log("Project Cam control center ready", "sys")
        self._log(f"repo: {REPO_ROOT}", "dim")
        self._log(f"python: {self.python}", "dim")
        self.root.after(60, self._pump)

    # -- helpers ------------------------------------------------------------

    def _family(self, preferred):
        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            return preferred[-1]
        for family in preferred:
            if family in available:
                return family
        return preferred[-1]

    def _style_ttk(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Kairat.Treeview", background=CARD, fieldbackground=CARD,
            foreground=TEXT, rowheight=28, borderwidth=0, font=self.table_font,
        )
        style.configure(
            "Kairat.Treeview.Heading", background="#000000", foreground=YELLOW,
            font=self.section_font, relief="flat", padding=(8, 6),
        )
        style.map(
            "Kairat.Treeview",
            background=[("selected", YELLOW)],
            foreground=[("selected", "#000000")],
        )
        style.map("Kairat.Treeview.Heading", background=[("active", "#000000")])

    # -- layout -------------------------------------------------------------

    def _build(self):
        topbar = tk.Frame(self.root, bg=BG)
        topbar.pack(fill="x", padx=22, pady=(16, 12))
        badge = tk.Label(topbar, text=" PC ", bg=YELLOW, fg="#000000",
                         font=self.card_font)
        badge.pack(side="left")
        tk.Label(topbar, text="  PROJECT CAM", font=self.title_font,
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(topbar, text="  ARENA CONTROL CENTER", font=self.title_font,
                 bg=BG, fg=YELLOW).pack(side="left")
        tk.Label(topbar, text="GARAGE ARENA · ALMATY\nLOCAL · MULTI-VIEW · 3D",
                 font=self.meta_font, bg=BG, fg=FAINT, justify="right",
                 ).pack(side="right")
        tk.Frame(self.root, bg=YELLOW, height=2).pack(fill="x", padx=0)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(body, bg=SIDEBAR, width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="MENU", bg=SIDEBAR, fg=FAINT,
                 font=self.meta_font, anchor="w").pack(fill="x", padx=18, pady=(18, 6))
        for name in ("CONTROL", "ANALYTICS", "MATCHES"):
            self._nav_item(sidebar, name)
        tk.Label(
            sidebar,
            text="FUTURE:\nUSERS · LEVELS\nCALENDAR · REPORTS",
            bg=SIDEBAR, fg=FAINT, font=self.meta_font, justify="left", anchor="w",
        ).pack(fill="x", padx=18, pady=(18, 6))
        tk.Label(sidebar, text="v0.9 · PRE-SEASON", bg=SIDEBAR, fg=FAINT,
                 font=self.meta_font, anchor="w").pack(side="bottom", fill="x",
                                                        padx=18, pady=14)

        content = tk.Frame(body, bg=BG)
        content.pack(side="left", fill="both", expand=True)
        self.view_builders = dict((
            ("CONTROL", self._build_control),
            ("ANALYTICS", self._build_analytics),
            ("MATCHES", self._build_matches),
        ))
        for name in self.view_builders:
            frame = tk.Frame(content, bg=BG)
            self.views[name] = frame

        footer = tk.Frame(self.root, bg=PANEL, highlightbackground=EDGE,
                          highlightthickness=1)
        footer.pack(fill="x", side="bottom", padx=22, pady=(8, 16))
        self.status_label = tk.Label(
            footer, textvariable=self.status, bg=PANEL, fg=DIM,
            font=self.section_font, anchor="w", padx=10,
        )
        self.status_label.pack(side="left", pady=9)
        tk.Entry(
            footer, textvariable=self.command, state="readonly",
            readonlybackground=PANEL, fg=DIM, relief="flat", font=self.meta_font,
        ).pack(side="left", fill="x", expand=True, padx=10)
        self.stop_button = tk.Button(
            footer, text="■ STOP", command=self.stop, state="disabled",
            bg=RED_BG, fg=RED, activebackground="#4A1B17", activeforeground=TEXT,
            relief="flat", font=self.card_font, padx=18,
        )
        self.stop_button.pack(side="right", padx=8, pady=5)

        self._show_view("CONTROL")

    def _nav_item(self, sidebar, name):
        row = tk.Frame(sidebar, bg=SIDEBAR)
        row.pack(fill="x")
        indicator = tk.Frame(row, bg=SIDEBAR, width=4)
        indicator.pack(side="left", fill="y")
        button = tk.Button(
            row, text=name, command=lambda: self._show_view(name), anchor="w",
            bg=SIDEBAR, fg=DIM, activebackground=PANEL, activeforeground=YELLOW,
            relief="flat", font=self.nav_font, padx=16, pady=9, borderwidth=0,
            highlightthickness=0, cursor="hand2",
        )
        button.pack(side="left", fill="x", expand=True)
        self.nav_items[name] = (indicator, button)

    def _show_view(self, name):
        if name not in self.views:
            return
        self._ensure_view(name)
        self.active_view = name
        for frame in self.views.values():
            frame.pack_forget()
        self.views[name].pack(fill="both", expand=True, padx=22, pady=(12, 0))
        for view_name, (indicator, button) in self.nav_items.items():
            active = view_name == name
            indicator.configure(bg=YELLOW if active else SIDEBAR)
            button.configure(fg=YELLOW if active else DIM,
                             bg=PANEL if active else SIDEBAR)

    def _ensure_view(self, name):
        if name in self.built_views:
            return
        self.view_builders[name](self.views[name])
        self.built_views.add(name)

    # -- CONTROL view ---------------------------------------------------------

    def _build_control(self, parent):
        left = tk.Frame(parent, bg=BG, width=480)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(18, 0))

        self._section(left, "LAUNCH")
        for spec in LAUNCHES:
            self._launch_card(left, spec)

        self._section(left, "TRACKING OPTIONS")
        options = tk.Frame(left, bg=PANEL, highlightbackground=EDGE,
                           highlightthickness=1)
        options.pack(fill="x", pady=(0, 8))
        self._checkbox(options, "Multiple people", self.multi_enabled)
        tk.Spinbox(
            options, from_=2, to=6, textvariable=self.multi_people, width=3,
            bg=CARD, fg=TEXT, buttonbackground=CARD, justify="center",
            relief="flat", font=self.body_font,
        ).pack(anchor="w", padx=30, pady=(0, 3))
        self._checkbox(options, "Local Face ID labels (not authentication)", self.face_id)
        self._checkbox(options, "Auto-orbit 3D camera", self.auto_orbit)
        self._checkbox(options, "Limb speed heat", self.limb_heat)
        self._entry_row(options, "Primary name", self.primary_person)

        self._section(left, "LOCAL FACE GALLERY")
        face = tk.Frame(left, bg=PANEL, highlightbackground=EDGE,
                        highlightthickness=1)
        face.pack(fill="x")
        self._entry_row(face, "Name", self.enroll_name)
        self._entry_row(face, "Camera", self.camera_source)
        actions = tk.Frame(face, bg=PANEL)
        actions.pack(fill="x", padx=8, pady=(4, 8))
        self._action_button(actions, "DOWNLOAD MODELS", self.setup_models,
                            solid=False).pack(side="left")
        self._action_button(actions, "ENROLL", self.enroll_face,
                            solid=True).pack(side="left", padx=6)
        self._action_button(actions, "LIST", self.list_faces,
                            solid=False, dim=True).pack(side="left")

        self._section(right, "SYSTEM READINESS")
        self.readiness_frame = tk.Frame(right, bg=BG)
        self.readiness_frame.pack(fill="x", pady=(0, 2))
        self._render_readiness()

        self._section(right, "MISSION LOG")
        self.log = tk.Text(
            right, bg=LOG_BG, fg=TEXT, font=self.log_font, relief="flat",
            state="disabled", wrap="word", padx=12, pady=10,
            highlightbackground=EDGE, highlightthickness=1,
        )
        self.log.pack(fill="both", expand=True, pady=(0, 4))
        for tag, color in (("sys", YELLOW), ("err", RED), ("cmd", YELLOW_HOVER),
                           ("dim", DIM)):
            self.log.tag_configure(tag, foreground=color)

    def _render_readiness(self):
        """Refresh file/device readiness without opening cameras or ML models."""
        if not hasattr(self, "readiness_frame"):
            return
        for child in self.readiness_frame.winfo_children():
            child.destroy()

        readiness = load_readiness()
        items = (
            ("CAMERAS", readiness["cameras"]),
            ("CALIBRATION", readiness["calibration"]),
            ("FACE MODELS", readiness["face_models"]),
            ("GALLERY", readiness["gallery"]),
        )
        for column, (label, state) in enumerate(items):
            self.readiness_frame.columnconfigure(column, weight=1, uniform="ready")
            card = tk.Frame(
                self.readiness_frame, bg=CARD,
                highlightbackground=EDGE, highlightthickness=1,
            )
            card.grid(
                row=0, column=column, sticky="nsew",
                padx=(0 if column == 0 else 6, 0),
            )
            indicator_color = YELLOW if state["ready"] else FAINT
            tk.Frame(card, bg=indicator_color, height=3).pack(fill="x")
            tk.Label(
                card, text=label, bg=CARD, fg=DIM,
                font=self.small_font, anchor="w",
            ).pack(fill="x", padx=9, pady=(7, 1))
            tk.Label(
                card, text=state["status"], bg=CARD, fg=indicator_color,
                font=self.meta_font, anchor="w",
            ).pack(fill="x", padx=9, pady=(0, 8))

    def _section(self, parent, text):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(10, 5))
        tk.Frame(row, bg=YELLOW, width=4, height=12).pack(side="left")
        tk.Label(row, text="  " + text, bg=BG, fg=DIM, font=self.section_font,
                 anchor="w").pack(side="left")

    def _launch_card(self, parent, spec):
        frame = tk.Frame(parent, bg=CARD, highlightbackground=EDGE,
                         highlightthickness=1)
        frame.pack(fill="x", pady=(0, 7))
        tk.Frame(frame, bg=spec.accent, width=4).pack(side="left", fill="y")
        inner = tk.Frame(frame, bg=CARD)
        inner.pack(side="left", fill="both", expand=True)
        button = tk.Button(
            inner, text="▶  " + spec.title, command=lambda: self.launch_live(spec),
            anchor="w", bg=CARD, fg=TEXT, activebackground=CARD_HOVER,
            activeforeground=YELLOW, relief="flat", font=self.card_font,
            padx=10, cursor="hand2",
        )
        button.pack(fill="x", pady=(6, 0))
        tk.Label(inner, text=spec.description, bg=CARD, fg=DIM,
                 font=self.body_font, anchor="w", padx=14).pack(fill="x",
                                                                pady=(0, 7))
        for widget in (frame, inner, button):
            widget.bind("<Enter>", lambda _e, b=button: b.configure(fg=YELLOW))
            widget.bind("<Leave>", lambda _e, b=button: b.configure(fg=TEXT))
        self.launch_buttons.append(button)

    def _checkbox(self, parent, text, variable):
        tk.Checkbutton(
            parent, text=text, variable=variable, bg=PANEL, fg=TEXT,
            activebackground=PANEL, activeforeground=YELLOW, selectcolor=CARD,
            relief="flat", font=self.body_font, anchor="w",
        ).pack(fill="x", padx=8, pady=2)

    def _entry_row(self, parent, label, variable):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=8, pady=3)
        tk.Label(row, text=label, width=13, anchor="w", bg=PANEL, fg=DIM,
                 font=self.body_font).pack(side="left")
        tk.Entry(row, textvariable=variable, bg=CARD, fg=TEXT,
                 insertbackground=YELLOW, relief="flat",
                 font=self.body_font).pack(side="left", fill="x", expand=True,
                                           ipady=2)

    def _action_button(self, parent, text, command, *, solid, dim=False):
        if solid:
            button = tk.Button(
                parent, text=text, command=command, bg=YELLOW, fg="#000000",
                activebackground=YELLOW_HOVER, activeforeground="#000000",
                relief="flat", font=self.section_font, padx=10, pady=4,
                cursor="hand2",
            )
        else:
            button = tk.Button(
                parent, text=text, command=command, bg=CARD,
                fg=FAINT if dim else YELLOW,
                activebackground=CARD_HOVER, activeforeground=TEXT,
                relief="flat", font=self.section_font, padx=10, pady=4,
                cursor="hand2",
            )
        self.launch_buttons.append(button)
        return button

    # -- ANALYTICS view -------------------------------------------------------

    def _build_analytics(self, parent):
        self.analytics_frame = parent
        self._render_analytics()

    def _render_analytics(self):
        parent = self.analytics_frame
        if self.analytics_paint_job is not None:
            try:
                parent.after_cancel(self.analytics_paint_job)
            except tk.TclError:
                pass
            self.analytics_paint_job = None
        for child in parent.winfo_children():
            child.destroy()
        data = load_analytics()

        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(2, 10))
        tk.Label(head, text="ANALYTICS", bg=BG, fg=TEXT,
                 font=self.title_font).pack(side="left")
        tk.Label(
            head,
            text=f"   {data.get('athlete', '')} · {data.get('date_range', '')}",
            bg=BG, fg=FAINT, font=self.body_font,
        ).pack(side="left", pady=(8, 0))
        tk.Button(head, text="⟳ REFRESH", command=self._render_analytics,
                  bg=CARD, fg=YELLOW, activebackground=CARD_HOVER,
                  activeforeground=TEXT, relief="flat", font=self.section_font,
                  padx=10, cursor="hand2").pack(side="right")

        if data.get("demo"):
            self._demo_banner(parent, data["source"])
        else:
            self._source_banner(parent, data["source"], data["updated_at"])

        kpis = tk.Frame(parent, bg=BG)
        kpis.pack(fill="x", pady=(6, 12))
        delta = _finite_number(data.get("rating_delta_pct"))
        delta_text = (
            f"▲ {delta:.0f}%" if delta is not None and delta > 0
            else f"▼ {abs(delta):.0f}%" if delta is not None and delta < 0
            else "—"
        )
        cards = (
            ("LEVEL", format_metric(data.get("level"), "{:.0f}"), "current tier"),
            ("EXACTNESS", format_metric(data.get("exactness_pct"), "{:.0f} %"),
             "hit precision"),
            ("QUICKNESS", format_metric(data.get("quickness_s"), "{:.2f} s"),
             "reaction to launch"),
            ("PROGRESS", format_metric(data.get("progress_pct"), "{:.0f}%"),
             "toward next level"),
            ("RATING", format_metric(data.get("rating"), "{:.0f}"), delta_text),
        )
        for i, (label, value, sub) in enumerate(cards):
            kpis.columnconfigure(i, weight=1, uniform="kpi")
            card = tk.Frame(kpis, bg=CARD, highlightbackground=EDGE,
                            highlightthickness=1)
            card.grid(row=0, column=i, sticky="nsew",
                      padx=(0 if i == 0 else 8, 0))
            tk.Label(card, text=label, bg=CARD, fg=DIM,
                     font=self.section_font).pack(anchor="w", padx=14,
                                                  pady=(12, 0))
            tk.Label(card, text=value, bg=CARD, fg=YELLOW,
                     font=self.kpi_font).pack(anchor="w", padx=14)
            sub_color = (
                GREEN if sub.startswith("▲")
                else RED if sub.startswith("▼")
                else FAINT
            )
            tk.Label(card, text=sub, bg=CARD, fg=sub_color,
                     font=self.small_font).pack(anchor="w", padx=14,
                                                pady=(0, 12))

        charts = tk.Frame(parent, bg=BG)
        charts.pack(fill="both", expand=True)
        trend_card = tk.Frame(charts, bg=CARD, highlightbackground=EDGE,
                              highlightthickness=1)
        trend_card.pack(side="left", fill="both", expand=True)
        tk.Label(trend_card, text="RATING — LAST SESSIONS", bg=CARD, fg=DIM,
                 font=self.section_font).pack(anchor="w", padx=14, pady=(12, 4))
        trend_canvas = tk.Canvas(trend_card, bg=CARD, width=560, height=250,
                                 highlightthickness=0)
        trend_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        radar_card = tk.Frame(charts, bg=CARD, highlightbackground=EDGE,
                              highlightthickness=1)
        radar_card.pack(side="left", fill="y", padx=(12, 0))
        tk.Label(radar_card, text="PERFORMANCE INDICATORS", bg=CARD, fg=DIM,
                 font=self.section_font).pack(anchor="w", padx=14, pady=(12, 4))
        radar_canvas = tk.Canvas(radar_card, bg=CARD, width=330, height=250,
                                 highlightthickness=0)
        radar_canvas.pack(padx=10, pady=(0, 10))

        def paint(_event=None):
            width = max(trend_canvas.winfo_width(), 300)
            height = max(trend_canvas.winfo_height(), 180)
            draw_trend_chart(trend_canvas, data.get("trend", []), width=width,
                             height=height, font=self.small_font)
            draw_radar_chart(radar_canvas, data.get("radar", {}),
                             width=330, height=250,
                             font=self.small_font)

        def paint_if_alive():
            self.analytics_paint_job = None
            try:
                if trend_canvas.winfo_exists() and radar_canvas.winfo_exists():
                    paint()
            except tk.TclError:
                pass

        trend_canvas.bind("<Configure>", paint)
        self.analytics_paint_job = parent.after_idle(paint_if_alive)

    def _demo_banner(self, parent, source):
        banner = tk.Frame(parent, bg=PANEL, highlightbackground=YELLOW_SHADE,
                          highlightthickness=1)
        banner.pack(fill="x", pady=(0, 4))
        tk.Frame(banner, bg=YELLOW, width=4).pack(side="left", fill="y")
        tk.Label(
            banner,
            text="PREVIEW · DEMO DATA — live session data will replace this "
                 "preview when available\nsource: " + str(source),
            bg=PANEL, fg=DIM, font=self.meta_font, justify="left", anchor="w",
            padx=10, pady=6,
        ).pack(side="left", fill="x")

    def _source_banner(self, parent, source, updated_at):
        banner = tk.Frame(parent, bg=PANEL, highlightbackground=EDGE,
                          highlightthickness=1)
        banner.pack(fill="x", pady=(0, 4))
        tk.Frame(banner, bg=GREEN, width=4).pack(side="left", fill="y")
        tk.Label(
            banner,
            text=f"LIVE DATA · UPDATED {updated_at}\nsource: {source}",
            bg=PANEL, fg=DIM, font=self.meta_font, justify="left", anchor="w",
            padx=10, pady=6,
        ).pack(side="left", fill="x")

    # -- MATCHES view -----------------------------------------------------------

    def _build_matches(self, parent):
        self.matches_frame = parent
        self._render_matches()

    def _render_matches(self):
        parent = self.matches_frame
        for child in parent.winfo_children():
            child.destroy()
        data = load_matches()
        analytics = load_analytics()

        head = tk.Frame(parent, bg=BG)
        head.pack(fill="x", pady=(2, 6))
        tk.Label(head, text="MATCHES", bg=BG, fg=TEXT,
                 font=self.title_font).pack(side="left")
        if data.get("demo"):
            summary = "   PREVIEW SESSION"
        elif analytics.get("demo"):
            summary = "   LIVE SESSION · ATHLETE METRICS NOT AVAILABLE"
        else:
            summary = (
                "   LEVEL " + format_metric(analytics.get("level"), "{:.0f}")
                + "  ·  EXACTNESS "
                + format_metric(analytics.get("exactness_pct"), "{:.0f}%")
                + "  ·  QUICKNESS "
                + format_metric(analytics.get("quickness_s"), "{:.2f}s")
            )
        tk.Label(head, text=summary, bg=BG, fg=FAINT,
                 font=self.body_font).pack(side="left", pady=(8, 0))
        tk.Button(head, text="⟳ REFRESH", command=self._render_matches,
                  bg=CARD, fg=YELLOW, activebackground=CARD_HOVER,
                  activeforeground=TEXT, relief="flat", font=self.section_font,
                  padx=10, cursor="hand2").pack(side="right")

        if data.get("demo"):
            self._demo_banner(parent, data["source"])
        else:
            self._source_banner(parent, data["source"], data["updated_at"])

        table_card = tk.Frame(parent, bg=CARD, highlightbackground=EDGE,
                              highlightthickness=1)
        table_card.pack(fill="both", expand=True, pady=(6, 4))
        tk.Label(table_card, text="BALLS", bg=CARD, fg=DIM,
                 font=self.section_font).pack(anchor="w", padx=14, pady=(12, 6))
        columns = (
            "num", "gun", "target", "speed", "angle", "spin", "result", "time"
        )
        tree = ttk.Treeview(table_card, columns=columns, show="headings",
                            style="Kairat.Treeview", selectmode="none")
        headings = (
            ("num", "#", 42), ("gun", "GUN", 75),
            ("target", "TARGET", 280), ("speed", "SPEED", 90),
            ("angle", "ANGLE", 75), ("spin", "SPIN", 65),
            ("result", "RESULT", 90), ("time", "TIME", 120),
        )
        for key, text, width in headings:
            tree.heading(key, text=text)
            tree.column(key, width=width, anchor="w",
                        stretch=(key == "target"))
        tree.tag_configure("ok", foreground=TEXT)
        tree.tag_configure("fail", foreground=RED)
        tree.tag_configure("neutral", foreground=DIM)
        for i, row in enumerate(data["rows"], start=1):
            tag = ("fail" if row["result"] == "✗"
                   else "ok" if row["result"] == "✓" else "neutral")
            display_result = (
                "✓ HIT" if row["result"] == "✓"
                else "✗ MISS" if row["result"] == "✗"
                else row["result"]
            )
            tree.insert("", "end", values=(
                i, row["gun"], row["target"], row["speed"], row["angle"],
                row.get("spin", "—"), display_result, row["time"],
            ), tags=(tag,))
        scroll = ttk.Scrollbar(table_card, orient="vertical",
                               command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 6), pady=(0, 10))
        tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 10))

    # -- actions ----------------------------------------------------------------

    def launch_live(self, spec):
        try:
            people = parse_multi_people(
                self.multi_people.get(), self.multi_enabled.get()
            )
        except ValueError as exc:
            self._log(f"Invalid people count: {exc}", "err")
            return
        command = build_live_command(
            repo_root=REPO_ROOT,
            script=spec.script,
            multi_people=people,
            face_id=self.face_id.get(),
            auto_orbit=self.auto_orbit.get(),
            limb_heat=self.limb_heat.get(),
            primary_person=self.primary_person.get(),
        )
        self._spawn(command, spec.title)

    def setup_models(self):
        self._spawn(build_model_setup_command(REPO_ROOT, self.python),
                    "FACE MODEL SETUP")

    def enroll_face(self):
        name = self.enroll_name.get().strip()
        if not name:
            self._log("Enter a name before enrollment", "err")
            return
        command = build_face_enroll_command(
            repo_root=REPO_ROOT, python=self.python, name=name,
            camera=self.camera_source.get().strip() or "0",
        )
        self._spawn(command, f"ENROLL {name}")

    def list_faces(self):
        command = [
            self.python,
            str(REPO_ROOT / "Parallel_working/scripts/face_enroll.py"),
            "--list",
        ]
        self._spawn(command, "FACE GALLERY")

    # -- process management -------------------------------------------------------

    def _spawn(self, command, title):
        current_pgid = getattr(self, "proc_pgid", None)
        if current_pgid is not None and process_group_alive(current_pgid):
            self._log("A pipeline is already running; stop it first", "err")
            return
        if self.proc is not None and current_pgid is not None:
            code = self.proc_exit_code
            if code is None:
                code = self.proc.poll()
            self._finish_current_process(0 if code is None else code)
        try:
            process = subprocess.Popen(
                command,
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
                env=dict(os.environ, PYTHONUNBUFFERED="1"),
            )
        except OSError as exc:
            self._log(f"Launch failed: {exc}", "err")
            self.proc = None
            self.proc_pgid = None
            self.proc_exit_code = None
            return
        self._cancel_shutdown_timer()
        self.proc_generation = getattr(self, "proc_generation", 0) + 1
        generation = self.proc_generation
        self.proc = process
        self.proc_pgid = process.pid
        self.proc_exit_code = None
        self.shutdown_stage = 0
        self.proc_title = title
        self.command.set(shlex.join(command))
        self._set_status_running(title)
        self._log("$ " + shlex.join(command), "cmd")
        self._set_interlock(True)
        self._show_view("CONTROL")
        threading.Thread(target=self._read_child, args=(process, generation),
                         daemon=True).start()

    def _read_child(self, process, generation):
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self.messages.put(
                        ("line", process, generation, line.rstrip())
                    )
        finally:
            self.messages.put(("exit", process, generation, process.wait()))

    def stop(self):
        process = self.proc
        pgid = self.proc_pgid
        if process is None or pgid is None:
            return
        self._advance_shutdown(process, self.proc_generation, pgid)

    def _advance_shutdown(self, process, generation, pgid):
        if (
            self.proc is not process
            or self.proc_generation != generation
            or self.proc_pgid != pgid
        ):
            return
        if not process_group_alive(pgid):
            self._finish_current_process(self._current_exit_code(process))
            return

        stage = self.shutdown_stage
        if stage == 0:
            sig = signal.SIGINT
            next_stage = 1
            delay = 10_000
            message = "SIGINT sent; waiting for clean shutdown"
        elif stage == 1:
            sig = signal.SIGTERM
            next_stage = 2
            delay = 3_000
            message = "SIGTERM sent; waiting for forced shutdown"
        elif stage == 2:
            sig = signal.SIGKILL
            next_stage = 3
            delay = None
            message = "SIGKILL sent; waiting for process exit"
        else:
            return

        self._cancel_shutdown_timer()
        self.shutdown_stage = next_stage
        try:
            os.killpg(pgid, sig)
            self._log(message, "sys")
        except OSError as exc:
            self._log(f"Shutdown signal failed: {exc}", "err")

        if not process_group_alive(pgid):
            self._finish_current_process(self._current_exit_code(process))
        elif delay is not None:
            self.shutdown_timer = self.root.after(
                delay,
                self._shutdown_timeout,
                process,
                generation,
                pgid,
                next_stage,
            )
        elif next_stage == 3:
            self.stop_button.configure(state="disabled")

    def _shutdown_timeout(self, process, generation, pgid, expected_stage):
        if (
            self.proc is not process
            or self.proc_generation != generation
            or self.proc_pgid != pgid
            or self.shutdown_stage != expected_stage
        ):
            return
        self.shutdown_timer = None
        self._advance_shutdown(process, generation, pgid)

    def _current_exit_code(self, process):
        code = self.proc_exit_code
        if code is None:
            code = process.poll()
        return 0 if code is None else int(code)

    def _finish_current_process(self, code):
        code = int(code)
        self._log(f"{self.proc_title} exited with code {code}",
                  "sys" if code in (0, 130, -2) else "err")
        self._set_status_idle(
            "IDLE" if code in (0, 130, -2) else f"EXITED {code}")
        self._cancel_shutdown_timer()
        self.proc = None
        self.proc_pgid = None
        self.proc_exit_code = None
        self.shutdown_stage = 0
        self._set_interlock(False)
        self._render_readiness()
        if self.closing:
            self.root.destroy()
            return True
        return False

    def _cancel_shutdown_timer(self):
        timer = getattr(self, "shutdown_timer", None)
        if timer is None:
            return
        self.shutdown_timer = None
        try:
            self.root.after_cancel(timer)
        except tk.TclError:
            pass

    def _set_status_running(self, title):
        self.status.set("● RUNNING  /  " + title)
        self.status_label.configure(fg="#000000", bg=YELLOW)

    def _set_status_idle(self, text="IDLE"):
        self.status.set(text)
        self.status_label.configure(
            fg=DIM if text == "IDLE" else RED, bg=PANEL)

    def _set_interlock(self, running):
        state = "disabled" if running else "normal"
        for button in self.launch_buttons:
            button.configure(state=state)
        self.stop_button.configure(state="normal" if running else "disabled")

    def _pump(self):
        destroy_after_exit = False
        try:
            while True:
                kind, process, generation, payload = self.messages.get_nowait()
                if (
                    process is not self.proc
                    or generation != self.proc_generation
                ):
                    continue
                if kind == "line":
                    self._log(str(payload))
                else:
                    code = int(payload)
                    self.proc_exit_code = code
                    if process_group_alive(self.proc_pgid):
                        self._log(
                            f"{self.proc_title} leader exited with code {code}; "
                            "process group still running",
                            "sys",
                        )
                    else:
                        destroy_after_exit = self._finish_current_process(code)
        except queue.Empty:
            pass
        if (
            self.proc is not None
            and self.proc_exit_code is not None
            and not process_group_alive(self.proc_pgid)
        ):
            destroy_after_exit = self._finish_current_process(
                self.proc_exit_code
            )
        if destroy_after_exit:
            return
        self.root.after(60, self._pump)

    def _log(self, text, tag=None):
        self.log.configure(state="normal")
        prefix = time.strftime("%H:%M:%S ") if tag else ""
        self.log.insert("end", prefix + str(text) + "\n", tag or "")
        self.log.configure(state="disabled")
        self.log.see("end")

    def close(self):
        self.closing = True
        if self.proc is None or self.proc_pgid is None:
            self._cancel_shutdown_timer()
            self.root.destroy()
            return
        self.stop()


def build_parser():
    parser = argparse.ArgumentParser(description="Project Cam desktop control center")
    parser.add_argument("--check", action="store_true",
                        help="Print resolved paths without opening a display.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.check:
        print("Project Cam control center")
        print(f"repo={REPO_ROOT}")
        print(f"python={resolve_venv_python()}")
        print(f"DISPLAY={os.environ.get('DISPLAY', '(unset)')}")
        for spec in LAUNCHES:
            state = "OK" if (REPO_ROOT / spec.script).is_file() else "MISSING"
            print(f"{state} {spec.script}")
        analytics = load_analytics()
        matches = load_matches()
        readiness = load_readiness()
        print(f"analytics={'demo' if analytics['demo'] else analytics['source']}")
        print(f"matches={'demo' if matches['demo'] else matches['source']}")
        print("readiness=" + ", ".join(
            f"{name}:{state['status']}" for name, state in readiness.items()
        ))
        return 0
    try:
        root = tk.Tk(className="project-cam")
    except tk.TclError as exc:
        print(f"Cannot open Project Cam window: {exc}", file=sys.stderr)
        return 1
    ArenaControlCenter(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
