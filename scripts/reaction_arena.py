#!/usr/bin/env python3
"""Reaction Arena — projector reaction game scored by body position.

A standalone projector/monitor game that listens to the live joint UDP stream
broadcast by the viewer (run_live_usb6_blm.sh, 127.0.0.1:5005) and scores the
player by WHERE THEY MOVE — never by detecting a fast ball. This plays to the
rig's strength (validated person tracking) and avoids its weak spot (fast-ball
hit detection), so it's a reliable, safe demo.

Game: the floor width is split into 3 zones (LEFT / CENTER / RIGHT). Each round
counts down 3-2-1-GO, lights a random target zone, and measures how fast the
player's hips enter it. Score + reaction time shown big for spectators.

Run alongside (does NOT touch the viewer or the BLM):
  T1: ./venv/bin/python scripts/uvc_keeper.py --watch
  T2: ./Parallel_working/run_live_usb6_blm.sh           # cinematic 3D + UDP broadcast
  T3: ./venv/bin/python scripts/reaction_arena.py       # this game (drag to projector, press f)
  T4 (optional, SAFE): live_aim_test.py ... (aim-only)  # BLM follows the player, no firing

Keys: SPACE start/pause · r reset · f fullscreen · q quit
"""
import argparse
import json
import socket
import threading
import time

import cv2
import numpy as np

ZONE_NAMES = ["LEFT", "CENTER", "RIGHT"]
COL_BG_TOP = (46, 34, 28)
COL_BG_BOT = (20, 16, 16)
COL_DIM = (60, 50, 44)
COL_TARGET = (40, 200, 60)        # green (go here)
COL_PLAYER = (255, 200, 40)       # cyan-ish (you are here)
COL_HIT = (60, 220, 90)
COL_MISS = (60, 60, 235)


class UDPJointListener:
    """Background listener for the viewer's {'joints': {name: {x_mm,y_mm,z_mm}}} packets."""

    def __init__(self, host="0.0.0.0", port=5005):
        self.lock = threading.Lock()
        self.joints = {}
        self.last_ts = 0.0
        self._run = True
        self._t = threading.Thread(target=self._listen, args=(host, port), daemon=True)
        self._t.start()

    def _listen(self, host, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.settimeout(1.0)
        while self._run:
            try:
                data, _ = s.recvfrom(65535)
                pkt = json.loads(data.decode("utf-8", errors="ignore"))
                j = pkt.get("joints", {})
                if isinstance(j, dict):
                    with self.lock:
                        self.joints = j
                        self.last_ts = time.time()
            except socket.timeout:
                continue
            except Exception:
                continue
        s.close()

    def player_xy_mm(self, max_age=0.6):
        """Return (x_mm, y_mm) of the player (hips midpoint, with fallbacks), or None."""
        with self.lock:
            if time.time() - self.last_ts > max_age:
                return None
            j = dict(self.joints)
        def g(name):
            v = j.get(name)
            if isinstance(v, dict) and "x_mm" in v:
                return np.array([v["x_mm"], v["y_mm"], v["z_mm"]], dtype=float)
            return None
        lh, rh = g("left_hip"), g("right_hip")
        if lh is not None and rh is not None:
            p = 0.5 * (lh + rh)
        else:
            for nm in ("nose", "left_shoulder", "right_shoulder", "left_hip", "right_hip"):
                p = g(nm)
                if p is not None:
                    break
            else:
                return None
        return float(p[0]), float(p[1])

    def stop(self):
        self._run = False


def zone_of(y_mm, arena_y_mm, n=3, flip=False):
    """Map a lateral coordinate to a zone index 0..n-1."""
    t = float(np.clip(y_mm / max(1.0, arena_y_mm), 0.0, 0.999))
    idx = int(t * n)
    return (n - 1 - idx) if flip else idx


class ReactionGame:
    """Pure state machine (no rendering) so it can be unit-tested.

    States: idle -> countdown -> active -> result -> (next round) ... -> done
    """

    def __init__(self, rounds=10, countdown_s=2.0, timeout_s=3.0, result_s=1.4, seed=None):
        self.rounds = rounds
        self.countdown_s = countdown_s
        self.timeout_s = timeout_s
        self.result_s = result_s
        self.rng = np.random.default_rng(seed)
        self.reset()

    def reset(self):
        self.state = "idle"
        self.round = 0
        self.score = 0
        self.target = None
        self.t_state = 0.0          # time the current state started
        self.go_time = None
        self.reactions = []         # successful reaction times (s)
        self.last_result = None     # ("hit", t) | ("miss", None)

    def start(self, now):
        if self.state in ("idle", "done"):
            self.reset()
            self._begin_round(now)

    def _begin_round(self, now):
        self.round += 1
        if self.round > self.rounds:
            self.state = "done"
            return
        prev = self.target
        z = int(self.rng.integers(0, 3))
        if z == prev:
            z = (z + 1) % 3
        self.target = z
        self.state = "countdown"
        self.t_state = now
        self.go_time = None
        self.last_result = None

    def update(self, now, player_zone):
        """Advance the machine. player_zone: int 0..2 or None (no player)."""
        if self.state == "countdown":
            if now - self.t_state >= self.countdown_s:
                self.state = "active"
                self.t_state = now
                self.go_time = now
        elif self.state == "active":
            if player_zone is not None and player_zone == self.target:
                rt = now - self.go_time
                self.reactions.append(rt)
                self.score += 1
                self.last_result = ("hit", rt)
                self.state = "result"
                self.t_state = now
            elif now - self.t_state >= self.timeout_s:
                self.last_result = ("miss", None)
                self.state = "result"
                self.t_state = now
        elif self.state == "result":
            if now - self.t_state >= self.result_s:
                self._begin_round(now)
        return self.state

    def countdown_value(self, now):
        remaining = self.countdown_s - (now - self.t_state)
        return max(1, int(np.ceil(remaining)))

    def best_reaction(self):
        return min(self.reactions) if self.reactions else None

    def avg_reaction(self):
        return float(np.mean(self.reactions)) if self.reactions else None


# ----------------------------- rendering -----------------------------

def _gradient_bg(w, h):
    img = np.empty((h, w, 3), np.uint8)
    ramp = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    top = np.array(COL_BG_TOP, np.float32); bot = np.array(COL_BG_BOT, np.float32)
    img[:] = (top[None] * (1 - ramp) + bot[None] * ramp).astype(np.uint8)[:, None, :]
    return img


def _text(img, s, org, scale, color, thick=2):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def render(game, player_zone, w, h, flip):
    img = _gradient_bg(w, h)
    # top status bar
    cv2.rectangle(img, (0, 0), (w, 54), (18, 14, 13), -1)
    _text(img, "REACTION ARENA", (20, 38), 0.9, (255, 255, 255))
    _text(img, f"Round {min(game.round, game.rounds)}/{game.rounds}", (w // 2 - 90, 36), 0.8, (200, 200, 200))
    _text(img, f"Score {game.score}", (w - 230, 36), 0.9, (150, 255, 170))
    best = game.best_reaction()
    if best is not None:
        _text(img, f"Best {best:.2f}s", (w - 380, 36), 0.7, (200, 200, 200), 1)

    # three zones
    names = list(reversed(ZONE_NAMES)) if flip else ZONE_NAMES
    pad = 16
    zw = (w - 4 * pad) // 3
    y0, y1 = 80, h - 90
    for i in range(3):
        x0 = pad + i * (zw + pad)
        x1 = x0 + zw
        is_target = (game.state in ("active", "result") and game.target == i)
        is_player = (player_zone == i)
        fill = COL_DIM
        if is_target and game.state == "active":
            # pulse the target
            pulse = 0.5 + 0.5 * np.sin(time.time() * 6)
            fill = tuple(int(COL_DIM[k] * (1 - pulse) + COL_TARGET[k] * pulse) for k in range(3))
        elif is_target and game.state == "result" and game.last_result and game.last_result[0] == "hit":
            fill = COL_HIT
        cv2.rectangle(img, (x0, y0), (x1, y1), fill, -1)
        border = COL_PLAYER if is_player else (90, 80, 60)
        cv2.rectangle(img, (x0, y0), (x1, y1), border, 6 if is_player else 2)
        _text(img, names[i], (x0 + zw // 2 - 70, (y0 + y1) // 2), 1.1,
              (255, 255, 255) if is_target else (170, 170, 170))
        if is_player:
            _text(img, "YOU", (x0 + zw // 2 - 34, y1 - 24), 0.7, COL_PLAYER, 2)

    # center overlays per state
    cx, cy = w // 2, h // 2
    if game.state == "idle":
        _text(img, "SPACE to start", (cx - 200, cy), 1.3, (255, 255, 255))
    elif game.state == "countdown":
        n = game.countdown_value(time.time())
        _text(img, str(n), (cx - 30, cy + 30), 4.0, (255, 255, 255), 6)
        _text(img, "GET READY", (cx - 150, y0 + 40), 0.9, (200, 200, 200), 2)
    elif game.state == "active":
        _text(img, "GO!", (cx - 70, y0 + 46), 1.2, COL_TARGET, 3)
    elif game.state == "result" and game.last_result:
        kind, rt = game.last_result
        if kind == "hit":
            _text(img, f"HIT!  {rt:.2f}s", (cx - 180, cy), 1.6, COL_HIT, 4)
        else:
            _text(img, "MISS", (cx - 110, cy), 1.6, COL_MISS, 4)
    elif game.state == "done":
        avg = game.avg_reaction()
        _text(img, f"FINAL  {game.score}/{game.rounds}", (cx - 230, cy - 20), 1.5, (150, 255, 170), 4)
        if avg is not None:
            _text(img, f"avg reaction {avg:.2f}s", (cx - 180, cy + 50), 0.9, (220, 220, 220), 2)
        _text(img, "SPACE to play again", (cx - 220, h - 110), 0.9, (200, 200, 200), 2)

    if player_zone is None:
        _text(img, "waiting for player...", (20, h - 30), 0.7, (60, 60, 235), 2)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--udp-port", type=int, default=5005)
    ap.add_argument("--arena-y-mm", type=float, default=3050.0,
                    help="Arena width (lateral axis the zones span), mm.")
    ap.add_argument("--flip", action="store_true",
                    help="Flip LEFT/RIGHT if the player's movement feels mirrored on screen.")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--countdown-s", type=float, default=2.0)
    ap.add_argument("--timeout-s", type=float, default=3.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fullscreen", action="store_true")
    args = ap.parse_args()

    udp = UDPJointListener(port=args.udp_port)
    game = ReactionGame(rounds=args.rounds, countdown_s=args.countdown_s, timeout_s=args.timeout_s)
    win = "Reaction Arena"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    if args.fullscreen:
        cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    print(f"[OK] Reaction Arena listening on UDP :{args.udp_port}. SPACE=start f=fullscreen q=quit")

    paused = False
    try:
        while True:
            now = time.time()
            xy = udp.player_xy_mm()
            pz = None if xy is None else zone_of(xy[1], args.arena_y_mm, 3, args.flip)
            if not paused:
                game.update(now, pz)
            img = render(game, pz, args.width, args.height, args.flip)
            cv2.imshow(win, img)
            k = cv2.waitKey(16) & 0xFF
            if k == ord("q"):
                break
            elif k == ord(" "):
                if game.state in ("idle", "done"):
                    game.start(now)
                else:
                    paused = not paused
            elif k == ord("r"):
                game.reset()
            elif k == ord("f"):
                cur = cv2.getWindowProperty(win, cv2.WND_PROP_FULLSCREEN)
                cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN,
                                      cv2.WINDOW_NORMAL if cur >= 1 else cv2.WINDOW_FULLSCREEN)
            try:
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break
    finally:
        udp.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
