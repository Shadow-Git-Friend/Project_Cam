"""C3D writer for Project_Cam 3D joint recordings.

Treats COCO-17 joints as virtual markers, writes a single-subject .c3d file
that Visual3D, Mokka, OpenSim (via TRC import in their pipelines), and most
biomechanics tooling can consume.

Units: millimetres throughout. The Project_Cam pipeline emits mm
(`triangulate_multi` and `frame_kinematics` are both mm), and we set
`POINT:UNITS = "mm"` so no scale conversion is needed downstream.

Missing joints (None / non-finite) are encoded as the standard C3D
invalid-marker convention (residual = -1, coordinates filled with NaN).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from ..joints import JOINT_NAMES

# Short uppercase labels keep us compatible with tools that historically clipped
# at 4 chars (legacy C3D readers). ezc3d itself accepts longer strings.
JOINT_C3D_LABELS: list[str] = [
    "NOSE",  # nose
    "LEYE",  # left_eye
    "REYE",  # right_eye
    "LEAR",  # left_ear
    "REAR",  # right_ear
    "LSHO",  # left_shoulder
    "RSHO",  # right_shoulder
    "LELB",  # left_elbow
    "RELB",  # right_elbow
    "LWRI",  # left_wrist
    "RWRI",  # right_wrist
    "LHIP",  # left_hip
    "RHIP",  # right_hip
    "LKNE",  # left_knee
    "RKNE",  # right_knee
    "LANK",  # left_ankle
    "RANK",  # right_ankle
]

assert len(JOINT_C3D_LABELS) == len(JOINT_NAMES), "label list must mirror COCO-17 joints"


def write_c3d(
    frames: list[dict[str, Any]],
    output_path: str | Path,
    fps: float,
    subject_id: str,
    session_id: str | None = None,
) -> Path:
    """Write a list of normalized frames (from `io.load_motion`) to a C3D file.

    Returns the absolute output path. Raises if `frames` is empty.
    """
    if not frames:
        raise ValueError("write_c3d requires at least one frame")
    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps!r}")

    # Lazy import: ezc3d is a heavy native dependency; only load when actually used.
    import ezc3d  # type: ignore

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_joints = len(JOINT_NAMES)
    n_frames = len(frames)
    # ezc3d expects shape (4, n_points, n_frames): rows 0..2 = XYZ, row 3 = residual.
    points = np.zeros((4, n_joints, n_frames), dtype=np.float64)

    for frame_idx, frame in enumerate(frames):
        joint_xyz_list = frame.get("joints") or []
        joint_conf_list = frame.get("joint_conf") or []
        for j_idx in range(n_joints):
            xyz = joint_xyz_list[j_idx] if j_idx < len(joint_xyz_list) else None
            if xyz is None:
                points[:3, j_idx, frame_idx] = float("nan")
                points[3, j_idx, frame_idx] = -1.0  # standard C3D invalid-marker residual
                continue
            try:
                x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
            except (TypeError, ValueError, IndexError):
                points[:3, j_idx, frame_idx] = float("nan")
                points[3, j_idx, frame_idx] = -1.0
                continue
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                points[:3, j_idx, frame_idx] = float("nan")
                points[3, j_idx, frame_idx] = -1.0
                continue
            points[0, j_idx, frame_idx] = x
            points[1, j_idx, frame_idx] = y
            points[2, j_idx, frame_idx] = z
            # Conf is in [0, 1]; map to a residual proxy (0 = perfect). We use 0 for
            # any valid sample because ezc3d/c3d consumers expect residual >= 0 for
            # valid markers; downstream tools that read residual literally would
            # otherwise infer noise from our pose-detector confidence which is not
            # measured in the same units.
            try:
                conf = float(joint_conf_list[j_idx]) if j_idx < len(joint_conf_list) else 1.0
            except (TypeError, ValueError):
                conf = 1.0
            # Even an unconfident-but-present joint stays valid; we surface
            # confidence in the JSON report and per-rep metrics elsewhere.
            points[3, j_idx, frame_idx] = 0.0
            del conf

    c3d = ezc3d.c3d()
    c3d["parameters"]["POINT"]["RATE"]["value"] = [float(fps)]
    c3d["parameters"]["POINT"]["UNITS"]["value"] = ["mm"]
    c3d["parameters"]["POINT"]["LABELS"]["value"] = list(JOINT_C3D_LABELS)
    c3d["parameters"]["POINT"]["DESCRIPTIONS"]["value"] = list(JOINT_NAMES)

    # Subject metadata (optional but biomech-lab consumers like to see it).
    if "SUBJECTS" not in c3d["parameters"]:
        c3d.add_parameter("SUBJECTS", "NAMES", [subject_id])
    else:
        c3d["parameters"]["SUBJECTS"]["NAMES"]["value"] = [subject_id]

    # Custom META group for Project_Cam provenance.
    meta_params = {
        "SOURCE": ["project_cam"],
        "SCHEMA_VERSION": ["project_cam.c3d_writer.v1"],
    }
    if session_id is not None:
        meta_params["SESSION_ID"] = [str(session_id)]
    for key, value in meta_params.items():
        c3d.add_parameter("META", key, value)

    c3d["data"]["points"] = points

    c3d.write(str(out_path))
    return out_path.resolve()
