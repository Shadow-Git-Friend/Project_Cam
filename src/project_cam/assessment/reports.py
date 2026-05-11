"""Report assembly for Project_Cam athlete movement assessment."""

from __future__ import annotations

from typing import Any

from . import SCHEMA_VERSION
from .compliance import assess_compliance
from .joints import JOINT_NAME_TO_INDEX
from .kinematics import ANGLE_TRIPLETS, frame_kinematics
from .metrics import confidence_score, summarize_session
from .rules import exercise_rules
from .segmentation import detect_reps_with_rejections

DISCLAIMER = "Coaching screen only; not diagnosis, medical advice, or talent ranking."


def build_report(
    frames: list[dict[str, Any]],
    exercise: str,
    config: dict[str, Any],
    athlete_id: str,
    age: int | None,
    sex: str | None,
    fps: float,
    session_id: str | None = None,
    maturity: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rules = exercise_rules(config, exercise)
    frame_metrics = [frame_kinematics(frame) for frame in frames]
    quality = confidence_score(frames, frame_metrics)
    metrics = summarize_session(frames, frame_metrics)
    segmentation = detect_reps_with_rejections(frame_metrics, exercise=exercise, rules=rules, fps=fps)
    reps = segmentation["reps"]
    rejected_reps = segmentation["rejected_reps"]
    annotate_reps_with_per_rep_metrics(reps, frame_metrics)
    compliance = assess_compliance(exercise, frames, frame_metrics, reps, rules, fps)
    metric_confidence = build_metric_confidence(frames)
    rep_quality = build_rep_quality(reps, frames, metric_confidence)
    calibration_gate = build_calibration_gate(calibration)
    demo_verdict = build_demo_verdict(compliance, calibration_gate, rep_quality)
    flags = evaluate_flags(exercise, rules, quality, metrics, compliance, calibration, metric_confidence, demo_verdict)
    movement_quality = build_movement_quality(flags, rep_quality, compliance, demo_verdict)

    return {
        "schema_version": SCHEMA_VERSION,
        "session": {
            "session_id": session_id,
            "athlete_id": athlete_id,
            "age": age,
            "sex": sex,
            "fps": fps,
            "frame_count": len(frames),
        },
        "exercise": exercise,
        "quality": quality,
        "metrics": metrics,
        "timeseries": build_timeseries(frame_metrics),
        "reps": reps,
        "rejected_reps": rejected_reps,
        "rep_quality": rep_quality,
        "metric_confidence": metric_confidence,
        "compliance": compliance,
        "maturity": maturity,
        "calibration": calibration,
        "calibration_gate": calibration_gate,
        "demo_verdict": demo_verdict,
        "movement_quality": movement_quality,
        "data_quality": {
            "score": quality.get("confidence_score", 0.0),
            "label": _data_quality_label(float(quality.get("confidence_score", 0.0))),
        },
        "passport_summary": build_passport_summary(exercise, metrics, reps, rep_quality, demo_verdict),
        "flags": flags,
        "reference_context": config.get("reference_context", []),
        "disclaimer": DISCLAIMER,
    }


def annotate_reps_with_per_rep_metrics(reps: list[dict[str, Any]], frame_metrics: list[dict[str, Any]]) -> None:
    """Compute per-rep depth, asymmetry, drift, and signed valgus over each rep window."""
    if not reps or not frame_metrics:
        return
    by_frame_index = {m.get("frame_index"): m for m in frame_metrics if m.get("frame_index") is not None}
    for rep in reps:
        start = rep.get("start_frame")
        end = rep.get("end_frame")
        if start is None or end is None:
            continue
        window = [by_frame_index[i] for i in range(start, end + 1) if i in by_frame_index]
        if not window:
            continue
        rep["per_rep_metrics"] = {
            "left_knee_min_deg": _window_min(window, "angles_deg", "left_knee"),
            "right_knee_min_deg": _window_min(window, "angles_deg", "right_knee"),
            "knee_asymmetry_max_deg": _window_max(window, "asymmetry_deg", "knee"),
            "knee_asymmetry_mean_deg": _window_mean(window, "asymmetry_deg", "knee"),
            "left_knee_drift_max": _window_max(window, "knee_line_deviation_ratio", "left"),
            "right_knee_drift_max": _window_max(window, "knee_line_deviation_ratio", "right"),
            "left_knee_valgus_max_signed": _window_max(window, "knee_valgus_signed_ratio", "left"),
            "right_knee_valgus_max_signed": _window_max(window, "knee_valgus_signed_ratio", "right"),
        }


def _window_min(window: list[dict[str, Any]], group: str, name: str) -> float | None:
    vals = [(m.get(group) or {}).get(name) for m in window]
    vals = [float(v) for v in vals if v is not None]
    return round(min(vals), 4) if vals else None


def _window_max(window: list[dict[str, Any]], group: str, name: str) -> float | None:
    vals = [(m.get(group) or {}).get(name) for m in window]
    vals = [float(v) for v in vals if v is not None]
    return round(max(vals), 4) if vals else None


def _window_mean(window: list[dict[str, Any]], group: str, name: str) -> float | None:
    vals = [(m.get(group) or {}).get(name) for m in window]
    vals = [float(v) for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def build_movement_quality(
    flags: list[dict[str, Any]],
    rep_quality: list[dict[str, Any]],
    compliance: dict[str, Any],
    demo_verdict: dict[str, Any],
) -> dict[str, Any]:
    """Movement-quality verdict derived from coaching flags and rep scoring.

    Distinct from data_quality (which measures tracking confidence). A session
    can score 99 on data quality and still need review here.
    """
    coaching_flags = [f for f in flags if f.get("severity") == "coaching"]
    has_unscored = any(rep.get("status") == "unscored" for rep in rep_quality)
    if demo_verdict.get("status") == "calibration_failed":
        label, status = "Cannot score", "blocked"
    elif compliance.get("status") != "ok" or has_unscored:
        label, status = "Needs review", "needs_review"
    elif coaching_flags:
        label, status = "Needs review", "needs_review"
    else:
        label, status = "Looks good", "good"
    return {
        "status": status,
        "label": label,
        "coaching_flag_count": len(coaching_flags),
        "coaching_flag_codes": [f.get("code") for f in coaching_flags],
        "unscored_rep_count": sum(1 for rep in rep_quality if rep.get("status") == "unscored"),
    }


def _data_quality_label(score: float) -> str:
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def build_metric_confidence(frames: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "angles_deg": {
            name: _angle_metric_confidence(frames, name, joints)
            for name, joints in ANGLE_TRIPLETS.items()
        }
    }


def build_rep_quality(
    reps: list[dict[str, Any]],
    frames: list[dict[str, Any]],
    metric_confidence: dict[str, Any],
) -> list[dict[str, Any]]:
    knee_statuses = [
        metric_confidence.get("angles_deg", {}).get("left_knee", {}).get("status"),
        metric_confidence.get("angles_deg", {}).get("right_knee", {}).get("status"),
    ]
    out = []
    for rep in reps:
        status = "scored" if all(status in {"trusted", "limited"} for status in knee_statuses) else "unscored"
        reasons = []
        if status == "unscored":
            reasons.append("knee_metric_low_confidence")
        out.append(
            {
                "rep_index": rep.get("index"),
                "status": status,
                "reason_codes": reasons,
                "depth_signal_deg": rep.get("min_signal"),
                "pelvis_travel_mm": rep.get("pelvis_travel_mm"),
                "duration_s": rep.get("duration_s"),
                "confidence_status": "limited" if "limited" in knee_statuses else status,
            }
        )
    return out


def build_calibration_gate(calibration: dict[str, Any] | None) -> dict[str, Any]:
    if calibration is None:
        return {
            "status": "not_run",
            "message": "No pre-session calibration report was provided.",
        }
    if calibration.get("status") == "ok":
        return {
            "status": "passed",
            "message": "Pre-session calibration check passed.",
        }
    return {
        "status": "failed",
        "message": "Pre-session calibration check failed; recalibrate or re-record before using assessment scores.",
        "warnings": calibration.get("warnings", []),
    }


def build_demo_verdict(
    compliance: dict[str, Any],
    calibration_gate: dict[str, Any],
    rep_quality: list[dict[str, Any]],
) -> dict[str, Any]:
    if calibration_gate.get("status") == "failed":
        return {
            "status": "calibration_failed",
            "label": "Calibration failed",
            "message": calibration_gate.get("message"),
        }
    if compliance.get("status") != "ok":
        return {
            "status": "re_record",
            "label": "Re-record",
            "message": compliance.get("reason"),
        }
    if any(rep.get("status") == "unscored" for rep in rep_quality):
        return {
            "status": "re_record",
            "label": "Re-record",
            "message": "One or more reps had low-confidence knee or hip metrics.",
        }
    return {
        "status": "usable",
        "label": "Usable",
        "message": "Session is usable for the focused squat-screening report.",
    }


def build_passport_summary(
    exercise: str,
    metrics: dict[str, Any],
    reps: list[dict[str, Any]],
    rep_quality: list[dict[str, Any]],
    demo_verdict: dict[str, Any],
) -> dict[str, Any]:
    knee_depth = _mean_side_summary(metrics, "angles_deg", "knee", "min")
    knee_asym = _summary_value(metrics, "asymmetry_deg", "knee", "mean")
    knee_drift = max(
        [
            v for v in (
                _summary_value(metrics, "knee_line_deviation_ratio", "left", "max"),
                _summary_value(metrics, "knee_line_deviation_ratio", "right", "max"),
            )
            if v is not None
        ],
        default=None,
    )
    knee_valgus = max(
        [
            v for v in (
                _summary_value(metrics, "knee_valgus_signed_ratio", "left", "max"),
                _summary_value(metrics, "knee_valgus_signed_ratio", "right", "max"),
            )
            if v is not None
        ],
        default=None,
    )
    return {
        "exercise": exercise,
        "usable": demo_verdict.get("status") == "usable",
        "scored_reps": sum(1 for rep in rep_quality if rep.get("status") == "scored"),
        "detected_reps": len(reps),
        "knee_depth_min_deg": knee_depth,
        "knee_asymmetry_mean_deg": knee_asym,
        "knee_drift_max_ratio": knee_drift,
        "knee_valgus_max_signed_ratio": knee_valgus,
    }


def _angle_metric_confidence(frames: list[dict[str, Any]], angle_name: str, joint_names: tuple[str, str, str]) -> dict[str, Any]:
    indices = [JOINT_NAME_TO_INDEX[name] for name in joint_names]
    valid_frames = 0
    has_camera_counts = False
    frame_scores = []
    min_cams_seen = []
    for frame in frames:
        joints = frame.get("joints", [])
        if any(idx >= len(joints) or joints[idx] is None for idx in indices):
            continue
        valid_frames += 1
        cams = frame.get("joint_cams", [])
        conf = frame.get("joint_conf", [])
        cams_vals = [int(cams[idx]) if idx < len(cams) else 0 for idx in indices]
        conf_vals = [float(conf[idx]) if idx < len(conf) else 1.0 for idx in indices]
        if any(val > 0 for val in cams_vals):
            has_camera_counts = True
            min_cams_seen.append(min(cams_vals))
            frame_scores.append(min(min(cams_vals) / 3.0, min(conf_vals)))
        else:
            frame_scores.append(min(conf_vals) * 0.65)

    frames_at_3plus_cams = sum(1 for v in min_cams_seen if v >= 3)
    frames_at_2plus_cams = sum(1 for v in min_cams_seen if v >= 2)
    cams3_ratio = frames_at_3plus_cams / valid_frames if valid_frames else 0.0
    cams2_ratio = frames_at_2plus_cams / valid_frames if valid_frames else 0.0

    if valid_frames == 0:
        status = "blocked"
        source = "missing"
        score = 0.0
    elif not has_camera_counts:
        status = "limited"
        source = "legacy_estimated"
        score = sum(frame_scores) / len(frame_scores)
    else:
        score = sum(frame_scores) / len(frame_scores) if frame_scores else 0.0
        source = "camera_counts"
        if cams3_ratio >= 0.90 and score >= 0.75:
            status = "trusted"
        elif cams3_ratio >= 0.50 and score >= 0.55:
            status = "limited"
        else:
            status = "blocked"

    return {
        "status": status,
        "source": source,
        "score": round(score, 4),
        "valid_frames": valid_frames,
        "frame_count": len(frames),
        "valid_frame_ratio": round(valid_frames / len(frames), 4) if frames else 0.0,
        "frames_at_3plus_cams_ratio": round(cams3_ratio, 4),
        "frames_at_2plus_cams_ratio": round(cams2_ratio, 4),
        "required_joints": list(joint_names),
        "minimum_required_cameras": 3,
    }


def build_timeseries(frame_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    angle_names = sorted({name for metrics in frame_metrics for name in (metrics.get("angles_deg") or {})})
    return {
        "frames": [metrics.get("frame_index") for metrics in frame_metrics],
        "time_s": [metrics.get("time_s") for metrics in frame_metrics],
        "angles_deg": {
            name: [(metrics.get("angles_deg") or {}).get(name) for metrics in frame_metrics]
            for name in angle_names
        },
    }


def evaluate_flags(
    exercise: str,
    rules: dict[str, Any],
    quality: dict[str, Any],
    metrics: dict[str, Any],
    compliance: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
    metric_confidence: dict[str, Any] | None = None,
    demo_verdict: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    flags = []
    thresholds = rules.get("thresholds", {})

    min_conf = float(thresholds.get("min_confidence_score", 45.0))
    if quality.get("confidence_score", 0.0) < min_conf:
        flags.append(_flag("low_confidence", "warning", "Many joints were missing or low confidence; interpret this report cautiously.", quality.get("confidence_score"), min_conf))

    max_asym = float(thresholds.get("max_left_right_angle_asymmetry_deg", 25.0))
    knee_asym = _summary_value(metrics, "asymmetry_deg", "knee", "mean")
    if knee_asym is not None and knee_asym > max_asym:
        flags.append(_flag("knee_asymmetry", "coaching", "Mean left/right knee angle asymmetry exceeded the coaching threshold.", knee_asym, max_asym))

    # Coaching signal: signed valgus only. The undirected magnitude metric is
    # depth-confounded (its denominator is the hip-ankle distance, which shrinks
    # at deep squats, inflating the ratio) and conflates anterior knee translation
    # with medial drift. Validated 2026-05-06 on clean vs intentional valgus
    # recordings: clean drift=1.21, valgus drift=0.72 — direction inverted from
    # what coaching would expect. Reported as observation only, never escalates
    # Movement Quality.
    max_knee_line = float(thresholds.get("max_knee_line_deviation_ratio", 0.20))
    max_valgus = float(thresholds.get("max_knee_valgus_signed_ratio", 0.12))
    for side in ("left", "right"):
        magnitude = _summary_value(metrics, "knee_line_deviation_ratio", side, "max")
        valgus = _summary_value(metrics, "knee_valgus_signed_ratio", side, "max")
        if valgus is not None and valgus > max_valgus:
            flags.append(_flag(
                f"{side}_knee_valgus",
                "coaching",
                f"{side.title()} knee drifts inward (valgus) during the squat pattern.",
                valgus,
                max_valgus,
            ))
        elif magnitude is not None and magnitude > max_knee_line:
            flags.append(_flag(
                f"{side}_knee_line_deviation",
                "info",
                f"{side.title()} knee was off the hip-ankle line (observation only; depth-confounded, not a coaching signal).",
                magnitude,
                max_knee_line,
            ))

    if exercise in {"squat", "single_leg_squat"}:
        depth_limit = float(thresholds.get("bottom_knee_angle_max_deg", 115.0))
        knee_min = _mean_side_summary(metrics, "angles_deg", "knee", "min")
        if knee_min is not None and knee_min > depth_limit:
            flags.append(_flag("shallow_depth", "coaching", "Knee flexion suggests the lowest position was shallow for this drill.", knee_min, depth_limit))

    if exercise == "push_up":
        elbow_limit = float(thresholds.get("bottom_elbow_angle_max_deg", 115.0))
        elbow_min = _mean_side_summary(metrics, "angles_deg", "elbow", "min")
        if elbow_min is not None and elbow_min > elbow_limit:
            flags.append(_flag("shallow_push_up", "coaching", "Elbow flexion suggests the bottom position was shallow.", elbow_min, elbow_limit))

    if exercise in {"push_up", "plank"}:
        trunk_limit = float(thresholds.get("max_trunk_alignment_error_deg", 25.0))
        trunk = _mean_side_summary(metrics, "angles_deg", "trunk_to_leg", "mean")
        if trunk is not None:
            err = abs(180.0 - trunk)
            if err > trunk_limit:
                flags.append(_flag("trunk_alignment", "coaching", "Shoulder-hip-ankle alignment drifted beyond the coaching threshold.", err, trunk_limit))

    if compliance and compliance.get("status") != "ok":
        flags.append(
            {
                "code": "protocol_compliance",
                "severity": "warning",
                "message": compliance.get("reason", "The recorded movement did not satisfy the configured exercise protocol."),
            }
        )

    if calibration and calibration.get("status") != "ok":
        flags.append(
            {
                "code": "calibration_warning",
                "severity": "warning",
                "message": "Calibration stability warning: " + " ".join(calibration.get("warnings", [])),
            }
        )

    if metric_confidence:
        for name in ("left_knee", "right_knee"):
            conf = metric_confidence.get("angles_deg", {}).get(name, {})
            if conf.get("status") == "blocked":
                flags.append(
                    {
                        "code": f"{name}_low_confidence",
                        "severity": "warning",
                        "message": f"{name.replace('_', ' ').title()} was not scored because too few cameras saw the required joints.",
                    }
                )

    if demo_verdict and demo_verdict.get("status") == "re_record":
        flags.append(
            {
                "code": "demo_re_record",
                "severity": "warning",
                "message": demo_verdict.get("message", "Re-record this session before demo use."),
            }
        )

    if not flags:
        flags.append(
            {
                "code": "no_major_flags",
                "severity": "info",
                "message": "No major coaching flags were triggered by the configured thresholds.",
            }
        )
    return flags


def _flag(code: str, severity: str, message: str, value: float | None, threshold: float) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "value": round(value, 4) if value is not None else None,
        "threshold": threshold,
    }


def _summary_value(metrics: dict[str, Any], group: str, name: str, field: str) -> float | None:
    summary = (metrics.get(group) or {}).get(name)
    if not isinstance(summary, dict):
        return None
    value = summary.get(field)
    return float(value) if value is not None else None


def _mean_side_summary(metrics: dict[str, Any], group: str, base_name: str, field: str) -> float | None:
    vals = []
    for side in ("left", "right"):
        value = _summary_value(metrics, group, f"{side}_{base_name}", field)
        if value is not None:
            vals.append(value)
    return sum(vals) / len(vals) if vals else None
