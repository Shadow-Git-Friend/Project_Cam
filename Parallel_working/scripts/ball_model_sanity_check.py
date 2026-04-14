"""Compare old vs new ball detector on a recorded test sequence.

Reports: detection count, mean confidence, per-camera detection rate, latency.
"""
import argparse, time
from pathlib import Path
import numpy as np
import cv2
from ultralytics import YOLO


def run_model(model_path, frames_dir, conf, device, imgsz):
    model = YOLO(model_path)
    cams = sorted([d.name for d in Path(frames_dir).iterdir() if d.is_dir()])
    stats = {c: {"n_frames": 0, "n_det": 0, "confs": [], "latencies_ms": []} for c in cams}
    # Warmup
    first_frame = sorted((Path(frames_dir) / cams[0]).glob("*.jpg"))[0]
    img = cv2.imread(str(first_frame))
    for _ in range(3):
        model(img, conf=conf, device=device, imgsz=imgsz, verbose=False)

    for cam in cams:
        cam_dir = Path(frames_dir) / cam
        frames = sorted(cam_dir.glob("*.jpg"))
        for fp in frames:
            img = cv2.imread(str(fp))
            t0 = time.perf_counter()
            r = model(img, conf=conf, device=device, imgsz=imgsz, verbose=False)[0]
            dt = (time.perf_counter() - t0) * 1000
            stats[cam]["n_frames"] += 1
            stats[cam]["latencies_ms"].append(dt)
            if r.boxes is not None and len(r.boxes) > 0:
                confs = r.boxes.conf.cpu().numpy()
                best = float(confs.max())
                stats[cam]["n_det"] += 1
                stats[cam]["confs"].append(best)
    return stats


def summarize(label, stats):
    print(f"\n=== {label} ===")
    total_frames = sum(s["n_frames"] for s in stats.values())
    total_det = sum(s["n_det"] for s in stats.values())
    all_conf = [c for s in stats.values() for c in s["confs"]]
    all_lat = [l for s in stats.values() for l in s["latencies_ms"]]
    for cam, s in stats.items():
        rate = s["n_det"] / max(s["n_frames"], 1) * 100
        mean_c = np.mean(s["confs"]) if s["confs"] else 0
        mean_l = np.mean(s["latencies_ms"]) if s["latencies_ms"] else 0
        print(f"  {cam}: det {s['n_det']:>3}/{s['n_frames']:<3} ({rate:5.1f}%)  "
              f"mean_conf={mean_c:.3f}  mean_lat={mean_l:.1f}ms")
    rate = total_det / max(total_frames, 1) * 100
    print(f"  TOTAL: {total_det}/{total_frames} ({rate:.1f}%)  "
          f"mean_conf={np.mean(all_conf) if all_conf else 0:.3f}  "
          f"mean_lat={np.mean(all_lat):.1f}ms  P95_lat={np.percentile(all_lat,95):.1f}ms")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sequence", default="Parallel_working/output/test_sequences/walk_01")
    ap.add_argument("--old", default="archive/04_garage_backup/garage-20260217T113109Z-3-001/garage/y26s_v1_garage.pt")
    ap.add_argument("--new", default="models/ball/yolo26s-672.engine")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--imgsz-old", type=int, default=1280)
    ap.add_argument("--imgsz-new", type=int, default=672)
    args = ap.parse_args()

    print(f"Sequence: {args.sequence} | conf={args.conf} | device={args.device}")
    print(f"OLD: {args.old} @ imgsz={args.imgsz_old}")
    print(f"NEW: {args.new} @ imgsz={args.imgsz_new}")

    old_stats = run_model(args.old, args.sequence, args.conf, args.device, args.imgsz_old)
    summarize("OLD (y26s_v1_garage, 75ep, old garage dataset)", old_stats)
    new_stats = run_model(args.new, args.sequence, args.conf, args.device, args.imgsz_new)
    summarize("NEW (yolo26s-672, 100ep, dataset-main)", new_stats)
