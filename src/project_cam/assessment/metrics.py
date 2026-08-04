"""Summary metrics for athlete movement assessment reports."""

from __future__ import annotations

from statistics import mean
from typing import Any

from .joints import JOINT_NAMES


def summarize_session(frames: list[dict[str, Any]], frame_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "angles_deg": _summarize_nested(frame_metrics, "angles_deg"),
        "distances": _summarize_nested(frame_metrics, "distances"),
        "asymmetry_deg": _summarize_nested(frame_metrics, "asymmetry_deg"),
        "knee_line_deviation_ratio": _summarize_nested(frame_metrics, "knee_line_deviation_ratio"),
        "knee_valgus_signed_ratio": _summarize_nested(frame_metrics, "knee_valgus_signed_ratio"),
        "movement": {
            "smoothness": smoothness(frame_metrics),
            "fatigue_drift": fatigue_drift(frame_metrics),
        },
    }


def confidence_score(frames: list[dict[str, Any]], frame_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not frames:
        return {
            "confidence_score": 0.0,
            "valid_frame_ratio": 0.0,
            "valid_joint_ratio_mean": 0.0,
            "joint_conf_mean": 0.0,
            "camera_coverage_mean": 0.0,
        }

    valid_ratios = [m.get("quality", {}).get("valid_joint_ratio", 0.0) for m in frame_metrics]
    valid_frame_ratio = sum(1 for ratio in valid_ratios if ratio > 0.0) / len(frames)
    joint_conf_vals = []
    cam_vals = []
    any_camera_counts = False
    for frame in frames:
        for point, conf, cams in zip(frame.get("joints", []), frame.get("joint_conf", []), frame.get("joint_cams", [])):
            if point is None:
                continue
            joint_conf_vals.append(float(conf))
            cam_vals.append(min(float(cams) / 3.0, 1.0))
            if cams:
                any_camera_counts = True

    valid_joint_ratio_mean = mean(valid_ratios) if valid_ratios else 0.0
    joint_conf_mean = mean(joint_conf_vals) if joint_conf_vals else 0.0
    camera_coverage_mean = mean(cam_vals) if any_camera_counts and cam_vals else (0.75 if joint_conf_vals else 0.0)
    score = 100.0 * (
        0.55 * valid_joint_ratio_mean
        + 0.25 * joint_conf_mean
        + 0.10 * valid_frame_ratio
        + 0.10 * camera_coverage_mean
    )
    return {
        "confidence_score": round(max(0.0, min(score, 100.0)), 2),
        "valid_frame_ratio": round(valid_frame_ratio, 4),
        "valid_joint_ratio_mean": round(valid_joint_ratio_mean, 4),
        "joint_conf_mean": round(joint_conf_mean, 4),
        "camera_coverage_mean": round(camera_coverage_mean, 4),
        "expected_joint_count": len(JOINT_NAMES),
    }


def smoothness(frame_metrics: list[dict[str, Any]]) -> dict[str, float | None]:
    summaries = {}
    for angle_name in _all_metric_names(frame_metrics, "angles_deg"):
        values = _metric_series(frame_metrics, "angles_deg", angle_name)
        if len(values) < 3:
            summaries[angle_name] = None
            continue
        second_diff = [abs(values[i + 2] - 2 * values[i + 1] + values[i]) for i in range(len(values) - 2)]
        summaries[angle_name] = round(mean(second_diff), 4) if second_diff else None
    return summaries


def fatigue_drift(frame_metrics: list[dict[str, Any]]) -> dict[str, float | None]:
    drift = {}
    for angle_name in _all_metric_names(frame_metrics, "angles_deg"):
        values = _metric_series(frame_metrics, "angles_deg", angle_name)
        if len(values) < 4:
            drift[angle_name] = None
            continue
        mid = len(values) // 2
        drift[angle_name] = round(mean(values[mid:]) - mean(values[:mid]), 4)
    return drift


def _summarize_nested(frame_metrics: list[dict[str, Any]], group: str) -> dict[str, dict[str, float | int] | None]:
    out = {}
    for name in _all_metric_names(frame_metrics, group):
        values = _metric_series(frame_metrics, group, name)
        if not values:
            out[name] = None
            continue
        out[name] = {
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "mean": round(mean(values), 4),
            "rom": round(max(values) - min(values), 4),
            "valid_frames": len(values),
        }
    return out


def _all_metric_names(frame_metrics: list[dict[str, Any]], group: str) -> list[str]:
    names = set()
    for metrics in frame_metrics:
        names.update((metrics.get(group) or {}).keys())
    return sorted(names)


def _metric_series(frame_metrics: list[dict[str, Any]], group: str, name: str) -> list[float]:
    values = []
    for metrics in frame_metrics:
        value = (metrics.get(group) or {}).get(name)
        if value is not None:
            values.append(float(value))
    return values

