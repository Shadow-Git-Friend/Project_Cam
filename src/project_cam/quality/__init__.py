"""Input-quality and drift checks for camera frames."""

from .frame_quality import (
    FrameQualityResult,
    QualityThresholds,
    analyze_frame,
    record_frame_quality,
)

__all__ = [
    "FrameQualityResult",
    "QualityThresholds",
    "analyze_frame",
    "record_frame_quality",
]
