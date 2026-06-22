#!/usr/bin/env python3
"""Render a 2x2 annotated detection mosaic for a recorded test sequence.

This reads:
- a recorded `test_sequences/<name>/` directory with per-camera JPG frames
- an analyzer JSONL file emitted by `ball_detection_analyzer.py`

It can write:
- an `.mp4` mosaic video
- a folder of annotated mosaic frames

This lets the user visually inspect false positives / false negatives frame by
frame.
"""

import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np


CAM_ORDER = ["camEast", "camNorth", "camSouth", "camWest"]
BOX_COLORS = [
    (60, 220, 60),
    (0, 200, 255),
    (0, 128, 255),
]


def frame_sort_key(name):
    match = re.search(r"(\d+)", name)
    if match:
        return int(match.group(1)), name
    return 10**12, name


def load_detections(jsonl_path):
    detections = {}
    with Path(jsonl_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            cam = rec.get("cam")
            frame = rec.get("frame")
            if cam and frame:
                detections[(cam, frame)] = rec
    return detections


def collect_frames(sequence_dir):
    frame_paths = {}
    all_names = set()
    for cam in CAM_ORDER:
        cam_dir = Path(sequence_dir) / cam
        cam_frames = {fp.name: fp for fp in sorted(cam_dir.glob("*.jpg"), key=lambda p: frame_sort_key(p.name))}
        frame_paths[cam] = cam_frames
        all_names.update(cam_frames.keys())
    frame_names = sorted(all_names, key=frame_sort_key)
    return frame_names, frame_paths


def read_metadata_fps(sequence_dir):
    meta_path = Path(sequence_dir) / "metadata.json"
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    fps = data.get("fps")
    if fps is None:
        return None
    try:
        return float(fps)
    except Exception:
        return None


def draw_boxes(tile, record, show_topk, scale_x=1.0, scale_y=1.0):
    boxes = list(record.get("boxes", []))[:show_topk] if record else []
    n_raw = int(record.get("n_boxes_raw", 0)) if record else 0
    h, w = tile.shape[:2]

    for idx, box in enumerate(boxes):
        x1, y1, x2, y2 = box["xyxy"]
        sx1 = x1 * scale_x
        sy1 = y1 * scale_y
        sx2 = x2 * scale_x
        sy2 = y2 * scale_y
        p1 = (max(0, int(round(sx1))), max(0, int(round(sy1))))
        p2 = (min(w - 1, int(round(sx2))), min(h - 1, int(round(sy2))))
        color = BOX_COLORS[min(idx, len(BOX_COLORS) - 1)]
        thickness = 2 if idx == 0 else 1
        cv2.rectangle(tile, p1, p2, color, thickness)
        cx = int(round((sx1 + sx2) * 0.5))
        cy = int(round((sy1 + sy2) * 0.5))
        cx = max(0, min(w - 1, cx))
        cy = max(0, min(h - 1, cy))
        cv2.drawMarker(tile, (cx, cy), color, cv2.MARKER_CROSS, 12, 2)
        label = f"#{idx + 1} {box['conf']:.2f}"
        cv2.putText(tile, label, (p1[0], max(18, p1[1] - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2, cv2.LINE_AA)

    status = f"raw={n_raw} shown={len(boxes)}"
    if not boxes:
        status = "NO DET"
        cv2.rectangle(tile, (0, 0), (w - 1, h - 1), (0, 0, 255), 3)
        cv2.putText(tile, status, (12, h - 14), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 0, 255), 2, cv2.LINE_AA)
    else:
        cv2.putText(tile, status, (12, h - 14), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 220, 255), 2, cv2.LINE_AA)


def build_tile(frame, cam, frame_name, record, tile_w, tile_h, show_topk):
    if frame is None:
        tile = np.zeros((tile_h, tile_w, 3), dtype=np.uint8)
        cv2.putText(tile, "MISSING FRAME", (20, tile_h // 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (0, 0, 255), 2, cv2.LINE_AA)
        scale_x = scale_y = 1.0
    else:
        src_h, src_w = frame.shape[:2]
        tile = cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA)
        scale_x = tile_w / float(src_w)
        scale_y = tile_h / float(src_h)

    cv2.putText(tile, cam, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                (0, 255, 0), 2, cv2.LINE_AA)
    cv2.putText(tile, frame_name, (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 2, cv2.LINE_AA)
    draw_boxes(tile, record, show_topk, scale_x=scale_x, scale_y=scale_y)
    return tile


def main():
    ap = argparse.ArgumentParser(description="Render annotated 2x2 ball-detection mosaics.")
    ap.add_argument("--sequence", required=True, help="Path to a test_sequences/<name>/ directory")
    ap.add_argument("--detections-jsonl", required=True, help="Analyzer JSONL file for this sequence")
    ap.add_argument("--output", default="", help="Output .mp4 path (default: beside the JSONL)")
    ap.add_argument("--output-dir", default="",
                    help="If set, write annotated mosaic frames into this directory")
    ap.add_argument("--fps", type=float, default=0.0, help="Output video FPS (default: metadata.json fps or 15)")
    ap.add_argument("--tile-width", type=int, default=640)
    ap.add_argument("--tile-height", type=int, default=360)
    ap.add_argument("--show-topk", type=int, default=3, help="How many saved boxes to overlay per tile")
    ap.add_argument("--image-ext", choices=["jpg", "png"], default="jpg")
    ap.add_argument("--jpg-quality", type=int, default=95)
    args = ap.parse_args()

    sequence_dir = Path(args.sequence)
    jsonl_path = Path(args.detections_jsonl)
    if not sequence_dir.is_dir():
        raise FileNotFoundError(f"missing sequence directory: {sequence_dir}")
    if not jsonl_path.is_file():
        raise FileNotFoundError(f"missing detections JSONL: {jsonl_path}")

    detections = load_detections(jsonl_path)
    frame_names, frame_paths = collect_frames(sequence_dir)
    if not frame_names:
        raise RuntimeError(f"no frames found under: {sequence_dir}")

    if not args.output and not args.output_dir:
        raise SystemExit("provide --output, --output-dir, or both")

    fps = args.fps if args.fps > 0 else (read_metadata_fps(sequence_dir) or 15.0)
    output_path = Path(args.output) if args.output else None
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    out_w = args.tile_width * 2
    out_h = args.tile_height * 2
    writer = None
    if output_path is not None:
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (out_w, out_h),
        )
        if not writer.isOpened():
            raise RuntimeError(f"failed to open video writer: {output_path}")

    scenario_name = sequence_dir.name
    subtitle = jsonl_path.name
    try:
        for idx, frame_name in enumerate(frame_names):
            panels = []
            for cam in CAM_ORDER:
                fp = frame_paths[cam].get(frame_name)
                frame = cv2.imread(str(fp)) if fp is not None else None
                rec = detections.get((cam, frame_name))
                panels.append(build_tile(frame, cam, frame_name, rec, args.tile_width, args.tile_height, args.show_topk))

            mosaic = np.vstack([np.hstack(panels[:2]), np.hstack(panels[2:])])
            cv2.putText(mosaic, scenario_name, (18, out_h - 44), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(mosaic, subtitle, (18, out_h - 16), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (255, 255, 0), 2, cv2.LINE_AA)
            if writer is not None:
                writer.write(mosaic)
            if output_dir is not None:
                image_name = f"mosaic_{idx:06d}.{args.image_ext}"
                image_path = output_dir / image_name
                if args.image_ext == "jpg":
                    cv2.imwrite(str(image_path), mosaic, [cv2.IMWRITE_JPEG_QUALITY, args.jpg_quality])
                else:
                    cv2.imwrite(str(image_path), mosaic)

            if idx % 50 == 0 or idx == len(frame_names) - 1:
                print(f"[{scenario_name}] wrote frame {idx + 1}/{len(frame_names)}")
    finally:
        if writer is not None:
            writer.release()

    if output_path is not None:
        print(f"Saved annotated mosaic: {output_path}")
    if output_dir is not None:
        print(f"Saved annotated mosaic frames: {output_dir}")


if __name__ == "__main__":
    main()
