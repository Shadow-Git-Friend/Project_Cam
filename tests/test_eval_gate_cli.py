"""CLI contract for the hardware-free evaluation gate."""

from __future__ import annotations

import subprocess
import sys


def test_eval_gate_cli_runs_without_runtime_warning():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "project_cam.evaluation.gate",
            "--pairs",
            "tests/fixtures/eval_pairs_ball_static.json",
            "--suite",
            "ball_static",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "RuntimeWarning" not in result.stderr
    assert "[eval-gate] suite=ball_static -> PASS" in result.stdout
