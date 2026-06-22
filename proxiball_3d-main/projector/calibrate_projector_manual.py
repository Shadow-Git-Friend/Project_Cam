#!/usr/bin/env python3
"""
calibrate_projector_manual.py — Manual projector-wall homography calibration.

How it works
------------
1. The script opens a pygame window showing 5 reference dots at known projector
   pixel positions. Move this window to the projector and maximise it (green
   button on Mac or drag to second screen first).
2. Measure where each dot lands on the wall with a tape measure.
3. Close the window (press Q or ESC), then type the measurements into the
   terminal when prompted.
4. The script computes and saves homography.json.
5. Run with --verify to interactively spot-check the calibration.

Wall coordinate convention (matches arena_dimensions.yaml):
  U (mm) : horizontal, east→west  (0 → 3050)
  V (mm) : vertical,   floor→ceil (0 → 2950)

Usage
-----
  python calibrate_projector_manual.py --wall south
  python calibrate_projector_manual.py --wall south --verify
"""

import argparse
import json
import os
import sys
import time
import threading

import numpy as np
import pygame

# ── Reference dot layout ──────────────────────────────────────────────────────
DOT_FRACS  = [(0.10, 0.10), (0.90, 0.10), (0.10, 0.90), (0.90, 0.90), (0.50, 0.50)]
DOT_LABELS = ["TL", "TR", "BL", "BR", "CTR"]
DOT_COLORS = [(0,255,0), (255,255,0), (0,120,255), (255,60,60), (255,255,255)]
DOT_RADIUS = 20

HOMOGRAPHY_PATH = os.path.join(os.path.dirname(__file__), "homography.json")


def dot_pixels(W, H):
    return [(int(fx * W), int(fy * H)) for fx, fy in DOT_FRACS]


# ── Pygame display (runs in main thread) ──────────────────────────────────────

def show_pattern(W, H, highlight=-1):
    """
    Open a pygame window showing the dot pattern.
    - Drag the window to the projector screen first, then press F for fullscreen.
    - Dots recompute every frame from actual screen size so they always fill it.
    - Press Q / ESC when done measuring.
    """
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("1) Drag to projector screen  2) Press F for fullscreen  3) Measure dots  4) Press Q when done")
    clock     = pygame.time.Clock()
    font_big  = pygame.font.SysFont("arial", 22, bold=True)
    font_sm   = pygame.font.SysFont("arial", 14)
    fullscreen = False

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif ev.key == pygame.K_f:
                    fullscreen = not fullscreen
                    if fullscreen:
                        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode((W, H))

        sw, sh = screen.get_size()
        pts = dot_pixels(sw, sh)          # recompute every frame from real size

        screen.fill((0, 0, 0))

        for i, (px, py) in enumerate(pts):
            col    = DOT_COLORS[i]
            dim    = (col[0]//5, col[1]//5, col[2]//5)
            active = (highlight < 0 or highlight == i)
            c      = col if active else dim

            pygame.draw.circle(screen, c, (px, py), DOT_RADIUS)
            pygame.draw.circle(screen, (200, 200, 200) if active else dim,
                               (px, py), DOT_RADIUS + 3, 2)

            lbl = font_big.render(DOT_LABELS[i], True, c)
            screen.blit(lbl, (px - lbl.get_width()//2, py - DOT_RADIUS - 28))

            coord = font_sm.render(f"({px},{py})", True, c)
            screen.blit(coord, (px - coord.get_width()//2, py + DOT_RADIUS + 6))

        hint_text = "Measure all dots → press Q when done  |  F = toggle fullscreen"
        hint = font_sm.render(hint_text, True, (70, 70, 70))
        screen.blit(hint, (sw//2 - hint.get_width()//2, sh - 22))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


def show_verification(W, H, H_mat):
    """Interactive verification window. User types wall coords, dot appears."""
    pygame.init()
    # Regular framed window — draggable to projector screen.
    # Do NOT go fullscreen here: macOS kills the window on focus-loss in
    # fullscreen mode, which breaks terminal input.
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Drag to projector screen — type coords in terminal")
    clock = pygame.time.Clock()
    font  = pygame.font.SysFont("arial", 16)

    state = {"px": None, "py": None, "label": ""}
    stop  = threading.Event()

    def input_thread():
        print("\nType  U V  (mm, space-separated) to project a dot there.")
        print("Type  q  to quit.\n")
        while not stop.is_set():
            try:
                raw = input("  wall U V (mm): ").strip()
            except EOFError:
                break
            if raw.lower() == "q":
                stop.set()
                break
            try:
                parts = raw.split()
                u, v = float(parts[0]), float(parts[1])
                pt = H_mat @ np.array([u, v, 1.0])
                px, py = int(pt[0]/pt[2]), int(pt[1]/pt[2])
                state["px"], state["py"] = px, py
                state["label"] = f"({u:.0f},{v:.0f})mm → px({px},{py})"
                print(f"  → projector pixel ({px}, {py})")
            except Exception:
                print("  Usage: <U_mm> <V_mm>  e.g.  1500 900")

    t = threading.Thread(target=input_thread, daemon=True)
    t.start()

    while not stop.is_set():
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pass  # ignore — only terminal 'q' closes the window
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    stop.set()  # emergency exit if terminal is unreachable

        sw, sh = screen.get_size()
        pts = dot_pixels(sw, sh)

        screen.fill((0, 0, 0))

        for i, (px, py) in enumerate(pts):
            c = tuple(v//4 for v in DOT_COLORS[i])
            pygame.draw.circle(screen, c, (px, py), DOT_RADIUS//2)

        if state["px"] is not None:
            px, py = state["px"], state["py"]
            if 0 <= px < sw and 0 <= py < sh:
                pygame.draw.circle(screen, (255, 140, 0), (px, py), 24)
                pygame.draw.circle(screen, (255, 255, 255), (px, py), 26, 2)
                lbl = font.render(state["label"], True, (255, 140, 0))
                screen.blit(lbl, (px + 30, py - 10))

        hint = font.render("type 'q' in terminal to quit  |  ESC = emergency exit", True, (60, 60, 60))
        screen.blit(hint, (sw//2 - hint.get_width()//2, sh - 24))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


# ── Calibration math ──────────────────────────────────────────────────────────

def compute_homography(proj_pts, wall_pts):
    import cv2
    src = np.array(wall_pts,  dtype=np.float64)
    dst = np.array(proj_pts,  dtype=np.float64)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None:
        raise RuntimeError("findHomography failed — check your measurements.")
    inliers = int(mask.sum()) if mask is not None else len(src)
    print(f"  Homography OK — {inliers}/{len(src)} inliers.")
    return H


def save_homography(H, wall, proj_w, proj_h, wall_pts, proj_pts):
    data = {
        "wall": wall, "proj_w": proj_w, "proj_h": proj_h,
        "H": H.tolist(),
        "calibration_points": [
            {"label": DOT_LABELS[i], "proj_px": list(proj_pts[i]),
             "wall_mm": list(wall_pts[i])}
            for i in range(len(proj_pts))
        ],
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(HOMOGRAPHY_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved → {HOMOGRAPHY_PATH}")


def load_homography():
    if not os.path.exists(HOMOGRAPHY_PATH):
        print(f"No calibration found at {HOMOGRAPHY_PATH}. Run without --verify first.")
        sys.exit(1)
    with open(HOMOGRAPHY_PATH) as f:
        data = json.load(f)
    data["H"] = np.array(data["H"], dtype=np.float64)
    return data


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wall",   default="south",
                    choices=["north","south","east","west"])
    ap.add_argument("--proj-w", type=int, default=1280)
    ap.add_argument("--proj-h", type=int, default=720)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    W, H = args.proj_w, args.proj_h

    if args.verify:
        data = load_homography()
        print(f"Loaded: wall={data['wall']}, {data['proj_w']}×{data['proj_h']}, {data['created']}")
        print("\nReprojection errors:")
        for cp in data["calibration_points"]:
            u, v   = cp["wall_mm"]
            px_o   = cp["proj_px"]
            pt     = data["H"] @ np.array([u, v, 1.0])
            px_r   = [pt[0]/pt[2], pt[1]/pt[2]]
            err    = np.hypot(px_r[0]-px_o[0], px_r[1]-px_o[1])
            print(f"  {cp['label']:3s}  err={err:.1f}px")
        show_verification(W, H, data["H"])
        return

    # ── Phase 1: show pattern ─────────────────────────────────────────────────
    print("\n" + "="*60)
    print("STEP 1 — A window will open with 5 coloured dots.")
    print("  • Move it to the projector screen")
    print("  • Maximise / fullscreen it (green button on Mac)")
    print("  • Measure where each dot lands on the wall with a tape measure:")
    print("      U = horizontal mm from the EAST edge of the wall")
    print("      V = vertical mm from the FLOOR")
    print("  • When done measuring ALL 5 dots, press Q to close the window")
    print("="*60)
    input("Press ENTER to open the pattern window …")

    show_pattern(W, H)   # blocks until Q pressed

    # ── Phase 2: collect measurements ────────────────────────────────────────
    proj_pts = dot_pixels(W, H)
    wall_pts = []

    print("\nSTEP 2 — Enter your measurements (in mm).\n")
    colors = ["GREEN", "YELLOW", "BLUE", "RED", "WHITE"]
    for i in range(len(DOT_FRACS)):
        px, py = proj_pts[i]
        print(f"  Dot {i+1}/5 — {DOT_LABELS[i]} ({colors[i]})  projector pixel ({px},{py})")
        while True:
            try:
                u = float(input("    U mm (horizontal from east edge): "))
                v = float(input("    V mm (vertical from floor):       "))
                break
            except ValueError:
                print("    Please enter a number.")
        wall_pts.append((u, v))
        print()

    # ── Phase 3: compute & save ───────────────────────────────────────────────
    print("Computing homography …")
    H_mat = compute_homography(proj_pts, wall_pts)

    print("\nReprojection errors (good calibration < 5 px):")
    errors = []
    for i, ((u, v), (px, py)) in enumerate(zip(wall_pts, proj_pts)):
        pt  = H_mat @ np.array([u, v, 1.0])
        rx, ry = pt[0]/pt[2], pt[1]/pt[2]
        err = np.hypot(rx - px, ry - py)
        errors.append(err)
        print(f"  {DOT_LABELS[i]:3s}  err={err:.1f}px")
    print(f"  Mean: {np.mean(errors):.1f}px")

    if np.mean(errors) > 20:
        print("\n  WARNING: large error — re-check measurements or re-run.")
    else:
        print("\n  Calibration looks good.")

    save_homography(H_mat, args.wall, W, H, wall_pts, proj_pts)
    print("\nRun with --verify to spot-check interactively.")


if __name__ == "__main__":
    main()
