#!/usr/bin/env python3
"""Validate that all configured cameras have intrinsics for the active mode."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def load_camera_names(config_path: Path) -> list[str]:
    data = yaml.safe_load(config_path.read_text())
    cams = data.get("cameras", {}) if data else {}
    if isinstance(cams, dict):
        return list(cams.keys())
    return [str(c["name"]) for c in cams]


def intrinsics_size(data: dict) -> tuple[int | None, int | None]:
    if "image_width" in data and "image_height" in data:
        return int(data["image_width"]), int(data["image_height"])
    resolution = data.get("resolution")
    if isinstance(resolution, list) and len(resolution) == 2:
        return int(resolution[0]), int(resolution[1])
    return None, None


def reprojection_error(data: dict) -> float | None:
    for key in ("reprojection_error", "rms", "rms_error", "mean_reprojection_error"):
        if key in data:
            try:
                return float(data[key])
            except Exception:
                return None
    return None


def check_intrinsics_payload(data: dict, width: int, height: int, max_reprojection_px: float) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if "camera_matrix" not in data:
        reasons.append("missing camera_matrix")
    if "distortion_coefficients" not in data and "dist_coeffs" not in data:
        reasons.append("missing distortion coefficients")

    image_width, image_height = intrinsics_size(data)
    if image_width != width or image_height != height:
        reasons.append(f"resolution mismatch: got {image_width}x{image_height}, expected {width}x{height}")

    reproj = reprojection_error(data)
    if reproj is None:
        reasons.append("missing reprojection error")
    elif reproj > max_reprojection_px:
        reasons.append(f"reprojection too high: {reproj:.3f}px > {max_reprojection_px:.3f}px")

    frames_used = data.get("frames_used")
    if frames_used is not None:
        try:
            if int(frames_used) < 3:
                reasons.append(f"too few calibration frames: {frames_used}")
        except Exception:
            reasons.append(f"invalid frames_used: {frames_used}")

    return not reasons, reasons


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate camera intrinsics against the active capture resolution.")
    ap.add_argument("--config", default="garage_lab_combined/config/cameras_6usb_test.yaml")
    ap.add_argument("--intrinsics-dir", default="garage_lab_combined/cal/intrinsics")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--max-reprojection-px", type=float, default=2.0)
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    names = load_camera_names(Path(args.config))
    intrinsics_dir = Path(args.intrinsics_dir)
    results = {}
    passed = True
    for name in names:
        path = intrinsics_dir / f"{name}_intrinsics.json"
        if not path.exists():
            results[name] = {"path": str(path), "passed": False, "reasons": ["missing intrinsics file"]}
            passed = False
            continue
        try:
            data = json.loads(path.read_text())
        except Exception as exc:
            results[name] = {"path": str(path), "passed": False, "reasons": [f"invalid JSON: {exc}"]}
            passed = False
            continue
        ok, reasons = check_intrinsics_payload(data, args.width, args.height, args.max_reprojection_px)
        results[name] = {
            "path": str(path),
            "passed": ok,
            "reasons": reasons,
            "image_width": intrinsics_size(data)[0],
            "image_height": intrinsics_size(data)[1],
            "reprojection_error": reprojection_error(data),
            "frames_used": data.get("frames_used"),
        }
        passed = passed and ok

    report = {
        "passed": passed,
        "config": args.config,
        "intrinsics_dir": str(intrinsics_dir),
        "expected": {"width": args.width, "height": args.height, "max_reprojection_px": args.max_reprojection_px},
        "cameras": results,
    }
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
