"""End-to-end pipeline benchmark (capture -> inference -> triangulation -> KF).

Dry-run emits one planned row per pipeline stage scope (capture_only,
inference_only, full) so the report can attribute latency by stage. A real run
would attach to the live viewer's perf JSONL; that path is intentionally left to
the live rig (see Parallel_working/ --perf-jsonl) and not faked here.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _bench_common import new_row, write_rows  # noqa: E402

SCOPES = ["capture_only", "inference_only", "full"]


def build_dry_run_rows(args) -> list:
    rows = []
    for scope in args.scopes:
        rows.append(new_row(
            camera_profile=args.camera_profile,
            camera_count=args.camera_count,
            resolution=args.resolution,
            model_name=scope,                 # scope recorded in model_name slot
            runtime_backend=args.backend,
            warmup_frames=args.warmup,
            measured_frames=0,
            mode="dry_run",
            measured=False,
        ))
    return rows


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--camera-profile", default="usb6")
    p.add_argument("--camera-count", type=int, default=6)
    p.add_argument("--resolution", default="1280x720")
    p.add_argument("--backend", default="tensorrt")
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--frames", type=int, default=300)
    p.add_argument("--scopes", nargs="+", default=SCOPES, choices=SCOPES)
    p.add_argument("--output", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.dry_run:
        raise SystemExit(
            "real pipeline benchmarking runs on the live rig; use "
            "Parallel_working/ --perf-jsonl, or pass --dry-run here")
    rows = build_dry_run_rows(args)
    path = write_rows(args.output, rows)
    print(f"[benchmark_pipeline] wrote {len(rows)} row(s) -> {path} (dry_run)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
