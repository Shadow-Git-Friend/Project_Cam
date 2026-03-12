import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def load_trial_errors(path):
    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("status") != "ok":
                continue
            rows.append(
                {
                    "trial_id": r["trial_id"],
                    "joint_name": r["joint_name"],
                    "gt_x": float(r["gt_x_mm"]),
                    "gt_y": float(r["gt_y_mm"]),
                    "gt_z": float(r["gt_z_mm"]),
                    "est_x": float(r["est_x_mm"]),
                    "est_y": float(r["est_y_mm"]),
                    "est_z": float(r["est_z_mm"]),
                    "err": float(r["e_norm_mm"]),
                }
            )
    if len(rows) == 0:
        raise RuntimeError(f"No valid rows in {path}")
    return rows


def plot_3d(rows, out_path):
    joints = sorted({r["joint_name"] for r in rows})
    cmap = plt.get_cmap("tab10")
    colors = {j: cmap(i % 10) for i, j in enumerate(joints)}

    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")

    for jn in joints:
        jrows = [r for r in rows if r["joint_name"] == jn]
        gt = np.array([[r["gt_x"], r["gt_y"], r["gt_z"]] for r in jrows], dtype=np.float64)
        est = np.array([[r["est_x"], r["est_y"], r["est_z"]] for r in jrows], dtype=np.float64)
        ax.scatter(gt[:, 0], gt[:, 1], gt[:, 2], c=[colors[jn]], s=45, label=f"{jn} GT")
        ax.scatter(est[:, 0], est[:, 1], est[:, 2], c=[colors[jn]], marker="x", s=40, label=f"{jn} EST")
        for g, e in zip(gt, est):
            ax.plot([g[0], e[0]], [g[1], e[1]], [g[2], e[2]], color=colors[jn], alpha=0.5, linewidth=1.0)

    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title("Joint Touch GT: 3D GT vs Estimated")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    plt.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_error_box(rows, out_path):
    joints = sorted({r["joint_name"] for r in rows})
    data = []
    for jn in joints:
        arr = [r["err"] for r in rows if r["joint_name"] == jn and np.isfinite(r["err"])]
        data.append(arr)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.boxplot(data, labels=joints, showfliers=True)
    ax.set_ylabel("Error norm (mm)")
    ax.set_title("Joint Touch GT: Error Distribution by Joint")
    ax.grid(True, axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Visualize joint-touch GT evaluation results.")
    ap.add_argument("--trial-errors-csv", required=True, help="Path to trial_errors.csv from evaluate_pose_joint_touch_gt.py")
    ap.add_argument("--out-dir", required=True, help="Output directory for figures")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_trial_errors(args.trial_errors_csv)
    plot_3d(rows, out_dir / "joint_touch_3d_gt_vs_est.png")
    plot_error_box(rows, out_dir / "joint_touch_error_boxplot.png")
    print(f"[DONE] Visualizations saved to: {out_dir}")


if __name__ == "__main__":
    main()
