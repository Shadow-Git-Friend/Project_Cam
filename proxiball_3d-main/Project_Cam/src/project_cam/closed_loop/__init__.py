"""Closed-loop telemetry: shared structures for live pose-launcher integration.

The assessment package is offline-only. Closed-loop additions (event logging,
outcome scoring, drill orchestration) live here so the live/launcher path can
import them without dragging in the offline-only assessment tree.
"""

from .event_log import EventLogger, EVENT_TYPES, SCHEMA_VERSION
from .safety_gates import GateResult, evaluate_joint_gate

__all__ = [
    "EventLogger",
    "EVENT_TYPES",
    "SCHEMA_VERSION",
    "GateResult",
    "evaluate_joint_gate",
]
