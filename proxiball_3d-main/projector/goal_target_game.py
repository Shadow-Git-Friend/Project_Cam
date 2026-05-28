#!/usr/bin/env python3
"""
goal_target_game.py — Footbonaut-style projector goal game (single process).

Projector (DP-1-2) shows a 3x3 grid; one zone is the active green target.
camNorth + YOLO + tracker detect the ball; when the ball decelerates
inside a grid zone, the program checks if it was the active one:
  active zone  → HIT  (green flash, +1 score, pick a new active zone)
  other zone   → MISS (red flash)

Both projector grid and camera detection live in the same wall (mm)
coordinate system:
  - Camera pixel → wall mm via SouthWallMapper (intrinsics + extrinsics).
  - Wall mm     → projector pixel via homography.json (manual calibration).

Run:
  ./venv/bin/python proxiball_3d-main/projector/goal_target_game.py \\
      --proj-pos 1920,0 --show-debug
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import yaml

PROJECTOR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROJECTOR_DIR.parents[1]
sys.path.insert(0, str(PROJECTOR_DIR))

from static_grid_goal_logic import (  # noqa: E402
    SOUTH_WALL_U_MAX_MM,
    SOUTH_WALL_V_MAX_MM,
    SouthWallMapper,
    target_grid_rectangles,
    wall_bounds_from_homography_data,
)
from trackers.persistent_tracker_v3 import PersistentTrackerV3  # noqa: E402


# ── Colours ───────────────────────────────────────────────────────────────────
BG       = (8, 11, 20)
DIM      = (38, 50, 75)
DIM_TEXT = (60, 80, 110)
ACTIVE   = (28, 215, 95)
HIT_FX   = (55, 235, 110)
MISS_FX  = (215, 40, 40)
WHITE    = (235, 238, 245)
YELLOW   = (255, 228, 35)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _project_path(p: str | Path) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else PROJECT_ROOT / pp


def _load_homography_data(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_homography(path: Path) -> Optional[np.ndarray]:
    data = _load_homography_data(path)
    if data is None:
        return None
    return np.array(data["H"], dtype=np.float64)


def _load_camera_device(cfg_path: Path, role: str) -> Optional[str]:
    if not cfg_path.exists():
        return None
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    return ((cfg.get("cameras") or {}).get(role) or {}).get("device")


def _wall_to_proj(H: np.ndarray, u_mm: float, v_mm: float) -> tuple[int, int]:
    pt = H @ np.array([float(u_mm), float(v_mm), 1.0])
    return int(round(pt[0] / pt[2])), int(round(pt[1] / pt[2]))


def _wall_to_proj_linear(u_mm: float, v_mm: float, pw: int, ph: int) -> tuple[int, int]:
    """Fallback if no homography: linear stretch of wall U/V across the projector."""
    px = int(round(u_mm / SOUTH_WALL_U_MAX_MM * pw))
    py = int(round((1.0 - v_mm / SOUTH_WALL_V_MAX_MM) * ph))
    return px, py


# ── Game state (shared between camera thread and projector thread) ────────────
class GameState:
    def __init__(self, n_rects: int):
        self.lock = threading.Lock()
        self.active_idx = random.randrange(n_rects)
        self.score = 0
        self.misses = 0
        self.flash_t = -999.0
        self.flash_kind = ""   # "hit" or "miss"
        self.flash_px = (0, 0)
        self.last_event: Optional[dict] = None
        self.last_wall_uv: Optional[tuple[float, float]] = None
        self.fps_est = 0.0
        self.det_count = 0
        self._n = n_rects

    def pick_new_active(self) -> None:
        choices = [i for i in range(self._n) if i != self.active_idx]
        self.active_idx = random.choice(choices)


# ── Camera worker ─────────────────────────────────────────────────────────────
def camera_loop(
    cap,
    model,
    tracker,
    mapper: SouthWallMapper,
    rects,
    state: GameState,
    args,
    H_proj: Optional[np.ndarray],
    last_frame: list,
    last_tracks: list,
    running: list,
    goal_log_fp,
) -> None:
    track_state: dict[int, dict] = defaultdict(
        lambda: {
            "last_t": None,
            "last_u": 0.0,
            "last_v": 0.0,
            "speed": 0.0,
            "peak": 0.0,
            "last_goal_t": -math.inf,
        }
    )
    t_prev = time.time()
    while running[0]:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.005)
            continue
        now = time.time()
        dt = max(1e-6, now - t_prev)
        t_prev = now
        state.fps_est = 0.92 * state.fps_est + 0.08 * (1.0 / dt)

        results = model(
            frame,
            conf=args.conf,
            imgsz=args.imgsz,
            classes=[0],
            verbose=False,
            device=args.device,
        )
        dets = []
        for r in results:
            if r.boxes is None:
                continue
            xyxy = r.boxes.xyxy.cpu().numpy()
            cf = r.boxes.conf.cpu().numpy()
            for i in range(len(cf)):
                x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
                side = max(x2 - x1, y2 - y1)
                if args.min_box_side_px > 0 and side < args.min_box_side_px:
                    continue
                if args.max_box_side_px > 0 and side > args.max_box_side_px:
                    continue
                dets.append(
                    {"bbox": np.array([x1, y1, x2, y2], dtype=np.float64),
                     "conf": float(cf[i])}
                )
        state.det_count = len(dets)
        tracks = tracker.update(dets)
        last_frame[0] = frame
        last_tracks[0] = tracks

        for tr in tracks:
            if tr.get("missed", 0) > 0:
                continue
            tid = int(tr["id"])
            cx, cy = [float(v) for v in tr["centroid"]]
            mapped = mapper.pixel_to_wall((cx, cy))
            if mapped is None:
                continue
            u_mm, v_mm, _ = mapped
            state.last_wall_uv = (u_mm, v_mm)

            st = track_state[tid]
            if st["last_t"] is not None:
                ddt = now - st["last_t"]
                if ddt > 1e-6:
                    sp = math.hypot(u_mm - st["last_u"], v_mm - st["last_v"]) / ddt
                    st["speed"] = sp
                    if sp > st["peak"]:
                        st["peak"] = sp
            st["last_t"], st["last_u"], st["last_v"] = now, u_mm, v_mm

            if now - st["last_goal_t"] < args.cooldown_s:
                continue
            if st["peak"] < args.min_flight_speed_mm_s:
                continue
            if st["speed"] > args.decel_ratio * st["peak"]:
                continue

            pad = args.hit_pad_mm
            rect = next(
                (r for r in rects
                 if r.u_min - pad <= u_mm <= r.u_max + pad
                 and r.v_min - pad <= v_mm <= r.v_max + pad),
                None,
            )
            if rect is None:
                continue

            st["last_goal_t"] = now
            st["peak"] = st["speed"]

            if H_proj is not None:
                fx, fy = _wall_to_proj(H_proj, u_mm, v_mm)
            else:
                fx, fy = _wall_to_proj_linear(u_mm, v_mm, args.proj_w, args.proj_h)

            with state.lock:
                is_hit = (rect.label == rects[state.active_idx].label)
                if is_hit:
                    state.score += 1
                    state.flash_kind = "hit"
                    state.pick_new_active()
                else:
                    state.misses += 1
                    state.flash_kind = "miss"
                state.flash_t = now
                state.flash_px = (fx, fy)
                state.last_event = {
                    "t": now,
                    "zone": rect.label,
                    "u_mm": u_mm,
                    "v_mm": v_mm,
                    "speed_mm_s": st["speed"],
                    "peak_speed_mm_s": st["peak"],
                    "track_id": tid,
                    "result": state.flash_kind,
                    "score": state.score,
                    "misses": state.misses,
                }

            if goal_log_fp is not None:
                goal_log_fp.write(json.dumps(state.last_event) + "\n")
                goal_log_fp.flush()

            print(
                f"[{state.flash_kind.upper():4s}] zone={rect.label} "
                f"u={u_mm:6.0f} v={v_mm:6.0f}mm  "
                f"speed={st['speed']:5.0f}/{st['peak']:5.0f} mm/s  "
                f"track={tid}  score={state.score}/{state.misses}"
            )


# ── Projector renderer ────────────────────────────────────────────────────────
def render_loop(
    state: GameState,
    rects,
    args,
    H_proj: Optional[np.ndarray],
    mapper: SouthWallMapper,
    last_frame: list,
    last_tracks: list,
    running: list,
) -> None:
    import pygame
    screen = pygame.display.set_mode((args.proj_w, args.proj_h))
    pygame.display.set_caption("Projector Goal Game — south wall")
    clock = pygame.time.Clock()

    font_zone  = pygame.font.SysFont("arial", 120, bold=True)
    font_zone2 = pygame.font.SysFont("arial", 80,  bold=True)
    font_big   = pygame.font.SysFont("arial", 90,  bold=True)
    font_hud   = pygame.font.SysFont("arial", 36,  bold=True)
    font_small = pygame.font.SysFont("arial", 22)

    def w2p(u, v):
        if H_proj is not None:
            return _wall_to_proj(H_proj, u, v)
        return _wall_to_proj_linear(u, v, args.proj_w, args.proj_h)

    while running[0]:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running[0] = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                    running[0] = False
                elif ev.key == pygame.K_r:
                    with state.lock:
                        state.score = 0
                        state.misses = 0
                        state.pick_new_active()
                elif ev.key == pygame.K_n:
                    with state.lock:
                        state.pick_new_active()
                elif ev.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()

        now = time.time()
        screen.fill(BG)

        with state.lock:
            ai = state.active_idx
            sc, ms = state.score, state.misses
            ft, fk, fp = state.flash_t, state.flash_kind, state.flash_px

        for i, rect in enumerate(rects):
            p0 = w2p(rect.u_min, rect.v_min)
            p1 = w2p(rect.u_max, rect.v_max)
            x0, y0 = min(p0[0], p1[0]), min(p0[1], p1[1])
            w = abs(p1[0] - p0[0])
            h = abs(p1[1] - p0[1])
            pr = pygame.Rect(x0, y0, w, h)
            if i == ai:
                pulse = (math.sin(now * 4 * math.pi) + 1) / 2
                fill_a = int(35 + 55 * pulse)
                s = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
                s.fill((*ACTIVE, fill_a))
                screen.blit(s, pr.topleft)
                pygame.draw.rect(screen, ACTIVE, pr, 6)
                fnt = font_zone if w > 240 else font_zone2
                lbl = fnt.render(rect.label, True, ACTIVE)
            else:
                pygame.draw.rect(screen, DIM, pr, 2)
                fnt = font_zone if w > 240 else font_zone2
                lbl = fnt.render(rect.label, True, DIM_TEXT)
            screen.blit(
                lbl,
                (pr.centerx - lbl.get_width() // 2,
                 pr.centery - lbl.get_height() // 2),
            )

        age = now - ft
        if age < 0.7 and fk:
            frac = age / 0.7
            color = HIT_FX if fk == "hit" else MISS_FX
            r = int(80 + 240 * frac)
            a = int(220 * (1 - frac))
            s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*color, a), (r + 1, r + 1), r, 6)
            screen.blit(s, (fp[0] - r - 1, fp[1] - r - 1))
            txt = "HIT!" if fk == "hit" else "MISS"
            big = font_big.render(txt, True, color)
            big_s = pygame.Surface(big.get_size(), pygame.SRCALPHA)
            big_s.blit(big, (0, 0))
            big_s.set_alpha(int(255 * (1 - frac)))
            screen.blit(big_s, (fp[0] - big.get_width() // 2, fp[1] - 150))

        hud_h = 70
        hud_y = args.proj_h - hud_h
        hud_bg = pygame.Surface((args.proj_w, hud_h), pygame.SRCALPHA)
        hud_bg.fill((0, 0, 0, 200))
        screen.blit(hud_bg, (0, hud_y))

        score_txt = font_hud.render(f"SCORE  {sc}", True, HIT_FX)
        miss_txt  = font_hud.render(f"MISS  {ms}",  True, MISS_FX)
        screen.blit(score_txt, (40, hud_y + 16))
        screen.blit(miss_txt, (40 + score_txt.get_width() + 60, hud_y + 16))
        zone_txt = font_hud.render(f"TARGET → {rects[ai].label}", True, ACTIVE)
        screen.blit(zone_txt,
                    (args.proj_w // 2 - zone_txt.get_width() // 2, hud_y + 16))
        fps_txt = font_small.render(
            f"{state.fps_est:4.1f} FPS   det={state.det_count}",
            True, WHITE,
        )
        screen.blit(fps_txt,
                    (args.proj_w - fps_txt.get_width() - 20, hud_y + 24))

        keys_txt = font_small.render(
            "  N: new target    R: reset    F: fullscreen    Q/ESC: quit",
            True, (140, 150, 175),
        )
        screen.blit(keys_txt, (20, 12))

        pygame.display.flip()

        if args.show_debug and last_frame[0] is not None:
            preview = last_frame[0].copy()
            for i, rect in enumerate(rects):
                pts = np.array(
                    [
                        mapper.wall_to_pixel(rect.u_min, rect.v_min),
                        mapper.wall_to_pixel(rect.u_max, rect.v_min),
                        mapper.wall_to_pixel(rect.u_max, rect.v_max),
                        mapper.wall_to_pixel(rect.u_min, rect.v_max),
                    ],
                    dtype=np.int32,
                )
                col = (0, 240, 80) if i == ai else (80, 180, 255)
                cv2.polylines(preview, [pts], True, col, 2)
                cu, cv = rect.center
                tx, ty = mapper.wall_to_pixel(cu, cv)
                cv2.putText(preview, rect.label, (tx - 16, ty + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
            for tr in last_tracks[0]:
                if tr.get("missed", 0) > 0:
                    continue
                cx, cy = [int(round(v)) for v in tr["centroid"]]
                x1, y1, x2, y2 = [int(round(v)) for v in tr["bbox"]]
                cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 230, 90), 2)
                cv2.circle(preview, (cx, cy), 5, (0, 255, 255), -1)
            ph, pw = preview.shape[:2]
            scale = 720 / pw
            small = cv2.resize(preview, (720, int(ph * scale)))
            with state.lock:
                uv = state.last_wall_uv
            if uv is not None:
                cv2.putText(small, f"U={uv[0]:6.0f} V={uv[1]:6.0f}mm",
                            (10, small.shape[0] - 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                            (200, 220, 255), 1)
            cv2.imshow("camNorth debug", small)
            cv2.waitKey(1)

        clock.tick(60)

    pygame.quit()


# ── Entry ─────────────────────────────────────────────────────────────────────
def build_arg_parser() -> argparse.ArgumentParser:
    default_model = PROJECT_ROOT / "models/ball/yolo26m-672.engine"
    if not default_model.exists():
        default_model = PROJECT_ROOT / "models/ball/yolo26m-672.pt"

    ap = argparse.ArgumentParser(
        description="Footbonaut-style projector goal game (camNorth + south wall)."
    )
    ap.add_argument("--cam-role", default="camNorth")
    ap.add_argument("--camera", default=None,
                    help="Override camera device. Default from cameras.yaml.")
    ap.add_argument("--camera-config",
                    default="garage_lab_combined/config/cameras.yaml")
    ap.add_argument("--intrinsics",
                    default="Remounted_West_East/cal/intrinsics/camNorth_intrinsics.json")
    ap.add_argument("--extrinsics",
                    default="Remounted_West_East/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--homography", default=str(PROJECTOR_DIR / "homography.json"),
                    help="Wall-mm → projector-px calibration JSON.")
    ap.add_argument("--model", default=str(default_model))
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--imgsz", type=int, default=672)

    ap.add_argument("--width",  type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps",    type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG")

    ap.add_argument("--proj-w", type=int, default=1920)
    ap.add_argument("--proj-h", type=int, default=1080)
    ap.add_argument("--proj-pos", default="1920,0",
                    help="X,Y position of projector window (top-left).")

    ap.add_argument("--min-flight-speed-mm-s", type=float, default=1500.0)
    ap.add_argument("--decel-ratio",  type=float, default=0.40)
    ap.add_argument("--hit-pad-mm",   type=float, default=80.0)
    ap.add_argument("--cooldown-s",   type=float, default=0.8)

    ap.add_argument("--max-box-side-px", type=float, default=120.0)
    ap.add_argument("--min-box-side-px", type=float, default=0.0)
    ap.add_argument("--reid-gate-px",    type=float, default=180.0)
    ap.add_argument("--jitter-thresh-px", type=float, default=3.0)
    ap.add_argument("--max-missed-frames", type=int, default=6)

    ap.add_argument("--show-debug", action="store_true",
                    help="Show small camera preview window on primary screen.")
    ap.add_argument("--goal-log-jsonl", default="")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()

    intrinsics_path = _project_path(args.intrinsics)
    extrinsics_path = _project_path(args.extrinsics)
    homography_path = _project_path(args.homography)
    model_path      = _project_path(args.model)
    if not intrinsics_path.exists():
        print(f"[ERROR] Intrinsics not found: {intrinsics_path}")
        return 2
    if not extrinsics_path.exists():
        print(f"[ERROR] Extrinsics not found: {extrinsics_path}")
        return 2
    if not model_path.exists():
        print(f"[ERROR] Ball model not found: {model_path}")
        return 2

    homography_data = _load_homography_data(homography_path)
    H_proj = (
        None if homography_data is None
        else np.array(homography_data["H"], dtype=np.float64)
    )
    if homography_data is None:
        print(f"[WARN] Homography missing at {homography_path}; using linear stretch.")
    else:
        print(f"[CAL] Loaded projector homography from {homography_path}")
        src_w = int(homography_data.get("proj_w", 0) or 0)
        src_h = int(homography_data.get("proj_h", 0) or 0)
        if src_w and src_h and (src_w, src_h) != (args.proj_w, args.proj_h):
            print(
                "[WARN] Homography metadata says "
                f"{src_w}x{src_h}, current projector is "
                f"{args.proj_w}x{args.proj_h}; recalibrate if the grid "
                "does not line up physically."
            )

    mapper = SouthWallMapper.from_files(
        intrinsics_path, extrinsics_path, cam_role=args.cam_role
    )
    bounds = (
        None if homography_data is None
        else wall_bounds_from_homography_data(homography_data)
    )
    if bounds is None:
        rects = target_grid_rectangles(SOUTH_WALL_U_MAX_MM, SOUTH_WALL_V_MAX_MM)
        print("[WARN] Grid using full south wall bounds.")
    else:
        rects = target_grid_rectangles(
            u_min=bounds.u_min,
            u_max=bounds.u_max,
            v_min=bounds.v_min,
            v_max=bounds.v_max,
        )
        print(
            "[CAL] Grid wall bounds from homography: "
            f"U={bounds.u_min:.0f}..{bounds.u_max:.0f}mm "
            f"V={bounds.v_min:.0f}..{bounds.v_max:.0f}mm"
        )

    cam_src = args.camera or _load_camera_device(
        _project_path(args.camera_config), args.cam_role
    )
    if cam_src is None:
        print("[ERROR] No camera device — provide --camera or fix cameras.yaml")
        return 2

    cap = cv2.VideoCapture(cam_src)
    if not cap.isOpened() and isinstance(cam_src, str) and cam_src.isdigit():
        cap = cv2.VideoCapture(int(cam_src))
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {cam_src}")
        return 2
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*args.fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM] {args.cam_role}: {cam_src} -> {actual_w}x{actual_h}")
    if (actual_w, actual_h) != (args.width, args.height):
        print(f"[WARN] Capture size {actual_w}x{actual_h} differs from requested "
              f"{args.width}x{args.height}; wall mapping may drift.")

    from ultralytics import YOLO
    print(f"[MODEL] Loading {model_path}")
    model = YOLO(str(model_path))
    print("[MODEL] Ready")

    tracker = PersistentTrackerV3({
        "jitter_thresh":     args.jitter_thresh_px,
        "reid_gate_px":      args.reid_gate_px,
        "max_missed_frames": args.max_missed_frames,
    })

    goal_log_fp = None
    if args.goal_log_jsonl:
        p = _project_path(args.goal_log_jsonl)
        p.parent.mkdir(parents=True, exist_ok=True)
        goal_log_fp = p.open("a", encoding="utf-8")

    # Position the SDL window before pygame.init
    pos = args.proj_pos.replace(" ", "")
    if "," in pos:
        os.environ["SDL_VIDEO_WINDOW_POS"] = pos

    import pygame
    pygame.init()

    state = GameState(n_rects=len(rects))
    running = [True]
    last_frame: list = [None]
    last_tracks: list = [[]]

    cam_thread = threading.Thread(
        target=camera_loop,
        args=(cap, model, tracker, mapper, rects, state, args,
              H_proj, last_frame, last_tracks, running, goal_log_fp),
        daemon=True,
    )
    cam_thread.start()

    try:
        render_loop(state, rects, args, H_proj, mapper,
                    last_frame, last_tracks, running)
    except KeyboardInterrupt:
        pass
    finally:
        running[0] = False
        cam_thread.join(timeout=2.0)
        cap.release()
        cv2.destroyAllWindows()
        if goal_log_fp is not None:
            goal_log_fp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
