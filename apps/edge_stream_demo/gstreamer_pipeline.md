# GStreamer Pipeline Notes

The demo can ingest RTSP through a GStreamer pipeline for lower, more predictable
latency than the default FFmpeg path, on OpenCV builds compiled with GStreamer
support (`cv2.getBuildInformation()` shows `GStreamer: YES`).

## H.264 RTSP → appsink

```text
rtspsrc location=rtsp://USER:PASS@HOST:554/stream1 latency=100 !
rtph264depay !
h264parse !
avdec_h264 !
videoconvert !
appsink drop=true sync=false
```

This is exactly what `build_gstreamer_pipeline(url, latency_ms)` produces
(`src/project_cam/streaming/rtsp_source.py`). `drop=true sync=false` keeps the
consumer on the latest frame instead of building a backlog — the same
"latest-frame" discipline the live multi-cam capture uses.

## Hardware-accelerated decode (NVIDIA)

On Jetson / dGPU boxes, swap the software decoder for NVDEC:

```text
rtspsrc location=... latency=100 !
rtph264depay ! h264parse !
nvv4l2decoder !
nvvideoconvert !
video/x-raw,format=BGRx !
videoconvert !
appsink drop=true sync=false
```

## DeepStream (future work)

For multi-stream batched inference at the edge, the natural next step is NVIDIA
DeepStream (`nvstreammux` → `nvinfer` → `nvtracker` → `nvdsosd`). It is **not**
implemented here; the current demo is a single-stream OpenCV ingestion harness.
This file documents the migration path, not a shipped feature.
