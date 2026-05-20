"""OpenCV dashboard renderer for the live push-up / squat trainer.

LinkedIn-style 'AI FITNESS ANALYTICS' layout: a large skeleton stage on the
left with a vertical depth gauge, and an analytics column on the right with
status, rep count, an angle dial, movement phase, tracking quality, a
coaching ribbon, and a phase timeline. Pure rendering: state in, BGR out.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from .rep_state import RepState

# --- palette (BGR) ---
_BG = (26, 26, 30)
_STAGE = (18, 18, 22)
_PANEL = (42, 42, 48)
_PANEL_HI = (54, 54, 62)
_TEXT = (240, 240, 240)
_MUTE = (140, 140, 148)
_GREEN = (96, 208, 116)
_BLUE = (224, 168, 72)
_AMBER = (64, 184, 240)
_RED = (84, 92, 232)
_YELLOW = (90, 220, 232)

_PHASE_COLOR = {
    "STANDING": _GREEN, "TOP": _GREEN,
    "DESCENDING": _AMBER, "LOWERING": _AMBER,
    "BOTTOM": _RED,
    "ASCENDING": _BLUE, "PUSHING UP": _BLUE,
    "GET IN POSITION": _AMBER,
}

_PHASE_DESC = {
    "STANDING": "Tall, ready position",
    "DESCENDING": "Lowering hips under control",
    "BOTTOM": "Hips at depth",
    "ASCENDING": "Driving back up",
    "TOP": "Arms fully extended",
    "LOWERING": "Chest toward the floor",
    "PUSHING UP": "Driving the body up",
    "GET IN POSITION": "Lower into a plank to begin",
}

# Ordered phase sequence per exercise, for the timeline strip.
_PHASE_ORDER = {
    "squat": ["STANDING", "DESCENDING", "BOTTOM", "ASCENDING"],
    "push_up": ["TOP", "LOWERING", "BOTTOM", "PUSHING UP"],
}

# COCO-17 body edges (limbs + torso box); the head is drawn as one circle.
_SKELETON_EDGES = [
    (5, 7), (7, 9), (6, 8), (8, 10),          # arms
    (11, 13), (13, 15), (12, 14), (14, 16),   # legs
    (5, 6), (11, 12), (5, 11), (6, 12),       # torso
]
_HEAD_JOINTS = (0, 1, 2, 3, 4)
_BODY_JOINTS = (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16)
# Fixed world span (mm) mapped across the skeleton panel -> constant scale,
# so the figure never auto-zooms as the athlete's bounding box changes.
_VIEW_SPAN_MM = 2400.0

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def render_dashboard(
    exercise: str,
    state: RepState,
    joints: list[Any],
    view: "SkeletonView | None" = None,
    width: int = 1180,
    height: int = 680,
) -> np.ndarray:
    """Render the trainer dashboard as a BGR uint8 image.

    ``view`` is a persistent SkeletonView that stabilises the skeleton's
    scale and orientation; pass the same instance on every frame. When
    omitted a throwaway one is used (fine for a single still render).
    """
    canvas = np.full((height, width, 3), _BG, dtype=np.uint8)
    if view is None:
        view = SkeletonView()
    phases = _PHASE_ORDER.get(exercise, ["UP", "DESCENDING", "BOTTOM", "ASCENDING"])
    phase_color = _PHASE_COLOR.get(state.phase, _MUTE)

    # ===== left: skeleton stage with vertical depth gauge =====
    stage_x, stage_y, stage_w, stage_h = 20, 20, 620, height - 40
    _round_rect(canvas, stage_x, stage_y, stage_w, stage_h, 14, _STAGE)
    # squats read best face-on (depth + knee tracking); push-ups side-on.
    plane = "front" if exercise == "squat" else "side"
    _chip(canvas, stage_x + 16, stage_y + 16,
          f"SKELETON VIEW - {plane.upper()}", _MUTE)
    gauge_w = 26
    _draw_skeleton(canvas, stage_x + 16, stage_y + 52,
                   stage_w - 48 - gauge_w, stage_h - 96, joints, view, plane,
                   phase_color)
    _depth_gauge(canvas, stage_x + stage_w - gauge_w - 16, stage_y + 52,
                 gauge_w, stage_h - 96, state.depth_pct, phase_color)

    # ===== right: analytics column =====
    col_x = stage_x + stage_w + 20
    col_w = width - col_x - 20

    cv2.putText(canvas, "AI FITNESS ANALYTICS", (col_x, stage_y + 30),
                _FONT, 0.9, _TEXT, 2, cv2.LINE_AA)
    cv2.line(canvas, (col_x, stage_y + 42), (col_x + 200, stage_y + 42),
             _GREEN, 3, cv2.LINE_AA)
    _chip(canvas, col_x + col_w - 150, stage_y + 12,
          exercise.replace("_", " ").upper(), _YELLOW, filled=True)

    y = stage_y + 60

    # status panel
    status_color = _GREEN if state.status == "UP" else _RED
    _round_rect(canvas, col_x, y, col_w, 62, 10, _PANEL)
    cv2.rectangle(canvas, (col_x, y), (col_x + 6, y + 62), status_color, -1)
    cv2.putText(canvas, "CURRENT STATUS", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, state.status, (col_x + 20, y + 50),
                _FONT, 0.92, status_color, 2, cv2.LINE_AA)
    y += 76

    # count tile + angle dial tile
    tile_w = (col_w - 14) // 2
    _round_rect(canvas, col_x, y, tile_w, 128, 10, _PANEL)
    cv2.putText(canvas, "COUNT", (col_x + 20, y + 26), _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, str(state.rep_count), (col_x + 18, y + 94),
                _FONT, 2.0, _TEXT, 4, cv2.LINE_AA)
    cv2.putText(canvas, f"incomplete  {state.incomplete_count}", (col_x + 20, y + 116),
                _FONT, 0.44, _MUTE, 1, cv2.LINE_AA)

    dial_x = col_x + tile_w + 14
    _round_rect(canvas, dial_x, y, tile_w, 128, 10, _PANEL)
    cv2.putText(canvas, "ANGLE", (dial_x + 20, y + 26), _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    _angle_dial(canvas, dial_x + tile_w // 2, y + 88, 42, state.current_angle, phase_color)
    y += 142

    # movement phase panel
    _round_rect(canvas, col_x, y, col_w, 74, 10, _PANEL)
    cv2.rectangle(canvas, (col_x, y), (col_x + 6, y + 74), phase_color, -1)
    cv2.putText(canvas, "MOVEMENT PHASE", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, state.phase, (col_x + 20, y + 50),
                _FONT, 0.8, phase_color, 2, cv2.LINE_AA)
    cv2.putText(canvas, _PHASE_DESC.get(state.phase, ""), (col_x + 20, y + 68),
                _FONT, 0.44, _MUTE, 1, cv2.LINE_AA)
    y += 88

    # tracking quality bar
    track_color = _GREEN if state.tracking_ok else _RED
    _round_rect(canvas, col_x, y, col_w, 52, 10, _PANEL)
    cv2.putText(canvas, "TRACKING QUALITY", (col_x + 20, y + 22),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    _bar(canvas, col_x + 20, y + 32, col_w - 40, 12, state.tracking_quality, track_color)
    y += 66

    # coaching ribbon
    _round_rect(canvas, col_x, y, col_w, 68, 10, _PANEL_HI)
    cv2.rectangle(canvas, (col_x, y), (col_x + 6, y + 68), _YELLOW, -1)
    cv2.putText(canvas, "COACHING", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    cv2.putText(canvas, _truncate(state.cue, 46), (col_x + 20, y + 50),
                _FONT, 0.58, _TEXT, 1, cv2.LINE_AA)
    y += 82

    # phase timeline strip
    _round_rect(canvas, col_x, y, col_w, 110, 10, _PANEL)
    cv2.putText(canvas, "PHASE TIMELINE", (col_x + 20, y + 24),
                _FONT, 0.46, _MUTE, 1, cv2.LINE_AA)
    _phase_timeline(canvas, col_x + 20, y + 40, col_w - 40, phases, state.phase)

    return canvas


def _round_rect(canvas: np.ndarray, x: int, y: int, w: int, h: int, r: int, color) -> None:
    r = max(0, min(r, w // 2, h // 2))
    if w <= 0 or h <= 0:
        return
    cv2.rectangle(canvas, (x + r, y), (x + w - r, y + h), color, -1)
    cv2.rectangle(canvas, (x, y + r), (x + w, y + h - r), color, -1)
    for cx, cy in ((x + r, y + r), (x + w - r, y + r),
                   (x + r, y + h - r), (x + w - r, y + h - r)):
        cv2.circle(canvas, (cx, cy), r, color, -1, cv2.LINE_AA)


def _chip(canvas: np.ndarray, x: int, y: int, text: str, color, filled: bool = False) -> None:
    (tw, th), _ = cv2.getTextSize(text, _FONT, 0.42, 1)
    pad = 8
    if filled:
        _round_rect(canvas, x, y, tw + 2 * pad, th + 2 * pad, 6, color)
        cv2.putText(canvas, text, (x + pad, y + th + pad - 1),
                    _FONT, 0.42, _BG, 1, cv2.LINE_AA)
    else:
        cv2.putText(canvas, text, (x, y + th + pad - 1),
                    _FONT, 0.42, color, 1, cv2.LINE_AA)


def _bar(canvas: np.ndarray, x: int, y: int, w: int, h: int, fraction: float, color) -> None:
    frac = max(0.0, min(1.0, float(fraction)))
    _round_rect(canvas, x, y, w, h, h // 2, _BG)
    if frac > 0:
        _round_rect(canvas, x, y, max(h, int(w * frac)), h, h // 2, color)
    cv2.putText(canvas, f"{frac * 100:.0f}%", (x + w - 42, y - 4),
                _FONT, 0.42, _TEXT, 1, cv2.LINE_AA)


def _depth_gauge(canvas: np.ndarray, x: int, y: int, w: int, h: int,
                 depth_pct: float, color) -> None:
    frac = max(0.0, min(1.0, depth_pct / 100.0))
    _round_rect(canvas, x, y, w, h, w // 2, _BG)
    fill_h = int(h * frac)
    if fill_h > 0:
        _round_rect(canvas, x, y + h - fill_h, w, fill_h, w // 2, color)
    cv2.putText(canvas, "DEPTH", (x - 4, y + h + 18), _FONT, 0.4, _MUTE, 1, cv2.LINE_AA)


def _angle_dial(canvas: np.ndarray, cx: int, cy: int, radius: int,
                angle: float | None, color) -> None:
    # Top half-ring gauge: joint flexion 0..180 deg.
    cv2.ellipse(canvas, (cx, cy), (radius, radius), 0, 180, 360, _BG, 8, cv2.LINE_AA)
    if angle is not None:
        frac = max(0.0, min(1.0, float(angle) / 180.0))
        cv2.ellipse(canvas, (cx, cy), (radius, radius), 0,
                    180, 180 + 180 * frac, color, 8, cv2.LINE_AA)
    text = "--" if angle is None else f"{angle:.0f}"
    (tw, _), _ = cv2.getTextSize(text, _FONT, 0.9, 2)
    cv2.putText(canvas, text, (cx - tw // 2, cy + 4), _FONT, 0.9, _TEXT, 2, cv2.LINE_AA)
    cv2.putText(canvas, "deg", (cx - 13, cy + 24), _FONT, 0.4, _MUTE, 1, cv2.LINE_AA)


def _phase_timeline(canvas: np.ndarray, x: int, y: int, w: int,
                    phases: list[str], current: str) -> None:
    n = max(1, len(phases))
    gap = 8
    seg = (w - gap * (n - 1)) // n
    for i, name in enumerate(phases):
        sx = x + i * (seg + gap)
        color = _PHASE_COLOR.get(name, _MUTE)
        active = name == current
        _round_rect(canvas, sx, y, seg, 30, 6, color if active else _PANEL_HI)
        if active:
            cv2.rectangle(canvas, (sx, y), (sx + seg, y + 30), _TEXT, 1, cv2.LINE_AA)
        label = name if len(name) <= 9 else name[:8] + "."
        (tw, _), _ = cv2.getTextSize(label, _FONT, 0.36, 1)
        txt_color = _BG if active else _MUTE
        cv2.putText(canvas, label, (sx + max(4, (seg - tw) // 2), y + 20),
                    _FONT, 0.36, txt_color, 1, cv2.LINE_AA)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "."


def _draw_skeleton(canvas: np.ndarray, x0: int, y0: int, w: int, h: int,
                   joints: list[Any], view: "SkeletonView", plane: str,
                   color) -> None:
    proj = view.project(joints, plane)
    if proj is None:
        msg = "WAITING FOR POSE"
        (tw, _), _ = cv2.getTextSize(msg, _FONT, 0.7, 2)
        cv2.putText(canvas, msg, (x0 + (w - tw) // 2, y0 + h // 2),
                    _FONT, 0.7, _MUTE, 2, cv2.LINE_AA)
        return

    pts = proj["points"]
    center_u, center_v = proj["center"]
    scale = min(w, h) / _VIEW_SPAN_MM   # fixed: figure never auto-zooms
    cx = x0 + w // 2
    cy = y0 + h // 2

    def to_px(uv):
        u, v = uv
        return (int(cx + (u - center_u) * scale), int(cy - (v - center_v) * scale))

    screen = [to_px(p) if p is not None else None for p in pts]

    # ground reference line at the lowest visible foot
    feet = [pts[i] for i in (15, 16) if pts[i] is not None]
    if feet:
        floor_y = int(cy - (min(p[1] for p in feet) - center_v) * scale)
        if y0 <= floor_y <= y0 + h:
            cv2.line(canvas, (x0 + 14, floor_y), (x0 + w - 14, floor_y),
                     _PANEL_HI, 2, cv2.LINE_AA)

    # limbs + torso
    for a, b in _SKELETON_EDGES:
        if screen[a] is not None and screen[b] is not None:
            cv2.line(canvas, screen[a], screen[b], color, 5, cv2.LINE_AA)

    # body joint markers
    for i in _BODY_JOINTS:
        s = screen[i]
        if s is not None:
            cv2.circle(canvas, s, 6, _BG, -1, cv2.LINE_AA)
            cv2.circle(canvas, s, 6, _TEXT, 2, cv2.LINE_AA)

    # head: one circle + neck line, instead of scattered eye/ear dots
    head = [pts[i] for i in _HEAD_JOINTS if pts[i] is not None]
    shoulders = [pts[i] for i in (5, 6) if pts[i] is not None]
    if head:
        head_uv = (sum(p[0] for p in head) / len(head),
                   sum(p[1] for p in head) / len(head))
        head_px = to_px(head_uv)
        head_r = max(9, int(115.0 * scale))
        if shoulders:
            neck_uv = (sum(p[0] for p in shoulders) / len(shoulders),
                       sum(p[1] for p in shoulders) / len(shoulders))
            cv2.line(canvas, to_px(neck_uv), head_px, color, 5, cv2.LINE_AA)
        cv2.circle(canvas, head_px, head_r, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, head_px, head_r, _TEXT, 2, cv2.LINE_AA)


class SkeletonView:
    """Stateful 3D->2D projector for the skeleton panel.

    Projects COCO-17 world joints onto a body-relative vertical plane and
    smooths the orientation and centering across frames, so the figure keeps
    a constant size and does not flip or swing with the arena axes as the
    athlete moves. ``plane="front"`` views the athlete face-on (limbs spread,
    knee tracking visible); ``plane="side"`` views them in profile. Create
    one per session and reuse it.
    """

    _CENTER_ALPHA = 0.18
    _FORWARD_ALPHA = 0.10

    def __init__(self) -> None:
        self._center: np.ndarray | None = None
        self._forward: np.ndarray | None = None

    def project(self, joints: list[Any], plane: str = "side") -> dict[str, Any] | None:
        """Return {'points': [(u, v) | None], 'center': (u, v)} or None.

        ``u`` is the horizontal screen axis (the athlete's lateral axis for
        ``plane="front"``, their forward axis for ``plane="side"``); ``v`` is
        world height.
        """
        pts: list[np.ndarray | None] = []
        for j in joints:
            if j is None:
                pts.append(None)
                continue
            try:
                p = np.asarray(j, dtype=float).reshape(-1)[:3]
            except (TypeError, ValueError):
                pts.append(None)
                continue
            if p.shape[0] < 3 or not np.isfinite(p).all():
                pts.append(None)
            else:
                pts.append(p)

        valid = [p for p in pts if p is not None]
        if len(valid) < 2:
            return None

        centroid = np.mean(valid, axis=0)
        if self._center is None:
            self._center = centroid
        else:
            self._center = ((1.0 - self._CENTER_ALPHA) * self._center
                            + self._CENTER_ALPHA * centroid)

        forward = self._update_forward(pts)
        if plane == "front":
            axis = np.array([forward[1], -forward[0]])  # lateral = forward rot -90
        else:
            axis = forward
        center_u = float(self._center[:2] @ axis)
        center_v = float(self._center[2])

        flat: list[tuple[float, float] | None] = []
        for p in pts:
            if p is None:
                flat.append(None)
            else:
                flat.append((float(p[:2] @ axis), float(p[2])))
        return {"points": flat, "center": (center_u, center_v)}

    def _update_forward(self, pts: list[np.ndarray | None]) -> np.ndarray:
        lateral = None
        for left, right in ((11, 12), (5, 6)):   # hips first, shoulders fallback
            a, b = pts[left], pts[right]
            if a is not None and b is not None:
                d = b[:2] - a[:2]
                norm = float(np.hypot(d[0], d[1]))
                if norm > 1e-6:
                    lateral = d / norm
                    break
        if lateral is None:
            return self._forward if self._forward is not None else np.array([1.0, 0.0])

        # forward = lateral rotated 90 deg in the ground plane -> sagittal view
        fwd = np.array([-lateral[1], lateral[0]])
        if self._forward is not None and float(fwd @ self._forward) < 0.0:
            fwd = -fwd   # keep the facing direction continuous between frames
        if self._forward is None:
            self._forward = fwd
        else:
            blended = ((1.0 - self._FORWARD_ALPHA) * self._forward
                       + self._FORWARD_ALPHA * fwd)
            norm = float(np.hypot(blended[0], blended[1]))
            if norm > 1e-6:
                self._forward = blended / norm
        return self._forward
