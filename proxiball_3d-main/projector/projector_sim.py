#!/usr/bin/env python3
"""
projector_sim.py — Proxiball arena projector simulator, polished edition.

World coordinates (mm, origin = north-east corner):
  X: 0 (north) → 6230 (south)
  Y: 0 (east)  → 3050 (west)
  Z: 0 (floor) → 2950 (ceiling)

Wall drills  (--wall south/north/east/west):
  1  target_grid   Footbonaut-style 3×3 target zones
  2  player_pass   Moving players — pass to the glowing foot
  3  keeper        Goalkeeper — shoot to the gap
  4  moving        Bouncing target that shrinks as you score
  5  sequence      Hit numbered targets in order 1→2→3→4→5

Floor drills (--wall floor, top-down):
  6  cones         Slalom cone course
  7  lanes         Passing lane board

Keys:  1-7 switch drill   SPACE start/stop   R reset   Q/ESC quit
"""

import argparse
import json
import math
import random
import socket
import threading
import time
from typing import List, Optional, Tuple

import numpy as np
import pygame

# ── Arena constants (mm) ──────────────────────────────────────────────────────
ARENA_X = 6230
ARENA_Y = 3050
ARENA_Z = 2950

WALL_DEFS = {
    "south": dict(fixed="X", fixed_val=ARENA_X, u_axis="Y", u_max=ARENA_Y, v_max=ARENA_Z, invert_v=True),
    "north": dict(fixed="X", fixed_val=0,       u_axis="Y", u_max=ARENA_Y, v_max=ARENA_Z, invert_v=True),
    "east":  dict(fixed="Y", fixed_val=0,       u_axis="X", u_max=ARENA_X, v_max=ARENA_Z, invert_v=True),
    "west":  dict(fixed="Y", fixed_val=ARENA_Y, u_axis="X", u_max=ARENA_X, v_max=ARENA_Z, invert_v=True),
    "floor": dict(fixed="Z", fixed_val=0,       u_axis="X", u_max=ARENA_X, v_max=ARENA_Y, invert_v=False),
}

WALL_DRILLS  = ["target_grid", "player_pass", "keeper", "moving", "sequence"]
FLOOR_DRILLS = ["cones", "lanes"]

# ── Colour palette ────────────────────────────────────────────────────────────
BG         = (8,   11,  20)
PANEL_C    = (11,  16,  30)
GRID_C     = (17,  23,  40)
WHITE      = (235, 238, 245)
DIM        = (38,  50,  75)
TEAM_A     = (42,  120, 215)
TEAM_B     = (200, 48,  48)
ACTIVE     = (28,  215, 95)
YELLOW     = (255, 228, 35)
ORANGE     = (255, 140, 24)
HIT_FX     = (55,  235, 110)
MISS_FX    = (215, 40,  40)
HUD_C      = (58,  200, 140)
CONE_C     = (255, 130, 18)
GRASS_A    = (21,  57,  27)
GRASS_B    = (25,  68,  31)
PITCH_LINE = (195, 205, 185)


# ── Low-level drawing helpers ─────────────────────────────────────────────────

def _filled_capsule(surf: pygame.Surface,
                    x1: float, y1: float, x2: float, y2: float,
                    r: int, color: tuple):
    """Thick-line capsule (pill shape) between two points."""
    r = max(1, int(r))
    pygame.draw.line(surf, color, (int(x1), int(y1)), (int(x2), int(y2)), r * 2)
    pygame.draw.circle(surf, color, (int(x1), int(y1)), r)
    pygame.draw.circle(surf, color, (int(x2), int(y2)), r)


def _draw_glow(surf: pygame.Surface, cx: int, cy: int, r: int, color: tuple,
               alpha: int = 110, rings: int = 3):
    """Soft radial glow around a point."""
    for i in range(rings, 0, -1):
        ri = r + i * max(4, r // 2)
        ai = alpha // (i + 1)
        s = pygame.Surface((ri * 2 + 2, ri * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color[:3], ai), (ri + 1, ri + 1), ri)
        surf.blit(s, (cx - ri - 1, cy - ri - 1))


def _draw_rect_glow(surf: pygame.Surface, rect: pygame.Rect, color: tuple,
                    alpha: int = 90, spread: int = 6):
    """Soft glow around a rectangle."""
    for i in range(spread, 0, -1):
        ai = alpha // (i + 1)
        r  = pygame.Rect(rect.x - i, rect.y - i, rect.w + i*2, rect.h + i*2)
        s  = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(s, (*color[:3], ai), s.get_rect(), 2)
        surf.blit(s, r.topleft)


def _pulsing(period: float, now: float, lo: float = 0.0, hi: float = 1.0) -> float:
    t = (math.sin(now * 2 * math.pi / period) + 1) / 2
    return lo + (hi - lo) * t


def _make_wall_bg(W: int, H: int) -> pygame.Surface:
    """Pre-rendered vertical gradient + subtle panel grid for wall view."""
    surf = pygame.Surface((W, H))
    for y in range(H):
        r = y / H
        c = (int(8 + 5 * r), int(11 + 7 * r), int(20 + 12 * r))
        pygame.draw.line(surf, c, (0, y), (W, y))
    for i in range(1, 12):
        x = int(i / 12 * W)
        pygame.draw.line(surf, (15, 21, 36), (x, 0), (x, H), 1)
    for j in range(1, 8):
        y = int(j / 8 * H)
        pygame.draw.line(surf, (13, 19, 33), (0, y), (W, y), 1)
    return surf


def _make_pitch_bg(W: int, H: int) -> pygame.Surface:
    """Pre-rendered top-down football pitch."""
    surf = pygame.Surface((W, H))
    n = 10
    sw = W // n
    for i in range(n + 1):
        c = GRASS_A if i % 2 == 0 else GRASS_B
        pygame.draw.rect(surf, c, (i * sw, 0, sw + 1, H))
    lw = 2
    bx, by = int(W * 0.03), int(H * 0.05)
    bw, bh = int(W * 0.94), int(H * 0.90)
    pygame.draw.rect(surf, PITCH_LINE, (bx, by, bw, bh), lw)
    pygame.draw.line(surf, PITCH_LINE, (W // 2, by), (W // 2, by + bh), lw)
    rc = int(min(bw, bh) * 0.13)
    pygame.draw.circle(surf, PITCH_LINE, (W // 2, H // 2), rc, lw)
    pygame.draw.circle(surf, PITCH_LINE, (W // 2, H // 2), 4)
    pa_w, pa_h = int(bw * 0.14), int(bh * 0.42)
    pa_y = (H - pa_h) // 2
    pygame.draw.rect(surf, PITCH_LINE, (bx, pa_y, pa_w, pa_h), lw)
    pygame.draw.rect(surf, PITCH_LINE, (bx + bw - pa_w, pa_y, pa_w, pa_h), lw)
    return surf


# ── Anatomical player silhouette ──────────────────────────────────────────────

def draw_player(surf: pygame.Surface, cx: float, cy_foot: float,
                h: float, color: tuple, *,
                highlight: Optional[str] = None,
                jersey_num: Optional[str] = None,
                lean: float = 0.0) -> dict:
    """
    Filled athletic player silhouette built from capsule shapes.
    lean: -1.0 (leaning left) to +1.0 (leaning right).
    Returns {'left': (px,py), 'right': (px,py)} foot pixel positions.
    """
    cx, cy_foot = int(cx), int(cy_foot)
    h = max(30, int(h))

    # Proportions
    head_r  = max(5, int(h * 0.078))
    head_rw = max(4, int(h * 0.066))
    nk_hw   = max(2, int(h * 0.032))
    nk_h    = max(2, int(h * 0.038))
    sh_hw   = max(5, int(h * 0.128))
    wst_hw  = max(3, int(h * 0.066))
    hip_hw  = max(4, int(h * 0.090))
    th_r    = max(2, int(h * 0.042))
    ca_r    = max(2, int(h * 0.032))
    ua_r    = max(2, int(h * 0.031))
    fa_r    = max(2, int(h * 0.025))
    ft_hw   = max(3, int(h * 0.052))
    ft_hh   = max(2, int(h * 0.022))

    # Vertical anchors from foot upward
    y_ft   = cy_foot
    y_kn   = cy_foot - int(h * 0.26)
    y_hip  = cy_foot - int(h * 0.49)
    y_wst  = cy_foot - int(h * 0.57)
    y_shl  = cy_foot - int(h * 0.83)
    y_nkt  = y_shl - nk_h
    y_hd   = y_nkt - head_r
    y_pit  = y_shl + int(h * 0.044)
    y_elb  = y_pit + int(h * 0.148)
    y_hnd  = y_elb + int(h * 0.128)

    # Lean shifts upper body
    lx = int(lean * h * 0.043)

    dark  = tuple(max(0, c - 65) for c in color)
    shoe  = (18, 20, 28)

    lf_x = cx - hip_hw // 2
    rf_x = cx + hip_hw // 2

    # Shoes
    pygame.draw.ellipse(surf, shoe,
        (lf_x - ft_hw, y_ft - ft_hh, ft_hw * 2, ft_hh * 2 + 2))
    pygame.draw.ellipse(surf, shoe,
        (rf_x - ft_hw, y_ft - ft_hh, ft_hw * 2, ft_hh * 2 + 2))

    # Calves
    _filled_capsule(surf, lf_x, y_ft,  lf_x, y_kn, ca_r, color)
    _filled_capsule(surf, rf_x, y_ft,  rf_x, y_kn, ca_r, color)

    # Thighs (shorts colour)
    _filled_capsule(surf, cx - hip_hw//2, y_kn, cx - hip_hw//2, y_hip, th_r, dark)
    _filled_capsule(surf, cx + hip_hw//2, y_kn, cx + hip_hw//2, y_hip, th_r, dark)

    # Shorts fill between thighs
    pygame.draw.polygon(surf, dark, [
        (cx - hip_hw - th_r + lx, y_hip),
        (cx + hip_hw + th_r + lx, y_hip),
        (cx + wst_hw + lx,        y_wst),
        (cx - wst_hw + lx,        y_wst),
    ])

    # Jersey torso
    pygame.draw.polygon(surf, color, [
        (cx - sh_hw + lx, y_shl),
        (cx + sh_hw + lx, y_shl),
        (cx + wst_hw + lx, y_wst),
        (cx - wst_hw + lx, y_wst),
    ])

    # Upper arms
    arm_sp = int(h * 0.036)
    _filled_capsule(surf, cx - sh_hw + ua_r + lx, y_pit,
                    cx - sh_hw - arm_sp + lx, y_elb, ua_r, color)
    _filled_capsule(surf, cx + sh_hw - ua_r + lx, y_pit,
                    cx + sh_hw + arm_sp + lx, y_elb, ua_r, color)

    # Forearms
    _filled_capsule(surf, cx - sh_hw - arm_sp + lx, y_elb,
                    cx - sh_hw - arm_sp // 2 + lx, y_hnd, fa_r, dark)
    _filled_capsule(surf, cx + sh_hw + arm_sp + lx, y_elb,
                    cx + sh_hw + arm_sp // 2 + lx, y_hnd, fa_r, dark)

    # Neck
    pygame.draw.rect(surf, color,
        (cx - nk_hw + lx, y_nkt - 2, nk_hw * 2, nk_h + 4))

    # Head
    pygame.draw.ellipse(surf, color,
        (cx - head_rw + lx, y_hd - head_r, head_rw * 2, int(head_r * 2.15)))

    # Jersey number
    if jersey_num is not None:
        fnt_sz = max(9, int(h * 0.125))
        fnt = pygame.font.SysFont("arial", fnt_sz, bold=True)
        ns = fnt.render(str(jersey_num), True, WHITE)
        chest_y = (y_shl + y_wst) // 2
        surf.blit(ns, (cx + lx - ns.get_width() // 2,
                       chest_y - ns.get_height() // 2))

    # Foot highlight
    for side, fx in [("left", lf_x), ("right", rf_x)]:
        if highlight == side:
            gr = max(6, int(h * 0.074))
            _draw_glow(surf, fx, y_ft, gr, YELLOW, alpha=160)
            pygame.draw.circle(surf, YELLOW, (fx, y_ft), gr)
            pygame.draw.circle(surf, WHITE,  (fx, y_ft), gr, 2)

    return {"left": (lf_x, y_ft), "right": (rf_x, y_ft)}


def draw_impact(surf: pygame.Surface, px: int, py: int,
                age: float, duration: float, color: tuple, max_r: int = 80):
    if age >= duration:
        return
    frac = age / duration
    if frac < 0.14:
        fl_r = int(28 * (1 - frac / 0.14))
        pygame.draw.circle(surf, WHITE, (px, py), fl_r)
    for k in range(3):
        offset = k * 0.11
        eff = max(0.0, frac - offset)
        if eff <= 0:
            continue
        norm  = eff / (1 - offset)
        r     = max(1, int(max_r * math.sqrt(norm + 0.01)))
        alpha = int(230 * (1 - norm))
        width = max(1, 3 - k)
        s = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color[:3], alpha), (r + 1, r + 1), r, width)
        surf.blit(s, (px - r - 1, py - r - 1))


def draw_cone(surf: pygame.Surface, cx: float, cy: float, r: float,
              color=CONE_C, shadow=True):
    if shadow:
        se = pygame.Surface((int(r * 1.6), int(r * 0.35)), pygame.SRCALPHA)
        pygame.draw.ellipse(se, (0, 0, 0, 70), se.get_rect())
        surf.blit(se, (int(cx - r * 0.8), int(cy + r * 0.66)))
    pts = [(int(cx),          int(cy - r)),
           (int(cx - r * 0.65), int(cy + r * 0.72)),
           (int(cx + r * 0.65), int(cy + r * 0.72))]
    pygame.draw.polygon(surf, color, pts)
    t = 0.38
    sx0 = cx + (-r * 0.65) * (1 - t)
    sx1 = cx + ( r * 0.65) * (1 - t)
    sy  = cy - r + r * 1.72 * t
    pygame.draw.line(surf, WHITE, (int(sx0), int(sy)), (int(sx1), int(sy)),
                     max(1, int(r * 0.14)))


# ── Impact FX + score popup ───────────────────────────────────────────────────

class ImpactFX:
    def __init__(self, px, py, color, duration=0.55, max_r=80):
        self.px, self.py = px, py
        self.color, self.duration, self.max_r = color, duration, max_r
        self.born = time.time()

    @property
    def alive(self):
        return time.time() - self.born < self.duration

    def draw(self, surf):
        draw_impact(surf, self.px, self.py,
                    time.time() - self.born, self.duration,
                    self.color, self.max_r)


class ScorePopup:
    """Floating text that rises and fades on score/miss."""
    def __init__(self, px, py, text, color, duration=0.85):
        self.px, self.py = px, py
        self.text, self.color, self.duration = text, color, duration
        self.born = time.time()

    @property
    def alive(self):
        return time.time() - self.born < self.duration

    def draw(self, surf):
        age  = time.time() - self.born
        frac = age / self.duration
        rise = int(55 * frac)
        a    = int(255 * (1 - frac) ** 1.5)
        fnt  = pygame.font.SysFont("arial", 30, bold=True)
        ts   = fnt.render(self.text, True, self.color)
        s    = pygame.Surface(ts.get_size(), pygame.SRCALPHA)
        s.blit(ts, (0, 0))
        s.set_alpha(a)
        surf.blit(s, (self.px - ts.get_width() // 2, self.py - rise - 18))


# ── Drill base class ──────────────────────────────────────────────────────────

class Drill:
    name     = "base"
    is_floor = False

    def reset(self): pass
    def update(self, dt: float, now: float): pass
    def draw(self, surf: pygame.Surface, W: int, H: int, uv2px, score: int, misses: int): pass
    def on_impact(self, u: float, v: float) -> str: return "ignore"
    def demo_ball_pos(self, now: float) -> Optional[Tuple[float, float]]: return None


# ════════════════════════════════════════════════════════════════════════════════
# 1. TARGET GRID
# ════════════════════════════════════════════════════════════════════════════════
class TargetGridDrill(Drill):
    name = "target_grid"
    ZONE_LABELS = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]

    def __init__(self, u_max, v_max, cols=3, rows=3):
        self.u_max, self.v_max = u_max, v_max
        u0, u1 = u_max * 0.08, u_max * 0.92
        v0, v1 = v_max * 0.06, v_max * 0.82
        cu, cv = (u1 - u0) / cols, (v1 - v0) / rows
        pu, pv = cu * 0.05, cv * 0.05
        self.cells = [
            (u0 + c*cu + pu, u0 + (c+1)*cu - pu,
             v0 + r*cv + pv, v0 + (r+1)*cv - pv)
            for r in range(rows) for c in range(cols)
        ]
        self.active_idx = -1
        self._demo_t    = 0.0
        self.reset()

    def reset(self):
        self.active_idx = -1
        self._pick()

    def _pick(self):
        prev = self.active_idx
        self.active_idx = random.choice([i for i in range(len(self.cells)) if i != prev])

    def on_impact(self, u, v):
        u0, u1, v0, v1 = self.cells[self.active_idx]
        if u0 <= u <= u1 and v0 <= v <= v1:
            self._pick()
            return "hit"
        return "miss"

    def demo_ball_pos(self, now):
        u0, u1, v0, v1 = self.cells[self.active_idx]
        if now - self._demo_t > 1.0 + random.random() * 0.5:
            self._demo_t = now
        frac = (now - self._demo_t) / 0.9
        if frac > 1:
            return None
        ut = (u0 + u1) / 2
        vt = (v0 + v1) / 2
        return ut * frac, vt * frac + self.v_max * 0.08 * (1 - frac)

    def draw(self, surf, W, H, uv2px, score, misses):
        now = time.time()
        for i, (u0, u1, v0, v1) in enumerate(self.cells):
            px0, py1 = uv2px(u0, v0)
            px1, py0 = uv2px(u1, v1)
            rect  = pygame.Rect(px0, py0, px1 - px0, py1 - py0)
            is_act = (i == self.active_idx)

            if is_act:
                # Animated fill
                pa = int(_pulsing(0.7, now, 22, 55))
                sf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                sf.fill((*ACTIVE, pa))
                surf.blit(sf, rect.topleft)
                _draw_rect_glow(surf, rect, ACTIVE, alpha=80, spread=6)
                pygame.draw.rect(surf, ACTIVE, rect, 3)
                color = ACTIVE
                fnt_sz = max(14, rect.w // 4)
            else:
                sf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                sf.fill((*DIM, 18))
                surf.blit(sf, rect.topleft)
                pygame.draw.rect(surf, DIM, rect, 1)
                color = DIM
                fnt_sz = max(12, rect.w // 5)

            fnt = pygame.font.SysFont("arial", fnt_sz, bold=True)
            lbl = fnt.render(self.ZONE_LABELS[i], True, color)
            surf.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                            rect.centery - lbl.get_height() // 2))


# ════════════════════════════════════════════════════════════════════════════════
# 2. PLAYER PASS — silhouettes, pass to the glowing foot
# ════════════════════════════════════════════════════════════════════════════════
class PlayerPassDrill(Drill):
    name = "player_pass"
    PLAYER_H_FRAC = 0.48

    def __init__(self, u_max, v_max):
        self.u_max, self.v_max = u_max, v_max
        anchors = [0.14, 0.30, 0.50, 0.68, 0.84]
        random.shuffle(anchors)
        teams = [TEAM_A, TEAM_A, TEAM_A, TEAM_B, TEAM_B]
        self.players = [
            {"team": t, "u_base": a * u_max,
             "phase": random.uniform(0, 2 * math.pi),
             "speed": random.uniform(0.05, 0.13),
             "amp":   u_max * random.uniform(0.04, 0.09)}
            for t, a in zip(teams, anchors)
        ]
        self.blue_idx      = [i for i, p in enumerate(self.players) if p["team"] == TEAM_A]
        self.target_player = None
        self.target_foot   = None
        self._target_u = self._target_v = 0.0
        self._foot_r   = v_max * 0.055
        self.reset()

    def reset(self):
        self._pick_target()

    def _pick_target(self):
        self.target_player = random.choice(self.blue_idx)
        self.target_foot   = random.choice(["left", "right"])

    def _player_u(self, p, now):
        return p["u_base"] + p["amp"] * math.sin(p["phase"] + now * p["speed"] * 2 * math.pi)

    def _player_vel(self, p, now):
        return (p["amp"] * p["speed"] * 2 * math.pi
                * math.cos(p["phase"] + now * p["speed"] * 2 * math.pi))

    def update(self, dt, now):
        p = self.players[self.target_player]
        u = self._player_u(p, now)
        foot_off = self.u_max * 0.028 * (-1 if self.target_foot == "left" else 1)
        self._target_u = u + foot_off
        self._target_v = 0.0

    def on_impact(self, u, v):
        if abs(u - self._target_u) < self._foot_r and v < self._foot_r * 2:
            self._pick_target()
            return "hit"
        return "miss"

    def demo_ball_pos(self, now):
        t0 = now % 1.5
        if t0 > 1.0:
            return None
        frac = t0 / 1.0
        return (self._target_u * frac,
                self._target_v + self.v_max * 0.07 * (1 - frac))

    def draw(self, surf, W, H, uv2px, score, misses):
        now  = time.time()
        h_px = H * self.PLAYER_H_FRAC
        for i, p in enumerate(self.players):
            u   = self._player_u(p, now)
            vel = self._player_vel(p, now)
            lean = max(-0.85, min(0.85, vel / (self.u_max * 0.025)))
            px, _  = uv2px(u, 0)
            _, py_foot = uv2px(0, 0)
            hl = self.target_foot if i == self.target_player else None
            draw_player(surf, px, py_foot, h_px, p["team"],
                        highlight=hl, jersey_num=str(i + 1), lean=lean)

        # Instruction banner
        fnt = pygame.font.SysFont("arial", 22, bold=True)
        foot_lbl = "LEFT FOOT" if self.target_foot == "left" else "RIGHT FOOT"
        txt = fnt.render(
            f"PASS  →  PLAYER {self.target_player + 1}   ·   {foot_lbl}",
            True, YELLOW)
        bx = W // 2 - txt.get_width() // 2 - 12
        bs = pygame.Surface((txt.get_width() + 24, txt.get_height() + 10), pygame.SRCALPHA)
        bs.fill((0, 0, 0, 130))
        surf.blit(bs, (bx, 10))
        surf.blit(txt, (bx + 12, 15))


# ════════════════════════════════════════════════════════════════════════════════
# 3. KEEPER
# ════════════════════════════════════════════════════════════════════════════════
class KeeperDrill(Drill):
    name = "keeper"
    GAP_THRESHOLD = 0.22

    def __init__(self, u_max, v_max):
        self.u_max, self.v_max = u_max, v_max
        self._keeper_u = u_max / 2
        self._speed    = u_max * 0.10
        self._dir      = 1
        self._gap_side = None
        self._gap_u0   = self._gap_u1 = 0.0
        self._gap_v0   = v_max * 0.05
        self._gap_v1   = v_max * 0.65
        self._dive_t   = -99.0

    def update(self, dt, now):
        self._keeper_u += self._dir * self._speed * dt
        if self._keeper_u < self.u_max * 0.15:
            self._dir = 1
        elif self._keeper_u > self.u_max * 0.85:
            self._dir = -1
        cf = self._keeper_u / self.u_max
        if cf < 0.5 - self.GAP_THRESHOLD:
            self._gap_side = "right"
            self._gap_u0   = self._keeper_u + self.u_max * 0.14
            self._gap_u1   = self.u_max * 0.94
        elif cf > 0.5 + self.GAP_THRESHOLD:
            self._gap_side = "left"
            self._gap_u0   = self.u_max * 0.06
            self._gap_u1   = self._keeper_u - self.u_max * 0.14
        else:
            self._gap_side = None

    def on_impact(self, u, v):
        if (self._gap_side
                and self._gap_u0 <= u <= self._gap_u1
                and self._gap_v0 <= v <= self._gap_v1):
            self._speed  = min(self._speed * 1.12, self.u_max * 0.35)
            self._dive_t = time.time()
            return "hit"
        return "miss"

    def demo_ball_pos(self, now):
        if not self._gap_side:
            return None
        t0 = now % 2.0
        if t0 > 1.2:
            return None
        frac  = t0 / 1.2
        u_tgt = (self._gap_u0 + self._gap_u1) / 2
        v_tgt = (self._gap_v0 + self._gap_v1) / 2
        return u_tgt * frac, v_tgt * frac + self.v_max * 0.1 * (1 - frac)

    def draw(self, surf, W, H, uv2px, score, misses):
        # Goal frame
        gx0, _ = uv2px(self.u_max * 0.04, 0)
        gx1, _ = uv2px(self.u_max * 0.96, 0)
        _, gy_cross = uv2px(0, self.v_max * 0.66)
        _, gy_bot   = uv2px(0, 0)
        pw = 5
        pygame.draw.line(surf, (200, 200, 200), (gx0, gy_cross), (gx0, gy_bot), pw)
        pygame.draw.line(surf, (200, 200, 200), (gx1, gy_cross), (gx1, gy_bot), pw)
        pygame.draw.line(surf, (200, 200, 200), (gx0, gy_cross), (gx1, gy_cross), pw)
        # Goal net lines
        for nx in range(gx0 + 30, gx1, 45):
            pygame.draw.line(surf, GRID_C, (nx, gy_cross), (nx, gy_bot), 1)
        for ny in range(gy_cross + 25, gy_bot, 35):
            pygame.draw.line(surf, GRID_C, (gx0, ny), (gx1, ny), 1)

        # Gap highlight
        if self._gap_side:
            gx0g, _ = uv2px(self._gap_u0, 0)
            gx1g, _ = uv2px(self._gap_u1, 0)
            _, gyv0 = uv2px(0, self._gap_v1)
            _, gyv1 = uv2px(0, self._gap_v0)
            rect = pygame.Rect(gx0g, gyv0, gx1g - gx0g, gyv1 - gyv0)
            pa   = int(_pulsing(0.75, time.time(), 28, 68))
            sf   = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            sf.fill((*ACTIVE, pa))
            surf.blit(sf, rect.topleft)
            _draw_rect_glow(surf, rect, ACTIVE, alpha=70, spread=5)
            pygame.draw.rect(surf, ACTIVE, rect, 2)
            fnt = pygame.font.SysFont("arial", 20, bold=True)
            lbl = fnt.render("SHOOT HERE", True, ACTIVE)
            surf.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                            rect.centery - lbl.get_height() // 2))

        # Keeper
        px, py_foot = uv2px(self._keeper_u, 0)
        h_px = H * 0.72
        lean = self._dir * 0.25
        draw_player(surf, px, py_foot, h_px, WHITE, jersey_num="1", lean=lean)
        arm_y  = int(py_foot - h_px * 0.65)
        span   = int(W * 0.16)
        pygame.draw.line(surf, WHITE, (px - span, arm_y), (px + span, arm_y), 6)

        # GOAL flash
        if time.time() - self._dive_t < 0.55:
            frac = (time.time() - self._dive_t) / 0.55
            a    = int(255 * (1 - frac))
            fnt2 = pygame.font.SysFont("arial", 56, bold=True)
            gt   = fnt2.render("GOAL!", True, YELLOW)
            gs   = pygame.Surface(gt.get_size(), pygame.SRCALPHA)
            gs.blit(gt, (0, 0))
            gs.set_alpha(a)
            surf.blit(gs, (W // 2 - gt.get_width() // 2, H // 3 - 20))


# ════════════════════════════════════════════════════════════════════════════════
# 4. MOVING TARGET
# ════════════════════════════════════════════════════════════════════════════════
class MovingTargetDrill(Drill):
    name     = "moving"
    INIT_SIZE = 280.0
    MIN_SIZE  = 70.0

    def __init__(self, u_max, v_max):
        self.u_max, self.v_max = u_max, v_max
        self.targets: list = []
        self._trail:  list = []
        self._spawn_one()

    def _spawn_one(self):
        m = self.INIT_SIZE
        self.targets.append({
            "u":    random.uniform(m, self.u_max - m),
            "v":    random.uniform(m, self.v_max * 0.75 - m),
            "vu":   random.choice([-1, 1]) * self.u_max * random.uniform(0.08, 0.15),
            "vv":   random.choice([-1, 1]) * self.v_max * random.uniform(0.05, 0.12),
            "size": self.INIT_SIZE,
        })

    def update(self, dt, now):
        for t in self.targets:
            t["u"] += t["vu"] * dt
            t["v"] += t["vv"] * dt
            half = t["size"] / 2
            if t["u"] - half < 0:              t["u"] = half;                 t["vu"] *= -1
            if t["u"] + half > self.u_max:     t["u"] = self.u_max - half;   t["vu"] *= -1
            if t["v"] - half < 0:              t["v"] = half;                 t["vv"] *= -1
            if t["v"] + half > self.v_max*0.80: t["v"] = self.v_max*0.80 - half; t["vv"] *= -1

    def on_impact(self, u, v):
        for t in self.targets:
            half = t["size"] / 2
            if abs(u - t["u"]) < half and abs(v - t["v"]) < half:
                t["size"] = max(self.MIN_SIZE, t["size"] * 0.75)
                t["vu"] *= -1.06
                t["vv"] *= -1.06
                if len(self.targets) < 3:
                    self._spawn_one()
                return "hit"
        return "miss"

    def demo_ball_pos(self, now):
        if not self.targets:
            return None
        t  = self.targets[0]
        t0 = now % 1.6
        if t0 > 1.1:
            return None
        frac = t0 / 1.1
        return t["u"] * frac, t["v"] * frac + self.v_max * 0.08 * (1 - frac)

    def draw(self, surf, W, H, uv2px, score, misses):
        now = time.time()
        for t in self.targets:
            half   = t["size"] / 2
            px0, py1 = uv2px(t["u"] - half, t["v"] - half)
            px1, py0 = uv2px(t["u"] + half, t["v"] + half)
            rect   = pygame.Rect(px0, py0, px1 - px0, py1 - py0)
            ratio  = (t["size"] - self.MIN_SIZE) / (self.INIT_SIZE - self.MIN_SIZE)
            r_col  = int(210 * ratio)
            g_col  = int(210 * (1 - ratio))
            color  = (r_col, g_col, 40)

            # Crosshair lines
            pygame.draw.line(surf, (*color, 120) if False else color,
                             (rect.centerx, rect.top), (rect.centerx, rect.bottom), 1)
            pygame.draw.line(surf, color,
                             (rect.left, rect.centery), (rect.right, rect.centery), 1)

            # Animated fill
            pa = int(_pulsing(0.6, now, 25, 60))
            sf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            sf.fill((*color, pa))
            surf.blit(sf, rect.topleft)
            _draw_rect_glow(surf, rect, color, alpha=60, spread=4)
            pygame.draw.rect(surf, color, rect, 2)

            fnt = pygame.font.SysFont("arial", max(12, int(rect.h * 0.28)), bold=True)
            lbl = fnt.render("HIT", True, color)
            surf.blit(lbl, (rect.centerx - lbl.get_width() // 2,
                            rect.centery - lbl.get_height() // 2))


# ════════════════════════════════════════════════════════════════════════════════
# 5. SEQUENCE
# ════════════════════════════════════════════════════════════════════════════════
class SequenceDrill(Drill):
    name = "sequence"
    N    = 5
    RAD  = 90

    def __init__(self, u_max, v_max):
        self.u_max, self.v_max = u_max, v_max
        self.positions: list = []
        self.step = 0
        self._best_time: Optional[float] = None
        self._round_start  = time.time()
        self._flash_wrong_t = -99.0
        self._flash_done_t  = -99.0
        self.reset()

    def reset(self):
        margin = self.RAD * 2.5
        self.positions = [
            (random.uniform(margin, self.u_max - margin),
             random.uniform(margin, self.v_max * 0.80 - margin))
            for _ in range(self.N)
        ]
        self.step = 0
        self._round_start = time.time()

    def on_impact(self, u, v):
        tu, tv = self.positions[self.step]
        if math.hypot(u - tu, v - tv) < self.RAD:
            self.step += 1
            if self.step >= self.N:
                elapsed = time.time() - self._round_start
                if self._best_time is None or elapsed < self._best_time:
                    self._best_time = elapsed
                self._flash_done_t = time.time()
                self.reset()
            return "hit"
        self._flash_wrong_t = time.time()
        self.step = 0
        return "miss"

    def demo_ball_pos(self, now):
        tu, tv = self.positions[self.step]
        t0 = now % 1.4
        if t0 > 0.9:
            return None
        frac = t0 / 0.9
        return tu * frac, tv * frac + self.v_max * 0.05 * (1 - frac)

    def draw(self, surf, W, H, uv2px, score, misses):
        now = time.time()
        # Connecting path lines
        for i in range(self.N - 1):
            ax, ay = uv2px(*self.positions[i])
            bx, by = uv2px(*self.positions[i + 1])
            pygame.draw.line(surf, (35, 48, 70), (ax, ay), (bx, by), 2)

        for i, (tu, tv) in enumerate(self.positions):
            px, py = uv2px(tu, tv)
            pr, _  = uv2px(tu + self.RAD, tv)
            r_px   = max(4, pr - px)

            is_curr = (i == self.step)
            is_done = (i < self.step)

            if is_done:
                color, bw = (40, 70, 50), 1
            elif is_curr:
                color, bw = ACTIVE, 3
                _draw_glow(surf, px, py, r_px, ACTIVE, alpha=100)
            else:
                color, bw = (55, 65, 95), 1

            if is_curr:
                pa = int(_pulsing(0.7, now, 18, 50))
                sc = pygame.Surface((r_px*2, r_px*2), pygame.SRCALPHA)
                pygame.draw.circle(sc, (*color, pa), (r_px, r_px), r_px)
                surf.blit(sc, (px - r_px, py - r_px))

            pygame.draw.circle(surf, color, (px, py), r_px, bw)
            fnt = pygame.font.SysFont("arial", int(r_px * 1.1), bold=True)
            lbl = fnt.render(str(i + 1), True, color)
            surf.blit(lbl, (px - lbl.get_width() // 2, py - lbl.get_height() // 2))

        # Flash overlays
        if now - self._flash_wrong_t < 0.30:
            a = int(75 * (1 - (now - self._flash_wrong_t) / 0.30))
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((180, 20, 20, a))
            surf.blit(s, (0, 0))

        if now - self._flash_done_t < 0.65:
            frac = (now - self._flash_done_t) / 0.65
            a    = int(255 * (1 - frac))
            bt   = f"   BEST {self._best_time:.1f}s" if self._best_time else ""
            fnt2 = pygame.font.SysFont("arial", 54, bold=True)
            gt   = fnt2.render(f"COMPLETE!{bt}", True, YELLOW)
            gs   = pygame.Surface(gt.get_size(), pygame.SRCALPHA)
            gs.blit(gt, (0, 0)); gs.set_alpha(a)
            surf.blit(gs, (W // 2 - gt.get_width() // 2, H // 2 - 35))

        fnt3 = pygame.font.SysFont("arial", 18, bold=True)
        prog = fnt3.render(f"STEP  {self.step} / {self.N}", True, WHITE)
        surf.blit(prog, (16, 14))


# ════════════════════════════════════════════════════════════════════════════════
# 6. FLOOR CONES
# ════════════════════════════════════════════════════════════════════════════════
class FloorConesDrill(Drill):
    name     = "cones"
    is_floor = True

    def __init__(self, u_max, v_max):
        self.u_max, self.v_max = u_max, v_max
        n = 7
        self.cones = [
            (u_max * (i + 1) / (n + 1),
             v_max / 2 + v_max * 0.19 * (1 if i % 2 == 0 else -1))
            for i in range(n)
        ]
        self.passed    = 0
        self._player_u = 0.0
        self._player_v = v_max / 2
        self._target   = 0

    def reset(self):
        self.passed    = 0
        self._player_u = 0.0
        self._player_v = self.v_max / 2
        self._target   = 0

    def update(self, dt, now):
        if self._target >= len(self.cones):
            return
        tu, tv = self.cones[self._target]
        du, dv = tu - self._player_u, tv - self._player_v
        dist   = math.hypot(du, dv)
        speed  = self.u_max * 0.25
        if dist < speed * dt:
            self._player_u, self._player_v = tu, tv
            self.passed  = self._target + 1
            self._target += 1
        else:
            self._player_u += (du / dist) * speed * dt
            self._player_v += (dv / dist) * speed * dt

    def on_impact(self, u, v):
        return "ignore"

    def draw(self, surf, W, H, uv2px, score, misses):
        # Path glow
        pts = [uv2px(u, v) for u, v in self.cones]
        if len(pts) > 1:
            pygame.draw.lines(surf, (45, 58, 45), False, pts, 3)

        # Cones
        for i, (cu, cv) in enumerate(self.cones):
            px, py = uv2px(cu, cv)
            color  = ACTIVE if i < self.passed else CONE_C
            draw_cone(surf, px, py, 16, color)

        # Arrow to next cone
        if self._target < len(self.cones):
            tu, tv = self.cones[self._target]
            tx, ty = uv2px(tu, tv)
            px, py = uv2px(self._player_u, self._player_v)
            dx, dy = tx - px, ty - py
            dist   = max(1, math.hypot(dx, dy))
            pygame.draw.line(surf, YELLOW, (px, py), (tx, ty), 2)

        # Player dot
        px, py = uv2px(self._player_u, self._player_v)
        r = 14
        pygame.draw.circle(surf, TEAM_A, (px, py), r)
        pygame.draw.circle(surf, WHITE,  (px, py), r, 2)
        fnt = pygame.font.SysFont("arial", 11, bold=True)
        n_lbl = fnt.render("10", True, WHITE)
        surf.blit(n_lbl, (px - n_lbl.get_width() // 2, py - n_lbl.get_height() // 2))

        fnt2 = pygame.font.SysFont("arial", 18, bold=True)
        lbl  = fnt2.render(f"CONES  {self.passed} / {len(self.cones)}", True, WHITE)
        surf.blit(lbl, (16, 14))


# ════════════════════════════════════════════════════════════════════════════════
# 7. PASSING LANES
# ════════════════════════════════════════════════════════════════════════════════
class FloorLanesDrill(Drill):
    name     = "lanes"
    is_floor = True

    def __init__(self, u_max, v_max):
        self.u_max, self.v_max = u_max, v_max
        cx, cy = u_max / 2, v_max / 2
        su, sv = u_max * 0.30, v_max * 0.30
        self.players = [
            (cx,      cy - sv, "9",  TEAM_A),
            (cx - su, cy,      "10", TEAM_A),
            (cx + su, cy,      "8",  TEAM_A),
            (cx,      cy + sv, "6",  TEAM_A),
        ]
        self.lanes: list      = []
        self._highlight: tuple = (0, 1, True)
        self._next_t = time.time()
        self._update_lanes()

    def _update_lanes(self):
        n     = len(self.players)
        pairs = [(i, j) for i in range(n) for j in range(n) if i < j]
        random.shuffle(pairs)
        self.lanes = [(i, j, random.random() > 0.35) for i, j in pairs[:5]]
        open_lanes = [l for l in self.lanes if l[2]]
        self._highlight = random.choice(open_lanes) if open_lanes else self.lanes[0]
        self._next_t    = time.time() + 3.0 + random.uniform(-0.5, 1.0)

    def update(self, dt, now):
        if now > self._next_t:
            self._update_lanes()

    def on_impact(self, u, v):
        return "ignore"

    def draw(self, surf, W, H, uv2px, score, misses):
        now = time.time()
        for fi, ti, open_ in self.lanes:
            fx, fy = uv2px(*self.players[fi][:2])
            tx, ty = uv2px(*self.players[ti][:2])
            is_hl  = ((fi, ti, open_) == self._highlight)
            if is_hl:
                # Dashed animated highlight
                pa = int(_pulsing(0.7, now, 160, 255))
                s  = pygame.Surface((W, H), pygame.SRCALPHA)
                pygame.draw.line(s, (*ACTIVE, pa), (fx, fy), (tx, ty), 4)
                surf.blit(s, (0, 0))
            elif open_:
                pygame.draw.line(surf, (65, 130, 75), (fx, fy), (tx, ty), 2)
            else:
                pygame.draw.line(surf, (100, 38, 38), (fx, fy), (tx, ty), 2)
                mx, my = (fx+tx)//2, (fy+ty)//2
                pygame.draw.line(surf, MISS_FX, (mx-9, my-9), (mx+9, my+9), 3)
                pygame.draw.line(surf, MISS_FX, (mx+9, my-9), (mx-9, my+9), 3)

        fnt = pygame.font.SysFont("arial", 15, bold=True)
        for pu, pv, label, color in self.players:
            px, py = uv2px(pu, pv)
            r = 20
            pygame.draw.circle(surf, color, (px, py), r)
            pygame.draw.circle(surf, WHITE,  (px, py), r, 2)
            lbl = fnt.render(label, True, WHITE)
            surf.blit(lbl, (px - lbl.get_width()//2, py - lbl.get_height()//2))

        fi, ti, _ = self._highlight
        fnt2 = pygame.font.SysFont("arial", 22, bold=True)
        txt  = fnt2.render(
            f"PASS:   #{self.players[fi][2]}  →  #{self.players[ti][2]}",
            True, ACTIVE)
        bx = W//2 - txt.get_width()//2 - 10
        bs = pygame.Surface((txt.get_width()+20, txt.get_height()+10), pygame.SRCALPHA)
        bs.fill((0, 0, 0, 130))
        surf.blit(bs, (bx, 10))
        surf.blit(txt, (bx + 10, 15))


# ── Drill registry ─────────────────────────────────────────────────────────────
DRILL_CLASSES = {
    "target_grid": TargetGridDrill,
    "player_pass": PlayerPassDrill,
    "keeper":      KeeperDrill,
    "moving":      MovingTargetDrill,
    "sequence":    SequenceDrill,
    "cones":       FloorConesDrill,
    "lanes":       FloorLanesDrill,
}


# ════════════════════════════════════════════════════════════════════════════════
# Main simulator
# ════════════════════════════════════════════════════════════════════════════════
class ProjectorSim:
    IMPACT_COOLDOWN = 0.40

    def __init__(self, wall="south", drill="target_grid",
                 W=1280, H=720, fullscreen=False, udp_port=None):
        assert wall in WALL_DEFS, f"Unknown wall: {wall}"
        self.wdef      = WALL_DEFS[wall]
        self.wall_name = wall
        self.W, self.H = W, H

        pygame.init()
        flags       = pygame.FULLSCREEN if fullscreen else 0
        self.screen = pygame.display.set_mode((W, H), flags)
        pygame.display.set_caption(f"Proxiball — {wall.capitalize()}")
        self.clock  = pygame.time.Clock()

        # Pre-render backgrounds
        self._wall_bg  = _make_wall_bg(W, H)
        self._pitch_bg = _make_pitch_bg(W, H)

        self._H_mat: Optional[np.ndarray] = None

        self.score  = 0
        self.misses = 0
        self.impacts: List[ImpactFX]    = []
        self.popups:  List[ScorePopup]  = []
        self._last_impact_t = -999.0
        self._miss_flash_t  = -999.0
        self.drill_active   = False

        self._ball_world: Optional[np.ndarray] = None
        self._prev_ball:  Optional[np.ndarray] = None
        self._ball_lock   = threading.Lock()
        self._running     = False

        self._drill_name = drill
        self._drill: Drill = self._make_drill(drill)

        if udp_port:
            self._start_udp(udp_port)

    # ── Coordinate mapping ───────────────────────────────────────────────────

    def set_homography(self, H: np.ndarray):
        self._H_mat = H.astype(np.float64)

    def _uv2px(self, u: float, v: float) -> Tuple[int, int]:
        if self._H_mat is not None:
            pt = self._H_mat @ np.array([u, v, 1.0])
            return int(pt[0] / pt[2]), int(pt[1] / pt[2])
        px = int(u / self.wdef["u_max"] * self.W)
        if self.wdef.get("invert_v", True):
            py = int((1.0 - v / self.wdef["v_max"]) * self.H)
        else:
            py = int(v / self.wdef["v_max"] * self.H)
        return px, py

    def _world_to_uv(self, x, y, z) -> Tuple[float, float]:
        u = y if self.wdef["u_axis"] == "Y" else x
        v = z if self.wdef.get("invert_v", True) else y
        return u, v

    def _crosses_wall(self, prev, curr) -> Optional[np.ndarray]:
        axis = {"X": 0, "Y": 1, "Z": 2}[self.wdef["fixed"]]
        fv   = float(self.wdef["fixed_val"])
        dp   = prev[axis] - fv
        dc   = curr[axis] - fv
        if (dp < 0 <= dc) or (dp > 0 >= dc):
            t = dp / (dp - dc)
            return prev + t * (curr - prev)
        return None

    # ── Drill management ─────────────────────────────────────────────────────

    def _make_drill(self, name: str) -> Drill:
        return DRILL_CLASSES[name](self.wdef["u_max"], self.wdef["v_max"])

    def _switch_drill(self, name: str):
        self._drill_name = name
        self._drill      = self._make_drill(name)
        self.score = self.misses = 0
        self.impacts.clear()
        self.popups.clear()
        self.drill_active = True
        pygame.display.set_caption(f"Proxiball — {self.wall_name} — {name}")

    # ── Impact ───────────────────────────────────────────────────────────────

    def _register_impact(self, x, y, z):
        now = time.time()
        if now - self._last_impact_t < self.IMPACT_COOLDOWN:
            return
        self._last_impact_t = now
        u, v   = self._world_to_uv(x, y, z)
        result = self._drill.on_impact(u, v) if self.drill_active else "ignore"
        px, py = self._uv2px(u, v)
        if result == "hit":
            self.score += 1
            self.impacts.append(ImpactFX(px, py, HIT_FX))
            self.popups.append(ScorePopup(px, py - 30, "+1", HIT_FX))
        elif result == "miss":
            self.misses += 1
            self.impacts.append(ImpactFX(px, py, MISS_FX))
            self.popups.append(ScorePopup(px, py - 30, "MISS", MISS_FX))
            self._miss_flash_t = now

    # ── UDP ──────────────────────────────────────────────────────────────────

    def _start_udp(self, port):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.settimeout(1.0)
        print(f"[UDP] Listening on :{port}")

        def _recv():
            while self._running:
                try:
                    data, _ = sock.recvfrom(8192)
                    pkt = json.loads(data.decode())
                except Exception:
                    continue
                ball = pkt.get("ball")
                if not ball:
                    continue
                curr = np.array([ball["x_mm"], ball["y_mm"], ball["z_mm"]], dtype=np.float64)
                with self._ball_lock:
                    prev, self._prev_ball, self._ball_world = self._prev_ball, curr, curr
                if prev is not None:
                    cross = self._crosses_wall(prev, curr)
                    if cross is not None:
                        self._register_impact(*cross)
            sock.close()

        self._running = True
        threading.Thread(target=_recv, daemon=True).start()

    # ── Demo ─────────────────────────────────────────────────────────────────

    def _demo_tick(self, state: dict, now: float):
        if not self.drill_active:
            return
        phase = state.get("phase", "idle")
        if phase == "idle":
            if now - state.get("t_idle", 0) < state.get("idle_dur", 0.6):
                return
            uv = self._drill.demo_ball_pos(now)
            if uv is None:
                state["t_idle"] = now
                return
            tu, tv = uv
            if self.wdef["u_axis"] == "Y":
                world_start = np.array([ARENA_X / 2, ARENA_Y / 2, ARENA_Z * 0.35])
                world_end   = np.array([float(self.wdef["fixed_val"]), tu, tv])
            else:
                world_start = np.array([ARENA_X / 2, ARENA_Y / 2, ARENA_Z * 0.35])
                world_end   = np.array([tu, float(self.wdef["fixed_val"]), tv])
            state.update({"phase": "fly", "start": world_start, "end": world_end,
                          "t0": now, "dur": 0.7 + random.random() * 0.4})
        elif phase == "fly":
            frac = min((now - state["t0"]) / state["dur"], 1.0)
            ball = state["start"] + frac * (state["end"] - state["start"])
            with self._ball_lock:
                self._ball_world = ball
            if frac >= 1.0:
                self._register_impact(*ball)
                state.update({"phase": "idle", "t_idle": now,
                              "idle_dur": 0.5 + random.random() * 0.7})

    # ── HUD ──────────────────────────────────────────────────────────────────

    def _draw_hud(self):
        # Bottom panel
        ph = 36
        ps = pygame.Surface((self.W, ph), pygame.SRCALPHA)
        ps.fill((6, 8, 18, 200))
        self.screen.blit(ps, (0, self.H - ph))
        pygame.draw.line(self.screen, (25, 35, 60),
                         (0, self.H - ph), (self.W, self.H - ph), 1)

        # Score chips
        fnt_big = pygame.font.SysFont("arial", 22, bold=True)
        fnt_sm  = pygame.font.SysFont("arial", 14)

        hit_txt  = fnt_big.render(f"{self.score}", True, HIT_FX)
        miss_txt = fnt_big.render(f"{self.misses}", True, MISS_FX)
        hit_lbl  = fnt_sm.render("HIT", True, (100, 160, 120))
        miss_lbl = fnt_sm.render("MISS", True, (160, 90, 90))

        y0 = self.H - ph + 5
        self.screen.blit(hit_lbl,  (18, y0 + 2))
        self.screen.blit(hit_txt,  (18 + hit_lbl.get_width() + 6, y0 - 2))
        x2 = 18 + hit_lbl.get_width() + 10 + hit_txt.get_width() + 20
        self.screen.blit(miss_lbl, (x2, y0 + 2))
        self.screen.blit(miss_txt, (x2 + miss_lbl.get_width() + 6, y0 - 2))

        # Centre info
        info = fnt_sm.render(
            f"{self.wall_name.upper()}  ·  {self._drill_name.replace('_', ' ').upper()}"
            f"  {'● DRILL' if self.drill_active else '○ STANDBY'}",
            True, (110, 125, 155))
        self.screen.blit(info, (self.W // 2 - info.get_width() // 2, y0 + 5))

        # Right: key hints
        hint = fnt_sm.render("1-8: drill   SPACE: pause   R: reset   Q: quit",
                              True, (65, 75, 100))
        self.screen.blit(hint, (self.W - hint.get_width() - 14, y0 + 5))

    def _draw_miss_flash(self):
        age = time.time() - self._miss_flash_t
        if age > 0.22:
            return
        a = int(70 * (1 - age / 0.22))
        s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        s.fill((160, 20, 20, a))
        self.screen.blit(s, (0, 0))

    def _draw_ball_dot(self):
        with self._ball_lock:
            bw = self._ball_world
        if bw is None:
            return
        u, v   = self._world_to_uv(*bw)
        px, py = self._uv2px(u, v)
        if 0 <= px <= self.W and 0 <= py <= self.H:
            _draw_glow(self.screen, px, py, 10, ORANGE, alpha=80, rings=2)
            pygame.draw.circle(self.screen, ORANGE, (px, py), 10)
            pygame.draw.circle(self.screen, WHITE,  (px, py), 10, 2)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self, demo=False):
        self._running     = True
        self.drill_active = True
        demo_state: dict  = {"phase": "idle", "t_idle": 0, "idle_dur": 0.3}
        prev_t            = time.time()
        key_map           = {
            pygame.K_1: "target_grid",
            pygame.K_2: "player_pass",
            pygame.K_3: "keeper",
            pygame.K_4: "moving",
            pygame.K_5: "sequence",
            pygame.K_6: "cones",
            pygame.K_7: "lanes",
        }

        while self._running:
            now = time.time()
            dt  = now - prev_t
            prev_t = now

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self._running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        self._running = False
                    elif ev.key == pygame.K_SPACE:
                        self.drill_active = not self.drill_active
                    elif ev.key == pygame.K_r:
                        self.score = self.misses = 0
                        self._drill.reset()
                        self.impacts.clear()
                        self.popups.clear()
                    elif ev.key in key_map:
                        self._switch_drill(key_map[ev.key])
                        demo_state = {"phase": "idle", "t_idle": now, "idle_dur": 0.3}

            if self.drill_active:
                self._drill.update(dt, now)
                if demo:
                    self._demo_tick(demo_state, now)

            # Background
            if self._drill.is_floor:
                self.screen.blit(self._pitch_bg, (0, 0))
            else:
                self.screen.blit(self._wall_bg, (0, 0))

            # Drill
            self._drill.draw(self.screen, self.W, self.H,
                             self._uv2px, self.score, self.misses)

            # Overlays (wall drills only)
            if not self._drill.is_floor:
                self._draw_ball_dot()
                self._draw_miss_flash()

            # FX
            self.impacts = [fx for fx in self.impacts if fx.alive]
            for fx in self.impacts:
                fx.draw(self.screen)

            self.popups = [p for p in self.popups if p.alive]
            for p in self.popups:
                p.draw(self.screen)

            self._draw_hud()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Proxiball projector simulator")
    ap.add_argument("--wall",       choices=list(WALL_DEFS), default="south")
    ap.add_argument("--drill",      choices=list(DRILL_CLASSES), default="target_grid")
    ap.add_argument("--width",      type=int, default=1280)
    ap.add_argument("--height",     type=int, default=720)
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--demo",       action="store_true",
                    help="Auto-simulate ball shots (no live pipeline needed)")
    ap.add_argument("--udp-port",   type=int, default=None,
                    help="UDP port to receive ball data from live pipeline")
    args = ap.parse_args()

    sim = ProjectorSim(
        wall=args.wall, drill=args.drill,
        W=args.width,   H=args.height,
        fullscreen=args.fullscreen,
        udp_port=args.udp_port,
    )
    sim.run(demo=args.demo)


if __name__ == "__main__":
    main()
