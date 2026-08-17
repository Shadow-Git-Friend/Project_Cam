#!/usr/bin/env python3
"""Measure true wheel RPM from a phone video, independently of the encoder.

Why this exists
---------------
The firmware reports RPM as `counts / PPR * 60000/dt`, with `PPR_LEFT = 1000`
and `PPR_RIGHT = 2000` — a factor of two apart. Both wheels reporting ~370 at
one plateau is consistent with that pair being right, but a COMMON error in
both is invisible in that comparison. `scripts/fit_rpm_setpoint.py` therefore
refuses to refit the setpoint map without an independent true RPM, because
fitting against the firmware's own number would make command, report and model
agree while all three were wrong.

This is that independent number, using a phone instead of a tachometer.

Method
------
Stick ONE high-contrast mark on the tyre, hold the phone still, film the wheel
at a steady plateau. Mean brightness inside a small fixed box rises once per
revolution as the mark sweeps through it, giving a 1-D periodic signal. Two
estimates come from that signal and are reported separately, never averaged:

  A. Autocorrelation — the answer. A period is a period whatever the pulse
     shape, so unlike a spectral peak it cannot be captured by a harmonic.
     Parabolic interpolation gives sub-frame precision.
  B. Mean crossings — a crude count that fails differently, so agreement is
     evidence and disagreement means the clip cannot say which is right.

The spectrum is printed for diagnosis only. Its strongest bin is routinely a
HARMONIC: a narrow pulse train has strong harmonics, and a fundamental falling
between two bins splits its energy across both while a harmonic landing on a
bin keeps all of its own. On a synthetic 370 RPM clip the top bin was 740.

Traps this checks for you
-------------------------
* **Aliasing, which CANNOT be detected from the clip.** A wheel past fps/2
  folds down to a *lower* apparent rate: 1500 RPM filmed at 30 fps reports
  300 RPM with 0.95 repeat strength — confident and wrong. Since folding pushes
  the answer DOWN, "measured rate is comfortably under Nyquist" is exactly what
  a badly aliased clip looks like, so testing that proves nothing. Pass
  `--expect-rpm` (the firmware's own reading, order of magnitude is enough) and
  the frame rate is checked as a PRECONDITION instead. The independent check is
  to re-film at a second frame rate: a true rate is unchanged, an alias moves.
* **Mains flicker.** LED and fluorescent light modulates at 100/120 Hz, which
  aliases into the band of interest at phone frame rates. The full peak list is
  printed so a suspicious neighbour is visible rather than silently chosen.
* **A wrong fps in the container.** Slow-motion clips are often stored at 30 fps
  with the true capture rate only in metadata. `--fps` overrides, and the tool
  prints what it used, because every number here scales linearly with it.

Usage
-----
    # 1. grab a frame and pick a box the mark sweeps through
    measure_rpm_from_video.py wheel.mp4 --dump-frame frame.png

    # 2. measure, passing the firmware's own reading so the frame rate is checked
    measure_rpm_from_video.py wheel.mp4 --roi 900,500,120,120 \
        --fps 240 --expect-rpm 370

`--roi` is effectively required: a mark that stays in frame changes only its
POSITION, not the total brightness, so whole-frame analysis has no signal.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

# Below this many revolutions the frequency resolution is too coarse to claim a
# percent-level number, which is what a setpoint refit needs.
MIN_REVOLUTIONS = 8
# Frames per revolution demanded of the EXPECTED rate. Nyquist alone (2x) leaves
# no margin, and the point is to stay far from the fold rather than near it.
MIN_FRAMES_PER_REV = 4.0
# Peak-to-peak brightness swing, relative to the mean, below which the "signal"
# is compression noise rather than a mark.
MIN_MODULATION = 0.05
# The two independent estimates must agree within this, or the clip is refused.
METHOD_AGREEMENT = 0.05
# How far the measurement may sit from the firmware's own reading before the
# most likely explanation is an alias rather than a calibration error.
EXPECTED_SANITY_FACTOR = 1.6
# A peak this tall relative to the global autocorrelation peak counts as a real
# repeat. The FIRST such peak is the period; see autocorrelation_hz.
FUNDAMENTAL_FRACTION = 0.75


class VideoError(Exception):
    """The clip cannot support the number being asked of it."""


def brightness_series(path: Path, roi: Optional[tuple[int, int, int, int]],
                      first_frame: int = 0, last_frame: Optional[int] = None,
                      ) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Mean ROI brightness per frame, optionally over a frame RANGE.

    The range exists for iPhone slow-motion, which exports at 30 fps with the
    ramp baked in: the head and tail play at real time and only the middle is
    slowed. Measuring the whole file mixes two time bases and the answer is
    neither one.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError(f"cannot open {path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    values = []
    index = -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        index += 1
        if index < first_frame:
            continue
        if last_frame is not None and index > last_frame:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if roi is not None:
            x, y, w, h = roi
            gray = gray[y:y + h, x:x + w]
            if gray.size == 0:
                raise VideoError(f"ROI {roi} is outside the {size[0]}x{size[1]} frame")
        values.append(float(gray.mean()))
    cap.release()
    if len(values) < 16:
        raise VideoError(f"only {len(values)} frames decoded; too short to measure")
    return np.asarray(values, dtype=np.float64), fps, size


def spectrum_peaks(signal: np.ndarray, fps: float, top: int = 5) -> dict:
    """The spectrum, for DIAGNOSIS only — never as the answer.

    Its strongest bin is not the rotation rate. A mark sweeping through a small
    box makes a narrow pulse once per revolution, and a narrow pulse train has
    strong harmonics; worse, a fundamental that falls between two bins splits
    its energy across both (scalloping) while a harmonic landing on a bin keeps
    all of its own. A synthetic 370 RPM clip reported its second harmonic at
    740 RPM as the strongest peak, with the true rate split across the two bins
    either side of it. That is exactly the confident wrong answer this tool
    exists to prevent, so the rate comes from autocorrelation and the spectrum
    is kept only to make mains flicker and aliases visible.
    """
    centred = signal - signal.mean()
    windowed = centred * np.hanning(len(centred))
    magnitude = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(len(windowed), d=1.0 / fps)
    magnitude[0] = 0.0                     # DC carries no rotation information
    if magnitude.max() <= 0:
        raise VideoError(
            "the signal is flat — no brightness changes at all. A mark that "
            "stays in frame the whole time does not change TOTAL brightness, "
            "so this needs --roi: a small fixed box the mark sweeps through")
    order = np.argsort(magnitude)[::-1][:top]
    peaks = [{"hz": round(float(freqs[i]), 4),
              "rpm": round(float(freqs[i]) * 60.0, 1),
              "relative_power": round(float(magnitude[i] / magnitude.max()), 3)}
             for i in order]
    return {"peaks": peaks, "resolution_hz": round(float(freqs[1]), 4)}


def autocorrelation_hz(signal: np.ndarray, fps: float,
                       min_hz: float = 0.5) -> tuple[float, float]:
    """Rotation rate from the FIRST strong autocorrelation peak, and its height.

    Not the tallest peak — the first one. Autocorrelation repeats at every
    multiple of the period, and a real wheel does not present an identical mark
    on every pass: wobble, lighting and exposure make alternate passes brighter,
    so the signal genuinely repeats every TWO revolutions and the peak at 2T can
    stand taller than the one at T. Taking the tallest then reports HALF the
    true rate.

    That is not hypothetical. On 2026-08-14 it read 194.5 RPM for a wheel really
    turning at ~390, and the halved number was built into a confident conclusion
    that an encoder constant was wrong and the two flywheels ran at a 2:1 ratio.
    Two better clips later showed the firmware had been right all along.

    Sub-sample precision by parabolic interpolation around the chosen peak.
    """
    x = signal - signal.mean()
    n = len(x)
    size = 1 << (2 * n - 1).bit_length()
    spec = np.fft.rfft(x, size)
    ac = np.fft.irfft(spec * np.conj(spec), size)[:n]
    if ac[0] <= 0:
        raise VideoError("the signal is flat; see --roi in the help")
    ac = ac / ac[0]

    min_lag = 2
    max_lag = min(n - 2, int(fps / min_hz))
    if max_lag <= min_lag:
        raise VideoError("the clip is too short to contain one full revolution")

    # A broad mark leaves a broad autocorrelation lobe at zero. Its descending
    # shoulder can be taller than every real repeat, so treating it as part of
    # the peak search turns pulse width into a fictitious 2--3 frame period.
    # The first valley separates that self-overlap from periodic recurrence.
    valley = 0
    while valley < max_lag - 1 and ac[valley + 1] <= ac[valley]:
        valley += 1

    search_start = max(min_lag, valley + 1)
    search = ac[search_start:max_lag + 1]
    threshold = FUNDAMENTAL_FRACTION * search.max()
    lag = None
    for candidate in range(search_start, max_lag + 1):
        if (ac[candidate] >= threshold
                and ac[candidate] >= ac[candidate - 1]
                and ac[candidate] >= ac[candidate + 1]):
            lag = candidate
            break
    if lag is None:
        # Nothing cleared the bar, so report the tallest lag as a raw integer and
        # let the caller reject it on strength. The parabola below only means
        # anything at a local maximum; on a slope, or at the window edge, it
        # extrapolates far outside the three samples it was fitted to.
        return fps / (int(np.argmax(search)) + search_start), 0.0

    y0, y1, y2 = ac[lag - 1], ac[lag], ac[lag + 1]
    denom = y0 - 2 * y1 + y2
    lag_refined = lag + (0.5 * (y0 - y2) / denom if denom < 0 else 0.0)
    return fps / lag_refined, float(ac[lag])


def count_revolutions(signal: np.ndarray) -> float:
    """Upward mean-crossings. A deliberately different failure mode from the FFT."""
    centred = signal - signal.mean()
    above = centred > 0
    return float(np.count_nonzero(~above[:-1] & above[1:]))


def measure(path: Path, roi=None, fps_override: Optional[float] = None,
            expect_rpm: Optional[float] = None, first_frame: int = 0,
            last_frame: Optional[int] = None) -> dict:
    signal, container_fps, size = brightness_series(path, roi, first_frame, last_frame)
    fps = fps_override or container_fps
    if not fps or fps <= 0:
        raise VideoError("no usable frame rate; pass --fps with the capture rate")

    modulation = float(signal.max() - signal.min()) / max(float(signal.mean()), 1e-9)
    if modulation < MIN_MODULATION:
        raise VideoError(
            f"brightness varies by only {modulation:.1%} of the mean, which is "
            f"compression noise, not a mark passing through. A mark that stays "
            f"in frame does not change TOTAL brightness — it only moves — so "
            f"this needs --roi: a small fixed box the mark sweeps through")

    duration = len(signal) / fps
    spectral = spectrum_peaks(signal, fps)
    hz, strength = autocorrelation_hz(signal, fps)
    rpm_auto = hz * 60.0
    rpm_count = count_revolutions(signal) / duration * 60.0 if duration > 0 else 0.0

    result = {
        "video": str(path), "frames": len(signal), "fps_used": fps,
        "fps_from_container": container_fps, "fps_overridden": fps_override is not None,
        "frame_size": f"{size[0]}x{size[1]}", "roi": roi, "duration_s": round(duration, 3),
        "first_frame": first_frame, "last_frame": last_frame,
        "rpm": round(rpm_auto, 1), "rpm_peak_count": round(rpm_count, 1),
        "autocorrelation_strength": round(strength, 3),
        "modulation": round(modulation, 3), "expect_rpm": expect_rpm,
        "revolutions_seen": round(hz * duration, 1),
        "spectrum": spectral, "refusals": [], "warnings": [],
    }

    revs = result["revolutions_seen"]
    if revs < MIN_REVOLUTIONS:
        result["refusals"].append(
            f"only {revs:.1f} revolutions in view (need {MIN_REVOLUTIONS}); "
            f"film for longer")

    # ALIASING IS NOT DETECTABLE FROM THE CLIP. Folding makes the apparent rate
    # LOWER, so a measured value comfortably under Nyquist is exactly what a
    # badly-aliased wheel looks like: 1500 RPM filmed at 30 fps reports 300 RPM
    # with 0.95 repeat strength. Checking the measured rate against Nyquist is
    # therefore worthless, and this used to do exactly that. The only real
    # defences are a PRECONDITION on the frame rate, and re-filming at a second
    # frame rate — a true rate is unchanged, an aliased one moves.
    if expect_rpm is None:
        result["warnings"].append(
            "no --expect-rpm given, so aliasing cannot be ruled out. Pass the "
            "firmware's own reading for this step; it need not be accurate, only "
            "the right order of magnitude")
    else:
        frames_per_rev = fps / max(expect_rpm / 60.0, 1e-9)
        if frames_per_rev < MIN_FRAMES_PER_REV:
            result["refusals"].append(
                f"a wheel near {expect_rpm:.0f} RPM gives only {frames_per_rev:.1f} "
                f"frames per revolution at {fps:.0f} fps (need "
                f"{MIN_FRAMES_PER_REV:.0f}). Anything at or past the fold reports a "
                f"confident WRONG answer, so re-film in slow motion")
        elif not (1 / EXPECTED_SANITY_FACTOR <= rpm_auto / max(expect_rpm, 1e-9)
                  <= EXPECTED_SANITY_FACTOR):
            result["refusals"].append(
                f"measured {rpm_auto:.0f} RPM against an expected ~{expect_rpm:.0f}: "
                f"too far apart to be a calibration error. Suspect aliasing or a "
                f"wrong fps, and re-film at a different frame rate to tell which")
    if strength < 0.3:
        result["refusals"].append(
            f"the signal repeats only weakly (autocorrelation {strength:.2f}); "
            f"the mark may be leaving the ROI, or the wheel is not at a steady "
            f"plateau")
    if rpm_auto > 0 and abs(rpm_count - rpm_auto) / rpm_auto > METHOD_AGREEMENT:
        result["refusals"].append(
            f"autocorrelation says {rpm_auto:.0f} RPM, crossing count says "
            f"{rpm_count:.0f} — over {METHOD_AGREEMENT:.0%} apart, so one of them "
            f"is wrong and this clip cannot say which")
    if fps_override is None and container_fps in (29.97, 30.0, 25.0):
        result["warnings"].append(
            f"container reports {container_fps} fps. Slow-motion clips often store "
            f"the PLAYBACK rate; if this was slow-mo, pass --fps with the true "
            f"capture rate or every number here is wrong by that ratio")
    result["ok"] = not result["refusals"]
    return result


def report(r: dict) -> None:
    print(f"{r['video']}  {r['frame_size']}  {r['frames']} frames  "
          f"{r['duration_s']} s @ {r['fps_used']} fps"
          + ("  (overridden)" if r["fps_overridden"] else ""))
    print(f"roi: {r['roi'] or 'whole frame'}\n")
    print(f"  RPM                {r['rpm']}   <- use this one")
    print(f"  RPM (crossings)    {r['rpm_peak_count']}   (independent cross-check)")
    print(f"  repeat strength    {r['autocorrelation_strength']}")
    print(f"  modulation         {r['modulation']:.1%} of mean brightness")
    print(f"  revolutions seen   {r['revolutions_seen']}")
    print("  spectrum (diagnostic only, its top bin is often a harmonic):")
    print("    " + ", ".join(f"{p['hz']}Hz={p['rpm']}rpm({p['relative_power']})"
                             for p in r["spectrum"]["peaks"]))
    for w in r["warnings"]:
        print(f"\n  WARNING: {w}")
    for f in r["refusals"]:
        print(f"\n  REFUSED: {f}")
    print(f"\n{'USABLE' if r['ok'] else 'NOT USABLE'} as a true-RPM reading.")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", type=Path)
    ap.add_argument("--roi", help="x,y,w,h of a small box the mark sweeps through")
    ap.add_argument("--fps", type=float, help="true capture rate for slow-motion clips")
    ap.add_argument("--expect-rpm", type=float,
                    help="the firmware's own reading for this step. Not treated as "
                         "truth — used only to prove the frame rate is high enough "
                         "that the answer cannot be an alias")
    ap.add_argument("--first-frame", type=int, default=0,
                    help="start of the SLOWED section of a ramped slow-motion clip")
    ap.add_argument("--last-frame", type=int,
                    help="end of the slowed section (inclusive)")
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--dump-frame", type=Path, help="write frame 0 as PNG to pick an ROI")
    args = ap.parse_args(argv)

    if args.dump_frame:
        cap = cv2.VideoCapture(str(args.video))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            print(f"error: cannot read a frame from {args.video}", file=sys.stderr)
            return 2
        cv2.imwrite(str(args.dump_frame), frame)
        print(f"wrote {args.dump_frame} ({frame.shape[1]}x{frame.shape[0]}) — "
              f"pick a box the mark passes through and pass it as --roi x,y,w,h")
        return 0

    roi = None
    if args.roi:
        try:
            parts = tuple(int(v) for v in args.roi.split(","))
        except ValueError:
            print("error: --roi must be four integers x,y,w,h", file=sys.stderr)
            return 2
        if len(parts) != 4:
            print("error: --roi must be four integers x,y,w,h", file=sys.stderr)
            return 2
        roi = parts

    try:
        result = measure(args.video, roi, args.fps, args.expect_rpm,
                         args.first_frame, args.last_frame)
    except VideoError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    report(result)
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
