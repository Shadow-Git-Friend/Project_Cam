"""Shared launcher math and correction helpers.

Extracted from the active launcher scripts without changing behavior.
"""

import json
import math
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np


def forward_right_vectors_from_yaw(yaw_deg: float) -> Tuple[np.ndarray, np.ndarray]:
    yaw = math.radians(yaw_deg)
    fwd = np.array([math.cos(yaw), math.sin(yaw), 0.0], dtype=np.float64)
    right = np.array([fwd[1], -fwd[0], 0.0], dtype=np.float64)
    return fwd, right


def world_to_launcher_xy_delta(
    target_xyz_mm: np.ndarray,
    launcher_xyz_mm: np.ndarray,
    launcher_yaw_deg: float,
) -> Tuple[float, float, float]:
    d = np.asarray(target_xyz_mm, dtype=np.float64) - np.asarray(launcher_xyz_mm, dtype=np.float64)
    fwd, right = forward_right_vectors_from_yaw(launcher_yaw_deg)
    x_lat_mm = float(np.dot(d[:2], right[:2]))
    y_fwd_mm = float(np.dot(d[:2], fwd[:2]))
    dz_mm = float(d[2])
    return x_lat_mm / 1000.0, y_fwd_mm / 1000.0, dz_mm / 1000.0


def solve_angles_ballistic(
    x_lat_m: float,
    y_fwd_m: float,
    dz_m: float,
    v_ms: float,
    g: float = 9.81,
) -> Optional[Tuple[float, float]]:
    if y_fwd_m <= 0.15:
        return None
    d = math.sqrt(x_lat_m * x_lat_m + y_fwd_m * y_fwd_m)
    if d <= 1e-6:
        return None
    h_deg = math.degrees(math.atan2(x_lat_m, y_fwd_m))
    disc = v_ms**4 - g * (g * d**2 + 2.0 * dz_m * v_ms**2)
    if disc < 0.0:
        return None
    v_rad = math.atan((v_ms**2 - math.sqrt(disc)) / (g * d))
    return math.degrees(v_rad), h_deg


def load_correction_model(path: str) -> Optional[Dict]:
    if not path:
        return None
    try:
        with open(Path(path), "r") as f:
            data = json.load(f)
        model = {
            "bias": np.array([
                data["global_bias_add_mm"]["x"],
                data["global_bias_add_mm"]["y"],
                data["global_bias_add_mm"]["z"],
            ], dtype=np.float64),
        }
        if "axis_linear_gt_from_est" in data:
            model["linear"] = data["axis_linear_gt_from_est"]
        return model
    except Exception as e:
        print(f"[WARN] Could not load correction model {path}: {e}")
        return None


def apply_correction(xyz_mm: np.ndarray, model: Optional[Dict], mode: str = "linear") -> np.ndarray:
    if model is None or mode == "none":
        return np.array(xyz_mm, dtype=np.float64, copy=True)
    xyz = np.array(xyz_mm, dtype=np.float64)
    if mode == "bias":
        return xyz + model["bias"]
    if mode == "linear" and "linear" in model:
        lin = model["linear"]
        for i, ax in enumerate(["x", "y", "z"]):
            if ax in lin:
                xyz[i] = lin[ax]["a"] * xyz[i] + lin[ax]["b"]
        return xyz
    return xyz + model["bias"]
