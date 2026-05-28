"""
run_all_scenarios.py
Run garage_inference.py for all scenarios 1-8 and write garage_report.txt.

Usage (from Footbonaut root):
    python Garage/run_all_scenarios.py [--start 1] [--end 8]
"""
import subprocess, sys, json, argparse, time
from pathlib import Path

ROOT         = Path(__file__).resolve().parent.parent
INFER_SCRIPT = Path(__file__).resolve().parent / "garage_inference.py"
SYNC_DIR     = ROOT / "Garage" / "garage" / "sync_records"
REPORT_PATH  = ROOT / "garage_report.txt"


def run_scenario(sid: int, engine_override: str = None) -> dict | None:
    scenario_dir = SYNC_DIR / str(sid)
    if not scenario_dir.exists():
        print(f"[SKIP] Scenario {sid}: directory not found ({scenario_dir})")
        return None

    cmd = [
        sys.executable, str(INFER_SCRIPT),
        "--scenario_dir", str(scenario_dir),
        "--scenario_id",  str(sid),
        "--out_dir",      str(ROOT),
    ]
    if engine_override:
        cmd += ["--model", engine_override]

    print(f"\n{'='*60}")
    print(f"  Scenario {sid}: {scenario_dir}")
    print(f"{'='*60}")
    t0 = time.perf_counter()

    result = subprocess.run(cmd, capture_output=False, text=True)
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"[ERROR] Scenario {sid} exited with code {result.returncode}")
        return {"scenario_id": sid, "error": f"exit_code={result.returncode}",
                "wall_time_s": round(elapsed, 1)}

    # Find the summary JSON written by garage_inference.py
    summaries = sorted(ROOT.glob(f"garage_scenario{sid}_*_summary.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    if summaries:
        with open(summaries[0]) as f:
            summary = json.load(f)
        summary["wall_time_s"] = round(elapsed, 1)
        return summary

    return {"scenario_id": sid, "error": "no_summary", "wall_time_s": round(elapsed, 1)}


def write_report(summaries: list):
    lines = [
        "=" * 70,
        "  GARAGE 4-CAMERA 3D BALL TRACKING — RESULTS REPORT",
        f"  Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        "",
        f"{'Scen':>4}  {'Frames':>7}  {'AvgFPS':>7}  {'YOLO ms':>8}  "
        f"{'Det%':>6}  {'AvgSpd':>7}  {'MaxSpd':>7}  {'Wall(s)':>8}",
        "-" * 70,
    ]

    for s in summaries:
        if "error" in s:
            lines.append(f"{s['scenario_id']:>4}  {'ERROR':>7}  {s['error']}")
            continue
        lines.append(
            f"{s['scenario_id']:>4}  "
            f"{s.get('frames', 0):>7}  "
            f"{s.get('avg_fps', 0):>7.1f}  "
            f"{s.get('avg_yolo_ms', 0):>8.1f}  "
            f"{s.get('ball_det_rate', 0):>6.1f}  "
            f"{s.get('avg_speed_mps', 0):>7.2f}  "
            f"{s.get('max_speed_mps', 0):>7.2f}  "
            f"{s.get('wall_time_s', 0):>8.1f}"
        )

    lines += [
        "-" * 70,
        "",
        "Columns:",
        "  Scen        — Scenario number",
        "  Frames      — Total frames processed",
        "  AvgFPS      — Average processing FPS",
        "  YOLO ms     — Average YOLO inference latency (ms)",
        "  Det%        — Ball detection rate (% frames with ≥1 camera)",
        "  AvgSpd      — Average 3D ball speed while tracked (m/s)",
        "  MaxSpd      — Peak 3D ball speed (m/s)",
        "  Wall(s)     — Wall-clock time to process scenario (s)",
        "",
        "Output videos:",
    ]
    for s in summaries:
        if "output_video" in s:
            lines.append(f"  Scenario {s['scenario_id']}: {s['output_video']}")

    lines += ["", "=" * 70]
    report_text = "\n".join(lines)

    REPORT_PATH.write_text(report_text)
    print("\n" + report_text)
    print(f"\n[REPORT] Written to: {REPORT_PATH}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start",  type=int, default=1)
    ap.add_argument("--end",    type=int, default=8)
    ap.add_argument("--model",  type=str, default=None,
                    help="Override model path per scenario")
    args = ap.parse_args()

    print(f"[Runner] Scenarios {args.start}–{args.end}")
    summaries = []
    for sid in range(args.start, args.end + 1):
        summary = run_scenario(sid, engine_override=args.model)
        if summary is not None:
            summaries.append(summary)

    write_report(summaries)


if __name__ == "__main__":
    main()
