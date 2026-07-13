"""Closed-loop telemetry: shared structures for live pose-launcher integration.

The assessment package is offline-only. Closed-loop additions (event logging,
outcome scoring, drill orchestration) live here so the live/launcher path can
import them without dragging in the offline-only assessment tree.
"""

from .event_log import EVENT_TYPES, SCHEMA_VERSION, EventLogger
from .firing_line import (
    FIRING_LINE_GEOMETRY_ID,
    FIRING_LINE_SCHEMA,
    FiringLineDecision,
    evaluate_firing_line,
    evaluate_shot_clearance,
    sample_ballistic_path_mm,
    segment_distance_3d,
)
from .safety_gates import GateResult, evaluate_joint_gate

__all__ = [
    "EventLogger",
    "EVENT_TYPES",
    "SCHEMA_VERSION",
    "FIRING_LINE_GEOMETRY_ID",
    "FIRING_LINE_SCHEMA",
    "FiringLineDecision",
    "GateResult",
    "evaluate_firing_line",
    "evaluate_joint_gate",
    "evaluate_shot_clearance",
    "sample_ballistic_path_mm",
    "segment_distance_3d",
]
