"""Mesh rendering helpers for SMPL avatar output."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np


def mesh_triangles(vertices_mm, faces) -> np.ndarray:
    """Return face-indexed triangles with shape ``(n_faces, 3, 3)``."""

    vertices = np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 3)
    face_idx = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if len(face_idx) == 0:
        return np.empty((0, 3, 3), dtype=np.float64)
    return vertices[face_idx]


def add_mesh_to_axes(
    ax,
    vertices_mm,
    faces,
    *,
    alpha: float = 0.35,
    facecolor: str = "#d8d8d8",
    edgecolor: str = "none",
    max_faces: Optional[int] = None,
):
    """Add a triangular mesh to a matplotlib 3D axes and return the collection."""

    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    triangles = mesh_triangles(vertices_mm, _sample_faces(faces, max_faces))
    body = Poly3DCollection(
        triangles,
        alpha=float(alpha),
        facecolors=facecolor,
        edgecolors=edgecolor,
    )
    ax.add_collection3d(body)
    return body


def draw_mesh_cv2(
    img: np.ndarray,
    vertices_mm,
    faces,
    project_fn: Callable,
    *,
    color_bgr: tuple[int, int, int] = (220, 220, 216),
    edge_bgr: tuple[int, int, int] | None = None,
    alpha: float = 0.45,
    max_faces: Optional[int] = 1500,
) -> np.ndarray:
    """Project and draw a triangular mesh into an existing OpenCV BGR frame."""

    vertices = np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 3)
    face_idx = _sample_faces(faces, max_faces)
    if len(vertices) == 0 or len(face_idx) == 0:
        return img
    screen, ok = project_fn(vertices)
    overlay = img.copy()
    z_values = vertices[:, 2]
    face_depth = np.nanmean(z_values[face_idx], axis=1)
    order = np.argsort(face_depth)
    for face_i in order:
        face = face_idx[face_i]
        if not np.all(ok[face]):
            continue
        poly = np.asarray(screen[face], dtype=np.int32)
        cv2.fillConvexPoly(overlay, poly, color_bgr, cv2.LINE_AA)
        if edge_bgr is not None:
            cv2.polylines(overlay, [poly], True, edge_bgr, 1, cv2.LINE_AA)
    a = float(np.clip(alpha, 0.0, 1.0))
    cv2.addWeighted(overlay, a, img, 1.0 - a, 0.0, img)
    return img


def export_mesh(vertices_mm, faces, path) -> Path:
    """Export an avatar mesh using trimesh and return the written path."""

    try:
        import trimesh  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        from .smpl_fit import OptionalAvatarDependencyError

        raise OptionalAvatarDependencyError(
            "Install trimesh to export SMPL avatar meshes"
        ) from exc
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vertices = np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 3)
    face_idx = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=vertices, faces=face_idx, process=False)
    mesh.export(str(out_path))
    return out_path


def _sample_faces(faces, max_faces: Optional[int]) -> np.ndarray:
    face_idx = np.asarray(faces, dtype=np.int64).reshape(-1, 3)
    if max_faces is None or int(max_faces) <= 0 or len(face_idx) <= int(max_faces):
        return face_idx
    step = max(1, int(np.ceil(len(face_idx) / float(max_faces))))
    return face_idx[::step]
