"""Protocol-compliance checks for offline assessment reports."""

from __future__ import annotations

from typing import Any


def assess_compliance(
    exercise: str,
    frames: list[dict[str, Any]],
    frame_metrics: list[dict[str, Any]],
    reps: list[dict[str, Any]],
    rules: dict[str, Any],
    fps: float,
) -> dict[str, Any]:
    protocol = rules.get("protocol", {})
    min_fps = float(protocol.get("min_fps", 15.0))
    min_valid_frame_ratio = float(protocol.get("min_valid_frame_ratio", 0.6))
    min_reps = int(protocol.get("min_reps", 1))
    min_rom = float(protocol.get("min_rom_deg", rules.get("segmentation", {}).get("min_rom_deg", 25.0)))

    valid_frame_ratio = _valid_frame_ratio(frame_metrics)
    completed_reps = [rep for rep in reps if rep.get("type") == "rep"]
    max_rom = max(
        [float(rep["knee_rom_deg"]) for rep in completed_reps if rep.get("knee_rom_deg") is not None],
        default=0.0,
    )

    reasons = []
    suggestions = []
    if fps < min_fps:
        reasons.append(f"Recording FPS {fps:g} is below the requested {min_fps:g} FPS for {exercise}.")
        suggestions.append("Re-record at the protocol framerate.")
    if valid_frame_ratio < min_valid_frame_ratio:
        reasons.append(f"Only {valid_frame_ratio:.0%} of frames had enough visible joints; expected at least {min_valid_frame_ratio:.0%}.")
        suggestions.append("Re-record with the athlete fully visible to at least two cameras.")
    if exercise != "plank":
        if len(completed_reps) < min_reps or max_rom < min_rom:
            reasons.append(
                f"Only {len(completed_reps)} rep(s) detected with {max_rom:.1f}° maximum ROM; "
                f"expected {min_reps}+ rep(s) with >{min_rom:.0f}° ROM for {exercise} assessment."
            )
            suggestions.append(f"Re-record with full-range {exercise.replace('_', ' ')} repetitions.")
    else:
        min_hold_s = float(protocol.get("min_hold_s", 5.0))
        hold_s = reps[0].get("duration_s", 0.0) if reps else 0.0
        if hold_s < min_hold_s:
            reasons.append(f"Plank hold was {hold_s:.1f}s; expected at least {min_hold_s:.1f}s.")
            suggestions.append("Re-record a longer plank hold.")

    if reasons:
        return {
            "status": "insufficient",
            "reason": " ".join(reasons),
            "suggestion": " ".join(suggestions) if suggestions else "Re-record the exercise protocol.",
            "completed_reps": len(completed_reps),
            "max_rom_deg": round(max_rom, 4),
            "valid_frame_ratio": round(valid_frame_ratio, 4),
            "required": {
                "min_fps": min_fps,
                "min_reps": min_reps,
                "min_rom_deg": min_rom,
                "min_valid_frame_ratio": min_valid_frame_ratio,
            },
        }

    return {
        "status": "ok",
        "reason": "Movement pattern and data coverage matched the configured protocol checks.",
        "suggestion": None,
        "completed_reps": len(completed_reps),
        "max_rom_deg": round(max_rom, 4),
        "valid_frame_ratio": round(valid_frame_ratio, 4),
        "required": {
            "min_fps": min_fps,
            "min_reps": min_reps,
            "min_rom_deg": min_rom,
            "min_valid_frame_ratio": min_valid_frame_ratio,
        },
    }


def _valid_frame_ratio(frame_metrics: list[dict[str, Any]]) -> float:
    if not frame_metrics:
        return 0.0
    valid = 0
    for metrics in frame_metrics:
        if metrics.get("quality", {}).get("valid_joint_ratio", 0.0) >= 0.35:
            valid += 1
    return valid / len(frame_metrics)

