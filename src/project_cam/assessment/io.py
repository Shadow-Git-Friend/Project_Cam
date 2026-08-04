"""Input/output adapters for Project_Cam motion JSON and UDP joint JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .joints import JOINT_NAME_TO_INDEX, JOINT_NAMES, empty_joint_list


def load_motion(path: str | Path, default_fps: float = 15.0) -> list[dict[str, Any]]:
    """Load existing offline JSON or UDP JSONL into normalized frame records."""
    motion_path = Path(path)
    if motion_path.suffix.lower() == ".jsonl":
        return _load_jsonl(motion_path, default_fps=default_fps)
    return _load_json(motion_path, default_fps=default_fps)


def write_json(path: str | Path, payload: Any) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def _load_json(path: Path, default_fps: float) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        raw_frames = data.get("frames", [])
        session = data.get("session", {})
    elif isinstance(data, list):
        raw_frames = data
        session = {}
    else:
        raise ValueError(f"{path} must contain a JSON object or list of frame records")

    return [
        normalize_frame(record, index=idx, default_fps=default_fps, source=str(path), session=session)
        for idx, record in enumerate(raw_frames)
        if isinstance(record, dict)
    ]


def _load_jsonl(path: Path, default_fps: float) -> list[dict[str, Any]]:
    frames = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            if not isinstance(record, dict):
                continue
            frames.append(
                normalize_frame(record, index=idx, default_fps=default_fps, source=str(path), session=record.get("session", {}))
            )
    return frames


def normalize_frame(
    record: dict[str, Any],
    index: int,
    default_fps: float,
    source: str,
    session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frame_index = int(record.get("frame_index", record.get("frame", index)))
    time_s = record.get("time_s", record.get("elapsed_s"))
    if time_s is None:
        time_s = frame_index / default_fps if default_fps > 0 else float(index)

    joints_raw = record.get("joints_3d", record.get("joints", {}))
    joints, conf, cams = normalize_joints(joints_raw)

    return {
        "frame_index": frame_index,
        "time_s": float(time_s),
        "wall_clock_ts": record.get("ts", record.get("timestamp")),
        "joints": joints,
        "joint_conf": conf,
        "joint_cams": cams,
        "session": dict(session or {}),
        "source": source,
    }


def normalize_joints(raw: Any) -> tuple[list[list[float] | None], list[float], list[int]]:
    joints = empty_joint_list()
    conf = [0.0] * len(JOINT_NAMES)
    cams = [0] * len(JOINT_NAMES)

    if isinstance(raw, list):
        for idx, value in enumerate(raw[: len(JOINT_NAMES)]):
            point = coerce_point(value)
            joints[idx] = point
            if point is not None:
                conf[idx] = 1.0
        return joints, conf, cams

    if isinstance(raw, dict):
        for name, value in raw.items():
            idx = _joint_key_to_index(name)
            if idx is None:
                continue
            point = coerce_point(value)
            joints[idx] = point
            if isinstance(value, dict):
                conf[idx] = _coerce_float(value.get("conf", value.get("score", 1.0)), 0.0)
                cams[idx] = int(_coerce_float(value.get("cams", value.get("camera_count", 0)), 0.0))
            elif point is not None:
                conf[idx] = 1.0
        return joints, conf, cams

    return joints, conf, cams


def coerce_point(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if {"x_mm", "y_mm", "z_mm"}.issubset(value):
            vals = [value["x_mm"], value["y_mm"], value["z_mm"]]
        elif {"x", "y", "z"}.issubset(value):
            vals = [value["x"], value["y"], value["z"]]
        else:
            return None
    elif isinstance(value, (list, tuple)) and len(value) >= 3:
        vals = value[:3]
    else:
        return None

    point = [_coerce_float(v, None) for v in vals]
    if any(v is None for v in point):
        return None
    return [float(v) for v in point]


def _joint_key_to_index(key: Any) -> int | None:
    if isinstance(key, int):
        return key if 0 <= key < len(JOINT_NAMES) else None
    if isinstance(key, str):
        if key in JOINT_NAME_TO_INDEX:
            return JOINT_NAME_TO_INDEX[key]
        if key.isdigit():
            idx = int(key)
            return idx if 0 <= idx < len(JOINT_NAMES) else None
    return None


def _coerce_float(value: Any, default: float | None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

