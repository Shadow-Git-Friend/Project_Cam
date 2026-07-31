"""Fail-closed all-person clearance gate for pose-driven launcher shots.

This module owns no sockets, serial ports, threads, or hardware.  The viewer
publishes a versioned world-space snapshot and a launcher runtime supplies the
actual commanded ballistic path.  A shot is allowed only when the snapshot is
fresh, internally consistent, and every localized non-primary body is outside
the swept trajectory corridor.

Face labels are intentionally absent from this API: identity is never fire
authorization.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from numbers import Integral, Real
from types import MappingProxyType
from typing import Any, Iterable, Mapping

import numpy as np

FIRING_LINE_SCHEMA = "project_cam.firing_line.v1"
FIRING_LINE_GEOMETRY_ID = "world_mm"
MAX_BALLISTIC_CHORD_ERROR_MM = 25.0
MAX_SAFETY_PEOPLE = 8
MAX_TRAJECTORY_POINTS = 256

# COCO-17 bones.  Individual usable joints are checked as points too, which
# covers partial detections whose neighboring joint is unavailable.
COCO_BODY_SEGMENTS = (
    ("nose", "left_eye"),
    ("nose", "right_eye"),
    ("left_eye", "right_eye"),
    ("left_eye", "left_ear"),
    ("right_eye", "right_ear"),
    ("left_ear", "left_shoulder"),
    ("right_ear", "right_shoulder"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"),
    ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"),
    ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"),
    ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"),
    ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"),
    ("right_knee", "right_ankle"),
)
COCO_JOINT_NAMES = frozenset(
    joint_name for segment in COCO_BODY_SEGMENTS for joint_name in segment
)


@dataclass(frozen=True)
class FiringLineDecision:
    """One immediate authorization result; clear results must not be cached."""

    ok: bool
    reason: str | None
    message: str | None
    detail: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a detached JSON-safe representation for decision logs."""

        return {
            "ok": self.ok,
            "reason": self.reason,
            "message": self.message,
            "detail": _thaw_detail(self.detail),
        }


def _freeze_detail(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return MappingProxyType(
            {str(key): _freeze_detail(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_detail(item) for item in value)
    if isinstance(value, np.generic):
        return value.item()
    return value


def _thaw_detail(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {str(key): _thaw_detail(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_detail(item) for item in value]
    return value


def _allow(**detail: Any) -> FiringLineDecision:
    return FiringLineDecision(True, None, None, _freeze_detail(detail))


def _block(reason: str, message: str, **detail: Any) -> FiringLineDecision:
    return FiringLineDecision(False, reason, message, _freeze_detail(detail))


def _finite_vector(value: Any, size: int, label: str) -> np.ndarray:
    try:
        raw = np.asarray(value, dtype=object).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if raw.shape != (size,):
        raise ValueError(f"{label} must contain {size} finite values")
    if any(isinstance(item, (bool, np.bool_)) or not isinstance(item, Real) for item in raw):
        raise ValueError(f"{label} must contain numeric JSON values")
    try:
        array = raw.astype(np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} values exceed the numeric range") from exc
    if not np.isfinite(array).all():
        raise ValueError(f"{label} must contain {size} finite values")
    return array


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{label} must be a numeric JSON value")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} exceeds the numeric range") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _plain_int(value: Any, label: str) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be an integer")
    return int(value)


def sample_ballistic_path_mm(
    *,
    launcher_xyz_mm: Iterable[float],
    launcher_yaw_deg: float,
    pitch_deg: float,
    yaw_deg: float,
    speed_mps: float,
    horizontal_distance_mm: float,
    extension_mm: float = 1000.0,
    samples: int = 48,
    gravity_m_s2: float = 9.81,
) -> np.ndarray:
    """Sample the commanded low ballistic arc in the viewer's world frame.

    ``launcher_yaw_deg`` defines the launcher's world-forward vector.  The
    commanded ``yaw_deg`` is relative to that vector and positive toward the
    launcher's right, matching ``launcher_common.py``.
    """

    origin = _finite_vector(launcher_xyz_mm, 3, "launcher_xyz_mm")
    launcher_yaw = math.radians(_finite_float(launcher_yaw_deg, "launcher_yaw_deg"))
    pitch = math.radians(_finite_float(pitch_deg, "pitch_deg"))
    horizontal_angle = math.radians(_finite_float(yaw_deg, "yaw_deg"))
    speed = _finite_float(speed_mps, "speed_mps")
    distance = _finite_float(horizontal_distance_mm, "horizontal_distance_mm")
    extension = _finite_float(extension_mm, "extension_mm")
    gravity = _finite_float(gravity_m_s2, "gravity_m_s2")
    requested_count = _plain_int(samples, "samples")
    if speed <= 0.0:
        raise ValueError("speed_mps must be > 0")
    if distance <= 0.0:
        raise ValueError("horizontal_distance_mm must be > 0")
    if extension < 0.0:
        raise ValueError("extension_mm must be >= 0")
    if gravity <= 0.0:
        raise ValueError("gravity_m_s2 must be > 0")
    if requested_count < 2:
        raise ValueError("samples must be >= 2")

    horizontal_speed = speed * math.cos(pitch)
    if horizontal_speed <= 1e-6:
        raise ValueError("pitch leaves no positive horizontal velocity")

    forward = np.array(
        [math.cos(launcher_yaw), math.sin(launcher_yaw), 0.0], dtype=np.float64
    )
    right = np.array([forward[1], -forward[0], 0.0], dtype=np.float64)
    direction = math.cos(horizontal_angle) * forward + math.sin(horizontal_angle) * right

    total_horizontal_m = (distance + extension) / 1000.0
    total_time_s = total_horizontal_m / horizontal_speed
    max_error_m = MAX_BALLISTIC_CHORD_ERROR_MM / 1000.0
    segment_estimate = total_time_s * math.sqrt(
        gravity / (8.0 * max_error_m)
    )
    if not all(
        math.isfinite(value)
        for value in (total_horizontal_m, total_time_s, segment_estimate)
    ):
        raise ValueError("derived ballistic trajectory exceeds the numeric range")
    minimum_segments = max(
        1,
        int(math.ceil(segment_estimate)),
    )
    count = max(requested_count, minimum_segments + 1)
    if count > MAX_TRAJECTORY_POINTS:
        raise ValueError(
            "trajectory needs more points than the safety computation cap"
        )
    travel_m = np.linspace(0.0, total_horizontal_m, count)
    elapsed_s = travel_m / horizontal_speed
    vertical_m = (
        speed * math.sin(pitch) * elapsed_s
        - 0.5 * gravity * elapsed_s * elapsed_s
    )
    path = origin[None, :] + travel_m[:, None] * 1000.0 * direction[None, :]
    path[:, 2] = origin[2] + vertical_m * 1000.0
    return path


def _point_segment_distance(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    delta = end - start
    denom = float(np.dot(delta, delta))
    if denom <= 1e-18:
        return float(np.linalg.norm(point - start))
    amount = float(np.clip(np.dot(point - start, delta) / denom, 0.0, 1.0))
    return float(np.linalg.norm(point - (start + amount * delta)))


def _segment_distance_arrays(
    p0: np.ndarray, p1: np.ndarray, q0: np.ndarray, q1: np.ndarray
) -> float:
    u = p1 - p0
    v = q1 - q0
    w = p0 - q0
    a = float(np.dot(u, u))
    b = float(np.dot(u, v))
    c = float(np.dot(v, v))
    d = float(np.dot(u, w))
    e = float(np.dot(v, w))
    eps = 1e-12

    if a <= eps and c <= eps:
        return float(np.linalg.norm(p0 - q0))
    if a <= eps:
        return _point_segment_distance(p0, q0, q1)
    if c <= eps:
        return _point_segment_distance(q0, p0, p1)

    denominator = a * c - b * b
    s_numerator = 0.0
    s_denominator = denominator
    t_numerator = 0.0
    t_denominator = denominator
    if denominator <= eps:
        s_numerator = 0.0
        s_denominator = 1.0
        t_numerator = e
        t_denominator = c
    else:
        s_numerator = b * e - c * d
        t_numerator = a * e - b * d
        if s_numerator < 0.0:
            s_numerator = 0.0
            t_numerator = e
            t_denominator = c
        elif s_numerator > s_denominator:
            s_numerator = s_denominator
            t_numerator = e + b
            t_denominator = c

    if t_numerator < 0.0:
        t_numerator = 0.0
        if -d < 0.0:
            s_numerator = 0.0
        elif -d > a:
            s_numerator = s_denominator
        else:
            s_numerator = -d
            s_denominator = a
    elif t_numerator > t_denominator:
        t_numerator = t_denominator
        if -d + b < 0.0:
            s_numerator = 0.0
        elif -d + b > a:
            s_numerator = s_denominator
        else:
            s_numerator = -d + b
            s_denominator = a

    s = 0.0 if abs(s_numerator) <= eps else s_numerator / s_denominator
    t = 0.0 if abs(t_numerator) <= eps else t_numerator / t_denominator
    closest_delta = w + s * u - t * v
    return float(np.linalg.norm(closest_delta))


def segment_distance_3d(a0: Any, a1: Any, b0: Any, b1: Any) -> float:
    """Return the shortest Euclidean distance between two finite 3D segments."""

    return _segment_distance_arrays(
        _finite_vector(a0, 3, "a0"),
        _finite_vector(a1, 3, "a1"),
        _finite_vector(b0, 3, "b0"),
        _finite_vector(b1, 3, "b1"),
    )


def _minimum_path_distance(
    path: np.ndarray, start: np.ndarray, end: np.ndarray
) -> float:
    return min(
        _segment_distance_arrays(path[index], path[index + 1], start, end)
        for index in range(len(path) - 1)
    )


def evaluate_firing_line(
    snapshot: dict[str, Any] | None,
    path_mm: Any,
    *,
    expected_primary_track_id: int | None = None,
    expected_primary_epoch: int | None = None,
    expected_y_mirrored: bool | None = None,
    now: float | None = None,
    max_staleness_s: float = 0.5,
    corridor_radius_mm: float = 600.0,
    trajectory_error_margin_mm: float = 0.0,
    min_joint_conf: float = 0.2,
    min_joint_cams: int = 2,
    min_person_joints: int = 3,
    max_joint_age_frames: int = 6,
    max_track_age_frames: int = 6,
) -> FiringLineDecision:
    """Evaluate one snapshot against one already-commanded trajectory.

    The function never converts malformed safety data into an allow.  Expected
    validation failures become structured block decisions; unrelated programmer
    errors are deliberately not swallowed.
    """

    if snapshot is None:
        return _block("clearance_missing", "no all-person safety snapshot available")
    if not isinstance(snapshot, dict):
        return _block("malformed_snapshot", "safety snapshot must be an object")
    try:
        path = np.asarray(path_mm, dtype=np.float64)
    except (TypeError, ValueError, OverflowError):
        return _block("invalid_trajectory", "trajectory must be numeric")
    if path.ndim != 2 or path.shape[0] < 2 or path.shape[1] != 3 or not np.isfinite(path).all():
        return _block("invalid_trajectory", "trajectory must have shape (N>=2, 3) and be finite")
    if path.shape[0] > MAX_TRAJECTORY_POINTS:
        return _block(
            "capacity_exceeded",
            "trajectory exceeds the bounded safety computation capacity",
            trajectory_points=int(path.shape[0]),
            max_trajectory_points=MAX_TRAJECTORY_POINTS,
        )

    try:
        max_age = _finite_float(max_staleness_s, "max_staleness_s")
        radius = _finite_float(corridor_radius_mm, "corridor_radius_mm")
        trajectory_margin = _finite_float(
            trajectory_error_margin_mm, "trajectory_error_margin_mm"
        )
        confidence_floor = _finite_float(min_joint_conf, "min_joint_conf")
        camera_floor = _plain_int(min_joint_cams, "min_joint_cams")
        joint_floor = _plain_int(min_person_joints, "min_person_joints")
        joint_age_limit = _plain_int(max_joint_age_frames, "max_joint_age_frames")
        track_age_limit = _plain_int(max_track_age_frames, "max_track_age_frames")
        if (
            max_age <= 0
            or radius <= 0
            or trajectory_margin < 0
            or not 0 <= confidence_floor <= 1
        ):
            raise ValueError("invalid positive safety threshold")
        if (
            camera_floor < 1
            or joint_floor < 1
            or joint_age_limit < 0
            or track_age_limit < 0
        ):
            raise ValueError("invalid integer safety threshold")
    except ValueError as exc:
        return _block("invalid_configuration", str(exc))

    if snapshot.get("schema") != FIRING_LINE_SCHEMA:
        return _block(
            "schema_mismatch",
            "unsupported or missing firing-line schema",
            expected=FIRING_LINE_SCHEMA,
            actual=snapshot.get("schema"),
        )
    if snapshot.get("geometry_id") != FIRING_LINE_GEOMETRY_ID:
        return _block(
            "geometry_mismatch",
            "safety snapshot is not in the required world-mm frame",
            expected=FIRING_LINE_GEOMETRY_ID,
            actual=snapshot.get("geometry_id"),
        )
    mirrored = snapshot.get("y_mirrored")
    if not isinstance(mirrored, (bool, np.bool_)):
        return _block("malformed_snapshot", "y_mirrored must be boolean")
    if snapshot.get("mode") != "multi_person":
        return _block(
            "multi_person_required",
            "firing requires a multi-person tracking safety stream",
        )

    try:
        current_time = time.time() if now is None else _finite_float(now, "now")
        snapshot_time = _finite_float(snapshot.get("snapshot_ts"), "snapshot_ts")
        age_s = current_time - snapshot_time
    except ValueError as exc:
        return _block("malformed_snapshot", str(exc))
    if age_s < -0.5:
        return _block("malformed_snapshot", "snapshot timestamp is in the future", age_s=age_s)
    if age_s > max_age:
        return _block(
            "clearance_stale",
            f"safety snapshot age {age_s:.3f}s exceeds {max_age:.3f}s",
            age_s=age_s,
            max_staleness_s=max_age,
        )

    ambiguous = snapshot.get("ambiguous_detections")
    if not isinstance(ambiguous, (bool, np.bool_)):
        return _block("malformed_snapshot", "ambiguous_detections must be boolean")
    try:
        unassigned = _plain_int(
            snapshot.get("unassigned_candidate_count"),
            "unassigned_candidate_count",
        )
    except ValueError as exc:
        return _block("malformed_snapshot", str(exc))
    if unassigned < 0:
        return _block(
            "malformed_snapshot",
            "unassigned_candidate_count must be >= 0",
        )
    if bool(ambiguous) or unassigned > 0:
        return _block(
            "ambiguous_detections",
            "one or more pose detections are not safely associated to a track",
            unassigned_candidate_count=unassigned,
        )

    try:
        frame = _plain_int(snapshot.get("frame"), "frame")
        primary_track_id = _plain_int(
            snapshot.get("primary_track_id"), "primary_track_id"
        )
        primary_epoch = _plain_int(snapshot.get("primary_epoch"), "primary_epoch")
        observed_count = _plain_int(
            snapshot.get("observed_person_count"), "observed_person_count"
        )
    except ValueError as exc:
        return _block("malformed_snapshot", str(exc))
    if frame < 0:
        return _block("malformed_snapshot", "frame must be >= 0")
    if primary_track_id <= 0:
        return _block("malformed_snapshot", "primary_track_id must be > 0")
    if primary_epoch < 0:
        return _block("malformed_snapshot", "primary_epoch must be >= 0")
    if observed_count < 1:
        return _block("malformed_snapshot", "observed_person_count must be >= 1")
    if (
        expected_primary_track_id is None
        or expected_primary_epoch is None
        or expected_y_mirrored is None
    ):
        return _block(
            "aim_context_missing",
            "primary track, epoch, and mirror mode captured at aim are required",
        )
    try:
        expected_track_id = _plain_int(
            expected_primary_track_id, "expected_primary_track_id"
        )
        expected_epoch = _plain_int(
            expected_primary_epoch, "expected_primary_epoch"
        )
    except ValueError as exc:
        return _block("aim_context_invalid", str(exc))
    if expected_track_id <= 0 or expected_epoch < 0 or not isinstance(
        expected_y_mirrored, (bool, np.bool_)
    ):
        return _block(
            "aim_context_invalid",
            "aim context values have invalid types or ranges",
        )
    if bool(mirrored) != bool(expected_y_mirrored):
        return _block("geometry_mismatch", "snapshot Y-mirror mode changed")
    if primary_track_id != expected_track_id:
        return _block(
            "primary_changed",
            "primary track changed after aim",
            expected_primary_track_id=expected_track_id,
            primary_track_id=primary_track_id,
        )
    if primary_epoch != expected_epoch:
        return _block(
            "primary_changed",
            "primary epoch changed after aim",
            expected_primary_epoch=expected_epoch,
            primary_epoch=primary_epoch,
        )

    people = snapshot.get("people")
    if not isinstance(people, list):
        return _block("malformed_snapshot", "people must be an array")
    if len(people) > MAX_SAFETY_PEOPLE:
        return _block(
            "capacity_exceeded",
            "people array exceeds the bounded safety computation capacity",
            people_count=len(people),
            max_people=MAX_SAFETY_PEOPLE,
        )
    if observed_count != len(people):
        return _block(
            "person_count_mismatch",
            "observed_person_count does not match people array",
            observed_person_count=observed_count,
            people_count=len(people),
        )

    parsed_people: list[tuple[int, bool, dict[str, np.ndarray]]] = []
    track_ids: set[int] = set()
    primary_markers: list[int] = []
    for person in people:
        if not isinstance(person, dict):
            return _block("malformed_snapshot", "each person must be an object")
        try:
            track_id = _plain_int(person.get("track_id"), "track_id")
            track_last_seen = _plain_int(
                person.get("track_last_seen_frame"),
                "track_last_seen_frame",
            )
        except ValueError as exc:
            return _block("malformed_snapshot", str(exc))
        if track_id <= 0:
            return _block("malformed_snapshot", "track_id must be > 0")
        if track_last_seen < 0 or track_last_seen > frame:
            return _block(
                "malformed_snapshot",
                "track_last_seen_frame must be between zero and snapshot frame",
                track_id=track_id,
            )
        if frame - track_last_seen > track_age_limit:
            return _block(
                "track_stale",
                "tracked person has not been confirmed recently enough",
                track_id=track_id,
                track_age_frames=frame - track_last_seen,
                max_track_age_frames=track_age_limit,
            )
        if track_id in track_ids:
            return _block("duplicate_track_id", "people array contains a duplicate track ID", track_id=track_id)
        track_ids.add(track_id)
        primary_flag = person.get("primary")
        if not isinstance(primary_flag, (bool, np.bool_)):
            return _block("malformed_snapshot", "person.primary must be boolean", track_id=track_id)
        if primary_flag:
            primary_markers.append(track_id)
        joints_obj = person.get("joints")
        if not isinstance(joints_obj, dict):
            return _block("malformed_snapshot", "person.joints must be an object", track_id=track_id)

        usable: dict[str, np.ndarray] = {}
        for joint_name, joint in joints_obj.items():
            if not isinstance(joint_name, str) or not isinstance(joint, dict):
                return _block("malformed_snapshot", "joint entries must be named objects", track_id=track_id)
            if joint_name not in COCO_JOINT_NAMES:
                return _block(
                    "malformed_snapshot",
                    "joint name is not part of the COCO-17 schema",
                    track_id=track_id,
                    joint=joint_name,
                )
            try:
                point = _finite_vector(
                    [joint.get("x_mm"), joint.get("y_mm"), joint.get("z_mm")],
                    3,
                    f"joint {joint_name}",
                )
                conf = _finite_float(joint.get("conf"), f"joint {joint_name}.conf")
                cams = _plain_int(joint.get("cams"), f"joint {joint_name}.cams")
                last_seen = _plain_int(
                    joint.get("last_seen_frame"),
                    f"joint {joint_name}.last_seen_frame",
                )
            except ValueError as exc:
                return _block("malformed_snapshot", str(exc), track_id=track_id)
            if not 0.0 <= conf <= 1.0:
                return _block(
                    "malformed_snapshot",
                    "joint confidence must be between zero and one",
                    track_id=track_id,
                    joint=joint_name,
                )
            if cams < 0 or last_seen < 0:
                return _block(
                    "malformed_snapshot",
                    "joint cameras and last-seen frame must be non-negative",
                    track_id=track_id,
                    joint=joint_name,
                )
            if last_seen > frame:
                return _block(
                    "malformed_snapshot",
                    "joint last_seen_frame is newer than snapshot frame",
                    track_id=track_id,
                    joint=joint_name,
                )
            if (
                conf >= confidence_floor
                and cams >= camera_floor
                and frame - last_seen <= joint_age_limit
            ):
                usable[joint_name] = point
        parsed_people.append((track_id, bool(primary_flag), usable))

    if primary_track_id not in track_ids or primary_markers != [primary_track_id]:
        return _block(
            "primary_invalid",
            "snapshot must contain exactly one primary matching primary_track_id",
            primary_track_id=primary_track_id,
            primary_markers=primary_markers,
        )

    closest_distance: float | None = None
    closest_track: int | None = None
    closest_joint: str | None = None
    secondary_count = 0
    for track_id, is_primary, joints in parsed_people:
        if is_primary:
            continue
        secondary_count += 1
        if len(joints) < joint_floor:
            return _block(
                "person_unlocalized",
                "non-primary person lacks enough fresh multi-camera joints",
                track_id=track_id,
                usable_joint_count=len(joints),
                min_person_joints=joint_floor,
            )

        for joint_name, point in joints.items():
            distance = _minimum_path_distance(path, point, point)
            if closest_distance is None or distance < closest_distance:
                closest_distance = distance
                closest_track = track_id
                closest_joint = joint_name
        for first_name, second_name in COCO_BODY_SEGMENTS:
            if first_name not in joints or second_name not in joints:
                continue
            distance = _minimum_path_distance(
                path, joints[first_name], joints[second_name]
            )
            if closest_distance is None or distance < closest_distance:
                closest_distance = distance
                closest_track = track_id
                closest_joint = f"{first_name}-{second_name}"

    final_age_s = (
        time.time() - snapshot_time if now is None else age_s
    )
    if final_age_s > max_age:
        return _block(
            "clearance_stale",
            "safety snapshot expired during clearance evaluation",
            age_s=final_age_s,
            max_staleness_s=max_age,
        )
    effective_radius = radius + trajectory_margin
    detail = {
        "age_s": final_age_s,
        "primary_track_id": primary_track_id,
        "primary_epoch": primary_epoch,
        "observed_person_count": observed_count,
        "secondary_person_count": secondary_count,
        "corridor_radius_mm": radius,
        "trajectory_error_margin_mm": trajectory_margin,
        "effective_corridor_radius_mm": effective_radius,
        "closest_track_id": closest_track,
        "closest_joint": closest_joint,
        "closest_distance_mm": closest_distance,
    }
    if closest_distance is not None and closest_distance <= effective_radius:
        return _block(
            "firing_line_blocked",
            "a non-primary person intersects the commanded ballistic corridor",
            **detail,
        )
    return _allow(**detail)


def evaluate_shot_clearance(
    snapshot: dict[str, Any] | None,
    *,
    launcher_xyz_mm: Iterable[float],
    launcher_yaw_deg: float,
    pitch_deg: float,
    yaw_deg: float,
    speed_mps: float,
    target_xyz_mm: Iterable[float],
    extension_mm: float = 1000.0,
    trajectory_samples: int = 48,
    gravity_m_s2: float = 9.81,
    **gate_kwargs: Any,
) -> FiringLineDecision:
    """Build the actual commanded arc, then evaluate it fail-closed."""

    try:
        launcher = _finite_vector(launcher_xyz_mm, 3, "launcher_xyz_mm")
        target = _finite_vector(target_xyz_mm, 3, "target_xyz_mm")
        horizontal_distance = float(np.linalg.norm((target - launcher)[:2]))
        path = sample_ballistic_path_mm(
            launcher_xyz_mm=launcher,
            launcher_yaw_deg=launcher_yaw_deg,
            pitch_deg=pitch_deg,
            yaw_deg=yaw_deg,
            speed_mps=speed_mps,
            horizontal_distance_mm=horizontal_distance,
            extension_mm=extension_mm,
            samples=trajectory_samples,
            gravity_m_s2=gravity_m_s2,
        )
    except (ValueError, OverflowError) as exc:
        return _block("invalid_trajectory", str(exc))
    # The polyline under-approximates the continuous parabola by at most this
    # amount, so inflate rather than risk a false-clear between sample points.
    gate_kwargs["trajectory_error_margin_mm"] = MAX_BALLISTIC_CHORD_ERROR_MM
    return evaluate_firing_line(snapshot, path, **gate_kwargs)


__all__ = [
    "COCO_BODY_SEGMENTS",
    "COCO_JOINT_NAMES",
    "FIRING_LINE_GEOMETRY_ID",
    "FIRING_LINE_SCHEMA",
    "FiringLineDecision",
    "MAX_BALLISTIC_CHORD_ERROR_MM",
    "MAX_SAFETY_PEOPLE",
    "MAX_TRAJECTORY_POINTS",
    "evaluate_firing_line",
    "evaluate_shot_clearance",
    "sample_ballistic_path_mm",
    "segment_distance_3d",
]
