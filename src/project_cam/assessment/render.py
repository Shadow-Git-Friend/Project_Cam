"""HTML rendering for athlete assessment reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def render_html_report(report: dict[str, Any], output_path: str | Path) -> None:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html")
    context = _template_context(report)
    out_path.write_text(template.render(**context), encoding="utf-8")


def _template_context(report: dict[str, Any]) -> dict[str, Any]:
    timeseries = report.get("timeseries", {})
    angle_series = timeseries.get("angles_deg", {})
    knee_series = {
        name: angle_series[name]
        for name in ("left_knee", "right_knee")
        if name in angle_series
    }
    if not knee_series:
        knee_series = dict(list(angle_series.items())[:2])

    asymmetry = report.get("metrics", {}).get("asymmetry_deg", {})
    symmetry_labels = []
    symmetry_values = []
    for name, summary in asymmetry.items():
        if isinstance(summary, dict) and summary.get("mean") is not None:
            symmetry_labels.append(name)
            symmetry_values.append(summary["mean"])

    raw_time = timeseries.get("time_s", [])
    raw_frames = timeseries.get("frames", [])
    series_len = len(next(iter(knee_series.values()), []))
    if raw_time and any(v is not None for v in raw_time):
        labels = [round(float(v), 1) if v is not None else None for v in raw_time]
        x_axis_label = "Time (s)"
    elif raw_frames and any(v is not None for v in raw_frames):
        labels = list(raw_frames)
        x_axis_label = "Frame index"
    else:
        labels = list(range(series_len))
        x_axis_label = "Frame index"

    rep_markers = _rep_marker_positions(report.get("reps", []), labels, raw_frames)

    score = float(report.get("quality", {}).get("confidence_score", 0.0))
    return {
        "report": report,
        "data_quality_score": score,
        "data_quality_color": _score_color(score),
        "data_quality_label": report.get("data_quality", {}).get("label", _data_quality_label(score)),
        "movement_quality": report.get("movement_quality") or {},
        "movement_quality_color": _movement_color((report.get("movement_quality") or {}).get("status")),
        "frames_json": json.dumps(labels),
        "x_axis_label": x_axis_label,
        "angle_series_json": json.dumps(knee_series),
        "rep_markers_json": json.dumps(rep_markers),
        "rep_rows": _rep_rows(report),
        "metric_confidence_rows": _metric_confidence_rows(report),
        "symmetry_labels_json": json.dumps(symmetry_labels),
        "symmetry_values_json": json.dumps(symmetry_values),
    }


def _rep_marker_positions(
    reps: list[dict[str, Any]],
    labels: list[Any],
    raw_frames: list[Any],
) -> list[dict[str, Any]]:
    """For each rep, return {bottom_x, start_x, end_x} mapped to chart x-axis values."""
    out = []
    frame_to_label = {}
    if raw_frames:
        for idx, frame_idx in enumerate(raw_frames):
            if frame_idx is not None and idx < len(labels):
                frame_to_label[int(frame_idx)] = labels[idx]
    for rep in reps:
        marker = {
            "index": rep.get("index"),
            "start_x": frame_to_label.get(rep.get("start_frame")),
            "bottom_x": frame_to_label.get(rep.get("bottom_frame")),
            "end_x": frame_to_label.get(rep.get("end_frame")),
        }
        out.append(marker)
    return out


def _data_quality_label(score: float) -> str:
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def _movement_color(status: str | None) -> str:
    if status == "good":
        return "#2e7d32"
    if status == "needs_review":
        return "#f9a825"
    if status == "blocked":
        return "#c62828"
    return "#52606d"


def _score_color(score: float) -> str:
    if score >= 75:
        return "#2e7d32"
    if score >= 50:
        return "#f9a825"
    return "#c62828"


def _rep_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    qualities = {
        item.get("rep_index"): item
        for item in report.get("rep_quality", [])
        if isinstance(item, dict)
    }
    rows = []
    for rep in report.get("reps", []):
        quality = qualities.get(rep.get("index"), {})
        reason_codes = quality.get("reason_codes") or []
        per_rep = rep.get("per_rep_metrics") or {}
        depth = _min_or_none(per_rep.get("left_knee_min_deg"), per_rep.get("right_knee_min_deg"))
        valgus = _max_or_none(per_rep.get("left_knee_valgus_max_signed"), per_rep.get("right_knee_valgus_max_signed"))
        drift = _max_or_none(per_rep.get("left_knee_drift_max"), per_rep.get("right_knee_drift_max"))
        rows.append(
            {
                "index": rep.get("index"),
                "frames": f"{rep.get('start_frame')} - {rep.get('end_frame')}",
                "pelvis_travel_mm": _fmt(rep.get("pelvis_travel_mm"), 1),
                "depth_deg": _fmt(depth, 1),
                "knee_asymmetry_deg": _fmt(per_rep.get("knee_asymmetry_mean_deg"), 1),
                "knee_drift_ratio": _fmt(drift, 3),
                "knee_valgus_signed": _fmt(valgus, 3),
                "confidence": quality.get("confidence_status") or quality.get("status") or "unknown",
                "status": quality.get("status", "unknown"),
                "reason_codes": ", ".join(reason_codes) if reason_codes else "ok",
            }
        )
    return rows


def _min_or_none(*vals: Any) -> float | None:
    cleaned = [float(v) for v in vals if v is not None]
    return min(cleaned) if cleaned else None


def _max_or_none(*vals: Any) -> float | None:
    cleaned = [float(v) for v in vals if v is not None]
    return max(cleaned) if cleaned else None


def _metric_confidence_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for group_name, metrics in (report.get("metric_confidence") or {}).items():
        if not isinstance(metrics, dict):
            continue
        for metric_name, confidence in metrics.items():
            if not isinstance(confidence, dict):
                continue
            if metric_name not in {"left_knee", "right_knee", "left_hip", "right_hip"}:
                continue
            rows.append(
                {
                    "metric": f"{group_name}.{metric_name}",
                    "status": confidence.get("status"),
                    "source": confidence.get("source"),
                    "score": _fmt(confidence.get("score"), 2),
                    "valid_frame_ratio": _fmt(confidence.get("valid_frame_ratio"), 2),
                }
            )
    return rows


def _fmt(value: Any, places: int) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return str(value)
