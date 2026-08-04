#!/usr/bin/env python3
"""
draw_camera_layout_diagram.py — labelled mounting diagram for the 6-USB cable-aware layout.

Produces a 2-panel schematic (top-down + side view) showing each camera's position,
the direction it points, and the role it "owns". Meant as a print/mount reference,
NOT a coverage simulation (use visualize_camera_coverage.py for coverage %).

Output: scripts/coverage_out/layout_diagram_six_usb.png
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ARENA = np.array([6230.0, 3050.0, 2950.0])   # X N->S, Y E->W, Z up
OUT = Path(__file__).resolve().parent / "coverage_out"
OUT.mkdir(parents=True, exist_ok=True)

# name, pos(x,y,z), aim(x,y,z), color, role(short), physical
CAMS = [
    ("camNorth_EastHigh", (80, 550, 2200),  (3600, 1500, 1100), "#1f77b4",
     "Front-high pose + BLM aim (E)", "1080P USB"),
    ("camNorth_WestHigh", (80, 2500, 2200), (3600, 1500, 1100), "#2ca02c",
     "Front-high pose + BLM aim (W)", "1080P USB"),
    ("camEast_Low",       (3100, 80, 450),   (3400, 1500, 450),  "#ff7f0e",
     "Low side: push-ups / feet (E)", "C920"),
    ("camWest_Low",       (3100, 2970, 450), (3400, 1500, 450),  "#d62728",
     "Low side: push-ups / feet (W)", "C920"),
    ("camSouth_High",     (6150, 2300, 2300),(2800, 1500, 1000), "#9467bd",
     "Rear-high: depth + ball approach", "1080P USB"),
    ("camBounce_TargetLow",(5000, 80, 350),  (6230, 1600, 850),  "#8c564b",
     "Bounce / goal: south wall + floor", "1080P USB"),
]


def aim_arrow(ax, x0, y0, x1, y1, color, length=1300):
    d = np.array([x1 - x0, y1 - y0], float)
    n = np.linalg.norm(d)
    if n < 1e-6:
        return
    d = d / n * min(length, n)
    ax.annotate("", xy=(x0 + d[0], y0 + d[1]), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=2.2, alpha=0.9))


fig, (axT, axS) = plt.subplots(2, 1, figsize=(13, 15),
                               gridspec_kw={"height_ratios": [3, 1.5]})

# ───────────────────────── TOP-DOWN (Y horizontal, X vertical) ─────────────────
axT.add_patch(plt.Rectangle((0, 0), ARENA[1], ARENA[0], fill=False, ec="black", lw=2))
# bounce strip near south wall
axT.add_patch(plt.Rectangle((0, 5600), ARENA[1], ARENA[0]-5600, color="red", alpha=0.10))
axT.text(ARENA[1]/2, 5900, "BOUNCE STRIP", color="red", ha="center", fontsize=9, alpha=0.8)
# player working zone
axT.add_patch(plt.Rectangle((600, 1800), 1850, 3200, color="green", alpha=0.07))
axT.text(1525, 3400, "player working zone", color="green", ha="center", fontsize=9, alpha=0.7)
# wall labels
axT.text(ARENA[1]/2, -180, "NORTH wall (X=0)", ha="center", fontsize=10, weight="bold")
axT.text(ARENA[1]/2, ARENA[0]+260, "SOUTH wall (X=6230) — projection / impact / goal grid",
         ha="center", fontsize=10, weight="bold", color="#b00")
axT.text(-160, ARENA[0]/2, "EAST (Y=0)", va="center", rotation=90, fontsize=9)
axT.text(ARENA[1]+160, ARENA[0]/2, "WEST (Y=3050)", va="center", rotation=90, fontsize=9)

# per-camera label offset (points) so nothing overlaps the title/each other
LBL_OFF = {
    "camNorth_EastHigh":  (-150, 55),
    "camNorth_WestHigh":  (15, 55),
    "camEast_Low":        (15, -10),
    "camWest_Low":        (-150, -10),
    "camSouth_High":      (-150, -70),
    "camBounce_TargetLow":(15, 25),
}
for name, p, a, c, role, phys in CAMS:
    axT.scatter(p[1], p[0], s=180, color=c, edgecolor="white", zorder=5)
    aim_arrow(axT, p[1], p[0], a[1], a[0], c)
    lbl = f"{name}\n[{phys}]\n{role}"
    axT.annotate(lbl, (p[1], p[0]), textcoords="offset points",
                 xytext=LBL_OFF.get(name, (8, 8)), fontsize=8, color=c, weight="bold")

axT.set_xlim(-700, ARENA[1]+900); axT.set_ylim(-650, ARENA[0]+700)
axT.invert_yaxis()                                  # North on top
axT.set_aspect("equal"); axT.set_title("TOP-DOWN VIEW (bird's eye) — positions + aim direction", fontsize=12, weight="bold", pad=22)
axT.set_xlabel("Y  East → West (mm)"); axT.set_ylabel("X  North → South (mm)")

# ───────────────────────── SIDE (X horizontal, Z vertical) ─────────────────────
axS.add_patch(plt.Rectangle((0, 0), ARENA[0], ARENA[2], fill=False, ec="black", lw=2))
axS.axhline(0, color="saddlebrown", lw=3)           # floor
axS.text(ARENA[0]/2, -230, "floor", ha="center", fontsize=9, color="saddlebrown")
axS.text(80, ARENA[2]+90, "NORTH (X=0)", fontsize=9)
axS.text(ARENA[0]-80, ARENA[2]+90, "SOUTH wall (X=6230)", fontsize=9, ha="right", color="#b00")
axS.axvline(ARENA[0], color="#b00", lw=3, alpha=0.5)

for name, p, a, c, role, phys in CAMS:
    axS.scatter(p[0], p[2], s=170, color=c, edgecolor="white", zorder=5)
    aim_arrow(axS, p[0], p[2], a[0], a[2], c, length=900)
    axS.annotate(name.replace("cam", ""), (p[0], p[2]), textcoords="offset points",
                 xytext=(6, 8), fontsize=8, color=c, weight="bold")

axS.set_xlim(-300, ARENA[0]+400); axS.set_ylim(-350, ARENA[2]+250)
axS.set_aspect("equal"); axS.set_title("SIDE VIEW (looking from the East) — mounting heights", fontsize=12, weight="bold")
axS.set_xlabel("X  North → South (mm)"); axS.set_ylabel("Z  height (mm)")

# legend / role table at bottom
roles = "\n".join(f"●  {n}  [{ph}] — {r}" for n, _, _, c, r, ph in CAMS)
fig.text(0.5, 0.005,
         "2× North-high → front 3D for BLM aim + occlusion backup   |   2× side-low → push-ups/squats feet   |   "
         "1× South-high → depth + ball approach   |   1× bounce → goal wall + floor bounce",
         ha="center", fontsize=9, style="italic")

plt.tight_layout(rect=[0, 0.02, 1, 1])
out = OUT / "layout_diagram_six_usb.png"
fig.savefig(out, dpi=140, bbox_inches="tight")
print("saved:", out)
