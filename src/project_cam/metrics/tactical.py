"""Tactical KPIs: pitch control, team shape, PPDA, xT, pass networks.

numpy-only. Pitch frame: X along pitch length (0 = own goal line,
`pitch_length` = opponent goal line), Y along width, metres.

Pitch control here is the Voronoi (nearest-player) occupancy model — the
standard baseline (Efthimiou "Voronoi diagrams in football"). The
velocity-aware Spearman/Shaw model is a planned upgrade
(see ROADMAP.md, feat/tactical-engine); the API is grid-based so the upgrade
swaps the ownership kernel without changing callers.

xT (Expected Threat) implements Karun Singh's public formulation
(https://karun.in/blog/expected-threat.html): value iteration over a pitch
grid where each cell's threat is the probability mass of eventually scoring,

    xT(z) = s(z) * g(z) + m(z) * sum_z' T(z -> z') * xT(z')

with s/m the shoot/move choice probabilities, g the score probability and T
the move transition matrix, all estimated from event data. Fully original
code — no license exposure.
"""

from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# Pitch control / shape
# --------------------------------------------------------------------------

def voronoi_control(
    team_a_xy: np.ndarray,
    team_b_xy: np.ndarray,
    pitch_length: float = 105.0,
    pitch_width: float = 68.0,
    grid_step: float = 1.0,
) -> dict:
    """Fraction of pitch area closest to each team (nearest-player Voronoi).

    Returns {"team_a": float, "team_b": float, "grid": (H, W) int8 array}
    where grid cells are 0 for team A control, 1 for team B.
    """
    a = np.atleast_2d(np.asarray(team_a_xy, dtype=float))
    b = np.atleast_2d(np.asarray(team_b_xy, dtype=float))
    if a.size == 0 or b.size == 0:
        raise ValueError("both teams need at least one player")

    xs = np.arange(grid_step / 2, pitch_length, grid_step)
    ys = np.arange(grid_step / 2, pitch_width, grid_step)
    gx, gy = np.meshgrid(xs, ys)
    cells = np.stack([gx.ravel(), gy.ravel()], axis=1)  # (M, 2)

    def min_dist(players: np.ndarray) -> np.ndarray:
        diff = cells[:, None, :] - players[None, :, :]
        return np.min(np.linalg.norm(diff, axis=2), axis=1)

    owner = (min_dist(b) < min_dist(a)).astype(np.int8)  # 1 where B is closer
    frac_b = float(np.mean(owner))
    return {
        "team_a": 1.0 - frac_b,
        "team_b": frac_b,
        "grid": owner.reshape(len(ys), len(xs)),
    }


def convex_hull_area(points_xy: np.ndarray) -> float:
    """Area of the 2-D convex hull (Andrew's monotone chain + shoelace)."""
    pts = np.unique(np.asarray(points_xy, dtype=float).reshape(-1, 2), axis=0)
    if len(pts) < 3:
        return 0.0
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])

    lower: list[np.ndarray] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[np.ndarray] = []
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = np.asarray(lower[:-1] + upper[:-1])
    x, y = hull[:, 0], hull[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def team_shape(players_xy: np.ndarray) -> dict:
    """Compactness/shape descriptors for one team's outfield positions."""
    pts = np.asarray(players_xy, dtype=float)
    centroid = pts.mean(axis=0)
    return {
        "centroid_x": float(centroid[0]),
        "centroid_y": float(centroid[1]),
        "hull_area_m2": convex_hull_area(pts),
        "depth_m": float(pts[:, 0].max() - pts[:, 0].min()),
        "width_m": float(pts[:, 1].max() - pts[:, 1].min()),
        "spread_m": float(np.mean(np.linalg.norm(pts - centroid, axis=1))),
        "line_height_m": float(np.min(pts[:, 0])),  # deepest defender's X
    }


# --------------------------------------------------------------------------
# Pressing
# --------------------------------------------------------------------------

def ppda(opponent_passes: int, defensive_actions: int) -> float | None:
    """Passes allowed Per Defensive Action (lower = more intense pressing).

    Both counts must already be restricted to the pressing zone (conventionally
    the ~60% of the pitch furthest from the defending goal).
    """
    if defensive_actions <= 0:
        return None
    return opponent_passes / defensive_actions


# --------------------------------------------------------------------------
# Expected Threat (xT)
# --------------------------------------------------------------------------

def compute_xt(
    shoot_prob: np.ndarray,
    goal_prob: np.ndarray,
    transition: np.ndarray,
    n_iters: int = 50,
) -> np.ndarray:
    """Value-iterate the xT fixed point over a flattened pitch grid.

    shoot_prob, goal_prob: (M,) per-cell P(shoot | possession) and
        P(goal | shot). move_prob is implicitly 1 - shoot_prob.
    transition: (M, M) row-stochastic move matrix T[z, z'].
    """
    s = np.asarray(shoot_prob, dtype=float)
    g = np.asarray(goal_prob, dtype=float)
    tr = np.asarray(transition, dtype=float)
    m = 1.0 - s
    xt = np.zeros_like(s)
    for _ in range(n_iters):
        xt = s * g + m * (tr @ xt)
    return xt


def xt_of_action(xt_grid: np.ndarray, start_cell: int, end_cell: int) -> float:
    """xT value credited to a move action: threat gained by the ball's move."""
    return float(xt_grid[end_cell] - xt_grid[start_cell])


# --------------------------------------------------------------------------
# Pass networks
# --------------------------------------------------------------------------

def pass_network(passes: list[tuple[str, str]]) -> dict:
    """Degree centrality (+ betweenness when networkx is available).

    passes: list of (passer, receiver) IDs. Degree centrality is the player's
    share of pass involvements, normalised by (n_players - 1) as in networkx,
    so values are comparable across squad sizes.
    """
    players = sorted({p for edge in passes for p in edge})
    n = len(players)
    degree = {p: 0 for p in players}
    for frm, to in passes:
        degree[frm] += 1
        degree[to] += 1
    norm = max(n - 1, 1)
    result: dict = {
        "players": players,
        "edge_count": len(passes),
        "degree_centrality": {p: degree[p] / norm for p in players},
    }
    try:
        import networkx as nx

        graph = nx.DiGraph()
        graph.add_edges_from(passes)
        result["betweenness_centrality"] = nx.betweenness_centrality(graph)
    except ImportError:
        result["betweenness_centrality"] = None
    return result
