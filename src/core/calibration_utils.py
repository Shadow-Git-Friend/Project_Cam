"""Shared helpers for reading camera calibration files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import numpy as np


@dataclass
class Intrinsics:
    camera: str
    matrix: np.ndarray
    dist_coeffs: np.ndarray
    image_size: tuple[int, int]
    board: Dict
    dictionary: str


@dataclass
class ExtrinsicTransform:
    camera: str
    reference: str
    matrix: np.ndarray
    rotation_vector: np.ndarray
    translation_vector: np.ndarray
    num_observations: int
    rotation_std_deg: float
    translation_std_m: float


def _read_json(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"Calibration file not found: {path}")
    return json.loads(path.read_text())


def load_intrinsics(
    camera: str,
    base_dir: Path | str = Path("calibration_results"),
) -> Intrinsics:
    base_dir = Path(base_dir)
    data = _read_json(base_dir / f"{camera}_intrinsics.json")
    return Intrinsics(
        camera=data["camera"],
        matrix=np.array(data["camera_matrix"], dtype=np.float64),
        dist_coeffs=np.array(data["distortion_coefficients"], dtype=np.float64),
        image_size=tuple(data["image_size"]),
        board=data["board"],
        dictionary=data.get("dictionary", "DICT_4X4_50"),
    )


def load_all_intrinsics(base_dir: Path | str = Path("calibration_results")) -> Dict[str, Intrinsics]:
    base_dir = Path(base_dir)
    intrinsics: Dict[str, Intrinsics] = {}
    for path in sorted(base_dir.glob("*_intrinsics.json")):
        cam_name = path.stem.replace("_intrinsics", "")
        intrinsics[cam_name] = load_intrinsics(cam_name, base_dir)
    if not intrinsics:
        raise RuntimeError(f"No intrinsics json files found under {base_dir}")
    return intrinsics


def load_extrinsics(path: Path | str = Path("calibration_results/extrinsics.json")) -> Dict[str, ExtrinsicTransform]:
    data = _read_json(Path(path))
    reference = data.get("reference_camera")
    transforms = {}
    for cam_name, payload in data.get("transforms", {}).items():
        transforms[cam_name] = ExtrinsicTransform(
            camera=cam_name,
            reference=reference,
            matrix=np.array(payload["matrix"], dtype=np.float64),
            rotation_vector=np.array(payload["rotation_vector"], dtype=np.float64),
            translation_vector=np.array(payload["translation_vector"], dtype=np.float64),
            num_observations=int(payload.get("num_observations", 0)),
            rotation_std_deg=float(payload.get("rotation_std_deg", 0.0)),
            translation_std_m=float(payload.get("translation_std_m", 0.0)),
        )
    if not transforms:
        raise RuntimeError("Extrinsics file does not contain any transforms")
    return transforms


def get_transform(
    target_camera: str,
    transforms: Dict[str, ExtrinsicTransform],
    reference_camera: Optional[str] = None,
) -> np.ndarray:
    if target_camera not in transforms:
        raise KeyError(f"Camera '{target_camera}' missing from extrinsics.")
    transform = transforms[target_camera]
    if reference_camera and transform.reference != reference_camera:
        raise ValueError(
            f"Extrinsics reference ({transform.reference}) does not match requested reference ({reference_camera})."
        )
    return transform.matrix


def compose_to_reference(
    camera: str,
    transforms: Dict[str, ExtrinsicTransform],
) -> np.ndarray:
    """Return 4x4 transform from reference to the given camera."""
    return np.array(transforms[camera].matrix, dtype=np.float64)


def invert_transform(transform: np.ndarray) -> np.ndarray:
    R = transform[:3, :3]
    t = transform[:3, 3]
    inv = np.eye(4, dtype=np.float64)
    inv[:3, :3] = R.T
    inv[:3, 3] = -R.T @ t
    return inv


# --- HOMOGRAPHY UTILITIES (for 2D goal detection) ---

@dataclass
class Homography:
    """Stores homography matrix and metadata."""
    camera: str
    matrix: np.ndarray
    src_points: np.ndarray  # Image coordinates
    dst_points: np.ndarray  # Wall coordinates
    wall_size: tuple[float, float]  # (width, height) in cm


def save_homography(
    camera: str,
    H: np.ndarray,
    src_points: np.ndarray,
    dst_points: np.ndarray,
    wall_size: tuple[float, float],
    base_dir: Path | str = Path("config"),
) -> Path:
    """Save homography matrix and metadata to files."""
    base_dir = Path(base_dir)
    base_dir.mkdir(exist_ok=True)
    
    # Save matrix as .npy
    matrix_path = base_dir / f"{camera}_homography.npy"
    np.save(matrix_path, H)
    
    # Save metadata as .json
    meta = {
        "camera": camera,
        "src_points": src_points.tolist(),
        "dst_points": dst_points.tolist(),
        "wall_width_cm": wall_size[0],
        "wall_height_cm": wall_size[1],
    }
    meta_path = base_dir / f"{camera}_homography.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    
    return matrix_path


def load_homography(
    camera: str,
    base_dir: Path | str = Path("config"),
) -> Homography:
    """Load homography matrix and metadata."""
    base_dir = Path(base_dir)
    
    matrix_path = base_dir / f"{camera}_homography.npy"
    meta_path = base_dir / f"{camera}_homography.json"
    
    if not matrix_path.exists():
        raise FileNotFoundError(f"Homography matrix not found: {matrix_path}")
    
    H = np.load(matrix_path)
    
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        return Homography(
            camera=camera,
            matrix=H,
            src_points=np.array(meta["src_points"], dtype=np.float32),
            dst_points=np.array(meta["dst_points"], dtype=np.float32),
            wall_size=(meta["wall_width_cm"], meta["wall_height_cm"]),
        )
    else:
        # Fallback with no metadata
        return Homography(
            camera=camera,
            matrix=H,
            src_points=np.zeros((4, 2), dtype=np.float32),
            dst_points=np.zeros((4, 2), dtype=np.float32),
            wall_size=(450.0, 200.0),
        )


def transform_point(
    point: tuple[float, float],
    H: np.ndarray,
) -> np.ndarray:
    """Transform a 2D point using homography matrix."""
    pt = np.array([[[point[0], point[1]]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt, H)
    return transformed[0][0]


def inverse_transform_point(
    point: tuple[float, float],
    H: np.ndarray,
) -> np.ndarray:
    """Transform from wall coordinates back to image coordinates."""
    H_inv = np.linalg.inv(H)
    return transform_point(point, H_inv)


# Import cv2 for homography functions
try:
    import cv2
except ImportError:
    pass  # cv2 only needed for transform functions

