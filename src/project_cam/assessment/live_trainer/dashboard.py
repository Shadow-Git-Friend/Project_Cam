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
}

_PHASE_DESC = {
    "STANDING": "Tall, ready position",
    "DESCENDING": "Lowering hips under control",
    "BOTTOM": "Hips at depth",
    "ASCENDING": "Driving back up",
    "TOP": "Arms fully extended",
    "LOWERING": "Chest toward the floor",
    "PUSHING UP": "Driving the body up",
}

# Ordered phase sequence per exercise, for the timeline strip.
_PHASE_ORDER = {
    "squat": ["STANDING", "DESCENDING", "BOTTOM", "ASCENDING"],
    "push_up": ["TOP", "LOWERING", "BOTTOM", "PUSHING UP"],
}

# COCO-17 skeleton edges (limbs + torso + head links).
_SKELETON_EDGES = [
    (5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12),
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6),
]

_FONT = cv2.FONT_HERSHEY_SIMPLEX


def render_dashboard(
    exercise: str,
    state: RepState,
    joints: list[Any],
    width: int = 1180,
    height: int = 680,
) -> np.ndarray:
    """Render the trainer dashboard as a BGR uint8 image."""
    canvas = np.full((height, width, 3), _BG, dtype=np.uint8)
    phases = _PHASE_ORDER.get(exercise, ["UP", "DESCENDING", "BOTTOM", "ASCENDING"])
    phase_color = _PHASE_COLOR.get(state.phase, _MUTE)

    # ===== left: skeleton stage with vertical depth gauge =====
    stage_x, stage_y, stage_w, stage_h = 20, 20, 620, height - 40
    _round_rect(canvas, stage_x, stage_y, stage_w, stage_h, 14, _STAGE)
    _chip(canvas, stage_x + 16, stage_y + 16, "SKELETON VIEW", _MUTE)
    gauge_w = 26
    _draw_skeleton(canvas, stage_x + 16, stage_y + 52,
                   stage_w - 48 - gauge_w, stage_h - 96, joints, phase_color)
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
                   joints: list[Any], color) -> None:
    # Project 3D joints to a 2D side view: horizontal = x_mm, vertical = z_mm.
    pts: list[tuple[float, float] | None] = []
    for j in joints:
        if j is None or len(j) < 3:
            pts.append(None)
        else:
            pts.append((float(j[0]), float(j[2])))
    valid = [p for p in pts if p is not None]
    if len(valid) < 2:
        msg = "WAITING FOR POSE"
        (tw, _), _ = cv2.getTextSize(msg, _FONT, 0.7, 2)
        cv2.putText(canvas, msg, (x0 + (w - tw) // 2, y0 + h // 2),
                    _FONT, 0.7, _MUTE, 2, cv2.LINE_AA)
        return

    xs = [p[0] for p in valid]
    zs = [p[1] for p in valid]
    span_x = max(1.0, max(xs) - min(xs))
    span_z = max(1.0, max(zs) - min(zs))
    pad = 40
    scale = min((w - 2 * pad) / span_x, (h - 2 * pad) / span_z)
    off_x = x0 + (w - span_x * scale) / 2.0
    off_y = y0 + (h - span_z * scale) / 2.0

    def to_px(p):
        px = int(off_x + (p[0] - min(xs)) * scale)
        py = int(off_y + (max(zs) - p[1]) * scale)  # flip: z up -> y down
        return px, py

    screen = [to_px(p) if p is not None else None for p in pts]
    for a, b in _SKELETON_EDGES:
        if screen[a] is not None and screen[b] is not None:
            cv2.line(canvas, screen[a], screen[b], color, 3, cv2.LINE_AA)
    for s in screen:
        if s is not None:
            cv2.circle(canvas, s, 6, _BG, -1, cv2.LINE_AA)
            cv2.circle(canvas, s, 6, _TEXT, 2, cv2.LINE_AA)
