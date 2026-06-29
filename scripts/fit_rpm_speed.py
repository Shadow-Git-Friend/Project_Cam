#!/usr/bin/env python3
"""Fit ball exit speed v(RPM) from horizontal-fire landing measurements.

The ballistic aim solver (launcher_common.solve_angles_ballistic) needs the
ball's exit speed. Until now it assumed a fixed 10 m/s, so shots land short/long
even when the aim direction is correct. This tool turns a handful of measured
shots into a v(RPM) model that the launcher then uses.

MEASUREMENT (per RPM, no fancy gear):
  1. Measure the barrel exit height H above the floor once (metres).
  2. Aim the BLM horizontal: `set 0 0 <rpm> <rpm>` then `reload` + `shoot`
     (use blm_interactive.py; the firmware enforces the >=400 RPM gate).
  3. Measure the horizontal distance d (metres) from the point directly BELOW
     the barrel to where the ball first hits the floor.
  4. Enter "<rpm> <d>" here. Exit speed (drag ignored): v = d * sqrt(g / (2H)).

This is self-consistent with the solver (which also ignores drag), so it is
accurate for targets near the calibration distances. Re-fit with more points
(or at the distances you actually shoot) to refine.

IMPORTANT (accuracy):
  * pitch 0 must be TRULY horizontal -- a mechanical tilt at "0" biases v. Check
    with a level / laser before measuring.
  * Do >=3 shots per RPM (5 at the RPM you actually use). Same ball, same power
    state. Enter every shot; same-RPM shots are averaged.
  * The model is clamped to the measured RPM range at aim time -- it will NOT
    extrapolate. Only shoot at RPMs you calibrated.
  * RECOMMENDED first pass: calibrate ONE RPM (e.g. 800) with 5 shots -> constant
    model -> verify on a non-human target, then add more RPMs if you need a curve.

Usage:
  ./venv/bin/python scripts/fit_rpm_speed.py \
      --out garage_lab_combined/cal/blm/rpm_speed_model.json
  # non-interactive: --height-m 0.5 --points "400:2.1,600:3.0,800:3.9"
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np


def speed_from_drop(distance_m: float, height_m: float, g: float) -> float:
    """Horizontal launch from height H, lands at horizontal distance d -> v."""
    if height_m <= 0 or distance_m <= 0:
        return 0.0
    t = math.sqrt(2.0 * height_m / g)
    return distance_m / t


def fit(points, g, height_m, kind):
    rpms = np.array([p[0] for p in points], dtype=float)
    vs = np.array([p[1] for p in points], dtype=float)
    out = {
        "model": "linear_rpm_to_mps",
        "g": g,
        "launch_height_m": height_m,
        "rpm_min": float(rpms.min()),
        "rpm_max": float(rpms.max()),
        "points": [{"rpm": float(r), "v_mps": float(v)} for r, v in zip(rpms, vs)],
    }
    # Single operating RPM (e.g. 5 shots at 800): a polynomial fit on identical
    # RPMs is singular -> store a constant speed (the averaged measurement).
    if len(np.unique(rpms)) == 1:
        out["model"] = "constant_mps"
        out["rpm"] = float(rpms[0])
        out["v_mps"] = float(vs.mean())
        out["fit_rmse_mps"] = float(vs.std())
        out["n_shots"] = int(len(vs))
        return out
    if kind == "interp" or len(points) < 2:
        out["model"] = "interp_rpm_to_mps"
        return out
    deg = 2 if (kind == "quadratic" and len(points) >= 3) else 1
    coeffs = np.polyfit(rpms, vs, deg).tolist()
    if deg == 1:
        out["a"], out["b"] = float(coeffs[0]), float(coeffs[1])
    else:
        out["model"] = "quadratic_rpm_to_mps"
        out["a2"], out["a1"], out["a0"] = [float(c) for c in coeffs]
    # report fit residual
    pred = np.polyval(coeffs, rpms)
    out["fit_rmse_mps"] = float(np.sqrt(np.mean((pred - vs) ** 2)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="garage_lab_combined/cal/blm/rpm_speed_model.json")
    ap.add_argument("--height-m", type=float, default=None, help="barrel exit height (m)")
    ap.add_argument("--g", type=float, default=9.81)
    ap.add_argument("--fit", choices=["linear", "quadratic", "interp"], default="linear")
    ap.add_argument("--points", default="", help="non-interactive: 'rpm:dist,rpm:dist,...' (dist in m)")
    args = ap.parse_args()

    H = args.height_m
    if H is None:
        H = float(input("Barrel exit height above floor, metres (e.g. 0.5): ").strip())

    pts = []
    if args.points:
        for tok in args.points.split(","):
            r, d = tok.split(":")
            v = speed_from_drop(float(d), H, args.g)
            pts.append((float(r), v))
            print(f"  RPM {float(r):.0f}: d={float(d):.2f} m -> v={v:.2f} m/s")
    else:
        print("\nFire HORIZONTAL (set 0 0 <rpm> <rpm>; reload; shoot) and measure landing distance.")
        print("Enter '<rpm> <distance_m>' per shot. Blank line or 'done' to fit.\n")
        while True:
            line = input("  rpm distance_m > ").strip()
            if not line or line.lower() == "done":
                break
            try:
                r, d = line.split()
                v = speed_from_drop(float(d), H, args.g)
                pts.append((float(r), v))
                print(f"    -> v = {v:.2f} m/s")
            except Exception:
                print("    (format: '600 3.0')")

    if len(pts) < 1:
        print("No points; nothing to save.")
        return
    pts.sort()
    model = fit(pts, args.g, H, args.fit)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(model, open(args.out, "w"), indent=2)
    print(f"\n[model] {model.get('model')}  (valid range {model['rpm_min']:.0f}-{model['rpm_max']:.0f} RPM)")
    if model["model"] == "constant_mps":
        print(f"  v = {model['v_mps']:.2f} m/s at {model['rpm']:.0f} RPM "
              f"(+/-{model.get('fit_rmse_mps',0):.2f} over {model.get('n_shots',1)} shots)")
        print("  NOTE: single-RPM model -> only shoot at this RPM until you add more points.")
    elif "a" in model:
        print(f"  v(rpm) = {model['a']:.5f}*rpm + {model['b']:.3f}   (rmse {model.get('fit_rmse_mps',0):.2f} m/s)")
        for r in (400, 600, 800):
            print(f"   rpm {r} -> {model['a']*r + model['b']:.2f} m/s")
    print("  (speed is clamped to the measured RPM range at aim time -- no extrapolation)")
    print(f"[DONE] wrote {args.out}")


if __name__ == "__main__":
    main()
