"""Camera input-quality / drift metrics.

These tests use small NumPy arrays rather than camera frames, so they run in CI
without OpenCV, hardware, or video files.
"""

from __future__ import annotations

import numpy as np

from project_cam.monitoring import METRIC_NAMES, MetricsRegistry
from project_cam.quality.frame_quality import (
    QualityThresholds,
    analyze_frame,
    record_frame_quality,
)


def test_checkerboard_frame_is_bright_enough_and_sharp():
    pattern = (np.indices((16, 16)).sum(axis=0) % 2).astype(np.uint8) * 255
    frame = np.stack([pattern, pattern, pattern], axis=2)

    result = analyze_frame(
        frame,
        camera_id="camA",
        thresholds=QualityThresholds(
            min_brightness=20.0,
            max_brightness=240.0,
            min_laplacian_var=1000.0,
        ),
    )

    assert result.frame_present is True
    assert result.status == "ok"
    assert result.brightness_mean == 127.5
    assert result.blur_laplacian_var > 1000.0
    assert result.reasons == []


def test_missing_frame_is_reported_as_bad_quality():
    result = analyze_frame(None, camera_id="camA")

    assert result.frame_present is False
    assert result.status == "bad"
    assert result.reasons == ["missing_frame"]


def test_underexposed_blurry_frame_reports_both_reasons():
    frame = np.zeros((12, 12, 3), dtype=np.uint8)

    result = analyze_frame(
        frame,
        camera_id="camA",
        thresholds=QualityThresholds(
            min_brightness=20.0,
            max_brightness=240.0,
            min_laplacian_var=10.0,
        ),
    )

    assert result.status == "bad"
    assert result.brightness_mean == 0.0
    assert result.blur_laplacian_var == 0.0
    assert result.reasons == ["underexposed", "blurry"]


def test_frame_quality_metrics_are_in_contract_and_recordable():
    assert "project_cam_frame_brightness" in METRIC_NAMES
    assert "project_cam_frame_blur_laplacian_var" in METRIC_NAMES
    assert "project_cam_frame_quality_bad_total" in METRIC_NAMES

    reg = MetricsRegistry()
    result = analyze_frame(None, camera_id="camA")
    record_frame_quality(reg, result, camera_profile="usb6")
    _content_type, payload = reg.render()
    text = payload.decode("utf-8")

    assert "project_cam_frame_quality_bad_total" in text
    assert "missing_frame" in text
