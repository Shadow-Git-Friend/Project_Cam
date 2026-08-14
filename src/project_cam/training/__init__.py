"""Garage training drills — pure, display-free state machines.

The runner (garage_lab_combined/scripts/training_drill.py) feeds live UDP
joints into these machines and renders a scoreboard. Everything here is
stdlib-only and clock-injected so it unit-tests without cameras or cv2.
"""

from project_cam.training.drills import (
    DRILL_REGISTRY,
    BalanceDrill,
    CmjDrill,
    GkSaveDrill,
    GkSaveServedDrill,
    GkUpDownDrill,
    HopSymmetryDrill,
    LineHopsDrill,
    ReactiveCutDrill,
    ShuttleDrill,
    append_session_index,
    build_session_record,
    pelvis_mm,
    zone_of,
)

__all__ = [
    "DRILL_REGISTRY",
    "BalanceDrill",
    "CmjDrill",
    "GkSaveDrill",
    "GkSaveServedDrill",
    "GkUpDownDrill",
    "HopSymmetryDrill",
    "LineHopsDrill",
    "ReactiveCutDrill",
    "ShuttleDrill",
    "append_session_index",
    "build_session_record",
    "pelvis_mm",
    "zone_of",
]
