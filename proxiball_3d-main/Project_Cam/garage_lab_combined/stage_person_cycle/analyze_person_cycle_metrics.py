#!/usr/bin/env python3
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


def _safe_mean(vals):
    return mean(vals) if vals else None


def _safe_median(vals):
    return median(vals) if vals else None


def _fmt(v, nd=3):
    if v is None:
        return "n/a"
    return f"{v:.{nd}f}"


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def summarize(rows, expected_seq):
    by_decision = defaultdict(int)
    per_joint = defaultdict(lambda: defaultdict(list))

    for r in rows:
        d = r.get("decision", "UNKNOWN")
        j = r.get("input_joint_name", "") or "unknown"
        by_decision[d] += 1
        extra = r.get("extra", {}) or {}
        calc = r.get("calculated_pitch_yaw_v", {}) or {}

        if d == "OK":
            per_joint[j]["ok_count"].append(1)
            per_joint[j]["acquire_elapsed_sec"].append(float(extra.get("acquire_elapsed_sec", 0.0)))
            per_joint[j]["conf_mean"].append(float(extra.get("conf_mean", 0.0)))
            per_joint[j]["cams_min"].append(float(extra.get("cams_min", 0.0)))
            per_joint[j]["std_mm"].append(float(extra.get("std_mm", 0.0)))
            per_joint[j]["target_hold_sec"].append(float(extra.get("target_hold_sec", 0.0)))
            if calc.get("rpm_cmd") is not None:
                per_joint[j]["rpm_cmd"].append(float(calc.get("rpm_cmd")))
            if calc.get("pitch_deg") is not None:
                per_joint[j]["pitch_deg"].append(float(calc.get("pitch_deg")))
            if calc.get("yaw_deg") is not None:
                per_joint[j]["yaw_deg"].append(float(calc.get("yaw_deg")))

        elif d == "HOLD_SUMMARY":
            per_joint[j]["hold_actual_sec"].append(float(extra.get("hold_actual_sec", 0.0)))
            per_joint[j]["hold_valid_ratio"].append(float(extra.get("hold_valid_ratio", 0.0)))
            per_joint[j]["hold_conf_mean"].append(float(extra.get("hold_conf_mean", 0.0)))
            per_joint[j]["hold_cams_mean"].append(float(extra.get("hold_cams_mean", 0.0)))
            per_joint[j]["hold_xyz_std_mm"].append(float(extra.get("hold_xyz_std_mm", 0.0)))

        elif d in ("OUT_OF_RANGE", "LOW_CONFIDENCE", "ESTOP"):
            per_joint[j][f"{d.lower()}_count"].append(1)

    total_expected = len(expected_seq)
    ok_for_expected = sum(1 for j in expected_seq if len(per_joint.get(j, {}).get("ok_count", [])) > 0)

    summary = {
        "events_total": len(rows),
        "decision_counts": dict(sorted(by_decision.items())),
        "expected_sequence": expected_seq,
        "expected_targets": total_expected,
        "expected_targets_with_ok": ok_for_expected,
        "sequence_ok_ratio": (ok_for_expected / total_expected) if total_expected > 0 else None,
        "per_joint": {},
    }

    for j, m in sorted(per_joint.items()):
        summary["per_joint"][j] = {
            "ok_count": len(m.get("ok_count", [])),
            "out_of_range_count": len(m.get("out_of_range_count", [])),
            "low_confidence_count": len(m.get("low_confidence_count", [])),
            "estop_count": len(m.get("estop_count", [])),
            "acquire_elapsed_sec_mean": _safe_mean(m.get("acquire_elapsed_sec", [])),
            "acquire_elapsed_sec_median": _safe_median(m.get("acquire_elapsed_sec", [])),
            "conf_mean": _safe_mean(m.get("conf_mean", [])),
            "cams_min_mean": _safe_mean(m.get("cams_min", [])),
            "std_mm_mean": _safe_mean(m.get("std_mm", [])),
            "target_hold_sec_mean": _safe_mean(m.get("target_hold_sec", [])),
            "hold_actual_sec_mean": _safe_mean(m.get("hold_actual_sec", [])),
            "hold_valid_ratio_mean": _safe_mean(m.get("hold_valid_ratio", [])),
            "hold_conf_mean": _safe_mean(m.get("hold_conf_mean", [])),
            "hold_cams_mean": _safe_mean(m.get("hold_cams_mean", [])),
            "hold_xyz_std_mm_mean": _safe_mean(m.get("hold_xyz_std_mm", [])),
            "rpm_cmd_mean": _safe_mean(m.get("rpm_cmd", [])),
            "pitch_deg_mean": _safe_mean(m.get("pitch_deg", [])),
            "yaw_deg_mean": _safe_mean(m.get("yaw_deg", [])),
        }

    return summary


def render_markdown(summary, log_path):
    lines = []
    lines.append("# Person Cycle Metrics Report")
    lines.append("")
    lines.append(f"- Source log: `{log_path}`")
    lines.append(f"- Total events: `{summary['events_total']}`")
    lines.append(f"- Sequence OK ratio: `{_fmt(summary['sequence_ok_ratio'], 3)}`")
    lines.append("")
    lines.append("## Decision Counts")
    for k, v in summary["decision_counts"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    lines.append("## Per-Joint Summary")
    for j, m in summary["per_joint"].items():
        lines.append(f"### {j}")
        lines.append(f"- OK count: `{m['ok_count']}`")
        lines.append(f"- OUT_OF_RANGE count: `{m['out_of_range_count']}`")
        lines.append(f"- LOW_CONFIDENCE count: `{m['low_confidence_count']}`")
        lines.append(f"- ESTOP count: `{m['estop_count']}`")
        lines.append(f"- Acquire time mean (s): `{_fmt(m['acquire_elapsed_sec_mean'])}`")
        lines.append(f"- Confidence mean: `{_fmt(m['conf_mean'])}`")
        lines.append(f"- Cameras mean: `{_fmt(m['cams_min_mean'])}`")
        lines.append(f"- 3D stability std mean (mm): `{_fmt(m['std_mm_mean'])}`")
        lines.append(f"- Hold requested mean (s): `{_fmt(m['target_hold_sec_mean'])}`")
        lines.append(f"- Hold actual mean (s): `{_fmt(m['hold_actual_sec_mean'])}`")
        lines.append(f"- Hold valid ratio mean: `{_fmt(m['hold_valid_ratio_mean'])}`")
        lines.append(f"- Hold XYZ std mean (mm): `{_fmt(m['hold_xyz_std_mm_mean'])}`")
        lines.append(f"- RPM cmd mean: `{_fmt(m['rpm_cmd_mean'])}`")
        lines.append(f"- Pitch mean (deg): `{_fmt(m['pitch_deg_mean'])}`")
        lines.append(f"- Yaw mean (deg): `{_fmt(m['yaw_deg_mean'])}`")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Summarize launcher runtime JSONL decisions for person-cycle tests")
    ap.add_argument("--log", required=True, help="Path to runtime JSONL log")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--expected-sequence", default="right_knee,nose,body_center")
    args = ap.parse_args()

    log_path = Path(args.log)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_jsonl(log_path)
    expected_seq = [x.strip() for x in args.expected_sequence.split(",") if x.strip()]
    summary = summarize(rows, expected_seq)

    summary_path = out_dir / "person_cycle_summary.json"
    report_path = out_dir / "person_cycle_report.md"

    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report_path.write_text(render_markdown(summary, str(log_path)), encoding="utf-8")

    print(f"[DONE] {summary_path}")
    print(f"[DONE] {report_path}")


if __name__ == "__main__":
    main()
