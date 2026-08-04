"""Desktop placement for the live cv2 windows (display-only).

Nothing here touches triangulation, pose state, UDP or scoring. It decides
where an OpenCV window sits on the desktop and how large it is, so the training
stack can open the athlete-facing drill board and the 3D arena view side by
side instead of making the operator drag both into place every session.

Two details matter and are easy to get wrong:

* **Use the window manager's work area, not the screen size.** The GNOME dock
  and top panel reserve edges (measured on this rig: ``_NET_WORKAREA`` is
  ``70, 27, 1850, 1053`` on a 1920x1080 screen). A pane computed from the raw
  screen lands under the dock, the window manager shifts it right, and the two
  "halves" overlap.
* **Keep the content aspect ratio.** ``pane_rect`` fits the caller's render
  aspect inside its share of the work area, so the image is shown without
  letterbox bars and without resampling seams. OpenCV's Qt backend letterboxes
  on its own with a light-grey fill, which looks broken next to a dark board.
"""

from __future__ import annotations

import os
import re
import subprocess

#: Fallback when neither the environment nor X11 can be queried.
DEFAULT_WORKAREA = (0, 0, 1920, 1080)

#: ``x,y,w,h`` override, for headless tests and multi-monitor rigs where the
#: work area is not the primary display.
WORKAREA_ENV = "PROJECT_CAM_WORKAREA"

#: Accepted ``--window-pane`` values. ``none`` leaves placement to the WM.
PANES = ("none", "left", "right", "full")


def parse_workarea(text):
    """``(x, y, w, h)`` from ``"x,y,w,h"`` (commas and/or spaces), else None."""
    if not text:
        return None
    parts = [p for p in re.split(r"[,\s]+", str(text).strip()) if p]
    if len(parts) < 4:
        return None
    try:
        x, y, w, h = (int(float(p)) for p in parts[:4])
    except ValueError:
        return None
    if w <= 0 or h <= 0:
        return None
    return (x, y, w, h)


def _run(cmd, timeout=2.0):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout if out.returncode == 0 else ""


def _workarea_from_xprop():
    """First viewport of ``_NET_WORKAREA`` — the desktop minus docks/panels."""
    out = _run(["xprop", "-root", "_NET_WORKAREA"])
    if "=" not in out:
        return None
    return parse_workarea(out.split("=", 1)[1])


def _workarea_from_xrandr():
    """Primary display geometry — no dock/panel exclusion, so second choice."""
    out = _run(["xrandr", "--current"])
    for line in out.splitlines():
        if " connected primary " not in line:
            continue
        m = re.search(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line)
        if m:
            w, h, x, y = (int(m.group(i)) for i in (1, 2, 3, 4))
            return (x, y, w, h)
    return None


def screen_workarea(default=DEFAULT_WORKAREA):
    """Usable desktop rect: env override -> ``_NET_WORKAREA`` -> xrandr -> default."""
    for source in (
        lambda: parse_workarea(os.environ.get(WORKAREA_ENV)),
        _workarea_from_xprop,
        _workarea_from_xrandr,
    ):
        try:
            rect = source()
        except Exception:  # pragma: no cover - defensive: placement is cosmetic
            rect = None
        if rect:
            return rect
    return tuple(default)


def pane_rect(pane, aspect=16.0 / 9.0, workarea=None, panes=2, margin=0):
    """Content rect ``(x, y, w, h)`` for one pane of a horizontal split.

    ``pane`` is ``left`` / ``right`` (halves), ``full`` (whole work area) or
    ``none`` -> ``None``, meaning "leave the window where the WM puts it".
    The returned rect keeps ``aspect`` and is centred inside the pane's share,
    so the caller's frame is displayed 1:1 with no letterboxing.
    """
    if pane in (None, "", "none"):
        return None
    if pane not in PANES:
        raise ValueError(f"unknown pane {pane!r}; expected one of {PANES}")
    if not aspect or aspect <= 0:
        aspect = 16.0 / 9.0
    x0, y0, area_w, area_h = workarea or screen_workarea()
    panes = max(1, int(panes))
    index = {"left": 0, "right": panes - 1, "full": 0}[pane]
    share_w = area_w if pane == "full" else area_w // panes
    avail_w = max(1, share_w - 2 * margin)
    avail_h = max(1, area_h - 2 * margin)
    w = min(avail_w, int(round(avail_h * aspect)))
    h = max(1, int(round(w / aspect)))
    if h > avail_h:  # pragma: no cover - rounding guard
        h = avail_h
        w = max(1, int(round(h * aspect)))
    x = x0 + index * share_w + (share_w - w) // 2
    y = y0 + (area_h - h) // 2
    return (int(x), int(y), int(w), int(h))


#: Cap on the cumulative correction, so a window the WM keeps clamping (a
#: reserved edge, a snapped tile) settles instead of walking off the screen.
MAX_CORRECTION_PX = 240


def place_window(name, rect, pump=None, passes=6):
    """Resize/move an existing cv2 window so its IMAGE area lands on ``rect``.

    Applying the geometry once is not enough, for two independent reasons:

    * The window manager adds decoration, so the frame origin we ask for is not
      where the image lands (measured here: +37 px in y for the title bar).
    * Qt lays the window out asynchronously. Sizing it in the same tick as its
      first ``imshow`` is silently overridden by that layout, which leaves a
      stub window in the corner.

    So this pumps the GUI event loop, applies, reads the real image rect back
    and re-applies against the error until it agrees. ``pump`` is the caller's
    event pump (``cv2.waitKey``). Placement is cosmetic: every failure is
    swallowed, because a window in the wrong spot must never end a session.
    """
    if not rect:
        return
    import cv2  # local: keeps the geometry helpers importable headless

    x, y, w, h = (int(v) for v in rect)

    def _pump():
        if pump is None:
            return
        try:
            pump(1)
        except Exception:
            pass

    def _clamp(value):
        return max(-MAX_CORRECTION_PX, min(MAX_CORRECTION_PX, value))

    off_x = off_y = 0
    size_w, size_h = w, h
    for _ in range(max(1, int(passes))):
        _pump()
        try:
            cv2.resizeWindow(name, max(1, size_w), max(1, size_h))
            cv2.moveWindow(name, max(0, x + off_x), max(0, y + off_y))
        except cv2.error:
            return
        _pump()
        try:
            ix, iy, iw, ih = (int(v) for v in cv2.getWindowImageRect(name))
        except (cv2.error, TypeError, ValueError):
            return
        if iw <= 0 or ih <= 0:  # not realised yet — try again next pass
            continue
        dx, dy, dw, dh = x - ix, y - iy, w - iw, h - ih
        if max(abs(dx), abs(dy), abs(dw), abs(dh)) <= 1:
            return
        off_x, off_y = _clamp(off_x + dx), _clamp(off_y + dy)
        size_w, size_h = max(1, size_w + dw), max(1, size_h + dh)
