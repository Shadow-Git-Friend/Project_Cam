"""Optional SMPL avatar fitting and mesh rendering utilities."""

from .async_fitter import AsyncFitSnapshot, AsyncSmplFitter, anchor_vertices, pelvis_from_coco
from .coco_smpl_map import COCO_TO_SMPL, SMPL_JOINT_NAMES, SmplJointTargets, extract_smpl_targets
from .mesh_renderer import add_mesh_to_axes, draw_mesh_cv2, export_mesh, mesh_triangles
from .smpl_fit import (
    OptionalAvatarDependencyError,
    SmplFitConfig,
    SmplFitResult,
    SmplFitter,
    SmplSessionFitter,
)

__all__ = [
    "AsyncFitSnapshot",
    "AsyncSmplFitter",
    "anchor_vertices",
    "pelvis_from_coco",
    "COCO_TO_SMPL",
    "SMPL_JOINT_NAMES",
    "SmplJointTargets",
    "extract_smpl_targets",
    "mesh_triangles",
    "add_mesh_to_axes",
    "draw_mesh_cv2",
    "export_mesh",
    "OptionalAvatarDependencyError",
    "SmplFitConfig",
    "SmplFitResult",
    "SmplFitter",
    "SmplSessionFitter",
]
