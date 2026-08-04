"""Unit tests for the Reaction Arena game logic (no display / no UDP)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "reaction_arena", Path(__file__).resolve().parent.parent / "scripts" / "reaction_arena.py")
ra = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ra)


def test_zone_of_basic():
    assert ra.zone_of(0, 3000) == 0
    assert ra.zone_of(1500, 3000) == 1
    assert ra.zone_of(2999, 3000) == 2
    # clamps out-of-range
    assert ra.zone_of(-100, 3000) == 0
    assert ra.zone_of(9999, 3000) == 2


def test_zone_of_flip():
    assert ra.zone_of(0, 3000, flip=True) == 2
    assert ra.zone_of(2999, 3000, flip=True) == 0
    assert ra.zone_of(1500, 3000, flip=True) == 1


def test_full_round_hit():
    g = ra.ReactionGame(rounds=3, countdown_s=2.0, timeout_s=3.0, result_s=1.4, seed=0)
    g.start(0.0)
    assert g.state == "countdown" and g.round == 1
    target = g.target
    g.update(1.0, None)
    assert g.state == "countdown"          # still counting down
    g.update(2.0, None)
    assert g.state == "active" and g.go_time == 2.0
    g.update(2.3, target)                  # player steps into the target zone
    assert g.state == "result"
    assert g.score == 1
    assert g.last_result[0] == "hit"
    assert abs(g.last_result[1] - 0.3) < 1e-6
    g.update(2.0 + 1.4 + 0.4, None)        # result window elapses -> next round
    assert g.round == 2


def test_round_miss_on_timeout():
    g = ra.ReactionGame(rounds=3, countdown_s=1.0, timeout_s=2.0, seed=1)
    g.start(0.0)
    target = g.target
    wrong = (target + 1) % 3
    g.update(1.0, None)                     # -> active, go_time=1.0
    assert g.state == "active"
    g.update(3.1, wrong)                    # 2.1s in wrong zone > timeout -> miss
    assert g.state == "result" and g.last_result == ("miss", None)
    assert g.score == 0


def test_game_completes():
    g = ra.ReactionGame(rounds=1, countdown_s=0.5, timeout_s=1.0, result_s=0.5, seed=2)
    g.start(0.0)
    t = g.target
    g.update(0.5, None)                     # active
    g.update(0.6, t)                        # hit -> result
    g.update(1.2, None)                     # result elapses -> begin round 2 > rounds -> done
    assert g.state == "done"
    assert g.score == 1
