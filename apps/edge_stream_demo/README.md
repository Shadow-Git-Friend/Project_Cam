# Edge Stream Demo

A small video-analytics ingestion demo aligned with RTSP / GStreamer / edge-AI
job requirements. It reads a **local file**, an **RTSP URL**, or a **V4L device**
through OpenCV (optionally via a GStreamer pipeline), emits a schema-stable JSONL
event stream, and can write an annotated preview.

**This demo is BLM-disabled by design** — it can never actuate the launcher. See
[../../docs/safety_boundaries.md](../../docs/safety_boundaries.md).

## Run

Local file (no RTSP hardware needed):

```bash
PYTHONPATH=src ./venv/bin/python -m project_cam.streaming.rtsp_source \
  --source data/benchmark/walk.mp4 \
  --output-jsonl data/events/edge_demo.jsonl \
  --max-frames 300 --no-blm
```

RTSP URL:

```bash
PYTHONPATH=src ./venv/bin/python -m project_cam.streaming.rtsp_source \
  --source rtsp://user:pass@192.168.1.20:554/stream1 \
  --output-jsonl data/events/edge_demo.jsonl --no-blm
```

RTSP via a GStreamer pipeline (low latency, on GStreamer-enabled OpenCV builds):

```bash
PYTHONPATH=src ./venv/bin/python -m project_cam.streaming.rtsp_source \
  --source rtsp://127.0.0.1:8554/cam1 --gstreamer --latency-ms 100 --no-blm
```

Or the wrapper:

```bash
apps/edge_stream_demo/run_rtsp_demo.sh rtsp://127.0.0.1:8554/cam1
```

## Event JSONL schema

One JSON object per processed frame:

```json
{"ts": 1719600000.12, "frame_index": 0, "source": "rtsp://...", "detections": []}
```

`detections` is empty in the pure capture/throughput harness. Wire a
`detector(frame) -> [ {...} ]` callable into `run_stream` to populate it (e.g. a
YOLO ball/pose detector on the GPU box).

## GStreamer

See [gstreamer_pipeline.md](gstreamer_pipeline.md) for the pipeline string and
DeepStream notes (future work).
