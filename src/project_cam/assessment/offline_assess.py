"""CLI for offline athlete movement assessment from Project_Cam 3D joints."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .io import load_motion, write_json
from .maturity import maybe_calculate_maturity
from .reports import build_report
from .rules import DEFAULT_CONFIG_PATH, load_rules


def run_assessment(
    input_path: str | Path,
    output_path: str | Path,
    exercise: str,
    athlete_id: str,
    age: int | None,
    sex: str | None,
    fps: float,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    session_id: str | None = None,
    standing_height_cm: float | None = None,
    sitting_height_cm: float | None = None,
    body_mass_kg: float | None = None,
    calibration_report_path: str | Path | None = None,
    html_output_path: str | Path | None = None,
) -> dict[str, Any]:
    frames = load_motion(input_path, default_fps=fps)
    config = load_rules(config_path)
    maturity = maybe_calculate_maturity(
        sex=sex,
        age_years=age,
        standing_height_cm=standing_height_cm,
        sitting_height_cm=sitting_height_cm,
        body_mass_kg=body_mass_kg,
    )
    calibration = None
    if calibration_report_path:
        import json

        calibration = json.loads(Path(calibration_report_path).read_text(encoding="utf-8"))
    report = build_report(
        frames=frames,
        exercise=exercise,
        config=config,
        athlete_id=athlete_id,
        age=age,
        sex=sex,
        fps=fps,
        session_id=session_id,
        maturity=maturity,
        calibration=calibration,
    )
    write_json(output_path, report)
    if html_output_path:
        from .render import render_html_report

        render_html_report(report, html_output_path)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate an offline athlete movement assessment report from 3D joints.")
    ap.add_argument("--input", required=True, help="Input Project_Cam JSON or UDP JSONL joint file")
    ap.add_argument("--exercise", required=True, help="Exercise key from configs/exercises/football_academy_u10.yaml")
    ap.add_argument("--athlete-id", required=True, help="Pseudonymous athlete identifier")
    ap.add_argument("--age", type=int, default=None)
    ap.add_argument("--sex", choices=["male", "female", "unspecified"], default="unspecified")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    ap.add_argument("--output", required=True, help="Output report JSON path")
    ap.add_argument("--html-output", default=None, help="Optional output HTML report path")
    ap.add_argument("--standing-height-cm", type=float, default=None)
    ap.add_argument("--sitting-height-cm", type=float, default=None)
    ap.add_argument("--body-mass-kg", type=float, default=None)
    ap.add_argument("--calibration-report", default=None, help="Optional JSON from project_cam.assessment.cal_check")
    args = ap.parse_args(argv)

    report = run_assessment(
        input_path=args.input,
        output_path=args.output,
        exercise=args.exercise,
        athlete_id=args.athlete_id,
        age=args.age,
        sex=args.sex,
        fps=args.fps,
        config_path=args.config,
        session_id=args.session_id,
        standing_height_cm=args.standing_height_cm,
        sitting_height_cm=args.sitting_height_cm,
        body_mass_kg=args.body_mass_kg,
        calibration_report_path=args.calibration_report,
        html_output_path=args.html_output,
    )
    print(f"[OK] Wrote {report['exercise']} assessment report -> {args.output}")
    if args.html_output:
        print(f"[OK] Wrote HTML assessment report -> {args.html_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
