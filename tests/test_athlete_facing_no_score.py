"""The synthetic 0-100 balance score must not be shown to the athlete.

`score` is `100 - max(0, sway_rms_mm - 8.0) * 2.0` clamped to 0..100 — invented
constants with no validation behind them, presented on a big athlete-facing
board as if it were an assessment. It is the same composite rating the product
design explicitly rejects; it simply shipped before that decision.

Removing it from the display is deliberate and separate from the raw record:
`summary.avg_score` stays in the evidence for backward compatibility, but the
metric registry and every athlete-facing surface ignore it.
"""

import importlib.util
from pathlib import Path

import pytest

from project_cam.training.drills import DRILL_REGISTRY

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / "garage_lab_combined/scripts/training_drill.py"


def load_board():
    spec = importlib.util.spec_from_file_location("training_drill_board", BOARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finished_balance_drill():
    """A balance drill carrying two completed holds with real scores."""
    drill = DRILL_REGISTRY["balance"](holds=2, hold_s=1.0)
    drill.results = [
        {"hold": 1, "stance": "left", "sway_rms_mm": 31.0, "touchdowns": 1,
         "score": 54, "single_leg_pct": 92.0, "measured": True},
        {"hold": 2, "stance": "right", "sway_rms_mm": 18.0, "touchdowns": 0,
         "score": 80, "single_leg_pct": 97.0, "measured": True},
    ]
    return drill


# The drawer renders nothing in the default "idle" state, so a test that does
# not set a state passes vacuously. These are the states that actually paint
# hold results.
SCORING_STATES = ("countdown", "rest", "done")


def captured_board_strings(board, drill, state, monkeypatch):
    """Every string the balance drawer renders in one state."""
    drawn = []

    def spy(original):
        def wrapper(img, txt, *args, **kwargs):
            drawn.append(str(txt))
            return original(img, txt, *args, **kwargs)
        return wrapper

    for name in ("text", "text_c", "name_text"):
        if hasattr(board, name):
            monkeypatch.setattr(board, name, spy(getattr(board, name)))

    import numpy as np
    img = np.zeros((720, 1280, 3), dtype=np.uint8)

    class Args:
        width, height = 1280, 720

    drill.state = state
    board.DRAWERS["balance"](img, drill, 100.0, None, Args(), 1280, 720)
    return drawn


@pytest.mark.parametrize("state", SCORING_STATES)
def test_balance_board_never_prints_a_score(state, monkeypatch):
    board = load_board()
    drill = finished_balance_drill()
    drawn = captured_board_strings(board, drill, state, monkeypatch)

    assert drawn, f"state {state!r} rendered nothing - test would pass vacuously"
    offenders = [s for s in drawn if "score" in s.lower()]
    assert not offenders, f"athlete-facing board still shows a score: {offenders}"


@pytest.mark.parametrize("state", SCORING_STATES)
def test_balance_board_still_shows_the_measured_facts(state, monkeypatch):
    """Removing the composite must not remove the real measurements with it."""
    board = load_board()
    drill = finished_balance_drill()
    drawn = " | ".join(captured_board_strings(board, drill, state, monkeypatch))

    assert "sway" in drawn.lower()
    assert "31" in drawn or "18" in drawn


def test_hold_event_line_has_no_score():
    board = load_board()
    drill = DRILL_REGISTRY["balance"](holds=2)
    event = {"event": "hold", "hold": 1, "stance": "left",
             "sway_rms_mm": 31.0, "touchdowns": 1, "score": 54}
    line = board.event_line(drill, event)

    assert "score" not in line.lower(), line
    assert "31 mm" in line          # the measurement survives
    assert "touch-down" in line


def test_headline_was_already_score_free():
    """Regression guard: the headline is the one surface that never carried it,
    and it feeds the desktop SESSIONS list."""
    drill = finished_balance_drill()
    assert "score" not in drill.headline().lower()


def test_raw_summary_keeps_avg_score_for_backward_compatibility():
    """Only the DISPLAY is removed. Deleting the field would break readers of
    already-written sessions; the registry simply never maps it."""
    drill = finished_balance_drill()
    assert "avg_score" in drill.summary()
