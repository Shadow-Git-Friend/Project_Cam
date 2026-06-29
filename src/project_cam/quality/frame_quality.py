"""Camera frame quality metrics that run without OpenCV.

The live pipeline can call this on sampled frames to detect lighting, blur, and
dropout drift before model outputs degrade. The implementation uses NumPy only
so tests and CI do not need camera or GUI dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from project_cam.monitoring import MetricsRegistry


@dataclass(frozen=True)
class QualityThresholds:
    min_brightness: float = 30.0
    max_brightness: float = 230.0
    min_laplacian_var: float = 80.0


@dataclass(frozen=True)
class FrameQualityResult:
    camera_id: str
    frame_present: bool
    status: str
    brightness_mean: Optional[float] = None
    blur_laplacian_var: Optional[float] = None
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "frame_present": self.frame_present,
            "status": self.status,
            "brightness_mean": self.brightness_mean,
            "blur_laplacian_var": self.blur_laplacian_var,
            "reasons": list(self.reasons),
        }


def _to_gray(frame: np.ndarray) -> np.ndarray:
    arr = np.asarray(frame)
    if arr.ndim == 2:
        gray = arr
    elif arr.ndim == 3 and arr.shape[2] in {3, 4}:
        gray = arr[..., :3].mean(axis=2)
    else:
        raise ValueError(f"frame must be HxW or HxWx3/4, got {arr.shape}")
    return gray.astype(np.float64, copy=False)


def _laplacian_variance(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    lap = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(np.var(lap))


def analyze_frame(
    frame: Optional[np.ndarray],
    *,
    camera_id: str,
    thresholds: QualityThresholds = QualityThresholds(),
) -> FrameQualityResult:
    """Return brightness/blur/dropout quality for one frame."""
    if frame is None:
        return FrameQualityResult(
            camera_id=camera_id,
            frame_present=False,
            status="bad",
            reasons=["missing_frame"],
        )

    gray = _to_gray(frame)
    brightness = float(gray.mean())
    blur_var = _laplacian_variance(gray)
    reasons: List[str] = []
    if brightness < thresholds.min_brightness:
        reasons.append("underexposed")
    elif brightness > thresholds.max_brightness:
        reasons.append("overexposed")
    if blur_var < thresholds.min_laplacian_var:
        reasons.append("blurry")

    return FrameQualityResult(
        camera_id=camera_id,
        frame_present=True,
        status="ok" if not reasons else "bad",
        brightness_mean=brightness,
        blur_laplacian_var=blur_var,
        reasons=reasons,
    )


def record_frame_quality(
    metrics: MetricsRegistry,
    result: FrameQualityResult,
    *,
    camera_profile: str,
) -> None:
    """Record a frame-quality result into the monitoring registry."""
    labels = {"camera_profile": camera_profile, "camera_id": result.camera_id}
    if result.brightness_mean is not None:
        metrics.set("project_cam_frame_brightness", result.brightness_mean, **labels)
    if result.blur_laplacian_var is not None:
        metrics.set("project_cam_frame_blur_laplacian_var", result.blur_laplacian_var, **labels)
    for reason in result.reasons:
        metrics.inc(
            "project_cam_frame_quality_bad_total",
            camera_profile=camera_profile,
            camera_id=result.camera_id,
            quality_reason=reason,
        )
