"""Offline ball-detection sweep on a recorded sequence.

Answers: at what conf threshold and top-K does the current pipeline lose detections?
Reports per-cam detection rate, bbox aspect ratio (motion-blur proxy), and the
delta between current defaults (conf=0.40, top-1) and proposed (conf=0.15, top-3).

Read-only on all inputs. Writes JSONL + stdout summary only.

Example:
    ./venv/bin/python Parallel_working/scripts/ball_detection_analyzer.py \\
        --sequence Parallel_working/output/test_sequences/jump_01 \\
        --model models/ball/yolo26m-672.engine \\
        --conf-sweep 0.10,0.15,0.20,0.25,0.30,0.40 \\
        --topk 3
"""
import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def box_aspect(x1, y1, x2, y2):
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    return max(w, h) / min(w, h)


MOSAIC_CAM_LAYOUT = {
    "camEast":  (0, 0),  # top-left
    "camNorth": (0, 1),  # top-right
    "camSouth": (1, 0),  # bottom-left
    "camWest":  (1, 1),  # bottom-right
}


def iter_mosaic_frames(mosaic_path, tile_w=1280, tile_h=720):
    """Yield (frame_idx, {cam: bgr_image}) from a 2x2 mosaic video.

    Matches make_mosaic() layout: top row [camEast, camNorth], bottom row [camSouth, camWest].
    Note: the mosaic has ball-box overlays burned in from the original live run;
    re-running YOLO on it is still valid because overlays are OUTSIDE the ball.
    """
    cap = cv2.VideoCapture(str(mosaic_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"cannot open mosaic: {mosaic_path}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if W != tile_w * 2 or H != tile_h * 2:
        print(f"[WARN] mosaic size {W}x{H} != expected {tile_w*2}x{tile_h*2}; slicing proportionally")
        tile_w, tile_h = W // 2, H // 2
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        tiles = {}
        for cam, (r, c) in MOSAIC_CAM_LAYOUT.items():
            y0, y1 = r * tile_h, (r + 1) * tile_h
            x0, x1 = c * tile_w, (c + 1) * tile_w
            tiles[cam] = frame[y0:y1, x0:x1].copy()
        yield idx, tiles
        idx += 1
    cap.release()


def run_sweep_mosaic(model, mosaic_path, conf_levels, topk, device, imgsz):
    cams = list(MOSAIC_CAM_LAYOUT.keys())
    min_conf = float(min(conf_levels))
    stats = {
        cam: {c: {"n_frames": 0, "n_det": 0, "n_multi": 0, "confs": [], "aspects": []}
              for c in conf_levels}
        for cam in cams
    }
    records = []
    latencies = []

    # Warmup.
    first_iter = iter_mosaic_frames(mosaic_path)
    _, first_tiles = next(first_iter)
    warm = first_tiles[cams[0]]
    for _ in range(3):
        model(warm, conf=min_conf, device=device, imgsz=imgsz, verbose=False)
    del first_iter

    for frame_idx, tiles in iter_mosaic_frames(mosaic_path):
        # Batch all 4 cams in one call (matches live viewer behavior).
        batch = [tiles[c] for c in cams]
        t0 = time.perf_counter()
        results = model(batch, conf=min_conf, device=device, imgsz=imgsz, verbose=False)
        latencies.append((time.perf_counter() - t0) * 1000.0)

        for cam, r in zip(cams, results):
            boxes = []
            if r.boxes is not None and len(r.boxes) > 0:
                all_conf = r.boxes.conf.cpu().numpy()
                all_xyxy = r.boxes.xyxy.cpu().numpy()
                order = np.argsort(-all_conf)
                for i in order:
                    c = float(all_conf[i])
                    x1, y1, x2, y2 = [float(v) for v in all_xyxy[i]]
                    boxes.append({"conf": c, "xyxy": [x1, y1, x2, y2],
                                  "aspect": box_aspect(x1, y1, x2, y2)})

            for c_thresh in conf_levels:
                kept = [b for b in boxes if b["conf"] >= c_thresh][:topk]
                st = stats[cam][c_thresh]
                st["n_frames"] += 1
                if kept:
                    st["n_det"] += 1
                    st["confs"].append(kept[0]["conf"])
                    st["aspects"].append(kept[0]["aspect"])
                    if len(kept) > 1:
                        st["n_multi"] += 1

            records.append({
                "cam": cam,
                "frame": int(frame_idx),
                "n_boxes_raw": len(boxes),
                "boxes": boxes[:topk],
            })
    return stats, records, latencies


def run_sweep(model, frames_dir, conf_levels, topk, device, imgsz):
    cams = sorted([d.name for d in Path(frames_dir).iterdir() if d.is_dir()])
    min_conf = float(min(conf_levels))

    # Per-(cam, conf) detection stats.
    stats = {
        cam: {c: {"n_frames": 0, "n_det": 0, "n_multi": 0, "confs": [], "aspects": []}
              for c in conf_levels}
        for cam in cams
    }
    # Per-frame records (for later diff between conf levels).
    records = []
    latencies = []

    # Warmup.
    first = sorted((Path(frames_dir) / cams[0]).glob("*.jpg"))[0]
    warm = cv2.imread(str(first))
    for _ in range(3):
        model(warm, conf=min_conf, device=device, imgsz=imgsz, verbose=False)

    for cam in cams:
        cam_dir = Path(frames_dir) / cam
        frames = sorted(cam_dir.glob("*.jpg"))
        for fp in frames:
            img = cv2.imread(str(fp))
            t0 = time.perf_counter()
            r = model(img, conf=min_conf, device=device, imgsz=imgsz, verbose=False)[0]
            latencies.append((time.perf_counter() - t0) * 1000.0)

            boxes = []
            if r.boxes is not None and len(r.boxes) > 0:
                all_conf = r.boxes.conf.cpu().numpy()
                all_xyxy = r.boxes.xyxy.cpu().numpy()
                order = np.argsort(-all_conf)
                for i in order:
                    c = float(all_conf[i])
                    x1, y1, x2, y2 = [float(v) for v in all_xyxy[i]]
                    boxes.append({"conf": c, "xyxy": [x1, y1, x2, y2],
                                  "aspect": box_aspect(x1, y1, x2, y2)})

            for c_thresh in conf_levels:
                kept = [b for b in boxes if b["conf"] >= c_thresh][:topk]
                st = stats[cam][c_thresh]
                st["n_frames"] += 1
                if kept:
                    st["n_det"] += 1
                    st["confs"].append(kept[0]["conf"])
                    st["aspects"].append(kept[0]["aspect"])
                    if len(kept) > 1:
                        st["n_multi"] += 1

            records.append({
                "cam": cam,
                "frame": fp.name,
                "n_boxes_raw": len(boxes),
                "boxes": boxes[:topk],
            })
    return stats, records, latencies


def summarize(stats, conf_levels):
    print(f"\n{'cam':<10} {'conf':>6} {'det_rate':>10} {'n_multi':>8} {'mean_conf':>10} {'mean_aspect':>12}")
    print("-" * 60)
    for cam in sorted(stats.keys()):
        for c in conf_levels:
            s = stats[cam][c]
            rate = s["n_det"] / max(1, s["n_frames"]) * 100.0
            mean_conf = float(np.mean(s["confs"])) if s["confs"] else 0.0
            mean_aspect = float(np.mean(s["aspects"])) if s["aspects"] else 0.0
            print(f"{cam:<10} {c:>6.2f} {rate:>9.1f}% {s['n_multi']:>8} "
                  f"{mean_conf:>10.3f} {mean_aspect:>12.2f}")
    print()
    # Aggregate across cams
    print(f"{'AGG':<10} {'conf':>6} {'det_rate':>10} {'recovered_vs_0.40':>20}")
    print("-" * 50)
    base_rate = None
    for c in conf_levels:
        total_f = sum(stats[cam][c]["n_frames"] for cam in stats)
        total_d = sum(stats[cam][c]["n_det"] for cam in stats)
        rate = total_d / max(1, total_f) * 100.0
        if abs(c - 0.40) < 1e-6:
            base_rate = rate
        delta = f"+{rate - base_rate:.1f}%" if base_rate is not None else "-"
        print(f"{'ALL':<10} {c:>6.2f} {rate:>9.1f}% {delta:>20}")


def high_aspect_frames(records, aspect_thresh=1.5, top_n=10):
    """Surface frames with streaked boxes (motion-blur proxy)."""
    streaks = []
    for r in records:
        for b in r["boxes"]:
            if b["aspect"] >= aspect_thresh:
                streaks.append({"cam": r["cam"], "frame": r["frame"],
                                "conf": b["conf"], "aspect": b["aspect"]})
    streaks.sort(key=lambda s: -s["aspect"])
    print(f"\nTop {top_n} motion-blur candidates (bbox aspect >= {aspect_thresh}):")
    for s in streaks[:top_n]:
        print(f"  {s['cam']:<10} {s['frame']:<25} conf={s['conf']:.3f} aspect={s['aspect']:.2f}")
    return streaks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sequence", default="",
                    help="Path to a test_sequences/<name>/ directory (per-cam frames)")
    ap.add_argument("--mosaic", default="",
                    help="Path to a mosaic2d_*.mp4 recording (2x2 tiled cams)")
    ap.add_argument("--model", default="models/ball/yolo26m-672.engine")
    ap.add_argument("--conf-sweep", default="0.10,0.15,0.20,0.25,0.30,0.40")
    ap.add_argument("--topk", type=int, default=3)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--imgsz", type=int, default=672)
    ap.add_argument("--jsonl-out", default="",
                    help="Optional path to dump per-frame records as JSONL")
    args = ap.parse_args()

    if not args.sequence and not args.mosaic:
        ap.error("provide either --sequence or --mosaic")

    conf_levels = sorted({float(c.strip()) for c in args.conf_sweep.split(",") if c.strip()})

    source = args.mosaic if args.mosaic else args.sequence
    print(f"Source: {source}")
    print(f"Model: {args.model} @ imgsz={args.imgsz} device={args.device}")
    print(f"Conf sweep: {conf_levels} | top-K: {args.topk}")

    model = YOLO(args.model)
    if args.mosaic:
        stats, records, latencies = run_sweep_mosaic(
            model, args.mosaic, conf_levels, args.topk, args.device, args.imgsz,
        )
    else:
        stats, records, latencies = run_sweep(
            model, args.sequence, conf_levels, args.topk, args.device, args.imgsz,
        )

    summarize(stats, conf_levels)
    high_aspect_frames(records)

    print(f"\nInference latency: mean={np.mean(latencies):.1f}ms "
          f"P95={np.percentile(latencies, 95):.1f}ms (n={len(latencies)})")

    if args.jsonl_out:
        out = Path(args.jsonl_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        print(f"\nWrote per-frame records: {out}")
