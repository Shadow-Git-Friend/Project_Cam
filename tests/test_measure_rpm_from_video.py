"""Tests for the phone-video RPM measurement.

This tool is the INDEPENDENT number that `fit_rpm_setpoint.py` refuses to run
without, so it has to be right before it is pointed at the rig — every test here
synthesises a clip whose true RPM is known by construction.

The refusals matter as much as the measurement. A wheel spinning past Nyquist
folds down to a lower rate that looks entirely plausible, and a slow-motion clip
whose container reports the playback rate scales every number by that ratio.
Both produce a confident wrong answer rather than an obvious failure.
"""

import importlib.util
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]

FRAME = 200
CENTRE = FRAME // 2
ORBIT_R = 60
DOT_R = 9
# A box the mark sweeps through once per revolution, at angle 0.
ROI = (CENTRE + ORBIT_R - 15, CENTRE - 15, 30, 30)


def load():
    spec = importlib.util.spec_from_file_location(
        "measure_rpm_from_video", ROOT / "scripts" / "measure_rpm_from_video.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vid():
    return load()


def synth(path: Path, rpm: float, fps: float, seconds: float,
          container_fps: float | None = None) -> Path:
    """A white mark orbiting a dark frame at exactly `rpm`."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                             container_fps or fps, (FRAME, FRAME))
    assert writer.isOpened()
    n = int(round(fps * seconds))
    for i in range(n):
        theta = 2 * math.pi * (rpm / 60.0) * (i / fps)
        frame = np.zeros((FRAME, FRAME, 3), dtype=np.uint8)
        x = int(round(CENTRE + ORBIT_R * math.cos(theta)))
        y = int(round(CENTRE + ORBIT_R * math.sin(theta)))
        cv2.circle(frame, (x, y), DOT_R, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()
    return path


def test_it_recovers_a_known_rpm(vid, tmp_path):
    """The plateau the rig actually produced, filmed at a phone slow-mo rate."""
    clip = synth(tmp_path / "a.mp4", rpm=370.0, fps=240.0, seconds=3.0)
    r = vid.measure(clip, roi=ROI)
    assert r["ok"], r["refusals"]
    assert abs(r["rpm"] - 370.0) / 370.0 < 0.02
    assert abs(r["rpm_peak_count"] - 370.0) / 370.0 < 0.05


@pytest.mark.parametrize("rpm", [250.0, 370.0, 555.0])
def test_it_tracks_across_the_ladder_range(vid, tmp_path, rpm):
    clip = synth(tmp_path / f"l{int(rpm)}.mp4", rpm=rpm, fps=240.0, seconds=3.0)
    r = vid.measure(clip, roi=ROI)
    assert r["ok"], r["refusals"]
    assert abs(r["rpm"] - rpm) / rpm < 0.02


def test_without_an_roi_it_fails_loudly_instead_of_guessing(vid, tmp_path):
    """A mark that stays in frame does not change TOTAL brightness — it only
    moves. So whole-frame analysis has no signal at all, and the honest answer
    is an error naming the fix, not a number derived from compression noise."""
    clip = synth(tmp_path / "b.mp4", rpm=370.0, fps=240.0, seconds=3.0)
    with pytest.raises(vid.VideoError, match="--roi"):
        vid.measure(clip, roi=None)


def test_the_spectrum_top_bin_is_a_harmonic_and_is_not_used(vid, tmp_path):
    """The bug the synthetic clips caught before the rig did.

    A mark sweeping a small box is a narrow pulse once per revolution, so the
    harmonics are strong; and a fundamental falling between two FFT bins splits
    its energy across both while a harmonic landing on a bin keeps all of its
    own. At 370 RPM the strongest bin was the SECOND harmonic, 740 RPM. Taking
    the spectrum's argmax would have doubled every true-RPM reading and the
    refit would have looked perfectly self-consistent.
    """
    clip = synth(tmp_path / "harm.mp4", rpm=370.0, fps=240.0, seconds=3.0)
    r = vid.measure(clip, roi=ROI)
    assert abs(r["rpm"] - 370.0) / 370.0 < 0.02
    top = r["spectrum"]["peaks"][0]["rpm"]
    assert abs(top - 740.0) < 20.0, f"expected the 2nd harmonic on top, got {top}"


def test_an_aliased_clip_is_convincing_and_wrong_on_its_own(vid, tmp_path):
    """The limitation, pinned so nobody trusts the output without a precondition.

    1500 RPM is 25 Hz; at 30 fps it folds to 5 Hz and the tool reports ~300 RPM
    with a repeat strength around 0.95. Every internal quality signal looks
    excellent. Folding pushes the apparent rate DOWN, so "comfortably below
    Nyquist" is precisely what a badly aliased clip looks like and testing that
    would prove nothing. All the tool can do alone is say it does not know.
    """
    clip = synth(tmp_path / "c.mp4", rpm=1500.0, fps=30.0, seconds=4.0)
    r = vid.measure(clip, roi=ROI)
    assert abs(r["rpm"] - 300.0) < 20.0, "expected the alias, not the truth"
    assert r["autocorrelation_strength"] > 0.8, "and it looks convincing"
    assert any("aliasing cannot be ruled out" in w for w in r["warnings"])


def test_the_expected_rpm_turns_aliasing_into_a_precondition(vid, tmp_path):
    """Given the firmware's own reading, the frame rate can be judged BEFORE
    the answer is believed — which is the only thing that actually works."""
    clip = synth(tmp_path / "c2.mp4", rpm=1500.0, fps=30.0, seconds=4.0)
    r = vid.measure(clip, roi=ROI, expect_rpm=1500.0)
    assert not r["ok"]
    assert any("frames per revolution" in x for x in r["refusals"])


def test_a_measurement_far_from_the_expectation_is_refused(vid, tmp_path):
    """Fast enough to sample, but nothing like the firmware's number: that is a
    sign of a wrong fps or an alias, not of a 23% calibration error."""
    clip = synth(tmp_path / "c3.mp4", rpm=370.0, fps=240.0, seconds=3.0)
    assert vid.measure(clip, roi=ROI, expect_rpm=370.0)["ok"]
    r = vid.measure(clip, roi=ROI, expect_rpm=1200.0)
    assert not r["ok"]
    assert any("too far apart" in x for x in r["refusals"])


def test_too_few_revolutions_is_refused(vid, tmp_path):
    clip = synth(tmp_path / "d.mp4", rpm=60.0, fps=240.0, seconds=2.0)  # 2 revs
    r = vid.measure(clip, roi=ROI)
    assert not r["ok"]
    assert any("revolutions in view" in x for x in r["refusals"])


def test_a_slow_motion_container_rate_is_flagged(vid, tmp_path):
    """Filmed at 240 but stored claiming 30: every number is 8x wrong and the
    tool must say so rather than report a confident 46 RPM."""
    clip = synth(tmp_path / "e.mp4", rpm=370.0, fps=240.0, seconds=3.0,
                 container_fps=30.0)
    r = vid.measure(clip, roi=ROI)
    assert any("PLAYBACK rate" in w for w in r["warnings"])
    # And overriding fps recovers the truth from the same file.
    fixed = vid.measure(clip, roi=ROI, fps_override=240.0)
    assert abs(fixed["rpm"] - 370.0) / 370.0 < 0.02


def test_fps_scales_every_number_linearly(vid, tmp_path):
    clip = synth(tmp_path / "f.mp4", rpm=370.0, fps=240.0, seconds=3.0)
    a = vid.measure(clip, roi=ROI, fps_override=240.0)
    b = vid.measure(clip, roi=ROI, fps_override=120.0)
    assert abs(a["rpm"] / b["rpm"] - 2.0) < 0.01


def test_a_flat_clip_is_an_error_not_a_zero(vid, tmp_path):
    path = tmp_path / "g.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 240.0,
                             (FRAME, FRAME))
    for _ in range(240):
        writer.write(np.zeros((FRAME, FRAME, 3), dtype=np.uint8))
    writer.release()
    with pytest.raises(vid.VideoError, match="not a mark"):
        vid.measure(path, roi=ROI)


def test_an_roi_outside_the_frame_is_an_error(vid, tmp_path):
    clip = synth(tmp_path / "h.mp4", rpm=370.0, fps=240.0, seconds=1.0)
    with pytest.raises(vid.VideoError, match="outside the"):
        vid.measure(clip, roi=(9000, 9000, 30, 30))


def test_a_missing_file_is_an_error(vid, tmp_path):
    with pytest.raises(vid.VideoError, match="cannot open"):
        vid.measure(tmp_path / "nope.mp4", roi=ROI)


def test_the_cli_reports_and_sets_exit_status(vid, tmp_path, capsys):
    clip = synth(tmp_path / "i.mp4", rpm=370.0, fps=240.0, seconds=3.0)
    out = tmp_path / "out.json"
    assert vid.main([str(clip), "--roi", "{},{},{},{}".format(*ROI),
                     "--fps", "240", "--expect-rpm", "370",
                     "--json-out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "RPM" in printed and "USABLE" in printed

    bad = synth(tmp_path / "j.mp4", rpm=1500.0, fps=30.0, seconds=4.0)
    assert vid.main([str(bad), "--roi", "{},{},{},{}".format(*ROI),
                     "--expect-rpm", "1500"]) == 1
