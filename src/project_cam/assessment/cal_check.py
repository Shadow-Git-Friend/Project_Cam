"""Known-geometry calibration checks for assessment sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from .io import load_motion, write_json
from .kinematics import distance_mm
from .joints import JOINT_NAME_TO_INDEX


def run_calibration_check(
    input_path: str | Path,
    output_path: str | Path,
    fps: float = 15.0,
    max_distance_std_mm: float = 15.0,
    max_missing_frame_ratio: float = 0.30,
) -> dict[str, Any]:
    frames = load_motion(input_path, default_fps=fps)
    report = build_calibration_report(
        frames=frames,
        max_distance_std_mm=max_distance_std_mm,
        max_missing_frame_ratio=max_missing_frame_ratio,
    )
    write_json(output_path, report)
    return report


def build_calibration_report(
    frames: list[dict[str, Any]],
    max_distance_std_mm: float = 15.0,
    max_missing_frame_ratio: float = 0.30,
) -> dict[str, Any]:
    measurements = {
        "shoulder_width_mm": _distance_series(frames, "left_shoulder", "right_shoulder"),
        "left_shoulder_to_wrist_mm": _distance_series(frames, "left_shoulder", "left_wrist"),
        "right_shoulder_to_wrist_mm": _distance_series(frames, "right_shoulder", "right_wrist"),
    }
    summarized = {name: _summarize_series(values, len(frames)) for name, values in measurements.items()}

    warnings = []
    for name, summary in summarized.items():
        if summary["valid_frames"] == 0:
            warnings.append(f"{name} could not be measured in any frame.")
            continue
        if summary["std"] > max_distance_std_mm:
            warnings.append(f"{name} jitter {summary['std']:.1f}mm exceeds {max_distance_std_mm:.1f}mm.")
        if summary["missing_frame_ratio"] > max_missing_frame_ratio:
            warnings.append(f"{name} missing-frame ratio {summary['missing_frame_ratio']:.0%} exceeds {max_missing_frame_ratio:.0%}.")

    return {
        "schema_version": "project_cam.assessment.calibration_check.v1",
        "status": "warning" if warnings else "ok",
        "frame_count": len(frames),
        "thresholds": {
            "max_distance_std_mm": max_distance_std_mm,
            "max_missing_frame_ratio": max_missing_frame_ratio,
        },
        "measurements": summarized,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a simple T-pose/known-geometry calibration stability check.")
    ap.add_argument("--input", required=True, help="Input Project_Cam JSON or UDP JSONL joint file")
    ap.add_argument("--output", required=True, help="Output calibration-check JSON path")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--max-distance-std-mm", type=float, default=15.0)
    ap.add_argument("--max-missing-frame-ratio", type=float, default=0.30)
    args = ap.parse_args(argv)

    report = run_calibration_check(
        input_path=args.input,
        output_path=args.output,
        fps=args.fps,
        max_distance_std_mm=args.max_distance_std_mm,
        max_missing_frame_ratio=args.max_missing_frame_ratio,
    )
    print(f"[OK] Calibration check {report['status']} -> {args.output}")
    return 0


def _distance_series(frames: list[dict[str, Any]], joint_a: str, joint_b: str) -> list[float]:
    idx_a = JOINT_NAME_TO_INDEX[joint_a]
    idx_b = JOINT_NAME_TO_INDEX[joint_b]
    values = []
    for frame in frames:
        joints = frame.get("joints", [])
        if idx_a >= len(joints) or idx_b >= len(joints):
            continue
        dist = distance_mm(joints[idx_a], joints[idx_b])
        if dist is not None:
            values.append(dist)
    return values


def _summarize_series(values: list[float], frame_count: int) -> dict[str, Any]:
    if not values:
        return {
            "mean": None,
            "std": 0.0,
            "min": None,
            "max": None,
            "valid_frames": 0,
            "missing_frame_ratio": 1.0 if frame_count else 0.0,
        }
    return {
        "mean": round(mean(values), 4),
        "std": round(pstdev(values), 4) if len(values) > 1 else 0.0,
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "valid_frames": len(values),
        "missing_frame_ratio": round(1.0 - (len(values) / frame_count), 4) if frame_count else 0.0,
    }


if __name__ == "__main__":
    raise SystemExit(main())

