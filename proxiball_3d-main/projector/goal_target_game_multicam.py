#!/usr/bin/env python3
"""
goal_target_game_multicam.py — Footbonaut-style projector game, 4-cam edition.

Architecture
------------
- 4 threaded camera captures (camEast, camNorth, camSouth, camWest by default).
- One shared YOLO model running per-camera per-tick.
- Multi-cam triangulation -> 3D ball position (mm).
- Per-axis Kalman filter (constant velocity) for trajectory continuity.
- "Hit" = 3D ball trajectory crosses south-wall plane (X = 6230 mm).
- Crossing (y_mm, z_mm) -> 3x3 grid zone. Active zone -> HIT, other zone -> MISS.

Display
-------
- Projector (DP-1-2, pygame window): the 3x3 target grid, calibrated via
  homography.json so projected rectangles align with the camera-measured zones.
- PC monitor (HDMI-1-0, cv2 window): 2x2 camera tile + active-target banner +
  score/miss HUD + per-cam detection overlay. This is what the operator sees.

Run
---
  ./proxiball_3d-main/projector/run_goal_target_multicam.sh
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

PROJECTOR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PROJECTOR_DIR.parents[1]
sys.path.insert(0, str(PROJECTOR_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "Parallel_working" / "scripts"))

# Helpers from the existing live viewer (no copy — direct import).
from live_4cam_arena_view_parallel import (  # noqa: E402
    JointKalmanFilter,
    ThreadedCapture,
    apply_uvc_low_latency_controls,
    load_cameras,
    load_extrinsics,
    load_intrinsics,
    open_camera_capture,
    project_world_to_pixel,
    robust_triangulate_ball,
    scale_intrinsics_matrix,
    select_ball_box_for_cam,
)

# Grid + south-wall mapping helpers.
from static_grid_goal_logic import (  # noqa: E402
    SOUTH_WALL_U_MAX_MM,
    SOUTH_WALL_V_MAX_MM,
    SOUTH_WALL_X_MM,
    SouthWallMapper,
    consensus_zone_from_wall_uv,
    target_grid_rectangles,
    temporal_consensus_zone,
    wall_bounds_from_homography_data,
    zone_votes_from_wall_uv,
)


# ── Colours ──────────────────────────────────────────────────────────────────
BG       = (8, 11, 20)
DIM      = (38, 50, 75)
DIM_TEXT = (60, 80, 110)
ACTIVE   = (28, 215, 95)
HIT_FX   = (55, 235, 110)
MISS_FX  = (215, 40, 40)
WHITE    = (235, 238, 245)


# ── Helpers ──────────────────────────────────────────────────────────────────
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


def _wall_to_proj(H: np.ndarray, u_mm: float, v_mm: float) -> tuple[int, int]:
    pt = H @ np.array([float(u_mm), float(v_mm), 1.0])
    return int(round(pt[0] / pt[2])), int(round(pt[1] / pt[2]))


def _wall_to_proj_linear(u_mm: float, v_mm: float, pw: int, ph: int) -> tuple[int, int]:
    px = int(round(u_mm / SOUTH_WALL_U_MAX_MM * pw))
    py = int(round((1.0 - v_mm / SOUTH_WALL_V_MAX_MM) * ph))
    return px, py


def _xrandr_output_geometry(output_name: str) -> Optional[tuple[int, int, int, int]]:
    if not output_name:
        return None
    try:
        proc = subprocess.run(
            ["xrandr", "--query"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    pattern = re.compile(
        rf"^{re.escape(output_name)}\s+connected(?:\s+primary)?\s+"
        r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)"
    )
    for line in proc.stdout.splitlines():
        m = pattern.search(line)
        if m:
            w, h, x, y = [int(v) for v in m.groups()]
            return x, y, w, h
    return None


# ── Game state shared between camera thread and render thread ────────────────
class GameState:
    def __init__(self, n_rects: int):
        self.lock = threading.Lock()
        self.active_idx = random.randrange(n_rects)
        self.score = 0
        self.misses = 0
        self.flash_t = -999.0
        self.flash_kind = ""    # "hit" or "miss"
        self.flash_px = (0, 0)   # projector pixel coords
        self.last_event: Optional[dict] = None
        self.last_wall_uv: Optional[tuple[float, float]] = None
        self.ball_world: Optional[np.ndarray] = None      # current 3D ball
        self.last_used_cams: list[str] = []
        self.last_reproj_err: Optional[float] = None
        self.last_per_cam_wall_uv: dict[str, tuple[float, float]] = {}
        self.last_per_cam_zones: dict[str, str | None] = {}
        self.last_zone_votes: dict[str, tuple[str, ...]] = {}
        self.last_no_hit_reason = "startup"
        self.fps_est = 0.0
        self.det_count = 0
        self._n = n_rects

    def pick_new_active(self) -> None:
        choices = [i for i in range(self._n) if i != self.active_idx]
        self.active_idx = random.choice(choices)


# ── Capture setup ────────────────────────────────────────────────────────────
def open_capture(device: str, width: int, height: int, fps: int, fourcc: str, args, cam: str):
    apply_uvc_low_latency_controls(device, cam, args, log=False)
    cap = open_camera_capture(device)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
    cap.set(cv2.CAP_PROP_FPS, int(fps))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    apply_uvc_low_latency_controls(device, cam, args, log=True)
    return cap


# ── YOLO + per-cam picker ────────────────────────────────────────────────────
def yolo_pick_per_cam(
    model,
    frames: dict[str, np.ndarray],
    args,
    kf_preds: dict[str, Optional[tuple[float, float]]],
) -> dict[str, tuple[float, float, float, float, float]]:
    """Run YOLO once on a batch of frames and return one bbox per cam."""
    cams = list(frames.keys())
    batch = [frames[c] for c in cams]
    results = model(
        batch,
        conf=args.ball_conf,
        imgsz=args.ball_imgsz,
        classes=[0],
        verbose=False,
        device=args.device,
    )
    out: dict[str, tuple[float, float, float, float, float]] = {}
    for cam, res in zip(cams, results):
        if res.boxes is None:
            continue
        xyxy = res.boxes.xyxy.cpu().numpy()
        cf = res.boxes.conf.cpu().numpy()
        boxes = []
        for i in range(len(cf)):
            x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
            boxes.append((x1, y1, x2, y2, float(cf[i])))
        pick = select_ball_box_for_cam(
            boxes,
            kf_preds.get(cam),
            args.ball_kf_gate_px,
            args.min_box_side_px,
            args.max_box_side_px,
        )
        if pick is not None:
            out[cam] = pick
    return out


# ── Camera thread ────────────────────────────────────────────────────────────
def camera_loop(
    captures: dict[str, ThreadedCapture],
    cam_order: list[str],
    intrinsics: dict[str, dict],
    extrinsics: dict[str, dict],
    proj_mats: dict[str, np.ndarray],
    mappers: dict[str, SouthWallMapper],
    rects,
    args,
    state: GameState,
    H_proj: Optional[np.ndarray],
    shared: dict,
    running: list[bool],
    goal_log_fp,
    debug_log_fp,
) -> None:
    from ultralytics import YOLO
    print(f"[MODEL] Loading {args.model}")
    model = YOLO(args.model)
    print("[MODEL] Ready")

    ball_kf = JointKalmanFilter(
        process_noise=args.kalman_process_noise,
        measurement_noise=args.kalman_measurement_noise,
        dt=1.0 / max(1.0, args.fps),
    )
    last_kf_t: Optional[float] = None
    last_hit_t = -math.inf

    # Track the previous RAW triangulated position for wall-crossing detection.
    # KF-smoothed state lags too much for a single-frame wall touch.
    prev_raw_pos: Optional[np.ndarray] = None
    prev_raw_t: Optional[float] = None

    # Rolling diagnostics so --debug can print a useful summary per second.
    dbg_last_print = 0.0
    dbg_det_per_cam: dict[str, int] = {c: 0 for c in cam_order}
    dbg_frames = 0
    dbg_tri_ok = 0
    dbg_x_min = float("inf")
    dbg_x_max = float("-inf")
    dbg_last_xyz: Optional[np.ndarray] = None
    vote_history: deque[tuple[float, str, str, float, float]] = deque()

    fps_dt = deque(maxlen=30)
    t_prev = time.time()

    while running[0]:
        # Gather a fresh frame from each cam.
        frames: dict[str, np.ndarray] = {}
        for cam in cam_order:
            ok, fr, _ts = captures[cam].read_latest()
            if ok and fr is not None:
                frames[cam] = fr
        if len(frames) < 2:
            time.sleep(0.005)
            continue

        now = time.time()
        dt = max(1e-6, now - t_prev)
        t_prev = now
        fps_dt.append(dt)
        state.fps_est = 1.0 / (sum(fps_dt) / len(fps_dt))

        # KF predicted reprojection per cam (for the per-cam KF gate).
        kf_preds: dict[str, Optional[tuple[float, float]]] = {c: None for c in frames}
        if ball_kf.initialized:
            pred_pos = ball_kf.predict_ahead(0.0)
            for cam in frames:
                try:
                    uv = project_world_to_pixel(
                        pred_pos,
                        extrinsics[cam]["R"], extrinsics[cam]["tvec"],
                        intrinsics[cam]["K"], intrinsics[cam]["D"],
                    )
                    if np.isfinite(uv).all():
                        kf_preds[cam] = (float(uv[0]), float(uv[1]))
                except Exception:
                    pass

        # YOLO + per-cam pick.
        picks = yolo_pick_per_cam(model, frames, args, kf_preds)
        state.det_count = len(picks)
        dbg_frames += 1
        for c in picks:
            dbg_det_per_cam[c] = dbg_det_per_cam.get(c, 0) + 1

        # Triangulate.
        ball_3d = None
        used_cams: list[str] = []
        reproj_err: Optional[float] = None
        obs_px: dict[str, np.ndarray] = {}
        if len(picks) >= 2:
            obs_px = {c: np.array([0.5 * (b[0] + b[2]), 0.5 * (b[1] + b[3])])
                      for c, b in picks.items()}
            obs_norm: dict[str, np.ndarray] = {}
            for cam in picks:
                und = cv2.undistortPoints(
                    np.array([[obs_px[cam]]], dtype=np.float64),
                    intrinsics[cam]["K"], intrinsics[cam]["D"],
                )
                obs_norm[cam] = und.reshape(2)
            ball_3d, used_cams, reproj_err = robust_triangulate_ball(
                obs_norm, obs_px, proj_mats, extrinsics, intrinsics,
                min_cams=2, max_reproj_px=args.ball_max_reproj_px,
            )
            if ball_3d is not None and np.isfinite(ball_3d).all():
                dbg_tri_ok += 1
                dbg_last_xyz = ball_3d.copy()
                bx = float(ball_3d[0])
                if bx < dbg_x_min:
                    dbg_x_min = bx
                if bx > dbg_x_max:
                    dbg_x_max = bx

        # KF predict step forward to `now`.
        if last_kf_t is not None:
            kf_dt = max(1e-3, now - last_kf_t)
            ball_kf.predict_step(dt=kf_dt)
        last_kf_t = now

        # Update with this tick's triangulation (if any).
        state.last_used_cams = used_cams
        state.last_reproj_err = reproj_err
        if ball_3d is not None and np.isfinite(ball_3d).all():
            ball_kf.update_step(ball_3d)
            state.ball_world = ball_3d

        # ── Consensus-voting hit detection ───────────────────────────────────
        # Each cam independently maps its detection through the south-wall
        # plane (ray-plane intersection). If the ball is physically AT the
        # wall, every cam's ray hits the same (Y, Z) → zone votes converge.
        # If the ball is mid-flight, each cam's ray hits the plane at a
        # different (Y, Z) → no zone gets enough votes.  This sidesteps the
        # async frame-time + reproj-gate failure modes of 3D triangulation.
        per_cam_wall_uv: dict[str, tuple[float, float]] = {}
        wall_projection_failed: list[str] = []
        for cam, box in picks.items():
            cx = 0.5 * (box[0] + box[2])
            cy = 0.5 * (box[1] + box[3])
            mapped = mappers[cam].pixel_to_wall((cx, cy))
            if mapped is None:
                wall_projection_failed.append(cam)
                continue
            u_mm, v_mm, _ = mapped
            per_cam_wall_uv[cam] = (u_mm, v_mm)

        zone_votes, per_cam_zones = zone_votes_from_wall_uv(
            rects,
            per_cam_wall_uv,
            pad_mm=args.consensus_pad_mm,
        )
        frame_consensus = consensus_zone_from_wall_uv(
            rects,
            per_cam_wall_uv,
            min_cams=args.min_consensus_cams,
            pad_mm=args.consensus_pad_mm,
        )
        for cam, zone_label in per_cam_zones.items():
            if zone_label is None:
                continue
            u_mm, v_mm = per_cam_wall_uv[cam]
            vote_history.append((now, cam, zone_label, u_mm, v_mm))
        while vote_history and now - vote_history[0][0] > args.consensus_window_s:
            vote_history.popleft()
        temporal_consensus = temporal_consensus_zone(
            vote_history,
            now=now,
            window_s=args.consensus_window_s,
            min_cams=args.min_consensus_cams,
        )
        consensus = frame_consensus or temporal_consensus
        consensus_source = (
            "frame-consensus" if frame_consensus is not None
            else "temporal-consensus" if temporal_consensus is not None
            else ""
        )

        crossing = None
        crossing_zone: Optional[str] = None
        crossing_cams: list[str] = []
        if consensus is not None:
            crossing_zone = consensus.zone_label
            crossing_cams = list(consensus.voting_cams)
            crossing = np.array(
                [args.wall_x_mm, consensus.u_mm, consensus.v_mm],
                dtype=np.float64,
            )

        if consensus is not None and now - last_hit_t < args.cooldown_s:
            no_hit_reason = "cooldown"
        elif consensus is not None:
            no_hit_reason = "consensus-ready"
        elif not picks:
            no_hit_reason = "no-ball-detections"
        elif not per_cam_wall_uv:
            no_hit_reason = "wall-projection-failed"
        else:
            no_hit_reason = "no-consensus"

        with state.lock:
            state.last_per_cam_wall_uv = dict(per_cam_wall_uv)
            state.last_per_cam_zones = dict(per_cam_zones)
            state.last_zone_votes = dict(zone_votes)
            state.last_no_hit_reason = no_hit_reason

        # Keep triangulation result (when it exists) for diagnostic display
        # but no longer required for hit decision.
        if ball_3d is not None and np.isfinite(ball_3d).all():
            prev_raw_pos = ball_3d.copy()
            prev_raw_t = now

        # Debug printout once per --debug-print-period-s.
        if args.debug and (now - dbg_last_print) >= args.debug_print_period_s:
            det_str = " ".join(f"{c}={dbg_det_per_cam.get(c, 0)}" for c in cam_order)
            xmin = "--" if dbg_x_min == float("inf") else f"{dbg_x_min:6.0f}"
            xmax = "--" if dbg_x_max == float("-inf") else f"{dbg_x_max:6.0f}"
            xyz_str = (
                f"xyz=({dbg_last_xyz[0]:6.0f},{dbg_last_xyz[1]:6.0f},{dbg_last_xyz[2]:6.0f})"
                if dbg_last_xyz is not None else "xyz=--"
            )
            vote_str = ", ".join(
                f"{lbl}={len(cams)}" for lbl, cams in zone_votes.items()
            ) or "no-zone-votes"
            if temporal_consensus is not None and frame_consensus is None:
                vote_str = (
                    f"{temporal_consensus.zone_label}="
                    f"{len(temporal_consensus.voting_cams)} temporal"
                )
            per_cam_str = "  ".join(
                f"{c}:({u:5.0f},{v:5.0f})/{per_cam_zones.get(c) or '--'}"
                for c, (u, v) in per_cam_wall_uv.items()
            ) or "no-wall-uv"
            print(
                f"[DBG] frames={dbg_frames:3d}  "
                f"per-cam det: {det_str}  "
                f"triangulations={dbg_tri_ok:3d}  "
                f"X range=[{xmin}..{xmax}]mm "
                f"(wall={args.wall_x_mm:.0f}±{args.wall_x_tolerance_mm:.0f})  "
                f"{xyz_str}"
            )
            print(
                f"[VOTE] {vote_str}  reason={no_hit_reason}  "
                f"per-cam UV: {per_cam_str}"
            )
            dbg_last_print = now
            dbg_frames = 0
            dbg_tri_ok = 0
            dbg_x_min = float("inf")
            dbg_x_max = float("-inf")
            for c in dbg_det_per_cam:
                dbg_det_per_cam[c] = 0

        # Crossing handler (consensus-driven).
        if crossing is not None and now - last_hit_t >= args.cooldown_s:
            u_mm = float(crossing[1])
            v_mm = float(crossing[2])
            state.last_wall_uv = (u_mm, v_mm)
            last_hit_t = now
            if H_proj is not None:
                fx, fy = _wall_to_proj(H_proj, u_mm, v_mm)
            else:
                fx, fy = _wall_to_proj_linear(
                    u_mm, v_mm, args.proj_w, args.proj_h
                )
            speed = (float(np.linalg.norm(ball_kf.get_velocity()))
                     if ball_kf.initialized else 0.0)
            with state.lock:
                is_hit = (crossing_zone == rects[state.active_idx].label)
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
                    "zone": crossing_zone,
                    "u_mm": u_mm,
                    "v_mm": v_mm,
                    "speed_mm_s": speed,
                    "result": state.flash_kind,
                    "score": state.score,
                    "misses": state.misses,
                    "voting_cams": crossing_cams,
                    "decision_source": consensus_source,
                    "zone_votes": {
                        label: list(cams)
                        for label, cams in zone_votes.items()
                    },
                    "per_cam_zones": per_cam_zones,
                    "tri_used_cams": used_cams,
                    "tri_reproj_err_px": (None if reproj_err is None
                                          else float(reproj_err)),
                    "tri_xyz_mm": (None if ball_3d is None
                                   else [float(v) for v in ball_3d]),
                }
            if goal_log_fp is not None:
                goal_log_fp.write(json.dumps(state.last_event) + "\n")
                goal_log_fp.flush()
            print(
                f"[{state.flash_kind.upper():4s}] zone={crossing_zone} "
                f"u={u_mm:6.0f} v={v_mm:6.0f}mm  "
                f"voted-by={crossing_cams}  speed={speed:5.0f}mm/s  "
                f"score={state.score}/{state.misses}"
            )
        if debug_log_fp is not None:
            debug_log_fp.write(
                json.dumps(
                    {
                        "t": now,
                        "detections": {
                            cam: [float(v) for v in box]
                            for cam, box in picks.items()
                        },
                        "wall_uv": {
                            cam: [float(uv[0]), float(uv[1])]
                            for cam, uv in per_cam_wall_uv.items()
                        },
                        "wall_projection_failed": wall_projection_failed,
                        "per_cam_zones": per_cam_zones,
                        "zone_votes": {
                            label: list(cams)
                            for label, cams in zone_votes.items()
                        },
                        "consensus_zone": crossing_zone,
                        "consensus_cams": crossing_cams,
                        "consensus_source": consensus_source,
                        "temporal_vote_count": len(vote_history),
                        "no_hit_reason": no_hit_reason,
                        "tri_used_cams": used_cams,
                        "tri_reproj_err_px": (
                            None if reproj_err is None else float(reproj_err)
                        ),
                        "tri_xyz_mm": (
                            None if ball_3d is None
                            else [float(v) for v in ball_3d]
                        ),
                    }
                )
                + "\n"
            )
            debug_log_fp.flush()

        # Publish per-cam state for cv2 renderer.
        with shared["lock"]:
            shared["frames"] = frames
            shared["picks"] = picks
            shared["kf_preds"] = kf_preds


# ── Pygame renderer (projector) ──────────────────────────────────────────────
def render_projector(
    state: GameState,
    rects,
    args,
    H_proj: Optional[np.ndarray],
    running: list[bool],
) -> None:
    import pygame

    proj_w = int(args.proj_w)
    proj_h = int(args.proj_h)
    projector_display_arg = args.projector_display
    force_projector_output = False
    geom = _xrandr_output_geometry(args.projector_output)
    if geom is not None:
        gx, gy, gw, gh = geom
        args.proj_pos = f"{gx},{gy}"
        proj_w, proj_h = gw, gh
        force_projector_output = True
        print(
            f"[DISP] projector output {args.projector_output}: "
            f"{proj_w}x{proj_h}+{gx}+{gy}"
        )
    elif args.projector_output:
        print(
            f"[WARN] xrandr output {args.projector_output!r} not found; "
            "falling back to --proj-pos/--projector-display."
        )

    # Position the SDL window before init so it lands on the projector display.
    pos = args.proj_pos.replace(" ", "")
    if "," in pos:
        os.environ["SDL_VIDEO_WINDOW_POS"] = pos
    os.environ.pop("SDL_VIDEO_CENTERED", None)

    pygame.init()

    # Auto-detect projector display if requested.
    target_display = 0
    use_display_arg = True
    if projector_display_arg == "auto":
        try:
            sizes = pygame.display.get_desktop_sizes()
            for i, (w, h) in enumerate(sizes):
                if (w, h) == (proj_w, proj_h):
                    target_display = i
                    break
            else:
                target_display = 1 if len(sizes) > 1 else 0
        except Exception:
            target_display = 1
    else:
        target_display = int(projector_display_arg)

    target_desc = f"display index {target_display}"
    if force_projector_output:
        target_desc += f" at {args.proj_pos}"

    def open_projector_screen(reason: str):
        if "," in pos:
            os.environ["SDL_VIDEO_WINDOW_POS"] = pos
        flags = pygame.RESIZABLE
        try:
            if use_display_arg:
                new_screen = pygame.display.set_mode(
                    (proj_w, proj_h), flags, display=target_display
                )
            else:
                new_screen = pygame.display.set_mode((proj_w, proj_h), flags)
        except TypeError:
            new_screen = pygame.display.set_mode((proj_w, proj_h), flags)
        pygame.display.set_caption("Projector goal game")
        print(
            f"[DISP] pygame {reason}: target={target_desc}, "
            f"size={proj_w}x{proj_h}, flags={flags}"
        )
        return new_screen

    screen = open_projector_screen("startup")

    pygame.display.set_caption("Projector goal game")
    clock = pygame.time.Clock()

    font_zone  = pygame.font.SysFont("arial", 140, bold=True)
    font_zone2 = pygame.font.SysFont("arial", 90,  bold=True)
    font_big   = pygame.font.SysFont("arial", 100, bold=True)
    font_hud   = pygame.font.SysFont("arial", 36,  bold=True)
    font_small = pygame.font.SysFont("arial", 22)

    def w2p(u, v):
        if H_proj is not None:
            return _wall_to_proj(H_proj, u, v)
        return _wall_to_proj_linear(u, v, proj_w, proj_h)

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

        now = time.time()
        screen.fill(BG)

        with state.lock:
            ai = state.active_idx
            sc, ms = state.score, state.misses
            ft, fk, fp = state.flash_t, state.flash_kind, state.flash_px

        # 3x3 grid.
        for i, rect in enumerate(rects):
            p0 = w2p(rect.u_min, rect.v_min)
            p1 = w2p(rect.u_max, rect.v_max)
            x0, y0 = min(p0[0], p1[0]), min(p0[1], p1[1])
            w = max(1, abs(p1[0] - p0[0]))
            h = max(1, abs(p1[1] - p0[1]))
            pr_rect = pygame.Rect(x0, y0, w, h)
            if i == ai:
                pulse = (math.sin(now * 4 * math.pi) + 1) / 2
                fill_a = int(35 + 55 * pulse)
                s = pygame.Surface((w, h), pygame.SRCALPHA)
                s.fill((*ACTIVE, fill_a))
                screen.blit(s, pr_rect.topleft)
                pygame.draw.rect(screen, ACTIVE, pr_rect, 6)
                fnt = font_zone if w > 240 else font_zone2
                lbl = fnt.render(rect.label, True, ACTIVE)
            else:
                pygame.draw.rect(screen, DIM, pr_rect, 2)
                fnt = font_zone if w > 240 else font_zone2
                lbl = fnt.render(rect.label, True, DIM_TEXT)
            screen.blit(
                lbl,
                (pr_rect.centerx - lbl.get_width() // 2,
                 pr_rect.centery - lbl.get_height() // 2),
            )

        # Hit / miss flash.
        age = now - ft
        if age < 0.7 and fk:
            frac = age / 0.7
            color = HIT_FX if fk == "hit" else MISS_FX
            r = int(80 + 280 * frac)
            a = int(220 * (1 - frac))
            s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*color, a), (r + 1, r + 1), r, 6)
            screen.blit(s, (fp[0] - r - 1, fp[1] - r - 1))
            txt = "HIT!" if fk == "hit" else "MISS"
            big = font_big.render(txt, True, color)
            big_s = pygame.Surface(big.get_size(), pygame.SRCALPHA)
            big_s.blit(big, (0, 0))
            big_s.set_alpha(int(255 * (1 - frac)))
            screen.blit(big_s, (fp[0] - big.get_width() // 2, fp[1] - 170))

        # Bottom HUD.
        hud_h = 70
        hud_y = proj_h - hud_h
        hud_bg = pygame.Surface((proj_w, hud_h), pygame.SRCALPHA)
        hud_bg.fill((0, 0, 0, 200))
        screen.blit(hud_bg, (0, hud_y))

        score_txt = font_hud.render(f"SCORE  {sc}", True, HIT_FX)
        miss_txt  = font_hud.render(f"MISS  {ms}",  True, MISS_FX)
        screen.blit(score_txt, (40, hud_y + 16))
        screen.blit(miss_txt, (40 + score_txt.get_width() + 60, hud_y + 16))
        zone_txt = font_hud.render(f"TARGET -> {rects[ai].label}", True, ACTIVE)
        screen.blit(zone_txt,
                    (proj_w // 2 - zone_txt.get_width() // 2, hud_y + 16))
        fps_txt = font_small.render(
            f"{state.fps_est:4.1f} FPS   det={state.det_count}",
            True, WHITE,
        )
        screen.blit(fps_txt,
                    (proj_w - fps_txt.get_width() - 20, hud_y + 24))

        keys_txt = font_small.render(
            "  N: new target    R: reset    Q/ESC: quit",
            True, (140, 150, 175),
        )
        screen.blit(keys_txt, (20, 12))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


# ── cv2 operator window (PC monitor) ─────────────────────────────────────────
def render_operator_window(
    captures: dict[str, ThreadedCapture],
    cam_order: list[str],
    mappers: dict[str, SouthWallMapper],
    rects,
    state: GameState,
    args,
    shared: dict,
    running: list[bool],
) -> None:
    win = "Goal Game - Operator"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    mx, my = [int(v) for v in args.monitor_pos.split(",")]
    cv2.moveWindow(win, mx, my)
    cv2.resizeWindow(win, 1280, 800)

    tile_w, tile_h = 600, 340
    banner_h = 80

    while running[0]:
        with shared["lock"]:
            frames = dict(shared.get("frames") or {})
            picks = dict(shared.get("picks") or {})
        with state.lock:
            active_idx = state.active_idx
            ai_lbl = rects[active_idx].label
            sc, ms = state.score, state.misses
            uv = state.last_wall_uv
            used = list(state.last_used_cams)
            reproj = state.last_reproj_err
            fps_est = state.fps_est
            per_cam_wall_uv = dict(state.last_per_cam_wall_uv)
            per_cam_zones = dict(state.last_per_cam_zones)
            zone_votes = dict(state.last_zone_votes)
            no_hit_reason = state.last_no_hit_reason

        # Build the 2x2 tile.
        rows = []
        for r in range(2):
            row_imgs = []
            for c in range(2):
                idx = r * 2 + c
                if idx < len(cam_order):
                    cam = cam_order[idx]
                    fr = frames.get(cam)
                else:
                    cam, fr = None, None
                if fr is None:
                    tile = np.zeros((tile_h, tile_w, 3), dtype=np.uint8)
                else:
                    tile = cv2.resize(fr, (tile_w, tile_h))
                    h_src, w_src = fr.shape[:2]
                    sx = tile_w / w_src
                    sy = tile_h / h_src
                    # Wall grid overlay using the cam mapper.
                    mapper = mappers.get(cam)
                    if mapper is not None:
                        for i, rect in enumerate(rects):
                            pts = []
                            for (uu, vv) in [
                                (rect.u_min, rect.v_min),
                                (rect.u_max, rect.v_min),
                                (rect.u_max, rect.v_max),
                                (rect.u_min, rect.v_max),
                            ]:
                                x, y = mapper.wall_to_pixel(uu, vv)
                                pts.append((int(x * sx), int(y * sy)))
                            color = ((0, 240, 80) if i == active_idx
                                     else (80, 180, 255))
                            cv2.polylines(
                                tile, [np.array(pts, dtype=np.int32)],
                                True, color, 2,
                            )
                            cu, cv_ = rect.center
                            tx, ty = mapper.wall_to_pixel(cu, cv_)
                            cv2.putText(
                                tile, rect.label,
                                (int(tx * sx) - 14, int(ty * sy) + 6),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.55, color, 2,
                            )
                    # YOLO pick overlay.
                    pk = picks.get(cam)
                    if pk is not None:
                        x1, y1, x2, y2, conf = pk
                        cv2.rectangle(
                            tile,
                            (int(x1 * sx), int(y1 * sy)),
                            (int(x2 * sx), int(y2 * sy)),
                            (0, 230, 90), 2,
                        )
                        cv2.circle(
                            tile,
                            (int(0.5 * (x1 + x2) * sx),
                             int(0.5 * (y1 + y2) * sy)),
                            5, (0, 255, 255), -1,
                        )
                        cv2.putText(
                            tile, f"ball {conf:.2f}",
                            (int(x1 * sx), max(18, int(y1 * sy) - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 230, 90), 2,
                        )
                    wall_uv = per_cam_wall_uv.get(cam)
                    if wall_uv is not None:
                        zone = per_cam_zones.get(cam) or "--"
                        cv2.putText(
                            tile,
                            f"U={wall_uv[0]:.0f} V={wall_uv[1]:.0f} {zone}",
                            (10, tile_h - 16),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.55,
                            (0, 255, 255),
                            2,
                        )
                    cv2.putText(
                        tile, cam, (10, 26),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75, (235, 240, 245), 2,
                    )
                row_imgs.append(tile)
            rows.append(np.hstack(row_imgs))
        tile_grid = np.vstack(rows)

        # Top banner.
        banner = np.zeros((banner_h, tile_grid.shape[1], 3), dtype=np.uint8)
        banner[:] = (18, 22, 36)
        cv2.putText(
            banner, f"TARGET -> {ai_lbl}",
            (24, 52), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (28, 215, 95), 3,
        )
        cv2.putText(
            banner, f"HIT {sc}", (520, 52),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, HIT_FX[::-1], 3,
        )
        cv2.putText(
            banner, f"MISS {ms}", (700, 52),
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, MISS_FX[::-1], 3,
        )
        if uv is not None:
            cv2.putText(
                banner, f"wall U={uv[0]:5.0f} V={uv[1]:5.0f}mm",
                (900, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 220, 255), 1,
            )
        cv2.putText(
            banner,
            f"cams={','.join(used) if used else '--'}"
            f"  reproj={('--' if reproj is None else f'{reproj:.1f}px')}"
            f"  fps={fps_est:.1f}",
            (900, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 200, 220), 1,
        )
        vote_str = ", ".join(
            f"{label}:{len(cams)}" for label, cams in zone_votes.items()
        ) or "none"
        cv2.putText(
            banner,
            f"votes={vote_str}  reason={no_hit_reason}",
            (900, 78), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 220, 255), 1,
        )

        canvas = np.vstack([banner, tile_grid])
        cv2.imshow(win, canvas)
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            running[0] = False
            break
        elif k == ord("n"):
            with state.lock:
                state.pick_new_active()
        elif k == ord("r"):
            with state.lock:
                state.score = 0
                state.misses = 0
                state.pick_new_active()

    cv2.destroyAllWindows()


# ── Entry ────────────────────────────────────────────────────────────────────
def build_arg_parser() -> argparse.ArgumentParser:
    default_model = PROJECT_ROOT / "models/ball/yolo26m-672.engine"
    if not default_model.exists():
        default_model = PROJECT_ROOT / "models/ball/yolo26m-672.pt"

    ap = argparse.ArgumentParser(
        description="Multi-cam projector goal game (camEast/N/S/W + south wall)."
    )
    ap.add_argument("--cams", default="camEast,camNorth,camSouth,camWest",
                    help="Comma-separated cam roles, in order.")
    ap.add_argument("--camera-config",
                    default="garage_lab_combined/config/cameras.yaml")
    # Defaults point at the post-remount candidate bundle (1920x1080, lateral
    # cams remounted 2026-05-25). Override to canonical paths if rolling back.
    ap.add_argument("--intrinsics-dir",
                    default="Remounted_West_East/cal/intrinsics")
    ap.add_argument("--extrinsics",
                    default="Remounted_West_East/cal/extrinsics/extrinsics_fixed.json")
    ap.add_argument("--homography",
                    default=str(PROJECTOR_DIR / "homography.json"))
    ap.add_argument("--model", default=str(default_model))
    ap.add_argument("--device", default="cuda:0")
    # Multicam consensus tolerates weaker per-cam boxes. Fast wall shots often
    # appear low-conf/blurred in the side cameras, and those side votes are
    # exactly what the consensus scorer needs.
    ap.add_argument("--ball-conf", type=float, default=0.20)
    ap.add_argument("--ball-imgsz", type=int, default=672)
    ap.add_argument("--max-box-side-px", type=float, default=220.0)
    ap.add_argument("--min-box-side-px", type=float, default=0.0)
    ap.add_argument("--ball-kf-gate-px", type=float, default=180.0)
    ap.add_argument("--ball-max-reproj-px", type=float, default=25.0)
    ap.add_argument("--kalman-process-noise",     type=float, default=800.0)
    ap.add_argument("--kalman-measurement-noise", type=float, default=25.0)

    ap.add_argument("--hit-pad-mm",   type=float, default=100.0,
                    help="Padding around grid rectangle (UV mm).")
    ap.add_argument("--cooldown-s",   type=float, default=0.8)
    ap.add_argument("--wall-x-mm",    type=float, default=SOUTH_WALL_X_MM)
    ap.add_argument("--wall-x-tolerance-mm", type=float, default=300.0,
                    help="(Legacy triangulation mode) accept any raw observation "
                         "within this many mm of the wall plane.")
    ap.add_argument("--raw-max-gap-s", type=float, default=0.5,
                    help="(Legacy) if gap between consecutive triangulations "
                         "exceeds this, skip interpolation.")

    # ── Consensus hit detection (primary) ────────────────────────────────────
    ap.add_argument("--min-consensus-cams", type=int, default=2,
                    help="Number of cameras that must independently project "
                         "their ball detection into the same zone to fire a hit.")
    ap.add_argument("--consensus-pad-mm", type=float, default=150.0,
                    help="Padding around each grid rectangle (in wall mm) when "
                         "deciding which zone a per-cam projection falls in.")
    ap.add_argument("--consensus-window-s", type=float, default=0.25,
                    help="Seconds of recent per-cam zone votes to combine for "
                         "async cameras.")

    ap.add_argument("--debug", action="store_true",
                    help="Print per-second detection/triangulation stats and "
                         "near-miss notices to stdout.")
    ap.add_argument("--debug-print-period-s", type=float, default=1.0)

    # FullHD MJPG @ 30 FPS matches the remount config (cameras.md + manifest).
    ap.add_argument("--width",  type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps",    type=int, default=30)
    ap.add_argument("--fourcc", default="MJPG")
    ap.add_argument("--no-uvc-controls", action="store_true",
                    help="Do not apply low-latency V4L2 controls to USB webcams.")
    ap.add_argument("--uvc-exposure", type=int, default=200,
                    help="Manual UVC exposure_time_absolute. 200 = about 20 ms; keeps C920 at 30 FPS.")
    ap.add_argument("--uvc-gain", type=int, default=160,
                    help="Manual UVC gain. Use -1 to leave gain unchanged.")
    ap.add_argument("--uvc-focus", type=int, default=0,
                    help="Manual UVC focus_absolute. Use -1 to leave focus unchanged.")
    ap.add_argument("--uvc-power-line-frequency", type=int, default=1,
                    help="UVC power_line_frequency: 1=50 Hz, 2=60 Hz.")

    ap.add_argument("--proj-w", type=int, default=1920)
    ap.add_argument("--proj-h", type=int, default=1080)
    ap.add_argument("--proj-pos", default="1920,0")
    ap.add_argument("--projector-output", default="",
                    help="xrandr output name for projector placement, e.g. DP-1-2. "
                         "When set, this overrides --proj-pos/--projector-display.")
    ap.add_argument("--projector-display", default="auto",
                    help="pygame display index (auto|0|1|...).")

    ap.add_argument("--monitor-pos", default="50,50")
    ap.add_argument("--goal-log-jsonl", default="")
    ap.add_argument("--debug-log-jsonl", default="",
                    help="Optional per-frame detection/projection/vote JSONL log.")
    return ap


def main() -> int:
    args = build_arg_parser().parse_args()

    cam_order = [c.strip() for c in args.cams.split(",") if c.strip()]
    if len(cam_order) < 2:
        print("[ERROR] Need at least 2 cameras for triangulation.")
        return 2

    cams_cfg = load_cameras(_project_path(args.camera_config))
    extrinsics_all = load_extrinsics(_project_path(args.extrinsics))

    captures: dict[str, ThreadedCapture] = {}
    intrinsics: dict[str, dict] = {}
    extrinsics: dict[str, dict] = {}
    proj_mats: dict[str, np.ndarray] = {}
    mappers: dict[str, SouthWallMapper] = {}

    for cam in cam_order:
        if cam not in cams_cfg:
            print(f"[ERROR] cam {cam} missing from {args.camera_config}")
            return 2
        if cam not in extrinsics_all:
            print(f"[ERROR] cam {cam} missing from {args.extrinsics}")
            return 2
        device = cams_cfg[cam]["device"]

        intr_path = (_project_path(args.intrinsics_dir)
                     / f"{cam}_intrinsics.json")
        if not intr_path.exists():
            print(f"[ERROR] intrinsics missing: {intr_path}")
            return 2
        K_raw, D, src_w, src_h = load_intrinsics(intr_path)
        K = scale_intrinsics_matrix(K_raw, src_w, src_h, args.width, args.height)
        intrinsics[cam] = {"K": K, "D": D}

        e = extrinsics_all[cam]
        extrinsics[cam] = e
        proj_mats[cam] = K @ e["P"]

        mappers[cam] = SouthWallMapper(K, D, e["R"], e["tvec"], wall_x_mm=args.wall_x_mm)

        cap = open_capture(device, args.width, args.height, args.fps, args.fourcc, args, cam)
        if cap is None:
            print(f"[ERROR] cannot open {cam} at {device}")
            return 2
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[CAM] {cam}: {device} -> {actual_w}x{actual_h}")
        captures[cam] = ThreadedCapture(cap, name=cam)

    homography_path = _project_path(args.homography)
    homography_data = _load_homography_data(homography_path)
    H_proj = (
        None if homography_data is None
        else np.array(homography_data["H"], dtype=np.float64)
    )
    if homography_data is None:
        print(f"[WARN] Homography missing at {args.homography}; using linear stretch.")
    else:
        print(f"[CAL] Loaded projector homography from {args.homography}")
        src_w = int(homography_data.get("proj_w", 0) or 0)
        src_h = int(homography_data.get("proj_h", 0) or 0)
        if src_w and src_h and (src_w, src_h) != (args.proj_w, args.proj_h):
            print(
                "[WARN] Homography metadata says "
                f"{src_w}x{src_h}, current projector is "
                f"{args.proj_w}x{args.proj_h}; recalibrate if the grid "
                "does not line up physically."
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
    state = GameState(n_rects=len(rects))
    running = [True]

    shared = {
        "lock": threading.Lock(),
        "frames": {},
        "picks": {},
        "kf_preds": {},
    }

    goal_log_fp = None
    if args.goal_log_jsonl:
        p = _project_path(args.goal_log_jsonl)
        p.parent.mkdir(parents=True, exist_ok=True)
        goal_log_fp = p.open("a", encoding="utf-8")
    debug_log_fp = None
    if args.debug_log_jsonl:
        p = _project_path(args.debug_log_jsonl)
        p.parent.mkdir(parents=True, exist_ok=True)
        debug_log_fp = p.open("a", encoding="utf-8")

    cam_thread = threading.Thread(
        target=camera_loop,
        args=(captures, cam_order, intrinsics, extrinsics, proj_mats,
              mappers, rects, args, state, H_proj, shared, running,
              goal_log_fp, debug_log_fp),
        daemon=True,
    )
    cam_thread.start()

    operator_thread = threading.Thread(
        target=render_operator_window,
        args=(captures, cam_order, mappers, rects, state, args,
              shared, running),
        daemon=True,
    )
    operator_thread.start()

    try:
        render_projector(state, rects, args, H_proj, running)
    except KeyboardInterrupt:
        pass
    finally:
        running[0] = False
        cam_thread.join(timeout=2.0)
        operator_thread.join(timeout=2.0)
        for cap in captures.values():
            cap.release()
        if goal_log_fp is not None:
            goal_log_fp.close()
        if debug_log_fp is not None:
            debug_log_fp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
