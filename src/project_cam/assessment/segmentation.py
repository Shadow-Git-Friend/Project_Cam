"""Rep/event segmentation for offline movement reports."""

from __future__ import annotations

from typing import Any


SIGNAL_BY_EXERCISE = {
    "squat": ("angles_deg", "knee"),
    "single_leg_squat": ("angles_deg", "knee"),
    "push_up": ("angles_deg", "elbow"),
}


def detect_reps(frame_metrics: list[dict[str, Any]], exercise: str, rules: dict[str, Any], fps: float) -> list[dict[str, Any]]:
    return detect_reps_with_rejections(frame_metrics, exercise, rules, fps)["reps"]


def detect_reps_with_rejections(
    frame_metrics: list[dict[str, Any]],
    exercise: str,
    rules: dict[str, Any],
    fps: float,
) -> dict[str, list[dict[str, Any]]]:
    if not frame_metrics:
        return {"reps": [], "rejected_reps": []}

    if exercise in {"squat", "single_leg_squat"}:
        return _detect_pelvis_z_reps(frame_metrics, exercise, rules, fps)

    return _detect_angle_reps(frame_metrics, exercise, rules, fps)


def _detect_angle_reps(frame_metrics: list[dict[str, Any]], exercise: str, rules: dict[str, Any], fps: float) -> dict[str, list[dict[str, Any]]]:
    signal = _exercise_signal(frame_metrics, exercise)
    if len(signal) < 3:
        return {"reps": _single_event(frame_metrics, fps), "rejected_reps": []}

    seg_rules = rules.get("segmentation", {})
    values = [v for _, v in signal]
    min_v = min(values)
    max_v = max(values)
    rom = max_v - min_v
    min_rom = float(seg_rules.get("min_rom_deg", 25.0))
    if rom < min_rom:
        return {"reps": [], "rejected_reps": [_rejected(frame_metrics, "low_rom", f"Angle ROM {rom:.1f} deg below {min_rom:.1f} deg")]}

    enter_threshold = float(seg_rules.get("enter_angle_deg", seg_rules.get("bottom_angle_max_deg", min_v + 0.35 * rom)))
    exit_threshold = float(seg_rules.get("exit_angle_deg", seg_rules.get("top_angle_min_deg", min_v + 0.75 * rom)))
    min_consecutive = max(1, int(seg_rules.get("min_consecutive_frames", 1)))
    min_duration_s = float(seg_rules.get("min_rep_duration_s", 0.3))
    max_duration_s = float(seg_rules.get("max_rep_duration_s", 8.0))
    max_missing_ratio = float(seg_rules.get("max_missing_frame_ratio", 0.30))
    ema_alpha = float(seg_rules.get("ema_alpha", 0.45))

    smoothed = _ema_signal(signal, ema_alpha)
    reps = []
    state = "up"
    below_count = 0
    above_count = 0
    last_up_pos = 0
    active = None
    pending = None

    for pos, (frame_idx, value) in enumerate(smoothed):
        if state == "up":
            if value >= exit_threshold:
                last_up_pos = pos
            if value <= enter_threshold:
                below_count += 1
            else:
                below_count = 0
            if below_count >= min_consecutive:
                if pending is not None:
                    _append_rep_if_valid(
                        reps, pending, pos - 1, signal, frame_metrics, fps,
                        min_rom, min_duration_s, max_duration_s, max_missing_ratio
                    )
                    pending = None
                active = {
                    "start_pos": last_up_pos,
                    "bottom_pos": pos,
                    "bottom_value": value,
                }
                state = "down"
                below_count = 0
                above_count = 0
        else:
            if active is not None and value < active["bottom_value"]:
                active["bottom_value"] = value
                active["bottom_pos"] = pos
            if value >= exit_threshold:
                above_count += 1
            else:
                above_count = 0
            if above_count >= min_consecutive:
                pending = {
                    "start_pos": active["start_pos"],
                    "bottom_pos": active["bottom_pos"],
                    "exit_pos": pos,
                }
                active = None
                state = "up"
                last_up_pos = pos
                above_count = 0

    if pending is not None:
        _append_rep_if_valid(
            reps, pending, len(signal) - 1, signal, frame_metrics, fps,
            min_rom, min_duration_s, max_duration_s, max_missing_ratio
        )
    return {"reps": reps, "rejected_reps": []}


def _detect_pelvis_z_reps(frame_metrics: list[dict[str, Any]], exercise: str, rules: dict[str, Any], fps: float) -> dict[str, list[dict[str, Any]]]:
    seg_rules = rules.get("segmentation", {})
    min_travel = float(seg_rules.get("min_pelvis_travel_mm", 150.0))
    enter_angle = float(seg_rules.get("enter_angle_deg", 90.0))
    exit_angle = float(seg_rules.get("exit_angle_deg", 120.0))
    min_duration_s = float(seg_rules.get("min_rep_duration_s", 0.3))
    max_duration_s = float(seg_rules.get("max_rep_duration_s", 8.0))
    max_missing_ratio = float(seg_rules.get("max_missing_frame_ratio", 0.30))
    pelvis_ema_alpha = float(seg_rules.get("pelvis_ema_alpha", seg_rules.get("ema_alpha", 1.0)))

    signal = _pelvis_signal(frame_metrics)
    if len(signal) < 3:
        return {"reps": [], "rejected_reps": [_rejected(frame_metrics, "missing_joints", "Not enough frames with both hip joints visible")]}

    signal = _smooth_pelvis_signal(signal, pelvis_ema_alpha)

    reps: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    state = "up"
    start_pos = 0
    start_z = signal[0]["pelvis_z"]
    bottom_pos = 0
    bottom_z = signal[0]["pelvis_z"]

    for pos, point in enumerate(signal):
        z = point["pelvis_z"]
        knee = point["knee_angle"]
        if state == "up":
            if z > start_z:
                start_z = z
                start_pos = pos
            if (start_z - z) >= (0.35 * min_travel) or (knee is not None and knee <= enter_angle):
                state = "down"
                bottom_pos = pos
                bottom_z = z
        else:
            if z < bottom_z:
                bottom_z = z
                bottom_pos = pos
            travel = start_z - bottom_z
            has_returned = (z - bottom_z) >= min_travel and (knee is None or knee >= exit_angle)
            if has_returned:
                _append_pelvis_rep_or_rejection(
                    reps=reps,
                    rejected=rejected,
                    signal=signal,
                    frame_metrics=frame_metrics,
                    start_pos=start_pos,
                    bottom_pos=bottom_pos,
                    end_pos=pos,
                    min_travel=min_travel,
                    min_duration_s=min_duration_s,
                    max_duration_s=max_duration_s,
                    max_missing_ratio=max_missing_ratio,
                    fps=fps,
                )
                state = "up"
                start_pos = pos
                start_z = z
                bottom_pos = pos
                bottom_z = z

    if state == "down":
        _append_pelvis_rep_or_rejection(
            reps=reps,
            rejected=rejected,
            signal=signal,
            frame_metrics=frame_metrics,
            start_pos=start_pos,
            bottom_pos=bottom_pos,
            end_pos=len(signal) - 1,
            min_travel=min_travel,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
            max_missing_ratio=max_missing_ratio,
            fps=fps,
        )

    if not reps and not rejected:
        max_travel = max(item["pelvis_z"] for item in signal) - min(item["pelvis_z"] for item in signal)
        rejected.append(_rejected(frame_metrics, "low_rom", f"Pelvis vertical travel {max_travel:.1f}mm below {min_travel:.1f}mm"))
    return {"reps": reps, "rejected_reps": rejected}


def _exercise_signal(frame_metrics: list[dict[str, Any]], exercise: str) -> list[tuple[int, float]]:
    kind, name = SIGNAL_BY_EXERCISE.get(exercise, ("angles_deg", "knee"))
    signal = []
    for idx, metrics in enumerate(frame_metrics):
        frame_idx = _frame_index(metrics, idx)
        value = None
        if kind == "angles_deg":
            left = metrics.get("angles_deg", {}).get(f"left_{name}")
            right = metrics.get("angles_deg", {}).get(f"right_{name}")
            vals = [v for v in (left, right) if v is not None]
            if vals:
                value = sum(vals) / len(vals)
        if value is not None:
            signal.append((frame_idx, float(value)))
    return signal


def _smooth_pelvis_signal(signal: list[dict[str, Any]], alpha: float) -> list[dict[str, Any]]:
    alpha = max(0.0, min(1.0, alpha))
    if not signal or alpha <= 0:
        return signal
    smoothed = []
    prev_z = signal[0]["pelvis_z"]
    prev_knee = signal[0]["knee_angle"]
    for point in signal:
        prev_z = alpha * point["pelvis_z"] + (1.0 - alpha) * prev_z
        if point["knee_angle"] is None:
            smoothed_knee = prev_knee
        elif prev_knee is None:
            smoothed_knee = point["knee_angle"]
            prev_knee = smoothed_knee
        else:
            prev_knee = alpha * point["knee_angle"] + (1.0 - alpha) * prev_knee
            smoothed_knee = prev_knee
        smoothed.append({**point, "pelvis_z": prev_z, "knee_angle": smoothed_knee})
    return smoothed


def _pelvis_signal(frame_metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for idx, metrics in enumerate(frame_metrics):
        pelvis_z = (metrics.get("distances") or {}).get("pelvis_center_z_mm")
        if pelvis_z is None:
            continue
        left_knee = (metrics.get("angles_deg") or {}).get("left_knee")
        right_knee = (metrics.get("angles_deg") or {}).get("right_knee")
        knees = [v for v in (left_knee, right_knee) if v is not None]
        out.append(
            {
                "pos": idx,
                "frame_index": _frame_index(metrics, idx),
                "pelvis_z": float(pelvis_z),
                "knee_angle": sum(knees) / len(knees) if knees else None,
            }
        )
    return out


def _single_event(frame_metrics: list[dict[str, Any]], fps: float) -> list[dict[str, Any]]:
    return [
        {
            "index": 1,
            "type": "event",
            "start_frame": _frame_index(frame_metrics[0], 0),
            "end_frame": _frame_index(frame_metrics[-1], len(frame_metrics) - 1),
            "duration_s": len(frame_metrics) / fps if fps > 0 else None,
        }
    ]


def _append_pelvis_rep_or_rejection(
    reps: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    signal: list[dict[str, Any]],
    frame_metrics: list[dict[str, Any]],
    start_pos: int,
    bottom_pos: int,
    end_pos: int,
    min_travel: float,
    min_duration_s: float,
    max_duration_s: float,
    max_missing_ratio: float,
    fps: float,
) -> None:
    start = signal[start_pos]
    bottom = signal[bottom_pos]
    end = signal[end_pos]
    pelvis_values = [item["pelvis_z"] for item in signal[start_pos:end_pos + 1]]
    knee_values = [item["knee_angle"] for item in signal[start_pos:end_pos + 1] if item["knee_angle"] is not None]
    travel = max(pelvis_values) - min(pelvis_values) if pelvis_values else 0.0
    duration_s = (end["frame_index"] - start["frame_index"] + 1) / fps if fps > 0 else None
    missing_ratio = _missing_ratio(frame_metrics, start["frame_index"], end["frame_index"])
    base = {
        "start_frame": start["frame_index"],
        "bottom_frame": bottom["frame_index"],
        "end_frame": end["frame_index"],
        "pelvis_travel_mm": round(travel, 4),
        "duration_s": duration_s,
        "missing_frame_ratio": round(missing_ratio, 4),
    }
    if travel < min_travel:
        rejected.append({**base, "reason_code": "low_rom", "message": f"Pelvis vertical travel {travel:.1f}mm below {min_travel:.1f}mm"})
        return
    if duration_s is not None and duration_s < min_duration_s:
        rejected.append({**base, "reason_code": "too_short", "message": f"Rep duration {duration_s:.2f}s below {min_duration_s:.2f}s"})
        return
    if duration_s is not None and duration_s > max_duration_s:
        rejected.append({**base, "reason_code": "too_long", "message": f"Rep duration {duration_s:.2f}s above {max_duration_s:.2f}s"})
        return
    if missing_ratio > max_missing_ratio:
        rejected.append({**base, "reason_code": "missing_joints", "message": f"Missing/low-quality frame ratio {missing_ratio:.0%} above {max_missing_ratio:.0%}"})
        return
    knee_rom_deg = (max(knee_values) - min(knee_values)) if knee_values else None
    reps.append(
        {
            "index": len(reps) + 1,
            "type": "rep",
            "segmentation_method": "pelvis_z_plus_knee_hysteresis",
            **base,
            "min_signal": min(knee_values) if knee_values else None,
            "max_signal": max(knee_values) if knee_values else None,
            "knee_rom_deg": knee_rom_deg,
        }
    )


def _rejected(frame_metrics: list[dict[str, Any]], reason_code: str, message: str) -> dict[str, Any]:
    start = _frame_index(frame_metrics[0], 0) if frame_metrics else None
    end = _frame_index(frame_metrics[-1], len(frame_metrics) - 1) if frame_metrics else None
    return {
        "start_frame": start,
        "end_frame": end,
        "reason_code": reason_code,
        "message": message,
    }


def _ema_signal(signal: list[tuple[int, float]], alpha: float) -> list[tuple[int, float]]:
    alpha = max(0.0, min(1.0, alpha))
    if not signal or alpha <= 0:
        return signal
    out = []
    prev = signal[0][1]
    for frame_idx, value in signal:
        prev = alpha * value + (1.0 - alpha) * prev
        out.append((frame_idx, prev))
    return out


def _append_rep_if_valid(
    reps: list[dict[str, Any]],
    pending: dict[str, int],
    end_pos: int,
    signal: list[tuple[int, float]],
    frame_metrics: list[dict[str, Any]],
    fps: float,
    min_rom: float,
    min_duration_s: float,
    max_duration_s: float,
    max_missing_ratio: float,
) -> None:
    start_pos = max(0, int(pending["start_pos"]))
    bottom_pos = max(start_pos, int(pending["bottom_pos"]))
    end_pos = max(bottom_pos, min(end_pos, len(signal) - 1))
    rep_values = [value for _, value in signal[start_pos:end_pos + 1]]
    if not rep_values:
        return
    duration_s = (signal[end_pos][0] - signal[start_pos][0] + 1) / fps if fps > 0 else None
    rom = max(rep_values) - min(rep_values)
    missing_ratio = _missing_ratio(frame_metrics, signal[start_pos][0], signal[end_pos][0])
    if rom < min_rom:
        return
    if duration_s is not None and duration_s < min_duration_s:
        return
    if duration_s is not None and duration_s > max_duration_s:
        return
    if missing_ratio > max_missing_ratio:
        return
    reps.append(
        {
            "index": len(reps) + 1,
            "type": "rep",
            "segmentation_method": "hysteresis",
            "start_frame": signal[start_pos][0],
            "bottom_frame": signal[bottom_pos][0],
            "end_frame": signal[end_pos][0],
            "duration_s": duration_s,
            "min_signal": min(rep_values),
            "max_signal": max(rep_values),
            "knee_rom_deg": rom,
            "missing_frame_ratio": round(missing_ratio, 4),
        }
    )


def _missing_ratio(frame_metrics: list[dict[str, Any]], start_frame: int, end_frame: int) -> float:
    selected = [
        m for i, m in enumerate(frame_metrics)
        if start_frame <= _frame_index(m, i) <= end_frame
    ]
    if not selected:
        return 1.0
    low_quality = sum(1 for m in selected if m.get("quality", {}).get("valid_joint_ratio", 0.0) < 0.35)
    return low_quality / len(selected)


def _value_for_frame(signal: list[tuple[int, float]], frame_idx: int) -> float | None:
    for idx, value in signal:
        if idx == frame_idx:
            return value
    return None


def _frame_index(metrics: dict[str, Any], fallback: int) -> int:
    value = metrics.get("frame_index", fallback)
    return int(value if value is not None else fallback)
