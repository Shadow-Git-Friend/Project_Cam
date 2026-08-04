"""Desktop window placement for the tiled training layout (display-only).

`place_window` is tested against a fake window manager rather than a real
display: the two failure modes that actually bit us — decoration offset and
Qt's asynchronous first layout — are both about what the WM reports back, so a
simulated WM reproduces them deterministically and headless.
"""

from __future__ import annotations

import sys

import pytest

from project_cam.viz.window import (
    MAX_CORRECTION_PX,
    PANES,
    pane_rect,
    parse_workarea,
    place_window,
    screen_workarea,
)

# The real measured work area on the rig: a 1920x1080 screen minus the GNOME
# dock (70 px left) and top panel (27 px).
RIG = (70, 27, 1850, 1053)


def test_parse_workarea_accepts_commas_spaces_and_rejects_junk():
    assert parse_workarea("70, 27, 1850, 1053") == RIG
    assert parse_workarea("70 27 1850 1053") == RIG
    assert parse_workarea("0,0,1920,1080,0,0,1920,1080") == (0, 0, 1920, 1080)
    for bad in (None, "", "1920x1080", "1,2,3", "a,b,c,d", "0,0,0,600", "0,0,800,-1"):
        assert parse_workarea(bad) is None, bad


def test_screen_workarea_honours_the_environment_override(monkeypatch):
    monkeypatch.setenv("PROJECT_CAM_WORKAREA", "100,50,1000,600")
    assert screen_workarea() == (100, 50, 1000, 600)
    # Unparseable override falls through to detection rather than crashing.
    monkeypatch.setenv("PROJECT_CAM_WORKAREA", "nonsense")
    rect = screen_workarea(default=(1, 2, 3, 4))
    assert len(rect) == 4 and rect[2] > 0 and rect[3] > 0


def test_panes_split_the_work_area_without_overlapping():
    left = pane_rect("left", workarea=RIG)
    right = pane_rect("right", workarea=RIG)
    # Both panes must fit inside the work area...
    for rect in (left, right):
        assert rect[0] >= RIG[0]
        assert rect[1] >= RIG[1]
        assert rect[0] + rect[2] <= RIG[0] + RIG[2]
        assert rect[1] + rect[3] <= RIG[1] + RIG[3]
    # ...and must not overlap. Advancing by the CONTENT width instead of the
    # pane's share would put the right window on top of the left one, which is
    # exactly the overlap the operator is currently fixing by hand.
    assert left[0] + left[2] <= right[0]
    assert left[1] == right[1] and left[2] == right[2] and left[3] == right[3]


@pytest.mark.parametrize(
    "area",
    [
        RIG,                  # width-bound: the 16:9 pane fills its half
        (0, 0, 2000, 300),    # height-bound: the pane is narrower than its half
    ],
)
def test_each_pane_stays_inside_its_own_half(area):
    """Panes are indexed by their SHARE of the work area, not by content width.

    On a width-bound desktop the two are equal, which hides the difference — so
    the height-bound case is the one that actually pins it: stepping by content
    width leaves the 'right' window sitting in the left half.
    """
    mid = area[0] + area[2] / 2
    left = pane_rect("left", workarea=area)
    right = pane_rect("right", workarea=area)
    assert left[0] + left[2] <= mid + 1, (left, mid)
    assert right[0] >= mid - 1, (right, mid)


def test_pane_defaults_to_the_detected_work_area(monkeypatch):
    """Callers pass only a pane name, so the default must be the live work area
    — a hardcoded screen size would misplace every non-1920x1080 desktop."""
    monkeypatch.setenv("PROJECT_CAM_WORKAREA", "100,50,1200,700")
    assert pane_rect("left") == pane_rect("left", workarea=(100, 50, 1200, 700))
    assert pane_rect("left")[0] == 100


def test_panes_start_at_the_work_area_not_the_screen_origin():
    """The dock offset is the reason this module exists.

    A pane computed from the raw 1920x1080 screen starts at x=0, the window
    manager shifts it clear of the dock, and the two halves then overlap by the
    dock width.
    """
    assert pane_rect("left", workarea=RIG)[0] == RIG[0] == 70
    assert pane_rect("left", workarea=(0, 0, 1920, 1080))[0] == 0


@pytest.mark.parametrize("aspect", [16 / 9, 4 / 3, 960 / 540, 1.0])
def test_pane_keeps_the_content_aspect_so_nothing_is_letterboxed(aspect):
    x, y, w, h = pane_rect("left", aspect=aspect, workarea=RIG)
    assert w / h == pytest.approx(aspect, rel=0.01)
    assert w <= RIG[2] // 2 and h <= RIG[3]


def test_pane_is_height_bound_on_a_short_work_area():
    """A wide, short work area must fit by height, not overflow it."""
    area = (0, 0, 1000, 200)
    x, y, w, h = pane_rect("left", aspect=16 / 9, workarea=area)
    assert h <= 200 and w <= 500
    assert w / h == pytest.approx(16 / 9, rel=0.01)


def test_none_means_leave_the_window_alone_and_unknown_panes_raise():
    assert pane_rect("none", workarea=RIG) is None
    assert pane_rect(None, workarea=RIG) is None
    assert pane_rect("full", workarea=RIG) is not None
    assert set(PANES) == {"none", "left", "right", "full"}
    with pytest.raises(ValueError):
        pane_rect("diagonal", workarea=RIG)


class FakeWindowManager:
    """Minimal stand-in for the cv2 GUI backend plus a window manager.

    * ``deco`` — the title bar pushes the IMAGE below the frame origin we ask
      for, so the naive single move lands the content too low.
    * ``chrome`` — with a toolbar present, ``resizeWindow`` sizes the frame and
      the image comes out smaller than requested.
    * ``unrealised_reads`` — Qt lays out asynchronously, so the first reads
      report a 0-sized image rect.
    """

    error = RuntimeError

    def __init__(self, deco=(0, 37), chrome=(0, 0), unrealised_reads=1):
        self.deco = deco
        self.chrome = chrome
        self.unrealised = unrealised_reads
        self.pos = (0, 0)
        self.size = (400, 250)
        self.calls = []
        self.requested = []

    # cv2 API surface used by place_window
    def resizeWindow(self, name, w, h):
        self.calls.append("resize")
        self.size = (w, h)

    def moveWindow(self, name, x, y):
        self.calls.append("move")
        self.requested.append((x, y))
        self.pos = (x, y)

    def getWindowImageRect(self, name):
        self.calls.append("read")
        if self.unrealised > 0:
            self.unrealised -= 1
            return (0, 0, 0, 0)
        return (
            self.pos[0] + self.deco[0],
            self.pos[1] + self.deco[1],
            self.size[0] - self.chrome[0],
            self.size[1] - self.chrome[1],
        )

    def waitKey(self, delay):
        self.calls.append("pump")
        return -1


def _place(monkeypatch, wm, rect=(995, 293, 925, 520)):
    monkeypatch.setitem(sys.modules, "cv2", wm)
    place_window("win", rect, pump=wm.waitKey)
    return wm.getWindowImageRect("win")


def test_placement_corrects_the_title_bar_offset(monkeypatch):
    wm = FakeWindowManager(deco=(0, 37), unrealised_reads=0)
    assert _place(monkeypatch, wm) == (995, 293, 925, 520)


def test_placement_survives_qt_laying_out_late(monkeypatch):
    """The bug this replaced: giving up on the first 0-sized readback left a
    stub window in the corner, which is what the 3D arena did when it placed
    itself in the same tick as its first imshow."""
    wm = FakeWindowManager(deco=(0, 37), unrealised_reads=3)
    assert _place(monkeypatch, wm) == (995, 293, 925, 520)


def test_placement_pumps_the_event_loop_before_sizing_the_window(monkeypatch):
    """Sizing a window in the same tick as its first imshow is overridden by
    Qt's own layout, so the pump has to come first, not just between passes."""
    wm = FakeWindowManager(unrealised_reads=0)
    _place(monkeypatch, wm)
    assert wm.calls[0] == "pump", wm.calls[:4]


def test_placement_compensates_window_chrome_eating_the_image(monkeypatch):
    wm = FakeWindowManager(deco=(0, 37), chrome=(0, 46), unrealised_reads=0)
    assert _place(monkeypatch, wm) == (995, 293, 925, 520)


def test_placement_settles_instead_of_walking_off_a_clamped_edge(monkeypatch):
    """A WM that refuses the position (reserved edge, snapped tile) must not be
    chased forever — the correction is capped and the call still returns."""

    class Stubborn(FakeWindowManager):
        def moveWindow(self, name, x, y):
            super().moveWindow(name, x, y)
            self.pos = (600, 600)  # the WM ignores every request

    wm = Stubborn(unrealised_reads=0)
    monkeypatch.setitem(sys.modules, "cv2", wm)
    place_window("win", (995, 293, 925, 520), pump=wm.waitKey)
    assert wm.size == (925, 520)  # size still honoured
    # Every attempted position stays within one correction of the target: an
    # uncapped loop drifts by the same error every pass and ends up asking for
    # a coordinate far off screen.
    assert wm.requested, "the position must still be attempted"
    for x, y in wm.requested:
        assert abs(x - 995) <= MAX_CORRECTION_PX, wm.requested
        assert abs(y - 293) <= MAX_CORRECTION_PX, wm.requested


def test_placement_is_a_noop_without_a_rect():
    """`--window-pane none` and the fullscreen path both pass None; that must
    not even import cv2, let alone raise."""
    place_window("no-such-window", None)
    place_window("no-such-window", None, pump=lambda _ms: None)


def test_placement_never_raises_when_the_backend_errors(monkeypatch):
    class Broken(FakeWindowManager):
        def resizeWindow(self, name, w, h):
            raise self.error("no window")

    wm = Broken()
    monkeypatch.setitem(sys.modules, "cv2", wm)
    place_window("win", (0, 0, 100, 100), pump=wm.waitKey)
