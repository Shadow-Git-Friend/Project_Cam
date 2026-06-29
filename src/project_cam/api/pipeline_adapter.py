"""Hardware-free adapter between the HTTP layer and the geometry core.

Loads camera/calibration profiles and wraps ``project_cam.geometry`` so the API
reuses the exact triangulation and Kalman code the live pipeline uses. Pure
Python (numpy + PyYAML) -- importable and testable without FastAPI, pydantic, or
any camera/GPU.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from project_cam.geometry import JointKalmanFilter, triangulate_multi

# Repo root: .../src/project_cam/api/pipeline_adapter.py -> parents[3].
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _config_dir() -> Path:
    return Path(os.environ.get("PROJECT_CAM_CONFIG_DIR", _REPO_ROOT / "configs"))


# Friendly profile aliases -> config file under configs/cameras/.
_PROFILE_FILES = {
    "usb6": "cameras_6cam_usb.yaml",
    "6cam": "cameras_6cam_usb.yaml",
    "arena_fixed_4cam": "cameras_4cam.yaml",
    "4cam": "cameras_4cam.yaml",
}

DEFAULT_PROFILE = os.environ.get("PROJECT_CAM_CAMERA_PROFILE", "usb6")
FALLBACK_PROFILE = "arena_fixed_4cam"


@dataclass(frozen=True)
class CameraProfile:
    """Parsed camera profile (geometry + roster + validation state)."""

    profile: str
    camera_count: int
    units: str
    status: str  # "validated" | "prototype"
    cameras: Dict[str, dict]
    arena_dimensions_mm: Dict[str, float] = field(default_factory=dict)
    geometry: Dict[str, object] = field(default_factory=dict)
    source_path: Optional[str] = None

    @property
    def validated(self) -> bool:
        return self.status == "validated"

    def camera_ids(self) -> List[str]:
        return list(self.cameras.keys())


def _resolve_profile_path(profile_or_path: str) -> Path:
    # Direct path wins.
    p = Path(profile_or_path)
    if p.suffix in {".yaml", ".yml"} and p.exists():
        return p
    fname = _PROFILE_FILES.get(profile_or_path)
    if fname is None:
        raise KeyError(
            f"unknown camera profile {profile_or_path!r}; "
            f"known: {sorted(_PROFILE_FILES)}")
    return _config_dir() / "cameras" / fname


def load_camera_profile(profile_or_path: str = DEFAULT_PROFILE) -> CameraProfile:
    """Load and validate a camera profile by alias or explicit YAML path."""
    path = _resolve_profile_path(profile_or_path)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    cameras = data.get("cameras") or {}
    if not isinstance(cameras, dict) or not cameras:
        raise ValueError(f"{path}: missing non-empty 'cameras' mapping")

    declared = data.get("camera_count")
    actual = len(cameras)
    if declared is not None and int(declared) != actual:
        raise ValueError(
            f"{path}: camera_count={declared} but {actual} cameras listed")

    return CameraProfile(
        profile=str(data.get("profile", profile_or_path)),
        camera_count=actual,
        units=str(data.get("units", "mm")),
        status=str(data.get("status", "prototype")),
        cameras=cameras,
        arena_dimensions_mm=data.get("arena_dimensions_mm") or {},
        geometry=data.get("geometry") or {},
        source_path=str(path),
    )


def list_profiles() -> List[str]:
    """Profiles whose config file is present on disk."""
    out = []
    seen = set()
    for alias, fname in _PROFILE_FILES.items():
        if fname in seen:
            continue
        if (_config_dir() / "cameras" / fname).exists():
            out.append(alias)
            seen.add(fname)
    return out


def _as_proj_mat(value) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float64)
    if arr.shape != (3, 4):
        raise ValueError(f"projection matrix must be 3x4, got {arr.shape}")
    return arr


def triangulate_observations(
    observations: Dict[str, Tuple[float, float]],
    proj_mats: Dict[str, object],
    *,
    min_cameras: int = 2,
) -> Tuple[Optional[np.ndarray], List[str]]:
    """Triangulate one world point from normalized observations.

    Only cameras present in BOTH ``observations`` and ``proj_mats`` contribute.
    Returns ``(point_mm | None, contributing_camera_ids)``. Delegates to
    ``project_cam.geometry.triangulate_multi`` -- no triangulation math here.
    """
    usable = {c: observations[c] for c in observations if c in proj_mats}
    if len(usable) < min_cameras:
        return None, sorted(usable.keys())
    proj = {c: _as_proj_mat(proj_mats[c]) for c in usable}
    point = triangulate_multi(usable, proj)
    if point is None:
        return None, sorted(usable.keys())
    return point, sorted(usable.keys())


def run_kalman_track(
    track: List[List[float]],
    *,
    dt: float = 1.0 / 15.0,
    process_noise: float = 500.0,
    measurement_noise: float = 10.0,
    predict_ahead_ms: float = 400.0,
) -> dict:
    """Filter a submitted 3D track and lead-predict ``predict_ahead_ms`` ahead.

    Reuses ``JointKalmanFilter`` (the live predictive-targeting filter). Pure
    function over a list of ``[x, y, z]`` mm points; does not touch live state.
    """
    if not track:
        raise ValueError("track must contain at least one [x, y, z] point")
    kf = JointKalmanFilter(
        process_noise=process_noise, measurement_noise=measurement_noise, dt=dt)
    for i, pt in enumerate(track):
        p = np.asarray(pt, dtype=np.float64)
        if p.shape[0] < 3:
            raise ValueError(f"track[{i}] must have 3 coordinates")
        if i > 0:
            kf.predict_step(dt)
        kf.update_step(p[:3])
    ahead_s = predict_ahead_ms / 1000.0
    return {
        "filtered_position_mm": kf.get_position().tolist(),
        "velocity_mm_s": kf.get_velocity().tolist(),
        "predicted_position_mm": kf.predict_ahead(ahead_s).tolist(),
        "prediction_uncertainty_mm": kf.prediction_uncertainty(ahead_s),
        "predict_ahead_ms": predict_ahead_ms,
        "samples": len(track),
    }
