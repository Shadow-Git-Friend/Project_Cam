"""Camera-attached live coach overlay for the 4-camera trainer.

This module is intentionally pure OpenCV/numpy helper code: it does not open
cameras, windows, sockets, or config files. The tracker owns live frames and
passes the freshest 2D/3D pose into these helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .rep_state import RepState


_FONT = cv2.FONT_HERSHEY_SIMPLEX

_TEXT = (245, 245, 245)
_MUTE = (165, 165, 172)
_DARK = (20, 22, 26)
_PANEL = (34, 36, 42)
_GREEN = (96, 215, 118)
_BLUE = (235, 178, 76)
_AMBER = (62, 190, 244)
_RED = (78, 86, 236)
_YELLOW = (88, 224, 238)

_SKELETON_EDGES = [
    (5, 7), (7, 9), (6, 8), (8, 10),
    (11, 13), (13, 15), (12, 14), (14, 16),
    (5, 6), (11, 12), (5, 11), (6, 12),
]
_JOINTS_FOR_VALIDITY = (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
_PUSHUP_PROJECTED_REPAIR_JOINTS = (11, 12, 13, 14, 15, 16)

# Parent joint of each lower-body joint, used to reject a projected joint
# whose bone to its parent is anatomically impossible (a joint that landed on
# the wall / pillow / door behind the athlete).
_LOWER_BODY_PARENT = {11: 5, 12: 6, 13: 11, 14: 12, 15: 13, 16: 14}
# A repaired bone may not exceed this multiple of the athlete's shoulder span.
_MAX_BONE_TO_SHOULDER_RATIO = 4.0

# Push-up leg-chain validation. A drawn leg joint must clear a higher score
# bar and form an anatomically plausible chain with the (reliable) torso,
# otherwise it is dropped rather than drawn pinned to background clutter.
_PUSHUP_LEG_JOINTS = (13, 14, 15, 16)
_PUSHUP_LEG_MIN_SCORE = 0.5
_LEG_BONE_MIN_RATIO = 0.30   # single-segment bone length / torso length
_LEG_BONE_MAX_RATIO = 1.9
_LEG_FULL_MIN_RATIO = 0.60   # hip->ankle span when the knee was dropped
_LEG_FULL_MAX_RATIO = 3.2
_LEG_AXIS_MIN_COS = 0.5      # leg must extend within ~60 deg of the body axis

# Push-up floor anchor. Wrists are the actual hand-floor contacts and are
# anchored by default; ankles are only joined into the floor line after they
# have been continuously valid (passed leg-chain validation) for several
# consecutive frames, so a single-frame fluke cannot pull the floor line off
# the hands.
_PUSHUP_FLOOR_ANKLE_STREAK_FRAMES = 5

_PHASE_COLOR = {
    "STANDING": _GREEN, "TOP": _GREEN,
    "DESCENDING": _AMBER, "LOWERING": _AMBER,
    "BOTTOM": _RED,
    "ASCENDING": _BLUE, "PUSHING UP": _BLUE,
}


@dataclass(frozen=True)
class Roi:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) * 0.5, (self.y1 + self.y2) * 0.5)


@dataclass(frozen=True)
class AngleLabel:
    text: str
    anchor: tuple[int, int]
    color: tuple[int, int, int] = _YELLOW


class StableRoi:
    """Fixed-size crop that pans smoothly but never auto-zooms per frame."""

    def __init__(self, width: int = 720, height: int = 560, alpha: float = 0.18):
        self.width = int(width)
        self.height = int(height)
        self.alpha = float(max(0.01, min(1.0, alpha)))
        self._center: np.ndarray | None = None

    def update(self, frame_shape: tuple[int, ...], kpts: Any, scores: Any) -> Roi:
        h, w = int(frame_shape[0]), int(frame_shape[1])
        crop_w = min(max(1, self.width), w)
        crop_h = min(max(1, self.height), h)

        pose_center = _pose_center(kpts, scores)
        if pose_center is None:
            target = self._center if self._center is not None else np.array([w * 0.5, h * 0.5])
        else:
            target = pose_center

        if self._center is None:
            self._center = np.asarray(target, dtype=float)
        else:
            self._center = (1.0 - self.alpha) * self._center + self.alpha * np.asarray(target, dtype=float)

        cx = float(np.clip(self._center[0], crop_w * 0.5, w - crop_w * 0.5))
        cy = float(np.clip(self._center[1], crop_h * 0.5, h - crop_h * 0.5))
        self._center = np.array([cx, cy], dtype=float)

        x1 = int(round(cx - crop_w * 0.5))
        y1 = int(round(cy - crop_h * 0.5))
        x1 = max(0, min(w - crop_w, x1))
        y1 = max(0, min(h - crop_h, y1))
        return Roi(x1=x1, y1=y1, x2=x1 + crop_w, y2=y1 + crop_h)


def select_best_camera(
    exercise: str,
    joints_3d: list[Any] | np.ndarray,
    per_cam_pose: dict[str, tuple[Any, Any]],
    camera_positions: dict[str, Any],
    previous_camera: str | None = None,
    switch_margin: float = 0.12,
) -> str | None:
    """Choose the clearest exercise-appropriate camera.

    Squats prefer a front/back view of the body. Push-ups prefer a side view.
    Geometry comes from 3D body orientation and camera positions; 2D pose
    confidence gates out cameras that do not currently see the athlete.
    """
    if not per_cam_pose:
        return previous_camera

    center, lateral, forward = _body_axes(joints_3d)
    scores: dict[str, float] = {}
    for cam, pose in per_cam_pose.items():
        pose_score = _pose_quality(pose)
        if pose_score <= 0.0:
            continue
        align = 0.5
        cam_pos = _as_vec3(camera_positions.get(cam))
        if cam_pos is not None and center is not None and lateral is not None and forward is not None:
            view = center[:2] - cam_pos[:2]
            norm = float(np.linalg.norm(view))
            if norm > 1e-6:
                view /= norm
                desired = lateral if exercise == "push_up" else forward
                align = abs(float(np.dot(view, desired)))
        if exercise == "push_up":
            # Push-ups need the legs in frame, not just the torso. Weighting
            # the camera with the clearest lower body biases selection toward
            # the view that actually sees the feet, which is the dominant
            # failure mode when the skeleton attaches to floor clutter.
            leg_score = _lower_body_quality(pose)
            scores[cam] = 0.55 * align + 0.20 * pose_score + 0.25 * leg_score
        else:
            scores[cam] = 0.72 * align + 0.28 * pose_score

    if not scores:
        return previous_camera
    best = max(scores, key=scores.get)
    if previous_camera in scores:
        if scores[previous_camera] >= scores[best] * (1.0 - switch_margin):
            return previous_camera
    return best


def crop_frame_to_roi(
    frame: np.ndarray,
    kpts: Any,
    roi: Roi,
    output_size: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Crop frame to ROI and translate keypoints into crop coordinates.

    ``output_size`` is ``(width, height)``. When provided, the crop is resized
    and keypoints are scaled accordingly.
    """
    crop = frame[roi.y1:roi.y2, roi.x1:roi.x2].copy()
    pts = _coerce_kpts(kpts)
    pts[:, 0] -= roi.x1
    pts[:, 1] -= roi.y1
    scale = 1.0
    if output_size is not None and crop.size:
        out_w, out_h = int(output_size[0]), int(output_size[1])
        sx = out_w / max(1, roi.width)
        sy = out_h / max(1, roi.height)
        crop = cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_LINEAR)
        pts[:, 0] *= sx
        pts[:, 1] *= sy
        scale = min(sx, sy)
    return crop, pts, scale


def repair_overlay_keypoints(
    exercise: str,
    raw_kpts: Any,
    raw_scores: Any,
    projected_kpts: Any | None,
    projected_scores: Any | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Prefer stable projected 3D joints where raw 2D pose is weak.

    Push-ups are the important case: single-camera YOLO frequently misplaces
    knees/heels when the athlete is side-on and close to the floor. The ROI
    still follows raw 2D pose, but drawing can use reprojected multi-camera
    joints for the lower body when they are available.
    """
    pts = _coerce_kpts(raw_kpts)
    scores = _coerce_scores(raw_scores)
    if exercise != "push_up" or projected_kpts is None or projected_scores is None:
        return pts, scores

    proj_pts = _coerce_kpts(projected_kpts)
    proj_scores = _coerce_scores(projected_scores)
    # Body-scale reference for the limb-length sanity check. Shoulders are the
    # most reliably tracked joints, so their span anchors the plausible bone
    # length; without it the guard is skipped rather than guessing.
    max_bone = None
    shoulder_span = _shoulder_span_px(pts, scores)
    if shoulder_span is not None:
        max_bone = shoulder_span * _MAX_BONE_TO_SHOULDER_RATIO

    # Parent-first order (hips, then knees, then ankles) so each joint's parent
    # is already resolved when its bone length is checked.
    for idx in _PUSHUP_PROJECTED_REPAIR_JOINTS:
        if not _valid_joint(proj_pts, proj_scores, idx):
            continue
        if max_bone is not None:
            parent = _LOWER_BODY_PARENT.get(idx)
            if parent is not None and np.isfinite(pts[parent]).all():
                bone = float(np.linalg.norm(proj_pts[idx] - pts[parent]))
                if bone > max_bone:
                    # Implausible limb: the projected joint landed far from the
                    # body (stale triangulation / background object). Keep the
                    # raw 2D joint instead of teleporting the skeleton.
                    continue
        pts[idx] = proj_pts[idx]
        scores[idx] = max(scores[idx], proj_scores[idx])
    return pts, scores


def _shoulder_span_px(pts: np.ndarray, scores: np.ndarray) -> float | None:
    """Pixel distance between the shoulders, or None when either is missing."""
    if not (_valid_joint(pts, scores, 5) and _valid_joint(pts, scores, 6)):
        return None
    span = float(np.linalg.norm(pts[5] - pts[6]))
    return span if span > 1e-3 else None


def validate_leg_chain(
    exercise: str,
    kpts: Any,
    scores: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Drop push-up lower-body joints that are untrustworthy.

    A mistracked leg (pinned to floor clutter, a swapped limb) cannot be
    corrected from overlay data, but it can be detected and not drawn. Each
    knee/ankle is checked against the reliable torso: it must clear a score
    bar and form an anatomically plausible chain (bone length vs torso, and
    direction along the body's long axis). Failing joints have their score
    zeroed so the skeleton, angle labels and floor line all skip them.
    """
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    if exercise != "push_up":
        return pts, scr

    # Layer 1: a leg joint below the push-up score bar is dropped outright.
    for idx in _PUSHUP_LEG_JOINTS:
        if 0.0 < scr[idx] < _PUSHUP_LEG_MIN_SCORE:
            scr[idx] = 0.0

    # Layer 2: anatomical chain check against the shoulder->hip torso axis.
    shoulder_mid = _valid_mean(pts, scr, (5, 6))
    hip_mid = _valid_mean(pts, scr, (11, 12))
    if shoulder_mid is None or hip_mid is None:
        return pts, scr  # no reliable torso anchor -- cannot validate
    axis = hip_mid - shoulder_mid
    torso_len = float(np.linalg.norm(axis))
    if torso_len < 1e-3:
        return pts, scr
    axis_unit = axis / torso_len

    for hip_i, knee_i, ankle_i in ((11, 13, 15), (12, 14, 16)):
        hip_pt = pts[hip_i] if _valid_joint(pts, scr, hip_i) else hip_mid
        knee_ok = False
        if _valid_joint(pts, scr, knee_i):
            if _leg_joint_plausible(pts[knee_i], hip_pt, axis_unit, torso_len,
                                    _LEG_BONE_MIN_RATIO, _LEG_BONE_MAX_RATIO):
                knee_ok = True
            else:
                scr[knee_i] = 0.0
        if _valid_joint(pts, scr, ankle_i):
            if knee_ok:
                parent, lo, hi = pts[knee_i], _LEG_BONE_MIN_RATIO, _LEG_BONE_MAX_RATIO
            else:
                # The knee was dropped; validate ankle against hip as a full leg.
                parent, lo, hi = hip_pt, _LEG_FULL_MIN_RATIO, _LEG_FULL_MAX_RATIO
            if not _leg_joint_plausible(pts[ankle_i], parent, axis_unit, torso_len, lo, hi):
                scr[ankle_i] = 0.0
    return pts, scr


def _valid_mean(pts: np.ndarray, scores: np.ndarray, ids: tuple[int, ...]) -> np.ndarray | None:
    valid = [pts[i] for i in ids if _valid_joint(pts, scores, i)]
    if not valid:
        return None
    return np.mean(valid, axis=0)


def _leg_joint_plausible(
    joint_pt: np.ndarray,
    parent_pt: np.ndarray,
    axis_unit: np.ndarray,
    torso_len: float,
    min_ratio: float,
    max_ratio: float,
) -> bool:
    d = np.asarray(joint_pt, dtype=float) - np.asarray(parent_pt, dtype=float)
    bone = float(np.linalg.norm(d))
    if bone < min_ratio * torso_len or bone > max_ratio * torso_len:
        return False
    return float(np.dot(d / bone, axis_unit)) >= _LEG_AXIS_MIN_COS


def _lower_body_quality(pose: tuple[Any, Any]) -> float:
    """Mean confidence of the visible lower-body (knee/ankle) joints."""
    if pose is None:
        return 0.0
    kpts, scores = pose
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    vals = [float(scr[i]) for i in _PUSHUP_LEG_JOINTS
            if np.isfinite(pts[i]).all() and scr[i] >= 0.35]
    if not vals:
        return 0.0
    return float(np.clip(np.mean(vals), 0.0, 1.0))


def compute_floor_anchor_ids(
    exercise: str,
    kpts: Any,
    scores: Any,
    allow_ankles: bool = False,
) -> list[int]:
    """Pick the joint indices the floor guide should ride on for ``exercise``.

    Push-ups default to wrists (9, 10) -- the actual hand-floor contacts that
    a coach sees on the mat. Ankles (15, 16) are advisory and are joined in
    only when ``allow_ankles`` is True *and* each ankle currently passes the
    overlay's own validity check (which folds in ``validate_leg_chain``).
    Squats are unchanged: ankles only, since the wrists swing high overhead.
    """
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    if exercise == "push_up":
        ids = [idx for idx in (9, 10) if _valid_joint(pts, scr, idx)]
        if allow_ankles:
            ids.extend(idx for idx in (15, 16) if _valid_joint(pts, scr, idx))
        return ids
    return [idx for idx in (15, 16) if _valid_joint(pts, scr, idx)]


class PushupFloorAnchor:
    """Temporal validity gate for joining ankles into the push-up floor guide.

    Wrists are the reliable hand-floor contact in a push-up. Ankles slip in
    and out of multi-camera triangulation as the body folds over them in
    oblique views; a one-frame fluke of "both ankles look valid" must not be
    enough to start pulling the floor line up toward the feet. This class
    tracks a streak of consecutive frames in which both ankles pass the
    overlay's own ``_valid_joint`` check and only reports ``allow_ankles`` as
    True once the streak has reached the required length.

    Intended use: one instance per coach session, updated once per rendered
    frame with the post-``validate_leg_chain`` keypoints/scores, then passed
    into ``render_coach_overlay`` so the floor guide can decide whether to
    include ankles this frame.
    """

    def __init__(self, required_streak: int = _PUSHUP_FLOOR_ANKLE_STREAK_FRAMES):
        self.required_streak = max(1, int(required_streak))
        self._streak = 0

    @property
    def streak(self) -> int:
        return self._streak

    @property
    def allow_ankles(self) -> bool:
        return self._streak >= self.required_streak

    def update(self, kpts: Any, scores: Any) -> bool:
        """Advance the streak for this frame and return ``allow_ankles``.

        Both ankles must currently be valid (post-validation) for the streak
        to increment; otherwise it resets to zero so an isolated good frame
        cannot count toward the required length.
        """
        pts = _coerce_kpts(kpts)
        scr = _coerce_scores(scores)
        if _valid_joint(pts, scr, 15) and _valid_joint(pts, scr, 16):
            self._streak += 1
        else:
            self._streak = 0
        return self.allow_ankles


class OverlayKeypointStabilizer:
    """Temporal smoother for the coach-overlay 2D keypoints.

    ``repair_overlay_keypoints`` chooses each joint fresh every frame from
    whichever source (projected 3D vs raw 2D) is valid, with no memory. As a
    push-up athlete's leg coverage flickers across the 2-camera triangulation
    threshold, a joint teleports between the two source positions or drops out
    entirely -- the "legs jump / jitter / vanish" symptom. This applies a
    per-joint EMA (kills jitter, smooths the source switch) and coasts a joint
    through brief dropouts before releasing it on a sustained loss.

    A per-joint jump gate additionally rejects a single-frame teleport (a joint
    that snapped onto the wall / pillow / a different body): such a measurement
    is dropped and the joint coasts, so a bad projected/raw joint cannot yank
    the drawn skeleton across the image.

    Stateful: create one per session and feed it the repaired keypoints every
    frame.
    """

    def __init__(self, alpha: float = 0.5, coast_frames: int = 6,
                 score_threshold: float = 0.35, max_jump_px: float = 160.0) -> None:
        self.alpha = float(max(0.05, min(1.0, alpha)))
        self.coast_frames = max(0, int(coast_frames))
        self.score_threshold = float(score_threshold)
        self.max_jump_px = float(max_jump_px) if max_jump_px and max_jump_px > 0 else None
        self._pos = np.full((17, 2), np.nan, dtype=float)
        self._score = np.zeros((17,), dtype=float)
        self._missing = np.full((17,), self.coast_frames + 1, dtype=int)

    def update(self, kpts: Any, scores: Any) -> tuple[np.ndarray, np.ndarray]:
        """Return EMA-smoothed, dropout-coasted, jump-gated (kpts, scores)."""
        pts = _coerce_kpts(kpts)
        scr = _coerce_scores(scores)
        out_pts = np.full((17, 2), np.nan, dtype=float)
        out_scores = np.zeros((17,), dtype=float)

        for idx in range(17):
            measured = scr[idx] >= self.score_threshold and bool(np.isfinite(pts[idx]).all())
            has_prior = bool(np.isfinite(self._pos[idx]).all())
            if measured and has_prior and self.max_jump_px is not None:
                if float(np.linalg.norm(pts[idx] - self._pos[idx])) > self.max_jump_px:
                    # Teleport: reject this measurement and coast on the last
                    # good position rather than smearing the skeleton toward it.
                    measured = False
            if measured:
                if has_prior:
                    self._pos[idx] = self.alpha * pts[idx] + (1.0 - self.alpha) * self._pos[idx]
                else:
                    self._pos[idx] = pts[idx]  # re-acquire: snap, no smear from stale state
                self._score[idx] = float(scr[idx])
                self._missing[idx] = 0
            else:
                self._missing[idx] += 1
                if self._missing[idx] > self.coast_frames or not np.isfinite(self._pos[idx]).all():
                    self._pos[idx] = np.nan  # sustained loss -> release the joint
                    self._score[idx] = 0.0
                    continue
                # within the coast window -> hold the last smoothed position

            out_pts[idx] = self._pos[idx]
            out_scores[idx] = self._score[idx]
        return out_pts, out_scores


def collect_angle_labels(
    exercise: str,
    metrics: dict[str, Any],
    kpts: Any,
    scores: Any,
) -> list[AngleLabel]:
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    angles = metrics.get("angles_deg") or {}
    labels: list[AngleLabel] = []

    def add(name: str, joint_idx: int, label: str) -> None:
        value = _finite_float(angles.get(name))
        if value is None or not _valid_joint(pts, scr, joint_idx):
            return
        x, y = pts[joint_idx]
        labels.append(AngleLabel(f"{label} {value:.0f}", (int(x) + 10, int(y) - 10)))

    if exercise == "push_up":
        add("left_elbow", 7, "L elbow")
        add("right_elbow", 8, "R elbow")
        trunk_vals = [
            _finite_float(angles.get("left_trunk_to_leg")),
            _finite_float(angles.get("right_trunk_to_leg")),
        ]
        trunk_present = [v for v in trunk_vals if v is not None]
        hips = [idx for idx in (11, 12) if _valid_joint(pts, scr, idx)]
        if trunk_present and hips:
            anchor = np.mean([pts[idx] for idx in hips], axis=0)
            labels.append(AngleLabel(f"trunk {np.mean(trunk_present):.0f}", (int(anchor[0]) + 12, int(anchor[1]) + 4)))
    else:
        add("left_knee", 13, "L knee")
        add("right_knee", 14, "R knee")
    return labels


def render_coach_overlay(
    frame: np.ndarray,
    exercise: str,
    state: RepState,
    metrics: dict[str, Any],
    kpts: Any,
    scores: Any,
    projected_floor: list[tuple[float, float]] | None = None,
    pushup_floor_anchor: PushupFloorAnchor | None = None,
) -> np.ndarray:
    """Draw live coach graphics over a camera frame.

    ``pushup_floor_anchor`` is an optional stateful gate (one instance per
    session) that lets the push-up floor guide include the ankles only after
    they have been continuously valid for several consecutive frames. When
    omitted, the push-up floor stays anchored on the wrists -- the reliable
    hand-floor contact.
    """
    canvas = frame.copy()
    # Drop push-up leg joints that are untrustworthy so the skeleton, angle
    # labels and floor line all skip them rather than rendering garbage.
    pts, scr = validate_leg_chain(exercise, kpts, scores)
    phase_color = _PHASE_COLOR.get(state.phase, _MUTE)
    valid_count = sum(1 for idx in _JOINTS_FOR_VALIDITY if _valid_joint(pts, scr, idx))

    _draw_header(canvas, exercise, state, phase_color)
    if valid_count < 5 or not state.tracking_ok:
        _draw_waiting(canvas, "STEP INTO COACH ZONE" if valid_count < 5 else "LOW TRACKING")
        return canvas
    if not state.acquired:
        # athlete is visible but not yet verified in the exercise posture
        _draw_waiting(canvas, "WAITING FOR PUSH-UP POSITION")
        return canvas

    allow_ankles = False
    if exercise == "push_up" and pushup_floor_anchor is not None:
        allow_ankles = pushup_floor_anchor.update(pts, scr)
    _draw_floor_guides(canvas, exercise, pts, scr, projected_floor, allow_ankles)
    _draw_skeleton(canvas, pts, scr, phase_color)
    for label in collect_angle_labels(exercise, metrics, pts, scr):
        _draw_label(canvas, label)
    _draw_depth_meter(canvas, state.depth_pct, phase_color)
    _draw_cue(canvas, state.cue)
    return canvas


def _draw_header(canvas: np.ndarray, exercise: str, state: RepState, color) -> None:
    h, w = canvas.shape[:2]
    cv2.rectangle(canvas, (0, 0), (w, 86), _DARK, -1)
    title = "LIVE COACH"
    cv2.putText(canvas, title, (22, 34), _FONT, 0.9, _TEXT, 2, cv2.LINE_AA)
    cv2.putText(canvas, exercise.replace("_", " ").upper(), (22, 66), _FONT, 0.62, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, f"REPS {state.rep_count}", (w - 210, 34), _FONT, 0.78, _TEXT, 2, cv2.LINE_AA)
    cv2.putText(canvas, state.phase, (w - 210, 66), _FONT, 0.58, color, 2, cv2.LINE_AA)
    cv2.line(canvas, (22, 80), (min(w - 22, 270), 80), color, 4, cv2.LINE_AA)


def _draw_waiting(canvas: np.ndarray, message: str) -> None:
    h, w = canvas.shape[:2]
    overlay = canvas.copy()
    cv2.rectangle(overlay, (0, 86), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.42, canvas, 0.58, 0, canvas)
    (tw, _), _ = cv2.getTextSize(message, _FONT, 0.95, 2)
    cv2.putText(canvas, message, ((w - tw) // 2, h // 2), _FONT, 0.95, _YELLOW, 2, cv2.LINE_AA)


def _draw_floor_guides(
    canvas: np.ndarray,
    exercise: str,
    pts: np.ndarray,
    scores: np.ndarray,
    projected_floor: list[tuple[float, float]] | None,
    allow_ankles: bool = False,
) -> None:
    if projected_floor and len(projected_floor) >= 2:
        poly = np.asarray(projected_floor, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(canvas, [poly], isClosed=True, color=(70, 90, 96), thickness=2, lineType=cv2.LINE_AA)

    ground_ids = compute_floor_anchor_ids(exercise, pts, scores, allow_ankles=allow_ankles)
    if not ground_ids:
        return
    y = int(np.median([pts[idx][1] for idx in ground_ids]))
    x_values = [pts[idx][0] for idx in ground_ids]
    x1 = int(max(0, min(x_values) - 120))
    x2 = int(min(canvas.shape[1] - 1, max(x_values) + 120))
    cv2.line(canvas, (x1, y), (x2, y), (76, 210, 228), 3, cv2.LINE_AA)
    cv2.line(canvas, (x1, y + 12), (x2, y + 12), (44, 94, 104), 1, cv2.LINE_AA)


def _draw_skeleton(canvas: np.ndarray, pts: np.ndarray, scores: np.ndarray, color) -> None:
    for a, b in _SKELETON_EDGES:
        if _valid_joint(pts, scores, a) and _valid_joint(pts, scores, b):
            cv2.line(canvas, _pt(pts[a]), _pt(pts[b]), color, 5, cv2.LINE_AA)
            cv2.line(canvas, _pt(pts[a]), _pt(pts[b]), (16, 18, 20), 1, cv2.LINE_AA)
    for idx in _JOINTS_FOR_VALIDITY:
        if _valid_joint(pts, scores, idx):
            cv2.circle(canvas, _pt(pts[idx]), 7, _DARK, -1, cv2.LINE_AA)
            cv2.circle(canvas, _pt(pts[idx]), 7, _TEXT, 2, cv2.LINE_AA)
    if _valid_joint(pts, scores, 0):
        cv2.circle(canvas, _pt(pts[0]), 13, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, _pt(pts[0]), 13, _TEXT, 2, cv2.LINE_AA)


def _draw_label(canvas: np.ndarray, label: AngleLabel) -> None:
    x, y = label.anchor
    text = label.text
    (tw, th), _ = cv2.getTextSize(text, _FONT, 0.48, 1)
    x = max(4, min(canvas.shape[1] - tw - 16, x))
    y = max(100, min(canvas.shape[0] - 8, y))
    cv2.rectangle(canvas, (x - 6, y - th - 8), (x + tw + 8, y + 5), _PANEL, -1)
    cv2.putText(canvas, text, (x, y), _FONT, 0.48, label.color, 1, cv2.LINE_AA)


def _draw_depth_meter(canvas: np.ndarray, depth_pct: float, color) -> None:
    h, w = canvas.shape[:2]
    x = w - 38
    y1 = 112
    y2 = h - 34
    cv2.rectangle(canvas, (x, y1), (x + 16, y2), _DARK, -1)
    frac = max(0.0, min(1.0, float(depth_pct) / 100.0))
    fill = int((y2 - y1) * frac)
    if fill > 0:
        cv2.rectangle(canvas, (x, y2 - fill), (x + 16, y2), color, -1)
    cv2.putText(canvas, "DEPTH", (w - 88, y2 + 20), _FONT, 0.38, _MUTE, 1, cv2.LINE_AA)


def _draw_cue(canvas: np.ndarray, cue: str) -> None:
    if not cue:
        return
    h, w = canvas.shape[:2]
    y = h - 70
    cv2.rectangle(canvas, (18, y), (min(w - 52, 720), y + 44), _PANEL, -1)
    cv2.rectangle(canvas, (18, y), (25, y + 44), _YELLOW, -1)
    cv2.putText(canvas, cue[:54], (36, y + 29), _FONT, 0.58, _TEXT, 1, cv2.LINE_AA)


def _pose_center(kpts: Any, scores: Any) -> np.ndarray | None:
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    valid = np.isfinite(pts).all(axis=1) & (scr >= 0.35)
    if int(np.count_nonzero(valid)) < 3:
        return None
    return np.median(pts[valid], axis=0)


def _pose_quality(pose: tuple[Any, Any]) -> float:
    if pose is None:
        return 0.0
    kpts, scores = pose
    pts = _coerce_kpts(kpts)
    scr = _coerce_scores(scores)
    valid = np.isfinite(pts).all(axis=1) & (scr >= 0.35)
    if int(np.count_nonzero(valid)) < 5:
        return 0.0
    return float(np.clip(np.mean(scr[valid]), 0.0, 1.0))


def _body_axes(joints_3d: list[Any] | np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    pts = _coerce_joints3d(joints_3d)
    valid = np.isfinite(pts).all(axis=1)
    if int(np.count_nonzero(valid)) < 2:
        return None, None, None
    center_ids = [idx for idx in (5, 6, 11, 12) if valid[idx]]
    center = np.mean(pts[center_ids] if center_ids else pts[valid], axis=0)
    lateral = None
    for left, right in ((11, 12), (5, 6)):
        if valid[left] and valid[right]:
            d = pts[right, :2] - pts[left, :2]
            norm = float(np.linalg.norm(d))
            if norm > 1e-6:
                lateral = d / norm
                break
    if lateral is None:
        return center, None, None
    forward = np.array([-lateral[1], lateral[0]], dtype=float)
    return center, lateral, forward


def _coerce_joints3d(joints: list[Any] | np.ndarray) -> np.ndarray:
    out = np.full((17, 3), np.nan, dtype=float)
    if joints is None:
        return out
    for idx, value in enumerate(list(joints)[:17]):
        if value is None:
            continue
        try:
            arr = np.asarray(value, dtype=float).reshape(-1)[:3]
        except (TypeError, ValueError):
            continue
        if arr.shape[0] == 3 and np.isfinite(arr).all():
            out[idx] = arr
    return out


def _coerce_kpts(kpts: Any) -> np.ndarray:
    out = np.full((17, 2), np.nan, dtype=float)
    try:
        arr = np.asarray(kpts, dtype=float)
    except (TypeError, ValueError):
        return out
    if arr.ndim < 2:
        return out
    rows = min(17, arr.shape[0])
    cols = min(2, arr.shape[1])
    out[:rows, :cols] = arr[:rows, :cols]
    return out


def _coerce_scores(scores: Any) -> np.ndarray:
    out = np.zeros((17,), dtype=float)
    try:
        arr = np.asarray(scores, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return out
    rows = min(17, arr.shape[0])
    out[:rows] = np.nan_to_num(arr[:rows], nan=0.0)
    return out


def _as_vec3(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value, dtype=float).reshape(-1)[:3]
    except (TypeError, ValueError):
        return None
    if arr.shape[0] < 3 or not np.isfinite(arr).all():
        return None
    return arr


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _valid_joint(pts: np.ndarray, scores: np.ndarray, idx: int, threshold: float = 0.35) -> bool:
    return bool(idx < len(pts) and idx < len(scores) and scores[idx] >= threshold and np.isfinite(pts[idx]).all())


def _pt(value: np.ndarray) -> tuple[int, int]:
    return int(round(float(value[0]))), int(round(float(value[1])))
