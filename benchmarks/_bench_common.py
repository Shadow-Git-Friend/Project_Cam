"""Shared schema + helpers for the reproducible benchmark suite.

Every benchmark writes the same wide CSV schema so 4-cam vs 6-cam, backend, and
resolution runs are directly comparable. The ``mode`` and ``measured`` columns
make it explicit which rows are real measurements vs planned/dry-run placeholders
-- the portfolio rule is: never present an unmeasured number as measured.
"""

from __future__ import annotations

import csv
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Dict, List

# Exact metric schema from PROJECT_IMPROVEMENT_PLAN, plus mode/measured markers.
COLUMNS: List[str] = [
    "run_id",
    "timestamp",
    "git_commit",
    "camera_profile",
    "camera_count",
    "resolution",
    "model_name",
    "runtime_backend",
    "precision",
    "warmup_frames",
    "measured_frames",
    "fps",
    "latency_p50_ms",
    "latency_p95_ms",
    "latency_p99_ms",
    "capture_latency_ms",
    "inference_latency_ms",
    "triangulation_latency_ms",
    "kalman_latency_ms",
    "render_latency_ms",
    "gpu_memory_mb",
    "cpu_percent",
    "dropped_frames_total",
    "queue_depth_mean",
    "frame_age_ms_mean",
    "mean_reprojection_px",
    "p95_reprojection_px",
    "mean_3d_error_mm",
    "p95_3d_error_mm",
    "detection_rate",
    "false_positive_rate",
    # explicit provenance markers (superset of the required schema)
    "mode",
    "measured",
]


def git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except Exception:
        return "unknown"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_row(**overrides) -> Dict[str, object]:
    """A fully-populated row with empty defaults, then overrides applied."""
    row = {col: "" for col in COLUMNS}
    row["run_id"] = uuid.uuid4().hex[:12]
    row["timestamp"] = now_iso()
    row["git_commit"] = git_commit()
    row["mode"] = "dry_run"
    row["measured"] = False
    row.update(overrides)
    unknown = set(overrides) - set(COLUMNS)
    if unknown:
        raise KeyError(f"unknown benchmark columns: {sorted(unknown)}")
    return row


def write_rows(path: str, rows: List[Dict[str, object]]) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})
    return path
