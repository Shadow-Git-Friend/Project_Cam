"""Unit tests for the garage training drill state machines (no cv2 / UDP)."""

import json
import math

import pytest

from project_cam.training import (
    DRILL_REGISTRY,
    BalanceDrill,
    GkSaveDrill,
    GkUpDownDrill,
    LineHopsDrill,
    ShuttleDrill,
    append_session_index,
    build_session_record,
    zone_of,
)
from project_cam.training.drills import (
    PROTOCOL_CATALOG,
    applied_parameters,
    plane_crossing,
    protocol_parameters_fingerprint,
    segment_point_distance,
    validate_workload,
)


def J(**kw):
    """joints dict from name=(x, y, z) kwargs."""
    return dict(kw)


def person(x=3000.0, y=1500.0, hip_z=1000.0, shoulder_z=1450.0,
           la_z=80.0, ra_z=80.0, lw=None, rw=None, ankle_y=None):
    """A minimal standing person for the drills that need pelvis/ankles/wrists."""
    ay = y if ankle_y is None else ankle_y
    j = {
        "left_hip": (x, y - 100, hip_z),
        "right_hip": (x, y + 100, hip_z),
        "left_shoulder": (x, y - 150, shoulder_z),
        "right_shoulder": (x, y + 150, shoulder_z),
        "left_ankle": (x, ay - 100, la_z),
        "right_ankle": (x, ay + 100, ra_z),
    }
    if lw is not None:
        j["left_wrist"] = lw
    if rw is not None:
        j["right_wrist"] = rw
    return j


# ----------------------------------------------------------------- registry

def test_registry_ids_and_roles():
    assert set(DRILL_REGISTRY) == {
        # field
        "balance", "shuttle", "line_hops", "reaction_zones",
        "cmj", "hop_symmetry", "reactive_cut",
        # goalkeeper
        "gk_save", "gk_save_served", "gk_updown",
    }
    roles = {cls.role for cls in DRILL_REGISTRY.values()}
    assert roles == {"field", "gk"}
    for kind, cls in DRILL_REGISTRY.items():
        assert cls.kind == kind
        # Arena-aware drills must be handed the configured geometry rather than
        # hiding a garage constant inside the state machine.
        if kind == "reaction_zones":
            drill = cls(arena_y_mm=3050.0)
        elif kind == "reactive_cut":
            drill = cls(arena_x_mm=6230.0, arena_y_mm=3050.0)
        elif kind == "gk_save_served":
            drill = cls(arena_x_mm=6230.0, arena_y_mm=3050.0)
        else:
            drill = cls()
        assert drill.state == "idle"
        assert drill.headline()  # never crashes with zero data
        assert isinstance(drill.summary(), dict)


def test_zone_of_matches_reaction_arena_semantics():
    assert zone_of(0, 3000) == 0
    assert zone_of(1500, 3000) == 1
    assert zone_of(2999, 3000) == 2
    assert zone_of(-50, 3000) == 0
    assert zone_of(9999, 3000) == 2
    assert zone_of(0, 3000, flip=True) == 2


# ------------------------------------------------------------ reaction zones

def reaction_drill(**overrides):
    params = {
        "arena_y_mm": 3050.0,
        "rounds": 2,
        "wall_margin_mm": 500.0,
        "arm_hold_s": 0.1,
        "cue_delay_min_s": 0.2,
        "cue_delay_max_s": 0.2,
        "cue_timeout_s": 0.5,
        "result_s": 0.1,
        "seed": 7,
    }
    params.update(overrides)
    return DRILL_REGISTRY["reaction_zones"](**params)


def test_reaction_zone_geometry_uses_configured_width_and_safe_centres():
    cls = DRILL_REGISTRY["reaction_zones"]
    with pytest.raises(TypeError):
        cls()  # arena width must come from --arena-y-mm, never a hidden 3050

    assert cls(arena_y_mm=3050.0).rounds == 10
    d = reaction_drill()
    expected_bounds = (
        (0.0, 3050.0 / 3.0),
        (3050.0 / 3.0, 2.0 * 3050.0 / 3.0),
        (2.0 * 3050.0 / 3.0, 3050.0),
    )
    for actual, expected in zip(d.zone_bounds_mm, expected_bounds):
        assert actual == pytest.approx(expected)
    assert d.target_centres_mm == pytest.approx((
        3050.0 / 6.0,
        3050.0 / 2.0,
        5.0 * 3050.0 / 6.0,
    ))
    for zone, centre in enumerate(d.target_centres_mm):
        assert zone_of(centre, 3050.0) == zone
    assert d.target_centres_mm[0] >= 500.0
    assert 3050.0 - d.target_centres_mm[2] >= 500.0

    with pytest.raises(ValueError, match="wall margin"):
        reaction_drill(wall_margin_mm=509.0)


def test_reaction_zones_requires_presence_and_voids_active_tracking_loss():
    d = reaction_drill(rounds=1, arm_hold_s=0.2,
                       cue_delay_min_s=0.5, cue_delay_max_s=0.5)
    d.start(0.0)
    assert d.state == "set_wait"

    d.update(0.3, None)
    assert d.state == "set_wait" and d.target is None
    d.update(0.4, person(y=1525.0))
    d.update(0.61, person(y=1525.0))
    assert d.state == "armed"
    assert d.arm_zone == 1
    assert d.target is None

    # The cue delay elapsed during a dropout. Armed stays armed and no target
    # is guessed until positive tracking resumes in the held zone.
    d.update(1.2, None)
    assert d.state == "armed" and d.target is None
    d.update(1.21, person(y=1525.0))
    assert d.state == "active"
    assert d.target in (0, 2) and d.target != d.arm_zone

    # Once the cue is live, a dropout invalidates the attempt. It is not a miss
    # and does not consume one of the requested completed rounds.
    d.update(1.3, None)
    assert d.state == "result"
    assert d.last_result[0] == "void"
    assert d.round_idx == 0
    assert d.voided_rounds == 1
    (event,) = d.pop_events()
    assert event["event"] == "round_void"
    assert event["reason"] == "tracking_lost"
    d.update(1.41, None)
    assert d.state == "set_wait"


def test_reaction_zones_armed_dropout_is_not_departure_but_observed_move_is():
    d = reaction_drill(arm_hold_s=0.2,
                       cue_delay_min_s=5.0, cue_delay_max_s=5.0)
    d.start(0.0)
    d.update(0.0, person(y=1525.0))
    d.update(0.21, person(y=1525.0))
    assert d.state == "armed"

    d.update(1.0, None)
    assert d.state == "armed"
    d.update(1.1, person(y=300.0))
    assert d.state == "set_wait"


def test_reaction_zones_randomises_delay_and_never_targets_the_armed_zone():
    delays = set()
    targets = set()
    for seed in range(8):
        d = reaction_drill(
            arm_hold_s=0.01,
            cue_delay_min_s=0.5,
            cue_delay_max_s=1.5,
            seed=seed,
        )
        d.start(0.0)
        d.update(0.0, person(y=1525.0))
        d.update(0.02, person(y=1525.0))
        assert d.state == "armed"
        delays.add(round(d.cue_at - 0.02, 6))
        d.update(d.cue_at, person(y=1525.0))
        assert d.state == "active"
        assert d.target != d.arm_zone
        targets.add(d.target)

    assert len(delays) > 1
    assert targets == {0, 2}


def test_reaction_zones_target_reached_after_timeout_is_a_miss():
    d = reaction_drill(rounds=1, cue_timeout_s=0.5)
    d.state = "active"
    d.target = 0
    d.arm_zone = 1
    d.go_time = 1.0

    d.update(1.501, person(y=d.target_centres_mm[0]))

    assert d.last_result == ("miss", None)
    assert d.hits == 0
    assert d.summary()["hits_in_timeout"] == 0


def test_reaction_zones_hit_miss_metrics_and_weakest_zone():
    d = reaction_drill(rounds=2)
    d.start(0.0)

    # Round 1: arm in CENTER, then hit the randomly selected outer target.
    d.update(0.0, person(y=1525.0))
    d.update(0.11, person(y=1525.0))
    assert d.state == "armed"
    d.update(0.32, person(y=1525.0))
    assert d.state == "active"
    first_target = d.target
    d.update(0.57, person(y=d.target_centres_mm[first_target]))
    assert d.last_result[0] == "hit"

    # Round 2 starts where round 1 ended. Holding that starting zone through
    # timeout is positive tracking in the wrong zone, therefore a real miss.
    d.update(0.68, person(y=d.target_centres_mm[first_target]))
    assert d.state == "set_wait"
    d.update(0.70, person(y=d.target_centres_mm[first_target]))
    d.update(0.81, person(y=d.target_centres_mm[first_target]))
    assert d.state == "armed"
    d.update(1.02, person(y=d.target_centres_mm[first_target]))
    assert d.state == "active"
    second_target = d.target
    assert second_target != first_target
    d.update(1.53, person(y=d.target_centres_mm[first_target]))
    assert d.last_result[0] == "miss"
    d.update(1.64, person(y=d.target_centres_mm[first_target]))
    assert d.state == "done"

    summary = d.summary()
    assert summary["rounds_completed"] == 2
    assert summary["hits_in_timeout"] == 1
    assert summary["avg_reaction_s"] == pytest.approx(0.25)
    assert set(summary["per_zone"]) == {"LEFT", "CENTER", "RIGHT"}
    assert summary["weakest_zone"] == d.zone_name(second_target)
    assert "score" not in json.dumps(summary).lower()


def test_reaction_zones_protocol_parameters_and_v1_record(tmp_path):
    assert validate_workload("reaction_zones", 5) == 5
    assert validate_workload("reaction_zones", 20) == 20
    for invalid in (4, 21):
        with pytest.raises(ValueError, match="between 5 and 20"):
            validate_workload("reaction_zones", invalid)

    drill = reaction_drill(rounds=10)
    spec = PROTOCOL_CATALOG["reaction_zones"]
    assert spec["protocol_id"] == "reaction_zones.v1"
    params = applied_parameters(drill)
    assert params == {
        "rounds": 10,
        "arena_y_mm": 3050.0,
        "wall_margin_mm": 500.0,
        "arm_hold_s": 0.1,
        "cue_timeout_s": 0.5,
        "cue_delay_min_s": 0.2,
        "cue_delay_max_s": 0.2,
    }
    context = {
        "protocol_id": spec["protocol_id"],
        "applied_parameters": params,
        "protocol_parameters_fingerprint":
            protocol_parameters_fingerprint(spec["protocol_id"], params),
    }
    record = build_session_record(
        drill,
        "Арлен",
        "2026-07-30T10:00:00",
        "2026-07-30T10:02:00",
        session_id="reaction-session-1",
        evidence_context=context,
    )
    assert record["schema"] == "project_cam.training.v1"
    assert record["drill"] == "reaction_zones"
    assert record["session_id"] == "reaction-session-1"
    assert record["evidence_context"] == context
    assert context["protocol_parameters_fingerprint"].startswith("sha256:")

    index = tmp_path / "sessions_index.jsonl"
    append_session_index(index, record)
    stored = [json.loads(line) for line in index.read_text().splitlines()]
    assert stored == [record]


# ------------------------------------------------------------------ balance

def test_balance_waits_for_tracking_before_first_hold():
    d = BalanceDrill(holds=1, hold_s=2.0, countdown_s=1.0)
    d.start(0.0)
    d.update(1.2, None)                      # countdown elapsed, nobody there
    assert d.state == "countdown"
    assert d.waiting_tracking is True
    d.update(1.3, person())                  # athlete appears
    d.update(2.4, person())                  # next countdown elapses tracked
    assert d.state == "hold"


def test_balance_measures_sway_and_touchdowns():
    d = BalanceDrill(holds=1, hold_s=4.0, countdown_s=1.0,
                     raise_mm=120.0, touch_mm=60.0)
    d.start(0.0)
    d.update(0.5, person())
    d.update(1.0, person())                  # -> hold at t=1.0
    assert d.state == "hold"
    t = 1.0
    # single-leg (right ankle raised 200mm) with a small sway circle
    for i in range(30):
        t += 0.1
        ang = i * 0.7
        j = person(x=3000 + 10 * math.cos(ang), y=1500 + 10 * math.sin(ang),
                   ra_z=280.0)
        d.update(t, j)
    # a REAL touchdown: foot stays down long enough for the median filter
    for k in range(5):
        d.update(t + 0.1 * (k + 1), person())     # dz ~0 for 0.5 s
    assert d.raised is False
    assert d.touchdowns == 1
    d.update(5.05, person(ra_z=280.0))            # hold window elapses
    assert d.state == "done"
    (ev,) = d.pop_events()
    assert ev["event"] == "hold"
    assert ev["stance"] == "left"
    assert ev["touchdowns"] == 1
    assert 5.0 <= ev["sway_rms_mm"] <= 15.0  # 10mm circle -> ~10mm RMS
    assert ev["score"] is not None
    s = d.summary()
    assert s["holds_completed"] == 1
    assert s["left_sway_mm"] == ev["sway_rms_mm"]
    assert "sway" in d.headline()


def test_balance_alternates_stance_legs():
    d = BalanceDrill(holds=2, hold_s=1.0, rest_s=0.5, countdown_s=0.5)
    assert d.stance_leg(0) == "left"
    assert d.stance_leg(1) == "right"


def test_balance_single_frame_lr_swap_is_ignored():
    """A one-frame ankle L/R swap (dz sign flip) must not register a
    touch-down or drop the raised state — the median window absorbs it."""
    d = BalanceDrill(holds=1, hold_s=3.0, countdown_s=1.0)
    d.start(0.0)
    d.update(0.5, person())
    d.update(1.0, person())                       # -> hold
    assert d.state == "hold"
    t = 1.0
    for _ in range(10):                           # clean single-leg second
        t += 0.1
        d.update(t, person(ra_z=280.0))
    assert d.raised is True
    # one frame where the tracker swaps the ankles (dz flips sign)
    d.update(t + 0.1, person(ra_z=80.0, la_z=280.0))
    for k in range(8):
        d.update(t + 0.2 + 0.1 * k, person(ra_z=280.0))
    assert d.raised is True                       # never dropped
    assert d.touchdowns == 0
    d.update(4.2, person(ra_z=280.0))             # hold window elapses
    assert d.state == "done"
    (ev,) = d.pop_events()
    assert ev["touchdowns"] == 0


def test_balance_subsecond_flap_does_not_count_touchdown():
    """A raise shorter than min_raised_s is jitter: putting it down again
    must not increment the touch-down counter."""
    d = BalanceDrill(holds=1, hold_s=4.0, countdown_s=1.0, min_raised_s=0.4,
                     dz_window_s=0.1)
    d.start(0.0)
    d.update(0.5, person())
    d.update(1.0, person())                       # -> hold
    t = 1.0
    for _ in range(5):                            # both feet down 0.5 s
        t += 0.1
        d.update(t, person())
    d.update(t + 0.1, person(ra_z=280.0))         # up for ONE frame (0.1 s)
    d.update(t + 0.2, person(ra_z=280.0))
    assert d.raised is True
    for k in range(5):                            # straight back down
        d.update(t + 0.3 + 0.1 * k, person())
    assert d.raised is False
    assert d.touchdowns == 0                      # 0.2 s raise = noise


# ------------------------------------------------------------------ shuttle

def walk_updates(drill, t0, positions, dt=0.1):
    t = t0
    for x in positions:
        t += dt
        drill.update(t, person(x=x))
    return t


def test_shuttle_full_rep_with_interpolated_splits():
    d = ShuttleDrill(reps=1, countdown_s=1.0, center_mm=3000.0, half_mm=2000.0,
                     arm_tol_mm=300.0, arm_hold_s=0.5)
    d.start(0.0)
    d.update(0.1, person(x=3050))            # in the center zone
    d.update(0.7, person(x=3050))            # held 0.6s -> countdown
    assert d.state == "countdown"
    d.update(1.8, person(x=3050))            # countdown elapsed -> run
    assert d.state == "run" and d.phase == "to_a"
    # sprint out: crosses A=5000 between samples 4900 -> 5100
    d.update(2.0, person(x=3050))
    d.update(2.5, person(x=4900))
    d.update(2.6, person(x=5100))
    assert d.phase == "to_b"
    # back across: crosses B=1000 (900 after 1100)
    d.update(3.5, person(x=1100))
    d.update(3.6, person(x=900))
    assert d.phase == "home"
    # home: crosses center=3000
    d.update(4.1, person(x=2900))
    d.update(4.2, person(x=3100))
    assert d.state == "done"
    (rep,) = d.pop_events()
    assert rep["event"] == "rep"
    # crossing of A interpolated at exactly halfway between 2.5 and 2.6
    assert abs(rep["t_out_s"] - (2.55 - 1.8)) < 1e-6
    assert abs(rep["total_s"] - (4.15 - 1.8)) < 1e-6
    s = d.summary()
    assert s["best_total_s"] == rep["total_s"]
    assert s["best_splits_s"]["out"] == rep["t_out_s"]
    assert "best" in d.headline()


def test_shuttle_aborts_on_tracking_loss_and_lets_athlete_retry():
    d = ShuttleDrill(reps=1, countdown_s=0.5, arm_hold_s=0.2, lost_abort_s=1.0,
                     rest_s=0.5, center_mm=3000.0)
    d.start(0.0)
    d.update(0.1, person(x=3000))
    d.update(0.4, person(x=3000))            # armed -> countdown
    d.update(1.0, person(x=3000))            # -> run
    assert d.state == "run"
    d.update(1.5, None)
    d.update(2.6, None)                      # lost > 1.0s
    assert d.state == "rest"
    assert d.aborts == 1
    (ev,) = d.pop_events()
    assert ev["event"] == "rep_abort"
    assert ev["reason"] == "tracking lost"
    d.update(3.2, person(x=3000))            # rest over -> arm again
    assert d.state == "arm"


def test_shuttle_rep_timeout_aborts():
    d = ShuttleDrill(reps=1, countdown_s=0.5, arm_hold_s=0.2, rep_timeout_s=5.0,
                     center_mm=3000.0)
    d.start(0.0)
    d.update(0.1, person(x=3000))
    d.update(0.4, person(x=3000))
    d.update(1.0, person(x=3000))            # run
    d.update(6.1, person(x=3200))            # never reaches a line
    assert d.state == "rest"
    assert d.pop_events()[0]["reason"] == "timeout"


# ---------------------------------------------------------------- line hops

def test_line_hops_counts_crossings_with_hysteresis():
    d = LineHopsDrill(sets=1, work_s=5.0, countdown_s=1.0, hys_mm=60.0)
    d.start(0.0)
    # calibration window: standing at y=1500
    d.update(0.5, person(ankle_y=1500))
    d.update(0.9, person(ankle_y=1500))
    d.update(1.05, person(ankle_y=1500))     # countdown ends -> work, line=1500
    assert d.state == "work"
    assert abs(d.line - 1500) < 1e-6
    t = 1.1
    # 4 clean side-to-side jumps (+250 / -250 around the line)
    for y in (1750, 1250, 1750, 1250):
        t += 0.3
        d.update(t, person(ankle_y=y))
    # jitter inside the hysteresis band must NOT count
    for y in (1530, 1470, 1520, 1480):
        t += 0.1
        d.update(t, person(ankle_y=y))
    d.update(6.2, person(ankle_y=1250))      # work window elapses
    assert d.state == "done"
    (ev,) = d.pop_events()
    assert ev["crossings"] == 3              # 4 positions -> 3 side flips
    assert d.summary()["total_crossings"] == 3
    assert "hops" in d.headline()


def test_line_hops_waits_for_tracking():
    d = LineHopsDrill(sets=1, countdown_s=0.5)
    d.start(0.0)
    d.update(0.6, None)
    assert d.state == "countdown" and d.waiting_tracking is True


# ------------------------------------------------------------------ gk save

def gk_set(x=3000.0, y=1525.0):
    return person(x=x, y=y)                  # center third of 3050mm width


def test_gk_save_hit_high_left_and_per_corner_stats():
    d = GkSaveDrill(rounds=1, arena_y_mm=3050.0, set_hold_s=0.4,
                    cue_delay_min_s=0.5, cue_delay_max_s=0.5, seed=3)
    d.start(0.0)
    d.update(0.1, gk_set())
    d.update(0.3, gk_set())
    d.update(0.6, gk_set())                  # held 0.5s >= 0.4 -> armed
    assert d.state == "armed"
    assert d.shoulder_ref is not None and d.hip_ref is not None
    d.update(1.2, gk_set())                  # past cue_at=0.6+0.5 -> active
    assert d.state == "active"
    side, high = d.target
    assert side in (0, 2) and isinstance(high, bool)
    # put a wrist into the cued corner
    wrist_y = 300.0 if side == 0 else 2750.0
    wrist_z = (d.shoulder_ref + 300.0) if high else (d.hip_ref * 0.6 - 100.0)
    j = gk_set()
    j["right_wrist"] = (3000.0, wrist_y, wrist_z)
    d.update(1.5, j)
    assert d.state == "result"
    assert d.saves == 1
    (ev,) = d.pop_events()
    assert ev["result"] == "save"
    assert abs(ev["reaction_s"] - 0.3) < 1e-6
    assert ev["corner"] == d.corner_name((side, high))
    d.update(3.0, gk_set())                  # result window elapses -> done
    assert d.state == "done"
    s = d.summary()
    assert s["saves"] == 1 and s["save_pct"] == 100.0
    assert s["per_corner"][ev["corner"]]["saves"] == 1
    assert "saves" in d.headline()


def test_gk_save_wrong_height_is_not_a_save_and_times_out():
    d = GkSaveDrill(rounds=1, set_hold_s=0.2, cue_delay_min_s=0.1,
                    cue_delay_max_s=0.1, cue_timeout_s=1.0, seed=0)
    d.start(0.0)
    d.update(0.05, gk_set())
    d.update(0.15, gk_set())
    d.update(0.25, gk_set())                 # armed
    d.update(0.5, gk_set())                  # active
    assert d.state == "active"
    side, high = d.target
    # correct side but hands at chest height: neither HIGH nor LOW band
    wrist_y = 300.0 if side == 0 else 2750.0
    j = gk_set()
    j["left_wrist"] = (3000.0, wrist_y, d.hip_ref + 200.0)
    d.update(0.9, j)
    assert d.state == "active"               # not a save
    d.update(1.6, gk_set())                  # timeout
    assert d.state == "result"
    assert d.pop_events()[0]["result"] == "miss"
    assert d.summary()["weakest_corner"] == d.corner_name()


def test_gk_save_rearms_if_keeper_leaves_center_early():
    d = GkSaveDrill(rounds=1, set_hold_s=0.2, cue_delay_min_s=5.0,
                    cue_delay_max_s=5.0, seed=1)
    d.start(0.0)
    d.update(0.05, gk_set())
    d.update(0.15, gk_set())
    d.update(0.3, gk_set())                  # armed, cue far away
    assert d.state == "armed"
    d.update(0.4, person(y=300))             # wandered into LEFT third
    assert d.state == "set_wait"


# ---------------------------------------------------------------- gk updown

def test_gk_updown_counts_reps_and_recovery_times():
    d = GkUpDownDrill(duration_s=20.0, countdown_s=1.0, down_frac=0.55,
                      up_frac=0.85, up_hold_s=0.2)
    d.start(0.0)
    for i in range(6):
        d.update(0.1 + i * 0.1, person(hip_z=1000))
    d.update(1.05, person(hip_z=1000))       # countdown done, stand_z=1000
    assert d.state == "work"
    assert abs(d.stand_z - 1000) < 1e-6
    # rep 1: down at t=2.0 (held for down_hold_s), back over the up-threshold at
    # 3.0, held 0.2 s. The recovery clock runs from the FIRST sample below the
    # threshold, so holding the down does not shorten the measured recovery.
    d.update(2.0, person(hip_z=400))         # below 550 -> pending down
    d.update(2.3, person(hip_z=400))         # held >= 0.25 -> down
    assert d.phase == "down"
    d.update(3.0, person(hip_z=900))         # above 850 -> pending up
    d.update(3.25, person(hip_z=920))        # held >= 0.2 -> rep!
    assert d.reps == 1
    (ev,) = d.pop_events()
    assert ev["event"] == "rep"
    assert abs(ev["recovery_s"] - 1.0) < 1e-6
    # bouncing above/below the up threshold must not count a rep
    d.update(4.0, person(hip_z=400))
    d.update(4.3, person(hip_z=400))
    d.update(4.9, person(hip_z=900))
    d.update(4.95, person(hip_z=800))        # dropped before hold satisfied
    d.update(5.1, person(hip_z=900))
    d.update(5.35, person(hip_z=920))        # held from 5.1 -> rep 2
    assert d.reps == 2
    d.update(25.0, person(hip_z=1000))       # duration elapsed
    assert d.state == "done"
    s = d.summary()
    assert s["reps"] == 2
    assert s["best_recovery_s"] is not None
    assert "down-ups" in d.headline()


def test_gk_updown_waits_for_tracking_before_starting_clock():
    d = GkUpDownDrill(duration_s=5.0, countdown_s=0.5)
    d.start(0.0)
    d.update(0.6, None)
    assert d.state == "countdown" and d.waiting_tracking is True


# ------------------------------------------------------------- session logs

def test_session_record_and_index_roundtrip(tmp_path):
    d = GkUpDownDrill()
    record = build_session_record(
        d,
        "Арлен",
        "2026-07-16T10:00:00",
        "2026-07-16T10:01:00",
        aborted=False,
        session_id="desktop-session-1",
    )
    assert record["schema"] == "project_cam.training.v1"
    assert record["drill"] == "gk_updown"
    assert record["athlete"] == "Арлен"
    assert record["session_id"] == "desktop-session-1"
    assert record["headline"] == d.headline()
    standalone = build_session_record(
        d,
        "Арлен",
        "2026-07-16T10:00:00",
        "2026-07-16T10:01:00",
    )
    assert "session_id" not in standalone
    index = tmp_path / "logs" / "sessions_index.jsonl"
    append_session_index(index, record)
    append_session_index(index, dict(record, athlete="Bob"))
    lines = index.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["athlete"] == "Арлен"   # readable, not \u-escaped
    assert "Арлен" in lines[0]


# ------------------------------------------------- cmj (load monitoring)

def cmj_pose(z):
    return {"left_hip": (500.0, 1435.0, z), "right_hip": (500.0, 1615.0, z)}


def cmj_calibrated(**kw):
    d = DRILL_REGISTRY["cmj"](countdown_s=1.0, calib_s=0.6, **kw)
    d.start(0.0)
    t = 0.0
    for _ in range(12):
        t += 0.1
        d.update(t, cmj_pose(950.0))
    assert d.state == "work" and d.stand_z == pytest.approx(950.0)
    return d, t


def jump(d, t, peak):
    for z in (880.0, 870.0, peak, peak - 40.0, 960.0, 950.0):
        t += 0.08
        d.update(t, cmj_pose(z))
    return t


def test_cmj_calibration_needs_a_tracked_athlete():
    """Autostart safety: the countdown must loop rather than calibrate a
    standing height from nothing."""
    d = DRILL_REGISTRY["cmj"](countdown_s=1.0, calib_s=0.6)
    d.start(0.0)
    t = 0.0
    for _ in range(30):
        t += 0.1
        d.update(t, None)
    assert d.state == "countdown"
    assert d.stand_z is None


def test_cmj_measures_pelvis_rise_above_standing():
    d, t = cmj_calibrated(jumps=2)
    t = jump(d, t, 1120.0)
    assert d.results[0]["pelvis_rise_mm"] == pytest.approx(170.0, abs=1.0)


def test_cmj_reports_drop_off_across_the_set():
    """The commercial point of the test: fatigue shows up as decay, so the
    trend matters more than any single jump."""
    d, t = cmj_calibrated(jumps=6)
    for peak in (1120.0, 1118.0, 1112.0, 1090.0, 1070.0, 1055.0):
        t = jump(d, t, peak)
    s = d.summary()
    assert s["jumps_completed"] == 6
    assert s["drop_off_pct"] is not None and s["drop_off_pct"] < 0
    assert s["best_pelvis_rise_mm"] == pytest.approx(170.0, abs=1.0)


def test_cmj_abandons_a_dip_that_never_becomes_a_jump():
    d, t = cmj_calibrated(jumps=2)
    for _ in range(40):                       # squat down and just stay there
        t += 0.1
        d.update(t, cmj_pose(870.0))
    assert d.results == []
    t += 0.1
    d.update(t, cmj_pose(950.0))              # stand back up
    assert d.state == "work"


def test_cmj_never_reports_a_jump_height():
    """Pelvis rise is not a force-plate jump height; the summary must not imply
    it is, because an academy will otherwise compare it to published norms."""
    d, _ = cmj_calibrated(jumps=1)
    keys = " ".join(DRILL_REGISTRY["cmj"](jumps=1).summary())
    assert "pelvis_rise" in keys
    assert "jump_height" not in keys


# --------------------------------------- hop symmetry (return-to-play)

def hop_pose(x):
    return {"left_hip": (x, 1435.0, 950.0), "right_hip": (x, 1615.0, 950.0)}


def run_hops(distances, **kw):
    d = DRILL_REGISTRY["hop_symmetry"](countdown_s=1.0, arm_hold_s=0.3,
                                       settle_hold_s=0.3,
                                       hops_per_leg=len(distances) // 2, **kw)
    d.start(0.0)
    t = 0.0
    for _ in range(12):
        t += 0.1
        d.update(t, hop_pose(500.0))
    for reach in distances:
        for _ in range(6):                    # back on the line, holding still
            t += 0.1
            d.update(t, hop_pose(500.0))
        for _ in range(8):                    # hop out and stabilise
            t += 0.1
            d.update(t, hop_pose(500.0 + reach))
    return d


def test_walking_back_to_the_line_is_not_a_hop():
    """The defect this test exists for: distance was measured from wherever the
    athlete last stood, so the walk back counted as a hop of the other leg and
    both legs came out identical. Left 1400 / right 1150 must stay 1400 / 1150.
    """
    d = run_hops([1400.0, 1150.0, 1400.0, 1150.0])
    legs = d.per_leg()
    assert legs["left"]["best_mm"] == pytest.approx(1400.0, abs=1.0)
    assert legs["right"]["best_mm"] == pytest.approx(1150.0, abs=1.0)
    assert d.summary()["limb_symmetry_pct"] == pytest.approx(82.1, abs=0.5)
    assert d.summary()["weaker_leg"] == "right"


def test_hop_symmetry_keeps_both_raw_distances():
    """Symmetry can be met while both limbs are weak, so the index alone is not
    enough to act on."""
    s = run_hops([1400.0, 1400.0]).summary()
    assert s["limb_symmetry_pct"] == pytest.approx(100.0)
    assert s["per_leg"]["left"]["best_mm"] is not None
    assert s["per_leg"]["right"]["best_mm"] is not None
    assert s["symmetry_reference_pct"] == 90.0


def test_a_shuffle_shorter_than_a_hop_is_not_recorded():
    d = run_hops([120.0, 120.0])
    assert d.results == []
    assert d.summary()["limb_symmetry_pct"] is None


def test_legs_alternate_starting_left():
    d = run_hops([1000.0, 1000.0, 1000.0, 1000.0])
    assert [r["leg"] for r in d.results] == ["left", "right", "left", "right"]


# ------------------------------------------- reactive cut (the differentiator)

def cut_pose(x, y):
    return {"left_hip": (x, y - 90.0, 950.0), "right_hip": (x, y + 90.0, 950.0)}


def armed_cut(**kw):
    d = DRILL_REGISTRY["reactive_cut"](arena_x_mm=6230.0, arena_y_mm=3050.0,
                                       arm_hold_s=0.3, result_s=0.3, **kw)
    d.start(0.0)
    t = 0.0
    for _ in range(6):
        t += 0.1
        d.update(t, cut_pose(300.0, 1525.0))
    assert d.state == "approach"
    t += 0.1
    d.update(t, cut_pose(3200.0, 1525.0))     # cross the cue line
    assert d.state == "active" and d.target in d.SIDES
    return d, t


def test_the_cue_fires_only_at_the_commitment_point():
    """A timing gate can time a rehearsed shuttle; the cue has to arrive while
    the athlete is already running or the drill measures nothing reactive."""
    d = DRILL_REGISTRY["reactive_cut"](arena_x_mm=6230.0, arena_y_mm=3050.0,
                                       arm_hold_s=0.3, reps=4, seed=1)
    d.start(0.0)
    t = 0.0
    for _ in range(6):
        t += 0.1
        d.update(t, cut_pose(300.0, 1525.0))
    for x in (1000.0, 2000.0, 3000.0):
        t += 0.1
        d.update(t, cut_pose(x, 1525.0))
        assert d.target is None, f"cue leaked before the line at x={x}"
    t += 0.1
    d.update(t, cut_pose(d.trigger_x_mm + 10.0, 1525.0))
    assert d.target is not None


def test_decision_and_execution_are_reported_separately():
    d, t = armed_cut(reps=2, seed=4)
    side = d.target
    offset = 900.0 if side == "RIGHT" else -900.0
    t += 0.25
    d.update(t, cut_pose(3400.0, 1525.0 + offset * 0.25))   # commits
    t += 0.25
    d.update(t, cut_pose(3600.0, 1525.0 + offset))          # clears the gate
    row = d.results[-1]
    assert row["result"] == "hit"
    assert row["decision_s"] is not None
    assert row["execution_s"] is not None
    assert row["decision_s"] < row["execution_s"]


def test_a_wrong_way_cut_is_an_error_not_a_discard():
    d, t = armed_cut(reps=2, seed=4)
    wrong = -900.0 if d.target == "RIGHT" else 900.0
    t += 0.3
    d.update(t, cut_pose(3500.0, 1525.0 + wrong))
    assert d.last_result[0] == "error"
    assert d.summary()["wrong_way_cuts"] == 1
    assert d.results[-1]["cued"] != d.results[-1]["went"]


def test_no_cut_within_the_timeout_is_a_miss():
    d, t = armed_cut(reps=2, seed=4)
    for _ in range(40):
        t += 0.1
        d.update(t, cut_pose(3300.0, 1525.0))
        if d.state != "active":
            break
    assert d.last_result[0] == "miss"


def test_tracking_loss_voids_a_cut_without_spending_a_rep():
    d, t = armed_cut(reps=3, seed=4)
    for _ in range(20):
        t += 0.1
        d.update(t, None)
        if d.state != "active":
            break
    assert d.last_result[0] == "void"
    assert d.summary()["voided_reps"] == 1
    assert d.summary()["reps_completed"] == 0, "a void must not consume a rep"


def test_a_gate_wider_than_the_arena_is_refused():
    """Fail closed rather than asking a garage athlete to reach a gate that does
    not fit between the walls."""
    with pytest.raises(ValueError, match="exceeds half the arena width"):
        DRILL_REGISTRY["reactive_cut"](arena_x_mm=6230.0, arena_y_mm=1200.0,
                                       gate_mm=700.0)


# ---------------------------------------------------------------------------
# GK 1b — SAVE THE CORNERS, served by the launcher
# ---------------------------------------------------------------------------
#
# The point of this drill is that a REAL delivery is the cue, so nearly every
# property below is about refusing to score what the ball track did not show.

GOAL_X = 6230.0
KEEPER_X = 5400.0


def served(**kw):
    kw.setdefault("serves", 3)
    kw.setdefault("goal_x_mm", GOAL_X)
    return DRILL_REGISTRY["gk_save_served"](**kw)


def keeper(y_hand=1525.0, z_hand=1200.0, x=KEEPER_X, y_pelvis=1525.0):
    return J(
        left_hip=(x, y_pelvis - 90, 900.0), right_hip=(x, y_pelvis + 90, 900.0),
        left_shoulder=(x, y_pelvis - 160, 1300.0),
        right_shoulder=(x, y_pelvis + 160, 1300.0),
        left_wrist=(x, y_hand, z_hand), right_wrist=(x, y_hand + 200, z_hand),
    )


def ball_at(x, y, z, vx=10000.0, coasting=False):
    return {"x_mm": x, "y_mm": y, "z_mm": z, "vx_mm_s": vx, "vy_mm_s": 0.0,
            "vz_mm_s": 0.0, "mode": "AIRBORNE", "cams": 3, "coasting": coasting}


def arm_served(d, t=100.0):
    d.start(t)
    for _ in range(15):
        t += 1 / 15
        d.update(t, keeper(), None)
    assert d.state == "armed", d.state
    return t


def deliver(d, t, target_y, target_z, *, hand="still", speed=10000.0,
            react_after=4, drop=(), coasting=False, dt=1 / 15):
    """One scripted delivery from x=300 to the goal plane."""
    duration = (GOAL_X - 300.0) / speed
    y0, z0 = 1525.0, 1200.0
    for i in range(int(duration / dt) + 2):
        frac = min(1.0, (i * dt) / duration)
        x = 300.0 + frac * (GOAL_X - 300.0)
        y, z = y0 + frac * (target_y - y0), z0 + frac * (target_z - z0)
        if hand == "follow" and i >= react_after:
            k = min(1.0, (i - react_after) / 3.0)
            j = keeper(y0 + k * (y - y0), z0 + k * (z - z0))
        elif hand == "prepositioned":
            j = keeper(target_y, target_z)
        else:
            j = keeper()
        b = None if i in drop else ball_at(x, y, z, speed, coasting=coasting)
        t += dt
        d.update(t, j, b)
        if d.state == "result":
            break
    return t


def one_serve(**kw):
    d = served()
    t = arm_served(d)
    deliver(d, t, **kw)
    return d


def last_void(d):
    voids = [e for e in d._events if e["event"] == "round_void"]
    return voids[-1]["reason"] if voids else None


def test_a_served_save_measures_reaction_from_the_delivery_not_a_screen():
    """The whole reason this drill exists: the virtual version measures reaction
    to a scoreboard, which a keeper never watches while facing a shot."""
    d = one_serve(target_y=2400.0, target_z=1600.0, hand="follow")
    row = d.results[-1]
    assert row["result"] == "save"
    assert row["corner"] == "HIGH-RIGHT"
    assert row["reaction_s"] >= 0.10, row
    assert row["min_hand_mm"] < d.save_radius_mm
    assert d.summary()["saves"] == 1


def test_an_untouched_delivery_is_a_goal():
    d = one_serve(target_y=600.0, target_z=400.0)
    assert d.results[-1]["result"] == "goal"
    assert d.results[-1]["corner"] == "LOW-LEFT"
    assert d.summary()["save_rate"] == 0.0


def test_a_serve_outside_the_posts_is_not_charged_to_the_keeper():
    """The launcher's aim is not commissioned, so a delivery that missed the goal
    is a launcher finding — scoring it as the keeper's miss would blame them for
    it and quietly depress the save rate."""
    d = one_serve(target_y=2900.0, target_z=1600.0)
    row = d.results[-1]
    assert row["result"] == "wide"
    assert row["corner"] is None
    s = d.summary()
    assert s["wide_serves"] == 1
    assert s["rounds_completed"] == 0, "a wide serve was never a chance"
    assert s["save_rate"] is None
    assert "missed the goal" in d.headline()


def test_a_ball_over_the_bar_is_also_wide():
    d = one_serve(target_y=1525.0, target_z=2400.0)
    assert d.results[-1]["result"] == "wide"


def test_a_centre_ball_is_scored_but_never_credited_to_a_corner():
    """Found by the first scripted delivery: a pure 2x2 partition labelled a ball
    crossing exactly on the centre line as HIGH-RIGHT. That is worthless as
    corner evidence and would have polluted the per-corner table a coach reads to
    pick the keeper's weak side."""
    d = one_serve(target_y=1525.0, target_z=1200.0, hand="prepositioned")
    row = d.results[-1]
    assert row["corner"] == "CENTRE"
    assert row["result"] == "save"
    assert d.summary()["saves"] == 1, "still a real chance and a real save"
    assert d.per_corner() == {}, "a centre ball is evidence about neither side"


def test_a_save_with_no_committed_movement_is_a_save_not_an_anticipation():
    """A ball served straight at hands that are already there is goalkeeping. The
    first version of the resolve branch scored it as a fault, because an
    unmeasured reaction failed the plausibility floor."""
    d = one_serve(target_y=1525.0, target_z=1200.0, hand="prepositioned")
    row = d.results[-1]
    assert row["result"] == "save"
    assert row["reaction_s"] is None
    assert d.summary()["anticipated"] == 0
    assert d.summary()["avg_reaction_s"] is None, "nothing to average"


def test_a_hand_that_moved_before_a_human_could_read_the_serve_is_not_scored():
    d = one_serve(target_y=2400.0, target_z=1600.0, hand="follow", react_after=0)
    row = d.results[-1]
    assert row["result"] == "anticipated"
    assert d.summary()["saves"] == 0
    assert d.summary()["anticipated"] == 1


def test_a_gap_in_the_ball_track_voids_a_goal_but_not_a_save():
    """The asymmetry that keeps the save rate honest.

    A touch is positively observed on a tight segment, so a gap elsewhere cannot
    invent it. "No touch" is exactly the verdict a gap CAN fabricate, so it is
    voided rather than credited.
    """
    missed = one_serve(target_y=600.0, target_z=400.0, drop=(2, 3, 4, 5, 6, 7))
    assert missed.results == []
    assert last_void(missed) == "ball_track_gap_unresolved"
    assert missed.summary()["goals"] == 0

    saved = one_serve(target_y=2400.0, target_z=1600.0, hand="follow",
                      drop=(1, 2))
    assert saved.results[-1]["result"] == "save", (
        "an observed touch survives a gap elsewhere in the flight")


def test_a_coasted_position_is_never_treated_as_a_measurement():
    """A coasting sample is the Kalman filter predicting through a detection
    drop. Scoring a save on one would be scoring an extrapolation."""
    d = served()
    t = arm_served(d)
    deliver(d, t, target_y=600.0, target_z=400.0, coasting=True)
    assert d.state == "armed", "no serve may be detected from coasted samples"
    assert d.results == []
    assert d.round_idx == 0, "and no round is consumed"


def test_a_ball_that_is_merely_moving_is_not_a_serve():
    """Below the serve-speed floor a reaction clock would start against a
    stimulus the keeper cannot read — someone walking the ball back, say."""
    d = served()
    t = arm_served(d)
    deliver(d, t, target_y=600.0, target_z=400.0, speed=800.0)
    assert d.state == "armed"
    assert d.results == []


def test_a_delivery_moving_away_from_the_goal_is_not_a_serve():
    d = served()
    t = arm_served(d)
    for x in (5000.0, 4000.0, 3000.0, 2000.0):
        t += 1 / 15
        d.update(t, keeper(), ball_at(x, 1525.0, 1200.0))
    assert d.state == "armed", "a ball leaving the goal is not a delivery"


def test_a_ball_acquired_behind_the_keeper_leaves_no_reaction_to_measure():
    """Same defect class as cueing a corner the keeper already occupies: if the
    delivery is first seen past the keeper there is nothing to react to."""
    d = served()
    t = arm_served(d)
    for x in (5900.0, 6000.0, 6100.0):
        t += 1 / 15
        d.update(t, keeper(), ball_at(x, 1525.0, 1200.0))
    assert d.state == "armed"


def test_a_serve_that_never_reaches_the_goal_plane_is_voided():
    d = served()
    t = arm_served(d)
    for i in range(60):
        t += 1 / 15
        d.update(t, keeper(), ball_at(1000.0 + i, 1525.0, 1200.0, vx=9000.0))
        if d.state == "result":
            break
    assert last_void(d) == "no_goal_plane_crossing"
    assert d.results == []


def test_the_keeper_must_be_in_the_goal_mouth_to_arm():
    d = served()
    t = 100.0
    d.start(t)
    for _ in range(20):                       # standing at the far end
        t += 1 / 15
        d.update(t, keeper(x=1200.0), None)
    assert d.state == "set_wait"
    for _ in range(20):                       # inside the posts, wrong side
        t += 1 / 15
        d.update(t, keeper(y_pelvis=2900.0), None)
    assert d.state == "set_wait"


def test_leaving_the_set_position_disarms_but_a_dropout_does_not():
    """The armed-state rule every drill follows: only POSITIVE evidence of
    leaving resets it, never a missed packet."""
    d = served()
    t = arm_served(d)
    for _ in range(5):
        t += 1 / 15
        d.update(t, None, None)
    assert d.state == "armed", "a tracking dropout must not disarm"
    for _ in range(3):
        t += 1 / 15
        d.update(t, keeper(x=1000.0), None)
    assert d.state == "set_wait"


def test_a_goal_that_does_not_fit_the_room_is_refused_not_clamped():
    """A clamped goal would score corners that are not where the tape says.

    The MESSAGE is pinned, not just the exception. A goal wider than the room also
    spans outside it, so the width check is redundant for correctness — what it
    uniquely gives the operator is a refusal that names the measurement they got
    wrong, while standing in the garage with a tape.
    """
    with pytest.raises(ValueError, match=r"goal width 4000 mm exceeds the arena"):
        served(goal_w_mm=4000.0)
    with pytest.raises(ValueError, match=r"outside the arena width"):
        served(goal_center_y_mm=200.0)
    with pytest.raises(ValueError, match=r"positive extent"):
        served(goal_h_mm=0.0)
    with pytest.raises(ValueError, match=r"save_radius_mm must be positive"):
        served(save_radius_mm=0.0)


def test_the_segment_test_is_what_makes_a_save_detectable_at_speed():
    """At 15 Hz a 10 m/s delivery advances ~667 mm per packet, so a
    point-to-point hand test would miss nearly every genuine save. Compared
    directly: the hand sits ON the path but far from both endpoints."""
    a, b = (0.0, 0.0, 0.0), (1000.0, 0.0, 0.0)
    hand = (500.0, 30.0, 0.0)
    assert segment_point_distance(a, b, hand) == pytest.approx(30.0)
    assert min(math.dist(a, hand), math.dist(b, hand)) > 400.0


def test_a_plane_crossing_is_only_reported_when_the_segment_straddles_it():
    """A crossing inferred from two samples on the same side is invented.

    Both directions and both sides, because the straddle test is now the SINGLE
    gate: the redundant `0 <= frac <= 1` bound was removed after a mutation sweep
    showed the two were exactly equivalent, so neither could be tested alone.
    """
    for a, b in (((0.0, 100.0, 200.0), (400.0, 100.0, 200.0)),      # both before
                 ((6400.0, 100.0, 200.0), (6800.0, 100.0, 200.0)),  # both past
                 ((6800.0, 100.0, 200.0), (6400.0, 100.0, 200.0))): # past, receding
        assert plane_crossing(a, b, 6230.0) is None, (a, b)
    # A segment ENDING exactly on the plane still crosses it.
    assert plane_crossing((6000.0, 0.0, 0.0), (6230.0, 0.0, 0.0), 6230.0) is not None
    y, z, frac = plane_crossing((6000.0, 100.0, 200.0), (6400.0, 300.0, 400.0), 6230.0)
    assert frac == pytest.approx(0.575)
    assert y == pytest.approx(215.0)
    assert z == pytest.approx(315.0)
