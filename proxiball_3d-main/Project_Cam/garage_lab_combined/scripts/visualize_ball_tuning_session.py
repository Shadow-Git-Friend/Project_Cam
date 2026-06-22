import argparse
import csv
import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_dimensions_mm(path):
    text = Path(path).read_text(encoding="utf-8")
    dims = {}
    for k in ("X", "Y", "Z"):
        m = re.search(rf"{k}\s*=\s*([\d.]+)\s*cm", text)
        if not m:
            raise RuntimeError(f"Cannot parse {k} from {path}")
        dims[k] = float(m.group(1)) * 10.0
    return dims


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
                    "gt_x": float(r["gt_x_mm"]),
                    "gt_y": float(r["gt_y_mm"]),
                    "gt_z": float(r["gt_z_mm"]),
                    "est_x": float(r["est_x_mm"]),
                    "est_y": float(r["est_y_mm"]),
                    "est_z": float(r["est_z_mm"]),
                    "err": float(r["e_norm_mm"]),
                }
            )
    if not rows:
        raise RuntimeError(f"No valid rows in {path}")
    return rows


def plot_static_3d(rows, dims, title, out_path):
    fig = plt.figure(figsize=(12, 9))
    ax = fig.add_subplot(111, projection="3d")

    gt = np.array([[r["gt_x"], r["gt_y"], r["gt_z"]] for r in rows], dtype=np.float64)
    est = np.array([[r["est_x"], r["est_y"], r["est_z"]] for r in rows], dtype=np.float64)
    err = np.array([r["err"] for r in rows], dtype=np.float64)

    ax.scatter(gt[:, 0], gt[:, 1], gt[:, 2], c="#1f77b4", s=35, label="GT")
    sc = ax.scatter(est[:, 0], est[:, 1], est[:, 2], c=err, cmap="magma", s=35, label="Estimated")
    for g, e in zip(gt, est):
        ax.plot([g[0], e[0]], [g[1], e[1]], [g[2], e[2]], color="#999999", alpha=0.5, linewidth=1.0)

    ax.set_xlim(0, dims["X"])
    ax.set_ylim(0, dims["Y"])
    ax.set_zlim(0, dims["Z"])
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_zlabel("Z (mm)")
    ax.set_title(title)
    ax.legend(loc="upper left")
    cb = plt.colorbar(sc, ax=ax, shrink=0.7, pad=0.1)
    cb.set_label("Error norm (mm)")
    plt.tight_layout()
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def plot_static_top_slices(rows, title, out_path):
    gt = np.array([[r["gt_x"], r["gt_y"], r["gt_z"]] for r in rows], dtype=np.float64)
    est = np.array([[r["est_x"], r["est_y"], r["est_z"]] for r in rows], dtype=np.float64)
    z_levels = sorted(set(gt[:, 2].tolist()))

    fig, axes = plt.subplots(2, 2, figsize=(12, 10), sharex=True, sharey=True)
    axes = axes.ravel()
    for ax, z in zip(axes, z_levels):
        idx = np.where(np.isclose(gt[:, 2], z))[0]
        g = gt[idx]
        e = est[idx]
        ax.scatter(g[:, 0], g[:, 1], c="#1f77b4", s=60, label="GT")
        ax.scatter(e[:, 0], e[:, 1], c="#d62728", marker="x", s=55, label="Estimated")
        for gi, ei in zip(g, e):
            ax.plot([gi[0], ei[0]], [gi[1], ei[1]], color="#888888", linewidth=1.0)
        ax.set_title(f"Z = {int(z)} mm")
        ax.grid(True, alpha=0.3)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2)
    fig.suptitle(title, y=0.97)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def load_ball_points(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pts = []
    for i, fr in enumerate(data):
        b = fr.get("ball")
        if b is None:
            continue
        arr = np.asarray(b, dtype=np.float64).reshape(3)
        if np.isfinite(arr).all():
            pts.append((i, arr))
    return pts, len(data)


def plot_dynamic_trajectories(session, dims, out_path):
    names = [
        ("ball_slow", "ball_slow.json"),
        ("ball_fast", "ball_fast.json"),
        ("ball_fast_ema0.1", "ball_fast_ema0_1.json"),
        ("no_ball", "no_ball.json"),
    ]

    fig = plt.figure(figsize=(14, 10))
    axes = [
        fig.add_subplot(2, 2, 1, projection="3d"),
        fig.add_subplot(2, 2, 2, projection="3d"),
        fig.add_subplot(2, 2, 3, projection="3d"),
        fig.add_subplot(2, 2, 4, projection="3d"),
    ]

    for ax, (label, fname) in zip(axes, names):
        p = session / "results_dynamic" / fname
        if not p.exists():
            ax.set_title(f"{label} (missing)")
            continue
        pts, n = load_ball_points(p)
        if len(pts) == 0:
            ax.set_title(f"{label}: 0/{n} frames")
            ax.set_xlim(0, dims["X"])
            ax.set_ylim(0, dims["Y"])
            ax.set_zlim(0, dims["Z"])
            ax.set_xlabel("X (mm)")
            ax.set_ylabel("Y (mm)")
            ax.set_zlabel("Z (mm)")
            continue

        arr = np.array([x[1] for x in pts], dtype=np.float64)
        ax.plot(arr[:, 0], arr[:, 1], arr[:, 2], color="#f4b400", linewidth=1.5)
        ax.scatter(arr[0, 0], arr[0, 1], arr[0, 2], c="green", s=35, label="start")
        ax.scatter(arr[-1, 0], arr[-1, 1], arr[-1, 2], c="red", s=35, label="end")
        ax.set_title(f"{label}: {len(pts)}/{n} frames")
        ax.set_xlim(0, dims["X"])
        ax.set_ylim(0, dims["Y"])
        ax.set_zlim(0, dims["Z"])
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_zlabel("Z (mm)")
        ax.legend(loc="upper left")

    fig.suptitle("Dynamic Ball Trajectories")
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_path, dpi=180)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Visualize static and dynamic ball tuning results.")
    ap.add_argument("--session", required=True, help="Session dir, e.g. garage_lab_combined/gt_eval/ball_tuning_...")
    ap.add_argument("--dimensions", default="garage_lab_combined/cal/extrinsics/Dimensions.txt")
    args = ap.parse_args()

    session = Path(args.session)
    vis_dir = session / "visualizations"
    vis_dir.mkdir(parents=True, exist_ok=True)
    dims = parse_dimensions_mm(args.dimensions)

    raw_csv = session / "reports_static_raw" / "trial_errors.csv"
    corr_csv = session / "reports_static_corrected" / "trial_errors.csv"

    if raw_csv.exists():
        rows_raw = load_trial_errors(raw_csv)
        plot_static_3d(
            rows_raw,
            dims=dims,
            title="Static 36-Point Ball Test: Raw (GT vs Estimated)",
            out_path=vis_dir / "static_raw_3d.png",
        )
        plot_static_top_slices(
            rows_raw,
            title="Static 36-Point Ball Test: Raw XY Slices by Z",
            out_path=vis_dir / "static_raw_xy_slices.png",
        )

    if corr_csv.exists():
        rows_corr = load_trial_errors(corr_csv)
        plot_static_3d(
            rows_corr,
            dims=dims,
            title="Static 36-Point Ball Test: Corrected (GT vs Estimated)",
            out_path=vis_dir / "static_corrected_3d.png",
        )
        plot_static_top_slices(
            rows_corr,
            title="Static 36-Point Ball Test: Corrected XY Slices by Z",
            out_path=vis_dir / "static_corrected_xy_slices.png",
        )

    plot_dynamic_trajectories(
        session=session,
        dims=dims,
        out_path=vis_dir / "dynamic_trajectories_3d.png",
    )

    print(f"[DONE] Visualizations saved to: {vis_dir}")


if __name__ == "__main__":
    main()
