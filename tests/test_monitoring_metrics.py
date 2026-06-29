"""Monitoring metric contract.

Runs on the minimal install: the metric names + text exposition are guaranteed
by the dependency-free fallback, and the real prometheus_client backend (when
present) renders the same names.
"""

import pytest

from project_cam.monitoring import (
    METRIC_NAMES,
    METRIC_SPECS,
    MetricsRegistry,
    get_metrics,
)

REQUIRED = [
    "project_cam_camera_count",
    "project_cam_frames_total",
    "project_cam_dropped_frames_total",
    "project_cam_capture_latency_ms",
    "project_cam_inference_latency_ms",
    "project_cam_triangulation_latency_ms",
    "project_cam_pipeline_latency_ms",
    "project_cam_gpu_memory_mb",
    "project_cam_pose_camera_count",
    "project_cam_ball_reprojection_error_px",
    "project_cam_joint_reprojection_error_px",
    "project_cam_safety_gate_blocked_total",
    "project_cam_event_logger_dropped_total",
    "project_cam_frame_brightness",
    "project_cam_frame_blur_laplacian_var",
    "project_cam_frame_quality_bad_total",
]


def test_all_required_metric_names_present():
    for name in REQUIRED:
        assert name in METRIC_NAMES


def test_render_exposes_every_metric_name():
    reg = MetricsRegistry()
    _content_type, payload = reg.render()
    text = payload.decode("utf-8")
    for name in METRIC_NAMES:
        assert name in text, f"{name} missing from /metrics output"


def test_counter_inc_and_gauge_set_and_histogram_observe():
    reg = MetricsRegistry()
    reg.inc("project_cam_frames_total", camera_profile="usb6", camera_id="camUsb01_C920")
    reg.set("project_cam_camera_count", 6, camera_profile="usb6")
    reg.observe("project_cam_triangulation_latency_ms", 1.2, camera_profile="usb6")
    reg.inc("project_cam_safety_gate_blocked_total", gate_reason="low_confidence")
    reg.set("project_cam_frame_brightness", 127.5, camera_profile="usb6", camera_id="camA")
    reg.set("project_cam_frame_blur_laplacian_var", 1200, camera_profile="usb6", camera_id="camA")
    reg.inc(
        "project_cam_frame_quality_bad_total",
        camera_profile="usb6",
        camera_id="camA",
        quality_reason="blurry",
    )
    _ct, payload = reg.render()
    text = payload.decode("utf-8")
    assert "project_cam_camera_count" in text


def test_wrong_metric_kind_raises():
    reg = MetricsRegistry()
    with pytest.raises(TypeError):
        reg.set("project_cam_frames_total", 1, camera_profile="usb6", camera_id="x")
    with pytest.raises(TypeError):
        reg.inc("project_cam_camera_count", camera_profile="usb6")


def test_unknown_metric_raises():
    reg = MetricsRegistry()
    with pytest.raises(KeyError):
        reg.inc("project_cam_not_a_metric")


def test_wrong_labels_raise():
    reg = MetricsRegistry()
    with pytest.raises(ValueError):
        reg.set("project_cam_camera_count", 4, wrong_label="x")


def test_spec_rejects_disallowed_label():
    from project_cam.monitoring.metrics import MetricSpec

    with pytest.raises(ValueError):
        MetricSpec("x", "gauge", "help", ("frame_id",))


def test_get_metrics_is_singleton():
    assert get_metrics() is get_metrics()


def test_every_spec_label_is_allowed():
    from project_cam.monitoring.metrics import ALLOWED_LABELS

    for spec in METRIC_SPECS:
        assert set(spec.labelnames) <= ALLOWED_LABELS
