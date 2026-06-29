"""Video-analytics streaming sources (RTSP / file / device).

A recruiter-facing edge-AI demo surface: ingest a local file, an RTSP URL, or a
V4L device through OpenCV (optionally via a GStreamer pipeline string), emit a
schema-stable JSONL event stream, and optionally write an annotated preview.

By design this path is BLM-disabled -- it can never actuate the launcher.
"""

from .rtsp_source import (
    StreamConfig,
    build_gstreamer_pipeline,
    classify_source,
)

__all__ = ["StreamConfig", "classify_source", "build_gstreamer_pipeline"]
