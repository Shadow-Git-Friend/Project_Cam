#!/usr/bin/env python3
"""Standalone camNorth detector for the static 3x3 south-wall projector grid.

This script does not control the projector. It watches the projected south-wall
grid through camNorth, maps the detected ball center onto the south-wall plane,
and counts a goal when the ball is inside a grid cell and suddenly decelerates.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

import cv2
import numpy as np
import yaml

PROJECTOR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROJECTOR_DIR.parents[1]
sys.path.insert(0, str(PROJECTOR_DIR))

from static_grid_goal_logic import (  # noqa: E402
    SOUTH_WALL_U_MAX_MM,
    SOUTH_WALL_V_MAX_MM,
    SouthWallMapper,
    StaticGridGoalLogic,
    WallRect,
    target_grid_rectangles,
    wall_bounds_from_homography,
)
from trackers.persistent_tracker_v3 import PersistentTrackerV3  # noqa: E402


def _project_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def _default_model_path() -> Path:
    engine = PROJECT_ROOT / "models/ball/yolo26m-672.engine"
    if engine.exists():
        return engine
    return PROJECT_ROOT / "models/ball/yolo26m-672.pt"


def _load_camera_device(config_path: Path, cam_role: str) -> str | None:
    if not config_path.exists():
        return None
    with config_path.open("r", encoding="utf-8") as fp:
        cfg = yaml.safe_load(fp) or {}
    cam_cfg = (cfg.get("cameras") or {}).get(cam_role) or {}
    return cam_cfg.get("device")


def _open_capture(source: str | int, width: int, height: int, fps: int, fourcc: str):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened() and isinstance(source, str) and source.isdigit():
        cap = cv2.VideoCapture(int(source))
    if not cap.isOpened():
        return None

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
    cap.set(cv2.CAP_PROP_FPS, int(fps))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def _choose_camera_source(args) -> str | int:
    if args.camera is not None:
        return int(args.camera) if str(args.camera).isdigit() else args.camera
    device = _load_camera_device(_project_path(args.camera_config), args.cam_role)
    if device:
        return device
    return int(args.cam_index)


def _raw_detections_from_yolo(results, min_side_px: float, max_side_px: float) -> list[dict]:
    detections: list[dict] = []
    for result in results:
        if result.boxes is None:
            continue
        xyxy_arr = result.boxes.xyxy.cpu().numpy()
        conf_arr = result.boxes.conf.cpu().numpy()
        for i in range(len(conf_arr)):
            x1, y1, x2, y2 = [float(v) for v in xyxy_arr[i]]
            side = max(x2 - x1, y2 - y1)
            if min_side_px > 0 and side < min_side_px:
                continue
            if max_side_px > 0 and side > max_side_px:
                continue
            detections.append(
                {
                    "bbox": np.array([x1, y1, x2, y2], dtype=np.float64),
                    "conf": float(conf_arr[i]),
                }
            )
    return detections


def _draw_grid(frame, mapper: SouthWallMapper, rects: list[WallRect], active_label: str | None):
    for rect in rects:
        pts = np.array(
            [
                mapper.wall_to_pixel(rect.u_min, rect.v_min),
                mapper.wall_to_pixel(rect.u_max, rect.v_min),
                mapper.wall_to_pixel(rect.u_max, rect.v_max),
                mapper.wall_to_pixel(rect.u_min, rect.v_max),
            ],
            dtype=np.int32,
        )
        color = (0, 240, 80) if active_label == rect.label else (80, 180, 255)
        cv2.polylines(frame, [pts], isClosed=True, color=color, thickness=2)
        cu, cv = rect.center
        tx, ty = mapper.wall_to_pixel(cu, cv)
        cv2.putText(
            frame,
            rect.label,
            (tx - 16, ty + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )


def _draw_hud(frame, score: int, last_event, wall_uv, fps_est: float):
    cv2.rectangle(frame, (8, 8), (470, 100), (0, 0, 0), -1)
    cv2.putText(
        frame,
        f"Static 3x3 goals: {score}",
        (18, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (230, 240, 245),
        2,
    )
    if wall_uv is not None:
        u, v = wall_uv
        cv2.putText(
            frame,
            f"south wall U={u:5.0f}mm V={v:5.0f}mm",
            (18, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (180, 220, 255),
            1,
        )
    if last_event is not None:
        cv2.putText(
            frame,
            f"last: {last_event.zone_label} {last_event.speed_mm_s:.0f}/{last_event.peak_speed_mm_s:.0f} mm/s",
            (18, 84),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (80, 255, 120),
            1,
        )
    cv2.putText(
        frame,
        f"{fps_est:4.1f} FPS",
        (frame.shape[1] - 115, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (220, 220, 220),
        2,
    )


def _write_goal_event(path: Path | None, event) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(
            json.dumps(
                {
                    "t": event.t_sec,
                    "zone": event.zone_label,
                    "u_mm": event.u_mm,
                    "v_mm": event.v_mm,
                    "speed_mm_s": event.speed_mm_s,
                    "peak_speed_mm_s": event.peak_speed_mm_s,
                    "track_id": event.track_id,
                }
            )
            + "\n"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Standalone camNorth ball detector for static 3x3 projector goals."
    )
    ap.add_argument("--camera", default=None, help="Camera index or device path. Defaults to camNorth in cameras.yaml.")
    ap.add_argument("--cam-index", type=int, default=0, help="Fallback camera index if camNorth device is unavailable.")
    ap.add_argument("--cam-role", default="camNorth")
    ap.add_argument("--camera-config", default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--intrinsics", default="Remounted_West_East/cal/intrinsics/camNorth_intrinsics.json")
    ap.add_argument("--extrinsics", default="Remounted_West_East/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--grid-homography", default=str(PROJECTOR_DIR / "homography.json"))
    ap.add_argument("--model", default=str(_default_model_path()))
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--imgsz", type=int, default=672)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--min-box-side-px", type=float, default=0.0)
    ap.add_argument("--max-box-side-px", type=float, default=120.0)
    ap.add_argument("--reid-gate-px", type=float, default=180.0)
    ap.add_argument("--jitter-thresh-px", type=float, default=3.0)
    ap.add_argument("--max-missed-frames", type=int, default=6)
    ap.add_argument("--min-flight-speed-mm-s", type=float, default=1500.0)
    ap.add_argument("--decel-ratio", type=float, default=0.40)
    ap.add_argument("--hit-pad-mm", type=float, default=80.0)
    ap.add_argument("--cooldown-s", type=float, default=0.8)
    ap.add_argument("--active-label", default="", help="Optional single active zone label, e.g. A1. Empty counts all 9 zones.")
    ap.add_argument("--goal-log-jsonl", default="", help="Optional JSONL path for goal events.")
    ap.add_argument("--no-show", action="store_true")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()
    model_path = _project_path(args.model)
    if not model_path.exists():
        print(f"[ERROR] Ball model not found: {model_path}")
        return 2

    mapper = SouthWallMapper.from_files(
        _project_path(args.intrinsics),
        _project_path(args.extrinsics),
        cam_role=args.cam_role,
    )
    bounds = wall_bounds_from_homography(_project_path(args.grid_homography))
    if bounds is None:
        rects = target_grid_rectangles(SOUTH_WALL_U_MAX_MM, SOUTH_WALL_V_MAX_MM)
        print("[WARN] Grid using full south wall bounds.")
    else:
        rects = target_grid_rectangles(
            u_min=bounds.u_min,
            u_max=bounds.u_max,
            v_min=bounds.v_min,
            v_max=bounds.v_max,
        )
        print(
            "[CAL] Grid wall bounds from homography: "
            f"U={bounds.u_min:.0f}..{bounds.u_max:.0f}mm "
            f"V={bounds.v_min:.0f}..{bounds.v_max:.0f}mm"
        )
    active_labels = [args.active_label] if args.active_label else None
    goal_logic = StaticGridGoalLogic(
        rects=rects,
        min_flight_speed_mm_s=args.min_flight_speed_mm_s,
        decel_ratio=args.decel_ratio,
        cooldown_s=args.cooldown_s,
        hit_pad_mm=args.hit_pad_mm,
        active_labels=active_labels,
    )

    source = _choose_camera_source(args)
    cap = _open_capture(source, args.width, args.height, args.fps, args.fourcc)
    if cap is None:
        print(f"[ERROR] Cannot open camera source: {source}")
        return 2

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM] {args.cam_role}: {source} -> {actual_w}x{actual_h}")
    if (actual_w, actual_h) != (args.width, args.height):
        print(
            "[WARN] Capture size differs from requested calibration size "
            f"({args.width}x{args.height}); wall mapping may drift."
        )

    from ultralytics import YOLO

    print(f"[MODEL] Loading {model_path}")
    model = YOLO(str(model_path))
    print("[MODEL] Ready")

    tracker = PersistentTrackerV3(
        {
            "jitter_thresh": args.jitter_thresh_px,
            "reid_gate_px": args.reid_gate_px,
            "max_missed_frames": args.max_missed_frames,
        }
    )
    trails = defaultdict(lambda: deque(maxlen=24))
    score = 0
    last_event = None
    last_wall_uv = None
    goal_log_path = _project_path(args.goal_log_jsonl) if args.goal_log_jsonl else None
    fps_est = 0.0
    t_prev = time.time()

    print("[INFO] Press q in the preview window to quit." if not args.no_show else "[INFO] Running headless. Press Ctrl+C to quit.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            now = time.time()
            dt = max(1e-6, now - t_prev)
            t_prev = now
            fps_est = 0.92 * fps_est + 0.08 * (1.0 / dt)

            results = model(
                frame,
                conf=args.conf,
                imgsz=args.imgsz,
                classes=[0],
                verbose=False,
                device=args.device,
            )
            detections = _raw_detections_from_yolo(
                results,
                min_side_px=args.min_box_side_px,
                max_side_px=args.max_box_side_px,
            )
            tracks = tracker.update(detections)
            display = None if args.no_show else frame.copy()

            if display is not None:
                _draw_grid(display, mapper, rects, args.active_label or None)

            live_ids = set()
            for track in tracks:
                if track.get("missed", 0) > 0:
                    continue
                tid = int(track["id"])
                live_ids.add(tid)
                cx, cy = [float(v) for v in track["centroid"]]
                mapped = mapper.pixel_to_wall((cx, cy))
                if mapped is None:
                    continue
                u_mm, v_mm, _point = mapped
                last_wall_uv = (u_mm, v_mm)
                event = goal_logic.update(now, u_mm, v_mm, track_id=tid)
                if event is not None:
                    score += 1
                    last_event = event
                    _write_goal_event(goal_log_path, event)
                    print(
                        f"[GOAL] #{score} zone={event.zone_label} "
                        f"u={event.u_mm:.0f} v={event.v_mm:.0f} "
                        f"speed={event.speed_mm_s:.0f}/{event.peak_speed_mm_s:.0f}mm/s "
                        f"track={event.track_id}"
                    )

                trails[tid].append((int(round(cx)), int(round(cy))))
                if display is not None:
                    x1, y1, x2, y2 = [int(round(v)) for v in track["bbox"]]
                    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 230, 90), 2)
                    cv2.circle(display, (int(round(cx)), int(round(cy))), 4, (0, 255, 255), -1)
                    cv2.putText(
                        display,
                        f"#{tid} U={u_mm:.0f} V={v_mm:.0f}",
                        (x1, max(18, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (0, 230, 90),
                        1,
                    )
                    pts = list(trails[tid])
                    for i in range(1, len(pts)):
                        cv2.line(display, pts[i - 1], pts[i], (255, 150, 0), 2)

            for tid in list(trails.keys()):
                if tid not in live_ids and len(trails[tid]) == 0:
                    trails.pop(tid, None)

            if display is not None:
                _draw_hud(display, score, last_event, last_wall_uv, fps_est)
                cv2.imshow("Static Projector Goal Detector - camNorth", display)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
