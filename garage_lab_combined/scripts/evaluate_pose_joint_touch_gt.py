import argparse
import csv
import json
from pathlib import Path

import numpy as np


JOINT_NAME_TO_INDEX = {
    "nose": 0,
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
    "left_knee": 13,
    "right_knee": 14,
    "left_ankle": 15,
    "right_ankle": 16,
}

JOINT_ALIASES = {
    "head": "nose",
    "left_arm": "left_wrist",
    "right_arm": "right_wrist",
}


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return np.nan


def percentile(values, q):
    if len(values) == 0:
        return np.nan
    return float(np.percentile(np.asarray(values, dtype=np.float64), q))


def normalize_joint_name(name):
    n = str(name).strip().lower()
    if n in JOINT_ALIASES:
        n = JOINT_ALIASES[n]
    return n


def resolve_joint_index(joint_name, joint_index):
    if joint_index is not None and str(joint_index).strip() != "":
        try:
            j = int(joint_index)
            if 0 <= j <= 16:
                return j
        except Exception:
            pass

    n = normalize_joint_name(joint_name)
    if n in JOINT_NAME_TO_INDEX:
        return JOINT_NAME_TO_INDEX[n]
    return None


def load_trials_csv(path):
    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            trial_id = str(r.get("trial_id", "")).strip()
            joint_name = normalize_joint_name(r.get("joint_name", ""))
            joint_index = resolve_joint_index(joint_name, r.get("joint_index"))

            gt_x = safe_float(r.get("x_mm", np.nan))
            gt_y = safe_float(r.get("y_mm", np.nan))
            gt_z = safe_float(r.get("z_mm", np.nan))

            rows.append(
                {
                    "trial_id": trial_id,
                    "joint_name": joint_name,
                    "joint_index": joint_index,
                    "gt_x_mm": gt_x,
                    "gt_y_mm": gt_y,
                    "gt_z_mm": gt_z,
                }
            )
    return rows


def frame_window(n, start_frac, end_frac):
    if n <= 0:
        return 0, 0
    a = int(max(0, min(n - 1, round((n - 1) * start_frac))))
    b = int(max(a + 1, min(n, round(n * end_frac))))
    return a, b


def analyze_trial(frames, gt, start_frac, end_frac):
    n_total = len(frames)
    a, b = frame_window(n_total, start_frac, end_frac)
    win = frames[a:b]
    jidx = gt["joint_index"]

    pts = []
    for fr in win:
        joints = fr.get("joints")
        if not isinstance(joints, list):
            continue
        if jidx is None or jidx < 0 or jidx >= len(joints):
            continue
        p = joints[jidx]
        if p is None:
            continue
        arr = np.asarray(p, dtype=np.float64).reshape(3)
        if not np.isfinite(arr).all():
            continue
        pts.append(arr)

    n_win = len(win)
    n_valid = len(pts)
    detect_ratio = (n_valid / n_win) if n_win > 0 else 0.0

    if n_valid == 0:
        return {
            "n_total": n_total,
            "win_start": a,
            "win_end": b,
            "n_window": n_win,
            "n_valid": 0,
            "detect_ratio": detect_ratio,
            "est": [np.nan, np.nan, np.nan],
            "err": [np.nan, np.nan, np.nan],
            "err_norm": np.nan,
            "std_xyz": [np.nan, np.nan, np.nan],
            "std_norm": np.nan,
        }

    pts = np.asarray(pts, dtype=np.float64)
    est = np.median(pts, axis=0)
    gt_vec = np.asarray([gt["gt_x_mm"], gt["gt_y_mm"], gt["gt_z_mm"]], dtype=np.float64)
    err = est - gt_vec
    err_norm = float(np.linalg.norm(err))

    std_xyz = np.std(pts, axis=0)
    centered = pts - est.reshape(1, 3)
    std_norm = float(np.mean(np.linalg.norm(centered, axis=1)))

    return {
        "n_total": n_total,
        "win_start": a,
        "win_end": b,
        "n_window": n_win,
        "n_valid": n_valid,
        "detect_ratio": detect_ratio,
        "est": est.tolist(),
        "err": err.tolist(),
        "err_norm": err_norm,
        "std_xyz": std_xyz.tolist(),
        "std_norm": std_norm,
    }


def fit_axis_linear_correction(est_vals, gt_vals):
    if len(est_vals) < 2:
        return {"a": 1.0, "b": 0.0}
    a, b = np.polyfit(np.asarray(est_vals), np.asarray(gt_vals), 1)
    return {"a": float(a), "b": float(b)}


def aggregate_joint(rows, joint_name):
    jrows = [r for r in rows if r.get("status") == "ok" and r.get("joint_name") == joint_name]
    errs = [r["e_norm_mm"] for r in jrows if np.isfinite(r["e_norm_mm"])]
    ex = [r["ex_mm"] for r in jrows if np.isfinite(r["ex_mm"])]
    ey = [r["ey_mm"] for r in jrows if np.isfinite(r["ey_mm"])]
    ez = [r["ez_mm"] for r in jrows if np.isfinite(r["ez_mm"])]
    det = [r["detect_ratio_window"] for r in jrows if np.isfinite(r["detect_ratio_window"])]
    stdn = [r["std_norm_mm"] for r in jrows if np.isfinite(r["std_norm_mm"])]

    rmse = float(np.sqrt(np.mean(np.square(errs)))) if len(errs) > 0 else np.nan
    return {
        "num_trials_ok": len(jrows),
        "error_norm_mm": {
            "mean": float(np.mean(errs)) if len(errs) > 0 else np.nan,
            "median": percentile(errs, 50),
            "rmse": rmse,
            "p90": percentile(errs, 90),
            "p95": percentile(errs, 95),
            "max": float(np.max(errs)) if len(errs) > 0 else np.nan,
        },
        "axis_bias_mm": {
            "ex_mean": float(np.mean(ex)) if len(ex) > 0 else np.nan,
            "ey_mean": float(np.mean(ey)) if len(ey) > 0 else np.nan,
            "ez_mean": float(np.mean(ez)) if len(ez) > 0 else np.nan,
        },
        "detection": {
            "detect_ratio_mean": float(np.mean(det)) if len(det) > 0 else np.nan,
        },
        "static_precision_mm": {
            "std_norm_mean": float(np.mean(stdn)) if len(stdn) > 0 else np.nan,
            "std_norm_p95": percentile(stdn, 95),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="Evaluate 3D joint-touch GT trials.")
    ap.add_argument("--trials-csv", required=True, help="CSV with columns: trial_id,joint_name,joint_index,x_mm,y_mm,z_mm")
    ap.add_argument("--results-dir", required=True, help="Directory with per-trial JSONs, e.g. J001.json")
    ap.add_argument("--out-dir", required=True, help="Output dir for reports")
    ap.add_argument("--window-start-frac", type=float, default=0.20)
    ap.add_argument("--window-end-frac", type=float, default=0.80)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    trials = load_trials_csv(args.trials_csv)
    rows = []

    for t in trials:
        trial_id = t["trial_id"]

        if t["joint_index"] is None:
            rows.append(
                {
                    "trial_id": trial_id,
                    "joint_name": t["joint_name"],
                    "joint_index": "",
                    "gt_x_mm": t["gt_x_mm"],
                    "gt_y_mm": t["gt_y_mm"],
                    "gt_z_mm": t["gt_z_mm"],
                    "status": "bad_joint_name_or_index",
                }
            )
            continue

        if not np.isfinite(t["gt_x_mm"]) or not np.isfinite(t["gt_y_mm"]) or not np.isfinite(t["gt_z_mm"]):
            rows.append(
                {
                    "trial_id": trial_id,
                    "joint_name": t["joint_name"],
                    "joint_index": t["joint_index"],
                    "gt_x_mm": t["gt_x_mm"],
                    "gt_y_mm": t["gt_y_mm"],
                    "gt_z_mm": t["gt_z_mm"],
                    "status": "missing_gt",
                }
            )
            continue

        p = Path(args.results_dir) / f"{trial_id}.json"
        if not p.exists():
            rows.append(
                {
                    "trial_id": trial_id,
                    "joint_name": t["joint_name"],
                    "joint_index": t["joint_index"],
                    "gt_x_mm": t["gt_x_mm"],
                    "gt_y_mm": t["gt_y_mm"],
                    "gt_z_mm": t["gt_z_mm"],
                    "status": "missing_result",
                }
            )
            continue

        with open(p, "r") as f:
            frames = json.load(f)

        s = analyze_trial(
            frames=frames,
            gt=t,
            start_frac=args.window_start_frac,
            end_frac=args.window_end_frac,
        )

        ex, ey, ez = s["err"]
        estx, esty, estz = s["est"]
        stdx, stdy, stdz = s["std_xyz"]
        rows.append(
            {
                "trial_id": trial_id,
                "joint_name": t["joint_name"],
                "joint_index": t["joint_index"],
                "gt_x_mm": t["gt_x_mm"],
                "gt_y_mm": t["gt_y_mm"],
                "gt_z_mm": t["gt_z_mm"],
                "est_x_mm": estx,
                "est_y_mm": esty,
                "est_z_mm": estz,
                "ex_mm": ex,
                "ey_mm": ey,
                "ez_mm": ez,
                "e_norm_mm": s["err_norm"],
                "std_x_mm": stdx,
                "std_y_mm": stdy,
                "std_z_mm": stdz,
                "std_norm_mm": s["std_norm"],
                "n_total_frames": s["n_total"],
                "window_start": s["win_start"],
                "window_end": s["win_end"],
                "n_window_frames": s["n_window"],
                "n_valid_joint_frames": s["n_valid"],
                "detect_ratio_window": s["detect_ratio"],
                "status": "ok" if np.isfinite(s["err_norm"]) else "no_joint_detected",
            }
        )

    cols = [
        "trial_id",
        "joint_name",
        "joint_index",
        "gt_x_mm",
        "gt_y_mm",
        "gt_z_mm",
        "est_x_mm",
        "est_y_mm",
        "est_z_mm",
        "ex_mm",
        "ey_mm",
        "ez_mm",
        "e_norm_mm",
        "std_x_mm",
        "std_y_mm",
        "std_z_mm",
        "std_norm_mm",
        "n_total_frames",
        "window_start",
        "window_end",
        "n_window_frames",
        "n_valid_joint_frames",
        "detect_ratio_window",
        "status",
    ]
    trial_csv = out_dir / "trial_errors.csv"
    with open(trial_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    ok_rows = [r for r in rows if r.get("status") == "ok"]
    err_norm = [r["e_norm_mm"] for r in ok_rows if np.isfinite(r["e_norm_mm"])]
    ex_vals = [r["ex_mm"] for r in ok_rows if np.isfinite(r["ex_mm"])]
    ey_vals = [r["ey_mm"] for r in ok_rows if np.isfinite(r["ey_mm"])]
    ez_vals = [r["ez_mm"] for r in ok_rows if np.isfinite(r["ez_mm"])]
    detect_vals = [r["detect_ratio_window"] for r in rows if "detect_ratio_window" in r and np.isfinite(r["detect_ratio_window"])]
    std_vals = [r["std_norm_mm"] for r in ok_rows if np.isfinite(r["std_norm_mm"])]

    rmse = float(np.sqrt(np.mean(np.square(err_norm)))) if len(err_norm) > 0 else np.nan
    summary = {
        "num_trials_total": len(rows),
        "num_trials_ok": len(ok_rows),
        "num_trials_missing_or_failed": len(rows) - len(ok_rows),
        "error_norm_mm": {
            "mean": float(np.mean(err_norm)) if len(err_norm) > 0 else np.nan,
            "median": percentile(err_norm, 50),
            "rmse": rmse,
            "p90": percentile(err_norm, 90),
            "p95": percentile(err_norm, 95),
            "max": float(np.max(err_norm)) if len(err_norm) > 0 else np.nan,
        },
        "axis_bias_mm": {
            "ex_mean": float(np.mean(ex_vals)) if len(ex_vals) > 0 else np.nan,
            "ey_mean": float(np.mean(ey_vals)) if len(ey_vals) > 0 else np.nan,
            "ez_mean": float(np.mean(ez_vals)) if len(ez_vals) > 0 else np.nan,
        },
        "static_precision_mm": {
            "std_norm_mean": float(np.mean(std_vals)) if len(std_vals) > 0 else np.nan,
            "std_norm_p95": percentile(std_vals, 95),
        },
        "detection": {
            "detect_ratio_mean": float(np.mean(detect_vals)) if len(detect_vals) > 0 else np.nan,
        },
    }

    joint_names = sorted({r["joint_name"] for r in rows if str(r.get("joint_name", "")).strip()})
    summary["per_joint"] = {}
    for jn in joint_names:
        summary["per_joint"][jn] = aggregate_joint(rows, jn)

    with open(out_dir / "summary_metrics.json", "w") as f:
        json.dump(summary, f, indent=2)

    est_x = [r["est_x_mm"] for r in ok_rows if np.isfinite(r["est_x_mm"]) and np.isfinite(r["gt_x_mm"])]
    est_y = [r["est_y_mm"] for r in ok_rows if np.isfinite(r["est_y_mm"]) and np.isfinite(r["gt_y_mm"])]
    est_z = [r["est_z_mm"] for r in ok_rows if np.isfinite(r["est_z_mm"]) and np.isfinite(r["gt_z_mm"])]
    gt_x = [r["gt_x_mm"] for r in ok_rows if np.isfinite(r["est_x_mm"]) and np.isfinite(r["gt_x_mm"])]
    gt_y = [r["gt_y_mm"] for r in ok_rows if np.isfinite(r["est_y_mm"]) and np.isfinite(r["gt_y_mm"])]
    gt_z = [r["gt_z_mm"] for r in ok_rows if np.isfinite(r["est_z_mm"]) and np.isfinite(r["gt_z_mm"])]

    correction_model = {
        "global_bias_add_mm": {
            "x": -summary["axis_bias_mm"]["ex_mean"] if np.isfinite(summary["axis_bias_mm"]["ex_mean"]) else 0.0,
            "y": -summary["axis_bias_mm"]["ey_mean"] if np.isfinite(summary["axis_bias_mm"]["ey_mean"]) else 0.0,
            "z": -summary["axis_bias_mm"]["ez_mean"] if np.isfinite(summary["axis_bias_mm"]["ez_mean"]) else 0.0,
        },
        "axis_linear_gt_from_est": {
            "x": fit_axis_linear_correction(est_x, gt_x),
            "y": fit_axis_linear_correction(est_y, gt_y),
            "z": fit_axis_linear_correction(est_z, gt_z),
        },
        "per_joint_bias_add_mm": {},
    }

    for jn in joint_names:
        stats = summary["per_joint"].get(jn, {})
        b = stats.get("axis_bias_mm", {})
        correction_model["per_joint_bias_add_mm"][jn] = {
            "x": -float(b["ex_mean"]) if np.isfinite(b.get("ex_mean", np.nan)) else 0.0,
            "y": -float(b["ey_mean"]) if np.isfinite(b.get("ey_mean", np.nan)) else 0.0,
            "z": -float(b["ez_mean"]) if np.isfinite(b.get("ez_mean", np.nan)) else 0.0,
        }

    with open(out_dir / "correction_model.json", "w") as f:
        json.dump(correction_model, f, indent=2)

    report_path = out_dir / "error_report.md"
    lines = []
    lines.append("# Joint Touch 3D GT Error Report")
    lines.append("")
    lines.append(f"- Trials total: `{summary['num_trials_total']}`")
    lines.append(f"- Trials valid: `{summary['num_trials_ok']}`")
    lines.append(f"- Trials missing/failed: `{summary['num_trials_missing_or_failed']}`")
    lines.append("")
    lines.append("## Error (mm)")
    lines.append(f"- Mean: `{summary['error_norm_mm']['mean']:.2f}`")
    lines.append(f"- Median: `{summary['error_norm_mm']['median']:.2f}`")
    lines.append(f"- RMSE: `{summary['error_norm_mm']['rmse']:.2f}`")
    lines.append(f"- P90: `{summary['error_norm_mm']['p90']:.2f}`")
    lines.append(f"- P95: `{summary['error_norm_mm']['p95']:.2f}`")
    lines.append(f"- Max: `{summary['error_norm_mm']['max']:.2f}`")
    lines.append("")
    lines.append("## Axis Bias (mm)")
    lines.append(f"- ex mean: `{summary['axis_bias_mm']['ex_mean']:.2f}`")
    lines.append(f"- ey mean: `{summary['axis_bias_mm']['ey_mean']:.2f}`")
    lines.append(f"- ez mean: `{summary['axis_bias_mm']['ez_mean']:.2f}`")
    lines.append("")
    lines.append("## Detection Quality")
    lines.append(f"- Mean detection ratio (window): `{summary['detection']['detect_ratio_mean']:.3f}`")
    lines.append("")
    lines.append("## Precision (Static Hold)")
    lines.append(f"- Mean std-norm (mm): `{summary['static_precision_mm']['std_norm_mean']:.2f}`")
    lines.append(f"- P95 std-norm (mm): `{summary['static_precision_mm']['std_norm_p95']:.2f}`")
    lines.append("")
    lines.append("## Per Joint")
    for jn in joint_names:
        js = summary["per_joint"].get(jn, {})
        je = js.get("error_norm_mm", {})
        lines.append(f"- `{jn}`: mean `{je.get('mean', np.nan):.2f}` mm, p95 `{je.get('p95', np.nan):.2f}` mm")
    lines.append("")
    lines.append("## Outputs")
    lines.append("- `trial_errors.csv`")
    lines.append("- `summary_metrics.json`")
    lines.append("- `correction_model.json`")
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"[DONE] {trial_csv}")
    print(f"[DONE] {out_dir / 'summary_metrics.json'}")
    print(f"[DONE] {out_dir / 'correction_model.json'}")
    print(f"[DONE] {report_path}")


if __name__ == "__main__":
    main()
