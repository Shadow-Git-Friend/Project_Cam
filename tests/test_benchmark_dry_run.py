"""Benchmark dry-runs write a valid CSV without GPU/cameras."""

import csv
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "benchmarks"

REQUIRED_COLUMNS = {
    "run_id", "timestamp", "git_commit", "camera_profile", "camera_count",
    "resolution", "fps", "latency_p95_ms", "mean_3d_error_mm", "mode", "measured",
}


def _run(script, *args):
    env = {"PYTHONPATH": str(REPO / "src")}
    import os

    full_env = {**os.environ, **env}
    proc = subprocess.run(
        [sys.executable, str(BENCH / script), *args],
        cwd=str(REPO), env=full_env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc


def _read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_camera_count_dry_run_writes_csv(tmp_path):
    out = tmp_path / "camera_count.csv"
    _run("benchmark_camera_count.py", "--dry-run", "--output", str(out))
    assert out.exists()
    rows = _read(out)
    assert len(rows) == 2
    counts = sorted(int(r["camera_count"]) for r in rows)
    assert counts == [4, 6]
    assert all(r["measured"] == "False" for r in rows)
    assert REQUIRED_COLUMNS <= set(rows[0].keys())


def test_inference_dry_run_writes_csv(tmp_path):
    out = tmp_path / "inf.csv"
    _run("benchmark_inference.py", "--dry-run", "--backend", "tensorrt",
         "--batch-size", "6", "--output", str(out))
    rows = _read(out)
    assert len(rows) == 1
    assert rows[0]["runtime_backend"] == "tensorrt"
    assert rows[0]["precision"] == "fp16"
    assert rows[0]["measured"] == "False"


def test_pipeline_dry_run_writes_stage_rows(tmp_path):
    out = tmp_path / "pipe.csv"
    _run("benchmark_pipeline.py", "--dry-run", "--output", str(out))
    rows = _read(out)
    scopes = {r["model_name"] for r in rows}
    assert {"capture_only", "inference_only", "full"} <= scopes


def test_real_pipeline_requires_live_rig(tmp_path):
    # Without --dry-run the pipeline benchmark must refuse rather than fake numbers.
    import os

    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    proc = subprocess.run(
        [sys.executable, str(BENCH / "benchmark_pipeline.py"),
         "--output", str(tmp_path / "x.csv")],
        cwd=str(REPO), env=env, capture_output=True, text=True)
    assert proc.returncode != 0
