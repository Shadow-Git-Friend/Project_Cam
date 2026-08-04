#!/usr/bin/env python3
"""
goal_detector.py — Single-camera (camNorth) ball detector → projector impact trigger.

Pipeline (from pipeline_infer.docx):
  YOLO (y26s custom model) → PersistentTrackerV3 (Hungarian + IoU + re-ID)
  → per-track EMA velocity + acceleration (Tracker3D style)
  → deceleration threshold → UDP impact to projector_sim

Wall hit fires two consecutive UDP packets that straddle the south wall plane
so projector_sim._crosses_wall() triggers:
  packet 1: x_mm = 6000  (inside arena, before wall)
  packet 2: x_mm = 6500  (past wall)

Usage
-----
  # Terminal 1 — projector sim, keeper drill, listening on UDP 5005
  python projector_sim.py --wall south --drill keeper --udp-port 5005 --width 1920 --height 1200

  # Terminal 2 — detector (drag preview window to laptop screen)
  python goal_detector.py --cam 1

  # Override model or camera:
  python goal_detector.py --cam 1 --model projector/model/best.pt
"""

import argparse
import json
import math
import os
import socket
import sys
import time

import cv2
import numpy as np
import yaml
from ultralytics import YOLO

sys.path.insert(0, os.path.dirname(__file__))
from trackers.persistent_tracker_v3 import PersistentTrackerV3

# ── Arena constants ────────────────────────────────────────────────────────────
_SOUTH_WALL_X   = 6230.0
_IMPACT_X_PREV  = 6000.0   # just inside arena
_IMPACT_X_NEXT  = 6500.0   # just past wall → triggers _crosses_wall in sim


# ── Per-track velocity tracker (adapted from Footbonaut/tracker/tracker3d.py) ─
class _TrackVelocity:
    """EMA velocity + acceleration for a single 2D track (px/frame)."""

    def __init__(self, alpha=0.6, history_len=30):
        self.alpha       = alpha
        self.history_len = history_len
        self.history     = []   # (cx, cy, t)
        self.speed       = 0.0
        self.peak_speed  = 0.0
        self.accel       = 0.0
        self._prev_speed = 0.0

    def update(self, cx, cy, t):
        self.history.append((cx, cy, t))
        if len(self.history) > self.history_len:
            self.history.pop(0)
        if len(self.history) >= 2:
            x1, y1, t1 = self.history[-2]
            x2, y2, t2 = self.history[-1]
            dt = t2 - t1
            if dt > 1e-4:
                inst_speed = math.hypot(x2 - x1, y2 - y1) / dt
                prev       = self.speed
                self.speed = self.alpha * self.speed + (1 - self.alpha) * inst_speed
                self.accel = self.alpha * self.accel + (1 - self.alpha) * (
                    (self.speed - prev) / dt
                )
                if self.speed > self.peak_speed:
                    self.peak_speed = self.speed


# ── UDP helper ─────────────────────────────────────────────────────────────────
def _send_impact(sock, host, port, u_mm, v_mm):
    for x in (_IMPACT_X_PREV, _IMPACT_X_NEXT):
        pkt = json.dumps({"ball": {"x_mm": x, "y_mm": u_mm, "z_mm": v_mm}}).encode()
        sock.sendto(pkt, (host, port))


def _px_to_uv(cx, cy, fw, fh, u_min, u_max, v_min, v_max):
    u = u_min + (cx / fw) * (u_max - u_min)
    v = v_max - (cy / fh) * (v_max - v_min)  # top of image = ceiling
    return float(np.clip(u, u_min, u_max)), float(np.clip(v, v_min, v_max))


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Goal detector — camNorth → projector sim")
    ap.add_argument("--cam",    type=int,   default=0,
                    help="Camera index (try 0, 1, 2 …)")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__),
                                                      "cfg", "config.yaml"))
    ap.add_argument("--model",  default=None,
                    help="Override model path from config")
    ap.add_argument("--no-show", action="store_true")
    args = ap.parse_args()

    # ── Config ────────────────────────────────────────────────────────────────
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    model_path = args.model or cfg["model"]
    conf       = cfg["conf"]
    imgsz      = cfg["imgsz"]
    classes    = cfg["classes"]

    jitter_thresh = cfg["jitter_thresh"]
    reid_gate     = cfg["reid_gate_px"]
    max_missed    = cfg["max_missed_frames"]
    alpha_vel     = cfg["alpha_vel"]
    history_len   = cfg["history_len"]

    min_flight    = cfg["min_flight_speed"]   # px/s
    decel_ratio   = cfg["decel_ratio"]
    cooldown      = cfg["impact_cooldown"]

    u_min = cfg["wall_u_min"]
    u_max = cfg["wall_u_max"]
    v_min = cfg["wall_v_min"]
    v_max = cfg["wall_v_max"]

    udp_host = cfg["udp_host"]
    udp_port = cfg["udp_port"]

    # ── Model ─────────────────────────────────────────────────────────────────
    model_abs = model_path if os.path.isabs(model_path) else os.path.join(
        os.path.dirname(__file__), "..", model_path)
    model_abs = os.path.normpath(model_abs)
    if not os.path.exists(model_abs):
        # fallback: try relative to cwd
        model_abs = model_path
    print(f"[MODEL] Loading {model_abs} …")
    model = YOLO(model_abs)
    print("[MODEL] Ready.")

    # ── Camera ────────────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(args.cam)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {args.cam}. Try --cam 1 or --cam 2.")
        return
    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[CAM]  index={args.cam}  {fw}×{fh}")

    # ── Tracker + velocity state ───────────────────────────────────────────────
    tracker    = PersistentTrackerV3(cfg)
    vel_state  = {}   # track_id → _TrackVelocity
    last_impact = {}  # track_id → timestamp of last impact

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[UDP]  Impacts → {udp_host}:{udp_port}")
    print(f"[WALL] U {u_min:.0f}–{u_max:.0f} mm   V {v_min:.0f}–{v_max:.0f} mm")
    print("[INFO] Press Q in preview to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.01)
            continue

        now  = time.time()
        disp = frame.copy() if not args.no_show else None

        # ── YOLO inference ────────────────────────────────────────────────────
        results  = model(frame, conf=conf, imgsz=imgsz, classes=classes, verbose=False)
        raw_dets = []
        for r in results:
            if r.boxes is not None:
                for i in range(len(r.boxes)):
                    bbox = r.boxes.xyxy[i].cpu().numpy()
                    cf   = float(r.boxes.conf[i].cpu())
                    raw_dets.append({"bbox": bbox, "conf": cf})

        # ── Track ─────────────────────────────────────────────────────────────
        tracks = tracker.update(raw_dets)

        for t in tracks:
            tid = t["id"]
            cx, cy = t["centroid"]

            # velocity tracking
            if tid not in vel_state:
                vel_state[tid] = _TrackVelocity(alpha=alpha_vel,
                                                history_len=history_len)
            vel_state[tid].update(cx, cy, now)
            vel  = vel_state[tid]

            # ── Impact detection ──────────────────────────────────────────────
            since_last = now - last_impact.get(tid, -999)
            if (since_last > cooldown
                    and vel.peak_speed > min_flight
                    and vel.speed < decel_ratio * vel.peak_speed):
                u_mm, v_mm = _px_to_uv(cx, cy, fw, fh, u_min, u_max, v_min, v_max)
                _send_impact(sock, udp_host, udp_port, u_mm, v_mm)
                last_impact[tid]  = now
                vel.peak_speed    = 0.0   # reset peak after impact
                print(f"[IMPACT] id={tid}  u={u_mm:.0f}mm  v={v_mm:.0f}mm  "
                      f"px=({cx:.0f},{cy:.0f})  spd={vel.speed:.1f}px/s")
                if disp is not None:
                    cv2.circle(disp, (int(cx), int(cy)), 36, (0, 40, 255), 3)
                    cv2.putText(disp, "IMPACT", (int(cx) - 35, int(cy) - 44),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 40, 255), 2)

            # ── Draw ──────────────────────────────────────────────────────────
            if disp is not None:
                x1, y1, x2, y2 = map(int, t["bbox"])
                cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 220, 80), 2)
                label = f"#{tid}  {vel.speed:.0f}px/s"
                cv2.putText(disp, label, (x1, max(14, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 80), 1)
                # trail
                trail = [(int(x), int(y)) for x, y, _ in vel_state[tid].history]
                for i in range(1, len(trail)):
                    cv2.line(disp, trail[i-1], trail[i], (255, 140, 0), 1)

        # ── Prune dead vel_state entries ──────────────────────────────────────
        live_ids = {t["id"] for t in tracks}
        for tid in list(vel_state):
            if tid not in live_ids:
                del vel_state[tid]
                last_impact.pop(tid, None)

        # ── HUD ───────────────────────────────────────────────────────────────
        if disp is not None:
            cv2.putText(disp, f"tracks: {len(tracks)}",
                        (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
            cv2.putText(disp, f"UDP → {udp_host}:{udp_port}",
                        (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (130, 130, 130), 1)
            cv2.imshow("Goal Detector — Q to quit", disp)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        elif cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    sock.close()


if __name__ == "__main__":
    main()
