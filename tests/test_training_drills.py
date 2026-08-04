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
    protocol_parameters_fingerprint,
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
        "gk_save", "gk_updown",
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
