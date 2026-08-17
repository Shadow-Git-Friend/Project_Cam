#!/usr/bin/env python3
"""Refit the firmware's RPM -> PWM setpoint map, and check the encoder scale.

Why this exists
---------------
The commanded RPM is not delivered, and the two wheels do not agree with each
other. Video-verified 2026-08-17 on IMG_2536, both wheels filmed at one plateau:
a 400 command delivers a true L=395.5 / R=511.6. The LEFT wheel is within 1.1%
of its command; the RIGHT is 28% over it, and 29% over the left. So a 500
command settles outside `blm_bridge`'s +/-10% arm band, which refuses to arm and
blocks the whole B1 speed calibration. The band is right; the map is wrong.

Two earlier figures for the same fault are superseded but worth keeping straight,
because each was wrong in an instructive way. "23% high" (2026-08-13, L=368 /
R=372) was read 20 s in while the wheels were still climbing -- a plateau needs
~30 s. "31% high" (2026-08-14, a 300 command giving L=392 / R=402) was settled,
but it puts the two wheels 2.5% apart where video later measured 29%; one of
those two sessions is not describing the machine that is on the bench now.
Resolve that before believing any single ladder.

Two things are being solved at once, and the ORDER matters:

1. **Encoder scale.** The firmware's reported RPM is `counts / PPR * 60000/dt`
   with `PPR_LEFT = 1000` and `PPR_RIGHT = 2000` -- a factor of two apart. If
   either constant is wrong the reported RPM is a fiction, and refitting the
   map against a fiction makes command, report and model all agree while all
   being wrong. So an INDEPENDENT true RPM (optical tachometer on reflective
   tape) is required, and this tool refuses to emit new constants if the
   reported/true ratio is not close to 1.
2. **Setpoint map.** The firmware computes `PWM = rpm * SLOPE + OFFSET`. Each
   ladder step gives an exact PWM (the command is known) and a measured true
   RPM, so regressing PWM on true RPM inverts the relation directly.

This tool does NOT touch ball exit speed. v(RPM) stays a separate model, fitted
by `fit_rpm_speed.py` and indexed on MEASURED RPM at the shot, because no
open-loop map can know that the ball is loading the wheels.

Usage
-----
    fit_rpm_setpoint.py ladder.json [--firmware control_14_full.ino]

`ladder.json` is a list of steps recorded through `blm_bridge`:

    [{"commanded_rpm": 250, "reported_left": 310, "reported_right": 305,
      "true_left": 308, "true_right": 306}, ...]

`true_*` are the independent readings (`measure_rpm_from_video.py`). Omit them
and the tool reports the map it WOULD fit and refuses to emit constants. Record
a step the wheel did not turn for as `0`, not by leaving it out: the tool drops
it from the regression and reports it, because it locates the bottom of the
usable band.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

# A reported/true ratio outside this band means the PPR constant is wrong, not
# that the tachometer is noisy. Refitting through it would bake the error in.
SCALE_TOLERANCE = 0.05
MIN_STEPS = 3

_NUM = r"[-+]?\d*\.?\d+"


class LadderError(Exception):
    """The ladder cannot support the conclusion being asked of it."""


def read_firmware_constants(path: Path) -> dict:
    """Take the map constants from the sketch, never from a copy in here.

    Including MIN_RPM_THRESHOLD: below it `updateMotorPWM()` forces PWM to 1000,
    so a ladder step under it carries no information about the slope and must
    not be regressed as though it did.
    """
    source = path.read_text(encoding="utf-8")
    out = {}
    for side in ("LEFT", "RIGHT"):
        slope = re.search(rf"{side}_SLOPE\s*=\s*({_NUM});", source)
        offset = re.search(rf"{side}_OFFSET\s*=\s*({_NUM});", source)
        if not slope or not offset:
            raise LadderError(f"{side}_SLOPE/{side}_OFFSET not found in {path}")
        out[side.lower()] = (float(slope.group(1)), float(offset.group(1)))
    threshold = re.search(rf"MIN_RPM_THRESHOLD\s*=\s*({_NUM});", source)
    if not threshold:
        raise LadderError(f"MIN_RPM_THRESHOLD not found in {path}")
    out["min_rpm_threshold"] = float(threshold.group(1))
    return out


def commanded_pwm(rpm: float, slope: float, offset: float,
                  min_rpm_threshold: float) -> int:
    """Reproduce `updateMotorPWM()` exactly, clamp included."""
    if rpm < min_rpm_threshold:
        return 1000
    return max(1000, min(1800, int(rpm * slope + offset)))


def least_squares(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Return (slope, intercept, r_squared) for y = slope*x + intercept."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise LadderError("every ladder step used the same RPM; the slope is "
                          "undetermined")
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return slope, intercept, r2


def encoder_scale(steps: list[dict], side: str) -> Optional[dict]:
    """reported/true per step. None when the tachometer column is absent."""
    pairs = [(s[f"reported_{side}"], s[f"true_{side}"])
             for s in steps
             if s.get(f"true_{side}") is not None and s[f"true_{side}"] > 0]
    if not pairs:
        return None
    ratios = [r / t for r, t in pairs]
    mean = sum(ratios) / len(ratios)
    return {"n": len(ratios), "mean_ratio": mean,
            "min_ratio": min(ratios), "max_ratio": max(ratios),
            "within_tolerance": abs(mean - 1.0) <= SCALE_TOLERANCE,
            "suggests_ppr_factor": round(mean, 3)}


def fit(steps: list[dict], constants: dict) -> dict:
    if len(steps) < MIN_STEPS:
        raise LadderError(
            f"{len(steps)} ladder steps, need at least {MIN_STEPS} to fit a line")

    threshold = constants["min_rpm_threshold"]
    result = {"n_steps": len(steps), "sides": {}}
    for side in ("left", "right"):
        slope_old, offset_old = constants[side]
        pwms, trues, not_spinning = [], [], []
        for s in steps:
            true = s.get(f"true_{side}")
            # A step below the firmware threshold produces PWM 1000 whatever the
            # command was, so it says nothing about the slope. Regressing it
            # would drag the fit toward a point the map does not control.
            if true is None or s["commanded_rpm"] < threshold:
                continue
            # Nor does a step the ESC never started. A 250 command clears
            # MIN_RPM_THRESHOLD but maps to PWM 1145/1129, under the ESCs' start
            # threshold, and on 2026-08-14 both wheels sat still for 30 s while
            # the firmware accepted it. Regressed as (0 RPM, that PWM) it pulled
            # the left slope from 0.2326 to 0.0598, which maps a 400 command
            # back below the start threshold -- a refit that stops the machine.
            if float(true) <= 0:
                not_spinning.append(s["commanded_rpm"])
                continue
            pwms.append(commanded_pwm(s["commanded_rpm"], slope_old, offset_old,
                                      threshold))
            trues.append(float(true))

        scale = encoder_scale(steps, side)
        entry = {"old_slope": slope_old, "old_offset": offset_old,
                 "encoder_scale": scale, "n_points": len(trues),
                 "not_spinning": not_spinning}

        if scale is None:
            entry["refused"] = ("no tachometer readings for this wheel; the "
                                "firmware's own RPM cannot validate itself")
        elif not scale["within_tolerance"]:
            entry["refused"] = (
                f"reported/true is {scale['mean_ratio']:.3f}, outside "
                f"1 +/-{SCALE_TOLERANCE}. Fix PPR_{side.upper()} first — "
                f"refitting through this would hide the error, not remove it")
        elif len(trues) < MIN_STEPS:
            entry["refused"] = (f"{len(trues)} usable points, need {MIN_STEPS}")
        else:
            slope_new, offset_new, r2 = least_squares(trues, pwms)
            entry.update({"new_slope": round(slope_new, 4),
                          "new_offset": int(round(offset_new)),
                          "r_squared": round(r2, 5)})
            if r2 < 0.98:
                entry["warning"] = (
                    f"r^2 = {r2:.3f}: PWM and RPM are not linear over this "
                    f"range, so a straight line is the wrong model here")
        result["sides"][side] = entry
    return result


def report(result: dict) -> None:
    print(f"ladder steps: {result['n_steps']}\n")
    for side, e in result["sides"].items():
        print(f"--- {side.upper()} ---")
        print(f"  current firmware: SLOPE={e['old_slope']} OFFSET={e['old_offset']:.0f}")
        scale = e["encoder_scale"]
        if scale is None:
            print("  encoder scale:    NOT CHECKED (no tachometer readings)")
        else:
            verdict = "OK" if scale["within_tolerance"] else "SUSPECT"
            print(f"  encoder scale:    reported/true = {scale['mean_ratio']:.3f} "
                  f"[{scale['min_ratio']:.3f}..{scale['max_ratio']:.3f}] "
                  f"n={scale['n']}  {verdict}")
        if e["not_spinning"]:
            commands = ", ".join(f"{c:g}" for c in e["not_spinning"])
            print(f"  did not spin:     {commands} — dropped from the fit. The "
                  f"usable band starts above the highest of these")
        if "refused" in e:
            print(f"  NO CONSTANTS:     {e['refused']}")
        else:
            print(f"  refit:            SLOPE={e['new_slope']} "
                  f"OFFSET={e['new_offset']}  (r^2={e['r_squared']})")
            if "warning" in e:
                print(f"  WARNING:          {e['warning']}")
        print()

    emitted = [s for s, e in result["sides"].items() if "refused" not in e]
    if len(emitted) == 2:
        left, right = result["sides"]["left"], result["sides"]["right"]
        print("Apply to control_14_full.ino, then ship as control_15:")
        print(f"  const float LEFT_SLOPE   = {left['new_slope']};")
        print(f"  const int   LEFT_OFFSET  = {left['new_offset']};")
        print(f"  const float RIGHT_SLOPE  = {right['new_slope']};")
        print(f"  const int   RIGHT_OFFSET = {right['new_offset']};")
        print("\nThen re-run the ladder to confirm commanded ~= measured inside "
              "blm_bridge's +/-10% arm band, BEFORE any B1 shot.")
    else:
        print("No constants emitted. Resolve the refusals above first.")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ladder", type=Path, help="JSON list of ladder steps")
    ap.add_argument("--firmware", type=Path, default=Path("control_14_full.ino"))
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)

    try:
        steps = json.loads(args.ladder.read_text(encoding="utf-8"))
        constants = read_firmware_constants(args.firmware)
        result = fit(steps, constants)
    except LadderError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    report(result)
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
