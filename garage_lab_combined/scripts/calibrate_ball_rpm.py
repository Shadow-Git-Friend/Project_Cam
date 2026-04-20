"""
Calibrate ball speed (m/s) from a recorded --ball-log-jsonl file.

Workflow:
  1. Set BLM wheels to a target RPM via blm_interactive.py (e.g. `set 15 0 600 600`).
  2. Run the live viewer with `--ball-log-jsonl /path/to/shot.jsonl`.
  3. Fire one or more shots at that RPM. Stop the viewer cleanly.
  4. Run this script to extract the fastest consecutive-frame speed in that JSONL.

Speed extraction:
  For each consecutive pair (i, i+1) where both have `detected=True` and
  valid ball_mm, compute speed = ||p2-p1|| / 1000 / (t2-t1).
  Report the 95th-percentile speed (peak post-launch, before deceleration/collision).

Example:
  ./venv/bin/python garage_lab_combined/scripts/calibrate_ball_rpm.py \
      --log Parallel_working/output/ball_logs/rpm600.jsonl --rpm 600

  Then to record the curve:
  ./venv/bin/python garage_lab_combined/scripts/calibrate_ball_rpm.py \
      --log rpm500.jsonl:500 rpm600.jsonl:600 rpm700.jsonl:700 \
              rpm800.jsonl:800 rpm900.jsonl:900 \
      --write garage_lab_combined/cal/ball_rpm_to_speed.json
"""

import argparse
import json
from pathlib import Path

import numpy as np


def speeds_from_log(path, min_dt=0.01, max_dt=0.2):
    pts = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not rec.get("detected"):
                continue
            bm = rec.get("ball_mm")
            if bm is None:
                continue
            pts.append((float(rec["t"]), np.asarray(bm, dtype=np.float64)))
    speeds = []
    for i in range(1, len(pts)):
        dt = pts[i][0] - pts[i - 1][0]
        if dt < min_dt or dt > max_dt:
            continue
        d = np.linalg.norm(pts[i][1] - pts[i - 1][1]) / 1000.0  # mm -> m
        speeds.append(d / dt)
    return np.array(speeds, dtype=np.float64)


def summarize(speeds):
    if speeds.size == 0:
        return None
    return {
        "n_pairs": int(speeds.size),
        "mean_mps": float(np.mean(speeds)),
        "median_mps": float(np.median(speeds)),
        "p95_mps": float(np.percentile(speeds, 95)),
        "max_mps": float(np.max(speeds)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", nargs="+", required=True,
                    help="Path to JSONL file. For curve mode use 'path:rpm' pairs.")
    ap.add_argument("--rpm", type=int, default=None, help="RPM for single-log mode.")
    ap.add_argument("--write", default="",
                    help="Write RPM->speed curve to this JSON path (multi-log mode only).")
    ap.add_argument("--metric", choices=["p95", "max", "median", "mean"], default="p95",
                    help="Which statistic to record as the canonical v_ms.")
    args = ap.parse_args()

    curve = {}
    for entry in args.log:
        if ":" in entry:
            path, rpm_str = entry.rsplit(":", 1)
            rpm = int(rpm_str)
        else:
            path = entry
            rpm = args.rpm
        s = speeds_from_log(path)
        summ = summarize(s)
        label = f"RPM={rpm}" if rpm is not None else path
        if summ is None:
            print(f"[{label}] no valid consecutive detections")
            continue
        print(f"[{label}] n={summ['n_pairs']} mean={summ['mean_mps']:.2f} "
              f"median={summ['median_mps']:.2f} p95={summ['p95_mps']:.2f} "
              f"max={summ['max_mps']:.2f} m/s")
        if rpm is not None:
            curve[str(rpm)] = summ[f"{args.metric}_mps"]

    if args.write and curve:
        sorted_rpms = sorted(int(k) for k in curve)
        payload = {
            "metric": args.metric,
            "points": [{"rpm": r, "v_ms": curve[str(r)]} for r in sorted_rpms],
        }
        Path(args.write).parent.mkdir(parents=True, exist_ok=True)
        with open(args.write, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"[WROTE] {args.write}")


if __name__ == "__main__":
    main()
