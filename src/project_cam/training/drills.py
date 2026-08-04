"""Pure drill state machines for garage training sessions.

Professional grounding for the catalog:

- SINGLE-LEG BALANCE — FIFA 11+ injury-prevention programme, Part 2
  (single-leg stance). Postural-sway magnitude is the standard proxy used in
  professional return-to-play balance testing; the rig's ~4 mm 3D precision
  makes 10-50 mm sway a real measurement.
- PRO-AGILITY SHUTTLE — the 5-10-5 change-of-direction test (NFL combine,
  football academies), scaled to the garage arena (±2 m from a center line
  instead of ±5 yd). Split times come from pelvis line-crossings with linear
  sub-frame interpolation.
- LATERAL LINE HOPS — FIFA 11+ Part 3 "jumping over a line" quick-feet
  plyometric. Counts lateral crossings of the athlete's own start line with
  hysteresis so tracking jitter can't fake a hop.
- SAVE THE CORNERS (GK) — reaction save matrix on the four goal corners.
  HIGH/LOW bands self-calibrate from the keeper's own shoulder/hip height at
  set; every round enforces the professional save -> recover -> set cycle
  before the next cue, and the cue fires after a random delay so it can't be
  anticipated.
- DOWN-UP RECOVERY (GK) — classic goalkeeper conditioning ("down-ups"):
  drop to the floor, return to a held set height, repeat for time. Thresholds
  self-calibrate from standing pelvis height.
- REACTION ZONES — projector-led lateral reaction across three equal garage
  zones, judged by pelvis position. The athlete holds their current zone to
  arm, then moves to a different randomly cued zone after an unpredictable
  delay; tracking loss voids an active attempt instead of inventing a result.

Every drill implements the same duck-typed API (mirrors
scripts/reaction_arena.py, which is live-validated on this rig):

    start(now)                begin from idle/done
    update(now, joints)       advance; joints = {name: (x_mm, y_mm, z_mm)}
                              for the PRIMARY person, or None when lost
    pop_events()              drain per-round result dicts (JSONL-ready)
    summary() / headline()    end-of-session aggregates

All machines are display-agnostic, stdlib-only, and deterministic when given
a seed — unit-testable without cameras, UDP, or cv2. Nothing in this module
touches the launcher: drills are view-only consumers of the pose broadcast.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path
from statistics import fmean, median

from .plausibility import (
    MAX_PELVIS_RISE_MM,
    MIN_DOWN_UP_S,
    MIN_HUMAN_REACTION_S,
    PositionGate,
    is_plausible_reaction,
)

# ----------------------------------------------------------------------------
# joint helpers
# ----------------------------------------------------------------------------

UDP_JOINTS_13 = [
    "nose",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
]


def get_joint(joints, name):
    """(x, y, z) floats for a joint, or None."""
    if not joints:
        return None
    v = joints.get(name)
    if v is None:
        return None
    try:
        return (float(v[0]), float(v[1]), float(v[2]))
    except (TypeError, ValueError, IndexError):
        return None


def midpoint(a, b):
    if a is None or b is None:
        return None
    return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)


def pelvis_mm(joints):
    return midpoint(get_joint(joints, "left_hip"), get_joint(joints, "right_hip"))


def ankle_mid_mm(joints):
    return midpoint(get_joint(joints, "left_ankle"), get_joint(joints, "right_ankle"))


def shoulder_mid_mm(joints):
    return midpoint(get_joint(joints, "left_shoulder"), get_joint(joints, "right_shoulder"))


def zone_of(coord_mm, span_mm, n=3, flip=False):
    """Map a lateral coordinate to a zone index 0..n-1 (reaction_arena semantics)."""
    span = max(1.0, float(span_mm))
    t = min(max(float(coord_mm) / span, 0.0), 0.999)
    idx = int(t * n)
    return (n - 1 - idx) if flip else idx


def _round(value, digits=1):
    return None if value is None else round(float(value), digits)


# ----------------------------------------------------------------------------
# FIELD 1 — single-leg balance (FIFA 11+ Part 2)
# ----------------------------------------------------------------------------

class BalanceDrill:
    kind = "balance"
    title = "SINGLE-LEG BALANCE"
    role = "field"

    def __init__(self, holds=4, hold_s=20.0, rest_s=8.0, countdown_s=5.0,
                 raise_mm=120.0, touch_mm=60.0, track_grace_s=0.7,
                 dz_window_s=0.35, min_raised_s=0.4):
        self.holds = max(1, int(holds))
        self.hold_s = float(hold_s)
        self.rest_s = float(rest_s)
        self.countdown_s = float(countdown_s)
        self.raise_mm = float(raise_mm)
        self.touch_mm = float(touch_mm)
        self.track_grace_s = float(track_grace_s)
        # Debounce against tracking noise: the free-foot height signal is
        # median-filtered over dz_window_s (a single-frame left/right swap
        # flips its sign for one sample — the median ignores it), and a
        # touch-down only counts if the foot was up for at least min_raised_s
        # (a sub-second flap is jitter, not a real foot-down).
        self.dz_window_s = float(dz_window_s)
        self.min_raised_s = float(min_raised_s)
        # Sway is an RMS over accumulated pelvis positions, so ONE triangulation
        # flier dominates it: a live session on 2026-08-01 logged a 31,633 mm
        # excursion in a 6.2 m room and reported 3,986 mm of sway on a leg the
        # athlete was standing on normally. The gate drops what the room cannot
        # contain and counts what it dropped.
        self._gate = PositionGate()
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.hold_idx = 0
        self.samples = []            # (t, pelvis_x, pelvis_y) while single-leg
        self.touchdowns = 0
        self.raised = False
        self.raised_time = 0.0
        self.results = []
        self.waiting_tracking = False
        self._events = []
        self._last_now = None
        self._last_track = None
        self._dz_samples = []        # (t, free-foot height above stance foot)
        self._raised_since = None
        self._gate.reset()

    def stance_leg(self, idx=None):
        idx = self.hold_idx if idx is None else idx
        return "left" if idx % 2 == 0 else "right"

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "countdown"
            self.t_state = now

    def _tracked(self, joints):
        return (pelvis_mm(joints) is not None
                and get_joint(joints, "left_ankle") is not None
                and get_joint(joints, "right_ankle") is not None)

    def update(self, now, joints=None):
        dt = 0.0 if self._last_now is None else max(0.0, now - self._last_now)
        self._last_now = now
        if self._tracked(joints):
            self._last_track = now
        tracked = self._last_track is not None and (now - self._last_track) <= self.track_grace_s

        if self.state == "countdown":
            if now - self.t_state >= self.countdown_s:
                if tracked:
                    self.waiting_tracking = False
                    self.state = "hold"
                    self.t_state = now
                    self.samples = []
                    self.touchdowns = 0
                    self.raised = False
                    self.raised_time = 0.0
                    self._dz_samples = []
                    self._raised_since = None
                    # Per-hold counters: a flier in hold 2 must not describe
                    # hold 3's capture quality.
                    self._gate.reset()
                else:
                    # Loop the countdown until the athlete is in the arena.
                    self.waiting_tracking = True
                    self.t_state = now
        elif self.state == "hold":
            stance = self.stance_leg()
            la = get_joint(joints, "left_ankle")
            ra = get_joint(joints, "right_ankle")
            if la is not None and ra is not None:
                dz_now = (ra[2] - la[2]) if stance == "left" else (la[2] - ra[2])
                self._dz_samples.append((now, dz_now))
            if self._dz_samples:
                self._dz_samples = [(t, v) for t, v in self._dz_samples
                                    if now - t <= self.dz_window_s]
            if self._dz_samples:
                # Median height of the free foot above the stance foot over the
                # window, then a Schmitt trigger. A one-frame L/R swap flips the
                # sign of a single sample — the median never sees it.
                dz = median(v for _, v in self._dz_samples)
                if self.raised and dz < self.touch_mm:
                    self.raised = False
                    if (self._raised_since is not None
                            and now - self._raised_since >= self.min_raised_s):
                        self.touchdowns += 1
                elif not self.raised and dz > self.raise_mm:
                    self.raised = True
                    self._raised_since = now
            if self.raised:
                self.raised_time += dt
                p = pelvis_mm(joints)
                if p is not None and self._gate.accept(now, p):
                    self.samples.append((now, p[0], p[1]))
            if now - self.t_state >= self.hold_s:
                metrics = self._hold_metrics(stance)
                self.results.append(metrics)
                self._events.append(dict(metrics, event="hold"))
                self.hold_idx += 1
                if self.hold_idx >= self.holds:
                    self.state = "done"
                else:
                    self.state = "rest"
                    self.t_state = now
        elif self.state == "rest":
            if now - self.t_state >= self.rest_s:
                self.state = "countdown"
                self.t_state = now
        return self.state

    def _hold_metrics(self, stance):
        sway = max_exc = None
        gate = self._gate.stats()
        # A hold whose capture was mostly garbage has no sway measurement. The
        # surviving samples are too few to describe a 20 s stance and reporting
        # them anyway is how an unreliable hold enters an athlete's baseline
        # looking exactly like a clean one.
        reliable = gate["rejected"] <= gate["accepted"]
        if reliable and len(self.samples) >= 5:
            xs = [s[1] for s in self.samples]
            ys = [s[2] for s in self.samples]
            cx, cy = fmean(xs), fmean(ys)
            d2 = [(x - cx) ** 2 + (y - cy) ** 2 for x, y in zip(xs, ys)]
            sway = math.sqrt(fmean(d2))
            max_exc = math.sqrt(max(d2))
        pct = min(100.0, 100.0 * self.raised_time / self.hold_s) if self.hold_s > 0 else 0.0
        score = None
        if sway is not None:
            score = int(max(0, min(100, round(100 - max(0.0, sway - 8.0) * 2.0
                                              - 10 * self.touchdowns))))
        return {
            "hold": self.hold_idx + 1,
            "stance": stance,
            "sway_rms_mm": _round(sway),
            "max_excursion_mm": _round(max_exc),
            "touchdowns": self.touchdowns,
            "single_leg_pct": _round(pct),
            "score": score,
            # Raw capture facts for this hold, never a verdict: how many pelvis
            # samples the room could not have produced.
            "samples_used": gate["accepted"],
            "samples_rejected": gate["rejected"],
        }

    def live_sway_mm(self, now, window_s=3.0):
        """Rolling sway over the trailing window — for the live HUD meter."""
        track = self.live_sway_track(now, window_s=window_s)
        return None if track is None else track["rms_mm"]

    def live_sway_track(self, now, window_s=3.0, max_points=48):
        """Sway as a 2-D field, not a scalar.

        A single RMS number says how much the athlete is moving but not WHERE —
        and drifting steadily onto the medial edge is a different fault from
        oscillating about a stable centre. Returns the offset of the newest
        sample from the window mean, plus a decimated trail, so the board can
        show direction without recomputing the mean (duplicating it here and in
        the renderer is how the two silently disagree).

        Coordinates are mm in the arena frame: ``dx`` along X, ``dy`` along Y.
        """
        pts = [(x, y) for t, x, y in self.samples if now - t <= window_s]
        if len(pts) < 5:
            return None
        cx = fmean(p[0] for p in pts)
        cy = fmean(p[1] for p in pts)
        rms = math.sqrt(fmean((p[0] - cx) ** 2 + (p[1] - cy) ** 2 for p in pts))
        step = max(1, len(pts) // max(1, max_points))
        trail = [(p[0] - cx, p[1] - cy) for p in pts[::step]]
        last = pts[-1]
        return {
            "rms_mm": rms,
            "offset_mm": (last[0] - cx, last[1] - cy),
            "trail_mm": trail,
        }

    def pop_events(self):
        ev, self._events = self._events, []
        return ev

    def summary(self):
        done = [r for r in self.results if r["sway_rms_mm"] is not None]
        by_leg = {}
        for leg in ("left", "right"):
            vals = [r["sway_rms_mm"] for r in done if r["stance"] == leg]
            by_leg[leg] = _round(fmean(vals)) if vals else None
        scores = [r["score"] for r in done if r["score"] is not None]
        return {
            "holds_completed": len(self.results),
            "holds_measured": len(done),
            "avg_sway_mm": _round(fmean(r["sway_rms_mm"] for r in done)) if done else None,
            "left_sway_mm": by_leg["left"],
            "right_sway_mm": by_leg["right"],
            "touchdowns": sum(r["touchdowns"] for r in self.results),
            "samples_rejected": sum(r.get("samples_rejected", 0)
                                    for r in self.results),
            "avg_score": _round(fmean(scores)) if scores else None,
            "avg_single_leg_pct": _round(fmean(r["single_leg_pct"] for r in self.results))
            if self.results else None,
        }

    def headline(self):
        s = self.summary()
        if s["avg_sway_mm"] is None:
            return "no measured holds"
        return f"sway {s['avg_sway_mm']:.0f} mm avg · {s['touchdowns']} touch-down(s)"


# ----------------------------------------------------------------------------
# FIELD 2 — pro-agility shuttle (garage-scaled 5-10-5)
# ----------------------------------------------------------------------------

class ShuttleDrill:
    kind = "shuttle"
    title = "PRO-AGILITY SHUTTLE"
    role = "field"

    def __init__(self, reps=3, rest_s=20.0, countdown_s=3.0, center_mm=3115.0,
                 half_mm=2000.0, arm_tol_mm=300.0, arm_hold_s=1.0,
                 rep_timeout_s=30.0, lost_abort_s=1.5):
        self.reps = max(1, int(reps))
        self.rest_s = float(rest_s)
        self.countdown_s = float(countdown_s)
        self.center = float(center_mm)
        self.half = float(half_mm)
        self.line_a = self.center + self.half
        self.line_b = self.center - self.half
        self.arm_tol = float(arm_tol_mm)
        self.arm_hold_s = float(arm_hold_s)
        self.rep_timeout_s = float(rep_timeout_s)
        self.lost_abort_s = float(lost_abort_s)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.completed = 0
        self.aborts = 0
        self.results = []            # per successful rep
        self.phase = None            # "to_a" | "to_b" | "home"
        self.go_time = None
        self.last_result = None      # ("ok", total) | ("abort", reason)
        self._split_a = None
        self._split_b = None
        self._prev = None            # (t, coord)
        self._arm_since = None
        self._lost_since = None
        self._events = []

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "arm"
            self.t_state = now

    @staticmethod
    def _cross_time(prev, cur, line, direction):
        """Sub-frame crossing time of `line`, or None. direction=+1 rising."""
        (t0, c0), (t1, c1) = prev, cur
        if direction > 0 and c0 < line <= c1:
            pass
        elif direction < 0 and c0 > line >= c1:
            pass
        else:
            return None
        if c1 == c0:
            return t1
        return t0 + (t1 - t0) * (line - c0) / (c1 - c0)

    def _abort_rep(self, now, reason):
        self.aborts += 1
        self._events.append({"event": "rep_abort", "reason": reason,
                             "after_s": _round(now - self.go_time, 2)})
        self.last_result = ("abort", reason)
        self.state = "rest"
        self.t_state = now

    def update(self, now, joints=None):
        p = pelvis_mm(joints)
        c = None if p is None else p[0]

        if self.state == "arm":
            if c is not None and abs(c - self.center) <= self.arm_tol:
                if self._arm_since is None:
                    self._arm_since = now
                elif now - self._arm_since >= self.arm_hold_s:
                    self.state = "countdown"
                    self.t_state = now
            else:
                self._arm_since = None
        elif self.state == "countdown":
            if now - self.t_state >= self.countdown_s:
                self.state = "run"
                self.phase = "to_a"
                self.go_time = now
                self._split_a = self._split_b = None
                self._prev = None
                self._lost_since = None
        elif self.state == "run":
            if c is None:
                if self._lost_since is None:
                    self._lost_since = now
                elif now - self._lost_since >= self.lost_abort_s:
                    self._abort_rep(now, "tracking lost")
                    return self.state
            else:
                self._lost_since = None
                cur = (now, c)
                if self._prev is not None:
                    if self.phase == "to_a":
                        tc = self._cross_time(self._prev, cur, self.line_a, +1)
                        if tc is not None:
                            self._split_a = tc
                            self.phase = "to_b"
                    elif self.phase == "to_b":
                        tc = self._cross_time(self._prev, cur, self.line_b, -1)
                        if tc is not None:
                            self._split_b = tc
                            self.phase = "home"
                    elif self.phase == "home":
                        tc = self._cross_time(self._prev, cur, self.center, +1)
                        if tc is not None:
                            self._finish_rep(tc)
                            return self.state
                self._prev = cur
            if self.state == "run" and now - self.go_time >= self.rep_timeout_s:
                self._abort_rep(now, "timeout")
        elif self.state == "rest":
            if now - self.t_state >= self.rest_s:
                self.state = "arm"
                self._arm_since = None
        return self.state

    def _finish_rep(self, t_home):
        t_a = self._split_a - self.go_time
        t_b = self._split_b - self._split_a
        t_h = t_home - self._split_b
        total = t_home - self.go_time
        self.completed += 1
        rep = {
            "event": "rep",
            "rep": self.completed,
            "t_out_s": _round(t_a, 3),
            "t_across_s": _round(t_b, 3),
            "t_home_s": _round(t_h, 3),
            "total_s": _round(total, 3),
        }
        self.results.append(rep)
        self._events.append(dict(rep))
        self.last_result = ("ok", total)
        if self.completed >= self.reps:
            self.state = "done"
        else:
            self.state = "rest"
            self.t_state = self.go_time + total

    def pop_events(self):
        ev, self._events = self._events, []
        return ev

    def best_rep(self):
        """The fastest completed rep, or None.

        Exposed so the live board can mark that rep's split boundaries against
        the running clock — the athlete is racing their own best, which is what a
        coach shouts, and a bare elapsed time cannot convey it.
        """
        if not self.results:
            return None
        return min(self.results, key=lambda r: r["total_s"])

    def summary(self):
        totals = [r["total_s"] for r in self.results]
        best = min(totals) if totals else None
        best_rep = next((r for r in self.results if r["total_s"] == best), None)
        return {
            "reps_completed": self.completed,
            "reps_target": self.reps,
            "aborts": self.aborts,
            "best_total_s": best,
            "avg_total_s": _round(fmean(totals), 3) if totals else None,
            "best_splits_s": None if best_rep is None else {
                "out": best_rep["t_out_s"],
                "across": best_rep["t_across_s"],
                "home": best_rep["t_home_s"],
            },
            "course_m": _round(4 * self.half / 1000.0, 1),
        }

    def headline(self):
        s = self.summary()
        if s["best_total_s"] is None:
            return "no completed reps"
        return f"best {s['best_total_s']:.2f} s · {s['reps_completed']}/{s['reps_target']} reps"


# ----------------------------------------------------------------------------
# FIELD 3 — lateral line hops (FIFA 11+ Part 3)
# ----------------------------------------------------------------------------

class LineHopsDrill:
    kind = "line_hops"
    title = "LATERAL LINE HOPS"
    role = "field"

    def __init__(self, sets=3, work_s=20.0, rest_s=10.0, countdown_s=3.0,
                 hys_mm=60.0, calib_s=1.0):
        self.sets = max(1, int(sets))
        self.work_s = float(work_s)
        self.rest_s = float(rest_s)
        self.countdown_s = float(countdown_s)
        self.hys = float(hys_mm)
        self.calib_s = float(calib_s)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.set_idx = 0
        self.line = None             # lateral (y) coord of the start line
        self.crossings = 0
        self.cross_times = []        # monotonic ts of each crossing, current set
        self.results = []
        self.waiting_tracking = False
        self._side = 0               # -1 | 0 | +1 relative to the line
        self._calib = []
        self._events = []

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "countdown"
            self.t_state = now

    def update(self, now, joints=None):
        am = ankle_mid_mm(joints)
        c = None if am is None else am[1]

        if self.state == "countdown":
            remaining = self.countdown_s - (now - self.t_state)
            if c is not None and remaining <= self.calib_s:
                self._calib.append(c)
            if remaining <= 0:
                if len(self._calib) >= 3:
                    # The line is wherever the athlete is standing at GO.
                    self.line = median(self._calib)
                    self.waiting_tracking = False
                    self.state = "work"
                    self.t_state = now
                    self.crossings = 0
                    self.cross_times = []
                    self._side = 0
                else:
                    self.waiting_tracking = True
                    self.t_state = now
                    self._calib = []
        elif self.state == "work":
            if c is not None and self.line is not None:
                if c > self.line + self.hys:
                    new = 1
                elif c < self.line - self.hys:
                    new = -1
                else:
                    new = self._side
                if self._side != 0 and new != self._side:
                    self.crossings += 1
                    # Keep WHEN each hop happened, not just how many. Cadence
                    # decay across a set is the training signal in a plyometric
                    # drill — an athlete who hops 40 times at a collapsing rate
                    # and one who holds rate both score "40", and only the
                    # second is doing the work. The count alone discarded it.
                    self.cross_times.append(now)
                self._side = new
            if now - self.t_state >= self.work_s:
                rate = self.crossings / self.work_s if self.work_s > 0 else 0.0
                result = {
                    "event": "set",
                    "set": self.set_idx + 1,
                    "crossings": self.crossings,
                    "rate_hz": _round(rate, 2),
                }
                result.update(self._cadence_halves())
                self.results.append(result)
                self._events.append(dict(result))
                self.set_idx += 1
                if self.set_idx >= self.sets:
                    self.state = "done"
                else:
                    self.state = "rest"
                    self.t_state = now
        elif self.state == "rest":
            if now - self.t_state >= self.rest_s:
                self.state = "countdown"
                self.t_state = now
                self._calib = []
        return self.state

    def pop_events(self):
        ev, self._events = self._events, []
        return ev

    def _cadence_halves(self):
        """Hop rate in the first vs the second half of the work window.

        Reported as facts plus a drop percentage. Two athletes with the same
        total can have opposite sets — one holding cadence, one collapsing — and
        only the second-half figure separates them. `None` when a half contains
        no hop, because a rate over an empty half is not zero, it is unmeasured.
        """
        half = self.work_s / 2.0
        if half <= 0:
            return {"first_half_rate_hz": None, "second_half_rate_hz": None,
                    "cadence_drop_pct": None}
        first = sum(1 for t in self.cross_times if t - self.t_state < half)
        second = len(self.cross_times) - first
        r1 = _round(first / half, 2) if first else None
        r2 = _round(second / half, 2) if second else None
        drop = None
        if r1 and r2 is not None:
            drop = _round(max(0.0, (r1 - r2) / r1 * 100.0), 1)
        return {"first_half_rate_hz": r1, "second_half_rate_hz": r2,
                "cadence_drop_pct": drop}

    def live_cadence_hz(self, now, window_s=2.0):
        """Hop rate over the trailing window — what the athlete is doing NOW,
        as opposed to the set average, which hides a collapse until the end."""
        if window_s <= 0:
            return None
        recent = [t for t in self.cross_times if now - t <= window_s]
        if len(recent) < 2:
            return None
        return len(recent) / window_s

    def summary(self):
        total = sum(r["crossings"] for r in self.results)
        rates = [r["rate_hz"] for r in self.results]
        drops = [r["cadence_drop_pct"] for r in self.results
                 if r.get("cadence_drop_pct") is not None]
        return {
            "sets_completed": len(self.results),
            "total_crossings": total,
            "best_rate_hz": max(rates) if rates else None,
            "avg_rate_hz": _round(fmean(rates), 2) if rates else None,
            "avg_cadence_drop_pct": _round(fmean(drops), 1) if drops else None,
        }

    def headline(self):
        s = self.summary()
        if not s["sets_completed"]:
            return "no completed sets"
        return f"{s['total_crossings']} hops · best {s['best_rate_hz']:.1f}/s"


# ----------------------------------------------------------------------------
# GK 1 — save the corners (reaction matrix, self-calibrated zones)
# ----------------------------------------------------------------------------

class GkSaveDrill:
    kind = "gk_save"
    title = "SAVE THE CORNERS"
    role = "gk"

    def __init__(self, rounds=10, arena_y_mm=3050.0, cue_timeout_s=2.5,
                 result_s=1.2, set_hold_s=0.8, cue_delay_min_s=0.5,
                 cue_delay_max_s=1.5, high_off_mm=150.0, low_frac=0.6,
                 flip=False, seed=None,
                 min_reaction_s=MIN_HUMAN_REACTION_S):
        self.rounds = max(1, int(rounds))
        self.arena_y = float(arena_y_mm)
        self.cue_timeout_s = float(cue_timeout_s)
        self.result_s = float(result_s)
        self.set_hold_s = float(set_hold_s)
        self.cue_delay = (float(cue_delay_min_s), float(cue_delay_max_s))
        self.high_off = float(high_off_mm)
        self.low_frac = float(low_frac)
        self.flip = bool(flip)
        # A "save" logged at 0.034 s on 2026-08-01 was the keeper's wrist already
        # sitting inside the corner when the cue fired. Two independent guards
        # follow from that: never cue a corner that is already satisfied, and
        # never call a sub-reaction-floor detection a save.
        self.min_reaction_s = float(min_reaction_s)
        # Kept for audit: one Random drives BOTH the corner choice and the cue
        # delay, so a pinned seed makes the whole sequence repeatable and
        # defeats the anti-anticipation design. Recorded, never fingerprinted.
        self.seed = seed
        self.rng = random.Random(seed)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.round_idx = 0
        self.saves = 0
        self.anticipated = 0
        self.voided_rounds = 0
        self.results = []            # {corner, result, reaction_s}
        self.target = None           # (side 0|2, high bool)
        self.shoulder_ref = None
        self.hip_ref = None
        self.cue_at = None
        self.go_time = None
        self.last_result = None      # ("save", rt) | ("miss", None)
        self._set_since = None
        self._calib_sh = []
        self._calib_hip = []
        self._events = []

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "set_wait"
            self.t_state = now

    def side_of(self, y_mm):
        return zone_of(y_mm, self.arena_y, 3, self.flip)

    def corner_name(self, target=None):
        target = self.target if target is None else target
        if target is None:
            return None
        side, high = target
        return ("HIGH" if high else "LOW") + "-" + ("LEFT" if side == 0 else "RIGHT")

    def _pick_target(self, joints=None):
        """A corner that is neither the last one nor already satisfied.

        Cueing a corner the keeper's wrist already occupies produces an instant
        "save" with a superhuman reaction time — which is exactly what the
        2026-08-01 log contains. Returns None when every candidate is already
        satisfied, and the caller voids the round rather than scoring it.
        """
        prev = self.target
        t = None
        for _ in range(8):
            t = (self.rng.choice((0, 2)), self.rng.random() < 0.5)
            if t != prev and self._wrist_in_target(joints, t) is None:
                return t
        if t is not None and self._wrist_in_target(joints, t) is not None:
            return None
        return t

    def _wrist_in_target(self, joints, target=None):
        target = self.target if target is None else target
        if target is None or self.shoulder_ref is None or self.hip_ref is None:
            return None
        side, high = target
        for name in ("left_wrist", "right_wrist"):
            w = get_joint(joints, name)
            if w is None:
                continue
            if self.side_of(w[1]) != side:
                continue
            if high:
                if w[2] > self.shoulder_ref + self.high_off:
                    return name
            else:
                if w[2] < self.hip_ref * self.low_frac:
                    return name
        return None

    def update(self, now, joints=None):
        p = pelvis_mm(joints)
        in_center = p is not None and self.side_of(p[1]) == 1

        if self.state == "set_wait":
            if in_center:
                if self._set_since is None:
                    self._set_since = now
                    self._calib_sh = []
                    self._calib_hip = []
                sh = shoulder_mid_mm(joints)
                hp = pelvis_mm(joints)
                if sh is not None:
                    self._calib_sh.append(sh[2])
                if hp is not None:
                    self._calib_hip.append(hp[2])
                if (now - self._set_since >= self.set_hold_s
                        and len(self._calib_sh) >= 3 and len(self._calib_hip) >= 3):
                    # Freeze this round's HIGH/LOW bands to the keeper's own frame.
                    self.shoulder_ref = median(self._calib_sh)
                    self.hip_ref = median(self._calib_hip)
                    self.state = "armed"
                    self.cue_at = now + self.rng.uniform(*self.cue_delay)
            else:
                self._set_since = None
        elif self.state == "armed":
            if p is not None and self.side_of(p[1]) != 1:
                # Positively left the set position before the cue — re-arm.
                # (A momentary tracking dropout must NOT reset the set.)
                self.state = "set_wait"
                self._set_since = None
            elif now >= self.cue_at:
                target = self._pick_target(joints)
                if target is None:
                    # Every corner was already occupied at cue time — there is
                    # no reaction to measure, so nothing is scored.
                    self._record_void(now, "pre_positioned")
                    return self.state
                self.target = target
                self.state = "active"
                self.go_time = now
        elif self.state == "active":
            wrist = self._wrist_in_target(joints)
            if wrist is not None:
                rt = now - self.go_time
                if is_plausible_reaction(rt, self.min_reaction_s):
                    self.saves += 1
                    self._record(now, "save", rt, wrist)
                else:
                    # Movement that cannot have been a response to this cue:
                    # recorded as its own failure mode, never as a save and
                    # never in a reaction average.
                    self.anticipated += 1
                    self._record(now, "anticipated", rt, wrist)
            elif now - self.go_time >= self.cue_timeout_s:
                self._record(now, "miss", None, None)
        elif self.state == "result":
            if now - self.t_state >= self.result_s:
                self.round_idx += 1
                if self.round_idx >= self.rounds:
                    self.state = "done"
                else:
                    self.state = "set_wait"
                    self._set_since = None
        return self.state

    def _record(self, now, result, rt, wrist):
        corner = self.corner_name()
        row = {"corner": corner, "result": result, "reaction_s": _round(rt, 3)}
        self.results.append(row)
        self._events.append({"event": "round", "round": self.round_idx + 1,
                             "wrist": wrist, **row})
        self.last_result = (result, rt)
        self.state = "result"
        self.t_state = now

    def _record_void(self, now, reason):
        """A round with nothing to measure: it consumes no round and scores none."""
        self.voided_rounds += 1
        self._events.append({"event": "round_void", "round": self.round_idx + 1,
                             "corner": None, "reason": reason})
        self.last_result = ("void", None)
        self.target = None
        self.state = "result"
        self.t_state = now

    def pop_events(self):
        ev, self._events = self._events, []
        return ev

    @staticmethod
    def _save_reactions(rows):
        """Reaction times of genuine saves only — an anticipation is not one."""
        return [r["reaction_s"] for r in rows
                if r["result"] == "save" and r["reaction_s"] is not None]

    def per_corner(self):
        out = {}
        for high in (True, False):
            for side in (0, 2):
                name = self.corner_name((side, high))
                rows = [r for r in self.results if r["corner"] == name]
                rts = self._save_reactions(rows)
                out[name] = {
                    "rounds": len(rows),
                    "saves": sum(1 for r in rows if r["result"] == "save"),
                    "anticipated": sum(1 for r in rows
                                       if r["result"] == "anticipated"),
                    "avg_reaction_s": _round(fmean(rts), 3) if rts else None,
                }
        return out

    def summary(self):
        rts = self._save_reactions(self.results)
        corners = self.per_corner()
        weakest = None
        scored = [(name, c) for name, c in corners.items() if c["rounds"] > 0]
        if scored:
            weakest = min(
                scored,
                key=lambda kv: (kv[1]["saves"] / kv[1]["rounds"],
                                -(kv[1]["avg_reaction_s"] or 99.0)),
            )[0]
        return {
            "rounds_completed": len(self.results),
            "saves": self.saves,
            "save_pct": _round(100.0 * self.saves / len(self.results))
            if self.results else None,
            "avg_reaction_s": _round(fmean(rts), 3) if rts else None,
            "best_reaction_s": _round(min(rts), 3) if rts else None,
            "per_corner": corners,
            "weakest_corner": weakest,
            # Failure modes, kept separate from the score: movement that beat the
            # reaction floor, and rounds that could not be cued at all.
            "anticipated": self.anticipated,
            "voided_rounds": self.voided_rounds,
        }

    def headline(self):
        s = self.summary()
        if not s["rounds_completed"]:
            return "no completed rounds"
        if s["avg_reaction_s"] is None:
            return f"{s['saves']}/{s['rounds_completed']} saves"
        return (f"{s['saves']}/{s['rounds_completed']} saves · "
                f"avg {s['avg_reaction_s']:.2f} s")


# ----------------------------------------------------------------------------
# GK 2 — down-up recovery (goalkeeper conditioning)
# ----------------------------------------------------------------------------

class GkUpDownDrill:
    kind = "gk_updown"
    title = "DOWN-UP RECOVERY"
    role = "gk"

    def __init__(self, duration_s=30.0, countdown_s=5.0, down_frac=0.55,
                 up_frac=0.85, up_hold_s=0.3, down_hold_s=0.25,
                 min_recovery_s=MIN_DOWN_UP_S):
        self.duration_s = float(duration_s)
        self.countdown_s = float(countdown_s)
        self.down_frac = float(down_frac)
        self.up_frac = float(up_frac)
        self.up_hold_s = float(up_hold_s)
        # The up phase already required a sustained hold; the down phase did not,
        # so a single pelvis-height flier crossing both thresholds logged a
        # complete down-up. A live session on 2026-07-31 averaged 0.10 s per rep
        # that way. Down now needs the same positive evidence as up, and a rep
        # faster than a body can physically perform is voided rather than scored.
        self.down_hold_s = float(down_hold_s)
        self.min_recovery_s = float(min_recovery_s)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.stand_z = None
        self.reps = 0
        self.voided_reps = 0
        self.recoveries = []
        self.phase = "up"
        self.waiting_tracking = False
        self._calib = []
        self._t_down = None
        self._down_since = None
        self._up_since = None
        self._events = []

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "countdown"
            self.t_state = now

    @property
    def down_thresh(self):
        return None if self.stand_z is None else self.down_frac * self.stand_z

    @property
    def up_thresh(self):
        return None if self.stand_z is None else self.up_frac * self.stand_z

    def update(self, now, joints=None):
        p = pelvis_mm(joints)
        z = None if p is None else p[2]

        if self.state == "countdown":
            if z is not None:
                self._calib.append(z)
            if now - self.t_state >= self.countdown_s:
                if len(self._calib) >= 5:
                    # Personal thresholds from standing pelvis height.
                    self.stand_z = median(self._calib)
                    self.waiting_tracking = False
                    self.state = "work"
                    self.t_state = now
                    self.phase = "up"
                else:
                    self.waiting_tracking = True
                    self.t_state = now
                    self._calib = []
        elif self.state == "work":
            if z is not None and self.stand_z is not None:
                if self.phase == "up":
                    if z < self.down_thresh:
                        # The down has to be HELD, exactly as the up is. The
                        # recovery clock still starts at the first sample below
                        # the threshold, which is the honest start of the drop.
                        if self._down_since is None:
                            self._down_since = now
                        elif now - self._down_since >= self.down_hold_s:
                            self.phase = "down"
                            self._t_down = self._down_since
                            self._down_since = None
                            self._up_since = None
                    else:
                        self._down_since = None
                elif self.phase == "down":
                    if z >= self.up_thresh:
                        if self._up_since is None:
                            self._up_since = now
                        elif now - self._up_since >= self.up_hold_s:
                            recovery = self._up_since - self._t_down
                            if recovery >= self.min_recovery_s:
                                self.reps += 1
                                self.recoveries.append(recovery)
                                self._events.append({
                                    "event": "rep",
                                    "rep": self.reps,
                                    "recovery_s": _round(recovery, 2),
                                })
                            else:
                                self.voided_reps += 1
                                self._events.append({
                                    "event": "rep_void",
                                    "recovery_s": _round(recovery, 2),
                                    "reason": "implausible_recovery",
                                })
                            self.phase = "up"
                    else:
                        self._up_since = None
            if now - self.t_state >= self.duration_s:
                self.state = "done"
        return self.state

    def pop_events(self):
        ev, self._events = self._events, []
        return ev

    def summary(self):
        return {
            "reps": self.reps,
            "voided_reps": self.voided_reps,
            "duration_s": self.duration_s,
            "reps_per_min": _round(60.0 * self.reps / self.duration_s)
            if self.duration_s > 0 else None,
            "avg_recovery_s": _round(fmean(self.recoveries), 2)
            if self.recoveries else None,
            "best_recovery_s": _round(min(self.recoveries), 2)
            if self.recoveries else None,
        }

    def headline(self):
        s = self.summary()
        if not s["reps"]:
            return "no completed reps"
        if s["avg_recovery_s"] is None:
            return f"{s['reps']} down-ups"
        return f"{s['reps']} down-ups · avg up {s['avg_recovery_s']:.2f} s"


# ----------------------------------------------------------------------------
# FIELD 4 — projector reaction zones (pelvis-scored lateral movement)
# ----------------------------------------------------------------------------

class ReactionZonesDrill:
    """Lateral reaction between three equal zones of the configured arena.

    The arena width is deliberately required: the board must pass its
    ``--arena-y-mm`` configuration rather than this state machine hiding a
    garage-specific constant. Targets are the geometric centres of each zone.
    ``wall_margin_mm`` is a validated minimum clearance for the two outer
    centres; an unsafe width/margin pair is rejected rather than moving a
    target away from its zone centre.
    """

    kind = "reaction_zones"
    title = "REACTION ZONES"
    role = "field"
    ZONE_NAMES = ("LEFT", "CENTER", "RIGHT")

    def __init__(self, arena_y_mm, rounds=10, wall_margin_mm=500.0,
                 arm_hold_s=0.6, cue_timeout_s=3.0, result_s=1.2,
                 cue_delay_min_s=0.5, cue_delay_max_s=1.5, seed=None,
                 min_reaction_s=MIN_HUMAN_REACTION_S):
        self.min_reaction_s = float(min_reaction_s)
        self.arena_y_mm = float(arena_y_mm)
        self.wall_margin_mm = float(wall_margin_mm)
        if not math.isfinite(self.arena_y_mm) or self.arena_y_mm <= 0:
            raise ValueError("arena width must be a positive finite value")
        if not math.isfinite(self.wall_margin_mm) or self.wall_margin_mm < 0:
            raise ValueError("wall margin must be a non-negative finite value")
        outer_centre_clearance = self.arena_y_mm / 6.0
        if self.wall_margin_mm > outer_centre_clearance:
            raise ValueError(
                f"wall margin {self.wall_margin_mm:g} mm exceeds the outer "
                f"zone-centre clearance {outer_centre_clearance:g} mm")

        self.rounds = max(1, int(rounds))
        self.arm_hold_s = float(arm_hold_s)
        self.cue_timeout_s = float(cue_timeout_s)
        self.result_s = float(result_s)
        self.cue_delay_min_s = float(cue_delay_min_s)
        self.cue_delay_max_s = float(cue_delay_max_s)
        if self.cue_delay_min_s < 0 or self.cue_delay_max_s < self.cue_delay_min_s:
            raise ValueError("cue delay range must be non-negative and ordered")
        # Audit-only: one Random drives both cue delay and target choice. A
        # pinned seed makes the sequence learnable, so profiles cannot set it.
        self.seed = seed
        self.rng = random.Random(seed)
        self.reset()

    @property
    def zone_bounds_mm(self):
        width = self.arena_y_mm / 3.0
        return tuple((i * width, (i + 1) * width) for i in range(3))

    @property
    def target_centres_mm(self):
        return tuple((lo + hi) / 2.0 for lo, hi in self.zone_bounds_mm)

    def zone_name(self, zone):
        return self.ZONE_NAMES[int(zone)]

    def side_of(self, y_mm):
        return zone_of(y_mm, self.arena_y_mm, 3)

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.round_idx = 0
        self.hits = 0
        self.voided_rounds = 0
        self.results = []
        self.target = None
        self.arm_zone = None
        self.cue_at = None
        self.go_time = None
        self.last_result = None
        self._candidate_zone = None
        self._present_since = None
        self._events = []

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self._begin_set_wait(now)

    def _begin_set_wait(self, now, observed_zone=None):
        self.state = "set_wait"
        self.t_state = now
        self.target = None
        self.arm_zone = None
        self.cue_at = None
        self.go_time = None
        self._candidate_zone = observed_zone
        self._present_since = now if observed_zone is not None else None

    def _pick_target(self):
        choices = tuple(zone for zone in range(3) if zone != self.arm_zone)
        return self.rng.choice(choices)

    def update(self, now, joints=None):
        p = pelvis_mm(joints)
        observed_zone = None if p is None else self.side_of(p[1])

        if self.state == "set_wait":
            if observed_zone is None:
                self._candidate_zone = None
                self._present_since = None
            elif observed_zone != self._candidate_zone:
                self._candidate_zone = observed_zone
                self._present_since = now
            elif (self._present_since is not None
                  and now - self._present_since >= self.arm_hold_s):
                self.arm_zone = observed_zone
                self.state = "armed"
                self.t_state = now
                self.cue_at = now + self.rng.uniform(
                    self.cue_delay_min_s, self.cue_delay_max_s)
        elif self.state == "armed":
            if observed_zone is None:
                # Absence is not evidence that the athlete left the held zone.
                return self.state
            if observed_zone != self.arm_zone:
                # Positive evidence of an early move: begin a fresh hold in the
                # newly observed zone.
                self._begin_set_wait(now, observed_zone)
            elif now >= self.cue_at:
                self.target = self._pick_target()
                self.state = "active"
                self.t_state = now
                self.go_time = now
        elif self.state == "active":
            if observed_zone is None:
                self._record(now, "void", None, "tracking_lost")
            else:
                elapsed = now - self.go_time
                if observed_zone == self.target and not is_plausible_reaction(
                        elapsed, self.min_reaction_s):
                    # The pelvis cannot have crossed a whole zone this fast; a
                    # lateral tracking flier can. No result is invented from it.
                    self._record(now, "void", None, "implausible_reaction")
                elif observed_zone == self.target and elapsed <= self.cue_timeout_s:
                    self._record(now, "hit", elapsed, None)
                elif elapsed >= self.cue_timeout_s:
                    self._record(now, "miss", None, None)
        elif self.state == "result":
            if now - self.t_state >= self.result_s:
                if self.round_idx >= self.rounds:
                    self.state = "done"
                else:
                    self._begin_set_wait(now)
        return self.state

    def _record(self, now, result, reaction_s, reason):
        target_name = self.zone_name(self.target)
        target_centre = _round(self.target_centres_mm[self.target], 1)
        if result == "void":
            self.voided_rounds += 1
            event = {
                "event": "round_void",
                "round": self.round_idx + 1,
                "zone": target_name,
                "target_center_mm": target_centre,
                "reason": reason,
            }
        else:
            self.round_idx += 1
            if result == "hit":
                self.hits += 1
            row = {
                "round": self.round_idx,
                "zone": target_name,
                "target_center_mm": target_centre,
                "result": result,
                "reaction_s": _round(reaction_s, 3),
            }
            self.results.append(row)
            event = {"event": "round", **row}
        self._events.append(event)
        self.last_result = (result, reaction_s)
        self.state = "result"
        self.t_state = now

    def pop_events(self):
        events, self._events = self._events, []
        return events

    def per_zone(self):
        out = {}
        for name in self.ZONE_NAMES:
            rows = [row for row in self.results if row["zone"] == name]
            reactions = [
                row["reaction_s"] for row in rows
                if row["reaction_s"] is not None
            ]
            out[name] = {
                "rounds": len(rows),
                "hits": len(reactions),
                "avg_reaction_s": _round(fmean(reactions), 3)
                if reactions else None,
            }
        return out

    def summary(self):
        reactions = [
            row["reaction_s"] for row in self.results
            if row["reaction_s"] is not None
        ]
        zones = self.per_zone()
        scored = [(name, row) for name, row in zones.items() if row["rounds"]]
        weakest = None
        if scored:
            weakest = min(
                scored,
                key=lambda item: (
                    item[1]["hits"] / item[1]["rounds"],
                    -(item[1]["avg_reaction_s"] or 99.0),
                ),
            )[0]
        return {
            "rounds_completed": len(self.results),
            "rounds_target": self.rounds,
            "hits_in_timeout": self.hits,
            "avg_reaction_s": _round(fmean(reactions), 3)
            if reactions else None,
            "per_zone": zones,
            "weakest_zone": weakest,
            "voided_rounds": self.voided_rounds,
        }

    def headline(self):
        summary = self.summary()
        if not summary["rounds_completed"]:
            return "no completed rounds"
        if summary["avg_reaction_s"] is None:
            return (
                f"{summary['hits_in_timeout']}/{summary['rounds_completed']} hits"
            )
        return (
            f"{summary['hits_in_timeout']}/{summary['rounds_completed']} hits · "
            f"avg {summary['avg_reaction_s']:.2f} s"
        )


# ----------------------------------------------------------------------------
# registry + session records
# ----------------------------------------------------------------------------

# ----------------------------------------------------------------------------
# FIELD 4 — countermovement jump (neuromuscular load monitoring)
# ----------------------------------------------------------------------------

class CmjDrill:
    """Repeated countermovement jumps, measured as PELVIS RISE.

    The countermovement jump is the most widely used neuromuscular monitoring
    test in professional football because a drop in jump output tracks
    accumulated fatigue. It also needs no floor space at all, which is what
    makes it viable in a 6 x 3 m garage.

    Deliberate honesty about the quantity: this reports the rise of the pelvis
    above its own standing height, NOT a force-plate or flight-time jump
    height. The two correlate but are not the same number, so the metric is
    named ``pelvis_rise_mm`` and must never be reported as "jump height".
    Compare an athlete against their own baseline, not against published
    force-plate norms.
    """

    kind = "cmj"
    title = "COUNTERMOVEMENT JUMP"
    role = "field"

    def __init__(self, jumps=5, countdown_s=5.0, calib_s=1.5, dip_mm=60.0,
                 rise_mm=80.0, settle_mm=45.0, track_grace_s=0.7,
                 min_air_s=0.12, max_rise_mm=MAX_PELVIS_RISE_MM):
        # The apex is a running max over pelvis height, so a single upward flier
        # becomes a permanent personal best: a live session logged a 751 mm
        # pelvis rise, past the elite range. Such a jump is still recorded — the
        # athlete did jump — but flagged and kept out of best/avg.
        self.max_rise_mm = float(max_rise_mm)
        self.jumps = max(1, int(jumps))
        self.countdown_s = float(countdown_s)
        self.calib_s = float(calib_s)
        self.dip_mm = float(dip_mm)
        self.rise_mm = float(rise_mm)
        self.settle_mm = float(settle_mm)
        self.track_grace_s = float(track_grace_s)
        self.min_air_s = float(min_air_s)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.stand_z = None
        self.results = []
        self.last_result = None
        self.apex_z = None
        self.phase = "settled"
        self._calib = []
        self._events = []
        self._last_track = None
        self._t_dip = None

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "countdown"
            self.t_state = now

    @property
    def completed(self):
        return len(self.results)

    def update(self, now, joints=None):
        pelvis = pelvis_mm(joints)
        if pelvis is not None:
            self._last_track = now
        tracked = (self._last_track is not None
                   and (now - self._last_track) <= self.track_grace_s)
        z = None if pelvis is None else pelvis[2]

        if self.state == "countdown":
            if z is not None and (now - self.t_state) >= (self.countdown_s - self.calib_s):
                self._calib.append(z)
            if now - self.t_state >= self.countdown_s:
                if tracked and len(self._calib) >= 3:
                    self.stand_z = median(self._calib)
                    self.state = "work"
                    self.t_state = now
                    self.phase = "settled"
                else:
                    # Loop the countdown until the athlete is actually standing
                    # in the arena — autostart must not calibrate on nothing.
                    self._calib = []
                    self.t_state = now
        elif self.state == "work":
            if z is None or self.stand_z is None:
                return
            dz = z - self.stand_z
            if self.phase == "settled":
                if dz <= -self.dip_mm:
                    self.phase = "dip"
                    self._t_dip = now
            elif self.phase == "dip":
                if dz >= self.rise_mm:
                    self.phase = "air"
                    self.apex_z = z
                elif dz > -self.settle_mm and self._t_dip is not None \
                        and (now - self._t_dip) > 2.0:
                    # A dip that never became a jump: abandon it rather than
                    # waiting forever in a half-state.
                    self.phase = "settled"
                    self._t_dip = None
            elif self.phase == "air":
                self.apex_z = max(self.apex_z or z, z)
                airborne = self._t_dip is not None and (now - self._t_dip) >= self.min_air_s
                if dz < self.settle_mm and airborne:
                    rise = float(self.apex_z - self.stand_z)
                    self._record(now, rise)
                    self.phase = "settled"
                    self.apex_z = None
                    self._t_dip = None

    def _record(self, now, rise_mm):
        index = len(self.results) + 1
        row = {"jump": index, "pelvis_rise_mm": _round(rise_mm, 1)}
        if float(rise_mm) > self.max_rise_mm:
            row["implausible"] = True
        self.results.append(row)
        self.last_result = rise_mm
        self._events.append({"event": "jump", **row})
        if len(self.results) >= self.jumps:
            self.state = "done"
            self.t_state = now

    def pop_events(self):
        out, self._events = self._events, []
        return out

    def rises(self):
        """Measured rises only — a flagged jump is evidence, not a measurement."""
        return [r["pelvis_rise_mm"] for r in self.results
                if r["pelvis_rise_mm"] is not None and not r.get("implausible")]

    def summary(self):
        rises = self.rises()
        third = max(1, len(rises) // 3)
        drop = None
        if len(rises) >= 3:
            first, last = fmean(rises[:third]), fmean(rises[-third:])
            if first > 0:
                drop = _round((last - first) / first * 100.0, 1)
        return {
            "jumps_completed": len(self.results),
            "jumps_target": self.jumps,
            "implausible_jumps": sum(1 for r in self.results
                                     if r.get("implausible")),
            "best_pelvis_rise_mm": _round(max(rises), 1) if rises else None,
            "avg_pelvis_rise_mm": _round(fmean(rises), 1) if rises else None,
            "drop_off_pct": drop,
            "standing_pelvis_mm": _round(self.stand_z, 1) if self.stand_z else None,
        }

    def headline(self):
        s = self.summary()
        if not s["jumps_completed"]:
            return "no completed jumps"
        text = f"best {s['best_pelvis_rise_mm']:.0f} mm pelvis rise"
        if s["drop_off_pct"] is not None:
            text += f" | drop-off {s['drop_off_pct']:+.0f}%"
        return text


# ----------------------------------------------------------------------------
# FIELD 5 — single-leg hop limb symmetry
# ----------------------------------------------------------------------------

class HopSymmetryDrill:
    """Alternating single-leg hops for distance, scored as limb symmetry.

    Limb symmetry on a battery of single-leg hop tests is the standard criterion
    used to inform return-to-sport decisions, conventionally at an index of 90%
    or better. Two honest caveats travel with that number and are surfaced in
    the summary rather than hidden: fewer than half of youth athletes reach 90%,
    and symmetry can be met while both limbs are weak, because the uninvolved
    limb also decays during a layoff. So this reports the index AND both raw
    distances, and it is a screening signal, never a clearance decision.

    Distance is measured as horizontal pelvis travel between a held single-leg
    stance and a stabilised landing — no takeoff detection, which keeps it
    robust to the jitter a 10 fps rig produces at the moment of push-off.
    """

    kind = "hop_symmetry"
    title = "SINGLE-LEG HOP SYMMETRY"
    role = "field"
    LEGS = ("left", "right")

    def __init__(self, hops_per_leg=3, countdown_s=5.0, arm_hold_s=1.0,
                 settle_hold_s=1.2, still_mm=70.0, min_hop_mm=250.0,
                 start_band_mm=350.0, track_grace_s=0.7):
        self.hops_per_leg = max(1, int(hops_per_leg))
        self.countdown_s = float(countdown_s)
        self.arm_hold_s = float(arm_hold_s)
        self.settle_hold_s = float(settle_hold_s)
        self.still_mm = float(still_mm)
        self.min_hop_mm = float(min_hop_mm)
        # Every hop is measured from ONE start line, and the athlete has to come
        # back to it to arm the next attempt. Without this the walk back to the
        # line is itself a large displacement and gets recorded as a hop of the
        # other leg — verified by driving the machine, not by inspection.
        self.start_band_mm = float(start_band_mm)
        self.track_grace_s = float(track_grace_s)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.attempt = 0
        self.results = []
        self.last_result = None
        self._events = []
        self._last_track = None
        self._anchor = None
        self._still_since = None
        self._land_ref = None
        self.start_x = None

    def leg(self, attempt=None):
        attempt = self.attempt if attempt is None else attempt
        return self.LEGS[attempt % 2]

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "countdown"
            self.t_state = now

    def update(self, now, joints=None):
        pelvis = pelvis_mm(joints)
        if pelvis is not None:
            self._last_track = now
        tracked = (self._last_track is not None
                   and (now - self._last_track) <= self.track_grace_s)
        x = None if pelvis is None else pelvis[0]

        if self.state == "countdown":
            if now - self.t_state >= self.countdown_s:
                if tracked:
                    self.state = "arm"
                    self.t_state = now
                    self._still_since = None
                else:
                    self.t_state = now
        elif self.state == "arm":
            # Stand still ON the start line to arm. The line is set once, by the
            # first arming position, so all hops share one origin.
            if x is None:
                self._still_since = None
                return
            if self.start_x is None:
                self.start_x = x
            if abs(x - self.start_x) > self.start_band_mm:
                # Still walking back from the last landing — cannot arm yet, and
                # that travel must never be mistaken for a hop.
                self._still_since = None
                self._anchor = None
                return
            if self._anchor is None or abs(x - self._anchor) > self.still_mm:
                self._anchor = x
                self._still_since = now
            elif now - self._still_since >= self.arm_hold_s:
                self.state = "hop"
                self.t_state = now
                self._land_ref = None
                self._still_since = None
        elif self.state == "hop":
            if x is None:
                return
            # Distance is measured from the START LINE, so returning toward it
            # shrinks the displacement instead of accumulating a phantom hop.
            travelled = abs(x - self.start_x)
            if travelled < self.min_hop_mm:
                return
            # Landed far enough — now require it to stay put, which is the
            # stabilisation half of the test.
            if self._land_ref is None or abs(x - self._land_ref) > self.still_mm:
                self._land_ref = x
                self._still_since = now
            elif now - self._still_since >= self.settle_hold_s:
                self._record(now, abs(self._land_ref - self.start_x),
                             now - self.t_state)

    def _record(self, now, distance_mm, settle_s):
        row = {
            "attempt": self.attempt + 1,
            "leg": self.leg(),
            "distance_mm": _round(distance_mm, 1),
            "stabilise_s": _round(settle_s, 2),
        }
        self.results.append(row)
        self.last_result = row
        self._events.append({"event": "hop", **row})
        self.attempt += 1
        self._anchor = None
        self._land_ref = None
        self._still_since = None
        if self.attempt >= self.hops_per_leg * 2:
            self.state = "done"
        else:
            self.state = "arm"
        self.t_state = now

    def pop_events(self):
        out, self._events = self._events, []
        return out

    def per_leg(self):
        out = {}
        for leg in self.LEGS:
            values = [r["distance_mm"] for r in self.results if r["leg"] == leg]
            out[leg] = {
                "hops": len(values),
                "best_mm": _round(max(values), 1) if values else None,
                "avg_mm": _round(fmean(values), 1) if values else None,
            }
        return out

    def summary(self):
        legs = self.per_leg()
        best = [legs[leg]["best_mm"] for leg in self.LEGS]
        lsi = None
        if all(v is not None and v > 0 for v in best):
            lsi = _round(min(best) / max(best) * 100.0, 1)
        weaker = None
        if all(v is not None for v in best) and best[0] != best[1]:
            weaker = self.LEGS[0] if best[0] < best[1] else self.LEGS[1]
        return {
            "hops_completed": len(self.results),
            "hops_target": self.hops_per_leg * 2,
            "per_leg": legs,
            "limb_symmetry_pct": lsi,
            "weaker_leg": weaker,
            # A screening signal, not a clearance decision — see the class
            # docstring. Both raw distances stay in per_leg for that reason.
            "symmetry_reference_pct": 90.0,
        }

    def headline(self):
        s = self.summary()
        if s["limb_symmetry_pct"] is None:
            return "symmetry needs both legs"
        text = f"symmetry {s['limb_symmetry_pct']:.0f}%"
        if s["weaker_leg"]:
            text += f" | weaker {s['weaker_leg']}"
        return text


# ----------------------------------------------------------------------------
# FIELD 6 — reactive change of direction
# ----------------------------------------------------------------------------

class ReactiveCutDrill:
    """Run forward, get a direction only at the last moment, cut.

    This is the drill a set of timing gates physically cannot run. Reactive
    agility — changing direction in response to an unplanned stimulus — is a
    quality largely independent of pre-planned change-of-direction speed, and it
    is the one that better separates skill levels in adolescent players. A gate
    can time a rehearsed shuttle; only a cue fired at the moment of commitment
    measures the decision.

    Two quantities are reported separately, because they train differently:
    ``decision_s`` (cue to the first committed lateral movement) and
    ``execution_s`` (cue to clearing the gate). A wrong-way cut is recorded as an
    error, never silently dropped.
    """

    kind = "reactive_cut"
    title = "REACTIVE CUT"
    role = "field"
    SIDES = ("LEFT", "RIGHT")

    def __init__(self, arena_x_mm, arena_y_mm, reps=6, countdown_s=5.0,
                 arm_hold_s=0.8, commit_mm=180.0, gate_mm=700.0,
                 cue_timeout_s=2.5, result_s=1.4, track_grace_s=0.7,
                 seed=None, min_reaction_s=MIN_HUMAN_REACTION_S):
        self.min_reaction_s = float(min_reaction_s)
        self.arena_x_mm = float(arena_x_mm)
        self.arena_y_mm = float(arena_y_mm)
        if not (math.isfinite(self.arena_x_mm) and self.arena_x_mm > 0):
            raise ValueError("arena length must be a positive finite value")
        if not (math.isfinite(self.arena_y_mm) and self.arena_y_mm > 0):
            raise ValueError("arena width must be a positive finite value")
        self.gate_mm = float(gate_mm)
        if self.gate_mm >= self.arena_y_mm / 2.0:
            raise ValueError(
                f"gate {self.gate_mm:g} mm exceeds half the arena width "
                f"{self.arena_y_mm / 2.0:g} mm")
        self.reps = max(1, int(reps))
        self.countdown_s = float(countdown_s)
        self.arm_hold_s = float(arm_hold_s)
        self.commit_mm = float(commit_mm)
        self.cue_timeout_s = float(cue_timeout_s)
        self.result_s = float(result_s)
        self.track_grace_s = float(track_grace_s)
        self.seed = seed
        self.rng = random.Random(seed)
        self.reset()

    @property
    def trigger_x_mm(self):
        """Half way down the run-up: the cue fires here, mid-stride."""
        return self.arena_x_mm / 2.0

    @property
    def centre_y_mm(self):
        return self.arena_y_mm / 2.0

    def reset(self):
        self.state = "idle"
        self.t_state = 0.0
        self.rep_idx = 0
        self.errors = 0
        self.voided = 0
        self.results = []
        self.last_result = None
        self.target = None
        self.go_time = None
        self.decision_s = None
        self._events = []
        self._last_track = None
        self._arm_since = None
        self._cue_y = None
        self._decision_side = None

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self.state = "set_wait"
            self.t_state = now

    def side_of_offset(self, dy):
        return "RIGHT" if dy > 0 else "LEFT"

    def update(self, now, joints=None):
        pelvis = pelvis_mm(joints)
        if pelvis is not None:
            self._last_track = now
        tracked = (self._last_track is not None
                   and (now - self._last_track) <= self.track_grace_s)

        if self.state == "set_wait":
            # Behind the start line, holding still.
            if pelvis is None:
                self._arm_since = None
                return
            if pelvis[0] > self.trigger_x_mm * 0.5:
                self._arm_since = None
                return
            if self._arm_since is None:
                self._arm_since = now
            elif now - self._arm_since >= self.arm_hold_s:
                self.state = "approach"
                self.t_state = now
                self._arm_since = None
        elif self.state == "approach":
            if pelvis is None:
                return
            if pelvis[0] >= self.trigger_x_mm:
                if abs(pelvis[1] - self.centre_y_mm) >= self.gate_mm:
                    # Already outside the gate when the cue fires: whichever side
                    # were cued, the next frame "clears" it. There is no cut to
                    # measure, so the rep is voided instead of scored.
                    self.target = self.rng.choice(self.SIDES)
                    self.go_time = now
                    self._finish(now, "void", None, None,
                                 reason="pre_positioned")
                    return
                self.target = self.rng.choice(self.SIDES)
                self.go_time = now
                self.decision_s = None
                self._cue_y = pelvis[1]
                self.state = "active"
                self.t_state = now
        elif self.state == "active":
            elapsed = now - self.go_time
            if pelvis is None:
                if not tracked:
                    self._finish(now, "void", None, None, reason="tracking_lost")
                return
            dy = pelvis[1] - self._cue_y
            if self.decision_s is None and abs(dy) >= self.commit_mm:
                if not is_plausible_reaction(elapsed, self.min_reaction_s):
                    # A committed cut inside the reaction floor is either the
                    # athlete already moving before the cue or a flier in the
                    # cue-time reference. Neither is a decision time.
                    self._finish(now, "void", None, None,
                                 reason="implausible_reaction")
                    return
                # First committed lateral movement — this is the decision, and
                # it is recorded even when the direction turns out to be wrong.
                self.decision_s = elapsed
                self._decision_side = self.side_of_offset(dy)
            cleared = abs(pelvis[1] - self.centre_y_mm) >= self.gate_mm
            if cleared:
                side = self.side_of_offset(pelvis[1] - self.centre_y_mm)
                result = "hit" if side == self.target else "error"
                self._finish(now, result, self.decision_s, elapsed, side=side)
            elif elapsed >= self.cue_timeout_s:
                self._finish(now, "miss", self.decision_s, None)
        elif self.state == "result":
            if now - self.t_state >= self.result_s:
                self.state = "set_wait"
                self.t_state = now
                self.target = None
                self.go_time = None
                self._arm_since = None

    def _finish(self, now, result, decision_s, execution_s, side=None,
                reason=None):
        row = {
            "rep": self.rep_idx + 1,
            "cued": self.target,
            "went": side,
            "result": result,
            "decision_s": _round(decision_s, 3),
            "execution_s": _round(execution_s, 3),
        }
        if reason:
            row["reason"] = reason
        self.last_result = (result, execution_s)
        if result == "error":
            self.errors += 1
        if result == "void":
            self.voided += 1
            self._events.append({"event": "rep_void", **row})
        else:
            self.results.append(row)
            self._events.append({"event": "rep", **row})
            self.rep_idx += 1
        self.state = "result"
        self.t_state = now
        if self.rep_idx >= self.reps:
            self.state = "done"

    def pop_events(self):
        out, self._events = self._events, []
        return out

    def per_side(self):
        out = {}
        for side in self.SIDES:
            rows = [r for r in self.results if r["cued"] == side]
            decisions = [r["decision_s"] for r in rows if r["decision_s"] is not None]
            out[side] = {
                "reps": len(rows),
                "correct": sum(1 for r in rows if r["result"] == "hit"),
                "avg_decision_s": _round(fmean(decisions), 3) if decisions else None,
            }
        return out

    def summary(self):
        decisions = [r["decision_s"] for r in self.results
                     if r["decision_s"] is not None]
        executions = [r["execution_s"] for r in self.results
                      if r["execution_s"] is not None]
        sides = self.per_side()
        slower = None
        pair = [sides[s]["avg_decision_s"] for s in self.SIDES]
        if all(v is not None for v in pair) and pair[0] != pair[1]:
            slower = self.SIDES[0] if pair[0] > pair[1] else self.SIDES[1]
        return {
            "reps_completed": len(self.results),
            "reps_target": self.reps,
            "correct_cuts": sum(1 for r in self.results if r["result"] == "hit"),
            "wrong_way_cuts": self.errors,
            "avg_decision_s": _round(fmean(decisions), 3) if decisions else None,
            "avg_execution_s": _round(fmean(executions), 3) if executions else None,
            "per_side": sides,
            "slower_side": slower,
            "voided_reps": self.voided,
        }

    def headline(self):
        s = self.summary()
        if not s["reps_completed"]:
            return "no completed reps"
        text = f"{s['correct_cuts']}/{s['reps_completed']} correct"
        if s["avg_decision_s"] is not None:
            text += f" | decision {s['avg_decision_s']:.2f} s"
        return text


DRILL_REGISTRY = {
    "balance": BalanceDrill,
    "shuttle": ShuttleDrill,
    "line_hops": LineHopsDrill,
    "gk_save": GkSaveDrill,
    "gk_updown": GkUpDownDrill,
    "reaction_zones": ReactionZonesDrill,
    "cmj": CmjDrill,
    "hop_symmetry": HopSymmetryDrill,
    "reactive_cut": ReactiveCutDrill,
}


# Protocol catalog: the ONE place that names a drill's workload parameter.
#
# The legacy CLI collapses four different concepts into `--rounds` (holds for
# balance, reps for shuttle, sets for line_hops, rounds for gk_save), which
# makes a stored "rounds: 10" unreadable without knowing the drill. Programs and
# evidence use the semantic name; `cli` is the mapping to the legacy flag and is
# an implementation detail.
#
# `fixed` names parameters that DEFINE the protocol but are not settable through
# the drill wrapper's allowlist. They still enter the fingerprint, so if one is
# ever made settable the baseline epoch rolls over on its own.
PROTOCOL_CATALOG = {
    "balance":   {"protocol_id": "balance.v1",
                  "workload": ("holds", "--rounds", 2, 8),
                  "fixed": ("hold_s",)},
    "shuttle":   {"protocol_id": "shuttle.v1",
                  "workload": ("reps", "--rounds", 1, 6),
                  "fixed": ()},
    "line_hops": {"protocol_id": "line_hops.v1",
                  "workload": ("sets", "--rounds", 1, 5),
                  "fixed": ("work_s",)},
    "gk_save":   {"protocol_id": "gk_save.v1",
                  "workload": ("rounds", "--rounds", 5, 20),
                  "fixed": ()},
    "gk_updown": {"protocol_id": "gk_updown.v1",
                  "workload": ("duration_s", "--duration", 15.0, 120.0),
                  "fixed": ()},
    "reaction_zones": {
        "protocol_id": "reaction_zones.v1",
        "workload": ("rounds", "--rounds", 5, 20),
        "fixed": (
            "arena_y_mm",
            "wall_margin_mm",
            "arm_hold_s",
            "cue_timeout_s",
            "cue_delay_min_s",
            "cue_delay_max_s",
        ),
    },
    "cmj": {
        "protocol_id": "cmj.v1",
        "workload": ("jumps", "--rounds", 3, 10),
        "fixed": ("dip_mm", "rise_mm", "settle_mm", "min_air_s"),
    },
    "hop_symmetry": {
        "protocol_id": "hop_symmetry.v1",
        "workload": ("hops_per_leg", "--rounds", 2, 5),
        "fixed": ("arm_hold_s", "settle_hold_s", "still_mm", "min_hop_mm"),
    },
    "reactive_cut": {
        "protocol_id": "reactive_cut.v1",
        "workload": ("reps", "--rounds", 4, 12),
        "fixed": (
            "arena_x_mm",
            "arena_y_mm",
            "gate_mm",
            "commit_mm",
            "arm_hold_s",
            "cue_timeout_s",
        ),
    },
}

# Excluded from the fingerprint on purpose: a different random cue order is the
# same protocol. But a PINNED seed makes the whole cue sequence (corner AND
# delay, both driven by one Random) reproducible, which defeats the drill's
# anti-anticipation design and would inflate reaction times across repeats — so
# programs must not pin it, and a pinned-seed session must not feed a reaction
# baseline. Recorded for audit only.
FINGERPRINT_EXCLUDED = ("seed",)


def validate_workload(drill_id, value):
    """Range-check a drill's workload parameter BEFORE the drill is built.

    The legacy path did `args.rounds or 4`, so `--rounds 0` silently became 4:
    the session ran a workload the caller never asked for while the record
    claimed otherwise. Reject instead of substituting.
    """
    spec = PROTOCOL_CATALOG.get(drill_id)
    if spec is None:
        raise ValueError(f"unknown drill {drill_id!r}")
    name, _cli, lo, hi = spec["workload"]
    if value is None:
        return None
    number = float(value) if isinstance(lo, float) else int(value)
    if not (lo <= number <= hi):
        raise ValueError(
            f"{drill_id}.{name} must be between {lo} and {hi}, got {value}")
    return number


def applied_parameters(drill):
    """The parameters the constructed drill is ACTUALLY running.

    Read back off the object rather than off the request, so clamping inside a
    constructor cannot leave the record disagreeing with the session.
    """
    spec = PROTOCOL_CATALOG.get(drill.kind)
    if spec is None:
        return {}
    name, _cli, _lo, _hi = spec["workload"]
    out = {name: getattr(drill, name)}
    for extra in spec["fixed"]:
        out[extra] = getattr(drill, extra)
    if drill.kind == "gk_save":
        out["flip"] = bool(getattr(drill, "flip", False))
    return out


def protocol_parameters_fingerprint(protocol_id, applied_parameters):
    """Stable hash of the protocol AND the parameters actually applied.

    A protocol id alone is not enough to decide comparability: "balance.v1" with
    4 holds of 20 s and the same protocol with 8 holds are different workloads,
    so they must not share a baseline. Numbers are canonicalised (integral
    floats collapse to ints, keys sorted) so 4 and 4.0 cannot spuriously split
    a baseline in two.
    """
    canonical = {}
    for key in sorted(applied_parameters or {}):
        value = applied_parameters[key]
        if isinstance(value, bool):
            canonical[key] = value
        elif isinstance(value, float) and value.is_integer():
            canonical[key] = int(value)
        else:
            canonical[key] = value
    payload = json.dumps({"protocol_id": protocol_id, "parameters": canonical},
                         sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_session_record(
        drill, athlete, started_iso, ended_iso, aborted=False, session_id="",
        athlete_id="", evidence_context=None):
    """One JSON-safe record describing a finished (or aborted) session.

    ``athlete_id`` and ``evidence_context`` are OPTIONAL additions to the same
    ``project_cam.training.v1`` schema: the desktop reader looks fields up by
    key and tolerates unknown ones, but rejects an unknown schema string, so
    the version must not be bumped until that reader accepts both.
    """
    record = {
        "schema": "project_cam.training.v1",
        "drill": drill.kind,
        "title": drill.title,
        "role": drill.role,
        "athlete": athlete or "",
        "started": started_iso,
        "ended": ended_iso,
        "aborted": bool(aborted),
        "headline": drill.headline(),
        "summary": drill.summary(),
    }
    if session_id:
        record["session_id"] = str(session_id)
    if athlete_id:
        record["athlete_id"] = str(athlete_id)
    if evidence_context:
        record["evidence_context"] = evidence_context
    return record


def append_session_index(index_path, record):
    """Append one compact line to the rolling session index (JSONL)."""
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
