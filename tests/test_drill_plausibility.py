"""Physical-plausibility guards on the drill state machines.

Every test here is anchored to a real defect observed in a live session, not to
a hypothetical one. The log lines are quoted in the test that fixes them so the
next reader can check the claim instead of trusting it:

    balance    2026-08-01T11:25  hold 2  sway_rms_mm 3986.5, max_excursion_mm 31633.3
    gk_save    2026-08-01T10:30  round 1 reaction_s 0.034, result "save"
    gk_updown  2026-07-31T13:00  "2 down-ups · avg up 0.10 s"
    cmj        2026-07-31T14:51  "best 751 mm pelvis rise"

All four sessions had six of six cameras open and ``pose_valid_frame_ratio``
1.0, so a capture-quality policy would have admitted every one of them.

The guards are argparse-free library defaults, and the live boards construct
these drills without passing them, so the tests exercise the DEFAULTS — per the
rule in .claude/rules/perf.md that a test which supplies a threshold explicitly
verifies nothing about production behaviour.
"""

import math
from types import SimpleNamespace

import pytest

from project_cam.training.drills import (
    BalanceDrill,
    CmjDrill,
    GkSaveDrill,
    GkUpDownDrill,
    ReactionZonesDrill,
    ReactiveCutDrill,
)
from project_cam.training.plausibility import (
    MAX_PELVIS_RISE_MM,
    MAX_PELVIS_SPEED_MM_S,
    MIN_DOWN_UP_S,
    MIN_HUMAN_REACTION_S,
    PositionGate,
    is_plausible_reaction,
)

ARENA_X_MM = 6230.0
ARENA_Y_MM = 3050.0


def person(x=3000.0, y=1500.0, hip_z=1000.0, shoulder_z=1450.0,
           la_z=80.0, ra_z=80.0, lw=None, rw=None):
    j = {
        "left_hip": (x, y - 100, hip_z),
        "right_hip": (x, y + 100, hip_z),
        "left_shoulder": (x, y - 150, shoulder_z),
        "right_shoulder": (x, y + 150, shoulder_z),
        "left_ankle": (x, y - 100, la_z),
        "right_ankle": (x, y + 100, ra_z),
    }
    if lw is not None:
        j["left_wrist"] = lw
    if rw is not None:
        j["right_wrist"] = rw
    return j


# --------------------------------------------------------------- PositionGate

def test_the_arena_cannot_contain_the_speed_a_flier_implies():
    """The gate's threshold has to be unreachable inside the room, not merely high."""
    room_diagonal_mm = math.dist((0.0, 0.0), (ARENA_X_MM, ARENA_Y_MM))
    # At the rig's 15 Hz, crossing the whole room corner to corner in one packet
    # implies this speed. It must be over the threshold, or the 31.6 m excursion
    # this module exists to reject would pass.
    assert room_diagonal_mm / (1.0 / 15.0) > MAX_PELVIS_SPEED_MM_S
    # And a genuine sprint must pass it: 8 m/s is faster than anyone accelerates
    # inside 6.2 m.
    assert 8000.0 < MAX_PELVIS_SPEED_MM_S


def test_one_flier_is_rejected_and_the_real_trajectory_survives_it():
    gate = PositionGate()
    assert gate.accept(0.0, (1000.0, 1500.0, 900.0)) is True
    # 30 m away one packet later — the balance hold-2 flier.
    assert gate.accept(0.1, (31000.0, 1500.0, 900.0)) is False
    # The flier must NOT have become the anchor, or every real sample after it
    # would be rejected as a teleport back.
    assert gate.accept(0.2, (1005.0, 1502.0, 901.0)) is True
    assert gate.accepted == 2
    assert gate.rejected_teleport == 1


def test_a_sustained_new_position_re_anchors_so_a_session_is_never_locked_out():
    gate = PositionGate()
    gate.accept(0.0, (1000.0, 1500.0, 900.0))
    # Tracking re-acquires the athlete across the room and STAYS there. Note the
    # timestamps: 5 m in one second is an ordinary run and would be accepted
    # outright, so the jump has to be inside one packet to be a teleport at all.
    assert gate.accept(0.05, (6000.0, 2900.0, 900.0)) is False
    assert gate.accept(0.10, (6002.0, 2901.0, 900.0)) is False
    assert gate.accept(0.15, (6001.0, 2902.0, 900.0)) is True
    assert gate.reanchors == 1
    assert gate.accept(0.20, (6003.0, 2903.0, 900.0)) is True


def test_unrelated_fliers_never_re_anchor_onto_garbage():
    gate = PositionGate()
    gate.accept(0.0, (1000.0, 1500.0, 900.0))
    # Three rejections in a row, but each in a different place: that is noise,
    # not a re-acquisition, so the run restarts instead of accepting the third.
    assert gate.accept(0.05, (31000.0, 1500.0, 900.0)) is False
    assert gate.accept(0.10, (-42000.0, 1500.0, 900.0)) is False
    assert gate.accept(0.15, (90000.0, 1500.0, 900.0)) is False
    assert gate.reanchors == 0
    assert gate.accepted == 1


def test_malformed_and_non_finite_samples_are_counted_separately():
    gate = PositionGate()
    assert gate.accept(0.0, (float("nan"), 0.0, 0.0)) is False
    assert gate.accept(0.0, (0.0, float("inf"), 0.0)) is False
    assert gate.accept(0.0, ("x", 0.0, 0.0)) is False
    assert gate.accept(0.0, (1.0, 2.0)) is False
    assert gate.rejected_invalid == 4
    assert gate.rejected_teleport == 0
    # A malformed sample must not have anchored anything either.
    assert gate.accept(0.0, (1000.0, 1500.0, 900.0)) is True


def test_simultaneous_samples_carry_no_speed_evidence():
    gate = PositionGate()
    gate.accept(5.0, (1000.0, 1500.0, 900.0))
    # Same timestamp: dividing by zero elapsed time would make any distance
    # infinitely fast, which is a statement about the clock, not the athlete.
    assert gate.accept(5.0, (2000.0, 1500.0, 900.0)) is True


def test_gate_construction_refuses_a_meaningless_threshold():
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            PositionGate(max_speed_mm_s=bad)
    with pytest.raises(ValueError):
        PositionGate(max_consecutive_rejections=0)


def test_stats_report_counts_not_a_verdict():
    gate = PositionGate()
    gate.accept(0.0, (0.0, 0.0, 0.0))
    gate.accept(0.1, (99000.0, 0.0, 0.0))
    stats = gate.stats()
    assert stats == {"accepted": 1, "rejected": 1, "rejected_teleport": 1,
                     "rejected_invalid": 0, "reanchors": 0}
    assert "quality" not in stats and "reliable" not in stats


# ----------------------------------------------------------- reaction floor

def test_the_reaction_floor_is_the_false_start_threshold():
    # World Athletics defines a sub-100 ms start reaction as anticipation.
    assert MIN_HUMAN_REACTION_S == pytest.approx(0.10)
    # The 34 ms "save" from the live log must fail it, and it must fail by a
    # margin larger than one 15 Hz packet, so the verdict is not a rounding call.
    assert not is_plausible_reaction(0.034)
    assert 0.10 - 0.034 > 1.0 / 15.0 * 0.9


def test_reaction_floor_rejects_nonsense_and_admits_a_real_reaction():
    assert not is_plausible_reaction(None)
    assert not is_plausible_reaction(float("nan"))
    assert not is_plausible_reaction(-0.5)
    assert is_plausible_reaction(0.25)


# ------------------------------------------------------------------- balance

def _run_balance_hold(drill, flier_at=None, flier_point=None, hz=15.0,
                      sway_mm=12.0):
    """Drive one full hold of a clean single-leg stance, optionally with a flier.

    The athlete stands on the left leg with the right foot raised, and the pelvis
    oscillates by a few millimetres — the real signal this drill measures.
    """
    drill.start(0.0)
    dt = 1.0 / hz
    t = 0.0
    # Countdown, standing on both feet.
    while drill.state == "countdown":
        t += dt
        drill.update(t, person())
    assert drill.state == "hold"
    step = 0
    while drill.state == "hold":
        t += dt
        step += 1
        x = 3000.0 + sway_mm * math.sin(step * 0.7)
        joints = person(x=x, la_z=80.0, ra_z=400.0)   # right foot raised
        if flier_at is not None and step == flier_at:
            joints["left_hip"] = (flier_point[0], flier_point[1], flier_point[2])
            joints["right_hip"] = (flier_point[0], flier_point[1], flier_point[2])
        drill.update(t, joints)
    return drill.results[0]


def test_a_single_flier_no_longer_becomes_the_balance_measurement():
    """The 2026-08-01 defect: one flier produced sway 3986 mm / excursion 31633 mm."""
    clean = _run_balance_hold(BalanceDrill(holds=1, hold_s=6.0, countdown_s=1.0))
    fouled = _run_balance_hold(
        BalanceDrill(holds=1, hold_s=6.0, countdown_s=1.0),
        flier_at=30, flier_point=(31000.0, 1500.0, 900.0),
    )
    assert clean["sway_rms_mm"] is not None
    assert clean["sway_rms_mm"] < 40.0
    # Same stance, same sway, one bad packet: the reported number must not move
    # by more than a few millimetres, and must stay in the range the room allows.
    assert fouled["sway_rms_mm"] == pytest.approx(clean["sway_rms_mm"], abs=5.0)
    assert fouled["max_excursion_mm"] < ARENA_X_MM
    # And the rejection is on the record rather than hidden.
    assert fouled["samples_rejected"] == 1
    assert fouled["samples_used"] > 20


def test_a_hold_that_was_mostly_garbage_reports_no_sway_at_all():
    """Refusing to report is the honest outcome; a number from 3 samples is not."""
    drill = BalanceDrill(holds=1, hold_s=4.0, countdown_s=1.0)
    drill.start(0.0)
    dt = 1.0 / 15.0
    t = 0.0
    while drill.state == "countdown":
        t += dt
        drill.update(t, person())
    step = 0
    while drill.state == "hold":
        t += dt
        step += 1
        joints = person(la_z=80.0, ra_z=400.0)
        if step % 3 != 0:
            # Two packets in three are garbage, and they alternate sides so the
            # run of rejections is never a sustained new position (which would
            # legitimately re-anchor). This is a broken capture, not a stance.
            far = 40000.0 * (1 if step % 2 == 0 else -1)
            joints["left_hip"] = (far, 1500.0, 900.0)
            joints["right_hip"] = (far, 1500.0, 900.0)
        drill.update(t, joints)
    hold = drill.results[0]
    assert hold["samples_rejected"] >= hold["samples_used"]
    assert hold["sway_rms_mm"] is None
    assert hold["max_excursion_mm"] is None
    assert hold["score"] is None
    summary = drill.summary()
    assert summary["holds_completed"] == 1
    assert summary["holds_measured"] == 0
    assert summary["avg_sway_mm"] is None
    assert summary["samples_rejected"] >= 1


# ------------------------------------------------------------------- gk_save

def _arm_gk_save(drill, t0=0.0, wrists=None):
    """Hold the set position long enough to arm, returning the current time."""
    t = t0
    drill.start(t)
    for _ in range(20):
        t += 0.1
        drill.update(t, person(y=ARENA_Y_MM / 2.0, **(wrists or {})))
        if drill.state == "armed":
            return t
    raise AssertionError(f"never armed, stuck in {drill.state}")


class _StuckRng:
    """An RNG that keeps proposing the same corner — the exhaustion case.

    With two wrists at most two of the four corners can be occupied at once, so
    ``_pick_target`` normally finds a free one. The void path is what happens
    when it cannot, and forcing the draw is the only deterministic way to reach
    it. (A collapsed pose with inverted shoulder/hip references is the physical
    route to the same state.)
    """

    def __init__(self, side, high):
        self._side = side
        self._high = high

    def choice(self, seq):
        return self._side

    def random(self):
        return 0.0 if self._high else 0.9

    def uniform(self, a, b):
        return a


def test_a_corner_the_wrist_already_occupies_is_never_cued():
    """The 0.034 s "save": the target was satisfied before the cue existed."""
    # Wrist parked low in the RIGHT third of the arena — LOW-RIGHT is satisfied.
    parked = {"rw": (3000.0, ARENA_Y_MM - 200.0, 200.0)}
    for seed in range(25):
        drill = GkSaveDrill(rounds=4, arena_y_mm=ARENA_Y_MM, seed=seed)
        t = _arm_gk_save(drill, wrists=parked)
        t = drill.cue_at + 0.01
        drill.update(t, person(y=ARENA_Y_MM / 2.0, **parked))
        if drill.state == "active":
            assert drill.corner_name() != "LOW-RIGHT"
            # ... and the cued corner really is unoccupied, so the first frame
            # after the cue cannot score.
            assert drill._wrist_in_target(
                person(y=ARENA_Y_MM / 2.0, **parked)) is None
        else:
            # Or the round was voided outright, which is also not a save.
            assert drill.saves == 0


def test_when_no_free_corner_can_be_cued_the_round_voids_instead_of_scoring():
    parked = {"rw": (3000.0, ARENA_Y_MM - 200.0, 200.0)}      # LOW-RIGHT
    drill = GkSaveDrill(rounds=4, arena_y_mm=ARENA_Y_MM, seed=3)
    _arm_gk_save(drill, wrists=parked)
    drill.pop_events()
    # Every draw lands on the corner the wrist already occupies.
    drill.rng = _StuckRng(side=2, high=False)
    drill.update(drill.cue_at + 0.01, person(y=ARENA_Y_MM / 2.0, **parked))
    assert drill.saves == 0
    assert drill.anticipated == 0
    assert drill.voided_rounds == 1
    assert drill.summary()["rounds_completed"] == 0
    (event,) = drill.pop_events()
    assert event["event"] == "round_void"
    assert event["reason"] == "pre_positioned"


def test_a_sub_floor_detection_is_an_anticipation_and_not_a_save():
    drill = GkSaveDrill(rounds=4, arena_y_mm=ARENA_Y_MM, seed=1)
    _arm_gk_save(drill)
    cue = drill.cue_at + 0.001
    drill.update(cue, person(y=ARENA_Y_MM / 2.0))
    assert drill.state == "active"
    side, high = drill.target
    y = 200.0 if side == 0 else ARENA_Y_MM - 200.0
    z = 1900.0 if high else 200.0
    # The wrist appears in the corner 34 ms after the cue — the live log value.
    drill.update(cue + 0.034, person(y=ARENA_Y_MM / 2.0, rw=(3000.0, y, z)))
    summary = drill.summary()
    assert summary["saves"] == 0
    assert summary["anticipated"] == 1
    assert summary["avg_reaction_s"] is None
    assert summary["best_reaction_s"] is None
    assert summary["save_pct"] == 0.0
    corner = summary["per_corner"][drill.corner_name()]
    assert corner["saves"] == 0
    assert corner["anticipated"] == 1
    assert corner["avg_reaction_s"] is None
    (event,) = drill.pop_events()
    assert event["result"] == "anticipated"
    assert event["reaction_s"] == pytest.approx(0.034, abs=1e-3)


def test_a_genuine_save_is_still_a_save():
    drill = GkSaveDrill(rounds=4, arena_y_mm=ARENA_Y_MM, seed=1)
    _arm_gk_save(drill)
    cue = drill.cue_at + 0.001
    drill.update(cue, person(y=ARENA_Y_MM / 2.0))
    side, high = drill.target
    y = 200.0 if side == 0 else ARENA_Y_MM - 200.0
    z = 1900.0 if high else 200.0
    drill.update(cue + 0.42, person(y=ARENA_Y_MM / 2.0, rw=(3000.0, y, z)))
    summary = drill.summary()
    assert summary["saves"] == 1
    assert summary["anticipated"] == 0
    assert summary["avg_reaction_s"] == pytest.approx(0.42, abs=0.01)


# ----------------------------------------------------------------- gk_updown

def _calibrate_updown(drill, stand_z=1000.0, hz=15.0):
    drill.start(0.0)
    dt = 1.0 / hz
    t = 0.0
    while drill.state == "countdown":
        t += dt
        drill.update(t, person(hip_z=stand_z))
    assert drill.state == "work"
    return t, dt


def test_a_single_height_flier_no_longer_counts_a_down_up():
    """The 2026-07-31 defect: "avg up 0.10 s" from a pelvis spike."""
    drill = GkUpDownDrill(duration_s=20.0)
    t, dt = _calibrate_updown(drill)
    # One packet on the floor, one packet back up, then standing again.
    t += dt
    drill.update(t, person(hip_z=300.0))
    t += dt
    drill.update(t, person(hip_z=980.0))
    for _ in range(10):
        t += dt
        drill.update(t, person(hip_z=1000.0))
    assert drill.reps == 0
    assert drill.summary()["reps"] == 0


def test_a_flier_during_a_crouch_cannot_manufacture_a_plausible_rep():
    """The case the recovery floor cannot catch, and the reason down must be held.

    The athlete crouches at 800 mm — below the 850 mm up-threshold, above the
    550 mm down-threshold, so no rep is in progress. A three-packet pose collapse
    dips to 300 mm for 0.13 s, well under the 0.25 s hold. If that were enough to
    confirm the down, the recovery clock would start there and the athlete's
    eventual stand two seconds later would be logged as a complete down-up with
    an entirely believable recovery time — which no reaction or recovery floor
    can distinguish from a real rep. The DURATION of the down is the only thing
    that separates them.
    """
    drill = GkUpDownDrill(duration_s=60.0)
    t, dt = _calibrate_updown(drill, stand_z=1000.0)
    assert drill.down_hold_s > 3 * dt             # the burst must be too short
    for _ in range(5):
        t += dt
        drill.update(t, person(hip_z=800.0))
    for _ in range(3):                            # 0.13 s of collapsed pose
        t += dt
        drill.update(t, person(hip_z=300.0))
    crouch_until = t + 2.0
    while t < crouch_until:                       # two seconds of crouching
        t += dt
        drill.update(t, person(hip_z=800.0))
    for _ in range(10):                           # then stand up and hold
        t += dt
        drill.update(t, person(hip_z=1000.0))
    assert drill.reps == 0
    assert drill.voided_reps == 0                 # nothing happened at all
    assert drill.summary()["avg_recovery_s"] is None


def test_an_impossibly_fast_but_sustained_down_up_is_voided_not_scored():
    drill = GkUpDownDrill(duration_s=30.0)
    t, dt = _calibrate_updown(drill)
    # Sustained down (so the phase is real) but back up within the physical
    # floor for the whole movement.
    for _ in range(5):
        t += dt
        drill.update(t, person(hip_z=300.0))
    for _ in range(8):
        t += dt
        drill.update(t, person(hip_z=980.0))
    assert drill.reps == 0
    assert drill.voided_reps == 1
    events = [e for e in drill.pop_events() if e["event"] == "rep_void"]
    assert events and events[0]["reason"] == "implausible_recovery"
    assert drill.summary()["voided_reps"] == 1


def test_a_real_down_up_still_counts_and_keeps_its_full_recovery_time():
    drill = GkUpDownDrill(duration_s=30.0)
    t, dt = _calibrate_updown(drill)
    down_start = t + dt
    while t < down_start + 1.2:               # a second on the floor
        t += dt
        drill.update(t, person(hip_z=300.0))
    while drill.reps == 0 and t < down_start + 4.0:
        t += dt
        drill.update(t, person(hip_z=980.0))
    assert drill.reps == 1
    recovery = drill.recoveries[0]
    assert recovery >= MIN_DOWN_UP_S
    # Measured from the FIRST sample below the threshold, not from the moment the
    # down was confirmed — holding the down must not shorten the recovery.
    assert recovery == pytest.approx(1.2 + 1.0 / 15.0, abs=0.2)


# ------------------------------------------------------------ reaction_zones

def test_an_instant_zone_flip_is_voided_and_consumes_no_round():
    drill = ReactionZonesDrill(arena_y_mm=ARENA_Y_MM, rounds=5, seed=2)
    t = 0.0
    drill.start(t)
    while drill.state != "armed":
        t += 0.1
        drill.update(t, person(y=ARENA_Y_MM / 2.0))
    t = drill.cue_at + 0.001
    drill.update(t, person(y=ARENA_Y_MM / 2.0))
    assert drill.state == "active"
    centres = drill.target_centres_mm
    # The pelvis "appears" in the cued zone 40 ms after the cue.
    drill.update(t + 0.04, person(y=centres[drill.target]))
    summary = drill.summary()
    assert summary["hits_in_timeout"] == 0
    assert summary["rounds_completed"] == 0
    assert summary["voided_rounds"] == 1
    (event,) = drill.pop_events()
    assert event["event"] == "round_void"
    assert event["reason"] == "implausible_reaction"


def test_a_real_zone_reaction_is_still_a_hit():
    drill = ReactionZonesDrill(arena_y_mm=ARENA_Y_MM, rounds=5, seed=2)
    t = 0.0
    drill.start(t)
    while drill.state != "armed":
        t += 0.1
        drill.update(t, person(y=ARENA_Y_MM / 2.0))
    t = drill.cue_at + 0.001
    drill.update(t, person(y=ARENA_Y_MM / 2.0))
    centres = drill.target_centres_mm
    drill.update(t + 0.9, person(y=centres[drill.target]))
    summary = drill.summary()
    assert summary["hits_in_timeout"] == 1
    assert summary["voided_rounds"] == 0
    assert summary["avg_reaction_s"] == pytest.approx(0.9, abs=0.05)


# ------------------------------------------------------------- reactive_cut

def _approach_reactive_cut(drill, y=ARENA_Y_MM / 2.0):
    t = 0.0
    drill.start(t)
    for _ in range(20):
        t += 0.1
        drill.update(t, person(x=500.0, y=y))
        if drill.state == "approach":
            break
    assert drill.state == "approach"
    return t


def test_an_athlete_already_outside_the_gate_voids_the_rep():
    drill = ReactiveCutDrill(arena_x_mm=ARENA_X_MM, arena_y_mm=ARENA_Y_MM,
                             reps=3, seed=5)
    t = _approach_reactive_cut(drill, y=ARENA_Y_MM / 2.0)
    # Crosses the trigger line already pressed against one side.
    t += 0.1
    drill.update(t, person(x=ARENA_X_MM / 2.0 + 10.0,
                           y=ARENA_Y_MM / 2.0 + drill.gate_mm + 50.0))
    assert drill.summary()["reps_completed"] == 0
    assert drill.summary()["voided_reps"] == 1
    events = [e for e in drill.pop_events() if e["event"] == "rep_void"]
    assert events and events[0]["reason"] == "pre_positioned"


def test_a_lateral_commitment_inside_the_reaction_floor_voids_the_rep():
    drill = ReactiveCutDrill(arena_x_mm=ARENA_X_MM, arena_y_mm=ARENA_Y_MM,
                             reps=3, seed=5)
    t = _approach_reactive_cut(drill)
    t += 0.1
    drill.update(t, person(x=ARENA_X_MM / 2.0 + 10.0, y=ARENA_Y_MM / 2.0))
    assert drill.state == "active"
    # 40 ms later the pelvis has apparently moved 300 mm sideways.
    drill.update(t + 0.04, person(x=ARENA_X_MM / 2.0 + 20.0,
                                  y=ARENA_Y_MM / 2.0 + 300.0))
    summary = drill.summary()
    assert summary["reps_completed"] == 0
    assert summary["voided_reps"] == 1
    assert summary["avg_decision_s"] is None


def test_a_real_cut_still_scores_and_keeps_both_timings():
    drill = ReactiveCutDrill(arena_x_mm=ARENA_X_MM, arena_y_mm=ARENA_Y_MM,
                             reps=3, seed=5)
    t = _approach_reactive_cut(drill)
    t += 0.1
    drill.update(t, person(x=ARENA_X_MM / 2.0 + 10.0, y=ARENA_Y_MM / 2.0))
    target = drill.target
    sign = 1.0 if target == "RIGHT" else -1.0
    drill.update(t + 0.35, person(x=ARENA_X_MM / 2.0 + 100.0,
                                  y=ARENA_Y_MM / 2.0 + sign * 250.0))
    drill.update(t + 0.80, person(
        x=ARENA_X_MM / 2.0 + 200.0,
        y=ARENA_Y_MM / 2.0 + sign * (drill.gate_mm + 20.0)))
    summary = drill.summary()
    assert summary["reps_completed"] == 1
    assert summary["correct_cuts"] == 1
    assert summary["voided_reps"] == 0
    assert summary["avg_decision_s"] == pytest.approx(0.35, abs=0.05)
    assert summary["avg_execution_s"] == pytest.approx(0.80, abs=0.05)


# ----------------------------------------------------------------------- cmj

def _drive_cmj_jump(drill, t, apex_z, stand_z=1000.0, dt=1.0 / 15.0):
    """One dip-and-jump cycle whose apex is `apex_z`."""
    for z in (stand_z - 120.0, stand_z - 150.0):
        t += dt
        drill.update(t, person(hip_z=z))
    for z in (stand_z + 120.0, apex_z, apex_z - 40.0):
        t += dt
        drill.update(t, person(hip_z=z))
    for _ in range(3):
        t += dt
        drill.update(t, person(hip_z=stand_z))
    return t


def test_an_impossible_pelvis_rise_is_recorded_but_never_becomes_the_best():
    """The 2026-07-31 defect: "best 751 mm pelvis rise"."""
    drill = CmjDrill(jumps=2, countdown_s=1.0, calib_s=0.5)
    drill.start(0.0)
    t = 0.0
    while drill.state == "countdown":
        t += 1.0 / 15.0
        drill.update(t, person(hip_z=1000.0))
    assert drill.state == "work"
    t = _drive_cmj_jump(drill, t, apex_z=1000.0 + 380.0)     # a real jump
    t = _drive_cmj_jump(drill, t, apex_z=1000.0 + 900.0)     # a flier apex
    summary = drill.summary()
    assert summary["jumps_completed"] == 2
    assert summary["implausible_jumps"] == 1
    assert summary["best_pelvis_rise_mm"] == pytest.approx(380.0, abs=15.0)
    assert summary["avg_pelvis_rise_mm"] == pytest.approx(380.0, abs=15.0)
    # The reading itself is still in the record — flagged, not deleted.
    flagged = [r for r in drill.results if r.get("implausible")]
    assert len(flagged) == 1
    assert flagged[0]["pelvis_rise_mm"] > MAX_PELVIS_RISE_MM
    assert "751" not in drill.headline()


def test_the_rise_bound_sits_above_the_elite_range_and_below_the_defect():
    # An elite countermovement jump must not be flagged...
    assert MAX_PELVIS_RISE_MM > 600.0
    # ...and the 751 mm reading from the live log must be.
    assert MAX_PELVIS_RISE_MM < 751.0


# ------------------------- the operator's log lines -------------------------
#
# The board's event_line() feeds the desktop MISSION LOG. A new outcome that it
# does not know about either prints as raw JSON or, worse, matches an older
# branch and is described as something it is not.

def _event_line(event, drill_kind):
    import importlib.util

    root = __import__("pathlib").Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "training_drill_board", root / "garage_lab_combined/scripts/training_drill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.event_line(SimpleNamespace(kind=drill_kind), event)


def test_an_anticipation_is_never_logged_as_a_miss():
    line = _event_line({"event": "round", "round": 1, "corner": "LOW-RIGHT",
                        "result": "anticipated", "reaction_s": 0.034,
                        "wrist": "left_wrist"}, "gk_save")
    assert "MISS" not in line
    assert "TOO EARLY" in line
    assert "0.034" in line
    assert "not scored" in line


def test_the_new_void_events_read_as_sentences_not_as_json():
    gk = _event_line({"event": "round_void", "round": 3, "corner": None,
                      "reason": "pre_positioned"}, "gk_save")
    assert gk.startswith("round 3: VOID")
    assert "pre positioned" in gk
    assert "{" not in gk, "a raw JSON dump is not an operator log line"

    updown = _event_line({"event": "rep_void", "recovery_s": 0.1,
                          "reason": "implausible_recovery"}, "gk_updown")
    assert "voided" in updown
    assert "implausible recovery" in updown
    assert "0.10s measured" in updown
    assert "{" not in updown
