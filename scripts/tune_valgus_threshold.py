"""Throwaway: measure signed valgus on real recordings to set thresholds.

Reports min / mean / p95 / max of `knee_valgus_signed_ratio` per side for each
recording in data/raw/. The goal is to pick a threshold that separates clean
from valgus without flagging clean. Delete this script after thresholds land.
"""

from __future__ import annotations

import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from project_cam.assessment.io import load_motion
from project_cam.assessment.kinematics import frame_kinematics

RECORDINGS = [
    ("clean", "data/raw/athlete_001_squat_clean.jsonl"),
    ("good", "data/raw/athlete_001_squat_good.jsonl"),
    ("valgus", "data/raw/athlete_001_squat_valgus.jsonl"),
]


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    sv = sorted(values)
    k = max(0, min(len(sv) - 1, int(round(q * (len(sv) - 1)))))
    return sv[k]


def main() -> None:
    print(f"{'label':<8}{'side':<8}{'n':>6}{'min':>10}{'mean':>10}{'p95':>10}{'max':>10}")
    rows: dict[str, dict[str, float]] = {}
    for label, path in RECORDINGS:
        frames = load_motion(ROOT / path, default_fps=15.0)
        per_frame = [frame_kinematics(f) for f in frames]
        for side in ("left", "right"):
            values = [
                fm["knee_valgus_signed_ratio"].get(side)
                for fm in per_frame
                if fm["knee_valgus_signed_ratio"].get(side) is not None
            ]
            values = [float(v) for v in values]
            row = {
                "n": len(values),
                "min": min(values) if values else float("nan"),
                "mean": mean(values) if values else float("nan"),
                "p95": percentile(values, 0.95),
                "max": max(values) if values else float("nan"),
            }
            rows[f"{label}_{side}"] = row
            print(
                f"{label:<8}{side:<8}{row['n']:>6}"
                f"{row['min']:>10.4f}{row['mean']:>10.4f}"
                f"{row['p95']:>10.4f}{row['max']:>10.4f}"
            )

    # Suggest a threshold: just above the worst clean p95, well below valgus p95.
    clean_p95 = max(rows["clean_left"]["p95"], rows["clean_right"]["p95"])
    valgus_p95 = max(rows["valgus_left"]["p95"], rows["valgus_right"]["p95"])
    print(
        f"\nclean p95 (max-side): {clean_p95:.4f}\n"
        f"valgus p95 (max-side): {valgus_p95:.4f}\n"
        f"separation ratio: {valgus_p95 / clean_p95 if clean_p95 > 0 else float('inf'):.2f}x"
    )
    midpoint = (clean_p95 + valgus_p95) / 2 if clean_p95 < valgus_p95 else valgus_p95 * 1.1
    suggestion = round(midpoint, 3)
    print(f"\nSuggested squat threshold: ~{suggestion:.3f}")
    print(f"Suggested single_leg_squat threshold: ~{suggestion * 1.4:.3f}  (40% looser)")


if __name__ == "__main__":
    main()
