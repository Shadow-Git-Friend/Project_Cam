"""Physical-plausibility gates for drill measurements.

Every constant here answers one question: could the athlete's body have produced
this reading in a 6.23 x 3.05 m room? A reading that fails is neither smoothed
nor silently dropped — it is counted and reported, so the session record shows
that the capture was faulty instead of showing a personal record that never
happened. That is the same rule the boards already follow for what they display
(report what the sensor measures, not the metric a coach expects); this module
adds the other half of it: refuse to report what the sensor cannot have
measured.

Motivating evidence, from live sessions with all six cameras open and
``pose_valid_frame_ratio`` 1.0 — so these are not degraded-capture sessions that
a comparability policy would have filtered out:

* ``balance`` 2026-08-01T11:25, hold 2: ``max_excursion_mm 31633.3``,
  ``sway_rms_mm 3986.5``. Thirty-one metres of pelvis travel in a 6.2 m room,
  which became the session headline (``avg_sway_mm 2031``) and would have become
  the athlete's balance baseline.
* ``gk_save`` 2026-08-01T10:30, round 1: ``reaction_s 0.034`` scored as a save —
  34 ms from cue to wrist-in-corner, inside a single 15 Hz packet.
* ``gk_updown`` 2026-07-31T13:00: ``avg up 0.10 s``. A drop to the floor and a
  return to the set height in 100 ms.

Stdlib only, no cv2 and no numpy, so the gates stay unit-testable next to the
state machines they protect.
"""

from __future__ import annotations

import math

# World Athletics treats a start reaction below 100 ms as anticipation rather
# than a reaction, because no athlete can hear a stimulus and produce force that
# fast. Simple visual reaction time is slower still (~150-200 ms before any
# movement time), so 100 ms is the conservative floor: it cannot void a genuine
# save, and anything under it is provably not a response to the cue.
MIN_HUMAN_REACTION_S = 0.10

# A pelvis cannot travel faster than this. The 100 m world record holder peaks
# near 12.3 m/s over a full track; inside a 6.23 m garage nothing approaches it.
# This is therefore a garbage filter for a triangulation flier, not a motion
# filter — the same distinction the display code makes for its velocity gate
# (see .claude/rules/perf.md, "the velocity gate is a GARBAGE filter").
MAX_PELVIS_SPEED_MM_S = 12000.0

# Elite countermovement-jump centre-of-mass rise tops out around 0.6 m; the
# pelvis marker on this rig tracks a similar magnitude. A reading above 0.7 m is
# a measurement fault, not a personal best.
MAX_PELVIS_RISE_MM = 700.0

# A goalkeeper down-up — pelvis to the floor and back to a held set height —
# takes appreciably longer than half a second even at professional pace.
MIN_DOWN_UP_S = 0.5


def is_plausible_reaction(reaction_s, min_reaction_s=MIN_HUMAN_REACTION_S):
    """True when ``reaction_s`` could be a genuine response to a cue.

    A non-finite, negative or below-floor value means the athlete was already in
    the target state when the cue fired, or a tracking flier crossed the
    threshold — either way it is not a reaction and must not enter a reaction
    average.
    """
    if reaction_s is None:
        return False
    value = float(reaction_s)
    if not math.isfinite(value):
        return False
    return value >= float(min_reaction_s)


class PositionGate:
    """Accept only position samples a human body could have produced.

    A sample is rejected when the speed implied from the last ACCEPTED sample
    exceeds ``max_speed_mm_s``. A rejected sample never becomes the new anchor —
    one flier must not disqualify the real trajectory that follows it — but
    after ``max_consecutive_rejections`` in a row the gate re-anchors, because a
    sustained new position is positive evidence of a re-acquisition while a
    single frame is not. That is the same asymmetry the drill state machines use
    for presence: absence is not evidence of leaving, sustained presence is.

    The gate keeps counters rather than a verdict. Whether a metric may still be
    reported from the surviving samples is the drill's decision, and it has to
    be visible in the record either way.
    """

    def __init__(self, max_speed_mm_s=MAX_PELVIS_SPEED_MM_S,
                 max_consecutive_rejections=3):
        speed = float(max_speed_mm_s)
        if not math.isfinite(speed) or speed <= 0.0:
            raise ValueError("max_speed_mm_s must be a positive finite value")
        streak = int(max_consecutive_rejections)
        if streak < 1:
            raise ValueError("max_consecutive_rejections must be >= 1")
        self.max_speed_mm_s = speed
        self.max_consecutive_rejections = streak
        self.reset()

    def reset(self):
        self.accepted = 0
        self.rejected_teleport = 0
        self.rejected_invalid = 0
        self.reanchors = 0
        self._last = None            # (t, x, y, z) of the last accepted sample
        self._pending = None         # (t, x, y, z) first sample of a reject run
        self._streak = 0

    @property
    def rejected(self):
        return self.rejected_teleport + self.rejected_invalid

    def accept(self, now, point):
        """Record ``point`` as observed at ``now``; True when it is plausible."""
        try:
            x, y, z = (float(point[0]), float(point[1]), float(point[2]))
        except (TypeError, ValueError, IndexError):
            self.rejected_invalid += 1
            return False
        t = float(now)
        if not all(math.isfinite(v) for v in (t, x, y, z)):
            self.rejected_invalid += 1
            return False

        if self._last is not None and self._is_unreachable(self._last, t, x, y, z):
            self._streak += 1
            if self._pending is None:
                self._pending = (t, x, y, z)
            # "Sustained" has to mean the athlete stayed in the NEW region for
            # the whole run of rejections. A run of unrelated fliers is not
            # evidence of anything, so it restarts the run instead of
            # re-anchoring onto the newest piece of garbage.
            consistent = not self._is_unreachable(self._pending, t, x, y, z)
            if not (consistent and self._streak >= self.max_consecutive_rejections):
                if not consistent:
                    self._pending = (t, x, y, z)
                    self._streak = 1
                self.rejected_teleport += 1
                return False
            # Re-anchor and accept, so the gate can never lock a whole session
            # out of measurement.
            self.reanchors += 1

        self._streak = 0
        self._pending = None
        self._last = (t, x, y, z)
        self.accepted += 1
        return True

    def _is_unreachable(self, anchor, t, x, y, z):
        """True when (x, y, z) at ``t`` is unreachable from ``anchor``.

        Returns False when it is reachable and when no elapsed time separates
        the two samples — simultaneous samples carry no speed evidence, so they
        are not the gate's business.
        """
        dt = t - anchor[0]
        if dt <= 0.0:
            return False
        return math.dist((x, y, z), anchor[1:]) / dt > self.max_speed_mm_s

    def stats(self):
        """Counters for the session record — raw facts, never a verdict."""
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "rejected_teleport": self.rejected_teleport,
            "rejected_invalid": self.rejected_invalid,
            "reanchors": self.reanchors,
        }
