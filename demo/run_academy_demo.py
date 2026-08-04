#!/usr/bin/env python3
"""End-to-end Academy Edition demo: one synthetic session -> player reports.

Simulates a 10-minute small-sided training block (8 players, 2 teams) at the
current rig's 15 FPS, runs the full project_cam.metrics stack on it, and
writes per-player markdown reports (EN/RU/KK) + a CSV metric dump to
demo/output/. No cameras, GPU, or model weights required.

    ./venv/bin/python demo/run_academy_demo.py

demo/academy_session_demo.ipynb is the annotated notebook version of this
script. On the live rig the synthetic block below is replaced by the
detection->tracking->pitch-homography trajectory stream.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from project_cam.metrics import (
    acwr,
    pass_network,
    physical_load,
    render_session_report,
    team_shape,
    voronoi_control,
)

FPS = 15.0
DURATION_S = 600.0
PITCH_L, PITCH_W = 40.0, 20.0  # small-sided indoor pitch, metres
POSITION_SIGMA_M = 0.05  # indoor multi-cam figure; arena rig measures ~0.004
OUT_DIR = Path(__file__).parent / "output"


def synth_trajectory(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Random-waypoint motion with jog/sprint episodes, clipped to the pitch."""
    t = np.arange(0.0, DURATION_S, 1.0 / FPS)
    pos = np.zeros((len(t), 2))
    pos[0] = rng.uniform([5, 3], [PITCH_L - 5, PITCH_W - 3])
    target = pos[0].copy()
    speed = 1.5
    for i in range(1, len(t)):
        if np.linalg.norm(target - pos[i - 1]) < 1.0 or rng.random() < 0.002:
            target = rng.uniform([1, 1], [PITCH_L - 1, PITCH_W - 1])
            # ~8% of legs are sprints, the rest walk/jog.
            speed = rng.choice([1.2, 2.5, 4.5, 7.5], p=[0.42, 0.35, 0.15, 0.08])
        direction = target - pos[i - 1]
        norm = np.linalg.norm(direction)
        step = speed / FPS
        pos[i] = pos[i - 1] + (direction / norm * min(step, norm) if norm > 0 else 0.0)
    pos += rng.normal(0.0, POSITION_SIGMA_M, size=pos.shape)
    return pos, t


def main() -> None:
    rng = np.random.default_rng(7)
    OUT_DIR.mkdir(exist_ok=True)
    session_start = datetime(2026, 7, 2, 5, 0, tzinfo=timezone.utc)  # 10:00 Almaty

    players = [f"{i + 1:02d}" for i in range(8)]
    teams = {p: ("A" if i < 4 else "B") for i, p in enumerate(players)}
    trajectories = {p: synth_trajectory(rng) for p in players}

    # --- per-player physical load + ACWR ---------------------------------
    rows = []
    for p in players:
        pos, t = trajectories[p]
        phys = physical_load(pos, t, position_sigma_m=POSITION_SIGMA_M)
        history = list(rng.normal(2800, 400, size=27).clip(min=0))
        load = acwr(history + [phys.total_distance_m])
        for lang in ("en", "ru", "kk"):
            text = render_session_report(
                p, phys.to_dict(), load.to_dict(), session_start_utc=session_start, lang=lang
            )
            (OUT_DIR / f"player_{p}_{lang}.md").write_text(text, encoding="utf-8")
        rows.append(
            {
                "player": p,
                "team": teams[p],
                "distance_m": round(phys.total_distance_m, 1),
                "distance_sigma_m": round(phys.total_distance_sigma_m, 1),
                "hsr_m": round(phys.hsr_distance_m, 1),
                "sprint_m": round(phys.sprint_distance_m, 1),
                "sprints": phys.sprint_count,
                "max_speed_kmh": round(phys.max_speed_kmh, 1),
                "accels": len(phys.accelerations),
                "decels": len(phys.decelerations),
                "met_power_wkg": round(phys.metabolic_power_mean_wkg, 2),
                "acwr": round(load.ratio, 2) if load.ratio else None,
                "acwr_band": load.band,
                "confidence": phys.confidence,
            }
        )

    with open(OUT_DIR / "session_metrics.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # --- tactical snapshot at mid-session --------------------------------
    mid = int(len(trajectories[players[0]][1]) // 2)
    team_a = np.array([trajectories[p][0][mid] for p in players if teams[p] == "A"])
    team_b = np.array([trajectories[p][0][mid] for p in players if teams[p] == "B"])
    control = voronoi_control(team_a, team_b, pitch_length=PITCH_L, pitch_width=PITCH_W)
    shape_a = team_shape(team_a)
    passes = [tuple(rng.choice([p for p in players if teams[p] == "A"], 2, replace=False))
              for _ in range(30)]
    network = pass_network(passes)

    tactical = [
        "# Tactical snapshot (mid-session)",
        f"- Pitch control: team A {control['team_a']:.0%} / team B {control['team_b']:.0%}",
        f"- Team A hull area: {shape_a['hull_area_m2']:.0f} m², "
        f"width {shape_a['width_m']:.1f} m, depth {shape_a['depth_m']:.1f} m",
        "- Team A degree centrality: "
        + ", ".join(f"{k}={v:.2f}" for k, v in network["degree_centrality"].items()),
        "",
    ]
    (OUT_DIR / "tactical_snapshot.md").write_text("\n".join(tactical), encoding="utf-8")

    print(f"Wrote {len(rows)} player reports x 3 languages + CSV + tactical snapshot")
    print(f"  -> {OUT_DIR}")
    print("\nSession table:")
    for row in rows:
        print(
            f"  #{row['player']} ({row['team']})  {row['distance_m']:7.1f} m "
            f"±{row['distance_sigma_m']:.0f}  HSR {row['hsr_m']:6.1f} m  "
            f"sprints {row['sprints']}  vmax {row['max_speed_kmh']:4.1f} km/h  "
            f"ACWR {row['acwr']} ({row['acwr_band']})"
        )


if __name__ == "__main__":
    main()
