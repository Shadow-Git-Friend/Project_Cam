"""Streaming source config (no live stream / camera required)."""

import pytest

from project_cam.streaming import (
    StreamConfig,
    build_gstreamer_pipeline,
    classify_source,
)


def test_classify_rtsp():
    assert classify_source("rtsp://user:pass@10.0.0.5:554/stream1") == "rtsp"
    assert classify_source("rtsps://host/cam") == "rtsp"


def test_classify_file():
    assert classify_source("data/benchmark/clip.mp4") == "file"
    assert classify_source("/abs/path/video.mkv") == "file"


def test_classify_device():
    assert classify_source("0") == "device"
    assert classify_source("/dev/video2") == "device"


def test_classify_unknown():
    assert classify_source("not_a_source") == "unknown"


def test_config_from_file_source():
    cfg = StreamConfig.from_source("clips/walk.mp4", output_jsonl="out.jsonl")
    assert cfg.source_type == "file"
    assert cfg.shoot_enabled is False
    assert cfg.capture_argument() == "clips/walk.mp4"


def test_config_from_rtsp_source():
    cfg = StreamConfig.from_source("rtsp://127.0.0.1:8554/cam1")
    assert cfg.source_type == "rtsp"
    assert cfg.capture_argument() == "rtsp://127.0.0.1:8554/cam1"


def test_config_device_index_becomes_int():
    cfg = StreamConfig.from_source("0")
    assert cfg.capture_argument() == 0


def test_gstreamer_pipeline_only_for_rtsp():
    cfg = StreamConfig.from_source("rtsp://h/cam", use_gstreamer=True, latency_ms=120)
    assert "rtspsrc location=rtsp://h/cam latency=120" in cfg.gst_pipeline
    assert cfg.capture_argument() == cfg.gst_pipeline
    with pytest.raises(ValueError):
        StreamConfig.from_source("clip.mp4", use_gstreamer=True)


def test_unknown_source_raises():
    with pytest.raises(ValueError):
        StreamConfig.from_source("garbage")


def test_build_gstreamer_pipeline_contents():
    p = build_gstreamer_pipeline("rtsp://x/y", latency_ms=200)
    assert "rtph264depay" in p
    assert "appsink" in p
    assert "latency=200" in p


def test_streaming_module_has_no_shoot_symbol():
    import project_cam.streaming.rtsp_source as mod

    names = dir(mod)
    assert not any("shoot" in n.lower() and n != "shoot_enabled" for n in names)
    assert not any("fire" in n.lower() for n in names)
