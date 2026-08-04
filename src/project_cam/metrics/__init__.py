"""Academy metrics package: camera-derived football KPIs.

Six KPI families (see METRICS.md): physical load, biomechanics, technical,
tactical, cognitive/scanning, injury & readiness. This package implements the
signal->number layer; upstream detection/tracking/pose services provide the
signals (pitch-frame trajectories, 3D joints, event lists).

Design constraints:
- numpy-only (no scipy/pandas/networkx hard deps) so the package imports on
  the minimal `pip install -e .` surface that CI gates.
- Every published number carries an uncertainty or confidence field; callers
  must not strip it (see .claude/rules — "no metric without confidence").
- All positions in metres in the pitch frame, timestamps in seconds.
"""

from project_cam.metrics.acwr import AcwrResult, acwr
from project_cam.metrics.biomech import (
    asymmetry_index,
    kick_foot_speed,
    stride_metrics,
)
from project_cam.metrics.physical import (
    ACCEL_THRESHOLD_MPS2,
    HSR_THRESHOLD_KMH,
    SPRINT_THRESHOLD_KMH,
    PhysicalLoadSummary,
    physical_load,
)
from project_cam.metrics.report import render_session_report
from project_cam.metrics.tactical import (
    compute_xt,
    convex_hull_area,
    pass_network,
    ppda,
    team_shape,
    voronoi_control,
    xt_of_action,
)

__all__ = [
    "ACCEL_THRESHOLD_MPS2",
    "HSR_THRESHOLD_KMH",
    "SPRINT_THRESHOLD_KMH",
    "AcwrResult",
    "PhysicalLoadSummary",
    "acwr",
    "asymmetry_index",
    "compute_xt",
    "convex_hull_area",
    "kick_foot_speed",
    "pass_network",
    "physical_load",
    "ppda",
    "render_session_report",
    "stride_metrics",
    "team_shape",
    "voronoi_control",
    "xt_of_action",
]
