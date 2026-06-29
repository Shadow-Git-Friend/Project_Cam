"""Single-model inference benchmark (YOLO ball / YOLO-Pose, .pt / ONNX / TRT).

Dry-run mode emits a planned-config CSV row without a GPU, model, or cameras --
this is what CI exercises. A real run (no --dry-run) attempts to load the model
and time inference; it errors clearly if ultralytics/torch or the weights are
missing rather than reporting a fabricated number.

Example:
  python benchmarks/benchmark_inference.py \
    --model models/ball/yolo26m-672.engine --backend tensorrt \
    --input data/benchmark/ball_frames --batch-size 6 \
    --output benchmarks/results/ball_trt_usb6.csv
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _bench_common import new_row, write_rows  # noqa: E402


def _backend_precision(backend: str) -> str:
    return {"tensorrt": "fp16", "onnxruntime": "fp32", "pytorch": "fp32"}.get(backend, "")


def build_dry_run_rows(args) -> list:
    return [new_row(
        camera_profile=args.camera_profile,
        camera_count=args.camera_count,
        resolution=args.resolution,
        model_name=os.path.basename(args.model),
        runtime_backend=args.backend,
        precision=_backend_precision(args.backend),
        warmup_frames=args.warmup,
        measured_frames=0,
        mode="dry_run",
        measured=False,
    )]


def run_real(args) -> list:  # pragma: no cover - needs GPU + weights
    import time

    try:
        from ultralytics import YOLO
    except Exception as exc:
        raise SystemExit(f"ultralytics not available for a real run: {exc}")
    if not os.path.exists(args.model):
        raise SystemExit(f"model not found: {args.model}")

    model = YOLO(args.model)
    import numpy as np

    h, w = (int(x) for x in args.resolution.split("x"))
    batch = [np.zeros((h, w, 3), dtype="uint8") for _ in range(args.batch_size)]
    for _ in range(args.warmup):
        model.predict(batch, verbose=False, imgsz=max(h, w))
    lat = []
    for _ in range(args.frames):
        t0 = time.perf_counter()
        model.predict(batch, verbose=False, imgsz=max(h, w))
        lat.append((time.perf_counter() - t0) * 1000.0)
    lat.sort()
    n = len(lat)
    fps = (args.batch_size * n) / (sum(lat) / 1000.0) if lat else 0.0
    return [new_row(
        camera_profile=args.camera_profile, camera_count=args.camera_count,
        resolution=args.resolution, model_name=os.path.basename(args.model),
        runtime_backend=args.backend, precision=_backend_precision(args.backend),
        warmup_frames=args.warmup, measured_frames=n, fps=round(fps, 2),
        latency_p50_ms=round(lat[n // 2], 3),
        latency_p95_ms=round(lat[min(n - 1, int(n * 0.95))], 3),
        latency_p99_ms=round(lat[min(n - 1, int(n * 0.99))], 3),
        inference_latency_ms=round(sum(lat) / n, 3),
        mode="measured", measured=True)]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="models/ball/yolo26m-672.engine")
    p.add_argument("--backend", default="tensorrt",
                   choices=["tensorrt", "onnxruntime", "pytorch"])
    p.add_argument("--input", default=None)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--frames", type=int, default=100)
    p.add_argument("--resolution", default="1280x720")
    p.add_argument("--camera-profile", default="usb6")
    p.add_argument("--camera-count", type=int, default=6)
    p.add_argument("--output", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    rows = build_dry_run_rows(args) if args.dry_run else run_real(args)
    path = write_rows(args.output, rows)
    print(f"[benchmark_inference] wrote {len(rows)} row(s) -> {path} "
          f"(mode={'dry_run' if args.dry_run else 'measured'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
