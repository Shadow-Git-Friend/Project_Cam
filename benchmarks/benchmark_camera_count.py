"""4-camera vs 6-camera comparison harness.

Loads both camera profiles (reusing the API adapter's profile loader) and emits
a dry-run CSV row per profile capturing the camera count and resolution. This
runs without GPU/cameras and proves the 4- vs 6-camera matrix is wired to the
real configs, not hardcoded.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
# Make the src package importable when run as a plain script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from _bench_common import new_row, write_rows  # noqa: E402
from project_cam.api.pipeline_adapter import load_camera_profile  # noqa: E402


def _profile_row(path_or_name: str, frames: int) -> dict:
    prof = load_camera_profile(path_or_name)
    res = prof.geometry.get("resolution") if isinstance(prof.geometry, dict) else None
    return new_row(
        camera_profile=prof.profile,
        camera_count=prof.camera_count,
        resolution=res or "1280x720",
        model_name="capture+pipeline",
        measured_frames=0,
        warmup_frames=0,
        mode="dry_run",
        measured=False,
    )


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config-4", default="configs/cameras/cameras_4cam.yaml")
    p.add_argument("--config-6", default="configs/cameras/cameras_6cam_usb.yaml")
    p.add_argument("--frames", type=int, default=300)
    p.add_argument("--output", required=True)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.dry_run:
        raise SystemExit(
            "real camera-count benchmarking needs both rigs connected; "
            "pass --dry-run for the config-driven matrix")
    rows = [_profile_row(args.config_4, args.frames),
            _profile_row(args.config_6, args.frames)]
    path = write_rows(args.output, rows)
    counts = ", ".join(str(r["camera_count"]) for r in rows)
    print(f"[benchmark_camera_count] wrote {len(rows)} row(s) "
          f"(camera_count={counts}) -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
