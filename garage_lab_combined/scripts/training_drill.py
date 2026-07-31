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

try:
    # Unicode-safe text (Cyrillic athlete names) — see .claude/rules/perf.md.
    from project_cam.viz.text import put_text as _put_text_unicode
except Exception:  # pragma: no cover - fonts/PIL missing
    _put_text_unicode = None

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

    def __init__(self, host="0.0.0.0", port=5005):
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
            except socket.timeout:
                continue
            except Exception:
                continue
        s.close()

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
#: and the evidence rail (from H-34). A drawer that paints into this band
#: overwrites the honesty rail, which is the one thing on the board that must
#: never be obscured.
STAGE_BOTTOM_RESERVED = 62


def stage_bottom(H):
    """Lowest y a per-drill drawer may use.

    Exists as one function rather than a remembered number because every drawer
    got it wrong independently: elements placed at y=660..670 on a 720-tall board
    painted straight over the key hints.
    """
    return int(H) - STAGE_BOTTOM_RESERVED


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


def hbar(img, x0, y0, w, h, frac, color, bg=PANEL):
    frac = max(0.0, min(1.0, frac))
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), bg, -1)
    if frac > 0:
        cv2.rectangle(img, (x0, y0), (x0 + int(w * frac), y0 + h), color, -1)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), DGREY, 1)


def pulse(a=0.35, b=1.0, hz=3.0):
    return a + (b - a) * (0.5 + 0.5 * math.sin(time.time() * 2 * math.pi * hz))


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
        text_c(img, "SETTLING", cx, cy + radius_px + int(sc(H, 44)),
               sc(H, 0.7), STEEL, 2, shadow=False)
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
    x0, x1 = int(sc(H, 90)), W - int(sc(H, 90))
    ly0, ly1 = int(sc(H, 180)), int(sc(H, 400))
    span0 = d.line_b - 700
    span1 = d.line_a + 700

    def X(mm):
        t = (mm - span0) / max(1.0, span1 - span0)
        return int(x0 + max(0.0, min(1.0, t)) * (x1 - x0))

    panel(img, x0, ly0, x1, ly1, radius=int(sc(H, 12)), border=DGREY)
    targets = {"to_a": "A", "to_b": "B", "home": "START"}
    target = targets.get(d.phase) if d.state == "run" else None
    for label, mm in (("B", d.line_b), ("START", d.center), ("A", d.line_a)):
        u = X(mm)
        hot = d.state == "run" and label == target
        col = mix(YELLOW, WHITE, pulse()) if hot else (WHITE if label == "START" else STEEL)
        if hot:
            glow(img, u, (ly0 + ly1) // 2, int(sc(H, 90)), YELLOW, gain=0.35)
        cv2.line(img, (u, ly0), (u, ly1), col, 4 if hot else 2, cv2.LINE_AA)
        text_c(img, label, u, ly0 - int(sc(H, 12)), sc(H, 0.8), col, 2,
               shadow=False)
    p = pelvis_mm(joints)
    if p is not None:
        v = ly0 + int(max(0.0, min(1.0, p[1] / args.arena_y_mm)) * (ly1 - ly0))
        cv2.circle(img, (X(p[0]), v), int(sc(H, 13)), YELLOW, -1, cv2.LINE_AA)
        cv2.circle(img, (X(p[0]), v), int(sc(H, 13)), (0, 0, 0), 2, cv2.LINE_AA)

    cy = int(sc(H, 520))
    if d.state == "arm":
        text_c(img, "WALK TO THE START LINE", W // 2, cy, sc(H, 1.4),
               mix(WHITE, YELLOW, pulse()), 3)
    elif d.state == "countdown":
        n = max(1, int(math.ceil(d.countdown_s - (now - d.t_state))))
        glow(img, W // 2, cy + int(sc(H, 4)), int(sc(H, 130)), YELLOW, gain=0.30)
        text_c(img, str(n), W // 2, cy + int(sc(H, 30)), sc(H, 4.0), YELLOW, 7)
    elif d.state == "run":
        t = now - d.go_time
        best = d.best_rep()
        cuts = None
        if best is not None:
            cuts = [best["t_out_s"],
                    best["t_out_s"] + best["t_across_s"],
                    best["total_s"]]
        value_unit(img, f"{t:5.2f}", "s", W // 2, cy, 3.0, WHITE, H, thick=6)
        delta = ghost_split_bar(img, int(sc(H, 110)), cy + int(sc(H, 40)),
                                W - int(sc(H, 220)), int(sc(H, 22)), t, cuts, H)
        text_c(img, f"SPRINT TO {target}", W // 2, cy + int(sc(H, 112)),
               sc(H, 1.0), YELLOW, 2)
        if delta is not None:
            sign = "+" if delta >= 0 else ""
            text_c(img, f"{sign}{delta:.2f}s vs best", W // 2,
                   cy + int(sc(H, 150)), sc(H, 0.8),
                   AMBER if delta > 0 else GREEN, 2, shadow=False)
    elif d.state == "rest":
        if d.last_result and d.last_result[0] == "ok":
            r = d.results[-1]
            best = d.best_rep()
            is_best = best is not None and r["total_s"] == best["total_s"]
            value_unit(img, f"{r['total_s']:.2f}", "s", W // 2, cy, 2.6,
                       YELLOW if is_best else GREEN, H, thick=5)
            text_c(img, f"REP {r['rep']}" + ("   NEW BEST" if is_best else ""),
                   W // 2, cy + int(sc(H, 40)), sc(H, 0.8),
                   YELLOW if is_best else STEEL, 2, shadow=False)
            # Splits as proportional segments: which leg of the shuttle cost the
            # time is the actionable part, and three numbers in a row hide it.
            # A brightness ramp, not three colours — the segments are one
            # measured time decomposed, so they must not read as three verdicts.
            segs = (("out", r["t_out_s"], STEEL),
                    ("across", r["t_across_s"], GREY),
                    ("home", r["t_home_s"], WHITE))
            bw = W - int(sc(H, 260))
            bx = int(sc(H, 130))
            by = cy + int(sc(H, 70))
            acc = 0
            for name, val, col in segs:
                seg_w = int(bw * (val / max(0.01, r["total_s"])))
                cv2.rectangle(img, (bx + acc, by),
                              (bx + acc + seg_w, by + int(sc(H, 20))), col, -1)
                text_c(img, f"{name} {val:.2f}", bx + acc + seg_w // 2,
                       by + int(sc(H, 44)), sc(H, 0.55), STEEL, 1, shadow=False)
                acc += seg_w
        elif d.last_result:
            text_c(img, "REP VOIDED", W // 2, cy, sc(H, 1.6), RED, 4)
            text_c(img, str(d.last_result[1]), W // 2, cy + int(sc(H, 44)),
                   sc(H, 0.8), STEEL, 2, shadow=False)
        left = d.rest_s - (now - d.t_state)
        text_c(img, f"rest {max(0, left):.0f}s", W // 2, cy + int(sc(H, 140)),
               sc(H, 0.8), STEEL, 2, shadow=False)
    elif d.state == "done":
        s = d.summary()
        if s["best_total_s"] is None:
            text_c(img, "NO COMPLETED REPS", W // 2, cy, sc(H, 1.4), STEEL, 3)
            return
        value_unit(img, f"{s['best_total_s']:.2f}", "s best", W // 2, cy, 2.6,
                   YELLOW, H, thick=5)
        text_c(img, f"avg {s['avg_total_s']:.2f} s over {s['reps_completed']} reps"
                    f"   |   course {s['course_m']} m", W // 2,
               cy + int(sc(H, 46)), sc(H, 0.85), WHITE, 2, shadow=False)
        if s["aborts"]:
            text_c(img, f"{s['aborts']} rep(s) voided on tracking loss",
                   W // 2, cy + int(sc(H, 82)), sc(H, 0.7), AMBER, 2,
                   shadow=False)


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
    cy = H // 2
    if d.state == "countdown":
        text_c(img, "STAND ON YOUR LINE", W // 2, cy - int(sc(H, 130)),
               sc(H, 1.5), WHITE, 3)
        if d.waiting_tracking:
            text_c(img, "STEP INTO THE ARENA", W // 2, cy - int(sc(H, 60)),
                   sc(H, 1.0), mix(RED, WHITE, pulse()), 2)
        else:
            n = max(1, int(math.ceil(d.countdown_s - (now - d.t_state))))
            glow(img, W // 2, cy - int(sc(H, 16)), int(sc(H, 150)), YELLOW,
                 gain=0.30)
            text_c(img, str(n), W // 2, cy + int(sc(H, 10)), sc(H, 5.0),
                   YELLOW, 8)
        text_c(img, "then jump side-to-side over it as fast as you can",
               W // 2, cy + int(sc(H, 110)), sc(H, 0.9), STEEL, 2, shadow=False)
        return
    # The line and the athlete's lateral offset from it.
    lx = W // 2
    ly0, ly1 = int(sc(H, 150)), int(sc(H, 380))
    panel(img, int(sc(H, 90)), ly0 - int(sc(H, 18)), W - int(sc(H, 90)),
          ly1 + int(sc(H, 18)), radius=int(sc(H, 12)), border=DGREY)
    cv2.line(img, (lx, ly0), (lx, ly1), YELLOW, 4, cv2.LINE_AA)
    am = ankle_mid_mm(joints)
    if am is not None and d.line is not None:
        off = max(-1.0, min(1.0, (am[1] - d.line) / 500.0))
        u = int(lx + off * (W * 0.28))
        v = (ly0 + ly1) // 2
        cv2.circle(img, (u, v), int(sc(H, 15)), WHITE, -1, cv2.LINE_AA)
        cv2.circle(img, (u, v), int(sc(H, 15)), (0, 0, 0), 2, cv2.LINE_AA)
    if d.state == "work":
        left = max(0.0, d.work_s - (now - d.t_state))
        # The hop count is the headline, so it gets its own column with room for
        # four digits; the earlier layout let it run into the cadence label.
        value_unit(img, str(d.crossings), "hops", int(sc(H, 250)),
                   int(sc(H, 495)), 3.2, YELLOW, H, thick=7)
        live = d.live_cadence_hz(now)
        avg = d.crossings / max(0.1, now - d.t_state)
        value_unit(img, "--" if live is None else f"{live:.1f}", "/s now",
                   W - int(sc(H, 250)), int(sc(H, 495)), 2.2, WHITE, H)
        text_c(img, f"set average {avg:.1f}/s", W - int(sc(H, 250)),
               int(sc(H, 531)), sc(H, 0.6), STEEL, 2, shadow=False)
        bottom = stage_bottom(H)
        hbar(img, int(sc(H, 120)), bottom - int(sc(H, 12)), W - int(sc(H, 240)),
             int(sc(H, 10)), 1 - left / d.work_s, YELLOW)
        text(img, f"{left:3.0f}s", (W - int(sc(H, 108)), bottom - int(sc(H, 2))),
             sc(H, 0.6), STEEL, 2, shadow=False)
        cadence_strip(img, int(sc(H, 120)), bottom - int(sc(H, 84)),
                      W - int(sc(H, 240)), int(sc(H, 56)), d.cross_times,
                      d.t_state, d.work_s, H)
    elif d.state == "rest":
        r = d.results[-1]
        value_unit(img, str(r["crossings"]), f"hops | set {r['set']}", W // 2,
                   int(sc(H, 480)), 2.6, GREEN, H, thick=5)
        drop = r.get("cadence_drop_pct")
        first, second = r.get("first_half_rate_hz"), r.get("second_half_rate_hz")
        if first is not None and second is not None:
            col = GREEN if (drop or 0) < 15 else (AMBER if (drop or 0) < 30 else RED)
            text_c(img, f"first half {first:.1f}/s   ->   second half {second:.1f}/s",
                   W // 2, int(sc(H, 530)), sc(H, 0.9), WHITE, 2, shadow=False)
            text_c(img, f"cadence held {100 - (drop or 0):.0f}%", W // 2,
                   int(sc(H, 568)), sc(H, 1.0), col, 2)
        else:
            text_c(img, f"{r['rate_hz']:.1f}/s average", W // 2, int(sc(H, 530)),
                   sc(H, 0.9), WHITE, 2, shadow=False)
        left = d.rest_s - (now - d.t_state)
        text_c(img, f"rest {max(0, left):.0f}s", W // 2, int(sc(H, 620)),
               sc(H, 0.8), STEEL, 2, shadow=False)
    elif d.state == "done":
        s = d.summary()
        value_unit(img, str(s["total_crossings"]), "hops total", W // 2,
                   int(sc(H, 500)), 2.6, YELLOW, H, thick=5)
        if s["best_rate_hz"] is not None:
            text_c(img, f"best set {s['best_rate_hz']:.1f}/s   |   "
                        f"avg {s['avg_rate_hz']:.1f}/s", W // 2, int(sc(H, 550)),
                   sc(H, 0.9), WHITE, 2, shadow=False)
        if s.get("avg_cadence_drop_pct") is not None:
            drop = s["avg_cadence_drop_pct"]
            col = GREEN if drop < 15 else (AMBER if drop < 30 else RED)
            text_c(img, f"average cadence drop within a set {drop:.0f}%",
                   W // 2, int(sc(H, 592)), sc(H, 0.85), col, 2, shadow=False)


def draw_gk_save(img, d, now, joints, args, W, H):
    gx0, gx1 = 170, W - 170
    gy0, gy1 = 130, 520
    cv2.rectangle(img, (gx0, gy0), (gx1, gy1), PANEL, -1)
    cv2.rectangle(img, (gx0, gy0), (gx1, gy1), WHITE, 3)   # goal frame
    bw = int((gx1 - gx0) * 0.32)
    bh = int((gy1 - gy0) * 0.40)
    boxes = {
        "HIGH-LEFT": (gx0 + 6, gy0 + 6, gx0 + 6 + bw, gy0 + 6 + bh),
        "HIGH-RIGHT": (gx1 - 6 - bw, gy0 + 6, gx1 - 6, gy0 + 6 + bh),
        "LOW-LEFT": (gx0 + 6, gy1 - 6 - bh, gx0 + 6 + bw, gy1 - 6),
        "LOW-RIGHT": (gx1 - 6 - bw, gy1 - 6 - bh, gx1 - 6, gy1 - 6),
    }
    cue = d.corner_name() if d.state in ("active", "result") else None
    # Heat accumulates DURING the session, not only at the end. A weakness the
    # keeper can see forming is a weakness they can work on in the same session;
    # revealing it after the last round makes it a report, not coaching.
    per = d.per_corner()
    summary = d.summary()
    weakest = summary["weakest_corner"]
    for name, (bx0, by0, bx1, by1) in boxes.items():
        c = per[name]
        base = (30, 29, 28)
        fill = base
        border = DGREY
        if c["rounds"]:
            # Tint by miss rate: a corner that keeps beating the keeper reddens.
            miss = 1.0 - (c["saves"] / c["rounds"])
            fill = mix(base, RED, 0.10 + 0.45 * miss)
        if d.state == "active" and name == cue:
            fill = mix(base, YELLOW, pulse(0.45, 1.0, 4.0))
            border = YELLOW
            glow(img, (bx0 + bx1) // 2, (by0 + by1) // 2, int(sc(H, 110)),
                 YELLOW, gain=0.30)
        elif d.state == "result" and name == cue:
            saved = bool(d.last_result and d.last_result[0] == "save")
            fill = GREEN if saved else RED
            border = WHITE
        cv2.rectangle(img, (bx0, by0), (bx1, by1), fill, -1)
        cv2.rectangle(img, (bx0, by0), (bx1, by1), border, 2)
        mid_x, mid_y = (bx0 + bx1) // 2, (by0 + by1) // 2
        if c["rounds"] and not (d.state == "result" and name == cue):
            weak = weakest == name and d.state == "done"
            text_c(img, f"{c['saves']}/{c['rounds']}", mid_x,
                   mid_y - int(sc(H, 4)), sc(H, 1.1),
                   RED if weak else WHITE, 2, shadow=False)
            if c["avg_reaction_s"] is not None:
                label, tcol = tier_of(c["avg_reaction_s"])
                text_c(img, f"{c['avg_reaction_s']:.2f}s", mid_x,
                       mid_y + int(sc(H, 32)), sc(H, 0.75), tcol, 2,
                       shadow=False)
                if d.state == "done":
                    text_c(img, label, mid_x, mid_y + int(sc(H, 58)),
                           sc(H, 0.55), tcol, 1, shadow=False)
        elif not c["rounds"]:
            text_c(img, "--", mid_x, mid_y + int(sc(H, 6)), sc(H, 0.8), DGREY,
                   2, shadow=False)
    # wrist markers inside the goal (flip-aware, height self-calibrated)
    if d.state in ("set_wait", "armed", "active") and joints:
        for wn, col in (("left_wrist", (255, 200, 40)), ("right_wrist", (40, 200, 255))):
            w = get_joint(joints, wn)
            if w is None:
                continue
            t = max(0.0, min(1.0, w[1] / d.arena_y))
            if d.flip:
                t = 1.0 - t
            u = int(gx0 + t * (gx1 - gx0))
            v = int(gy1 - max(0.0, min(1.0, w[2] / 2400.0)) * (gy1 - gy0))
            cv2.circle(img, (u, v), 10, col, -1)
            cv2.circle(img, (u, v), 10, (0, 0, 0), 2)

    cy = int(sc(H, 590))
    if d.state == "set_wait":
        text_c(img, "GET SET - CENTER, HANDS READY", W // 2, cy, sc(H, 1.3),
               mix(WHITE, YELLOW, pulse()), 3)
    elif d.state == "armed":
        text_c(img, "HOLD...", W // 2, cy, sc(H, 1.5), WHITE, 3)
    elif d.state == "active":
        text_c(img, cue or "", W // 2, cy, sc(H, 1.8), YELLOW, 4)
    elif d.state == "result" and d.last_result:
        kind, rt = d.last_result
        if kind == "save":
            label, tcol = tier_of(rt)
            value_unit(img, f"{rt:.2f}", "s", W // 2, cy, 2.2, GREEN, H, thick=5)
            text_c(img, f"SAVE  |  {label}", W // 2, cy + int(sc(H, 40)),
                   sc(H, 0.9), tcol, 2, shadow=False)
        else:
            text_c(img, "MISS", W // 2, cy, sc(H, 1.8), RED, 4)
    elif d.state == "done":
        s = d.summary()
        value_unit(img, f"{s['saves']}/{s['rounds_completed']}", "saves",
                   W // 2, cy, 2.2, YELLOW, H, thick=5)
        if s["avg_reaction_s"] is not None:
            label, tcol = tier_of(s["avg_reaction_s"])
            text_c(img, f"average reaction {s['avg_reaction_s']:.2f} s  |  {label}",
                   W // 2, cy + int(sc(H, 40)), sc(H, 0.85), tcol, 2,
                   shadow=False)
        if s["weakest_corner"]:
            text_c(img, f"weakest corner: {s['weakest_corner']}", W // 2,
                   cy + int(sc(H, 76)), sc(H, 0.85), RED, 2, shadow=False)


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
    cy = H // 2
    if d.state == "countdown":
        text_c(img, "STAND TALL - MEASURING YOUR HEIGHT", W // 2,
               cy - int(sc(H, 110)), sc(H, 1.2), WHITE, 3)
        if d.waiting_tracking:
            text_c(img, "STEP INTO THE ARENA", W // 2, cy - int(sc(H, 40)),
                   sc(H, 1.0), mix(RED, WHITE, pulse()), 2)
        else:
            n = max(1, int(math.ceil(d.countdown_s - (now - d.t_state))))
            glow(img, W // 2, cy, int(sc(H, 150)), YELLOW, gain=0.30)
            text_c(img, str(n), W // 2, cy + int(sc(H, 30)), sc(H, 5.0),
                   YELLOW, 8)
        return
    # Vertical pelvis meter, with the self-calibrated thresholds marked.
    mx0, mx1 = W // 2 - int(sc(H, 44)), W // 2 + int(sc(H, 44))
    my0, my1 = int(sc(H, 120)), int(sc(H, 500))
    top_z = (d.stand_z or 1000.0) * 1.15

    def V(z):
        return int(my1 - max(0.0, min(1.0, z / top_z)) * (my1 - my0))

    panel(img, mx0, my0, mx1, my1, radius=int(sc(H, 8)), border=DGREY, thick=2)
    p = pelvis_mm(joints)
    if p is not None:
        v = V(p[2])
        col = GREEN if d.phase == "down" else YELLOW
        cv2.rectangle(img, (mx0 + 3, v), (mx1 - 3, my1 - 3), col, -1)
    if d.stand_z:
        for zval, col, lbl in ((d.down_thresh, RED, "DOWN"),
                               (d.up_thresh, GREEN, "SET")):
            v = V(zval)
            cv2.line(img, (mx0 - int(sc(H, 24)), v), (mx1 + int(sc(H, 24)), v),
                     col, 2, cv2.LINE_AA)
            text(img, lbl, (mx1 + int(sc(H, 32)), v + int(sc(H, 6))),
                 sc(H, 0.6), col, 2, shadow=False)
    if d.state == "work":
        value_unit(img, str(d.reps), "reps", int(sc(H, 215)), cy, 4.0, YELLOW, H,
                   thick=8)
        cue = "GO DOWN!" if d.phase == "up" else "GET UP!"
        text_c(img, cue, W // 2, int(sc(H, 560)), sc(H, 1.5),
               mix(WHITE, YELLOW, pulse()), 3)
        if d.recoveries:
            last = d.recoveries[-1]
            ref = d.recoveries[0]
            ratio = last / ref if ref > 0 else 1.0
            col = GREEN if ratio <= 1.25 else (AMBER if ratio <= 1.6 else RED)
            value_unit(img, f"{last:.2f}", "s last up", W - int(sc(H, 235)),
                       cy - int(sc(H, 20)), 2.0, col, H)
            if len(d.recoveries) > 1:
                text_c(img, f"{ratio * 100 - 100:+.0f}% vs rep 1",
                       W - int(sc(H, 235)), cy + int(sc(H, 16)), sc(H, 0.6),
                       col, 2, shadow=False)
        bottom = stage_bottom(H)
        left = max(0.0, d.duration_s - (now - d.t_state))
        hbar(img, int(sc(H, 130)), bottom - int(sc(H, 12)), W - int(sc(H, 330)),
             int(sc(H, 10)), 1 - left / d.duration_s, YELLOW)
        text(img, f"{left:3.0f}s", (W - int(sc(H, 178)), bottom - int(sc(H, 2))),
             sc(H, 0.6), STEEL, 2, shadow=False)
        recovery_decay(img, int(sc(H, 130)), bottom - int(sc(H, 76)),
                       W - int(sc(H, 330)), int(sc(H, 48)), d.recoveries, H)
    elif d.state == "done":
        s = d.summary()
        value_unit(img, str(s["reps"]), "down-ups", W // 2, int(sc(H, 560)),
                   2.4, YELLOW, H, thick=5)
        if s["avg_recovery_s"] is not None:
            text_c(img, f"average get-up {s['avg_recovery_s']:.2f} s",
                   W // 2, int(sc(H, 600)), sc(H, 0.9), WHITE, 2, shadow=False)
        if len(d.recoveries) > 1:
            first, last = d.recoveries[0], d.recoveries[-1]
            drift = (last / first - 1.0) * 100.0 if first > 0 else 0.0
            col = GREEN if drift <= 25 else (AMBER if drift <= 60 else RED)
            text_c(img, f"first rep {first:.2f} s   ->   last rep {last:.2f} s"
                        f"   ({drift:+.0f}%)", W // 2, int(sc(H, 638)),
                   sc(H, 0.85), col, 2, shadow=False)
            recovery_decay(img, int(sc(H, 200)), int(sc(H, 460)),
                           W - int(sc(H, 500)), int(sc(H, 60)), d.recoveries, H)


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


def draw_cmj(img, d, now, joints, args, W, H):
    """Load monitoring: the hero is the rise, the story is the drop-off."""
    pelvis = pelvis_mm(joints)
    rises = d.rises()

    if d.state == "countdown":
        text_c(img, "STAND TALL AND STILL", W // 2, int(H * 0.32), sc(H, 1.4),
               mix(WHITE, YELLOW, pulse()), 3)
        text_c(img, "calibrating your standing height", W // 2, int(H * 0.40),
               sc(H, 0.55), STEEL, 2, shadow=False)
        n = max(1, int(math.ceil(d.countdown_s - (now - d.t_state))))
        text_c(img, str(n), W // 2, int(H * 0.62), sc(H, 4.0), YELLOW, 8)
        return

    # Live pelvis column with the standing reference marked.
    col_x = int(W * 0.13)
    col_w = int(W * 0.07)
    top, bot = int(H * 0.20), int(H * 0.80)
    panel(img, col_x, top, col_x + col_w, bot, radius=8, fill=(16, 18, 21),
          border=(36, 40, 44))
    if d.stand_z and pelvis is not None:
        span = max(1.0, d.stand_z * 0.45)
        frac = min(max((pelvis[2] - d.stand_z) / span, -1.0), 1.0)
        mid = (top + bot) // 2
        y = int(mid - frac * (bot - top) / 2)
        color = GREEN if frac > 0.05 else (AMBER if frac < -0.05 else WHITE)
        cv2.rectangle(img, (col_x + 3, min(mid, y)), (col_x + col_w - 3, max(mid, y)),
                      color, -1)
        cv2.line(img, (col_x - 10, mid), (col_x + col_w + 10, mid), STEEL, 2)
        text(img, "STAND", (col_x + col_w + 16, mid + 6), sc(H, 0.45), STEEL, 1,
             shadow=False)

    best = max(rises) if rises else None
    if best is not None:
        value_unit(img, f"{best:.0f}", "mm pelvis rise", int(W * 0.58),
                   int(H * 0.30), 2.6, WHITE, H, thick=6)
        text_c(img, "best of the set", int(W * 0.58), int(H * 0.365),
               sc(H, 0.5), STEEL, 1, shadow=False)
    else:
        text_c(img, "JUMP", int(W * 0.58), int(H * 0.30), sc(H, 2.4),
               mix(WHITE, YELLOW, pulse()), 6)

    # Per-jump bars: the decay across the set is the whole point.
    if rises:
        bx, by = int(W * 0.33), int(H * 0.72)
        bw = int(W * 0.045)
        scale_top = max(rises) or 1.0
        third = max(1, len(rises) // 3)
        base = fmean_safe(rises[:third])
        for i, rise in enumerate(rises):
            h_bar = int((rise / scale_top) * H * 0.22)
            x = bx + i * (bw + int(W * 0.012))
            drop = (rise - base) / base if base else 0.0
            color = GREEN if drop > -0.05 else (AMBER if drop > -0.12 else RED)
            cv2.rectangle(img, (x, by - h_bar), (x + bw, by), color, -1)
        text(img, "PELVIS RISE PER JUMP", (bx, by + int(H * 0.045)),
             sc(H, 0.45), STEEL, 1, shadow=False)

    s = d.summary()
    if s["drop_off_pct"] is not None:
        color = GREEN if s["drop_off_pct"] > -5 else (
            AMBER if s["drop_off_pct"] > -12 else RED)
        text(img, f"drop-off {s['drop_off_pct']:+.0f}%",
             (int(W * 0.72), int(H * 0.50)), sc(H, 0.7), color, 2)
    text(img, f"{s['jumps_completed']}/{s['jumps_target']} jumps",
         (int(W * 0.72), int(H * 0.56)), sc(H, 0.55), STEEL, 1, shadow=False)
    text(img, "pelvis rise, not force-plate jump height",
         (int(W * 0.33), int(H * 0.135)), sc(H, 0.45), STEEL, 1, shadow=False)


def draw_hop_symmetry(img, d, now, joints, args, W, H):
    """Return-to-play screening: two bars, one index, both raw distances."""
    legs = d.per_leg()
    s = d.summary()

    if d.state == "countdown":
        text_c(img, f"STAND ON YOUR {d.leg().upper()} LEG", W // 2,
               int(H * 0.34), sc(H, 1.4), mix(WHITE, YELLOW, pulse()), 3)
        n = max(1, int(math.ceil(d.countdown_s - (now - d.t_state))))
        text_c(img, str(n), W // 2, int(H * 0.62), sc(H, 4.0), YELLOW, 8)
        return

    lsi = s["limb_symmetry_pct"]
    if lsi is not None:
        color = GREEN if lsi >= 90.0 else (AMBER if lsi >= 80.0 else RED)
        value_unit(img, f"{lsi:.0f}", "% symmetry", W // 2, int(H * 0.27),
                   2.8, color, H, thick=6)
        text_c(img, "reference 90% - a screening signal, not clearance",
               W // 2, int(H * 0.335), sc(H, 0.5), STEEL, 1, shadow=False)
    else:
        text_c(img, f"HOP ON YOUR {d.leg().upper()} LEG", W // 2,
               int(H * 0.28), sc(H, 1.6), mix(WHITE, YELLOW, pulse()), 4)
        text_c(img, "land and hold it still", W // 2, int(H * 0.35),
               sc(H, 0.55), STEEL, 1, shadow=False)

    # Both raw distances side by side — symmetry can be met while both are weak.
    widest = max([legs[leg]["best_mm"] or 0.0 for leg in d.LEGS] + [1.0])
    bar_w = int(W * 0.30)
    for i, leg in enumerate(d.LEGS):
        y = int(H * 0.50) + i * int(H * 0.14)
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

    text(img, f"{s['hops_completed']}/{s['hops_target']} hops",
         (int(W * 0.045), int(H * 0.13)), sc(H, 0.5), STEEL, 1, shadow=False)


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
    trig_x = int(lx0 + (lx1 - lx0) * 0.5)
    cv2.line(img, (trig_x, lane_y0 + 4), (trig_x, lane_y1 - 4), YELLOW, 2)
    text(img, "CUE", (trig_x - int(W * 0.014), lane_y0 - int(H * 0.012)),
         sc(H, 0.45), YELLOW, 1, shadow=False)

    for side, gy in (("LEFT", lane_y0 + int(H * 0.035)),
                     ("RIGHT", lane_y1 - int(H * 0.035))):
        lit = d.target == side and d.state in ("active", "result")
        cv2.line(img, (trig_x, gy), (lx1 - 8, gy),
                 YELLOW if lit else (44, 48, 52), 3 if lit else 1)
        text(img, side, (lx1 - int(W * 0.07), gy - int(H * 0.012)),
             sc(H, 0.55), YELLOW if lit else STEEL, 2 if lit else 1,
             shadow=False)
        if lit:
            glow(img, (trig_x + lx1) // 2, gy, int(H * 0.10), YELLOW, 0.45)

    if pelvis is not None:
        t = min(max(pelvis[0] / max(1.0, d.arena_x_mm), 0.0), 1.0)
        u = min(max(pelvis[1] / max(1.0, d.arena_y_mm), 0.0), 1.0)
        px = int(lx0 + t * (lx1 - lx0))
        py = int(lane_y0 + u * (lane_y1 - lane_y0))
        glow(img, px, py, int(H * 0.05), WHITE, 0.5)
        cv2.circle(img, (px, py), max(4, int(H * 0.010)), WHITE, -1)

    if d.state == "set_wait":
        text_c(img, "BEHIND THE START LINE", W // 2, int(H * 0.27),
               sc(H, 1.3), mix(WHITE, YELLOW, pulse()), 3)
        text_c(img, "the direction comes only at the cue line", W // 2,
               int(H * 0.34), sc(H, 0.55), STEEL, 1, shadow=False)
    elif d.state == "approach":
        text_c(img, "GO", W // 2, int(H * 0.30), sc(H, 3.0), WHITE, 7)
    elif d.state == "active":
        text_c(img, d.target, W // 2, int(H * 0.30), sc(H, 3.4), YELLOW, 8)
    elif d.state == "result" and d.last_result:
        result, execution = d.last_result
        if result == "hit":
            value_unit(img, f"{d.results[-1]['decision_s'] or 0:.2f}", "s decision",
                       W // 2, int(H * 0.27), 2.4, GREEN, H, thick=6)
            if execution:
                text_c(img, f"cleared the gate in {execution:.2f} s", W // 2,
                       int(H * 0.345), sc(H, 0.55), STEEL, 1, shadow=False)
        elif result == "error":
            text_c(img, "WRONG WAY", W // 2, int(H * 0.28), sc(H, 2.2), RED, 6)
            text_c(img, f"cue was {d.results[-1]['cued']}", W // 2,
                   int(H * 0.355), sc(H, 0.6), STEEL, 2, shadow=False)
        elif result == "miss":
            text_c(img, "NO CUT", W // 2, int(H * 0.28), sc(H, 2.2), RED, 6)
        else:
            text_c(img, "VOID", W // 2, int(H * 0.28), sc(H, 2.0), RED, 6)
    elif d.state == "done":
        value_unit(img, f"{s['correct_cuts']}/{s['reps_completed']}", "correct",
                   W // 2, int(H * 0.26), 2.2, YELLOW, H, thick=5)
        if s["avg_decision_s"] is not None:
            value_unit(img, f"{s['avg_decision_s']:.2f}", "s avg decision",
                       W // 2, int(H * 0.37), 1.2, WHITE, H, thick=3)

    y = int(H * 0.13)
    text(img, "PER SIDE", (int(W * 0.045), y), sc(H, 0.45), STEEL, 1, shadow=False)
    for side in d.SIDES:
        y += int(H * 0.045)
        row = s["per_side"][side]
        avg = row["avg_decision_s"]
        color = STEEL if not row["reps"] else (
            GREEN if row["correct"] == row["reps"] else AMBER)
        tail = f"{avg:.2f} s" if avg else "-"
        text(img, f"{side:<6}{row['correct']}/{row['reps']}  {tail}",
             (int(W * 0.045), y), sc(H, 0.5), color, 2, shadow=False)
    if s["wrong_way_cuts"]:
        text(img, f"wrong way {s['wrong_way_cuts']}", (int(W * 0.045),
             y + int(H * 0.045)), sc(H, 0.5), RED, 2, shadow=False)
    if s["slower_side"]:
        note = f"slower side {s['slower_side']}"
        (tw, _), _ = cv2.getTextSize(note, cv2.FONT_HERSHEY_SIMPLEX, sc(H, 0.5), 2)
        text(img, note, (W - tw - int(W * 0.045), int(H * 0.13)), sc(H, 0.5),
             AMBER, 2, shadow=False)


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
    top = H - 34
    cv2.rectangle(img, (0, top), (W, H), BAR_BG, -1)
    cv2.line(img, (0, top), (W, top), (34, 40, 44), 1)
    x = 22
    fs = sc(H, 0.46)

    def cell(label, color):
        nonlocal x
        text(img, label, (x, H - 11), fs, color, 1, shadow=False)
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
        text(img, note, (W - tw - 22, H - 11), fs, STEEL, 1, shadow=False)


def render(drill, now, joints, age, athlete, session_t0, paused, args,
           quality=None, observed_hz=None):
    W, H = args.width, args.height
    img = _bg(W, H)
    # top bar
    cv2.rectangle(img, (0, 0), (W, 64), BAR_BG, -1)
    cv2.line(img, (0, 65), (W, 65), YELLOW, 2)
    text(img, drill.title, (22, 42), sc(H, 1.0), YELLOW, 2)
    if athlete:
        name_text(img, athlete, (W // 2 - 80, 42), sc(H, 0.9), WHITE, 2)
    clock = now - session_t0
    text(img, f"{progress_text(drill)}   {int(clock // 60):02d}:{int(clock % 60):02d}",
         (W - 330, 42), sc(H, 0.8), STEEL, 2, shadow=False)
    # drill board
    DRAWERS[drill.kind](img, drill, now, joints, args, W, H)

    # Tracking loss is a STATE, not a gap: dim the stage and say so. An armed
    # drill stays armed — only positive evidence of leaving disarms it — so this
    # banner reports the signal, it does not imply the attempt was cancelled.
    if joints is None and drill.state not in ("idle", "done"):
        stage = img[66:H - 34]
        stage[:] = (stage.astype(np.float32) * 0.35).astype(np.uint8)
        text_c(img, "TRACKING LOST", W // 2, int(H * 0.46), sc(H, 1.5),
               mix(RED, WHITE, pulse()), 4)
        text_c(img, "step back into the arena", W // 2, int(H * 0.53),
               sc(H, 0.6), STEEL, 2)

    if paused:
        text_c(img, "PAUSED", W // 2, 100, sc(H, 1.0), RED, 2)
    if drill.state == "idle":
        text_c(img, "PRESS SPACE TO START", W // 2, H // 2, sc(H, 1.4),
               mix(WHITE, YELLOW, pulse()), 3)
    # keys hint sits above the evidence rail so the rail is never crowded out
    text(img, "SPACE start/pause   R restart   F fullscreen   Q quit",
         (22, H - 44), sc(H, 0.45), DGREY, 1, shadow=False)
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
    if k == "round":
        if ev["result"] == "save":
            return f"round {ev['round']} {ev['corner']}: SAVE {ev['reaction_s']:.2f}s"
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
    ap.add_argument("--no-autostart", action="store_true",
                    help="wait for SPACE instead of starting immediately")
    ap.add_argument("--log-dir", default="garage_lab_combined/output/training_logs")
    args = ap.parse_args()

    drill = build_drill(args)
    listener = UDPJointListener(port=args.udp_port)
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

    win = "Project Cam - Training"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, args.width, args.height)
    if args.fullscreen:
        cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    print(f"[DRILL] {drill.title} — athlete: {args.athlete or '(unnamed)'} — "
          f"listening on UDP :{args.udp_port}", flush=True)
    print(f"[DRILL] logs -> {events_path}", flush=True)

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
                cv2.setWindowProperty(
                    win, cv2.WND_PROP_FULLSCREEN,
                    cv2.WINDOW_NORMAL if cur >= 1 else cv2.WINDOW_FULLSCREEN)
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
