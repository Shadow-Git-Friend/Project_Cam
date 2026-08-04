#!/usr/bin/env python3
"""Training Drill board — live garage drills scored by body position.

Listens to the joint UDP stream broadcast by the live viewer (127.0.0.1:5005)
and runs one of the professional training drills from
`project_cam.training.drills`, rendering a big athlete-facing scoreboard
(drag it to the projector / second monitor, press `f` for fullscreen).

VIEW-ONLY: this process consumes pose packets and draws. It never opens a
serial port and never actuates the BLM. It is normally launched together with
the viewer by `Parallel_working/run_training_drill.sh` (which the desktop
Control Center spawns), but can run standalone next to any viewer that
broadcasts `--udp-target-*`.

Drills:
  balance    SINGLE-LEG BALANCE   (FIFA 11+ Part 2, pelvis sway in mm)
  shuttle    PRO-AGILITY SHUTTLE  (garage-scaled 5-10-5, split timing)
  line_hops  LATERAL LINE HOPS    (FIFA 11+ Part 3 quick feet)
  gk_save    SAVE THE CORNERS     (GK reaction matrix, self-calibrated zones)
  gk_updown  DOWN-UP RECOVERY     (GK conditioning, recovery timing)
  reaction_zones  REACTION ZONES  (projector lateral reaction, three zones)
  cmj        COUNTERMOVEMENT JUMP (load monitoring, pelvis rise + drop-off)
  hop_symmetry  SINGLE-LEG HOP SYMMETRY (limb symmetry screening)
  reactive_cut  REACTIVE CUT      (cue at the commitment point, decision time)

Logs:
  <log-dir>/<drill>_<ts>.jsonl          per-round events (live)
  <log-dir>/<drill>_<ts>_summary.json   end-of-session record
  <log-dir>/sessions_index.jsonl        one line per session (desktop app reads this)

Keys: SPACE start/pause · R restart · F fullscreen · Q quit
"""

import argparse
import json
import math
import os
import signal
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from project_cam.training import (  # noqa: E402
    DRILL_REGISTRY,
    append_session_index,
    build_session_record,
)
from project_cam.training.drills import (  # noqa: E402
    PROTOCOL_CATALOG,
    ankle_mid_mm,
    applied_parameters,
    get_joint,
    pelvis_mm,
    protocol_parameters_fingerprint,
    validate_workload,
)
from project_cam.training.replay import PACKET_TRACE_SCHEMA  # noqa: E402
from project_cam.viz.window import PANES, pane_rect, place_window  # noqa: E402

try:
    # Unicode-safe text (Cyrillic athlete names) — see .claude/rules/perf.md.
    from project_cam.viz.text import put_text as _put_text_unicode
    from project_cam.viz.text import text_size as _text_size_unicode
except Exception:  # pragma: no cover - fonts/PIL missing
    _put_text_unicode = None
    _text_size_unicode = None

# ------------------------------- palette (BGR) -------------------------------
# Semantic roles, not decoration. YELLOW is the only bold colour and means one
# thing — the system is asking the athlete for something. Result colours are
# separate from the accent so a cue can never read as a verdict.
YELLOW = (0, 222, 255)          # club yellow #FFDE00 — cue / prompt / active
WHITE = (238, 238, 238)         # ice — live measured values
GREY = (150, 150, 150)
STEEL = (119, 115, 110)         # #6E7377 — units, labels, history, evidence
DGREY = (90, 90, 90)
GREEN = (90, 205, 70)           # good — inside band
AMBER = (59, 169, 240)          # #F0A93B — late, or DEGRADED capture
RED = (59, 59, 235)             # miss — timeout, touch-down, void
BG_TOP = (26, 24, 22)
BG_BOT = (10, 9, 9)
BAR_BG = (14, 13, 12)
PANEL = (22, 21, 20)


def resolve_trace_path(args):
    """Where to record the pose trace, or "" for nowhere.

    Explicit flags win. Otherwise a trace is written only inside a desktop
    session directory, which is where the rest of the evidence chain already
    lives (`PROJECT_CAM_SESSION_DIR`, owner-only mode) — a bare CLI run stays
    side-effect free.
    """
    if getattr(args, "no_record_packets", False):
        return ""
    explicit = str(getattr(args, "record_packets", "") or "").strip()
    if explicit:
        return explicit
    session_dir = os.environ.get("PROJECT_CAM_SESSION_DIR", "").strip()
    if not session_dir:
        return ""
    return str(Path(session_dir) / "pose_trace.jsonl")


class UDPJointListener:
    """Background listener for the viewer's joints packets (primary person).

    Liveness and tracking are separate facts. A viewer running
    `--udp-capture-context` also sends a heartbeat with an empty ``joints``
    when nothing passed the confidence/camera gates, so:

    - ``last_packet_ts`` advances on any well-formed packet (viewer is alive);
    - ``last_joint_ts`` advances only when at least one joint arrived.

    ``get()`` reports tracking from ``last_joint_ts``, so an empty heartbeat
    reads to the drill as absence of tracking, never as a fresh observation.
    Per-joint ``conf``/``cams`` are kept beside the coordinates rather than
    discarded: they are the only per-frame quality evidence the viewer sends,
    and the session's comparability block is aggregated from them.
    """

    def __init__(self, host="0.0.0.0", port=5005, record_path=None,
                 record_max_bytes=256 * 1024 * 1024):
        # Optional raw-packet recorder. Until now nothing persisted the pose
        # stream, so a defect seen in a live session could never be reproduced:
        # the summary said `sway_rms_mm 3986.5` and the packets that produced it
        # were gone. A recorded trace turns a live fault into a replayable test
        # (see project_cam.training.replay).
        self.record_path = str(record_path) if record_path else ""
        self.record_max_bytes = int(record_max_bytes)
        self.records_written = 0
        self.record_bytes = 0
        self.record_truncated = False
        self._record_stream = None
        # Set once the socket is bound. With port=0 the OS picks a free port, so
        # a test can drive the real socket path instead of a stubbed listener.
        self.bound_port = None
        self.lock = threading.Lock()
        self.joints = None
        self.joint_conf = {}
        self.joint_cams = {}
        self.last_ts = 0.0          # last joint observation (tracking)
        self.last_packet_ts = 0.0   # last packet of any kind (liveness)
        self.capture = None
        self._packets = 0
        self._packets_with_joints = 0
        self._cams_seen = []
        self._role_open_packets = {}
        self._run = True
        self._t = threading.Thread(target=self._listen, args=(host, port), daemon=True)
        self._t.start()

    def _listen(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        self.bound_port = int(s.getsockname()[1])
        s.settimeout(1.0)
        while self._run:
            try:
                data, _ = s.recvfrom(65535)
                pkt = json.loads(data.decode("utf-8", errors="ignore"))
                raw = pkt.get("joints")
                if isinstance(raw, dict):
                    joints, conf, cams = {}, {}, {}
                    for name, v in raw.items():
                        if isinstance(v, dict) and "x_mm" in v:
                            joints[name] = (float(v["x_mm"]), float(v["y_mm"]),
                                            float(v["z_mm"]))
                            if "conf" in v:
                                conf[name] = float(v["conf"])
                            if "cams" in v:
                                cams[name] = int(v["cams"])
                    now = time.time()
                    with self.lock:
                        self._observe_packet(pkt, joints, conf, cams, now)
                    self._record(pkt, now)
            except socket.timeout:
                continue
            except Exception:
                continue
        s.close()
        self._close_record()

    @staticmethod
    def trace_schema():
        return PACKET_TRACE_SCHEMA

    def _record(self, pkt, now):
        """Append the raw packet. Single writer (this thread), so no lock."""
        if not self.record_path or self.record_truncated:
            return
        try:
            if self._record_stream is None:
                path = Path(self.record_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                # Line-buffered: a trace is worthless if a hard exit eats the
                # last seconds, which is exactly when the fault happens.
                self._record_stream = open(path, "a", encoding="utf-8",
                                           buffering=1)
            line = json.dumps({"schema": PACKET_TRACE_SCHEMA, "t": now,
                               "packet": pkt},
                              ensure_ascii=False, separators=(",", ":")) + "\n"
            if self.record_bytes + len(line) > self.record_max_bytes:
                # Stop at the cap and say so once, rather than filling the disk
                # during an unattended session.
                self.record_truncated = True
                self._record_stream.write(json.dumps(
                    {"schema": PACKET_TRACE_SCHEMA, "t": now,
                     "truncated_at_bytes": self.record_bytes}) + "\n")
                self._close_record()
                return
            self._record_stream.write(line)
            self.record_bytes += len(line)
            self.records_written += 1
        except OSError:
            # A trace is diagnostic evidence; losing it must never take the
            # session down with it.
            self.record_truncated = True
            self._close_record()

    def _close_record(self):
        if self._record_stream is not None:
            try:
                self._record_stream.flush()
                self._record_stream.close()
            except OSError:
                pass
            self._record_stream = None

    def _observe_packet(self, pkt, joints, conf, cams, now):
        """Record one packet under the lock. Caller holds self.lock."""
        self._packets += 1
        self.last_packet_ts = now
        capture = pkt.get("capture")
        if isinstance(capture, dict):
            self.capture = capture
            opened = capture.get("opened_camera_roles")
            configured = capture.get("configured_camera_roles")
            if isinstance(configured, list):
                opened_set = set(opened) if isinstance(opened, list) else set()
                for role in configured:
                    seen, total = self._role_open_packets.get(role, (0, 0))
                    self._role_open_packets[role] = (
                        seen + (1 if role in opened_set else 0), total + 1)
        if not joints:
            # Heartbeat: the viewer is alive but tracked nothing. Deliberately
            # does NOT touch last_ts — an armed drill state must not see this as
            # a fresh observation, nor as positive evidence of leaving.
            return
        self._packets_with_joints += 1
        self._cams_seen.extend(cams.values())
        self.joints = joints
        self.joint_conf = conf
        self.joint_cams = cams
        self.last_ts = now

    def get(self, max_age=0.6):
        """(joints or None, age_s) — age is of the last JOINT observation."""
        with self.lock:
            age = time.time() - self.last_ts if self.last_ts else 1e9
            if not self.joints or age > max_age:
                return None, age
            return dict(self.joints), age

    def viewer_alive(self, max_age=2.0):
        """Did any packet (including a heartbeat) arrive recently?"""
        with self.lock:
            if not self.last_packet_ts:
                return False
            return (time.time() - self.last_packet_ts) <= max_age

    def capture_quality(self):
        """Aggregated comparability evidence, or None without a capture context.

        Returns raw observations only. Whether a session is baseline-eligible is
        decided by the versioned comparison policy from these numbers — never
        stored here as a boolean, so changing a threshold can be re-applied to
        history instead of silently grandfathering it.
        """
        with self.lock:
            if self.capture is None or self._packets == 0:
                return None
            ratios = {
                role: round(seen / total, 4)
                for role, (seen, total) in sorted(self._role_open_packets.items())
                if total > 0
            }
            cams_seen = sorted(self._cams_seen)
            median_cams = None
            if cams_seen:
                mid = len(cams_seen) // 2
                median_cams = (float(cams_seen[mid]) if len(cams_seen) % 2
                               else 0.5 * (cams_seen[mid - 1] + cams_seen[mid]))
            return {
                "context_schema": self.capture.get("context_schema", ""),
                "configured_camera_roles":
                    list(self.capture.get("configured_camera_roles", [])),
                "opened_camera_roles":
                    list(self.capture.get("opened_camera_roles", [])),
                "calibration_fingerprint":
                    self.capture.get("calibration_fingerprint", ""),
                "camera_open_ratio_by_role": ratios,
                "pose_valid_frame_ratio":
                    round(self._packets_with_joints / self._packets, 4),
                "median_reported_joint_cameras": median_cams,
                "packets_observed": self._packets,
            }

    def stop(self):
        self._run = False


# ------------------------------ draw helpers ---------------------------------

_BG_CACHE = {}


def _bg(w, h):
    """The stage gradient. Cached: it never changes, and rebuilding a 2.7 MB
    array every frame was pure waste on a machine also running six camera
    threads and pose inference."""
    key = (int(w), int(h))
    cached = _BG_CACHE.get(key)
    if cached is None:
        img = np.empty((h, w, 3), np.uint8)
        ramp = np.linspace(0, 1, h, dtype=np.float32)[:, None]
        top = np.array(BG_TOP, np.float32)
        bot = np.array(BG_BOT, np.float32)
        img[:] = (top[None] * (1 - ramp) + bot[None] * ramp).astype(np.uint8)[:, None, :]
        _BG_CACHE[key] = img
        cached = img
    return cached.copy()


def _build_glow_sprite(size=192):
    """One radial falloff, built once. Scaled and added where a glow is needed —
    no per-frame blur anywhere in the board."""
    axis = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    xx, yy = np.meshgrid(axis, axis)
    radial = np.sqrt(xx * xx + yy * yy)
    falloff = np.clip(1.0 - radial, 0.0, 1.0) ** 2.2
    return falloff


_GLOW = _build_glow_sprite()


_GLOW_PATCH = {}


def _glow_patch(radius, color):
    """Full-intensity coloured halo for one radius, built once.

    Radii on this board come from the layout, so only a handful of distinct
    values ever appear and the cache stays small. Keeping the patch in uint8
    lets the per-frame blend be a single SIMD `addWeighted` instead of a
    float32 round-trip over ~170k pixels, which measured at 2.31 ms.
    """
    key = (int(radius), tuple(color))
    patch = _GLOW_PATCH.get(key)
    if patch is None:
        size = int(radius) * 2
        sprite = cv2.resize(_GLOW, (size, size), interpolation=cv2.INTER_LINEAR)
        patch = (sprite[:, :, None] * np.array(color, np.float32)[None, None, :])
        patch = np.clip(patch, 0, 255).astype(np.uint8)
        _GLOW_PATCH[key] = patch
    return patch


def glow(img, cx, cy, radius, color, gain=1.0):
    """Additive halo. `gain` is meant to carry a measured value, not taste."""
    radius = int(max(2, radius))
    gain = float(max(0.0, min(1.0, gain)))
    if gain <= 0.01:
        return
    x0, y0 = int(cx) - radius, int(cy) - radius
    x1, y1 = int(cx) + radius, int(cy) + radius
    h, w = img.shape[:2]
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(w, x1), min(h, y1)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    patch = _glow_patch(radius, color)[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
    roi = img[sy0:sy1, sx0:sx1]
    cv2.addWeighted(roi, 1.0, patch, gain, 0.0, dst=roi)


def panel(img, x0, y0, x1, y1, radius=10, fill=PANEL, border=None, thick=1):
    """Rounded panel from rectangles and ellipse quadrants — cheap, and on a
    dark ground it reads as a rounded card without any alpha compositing."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    r = int(max(0, min(radius, (x1 - x0) // 2, (y1 - y0) // 2)))
    if fill is not None:
        cv2.rectangle(img, (x0 + r, y0), (x1 - r, y1), fill, -1)
        cv2.rectangle(img, (x0, y0 + r), (x1, y1 - r), fill, -1)
        for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r),
                       (x0 + r, y1 - r), (x1 - r, y1 - r)):
            cv2.circle(img, (cx, cy), r, fill, -1)
    if border is not None:
        cv2.line(img, (x0 + r, y0), (x1 - r, y0), border, thick, cv2.LINE_AA)
        cv2.line(img, (x0 + r, y1), (x1 - r, y1), border, thick, cv2.LINE_AA)
        cv2.line(img, (x0, y0 + r), (x0, y1 - r), border, thick, cv2.LINE_AA)
        cv2.line(img, (x1, y0 + r), (x1, y1 - r), border, thick, cv2.LINE_AA)
        for (cx, cy), a in (((x0 + r, y0 + r), 180), ((x1 - r, y0 + r), 270),
                            ((x1 - r, y1 - r), 0), ((x0 + r, y1 - r), 90)):
            cv2.ellipse(img, (cx, cy), (r, r), a, 0, 90, border, thick, cv2.LINE_AA)


def sc(H, s):
    """Font scale normalised to a 720-tall board, so the layout survives a
    different --height without hand-tuning every call."""
    return float(s) * (float(H) / 720.0)


#: Pixels `render()` reserves at the bottom for the key hints (baseline H-44)
#: and the evidence rail (from H-34), quoted at the 720-tall baseline. A drawer
#: that paints into this band overwrites the honesty rail, which is the one
#: thing on the board that must never be obscured.
STAGE_BOTTOM_RESERVED = 62

#: Top bar: height, the yellow rule under it, and the title baseline — also at
#: the 720 baseline. All chrome scales through `px()`, because the text inside
#: it scales with H: a fixed 64 px bar under 1.5x text is a cramped strip at
#: fullscreen, and a fixed bottom band leaves the rail's text hanging.
BAR_H, BAR_RULE, BAR_BASELINE = 64, 65, 42


def px(H, value):
    """A layout offset in pixels, normalised to a 720-tall board like `sc()`.

    Everything drawn on this board scales with H. Any offset that does not is a
    bug waiting for a different `--height`: the top-right clock was pinned at
    `W - 330`, sized for 1280x720, and ran 109 px off the edge at 1920x1080.
    """
    return int(round(float(value) * (float(H) / 720.0)))


def stage_bottom(H):
    """Lowest y a per-drill drawer may use.

    Exists as one function rather than a remembered number because every drawer
    got it wrong independently: elements placed at y=660..670 on a 720-tall board
    painted straight over the key hints.
    """
    return int(H) - px(H, STAGE_BOTTOM_RESERVED)


def value_unit(img, s, unit, cx, y, scale, color, H, thick=3):
    """A measurement is a number AND its unit. Draws them as one centred group
    so a bare figure can never appear on the board by accident."""
    fs = sc(H, scale)
    us = sc(H, scale * 0.34)
    (vw, _), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, fs, thick)
    (uw, _), _ = cv2.getTextSize(" " + unit, cv2.FONT_HERSHEY_SIMPLEX, us, 2)
    x = int(cx - (vw + uw) / 2)
    text(img, s, (x, int(y)), fs, color, thick)
    text(img, " " + unit, (x + vw, int(y)), us, STEEL, 2)


# Timing tiers are bands on a measured time, shown next to the raw value —
# never a graded score. Thresholds are display-only and deliberately coarse:
# the signal is quantised by the capture rate, so finer bands would be theatre.
TIER_GOOD_S = 0.50
TIER_LATE_S = 0.62


def tier_of(reaction_s):
    if reaction_s is None:
        return "—", STEEL
    if reaction_s <= TIER_GOOD_S:
        return "PERFECT", GREEN
    if reaction_s <= TIER_LATE_S:
        return "GOOD", GREEN
    return "LATE", AMBER


def text(img, s, org, scale, color, thick=2, shadow=True):
    """`shadow` draws a black outline first so text stays legible over a bright
    zone or a glow. It doubles the cost of the call (measured 0.46 ms for a
    large string), so pass shadow=False for the many small labels that sit on
    the plain dark ground and gain nothing from it."""
    if shadow:
        cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0),
                    thick + 3, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick,
                cv2.LINE_AA)


def text_c(img, s, cx, y, scale, color, thick=2, shadow=True):
    (tw, _), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    text(img, s, (int(cx - tw / 2), int(y)), scale, color, thick, shadow=shadow)


def name_text(img, s, org, scale, color, thick=2):
    """Athlete names may be non-ASCII — route through project_cam.viz.text."""
    if _put_text_unicode is not None:
        _put_text_unicode(img, s, org, scale, color, thick)
    else:
        safe = s.encode("ascii", errors="replace").decode("ascii")
        cv2.putText(img, safe, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                    thick, cv2.LINE_AA)


def name_width(s, scale, thick=2):
    """Rendered width of an athlete name, measured by whichever backend draws it.

    cv2's own measurement is wrong for the Cyrillic names this board shows (it
    counts bytes, not glyphs), so ask the Unicode helper when it is present.
    """
    if _text_size_unicode is not None:
        # cv2-compatible shape: ((width, height), baseline)
        return int(_text_size_unicode(s, scale, thick)[0][0])
    safe = s.encode("ascii", errors="replace").decode("ascii")
    return int(cv2.getTextSize(safe, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)[0][0])


def name_text_c(img, s, cx, y, scale, color, thick=2):
    """Centre an athlete name on `cx` using its measured width."""
    name_text(img, s, (int(cx - name_width(s, scale, thick) / 2), int(y)),
              scale, color, thick)


def hbar(img, x0, y0, w, h, frac, color, bg=PANEL):
    frac = max(0.0, min(1.0, frac))
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), bg, -1)
    if frac > 0:
        cv2.rectangle(img, (x0, y0), (x0 + int(w * frac), y0 + h), color, -1)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), DGREY, 1)


def pulse(a=0.35, b=1.0, hz=3.0):
    return a + (b - a) * (0.5 + 0.5 * math.sin(time.time() * 2 * math.pi * hz))


def hero(img, W, H, value, unit, caption=None, verdict=None, color=WHITE,
         y_frac=0.28, scale=2.9, thick=6):
    """The one number the athlete reads from across the garage.

    Every board puts its headline measurement in the same place, at the same
    size, with the same three parts: the value with its unit, a caption saying
    what was measured, and — only where a time is being judged — the tier word.
    Consistency is the point: a coach glancing at any drill knows where to look,
    and a number that moved to suit one layout would break that.
    """
    value_unit(img, value, unit, W // 2, int(H * y_frac), scale, color, H,
               thick=thick)
    if caption:
        text_c(img, caption, W // 2, int(H * (y_frac + 0.065)), sc(H, 0.5),
               STEEL, 1, shadow=False)
    if verdict:
        word, vcol = verdict
        text_c(img, word, W // 2, int(H * (y_frac + 0.135)), sc(H, 0.95), vcol, 3)


def prompt(img, W, H, msg, y_frac=0.28, scale=1.4, color=None, sub=None):
    """An ASK, in the hero slot: the system wants the athlete to do something.

    Yellow is reserved for this. A result never uses it, so the athlete can tell
    "do something" from "here is what you did" without reading a word.
    """
    text_c(img, msg, W // 2, int(H * y_frac), sc(H, scale),
           color if color is not None else mix(WHITE, YELLOW, pulse()), 3)
    if sub:
        text_c(img, sub, W // 2, int(H * (y_frac + 0.075)), sc(H, 0.55), STEEL,
               2, shadow=False)


def countdown(img, W, H, seconds_left, y_frac=0.30):
    """The pre-rep count, glowing so it carries at projector distance."""
    n = max(1, int(math.ceil(seconds_left)))
    glow(img, W // 2, int(H * y_frac) - int(sc(H, 30)), int(sc(H, 150)), YELLOW,
         gain=0.30)
    text_c(img, str(n), W // 2, int(H * y_frac), sc(H, 4.6), YELLOW, 8)


def stat_rail(img, W, H, title, rows, y_frac=0.13):
    """Per-attempt breakdown, top-left.

    A hero value is the current rep; this is the session. Weaknesses that only
    appear in the aggregate (one corner, one leg, one zone) are the coaching
    finding, and revealing them while the session runs makes them trainable
    today rather than a report afterwards.
    """
    x = int(W * 0.045)
    y = int(H * y_frac)
    text(img, title, (x, y), sc(H, 0.45), STEEL, 1, shadow=False)
    for label, value, color in rows:
        y += int(H * 0.045)
        text(img, f"{label}{value}", (x, y), sc(H, 0.5), color, 2, shadow=False)
    return y


def note_right(img, W, H, note, y_frac=0.13):
    """The protocol fact the hero number has to be read against, top-right.

    Right-aligned from the measured width — a fixed offset clips at fullscreen.
    """
    (tw, _), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, sc(H, 0.45), 1)
    text(img, note, (W - tw - int(W * 0.045), int(H * y_frac)), sc(H, 0.45),
         STEEL, 1, shadow=False)


def history_bars(img, x0, y0, width, height, values, H, reference=None,
                 label=None, tint=None, colors=None, tags=None, max_bars=24):
    """Per-attempt values oldest -> newest, scaled to the athlete's own best.

    The trend across a set is what a single current value cannot show: holding a
    number and decaying to it produce the same last rep. `reference` draws the
    athlete's own baseline (first or best attempt) so drift off it is readable
    without a population norm.

    `tags` labels each bar with a short string (L / R). Whenever a bar's colour
    carries a CATEGORY rather than a quality, the category must also be readable
    without colour: GREEN vs AMBER is a common confusion under deuteranopia, and
    an athlete-facing board that encodes which limb hopped in hue alone is
    unreadable to roughly one man in twelve.
    """
    # `colors` is a list parallel to `values` for the cases where the colour is a
    # property of the ATTEMPT (which limb hopped) rather than of the value, where
    # looking the value back up would mis-colour any repeated measurement.
    pairs = [(v, (colors[i] if colors and i < len(colors) else None),
              (tags[i] if tags and i < len(tags) else None))
             for i, v in enumerate(values) if v is not None][-max_bars:]
    if not pairs:
        if label:
            text(img, label, (x0, y0 - int(sc(H, 10))), sc(H, 0.5), STEEL, 1,
                 shadow=False)
        return
    shown = [v for v, _, _ in pairs]
    top = max(max(shown), reference or 0.0) or 1.0
    slot = width / max(1, len(shown))
    bw = max(3, int(slot * 0.68))
    for i, (val, col, tag) in enumerate(pairs):
        h = max(2, int(height * min(1.0, val / top)))
        cx_ = int(x0 + slot * (i + 0.5))
        if col is None:
            col = tint(val) if tint else WHITE
        cv2.rectangle(img, (cx_ - bw // 2, y0 + height - h),
                      (cx_ + bw // 2, y0 + height), col, -1)
        if tag:
            text_c(img, tag, cx_, y0 + height + int(sc(H, 18)), sc(H, 0.5),
                   col, 2, shadow=False)
    if reference:
        ry = y0 + height - int(height * min(1.0, reference / top))
        cv2.line(img, (x0, ry), (x0 + width, ry), STEEL, 1, cv2.LINE_AA)
    if label:
        text(img, label, (x0, y0 - int(sc(H, 10))), sc(H, 0.5), STEEL, 1,
             shadow=False)


def live_dot(img, cx, cy, H, color=WHITE, radius=11, halo=0.5):
    """Where the athlete is right now — one shape, used by every spatial stage."""
    glow(img, cx, cy, int(sc(H, 46)), color, gain=halo)
    cv2.circle(img, (cx, cy), int(sc(H, radius)), color, -1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), int(sc(H, radius)), (0, 0, 0), 2, cv2.LINE_AA)


def mix(c1, c2, t):
    return tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))


# --------------------------- per-drill scoreboards ---------------------------

#: Sway rings on the balance reticle, in mm. Coarse on purpose: reconstruction
#: precision on this rig is ~4 mm, so finer rings would imply resolution the
#: geometry does not have.
SWAY_RINGS_MM = (20.0, 40.0, 60.0)


def sway_reticle(img, cx, cy, radius_px, track, H):
    """Sway as a target, not a bar.

    An RMS scalar says how much the athlete moved; it cannot say WHERE. Drifting
    steadily onto one edge is a different fault from oscillating about a stable
    centre, and the coach's correction differs. The rings are the mm scale, the
    trail is the recent path, the dot is now.
    """
    per_mm = radius_px / SWAY_RINGS_MM[-1]
    cv2.line(img, (cx - radius_px, cy), (cx + radius_px, cy), DGREY, 1)
    cv2.line(img, (cx, cy - radius_px), (cx, cy + radius_px), DGREY, 1)
    for ring in SWAY_RINGS_MM:
        r = int(ring * per_mm)
        cv2.circle(img, (cx, cy), r, DGREY, 1, cv2.LINE_AA)
        # Labels sit on the up-right diagonal, where neither axis line runs —
        # placing them on the horizontal axis put digits straight on the rule.
        off = int(r * 0.7071)
        text(img, f"{ring:.0f}", (cx + off + int(sc(H, 4)),
                                  cy - off - int(sc(H, 4))),
             sc(H, 0.4), STEEL, 1, shadow=False)
    if track is None:
        # Inside the reticle: below it sits the foot indicator, and the two
        # collided at the panel edge.
        text_c(img, "SETTLING", cx, cy + int(sc(H, 8)), sc(H, 0.7), STEEL, 2,
               shadow=False)
        return
    trail = track["trail_mm"]
    for i in range(1, len(trail)):
        a, b = trail[i - 1], trail[i]
        # Older segments fade toward the panel, so the eye reads direction of
        # travel without introducing a colour. The trail is a measured path, so
        # it stays on WHITE — the live-measurement role.
        t = i / max(1, len(trail) - 1)
        cv2.line(img,
                 (cx + int(a[0] * per_mm), cy + int(a[1] * per_mm)),
                 (cx + int(b[0] * per_mm), cy + int(b[1] * per_mm)),
                 mix(PANEL, WHITE, 0.20 + 0.80 * t), 2, cv2.LINE_AA)
    dx, dy = track["offset_mm"]
    px = cx + int(max(-1.6, min(1.6, dx / SWAY_RINGS_MM[-1])) * radius_px)
    py = cy + int(max(-1.6, min(1.6, dy / SWAY_RINGS_MM[-1])) * radius_px)
    rms = track["rms_mm"]
    col = GREEN if rms < SWAY_RINGS_MM[0] else (YELLOW if rms < SWAY_RINGS_MM[1] else RED)
    glow(img, px, py, int(sc(H, 34)), col, gain=0.45)
    cv2.circle(img, (px, py), int(sc(H, 9)), col, -1, cv2.LINE_AA)
    cv2.circle(img, (px, py), int(sc(H, 9)), (0, 0, 0), 2, cv2.LINE_AA)


def draw_balance(img, d, now, joints, args, W, H):
    cy = H // 2
    if d.state in ("countdown", "rest"):
        stance = d.stance_leg().upper()
        text_c(img, f"STAND ON YOUR {stance} LEG", W // 2, cy - int(sc(H, 120)),
               sc(H, 1.5), WHITE, 3)
        if d.state == "countdown":
            if d.waiting_tracking:
                text_c(img, "STEP INTO THE ARENA", W // 2, cy, sc(H, 1.1),
                       mix(RED, WHITE, pulse()), 2)
            else:
                n = max(1, int(math.ceil(d.countdown_s - (now - d.t_state))))
                glow(img, W // 2, cy + int(sc(H, 34)), int(sc(H, 150)), YELLOW,
                     gain=0.30)
                text_c(img, str(n), W // 2, cy + int(sc(H, 60)), sc(H, 5.0),
                       YELLOW, 8)
        else:
            left = d.rest_s - (now - d.t_state)
            text_c(img, f"REST  {max(0, left):.0f}s", W // 2, cy, sc(H, 1.4),
                   STEEL, 3)
        if d.results:
            last = d.results[-1]
            if last["sway_rms_mm"] is not None:
                # Measured facts only. The legacy 0-100 `score` is an invented
                # composite (100 - max(0, sway-8)*2) and is no longer shown to
                # the athlete; it stays in the raw summary for old readers.
                text_c(img, f"last hold: sway {last['sway_rms_mm']:.0f} mm  |  "
                            f"{last['touchdowns']} touch-down(s)",
                       W // 2, cy + int(sc(H, 150)), sc(H, 0.9), STEEL, 2,
                       shadow=False)
    elif d.state == "hold":
        left = max(0.0, d.hold_s - (now - d.t_state))
        rad = int(sc(H, 150))
        rcx, rcy = W // 2, cy - int(sc(H, 20))
        panel(img, rcx - rad - int(sc(H, 26)), rcy - rad - int(sc(H, 26)),
              rcx + rad + int(sc(H, 26)), rcy + rad + int(sc(H, 26)),
              radius=int(sc(H, 16)), border=DGREY)
        track = d.live_sway_track(now)
        sway_reticle(img, rcx, rcy, rad, track, H)

        # Countdown and sway sit either side of the reticle, so neither competes
        # with it for the centre of the board.
        text(img, f"{left:4.1f}", (int(sc(H, 70)), cy - int(sc(H, 10))),
             sc(H, 3.2), WHITE, 6)
        text(img, "SECONDS LEFT", (int(sc(H, 74)), cy + int(sc(H, 34))),
             sc(H, 0.6), STEEL, 2, shadow=False)
        hbar(img, int(sc(H, 70)), cy + int(sc(H, 60)), int(sc(H, 240)),
             int(sc(H, 12)), 1 - left / d.hold_s, YELLOW)

        sway = None if track is None else track["rms_mm"]
        col = (STEEL if sway is None else
               (GREEN if sway < SWAY_RINGS_MM[0] else
                (YELLOW if sway < SWAY_RINGS_MM[1] else RED)))
        rx = W - int(sc(H, 230))
        value_unit(img, "--" if sway is None else f"{sway:.0f}", "mm",
                   rx, cy - int(sc(H, 10)), 3.0, col, H)
        text_c(img, "SWAY RMS", rx, cy + int(sc(H, 34)), sc(H, 0.6), STEEL, 2,
               shadow=False)

        stance = d.stance_leg()
        for i, leg in enumerate(("left", "right")):
            x = W // 2 - int(sc(H, 70)) + i * int(sc(H, 140))
            up = d.raised and leg != stance
            y = cy + int(sc(H, 195)) - (int(sc(H, 30)) if up else 0)
            r = int(sc(H, 24))
            cv2.circle(img, (x, y), r, YELLOW if leg == stance else STEEL,
                       -1 if leg == stance else 2, cv2.LINE_AA)
            text_c(img, leg[0].upper(), x, y + int(sc(H, 8)), sc(H, 0.8),
                   (0, 0, 0) if leg == stance else STEEL, 2, shadow=False)
        if not d.raised:
            text_c(img, "LIFT YOUR FREE FOOT", W // 2, cy + int(sc(H, 250)),
                   sc(H, 0.9), mix(RED, WHITE, pulse()), 2)
        elif d.touchdowns:
            text_c(img, f"touch-downs {d.touchdowns}", W // 2,
                   cy + int(sc(H, 250)), sc(H, 0.8), STEEL, 2, shadow=False)
    elif d.state == "done":
        text_c(img, "SESSION COMPLETE", W // 2, int(sc(H, 120)), sc(H, 1.4),
               YELLOW, 3)
        s = d.summary()
        done = [r for r in d.results if r["sway_rms_mm"] is not None]
        # Per-hold sway as a column chart: whether the athlete degraded across
        # the session is the coaching question, and a table of numbers hides it.
        if done:
            worst = max(max(r["sway_rms_mm"] for r in done), SWAY_RINGS_MM[0])
            bx0, bx1 = int(sc(H, 110)), W - int(sc(H, 110))
            base = int(sc(H, 470))
            top = int(sc(H, 200))
            slot = (bx1 - bx0) / len(done)
            bw = int(min(slot * 0.55, sc(H, 86)))
            cv2.line(img, (bx0, base), (bx1, base), DGREY, 1)
            for i, r in enumerate(done):
                v = r["sway_rms_mm"]
                cx_ = int(bx0 + slot * (i + 0.5))
                h = int((base - top) * min(1.0, v / worst))
                col = (GREEN if v < SWAY_RINGS_MM[0] else
                       (YELLOW if v < SWAY_RINGS_MM[1] else RED))
                cv2.rectangle(img, (cx_ - bw // 2, base - h),
                              (cx_ + bw // 2, base), col, -1)
                text_c(img, f"{v:.0f}", cx_, base - h - int(sc(H, 12)),
                       sc(H, 0.6), WHITE, 2, shadow=False)
                text_c(img, r["stance"][:1].upper(), cx_, base + int(sc(H, 26)),
                       sc(H, 0.6), STEEL, 2, shadow=False)
                if r["touchdowns"]:
                    text_c(img, f"td{r['touchdowns']}", cx_,
                           base + int(sc(H, 48)), sc(H, 0.5), AMBER, 1,
                           shadow=False)
            text(img, "sway RMS per hold, mm", (bx0, top - int(sc(H, 14))),
                 sc(H, 0.55), STEEL, 1, shadow=False)
        if s["avg_sway_mm"] is not None:
            lft = "--" if s["left_sway_mm"] is None else f"{s['left_sway_mm']:.0f}"
            rgt = "--" if s["right_sway_mm"] is None else f"{s['right_sway_mm']:.0f}"
            value_unit(img, f"{s['avg_sway_mm']:.0f}", "mm avg",
                       W // 2, int(sc(H, 570)), 2.2, YELLOW, H)
            text_c(img, f"left stance {lft} mm   |   right stance {rgt} mm",
                   W // 2, int(sc(H, 612)), sc(H, 0.8), STEEL, 2, shadow=False)
        else:
            # Every hold was refused. Saying so beats an empty panel, which reads
            # as "nothing happened" when in fact the capture was faulty.
            text_c(img, "NO MEASURED HOLD", W // 2, int(sc(H, 570)), sc(H, 1.4),
                   AMBER, 3)
            text_c(img, "pelvis tracking was not stable enough to measure sway",
                   W // 2, int(sc(H, 612)), sc(H, 0.8), STEEL, 2, shadow=False)
        if s["samples_rejected"]:
            unmeasured = s["holds_completed"] - s["holds_measured"]
            detail = f"{s['samples_rejected']} pelvis sample(s) outside the arena"
            if unmeasured:
                detail += f"   |   {unmeasured} hold(s) not measured"
            text_c(img, detail, W // 2, int(sc(H, 648)), sc(H, 0.6), AMBER, 1,
                   shadow=False)


def ghost_split_bar(img, x0, y0, width, height, elapsed, best, H):
    """The running clock against the athlete's own best rep.

    `best` carries cumulative split boundaries in seconds. The filled bar is the
    live rep; the ticks are where the best rep reached each line. Being ahead or
    behind is the only thing the athlete can act on mid-rep, and an elapsed
    number alone cannot express it. Returns the signed delta at the last passed
    boundary, or None before the first one.
    """
    total = best[-1] if best else None
    span = max(elapsed, total or elapsed, 0.1) * 1.05
    cv2.rectangle(img, (x0, y0), (x0 + width, y0 + height), PANEL, -1)
    if not best:
        # No ghost yet. Filling the bar against the live elapsed time would keep
        # it ~95% full at every instant, which reads as "nearly done" and means
        # nothing — an empty track that says why is honest.
        cv2.rectangle(img, (x0, y0), (x0 + width, y0 + height), DGREY, 1)
        text(img, "first rep - no ghost to compare against yet",
             (x0, y0 + height + int(sc(H, 26))), sc(H, 0.5), STEEL, 1,
             shadow=False)
        return None
    cv2.rectangle(img, (x0, y0), (x0 + width, y0 + height), DGREY, 1)
    for i, cut in enumerate(best or ()):
        u = x0 + int(width * min(1.0, cut / span))
        cv2.line(img, (u, y0 - int(sc(H, 6))), (u, y0 + height + int(sc(H, 6))),
                 STEEL, 2, cv2.LINE_AA)
        text_c(img, "ABC"[i] if i < 3 else "", u, y0 - int(sc(H, 12)),
               sc(H, 0.5), STEEL, 1, shadow=False)
    # Delta at the most recent boundary the live rep has passed. Positive means
    # slower than the best rep reached that same line.
    passed = [c for c in (best or ()) if c <= elapsed]
    delta = (elapsed - passed[-1]) if passed else None
    if delta is None:
        col = YELLOW        # no comparison yet — a prompt colour, not a verdict
    else:
        col = GREEN if delta <= 0 else AMBER
    cv2.rectangle(img, (x0, y0), (x0 + int(width * min(1.0, elapsed / span)),
                                  y0 + height), col, -1)
    if best:
        text(img, "ghost = your best rep", (x0, y0 + height + int(sc(H, 26))),
             sc(H, 0.5), STEEL, 1, shadow=False)
    return delta


def draw_shuttle(img, d, now, joints, args, W, H):
    """5-10-5 shuttle: hero clock above, the lane seen from above below.

    Same grammar as the other cue drills — the measurement is read in the middle
    of the board and the spatial stage sits under it, so an athlete sprinting
    does not have to re-find the number between reps.
    """
    x0, x1 = int(W * 0.07), int(W * 0.93)
    ly0, ly1 = int(H * 0.52), int(H * 0.78)
    span0 = d.line_b - 700
    span1 = d.line_a + 700

    def X(mm):
        t = (mm - span0) / max(1.0, span1 - span0)
        return int(x0 + max(0.0, min(1.0, t)) * (x1 - x0))

    panel(img, x0, ly0, x1, ly1, radius=int(sc(H, 12)), fill=(15, 16, 18),
          border=(38, 42, 46))
    targets = {"to_a": "A", "to_b": "B", "home": "START"}
    target = targets.get(d.phase) if d.state == "run" else None
    for label, mm in (("B", d.line_b), ("START", d.center), ("A", d.line_a)):
        u = X(mm)
        hot = d.state == "run" and label == target
        col = YELLOW if hot else (WHITE if label == "START" else STEEL)
        if hot:
            glow(img, u, (ly0 + ly1) // 2, int(sc(H, 100)), YELLOW, gain=0.40)
        cv2.line(img, (u, ly0), (u, ly1), col, 4 if hot else 2, cv2.LINE_AA)
        text_c(img, label, u, ly0 - int(sc(H, 12)),
               sc(H, 0.9 if hot else 0.75), col, 2, shadow=False)
    p = pelvis_mm(joints)
    if p is not None:
        v = ly0 + int(max(0.0, min(1.0, p[1] / args.arena_y_mm)) * (ly1 - ly0))
        live_dot(img, X(p[0]), v, H, WHITE, radius=12, halo=0.55)

    strip_y = int(H * 0.845)
    strip_x, strip_w = int(W * 0.10), int(W * 0.80)

    # ---- hero band -----------------------------------------------------------
    if d.state == "arm":
        prompt(img, W, H, "WALK TO THE START LINE", y_frac=0.28, scale=1.4,
               sub="the rep arms once you are standing on it")
    elif d.state == "countdown":
        prompt(img, W, H, "READY", y_frac=0.22, scale=1.4, color=WHITE)
        countdown(img, W, H, d.countdown_s - (now - d.t_state), y_frac=0.38)
    elif d.state == "run":
        t = now - d.go_time
        best = d.best_rep()
        cuts = None
        if best is not None:
            cuts = [best["t_out_s"],
                    best["t_out_s"] + best["t_across_s"],
                    best["total_s"]]
        hero(img, W, H, f"{t:.2f}", "s", caption="ELAPSED THIS REP",
             y_frac=0.26, scale=3.0)
        text_c(img, f"SPRINT TO {target}", W // 2, int(H * 0.415), sc(H, 1.05),
               YELLOW, 3)
        delta = ghost_split_bar(img, strip_x, strip_y, strip_w,
                                int(sc(H, 20)), t, cuts, H)
        if delta is not None:
            sign = "+" if delta >= 0 else ""
            text_c(img, f"{sign}{delta:.2f} s vs your best rep", W // 2,
                   strip_y - int(sc(H, 16)), sc(H, 0.6),
                   AMBER if delta > 0 else GREEN, 2, shadow=False)
    elif d.state == "rest":
        if d.last_result and d.last_result[0] == "ok":
            r = d.results[-1]
            best = d.best_rep()
            is_best = best is not None and r["total_s"] == best["total_s"]
            hero(img, W, H, f"{r['total_s']:.2f}", "s",
                 caption=f"REP {r['rep']} TOTAL", y_frac=0.25, scale=2.7,
                 color=YELLOW if is_best else GREEN, thick=5,
                 verdict=("NEW BEST", YELLOW) if is_best else None)
            # Splits as proportional segments: which leg of the shuttle cost the
            # time is the actionable part, and three numbers in a row hide it.
            # A brightness ramp, not three colours — the segments are one
            # measured time decomposed, so they must not read as three verdicts.
            segs = (("out", r["t_out_s"], STEEL),
                    ("across", r["t_across_s"], GREY),
                    ("home", r["t_home_s"], WHITE))
            acc = 0
            for name, val, col in segs:
                seg_w = int(strip_w * (val / max(0.01, r["total_s"])))
                cv2.rectangle(img, (strip_x + acc, strip_y),
                              (strip_x + acc + seg_w, strip_y + int(sc(H, 20))),
                              col, -1)
                text_c(img, f"{name} {val:.2f}", strip_x + acc + seg_w // 2,
                       strip_y + int(sc(H, 42)), sc(H, 0.55), STEEL, 1,
                       shadow=False)
                acc += seg_w
            text(img, "this rep, split by leg", (strip_x, strip_y - int(sc(H, 10))),
                 sc(H, 0.5), STEEL, 1, shadow=False)
        elif d.last_result:
            text_c(img, "REP VOIDED", W // 2, int(H * 0.27), sc(H, 2.0), RED, 5)
            text_c(img, str(d.last_result[1]), W // 2, int(H * 0.35),
                   sc(H, 0.7), STEEL, 2, shadow=False)
        left = d.rest_s - (now - d.t_state)
        text_c(img, f"rest {max(0, left):.0f} s", W // 2, int(H * 0.455),
               sc(H, 0.8), STEEL, 2, shadow=False)
    elif d.state == "done":
        s = d.summary()
        if s["best_total_s"] is None:
            text_c(img, "NO COMPLETED REPS", W // 2, int(H * 0.28), sc(H, 1.4),
                   STEEL, 3)
            return
        hero(img, W, H, f"{s['best_total_s']:.2f}", "s", caption="BEST REP",
             y_frac=0.25, scale=2.7, color=YELLOW, thick=5)
        text_c(img, f"average {s['avg_total_s']:.2f} s over "
                    f"{s['reps_completed']} reps", W // 2, int(H * 0.40),
               sc(H, 0.85), WHITE, 2, shadow=False)
        if s["aborts"]:
            text_c(img, f"{s['aborts']} rep(s) voided on tracking loss",
                   W // 2, int(H * 0.445), sc(H, 0.65), AMBER, 2, shadow=False)
        totals = [r["total_s"] for r in d.results]
        best = min(totals) if totals else None
        history_bars(img, strip_x, strip_y - int(sc(H, 26)), strip_w,
                     int(sc(H, 46)), totals, H, reference=best,
                     label="rep totals, oldest -> newest (lower is better)",
                     tint=lambda v: GREEN if best and v <= best * 1.03 else (
                         WHITE if best and v <= best * 1.10 else AMBER))

    # ---- per-rep record ------------------------------------------------------
    if d.results:
        best = min(r["total_s"] for r in d.results)
        rows = [(f"REP {r['rep']:<2}", f"{r['total_s']:.2f} s",
                 YELLOW if r["total_s"] == best else WHITE)
                for r in d.results[-4:]]
        stat_rail(img, W, H, "PER REP", rows)
    note_right(img, W, H,
               f"course {d.summary()['course_m']} m   "
               f"lines {(d.line_a - d.line_b) / 1000.0:.1f} m apart")


def cadence_strip(img, x0, y0, width, height, cross_times, t_state, work_s, H,
                  bucket_s=1.0):
    """Hops per second across the work window.

    A set total and a mean rate both hide the shape: holding 6/s for 30 s and
    starting at 10/s then dying to 3/s produce the same average, and only the
    second is a fatigue finding. The strip is the shape. Amber marks buckets
    below 70% of this set's own best bucket — relative to the athlete, never to a
    population norm.
    """
    n = max(1, int(math.ceil(work_s / bucket_s)))
    counts = [0] * n
    for t in cross_times:
        idx = int((t - t_state) / bucket_s)
        if 0 <= idx < n:
            counts[idx] += 1
    cv2.rectangle(img, (x0, y0), (x0 + width, y0 + height), PANEL, -1)
    peak = max(counts) if any(counts) else 0
    if not peak:
        text(img, "cadence - waiting for the first hop",
             (x0 + int(sc(H, 8)), y0 + height - int(sc(H, 10))), sc(H, 0.5),
             STEEL, 1, shadow=False)
        cv2.rectangle(img, (x0, y0), (x0 + width, y0 + height), DGREY, 1)
        return
    slot = width / n
    bw = max(2, int(slot * 0.7))
    for i, c in enumerate(counts):
        if not c:
            continue
        h = int(height * (c / peak))
        cx_ = int(x0 + slot * (i + 0.5))
        col = GREEN if c >= 0.7 * peak else AMBER
        cv2.rectangle(img, (cx_ - bw // 2, y0 + height - h),
                      (cx_ + bw // 2, y0 + height), col, -1)
    cv2.rectangle(img, (x0, y0), (x0 + width, y0 + height), DGREY, 1)
    text(img, f"cadence, hops/s  |  peak {peak}",
         (x0, y0 - int(sc(H, 10))), sc(H, 0.5), STEEL, 1, shadow=False)


def draw_line_hops(img, d, now, joints, args, W, H):
    """Quick feet over the athlete's own line: count is the hero, cadence the story."""
    if d.state == "countdown":
        prompt(img, W, H, "STAND ON YOUR LINE", y_frac=0.24, scale=1.45,
               sub="then jump side-to-side over it as fast as you can")
        if d.waiting_tracking:
            text_c(img, "STEP INTO THE ARENA", W // 2, int(H * 0.42), sc(H, 1.0),
                   mix(RED, WHITE, pulse()), 2)
        else:
            countdown(img, W, H, d.countdown_s - (now - d.t_state), y_frac=0.46)
        return

    strip_x, strip_w = int(W * 0.10), int(W * 0.80)
    strip_y = int(H * 0.845) - int(sc(H, 26))

    # ---- hero band -----------------------------------------------------------
    if d.state == "work":
        left = max(0.0, d.work_s - (now - d.t_state))
        live = d.live_cadence_hz(now)
        avg = d.crossings / max(0.1, now - d.t_state)
        hero(img, W, H, str(d.crossings), "hops",
             caption=f"{left:.0f} s LEFT IN THE SET", y_frac=0.24, scale=2.8,
             color=YELLOW, thick=6)
        rate = "--" if live is None else f"{live:.1f}"
        text_c(img, f"{rate} /s now      set average {avg:.1f} /s", W // 2,
               int(H * 0.395), sc(H, 0.95), WHITE, 2, shadow=False)
    elif d.state == "rest":
        r = d.results[-1]
        hero(img, W, H, str(r["crossings"]), "hops",
             caption=f"SET {r['set']} TOTAL", y_frac=0.23, scale=2.6,
             color=GREEN, thick=5)
        drop = r.get("cadence_drop_pct")
        first, second = r.get("first_half_rate_hz"), r.get("second_half_rate_hz")
        if first is not None and second is not None:
            col = GREEN if (drop or 0) < 15 else (AMBER if (drop or 0) < 30 else RED)
            text_c(img, f"first half {first:.1f}/s   ->   second half {second:.1f}/s",
                   W // 2, int(H * 0.395), sc(H, 0.9), WHITE, 2, shadow=False)
            text_c(img, f"cadence held {100 - (drop or 0):.0f}%", W // 2,
                   int(H * 0.445), sc(H, 1.0), col, 2)
        else:
            text_c(img, f"{r['rate_hz']:.1f}/s average", W // 2, int(H * 0.395),
                   sc(H, 0.9), WHITE, 2, shadow=False)
        left = d.rest_s - (now - d.t_state)
        text_c(img, f"rest {max(0, left):.0f} s", W // 2, int(H * 0.485),
               sc(H, 0.8), STEEL, 2, shadow=False)
    elif d.state == "done":
        s = d.summary()
        hero(img, W, H, str(s["total_crossings"]), "hops",
             caption="TOTAL ACROSS THE SESSION", y_frac=0.23, scale=2.6,
             color=YELLOW, thick=5)
        if s["best_rate_hz"] is not None:
            text_c(img, f"best set {s['best_rate_hz']:.1f}/s   |   "
                        f"avg {s['avg_rate_hz']:.1f}/s", W // 2, int(H * 0.395),
                   sc(H, 0.9), WHITE, 2, shadow=False)
        if s.get("avg_cadence_drop_pct") is not None:
            drop = s["avg_cadence_drop_pct"]
            col = GREEN if drop < 15 else (AMBER if drop < 30 else RED)
            text_c(img, f"average cadence drop within a set {drop:.0f}%",
                   W // 2, int(H * 0.445), sc(H, 0.85), col, 2, shadow=False)

    # ---- stage: the athlete's own line and their lateral offset from it -------
    # Deliberately shallow. This is a confirmation that the tracker sees the
    # hops, not the point of the drill: the earlier full-height lane spent 40% of
    # the board on one line and one dot.
    lx = W // 2
    ly0, ly1 = int(H * 0.55), int(H * 0.72)
    panel(img, int(W * 0.10), ly0, int(W * 0.90), ly1, radius=int(sc(H, 12)),
          fill=(15, 16, 18), border=(38, 42, 46))
    glow(img, lx, (ly0 + ly1) // 2, int(sc(H, 70)), YELLOW, gain=0.22)
    cv2.line(img, (lx, ly0 + int(sc(H, 6))), (lx, ly1 - int(sc(H, 6))), YELLOW, 4,
             cv2.LINE_AA)
    am = ankle_mid_mm(joints)
    if am is not None and d.line is not None:
        off = max(-1.0, min(1.0, (am[1] - d.line) / 500.0))
        live_dot(img, int(lx + off * (W * 0.30)), (ly0 + ly1) // 2, H, WHITE,
                 radius=13, halo=0.5)

    # ---- cadence shape -------------------------------------------------------
    if d.state == "work":
        cadence_strip(img, strip_x, strip_y, strip_w, int(sc(H, 46)),
                      d.cross_times, d.t_state, d.work_s, H)
        left = max(0.0, d.work_s - (now - d.t_state))
        hbar(img, strip_x, strip_y + int(sc(H, 56)), strip_w, int(sc(H, 8)),
             1 - left / d.work_s, YELLOW)
    elif d.results:
        totals = [r["crossings"] for r in d.results]
        best = max(totals)
        history_bars(img, strip_x, strip_y, strip_w, int(sc(H, 46)), totals, H,
                     reference=best, label="hops per set, oldest -> newest",
                     tint=lambda v: GREEN if v >= best * 0.95 else (
                         WHITE if v >= best * 0.85 else AMBER))

    # ---- per-set record ------------------------------------------------------
    if d.results:
        best = max(r["crossings"] for r in d.results)
        rows = [(f"SET {r['set']:<2}", f"{r['crossings']} hops  {r['rate_hz']:.1f}/s",
                 YELLOW if r["crossings"] == best else WHITE)
                for r in d.results[-4:]]
        stat_rail(img, W, H, "PER SET", rows)
    note_right(img, W, H, "the line is measured from where you start each set")


#: Short labels for the corner rail — the full names are too wide for a column.
CORNER_ROWS = (("HIGH-LEFT", "H-L"), ("HIGH-RIGHT", "H-R"),
               ("LOW-LEFT", "L-L"), ("LOW-RIGHT", "L-R"))


def goal_frame(img, x0, y0, x1, y1, H):
    """Posts and crossbar, so the stage reads as a goal rather than a rectangle.

    The keeper has to recognise the shape instantly from a set position several
    metres away; a plain outline of the same weight as the corner targets does
    not do that.
    """
    post = max(3, int(sc(H, 7)))
    panel(img, x0, y0, x1, y1, radius=int(sc(H, 6)), fill=(15, 16, 18),
          border=None)
    # Net: sparse, low-contrast, purely to seat the corners in a real goal.
    step = max(int(sc(H, 34)), 8)
    for u in range(x0 + step, x1, step):
        cv2.line(img, (u, y0), (u, y1), (30, 33, 36), 1)
    for v in range(y0 + step, y1, step):
        cv2.line(img, (x0, v), (x1, v), (30, 33, 36), 1)
    cv2.line(img, (x0, y0), (x1, y0), WHITE, post, cv2.LINE_AA)   # crossbar
    cv2.line(img, (x0, y0), (x0, y1), WHITE, post, cv2.LINE_AA)   # left post
    cv2.line(img, (x1, y0), (x1, y1), WHITE, post, cv2.LINE_AA)   # right post
    cv2.line(img, (x0, y1), (x1, y1), (52, 56, 60), 2, cv2.LINE_AA)  # goal line


def draw_gk_save(img, d, now, joints, args, W, H):
    """Reaction save matrix: the cue must be unmistakable, the history readable.

    Two rules drive the layout. The cued corner is the ONLY thing that glows and
    pulses — an earlier version tinted every corner by its miss rate, so a red
    slab from three rounds ago competed with the live cue for attention. And the
    per-corner record lives in the rail, not inside the targets, because a
    keeper diving at a corner cannot read a table inside it.
    """
    gx0, gx1 = int(W * 0.20), int(W * 0.80)
    gy0, gy1 = int(H * 0.46), int(H * 0.83)
    goal_frame(img, gx0, gy0, gx1, gy1, H)

    cue = d.corner_name() if d.state in ("active", "result") else None
    per = d.per_corner()
    weakest = d.summary()["weakest_corner"]
    result = d.last_result[0] if (d.state == "result" and d.last_result) else None

    bw = int((gx1 - gx0) * 0.30)
    bh = int((gy1 - gy0) * 0.42)
    inset = max(3, int(sc(H, 6)))
    boxes = {
        "HIGH-LEFT": (gx0 + inset, gy0 + inset, gx0 + inset + bw, gy0 + inset + bh),
        "HIGH-RIGHT": (gx1 - inset - bw, gy0 + inset, gx1 - inset, gy0 + inset + bh),
        "LOW-LEFT": (gx0 + inset, gy1 - inset - bh, gx0 + inset + bw, gy1 - inset),
        "LOW-RIGHT": (gx1 - inset - bw, gy1 - inset - bh, gx1 - inset, gy1 - inset),
    }
    for name, (bx0, by0, bx1, by1) in boxes.items():
        cx_, cy_ = (bx0 + bx1) // 2, (by0 + by1) // 2
        fill, border, thick = PANEL, (38, 42, 46), 1
        if name == cue and d.state == "active":
            fill, border, thick = (10, 52, 60), YELLOW, 3
            left = 1.0
            if d.go_time is not None:
                left = max(0.0, 1.0 - (now - d.go_time) / max(0.05, d.cue_timeout_s))
            glow(img, cx_, cy_, int(bw * 0.62), YELLOW, 0.30 + 0.45 * left)
        elif name == cue and result == "save":
            fill, border, thick = (10, 46, 18), GREEN, 3
            glow(img, cx_, cy_, int(bw * 0.62), GREEN, 0.55)
        elif name == cue and result == "anticipated":
            # Not a save and not a miss: the wrist beat the reaction floor, so
            # there is nothing to be proud of and nothing to have missed.
            fill, border, thick = (12, 34, 46), AMBER, 3
        elif name == cue and result:
            fill, border, thick = (24, 16, 44), RED, 3
            glow(img, cx_, cy_, int(bw * 0.62), RED, 0.5)
        panel(img, bx0, by0, bx1, by1, radius=int(sc(H, 8)), fill=fill,
              border=border, thick=thick)

        # A corner label, never a table: hue for the live state, and the weakest
        # corner marked only once the session has enough rounds to mean it.
        short = dict(CORNER_ROWS)[name]
        if name == cue and d.state == "active":
            lcol = YELLOW
        elif name == cue and result == "save":
            lcol = GREEN
        elif name == cue and result:
            lcol = RED
        elif d.state == "done" and weakest == name:
            lcol = AMBER
        else:
            lcol = STEEL
        text_c(img, short, cx_, cy_ + int(sc(H, 10)),
               sc(H, 1.15 if name == cue else 0.95), lcol,
               3 if name == cue else 2)
        c = per[name]
        if c["rounds"] and not (name == cue and d.state == "result"):
            text_c(img, f"{c['saves']}/{c['rounds']}", cx_,
                   cy_ + int(sc(H, 44)), sc(H, 0.55), STEEL, 1, shadow=False)

    # Wrists: the keeper's hands, mapped into the goal by the same
    # self-calibrated bands the drill scores with.
    if d.state in ("set_wait", "armed", "active") and joints:
        for wn, col in (("left_wrist", (255, 200, 40)),
                        ("right_wrist", (40, 200, 255))):
            w = get_joint(joints, wn)
            if w is None:
                continue
            t = max(0.0, min(1.0, w[1] / d.arena_y))
            if d.flip:
                t = 1.0 - t
            u = int(gx0 + t * (gx1 - gx0))
            v = int(gy1 - max(0.0, min(1.0, w[2] / 2400.0)) * (gy1 - gy0))
            cv2.circle(img, (u, v), int(sc(H, 10)), col, -1, cv2.LINE_AA)
            cv2.circle(img, (u, v), int(sc(H, 10)), (0, 0, 0), 2, cv2.LINE_AA)

    # ---- hero band -----------------------------------------------------------
    # gk_save has no countdown state: the set position IS the calibration, so
    # arming and measuring the keeper's own shoulder/hip bands are the same step.
    if d.state == "set_wait":
        prompt(img, W, H, "GET SET - CENTER, HANDS READY", y_frac=0.26,
               scale=1.25, sub=f"hold it for {d.set_hold_s:.1f} s to arm")
    elif d.state == "armed":
        prompt(img, W, H, "ARMED", y_frac=0.26, scale=1.5, color=WHITE,
               sub="a corner lights after an unpredictable delay")
    elif d.state == "active":
        text_c(img, cue or "", W // 2, int(H * 0.28), sc(H, 2.6), YELLOW, 6)
        text_c(img, "PUNCH A WRIST INTO IT", W // 2, int(H * 0.355),
               sc(H, 0.6), STEEL, 2, shadow=False)
    elif d.state == "result" and d.last_result:
        kind, rt = d.last_result
        if kind == "save":
            hero(img, W, H, f"{rt:.2f}", "s", caption="CUE TO WRIST IN CORNER",
                 verdict=tier_of(rt), color=tier_of(rt)[1], y_frac=0.26,
                 scale=2.7)
        elif kind == "anticipated":
            hero(img, W, H, f"{rt:.2f}", "s", caption="TOO EARLY - NOT SCORED",
                 verdict=("ANTICIPATED", AMBER), color=AMBER, y_frac=0.26,
                 scale=2.7)
            text_c(img, "your wrist was there before the cue could be answered",
                   W // 2, int(H * 0.40), sc(H, 0.55), STEEL, 2, shadow=False)
        elif kind == "void":
            prompt(img, W, H, "RESET", y_frac=0.26, scale=1.5, color=AMBER,
                   sub="a corner was already covered - hands back to set")
        else:
            text_c(img, "MISS", W // 2, int(H * 0.27), sc(H, 2.4), RED, 6)
            text_c(img, f"no wrist in {cue} within {d.cue_timeout_s:.1f} s",
                   W // 2, int(H * 0.35), sc(H, 0.55), STEEL, 2, shadow=False)
    elif d.state == "done":
        s = d.summary()
        hero(img, W, H, f"{s['saves']}/{s['rounds_completed']}", "saves",
             caption=f"A WRIST IN THE CUED CORNER WITHIN {d.cue_timeout_s:.1f} s",
             y_frac=0.24, color=YELLOW, scale=2.4, thick=5)
        if s["avg_reaction_s"] is not None:
            word, tcol = tier_of(s["avg_reaction_s"])
            text_c(img, f"average {s['avg_reaction_s']:.2f} s   |   {word}",
                   W // 2, int(H * 0.375), sc(H, 0.9), tcol, 2)
        if s["weakest_corner"]:
            text_c(img, f"WORK ON: {s['weakest_corner']}", W // 2,
                   int(H * 0.42), sc(H, 0.7), AMBER, 2)

    # ---- per-corner record ---------------------------------------------------
    rows = []
    for name, short in CORNER_ROWS:
        c = per[name]
        rounds, saves = int(c["rounds"]), int(c["saves"])
        avg = c["avg_reaction_s"]
        tail = f"{avg:.2f} s" if avg else "-"
        if rounds == 0:
            color = STEEL
        elif saves == rounds:
            color = GREEN
        elif saves == 0:
            color = RED
        else:
            color = AMBER
        rows.append((f"{short:<5}", f"{saves}/{rounds}  {tail}", color))
    # Failure modes stay visible instead of being absorbed by the score: a
    # session that logged four "saves" at 34 ms should read as four early hands,
    # not as a personal best.
    totals = d.summary()
    if totals["anticipated"]:
        rows.append(("EARLY", f"  {totals['anticipated']}", AMBER))
    if totals["voided_rounds"]:
        rows.append(("VOID ", f"  {totals['voided_rounds']}", AMBER))
    stat_rail(img, W, H, "PER CORNER", rows)
    note_right(img, W, H, "HIGH/LOW bands measured from your own shoulder and hip")


def recovery_decay(img, x0, y0, width, height, recoveries, H, max_bars=24):
    """Per-rep get-up time, oldest to newest.

    This is the whole point of a conditioning drill: the rep count says the work
    was done, the recovery trend says what it cost. Bars are scaled to the
    athlete's OWN first rep, so the reference is their fresh state rather than a
    population norm, and a rep taking twice as long as their first is visibly
    twice the bar.
    """
    if not recoveries:
        text(img, "recovery per rep - first rep pending",
             (x0, y0 + height - int(sc(H, 8))), sc(H, 0.5), STEEL, 1,
             shadow=False)
        return
    shown = recoveries[-max_bars:]
    ref = recoveries[0] if recoveries[0] > 0 else max(shown)
    worst = max(max(shown), ref * 2.0)
    slot = width / max(1, len(shown))
    bw = max(3, int(slot * 0.68))
    for i, val in enumerate(shown):
        h = max(2, int(height * min(1.0, val / worst)))
        cx_ = int(x0 + slot * (i + 0.5))
        ratio = val / ref if ref > 0 else 1.0
        col = GREEN if ratio <= 1.25 else (AMBER if ratio <= 1.6 else RED)
        cv2.rectangle(img, (cx_ - bw // 2, y0 + height - h),
                      (cx_ + bw // 2, y0 + height), col, -1)
    # The reference line is the first rep, drawn so drift off it is readable.
    ry = y0 + height - int(height * min(1.0, ref / worst))
    cv2.line(img, (x0, ry), (x0 + width, ry), STEEL, 1, cv2.LINE_AA)
    text(img, f"rep 1 = {ref:.2f}s", (x0 + width + int(sc(H, 8)),
                                      ry + int(sc(H, 5))),
         sc(H, 0.5), STEEL, 1, shadow=False)
    text(img, "recovery per rep, oldest -> newest",
         (x0, y0 - int(sc(H, 10))), sc(H, 0.5), STEEL, 1, shadow=False)


def draw_gk_updown(img, d, now, joints, args, W, H):
    """Down-up conditioning: reps are the work, the recovery trend is the cost."""
    if d.state == "countdown":
        prompt(img, W, H, "STAND TALL", y_frac=0.24, scale=1.4,
               sub="measuring your set height")
        if d.waiting_tracking:
            text_c(img, "STEP INTO THE ARENA", W // 2, int(H * 0.42), sc(H, 1.0),
                   mix(RED, WHITE, pulse()), 2)
        else:
            countdown(img, W, H, d.countdown_s - (now - d.t_state), y_frac=0.46)
        note_right(img, W, H, "DOWN/SET lines measured from your own height")
        return

    # ---- hero band -----------------------------------------------------------
    if d.state == "work":
        left = max(0.0, d.duration_s - (now - d.t_state))
        hero(img, W, H, str(d.reps), "reps", caption=f"{left:.0f} s LEFT IN THE BLOCK",
             y_frac=0.24, scale=2.8, color=YELLOW, thick=6)
        cue = "GO DOWN" if d.phase == "up" else "GET UP"
        text_c(img, cue, W // 2, int(H * 0.395), sc(H, 1.3),
               mix(WHITE, YELLOW, pulse()), 3)
    else:
        s = d.summary()
        hero(img, W, H, str(s["reps"]), "down-ups", y_frac=0.23, scale=2.6,
             color=YELLOW, thick=5,
             caption=None if s["avg_recovery_s"] is None else
             f"AVERAGE GET-UP {s['avg_recovery_s']:.2f} s")
        if len(d.recoveries) > 1:
            first, last = d.recoveries[0], d.recoveries[-1]
            drift = (last / first - 1.0) * 100.0 if first > 0 else 0.0
            col = GREEN if drift <= 25 else (AMBER if drift <= 60 else RED)
            text_c(img, f"first rep {first:.2f} s   ->   last rep {last:.2f} s"
                        f"   ({drift:+.0f}%)", W // 2, int(H * 0.40),
                   sc(H, 0.85), col, 2, shadow=False)
        if s["voided_reps"]:
            stat_rail(img, W, H, "VOIDED",
                      [("TOO FAST", f"  {s['voided_reps']}", AMBER)])

    # ---- stage: pelvis height against the keeper's own DOWN/SET lines --------
    mx0 = W // 2 - int(W * 0.038)
    mx1 = W // 2 + int(W * 0.038)
    my0, my1 = int(H * 0.47), int(H * 0.765)
    top_z = (d.stand_z or 1000.0) * 1.15
    span = max(1.0, top_z * 0.5)

    def frac_of(z):
        # height_column works in signed fractions about mid-gauge, so map the
        # absolute pelvis height onto that scale via the gauge's own midpoint.
        return (z - top_z * 0.5) / span

    marks = ()
    if d.stand_z:
        marks = ((frac_of(d.down_thresh), RED, "DOWN"),
                 (frac_of(d.up_thresh), GREEN, "SET"))
    p = pelvis_mm(joints)
    # WHITE, not the phase colour: the pelvis height is a live MEASUREMENT, and a
    # yellow column read as a cue while the cue is already the GO DOWN / GET UP
    # prompt. It also swamped the DOWN/SET threshold lines drawn over it.
    height_column(img, mx0, my0, mx1, my1, H,
                  None if p is None else frac_of(p[2]), marks=marks,
                  show_mid=False, fill_from="bottom", live_color=WHITE)

    # ---- recovery decay ------------------------------------------------------
    strip_x, strip_w = int(W * 0.12), int(W * 0.72)
    strip_y = int(H * 0.845) - int(sc(H, 26))
    recovery_decay(img, strip_x, strip_y, strip_w, int(sc(H, 46)), d.recoveries, H)

    # ---- per-rep record ------------------------------------------------------
    if d.recoveries:
        ref = d.recoveries[0]
        rows = []
        for i, val in list(enumerate(d.recoveries))[-4:]:
            ratio = val / ref if ref > 0 else 1.0
            col = GREEN if ratio <= 1.25 else (AMBER if ratio <= 1.6 else RED)
            rows.append((f"REP {i + 1:<2}", f"{val:.2f} s", col))
        stat_rail(img, W, H, "GET-UP TIME", rows)
    note_right(img, W, H, "DOWN/SET lines measured from your own height")


def draw_reaction_zones(img, d, now, joints, args, W, H):
    """Projector board for pelvis-scored LEFT/CENTER/RIGHT reactions.

    Built for a dim, distant projector image: the hero value is ~11% of frame
    height, nothing meaningful sits in the outer 4%, and no distinction is
    carried by hue alone — the cued zone is also the only one that glows and the
    only one with a heavy border.
    """
    pelvis = pelvis_mm(joints)
    player_zone = None if pelvis is None else d.side_of(pelvis[1])
    cued = d.state in ("active", "result")

    # Zone band. Kept inside a 6% side margin so a keystoned projector cannot
    # clip a target off the edge of the image.
    band_x0, band_x1 = int(W * 0.06), int(W * 0.94)
    band_y0, band_y1 = int(H * 0.56), int(H * 0.82)
    zone_w = (band_x1 - band_x0) / 3.0

    for zone, name in enumerate(d.ZONE_NAMES):
        x0 = int(band_x0 + zone * zone_w)
        x1 = int(band_x0 + (zone + 1) * zone_w) - 6
        cx, cy = (x0 + x1) // 2, (band_y0 + band_y1) // 2
        is_target = cued and d.target == zone
        result = d.last_result[0] if (d.state == "result" and d.last_result) else None

        fill, border, thick = PANEL, (38, 42, 46), 1
        if is_target and d.state == "active":
            fill, border, thick = (8, 50, 58), YELLOW, 3
        elif is_target and result == "hit":
            fill, border, thick = (10, 46, 18), GREEN, 3
        elif is_target and result in ("miss", "void"):
            fill, border, thick = (24, 16, 44), RED, 3
        panel(img, x0, band_y0, x1, band_y1, radius=int(H * 0.018),
              fill=fill, border=border, thick=thick)

        if is_target:
            # Intensity carries the cue's urgency (time left before timeout),
            # so the glow is a readout, not decoration.
            if d.state == "active" and d.go_time is not None:
                left = max(0.0, 1.0 - (now - d.go_time) / max(0.05, d.cue_timeout_s))
            else:
                left = 1.0
            hue = YELLOW if d.state == "active" else (
                GREEN if result == "hit" else RED)
            glow(img, cx, cy, int(zone_w * 0.55), hue, 0.30 + 0.45 * left)

        # Yellow means "the system is asking you for something", so it belongs to
        # the live cue only. Once the round has resolved the label carries the
        # verdict colour instead — a cue must never read as a result.
        if is_target and d.state == "active":
            label_color = YELLOW
        elif is_target and result == "hit":
            label_color = GREEN
        elif is_target and result in ("miss", "void"):
            label_color = RED
        else:
            label_color = STEEL
        text_c(img, name, cx, band_y0 + int(H * 0.075),
               sc(H, 1.05 if is_target else 0.85),
               label_color, 3 if is_target else 2)
        # The dot marks the zone CENTRE — a label for the cue, never a required
        # position. Scoring only needs zone entry, which keeps the athlete a full
        # zone width off the wall at the outer boundary.
        cv2.circle(img, (cx, band_y1 - int(H * 0.035)), max(3, int(H * 0.006)),
                   YELLOW if is_target else (47, 52, 56), -1)

    # Live pelvis, mapped along the real arena width.
    if pelvis is not None:
        t = min(max(pelvis[1] / max(1.0, d.arena_y_mm), 0.0), 1.0)
        if getattr(args, "flip", False):
            t = 1.0 - t
        px = int(band_x0 + t * (band_x1 - band_x0))
        py = band_y1 - int(H * 0.035)
        glow(img, px, py, int(H * 0.055), WHITE, 0.5)
        cv2.circle(img, (px, py), max(4, int(H * 0.011)), WHITE, -1)

    # ---- hero band -----------------------------------------------------------
    if d.state == "set_wait":
        msg = "STEP INTO A ZONE" if player_zone is None else "HOLD YOUR ZONE TO ARM"
        text_c(img, msg, W // 2, int(H * 0.26), sc(H, 1.3),
               mix(WHITE, YELLOW, pulse()), 3)
        text_c(img, f"{d.arm_hold_s:.1f} s", W // 2, int(H * 0.34),
               sc(H, 0.6), STEEL, 2)
    elif d.state == "armed":
        text_c(img, "ARMED", W // 2, int(H * 0.26), sc(H, 1.5), WHITE, 4)
        text_c(img, "cue fires after an unpredictable delay", W // 2,
               int(H * 0.34), sc(H, 0.55), STEEL, 2)
    elif d.state == "active":
        text_c(img, "GO", W // 2, int(H * 0.30), sc(H, 3.4), YELLOW, 7)
    elif d.state == "result" and d.last_result:
        result, reaction = d.last_result
        if result == "hit":
            word, color = tier_of(reaction)
            value_unit(img, f"{reaction:.2f}", "s", W // 2, int(H * 0.28),
                       2.9, color, H, thick=6)
            text_c(img, "SECONDS TO ZONE", W // 2, int(H * 0.345),
                   sc(H, 0.5), STEEL, 1, shadow=False)
            text_c(img, word, W // 2, int(H * 0.415), sc(H, 0.95), color, 3)
        elif result == "miss":
            text_c(img, "MISS", W // 2, int(H * 0.28), sc(H, 2.4), RED, 6)
            text_c(img, f"no zone entry within {d.cue_timeout_s:.1f} s",
                   W // 2, int(H * 0.36), sc(H, 0.55), STEEL, 2)
        else:
            text_c(img, "VOID", W // 2, int(H * 0.28), sc(H, 2.2), RED, 6)
            text_c(img, "tracking lost - round not counted", W // 2,
                   int(H * 0.36), sc(H, 0.55), STEEL, 2)
    elif d.state == "done":
        s = d.summary()
        value_unit(img, f"{s['hits_in_timeout']}/{s['rounds_completed']}",
                   "hits", W // 2, int(H * 0.27), 2.4, YELLOW, H, thick=5)
        if s["avg_reaction_s"] is not None:
            value_unit(img, f"{s['avg_reaction_s']:.2f}", "s avg", W // 2,
                       int(H * 0.38), 1.3, WHITE, H, thick=3)
        if s["weakest_zone"]:
            text_c(img, f"WORK ON: {s['weakest_zone']}", W // 2,
                   int(H * 0.45), sc(H, 0.7), AMBER, 2)

    # ---- per-zone history: the diagnostic that makes this a session ----------
    stats = d.per_zone()
    if stats:
        y = int(H * 0.13)
        text(img, "PER ZONE", (int(W * 0.045), y), sc(H, 0.45), STEEL, 1, shadow=False)
        for name in d.ZONE_NAMES:
            y += int(H * 0.045)
            row = stats.get(name) or {}
            rounds = int(row.get("rounds") or 0)
            hits = int(row.get("hits") or 0)
            avg = row.get("avg_reaction_s")
            if rounds == 0:
                color, tail = STEEL, "-"
            elif hits == rounds:
                color, tail = GREEN, f"{avg:.2f} s" if avg else "-"
            elif hits == 0:
                color, tail = RED, "-"
            else:
                color, tail = AMBER, f"{avg:.2f} s" if avg else "-"
            text(img, f"{name:<7}{hits}/{rounds}  {tail}",
                 (int(W * 0.045), y), sc(H, 0.5), color, 2, shadow=False)

    # Zone geometry, so the space the drill is using is never implicit.
    note = (f"zone width {d.arena_y_mm / 3.0:.0f} mm"
            f"   boundary {d.arena_y_mm / 3.0:.0f} mm from wall")
    (tw, _), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, sc(H, 0.45), 1)
    text(img, note, (W - tw - int(W * 0.045), int(H * 0.13)), sc(H, 0.45), STEEL, 1,
         shadow=False)


def height_column(img, x0, y0, x1, y1, H, frac, marks=(), label=None,
                  show_mid=True, fill_from="mid", live_color=None):
    """A vertical gauge of the athlete's own height.

    `frac` is signed and normalised about the gauge's midpoint: 0 is mid, +1 the
    top. Two modes, because two drills measure different things off it:

    * ``fill_from="mid"`` with ``show_mid`` — the mid line is the athlete's own
      standing reference and the fill is the deviation from it (cmj: rise).
    * ``fill_from="bottom"`` without it — the fill is absolute height and the
      meaning lives in the marked thresholds (gk_updown: DOWN/SET). Drawing an
      arbitrary mid line here put a second rule next to the DOWN line and read
      as a threshold that does not exist.
    """
    panel(img, x0, y0, x1, y1, radius=int(sc(H, 8)), fill=(15, 16, 18),
          border=(38, 42, 46))
    mid = (y0 + y1) // 2

    def row(value):
        return int(mid - max(-1.0, min(1.0, value)) * (y1 - y0) / 2)

    # Fill first, THEN the thresholds: drawn the other way round, a tall fill
    # painted straight over the DOWN/SET lines that give it meaning.
    if frac is not None:
        v = row(frac)
        color = live_color or (GREEN if frac > 0.05 else
                               (AMBER if frac < -0.05 else WHITE))
        anchor = mid if fill_from == "mid" else y1 - int(sc(H, 3))
        cv2.rectangle(img, (x0 + int(sc(H, 6)), min(anchor, v)),
                      (x1 - int(sc(H, 6)), max(anchor, v)),
                      mix((15, 16, 18), color, 0.22), -1)
    for value, color, name in marks:
        v = row(value)
        cv2.line(img, (x0 + int(sc(H, 3)), v), (x1 - int(sc(H, 3)), v), color, 2,
                 cv2.LINE_AA)
        text(img, name, (x1 + int(sc(H, 10)), v + int(sc(H, 6))), sc(H, 0.45),
             color, 1, shadow=False)
    if frac is not None:
        v = row(frac)
        color = live_color or (GREEN if frac > 0.05 else
                               (AMBER if frac < -0.05 else WHITE))
        glow(img, (x0 + x1) // 2, v, int(sc(H, 40)), color, gain=0.35)
        cv2.line(img, (x0 + int(sc(H, 3)), v), (x1 - int(sc(H, 3)), v), color, 3,
                 cv2.LINE_AA)
    if show_mid:
        cv2.line(img, (x0 - int(sc(H, 8)), mid), (x1 + int(sc(H, 8)), mid), STEEL,
                 2, cv2.LINE_AA)
        if label:
            text(img, label, (x1 + int(sc(H, 12)), mid + int(sc(H, 6))),
                 sc(H, 0.45), STEEL, 1, shadow=False)


def draw_cmj(img, d, now, joints, args, W, H):
    """Load monitoring: the hero is the rise, the story is the drop-off."""
    pelvis = pelvis_mm(joints)
    rises = d.rises()
    s = d.summary()

    if d.state == "countdown":
        prompt(img, W, H, "STAND TALL AND STILL", y_frac=0.26, scale=1.4,
               sub="measuring your standing pelvis height")
        countdown(img, W, H, d.countdown_s - (now - d.t_state), y_frac=0.44)
        note_right(img, W, H, "pelvis rise, not force-plate jump height")
        return

    # ---- hero band -----------------------------------------------------------
    best = max(rises) if rises else None
    if d.state == "done":
        hero(img, W, H, "--" if best is None else f"{best:.0f}", "mm",
             caption="BEST PELVIS RISE OF THE SET", y_frac=0.25, scale=2.7,
             color=YELLOW, thick=5)
        if s["drop_off_pct"] is not None:
            color = GREEN if s["drop_off_pct"] > -5 else (
                AMBER if s["drop_off_pct"] > -12 else RED)
            text_c(img, f"drop-off {s['drop_off_pct']:+.0f}% across the set",
                   W // 2, int(H * 0.40), sc(H, 0.9), color, 2)
    elif best is not None:
        hero(img, W, H, f"{best:.0f}", "mm", caption="BEST SO FAR", y_frac=0.25,
             scale=2.7, thick=5)
        last = rises[-1]
        col = GREEN if last >= best * 0.95 else (
            AMBER if last >= best * 0.88 else RED)
        text_c(img, f"last jump {last:.0f} mm", W // 2, int(H * 0.395),
               sc(H, 0.85), col, 2, shadow=False)
    else:
        prompt(img, W, H, "JUMP", y_frac=0.26, scale=2.4,
               sub="dip and drive as high as you can")

    # ---- stage: the live pelvis against the athlete's own standing height -----
    # The gauge stops above the session strip: a column that reached the bottom
    # of the stage was overdrawn by the per-jump bars.
    col_w = int(W * 0.075)
    col_x = W // 2 - col_w // 2
    top, bot = int(H * 0.47), int(H * 0.765)
    frac = None
    if d.stand_z and pelvis is not None:
        frac = (pelvis[2] - d.stand_z) / max(1.0, d.stand_z * 0.45)
    marks = ()
    if best is not None and d.stand_z:
        marks = ((best / max(1.0, d.stand_z * 0.45), GREEN, f"best {best:.0f}"),)
    height_column(img, col_x, top, col_x + col_w, bot, H, frac, marks=marks,
                  label="STAND")

    # ---- per-jump decay ------------------------------------------------------
    third = max(1, len(rises) // 3)
    base = fmean_safe(rises[:third]) if rises else None
    history_bars(img, int(W * 0.10), int(H * 0.845) - int(sc(H, 26)),
                 int(W * 0.80), int(sc(H, 46)), rises, H, reference=base,
                 label=f"pelvis rise per jump  |  {s['jumps_completed']}/"
                       f"{s['jumps_target']} jumps",
                 tint=lambda v: GREEN if base and v >= base * 0.95 else (
                     AMBER if base and v >= base * 0.88 else RED))

    # ---- per-jump record -----------------------------------------------------
    rows = [(f"JUMP {i + 1:<2}", f"{v:.0f} mm",
             YELLOW if v == best else WHITE)
            for i, v in list(enumerate(rises))[-4:]]
    if s["implausible_jumps"]:
        # A rise past the elite range is a measurement fault; it stays on screen
        # so the coach knows a jump was discarded rather than never happened.
        rows.append(("FAULT", f"  {s['implausible_jumps']}", AMBER))
    if rows:
        stat_rail(img, W, H, "PER JUMP", rows)
    note_right(img, W, H, "pelvis rise, not force-plate jump height")


def draw_hop_symmetry(img, d, now, joints, args, W, H):
    """Return-to-play screening: two bars, one index, both raw distances."""
    legs = d.per_leg()
    s = d.summary()

    if d.state == "countdown":
        prompt(img, W, H, f"STAND ON YOUR {d.leg().upper()} LEG", y_frac=0.26,
               scale=1.4, sub="hop forward and stick the landing")
        countdown(img, W, H, d.countdown_s - (now - d.t_state), y_frac=0.46)
        note_right(img, W, H, "distance from a fixed start line, not a stride count")
        return

    lsi = s["limb_symmetry_pct"]
    if lsi is not None:
        color = GREEN if lsi >= 90.0 else (AMBER if lsi >= 80.0 else RED)
        verdict = None
        if s["weaker_leg"]:
            verdict = (f"WEAKER: {s['weaker_leg'].upper()}", color)
        hero(img, W, H, f"{lsi:.0f}", "% symmetry", y_frac=0.25, scale=2.8,
             color=color,
             caption="reference 90% - a screening signal, not clearance",
             verdict=verdict)
    else:
        prompt(img, W, H, f"HOP ON YOUR {d.leg().upper()} LEG", y_frac=0.26,
               scale=1.6, sub="land and hold it still")

    # Both raw distances side by side — symmetry can be met while both are weak.
    widest = max([legs[leg]["best_mm"] or 0.0 for leg in d.LEGS] + [1.0])
    bar_w = int(W * 0.30)
    for i, leg in enumerate(d.LEGS):
        y = int(H * 0.48) + i * int(H * 0.13)
        x0 = int(W * 0.20)
        best = legs[leg]["best_mm"]
        active = (d.leg() == leg and d.state in ("arm", "hop"))
        panel(img, x0, y, x0 + bar_w, y + int(H * 0.085), radius=6,
              fill=(16, 18, 21), border=YELLOW if active else (36, 40, 44),
              thick=2 if active else 1)
        if best:
            fill_w = int(bar_w * (best / widest))
            weaker = s["weaker_leg"] == leg
            cv2.rectangle(img, (x0 + 2, y + 2),
                          (x0 + max(4, fill_w) - 2, y + int(H * 0.085) - 2),
                          AMBER if weaker else GREEN, -1)
        text(img, leg.upper(), (int(W * 0.115), y + int(H * 0.06)),
             sc(H, 0.7), WHITE if active else STEEL, 2)
        label = "-" if not best else f"{best:.0f} mm"
        label_x = x0 + bar_w + int(W * 0.02)
        text(img, label, (label_x, y + int(H * 0.06)), sc(H, 0.75), WHITE, 2)
        stab = [r["stabilise_s"] for r in d.results if r["leg"] == leg]
        if stab:
            # Place the secondary readout past the measured width of the value,
            # not at a guessed offset — "1400 mm" is wider than "-".
            (lw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX,
                                         sc(H, 0.75), 2)
            text(img, f"stabilise {fmean_safe(stab):.1f} s",
                 (label_x + lw + int(W * 0.025), y + int(H * 0.06)),
                 sc(H, 0.5), STEEL, 1, shadow=False)

    # ---- every hop, coloured by limb: the raw data behind the index -----------
    strip_x, strip_w = int(W * 0.10), int(W * 0.80)
    strip_y = int(H * 0.845) - int(sc(H, 26))
    hops = [r["distance_mm"] for r in d.results]
    # Each bar is tagged L / R as well as coloured: which limb hopped is a
    # category, and a category must never be carried by hue alone on a board an
    # athlete reads from three metres away.
    history_bars(
        img, strip_x, strip_y, strip_w, int(sc(H, 46)), hops, H,
        colors=[GREEN if r["leg"] == "left" else AMBER for r in d.results],
        tags=[r["leg"][0].upper() for r in d.results],
        label=f"every hop, oldest -> newest  |  {s['hops_completed']}/"
              f"{s['hops_target']} hops  |  L left leg, R right leg")

    # ---- per-leg record ------------------------------------------------------
    rows = []
    for leg in d.LEGS:
        row = legs[leg]
        best = row["best_mm"]
        weaker = s["weaker_leg"] == leg
        rows.append((f"{leg.upper():<6}",
                     f"{row['hops']} hops  " + ("-" if not best else f"{best:.0f} mm"),
                     AMBER if weaker else (WHITE if row["hops"] else STEEL)))
    stat_rail(img, W, H, "PER LEG", rows)
    note_right(img, W, H, "both limbs can be weak at 100% - read the distances")


def draw_reactive_cut(img, d, now, joints, args, W, H):
    """The drill timing gates cannot run: the cue arrives mid-stride."""
    pelvis = pelvis_mm(joints)
    s = d.summary()

    # Run-up lane, seen from above: start line, trigger, and the two gates.
    lane_y0, lane_y1 = int(H * 0.52), int(H * 0.84)
    lx0, lx1 = int(W * 0.08), int(W * 0.92)
    mid_y = (lane_y0 + lane_y1) // 2
    panel(img, lx0, lane_y0, lx1, lane_y1, radius=int(H * 0.016),
          fill=(15, 17, 20), border=(34, 38, 42))
    # The cue line is a LANDMARK, so it is only yellow while it is about to fire
    # or has just fired. Leaving it yellow through the result kept the board
    # asking for something after the rep was over (the shuttle's START line is
    # white for the same reason).
    trig_x = int(lx0 + (lx1 - lx0) * 0.5)
    trig_col = YELLOW if d.state in ("approach", "active") else STEEL
    cv2.line(img, (trig_x, lane_y0 + 4), (trig_x, lane_y1 - 4), trig_col, 2)
    text(img, "CUE", (trig_x - int(W * 0.014), lane_y0 - int(H * 0.012)),
         sc(H, 0.45), trig_col, 1, shadow=False)

    # A cue colour must never survive into the result: yellow is the ask, and the
    # resolved gate carries the verdict instead (same rule as the zone board).
    outcome = d.last_result[0] if (d.state == "result" and d.last_result) else None
    lit_color = YELLOW if d.state == "active" else (
        GREEN if outcome == "hit" else RED)
    for side, gy in (("LEFT", lane_y0 + int(H * 0.05)),
                     ("RIGHT", lane_y1 - int(H * 0.05))):
        lit = d.target == side and d.state in ("active", "result")
        cv2.line(img, (trig_x, gy), (lx1 - 8, gy),
                 lit_color if lit else (44, 48, 52), 3 if lit else 1)
        text(img, side, (lx1 - int(W * 0.07), gy - int(H * 0.012)),
             sc(H, 0.55), lit_color if lit else STEEL, 2 if lit else 1,
             shadow=False)
        if lit:
            # Radius kept inside the lane — a larger halo spilled past the panel
            # and read as a smudge on the background.
            glow(img, (trig_x + lx1) // 2, gy, int(H * 0.055), lit_color, 0.45)

    if pelvis is not None:
        t = min(max(pelvis[0] / max(1.0, d.arena_x_mm), 0.0), 1.0)
        u = min(max(pelvis[1] / max(1.0, d.arena_y_mm), 0.0), 1.0)
        live_dot(img, int(lx0 + t * (lx1 - lx0)),
                 int(lane_y0 + u * (lane_y1 - lane_y0)), H, WHITE, radius=11,
                 halo=0.5)

    if d.state == "set_wait":
        prompt(img, W, H, "BEHIND THE START LINE", y_frac=0.26, scale=1.3,
               sub="the direction comes only at the cue line")
    elif d.state == "approach":
        text_c(img, "GO", W // 2, int(H * 0.28), sc(H, 3.0), WHITE, 7)
        text_c(img, "sprint at the cue line", W // 2, int(H * 0.355),
               sc(H, 0.55), STEEL, 2, shadow=False)
    elif d.state == "active":
        text_c(img, d.target, W // 2, int(H * 0.28), sc(H, 3.2), YELLOW, 8)
        text_c(img, "CUT NOW", W // 2, int(H * 0.355), sc(H, 0.6), STEEL, 2,
               shadow=False)
    elif d.state == "result" and d.last_result:
        result, execution = d.last_result
        if result == "hit":
            decision = d.results[-1]["decision_s"] or 0.0
            # Decision and execution train differently, so they are never added
            # into one number: the hero is the reaction to the cue, the caption
            # is the movement that followed it.
            hero(img, W, H, f"{decision:.2f}", "s", y_frac=0.25, scale=2.6,
                 color=tier_of(decision)[1], verdict=tier_of(decision),
                 caption="CUE TO FIRST COMMITTED STEP"
                         + ("" if not execution
                            else f"   |   GATE IN {execution:.2f} s"))
        elif result == "error":
            text_c(img, "WRONG WAY", W // 2, int(H * 0.27), sc(H, 2.2), RED, 6)
            text_c(img, f"the cue was {d.results[-1]['cued']} - "
                        f"recorded, not discarded", W // 2, int(H * 0.35),
                   sc(H, 0.55), STEEL, 2, shadow=False)
        elif result == "miss":
            text_c(img, "NO CUT", W // 2, int(H * 0.27), sc(H, 2.2), RED, 6)
            text_c(img, "no committed lateral movement after the cue", W // 2,
                   int(H * 0.35), sc(H, 0.55), STEEL, 2, shadow=False)
        else:
            text_c(img, "VOID", W // 2, int(H * 0.27), sc(H, 2.0), RED, 6)
            text_c(img, "tracking lost - rep not counted", W // 2,
                   int(H * 0.35), sc(H, 0.55), STEEL, 2, shadow=False)
    elif d.state == "done":
        hero(img, W, H, f"{s['correct_cuts']}/{s['reps_completed']}", "correct",
             y_frac=0.23, scale=2.4, color=YELLOW, thick=5,
             caption=None if s["avg_decision_s"] is None else
             f"AVERAGE DECISION {s['avg_decision_s']:.2f} s")
        if s["avg_execution_s"] is not None:
            text_c(img, f"average gate clearance {s['avg_execution_s']:.2f} s",
                   W // 2, int(H * 0.395), sc(H, 0.85), WHITE, 2, shadow=False)
        if s["wrong_way_cuts"]:
            text_c(img, f"{s['wrong_way_cuts']} wrong-way commit(s)", W // 2,
                   int(H * 0.44), sc(H, 0.75), RED, 2, shadow=False)

    # ---- per-side record -----------------------------------------------------
    rows = []
    for side in d.SIDES:
        row = s["per_side"][side]
        avg = row["avg_decision_s"]
        color = STEEL if not row["reps"] else (
            GREEN if row["correct"] == row["reps"] else AMBER)
        tail = f"{avg:.2f} s" if avg else "-"
        rows.append((f"{side:<6}", f"{row['correct']}/{row['reps']}  {tail}",
                     color))
    if s["wrong_way_cuts"]:
        rows.append(("WRONG ", str(s["wrong_way_cuts"]), RED))
    if s["voided_reps"]:
        rows.append(("VOID  ", str(s["voided_reps"]), AMBER))
    stat_rail(img, W, H, "PER SIDE", rows)
    note = ("cue fires at the commitment point"
            if not s["slower_side"] else f"slower side {s['slower_side']}")
    note_right(img, W, H, note)


def fmean_safe(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


DRAWERS = {
    "balance": draw_balance,
    "shuttle": draw_shuttle,
    "line_hops": draw_line_hops,
    "gk_save": draw_gk_save,
    "gk_updown": draw_gk_updown,
    "reaction_zones": draw_reaction_zones,
    "cmj": draw_cmj,
    "hop_symmetry": draw_hop_symmetry,
    "reactive_cut": draw_reactive_cut,
}


def progress_text(d):
    if d.kind == "balance":
        return f"HOLD {min(d.hold_idx + 1, d.holds)}/{d.holds}"
    if d.kind == "shuttle":
        return f"REP {min(d.completed + 1, d.reps)}/{d.reps}"
    if d.kind == "line_hops":
        return f"SET {min(d.set_idx + 1, d.sets)}/{d.sets}"
    if d.kind == "gk_save":
        return f"ROUND {min(d.round_idx + 1, d.rounds)}/{d.rounds}"
    if d.kind == "gk_updown":
        return f"{d.duration_s:.0f}s BLOCK"
    if d.kind == "reaction_zones":
        return f"ROUND {min(d.round_idx + 1, d.rounds)}/{d.rounds}"
    if d.kind == "cmj":
        return f"JUMP {min(d.completed + 1, d.jumps)}/{d.jumps}"
    if d.kind == "hop_symmetry":
        return f"HOP {min(d.attempt + 1, d.hops_per_leg * 2)}/{d.hops_per_leg * 2}"
    if d.kind == "reactive_cut":
        return f"REP {min(d.rep_idx + 1, d.reps)}/{d.reps}"
    return ""


def evidence_rail(img, W, H, quality, observed_hz, min_cameras=6):
    """The honesty rail: the capture context this session will be judged on,
    reported WHILE it is running so a degraded run is visible before it becomes
    a record. Nothing here is green unless it was actually verified — presence
    of a file is not health, and an open camera is not a good camera.
    """
    top = H - px(H, 34)
    baseline = H - px(H, 11)
    margin = px(H, 22)
    cv2.rectangle(img, (0, top), (W, H), BAR_BG, -1)
    cv2.line(img, (0, top), (W, top), (34, 40, 44), 1)
    x = margin
    fs = sc(H, 0.46)

    def cell(label, color):
        nonlocal x
        text(img, label, (x, baseline), fs, color, 1, shadow=False)
        (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        x += tw + int(sc(H, 26))

    if not quality:
        # No capture context at all: say so rather than implying a clean run.
        cell("CAPTURE CONTEXT UNAVAILABLE", AMBER)
    else:
        opened = len(quality.get("opened_camera_roles") or ())
        configured = len(quality.get("configured_camera_roles") or ()) or opened
        degraded = opened < int(min_cameras)
        cell(f"CAMERAS {opened}/{configured}", AMBER if degraded else GREEN)
        ratio = quality.get("pose_valid_frame_ratio")
        if ratio is not None:
            cell(f"VALID {ratio * 100:.0f}%", AMBER if ratio < 0.90 else GREEN)
        cams = quality.get("median_reported_joint_cameras")
        if cams is not None:
            cell(f"MEDIAN {cams:.0f} CAMS/JOINT", STEEL)
        fingerprint = str(quality.get("calibration_fingerprint") or "")
        if fingerprint.startswith("sha256:"):
            cell(f"CALIB {fingerprint[7:15]}", STEEL)
        if degraded:
            cell("DEGRADED", AMBER)

    # Timing resolution, derived from the OBSERVED packet rate rather than an
    # assumed capture rate. A reaction time is quantised by one packet interval.
    if observed_hz and observed_hz > 0.5:
        note = f"+/-{0.5 / observed_hz:.2f} s @ {observed_hz:.0f} Hz"
        (tw, _), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        text(img, note, (W - tw - margin, baseline), fs, STEEL, 1, shadow=False)


def render(drill, now, joints, age, athlete, session_t0, paused, args,
           quality=None, observed_hz=None):
    W, H = args.width, args.height
    img = _bg(W, H)
    # top bar — chrome scales with the board, like the text inside it
    margin, baseline = px(H, 22), px(H, BAR_BASELINE)
    cv2.rectangle(img, (0, 0), (W, px(H, BAR_H)), BAR_BG, -1)
    cv2.line(img, (0, px(H, BAR_RULE)), (W, px(H, BAR_RULE)), YELLOW, 2)
    text(img, drill.title, (margin, baseline), sc(H, 1.0), YELLOW, 2)
    if athlete:
        name_text_c(img, athlete, W // 2, baseline, sc(H, 0.9), WHITE, 2)
    clock = now - session_t0
    # Right-align from the MEASURED width. A fixed `W - 330` offset was sized at
    # 1280x720 while the text scales with H, so at fullscreen the clock ran off
    # the screen — 109 px past the edge on "ROUND 20/20" at 1920x1080.
    progress = (f"{progress_text(drill)}   "
                f"{int(clock // 60):02d}:{int(clock % 60):02d}")
    (progress_w, _), _ = cv2.getTextSize(
        progress, cv2.FONT_HERSHEY_SIMPLEX, sc(H, 0.8), 2)
    text(img, progress, (W - progress_w - margin, baseline),
         sc(H, 0.8), STEEL, 2, shadow=False)
    # drill board
    DRAWERS[drill.kind](img, drill, now, joints, args, W, H)

    # Tracking loss is a STATE, not a gap: dim the stage and say so. An armed
    # drill stays armed — only positive evidence of leaving disarms it — so this
    # banner reports the signal, it does not imply the attempt was cancelled.
    if joints is None and drill.state not in ("idle", "done"):
        stage = img[px(H, BAR_RULE) + 1:H - px(H, 34)]
        stage[:] = (stage.astype(np.float32) * 0.35).astype(np.uint8)
        text_c(img, "TRACKING LOST", W // 2, int(H * 0.46), sc(H, 1.5),
               mix(RED, WHITE, pulse()), 4)
        text_c(img, "step back into the arena", W // 2, int(H * 0.53),
               sc(H, 0.6), STEEL, 2)

    if paused:
        text_c(img, "PAUSED", W // 2, px(H, 100), sc(H, 1.0), RED, 2)
    if drill.state == "idle":
        text_c(img, "PRESS SPACE TO START", W // 2, H // 2, sc(H, 1.4),
               mix(WHITE, YELLOW, pulse()), 3)
    # keys hint sits above the evidence rail so the rail is never crowded out
    text(img, "SPACE start/pause   R restart   F fullscreen   Q quit",
         (margin, H - px(H, 44)), sc(H, 0.45), DGREY, 1, shadow=False)
    evidence_rail(img, W, H, quality, observed_hz,
                  min_cameras=getattr(args, "min_cameras_expected", 6))
    return img


# ----------------------------------- main ------------------------------------

def session_evidence_context(drill, listener):
    """Comparability facts for this session, or None when the viewer sent none.

    Raw observations only — no quality_class and no baseline_eligible boolean.
    Those are decided by the versioned comparison policy from these numbers, so
    changing a threshold can be re-applied to past sessions instead of
    grandfathering whatever was true the day they were recorded.
    """
    spec = PROTOCOL_CATALOG.get(drill.kind)
    if spec is None:
        return None
    params = applied_parameters(drill)
    context = {
        "protocol_id": spec["protocol_id"],
        "applied_parameters": params,
        "protocol_parameters_fingerprint": protocol_parameters_fingerprint(
            spec["protocol_id"], params),
    }
    quality = listener.capture_quality() if listener is not None else None
    if quality:
        context.update(quality)
    seed = getattr(drill, "seed", None)
    if seed is not None:
        # Audit only, deliberately outside the fingerprint — see
        # FINGERPRINT_EXCLUDED. A pinned seed makes cues predictable.
        context["seed_pinned"] = True
    return context


def build_drill(args):
    kind = args.drill
    # Range-check before building: the old `args.rounds or 4` turned --rounds 0
    # into 4 silently, so the session ran a workload nobody asked for.
    workload = validate_workload(
        kind, args.duration if kind == "gk_updown" else args.rounds)
    if kind == "balance":
        return DRILL_REGISTRY[kind](holds=workload or 4, hold_s=args.hold_s)
    if kind == "shuttle":
        return DRILL_REGISTRY[kind](reps=workload or 3,
                                    center_mm=args.shuttle_center_mm,
                                    half_mm=args.shuttle_half_mm)
    if kind == "line_hops":
        return DRILL_REGISTRY[kind](sets=workload or 3, work_s=args.work_s)
    if kind == "gk_save":
        return DRILL_REGISTRY[kind](rounds=workload or 10,
                                    arena_y_mm=args.arena_y_mm,
                                    flip=args.flip, seed=args.seed)
    if kind == "gk_updown":
        return DRILL_REGISTRY[kind](duration_s=workload or 30.0)
    if kind == "cmj":
        return DRILL_REGISTRY[kind](jumps=workload or 5)
    if kind == "hop_symmetry":
        return DRILL_REGISTRY[kind](hops_per_leg=workload or 3)
    if kind == "reactive_cut":
        return DRILL_REGISTRY[kind](arena_x_mm=args.arena_x_mm,
                                    arena_y_mm=args.arena_y_mm,
                                    reps=workload or 6, seed=args.seed)
    if kind == "reaction_zones":
        return DRILL_REGISTRY[kind](
            arena_y_mm=args.arena_y_mm,
            rounds=workload or 10,
            wall_margin_mm=args.wall_margin_mm,
            seed=args.seed,
        )
    raise SystemExit(f"unknown drill: {kind}")


def event_line(drill, ev):
    k = ev.get("event")
    if k == "hold":
        sway = "--" if ev["sway_rms_mm"] is None else f"{ev['sway_rms_mm']:.0f} mm"
        return (f"hold {ev['hold']} ({ev['stance']}): sway {sway}, "
                f"{ev['touchdowns']} touch-down(s)")
    if k == "rep" and drill.kind == "shuttle":
        return (f"rep {ev['rep']}: {ev['total_s']:.2f}s "
                f"(out {ev['t_out_s']:.2f} / across {ev['t_across_s']:.2f} / "
                f"home {ev['t_home_s']:.2f})")
    if k == "rep_abort":
        return f"rep voided: {ev['reason']}"
    if k == "set":
        return f"set {ev['set']}: {ev['crossings']} hops ({ev['rate_hz']:.1f}/s)"
    if k == "round" and drill.kind == "reaction_zones":
        if ev["result"] == "hit":
            return (
                f"round {ev['round']} {ev['zone']}: "
                f"HIT {ev['reaction_s']:.2f}s"
            )
        return f"round {ev['round']} {ev['zone']}: MISS"
    if k == "round_void" and drill.kind == "reaction_zones":
        return (
            f"round {ev['round']} {ev['zone']}: "
            f"VOID ({ev['reason'].replace('_', ' ')})"
        )
    if k == "round_void":
        return (f"round {ev['round']}: VOID "
                f"({str(ev.get('reason', 'unknown')).replace('_', ' ')})")
    if k == "round":
        if ev["result"] == "save":
            return f"round {ev['round']} {ev['corner']}: SAVE {ev['reaction_s']:.2f}s"
        if ev["result"] == "anticipated":
            # Must not read as a miss: the keeper moved, just not in response to
            # the cue. Logging it as MISS would hide the fault this names.
            return (f"round {ev['round']} {ev['corner']}: TOO EARLY "
                    f"{ev['reaction_s']:.3f}s (not scored)")
        return f"round {ev['round']} {ev['corner']}: MISS"
    if k == "jump":
        return f"jump {ev['jump']}: pelvis rise {ev['pelvis_rise_mm']:.0f} mm"
    if k == "hop":
        return (f"hop {ev['attempt']} ({ev['leg']}): {ev['distance_mm']:.0f} mm, "
                f"stabilised in {ev['stabilise_s']:.1f}s")
    if k == "rep" and drill.kind == "reactive_cut":
        decision = ev.get("decision_s")
        tail = f"decision {decision:.2f}s" if decision else "no commit"
        return (f"rep {ev['rep']} cue {ev['cued']} -> {ev['went'] or '-'}: "
                f"{ev['result'].upper()}, {tail}")
    if k == "rep_void" and drill.kind == "reactive_cut":
        return f"rep {ev['rep']}: VOID ({ev.get('reason', 'unknown')})"
    if k == "rep_void":
        recovery = ev.get("recovery_s")
        measured = "" if recovery is None else f" ({recovery:.2f}s measured)"
        return (f"rep voided: {str(ev.get('reason', 'unknown')).replace('_', ' ')}"
                f"{measured}")
    if k == "rep":
        return f"down-up {ev['rep']}: recovery {ev['recovery_s']:.2f}s"
    return json.dumps(ev, ensure_ascii=False)


def has_data(drill):
    return (
        bool(getattr(drill, "results", None))
        or getattr(drill, "reps", 0) > 0
        or getattr(drill, "voided_rounds", 0) > 0
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drill", required=True, choices=sorted(DRILL_REGISTRY),
                    help="which drill to run: balance | shuttle | line_hops | "
                         "gk_save | gk_updown | reaction_zones")
    ap.add_argument("--athlete", default="", help="athlete name for the logs/HUD")
    ap.add_argument("--rounds", type=int, default=None,
                    help="holds/reps/sets/rounds (drill-appropriate default)")
    ap.add_argument("--duration", type=float, default=None,
                    help="work duration in seconds (gk_updown)")
    ap.add_argument("--flip", action="store_true",
                    help="mirror LEFT/RIGHT if screen sides feel inverted")
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed (gk_save/reaction_zones cues; audit only)")
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--udp-max-age", type=float, default=0.6)
    ap.add_argument("--arena-x-mm", type=float, default=6230.0)
    ap.add_argument("--arena-y-mm", type=float, default=3050.0)
    ap.add_argument("--wall-margin-mm", type=float, default=500.0,
                    help="minimum pelvis-target clearance from side walls")
    ap.add_argument("--shuttle-center-mm", type=float, default=3115.0)
    ap.add_argument("--shuttle-half-mm", type=float, default=2000.0)
    ap.add_argument("--hold-s", type=float, default=20.0, help="balance hold length")
    ap.add_argument("--work-s", type=float, default=20.0, help="line_hops set length")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--window-pane", choices=list(PANES), default="none",
                    help="Place the board on one half of the desktop work area so "
                         "the 3D arena view fits beside it (display-only). "
                         "'none' leaves placement to the window manager; "
                         "--fullscreen overrides it.")
    ap.add_argument("--wait-for-arena", type=float, default=0.0,
                    help="Seconds to wait for the viewer's first UDP packet before "
                         "opening the board window, so both windows appear together "
                         "instead of the board sitting empty through model load and "
                         "camera open. 0 opens immediately (standalone use).")
    ap.add_argument("--no-autostart", action="store_true",
                    help="wait for SPACE instead of starting immediately")
    ap.add_argument("--log-dir", default="garage_lab_combined/output/training_logs")
    ap.add_argument("--record-packets", default="",
                    help="Write every received pose packet verbatim to this JSONL "
                         "so the session can be replayed into a drill later "
                         "(project_cam.training.replay). Defaults to "
                         "<session dir>/pose_trace.jsonl when launched from the "
                         "desktop Control Center, which is where evidence belongs; "
                         "off for a bare CLI run. --no-record-packets disables it.")
    ap.add_argument("--no-record-packets", action="store_true",
                    help="never write a pose trace, even inside a desktop session")
    args = ap.parse_args()

    drill = build_drill(args)
    listener = UDPJointListener(port=args.udp_port,
                                record_path=resolve_trace_path(args))
    stop = {"flag": False}

    def _sig(_s, _f):
        stop["flag"] = True

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    log_dir = Path(args.log_dir)
    if not log_dir.is_absolute():
        log_dir = REPO_ROOT / log_dir
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    events_path = log_dir / f"{args.drill}_{stamp}.jsonl"
    summary_path = log_dir / f"{args.drill}_{stamp}_summary.json"
    index_path = log_dir / "sessions_index.jsonl"
    events_fh = None
    started_iso = datetime.now().isoformat(timespec="seconds")
    desktop_session_id = os.environ.get("PROJECT_CAM_SESSION_ID", "").strip()
    finalized = False

    def finalize(aborted):
        nonlocal finalized
        if finalized or not has_data(drill):
            return
        record = build_session_record(
            drill, args.athlete, started_iso,
            datetime.now().isoformat(timespec="seconds"), aborted=aborted,
            session_id=desktop_session_id,
            evidence_context=session_evidence_context(drill, listener))
        log_dir.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        append_session_index(index_path, record)
        finalized = True
        print(f"[DRILL] {'aborted' if aborted else 'complete'}: "
              f"{drill.headline()}  ->  {summary_path.name}", flush=True)

    print(f"[DRILL] {drill.title} — athlete: {args.athlete or '(unnamed)'} — "
          f"listening on UDP :{args.udp_port}", flush=True)
    print(f"[DRILL] logs -> {events_path}", flush=True)

    # Open the board only once the arena viewer is actually streaming, so both
    # windows appear together. The viewer needs tens of seconds for the TensorRT
    # engines and the six USB cameras; a board opened first sits empty through
    # all of it and its countdown would burn while the athlete sees nothing.
    # `--udp-capture-context` makes the viewer heartbeat even when it tracks
    # nobody, so liveness arrives on its first loop iteration — the same moment
    # its own window appears.
    if args.wait_for_arena > 0 and not listener.viewer_alive(max_age=3.0):
        deadline = time.time() + args.wait_for_arena
        announced = time.time()
        print(f"[DRILL] waiting for the arena viewer on UDP :{args.udp_port} "
              f"(up to {args.wait_for_arena:.0f}s) so both windows open together ...",
              flush=True)
        while not stop["flag"] and not listener.viewer_alive(max_age=3.0):
            now = time.time()
            if now >= deadline:
                print("[DRILL] arena viewer not heard — opening the board anyway",
                      flush=True)
                break
            if now - announced >= 10.0:
                print(f"[DRILL] ... arena still starting "
                      f"({deadline - now:.0f}s before opening anyway)", flush=True)
                announced = now
            time.sleep(0.2)
        if stop["flag"]:
            print("[DRILL] stopped before the board opened", flush=True)
            listener.stop()
            return
        if listener.viewer_alive(max_age=3.0):
            print("[DRILL] arena viewer is live", flush=True)

    win = "Project Cam - Training"
    # GUI_NORMAL drops the Qt toolbar/status bar. This window is athlete-facing,
    # and with chrome present `resizeWindow` sizes the frame rather than the
    # image, which silently shrinks an exact half-screen pane.
    cv2.namedWindow(win, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
    cv2.resizeWindow(win, args.width, args.height)
    pane = None
    if args.fullscreen:
        cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        pane = pane_rect(args.window_pane, aspect=args.width / max(1, args.height))
        if pane is not None:
            # The window has to be realised before its geometry reads back.
            cv2.imshow(win, np.zeros((args.height, args.width, 3), np.uint8))
            cv2.waitKey(1)
            place_window(win, pane, pump=cv2.waitKey)

    session_t0 = time.time()
    quality = None
    observed_hz = None
    last_quality_at = 0.0
    paused = False
    if not args.no_autostart:
        drill.start(session_t0)

    try:
        while not stop["flag"]:
            now = time.time()
            joints, age = listener.get(args.udp_max_age)
            if not paused:
                drill.update(now, joints)
            for ev in drill.pop_events():
                if events_fh is None:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    events_fh = events_path.open("a", encoding="utf-8")
                rec = {"ts": round(now, 3), "drill": drill.kind,
                       "athlete": args.athlete, **ev}
                events_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                events_fh.flush()
                print(f"[DRILL] {event_line(drill, ev)}", flush=True)
            if drill.state == "done":
                finalize(aborted=False)
            # Evidence rail data. capture_quality() is cheap (a dict build under
            # a lock), but it is only rebuilt a few times a second because the
            # rail reports session aggregates, not per-frame values.
            if now - last_quality_at >= 0.5:
                quality = listener.capture_quality()
                elapsed = max(1e-3, now - session_t0)
                packets = (quality or {}).get("packets_observed") or 0
                observed_hz = packets / elapsed if packets else None
                last_quality_at = now
            img = render(drill, now, joints, age, args.athlete, session_t0,
                         paused, args, quality=quality, observed_hz=observed_hz)
            cv2.imshow(win, img)
            k = cv2.waitKey(16) & 0xFF
            if k == ord("q"):
                break
            elif k == ord(" "):
                if drill.state in ("idle", "done"):
                    drill.start(now)
                    finalized = False
                    started_iso = datetime.now().isoformat(timespec="seconds")
                    session_t0 = now
                else:
                    paused = not paused
            elif k == ord("r"):
                drill.reset()
                drill.start(now)
                finalized = False
                started_iso = datetime.now().isoformat(timespec="seconds")
                session_t0 = now
            elif k == ord("f"):
                cur = cv2.getWindowProperty(win, cv2.WND_PROP_FULLSCREEN)
                if cur >= 1:
                    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_NORMAL)
                    # Leaving fullscreen restores the previous frame on this cv2
                    # build and collapses it to a stub on others; re-assert the
                    # pane so `f` always returns to the tiled layout.
                    place_window(win, pane, pump=cv2.waitKey)
                else:
                    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                                          cv2.WINDOW_FULLSCREEN)
            try:
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    except KeyboardInterrupt:
        pass
    finally:
        finalize(aborted=drill.state != "done")
        if events_fh is not None:
            events_fh.close()
        listener.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
