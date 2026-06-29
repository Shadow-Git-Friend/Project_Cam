"""RTSP / file / device video source for the edge-analytics demo.

The config layer (source classification, GStreamer pipeline construction,
argument parsing) is pure and unit-testable without a live stream or cameras.
The capture/run layer imports OpenCV lazily so config tests never need a device.

BLM is hard-disabled here: ``StreamConfig.shoot_enabled`` is always False and no
launcher actuation path exists in this module.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


def classify_source(source: str) -> str:
    """Classify a stream source string.

    Returns one of ``"rtsp"``, ``"file"``, ``"device"``, ``"unknown"``.
    """
    s = str(source).strip()
    low = s.lower()
    if low.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if low.startswith(("http://", "https://")) and (
            low.endswith((".m3u8", ".mjpg", ".mjpeg")) or "/stream" in low):
        return "rtsp"  # network stream, handled by the same capture path
    if s.isdigit() or low.startswith("/dev/video"):
        return "device"
    if low.endswith((".mp4", ".avi", ".mkv", ".mov", ".webm", ".m4v")):
        return "file"
    # Bare existing path with no known extension still counts as a file attempt.
    if "/" in s or "\\" in s:
        return "file"
    return "unknown"


def build_gstreamer_pipeline(rtsp_url: str, latency_ms: int = 100) -> str:
    """Construct a low-latency H.264 RTSP -> appsink GStreamer pipeline string.

    Suitable for ``cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)`` on builds with
    GStreamer support.
    """
    return (
        f"rtspsrc location={rtsp_url} latency={int(latency_ms)} ! "
        "rtph264depay ! h264parse ! avdec_h264 ! "
        "videoconvert ! appsink drop=true sync=false"
    )


@dataclass
class StreamConfig:
    """Resolved configuration for one streaming source."""

    source: str
    source_type: str
    latency_ms: int = 100
    use_gstreamer: bool = False
    gst_pipeline: Optional[str] = None
    output_jsonl: Optional[str] = None
    max_frames: Optional[int] = None
    annotate_output: Optional[str] = None
    shoot_enabled: bool = field(default=False, init=False)  # always False

    @classmethod
    def from_source(
        cls,
        source: str,
        *,
        latency_ms: int = 100,
        use_gstreamer: bool = False,
        output_jsonl: Optional[str] = None,
        max_frames: Optional[int] = None,
        annotate_output: Optional[str] = None,
    ) -> "StreamConfig":
        stype = classify_source(source)
        if stype == "unknown":
            raise ValueError(f"unrecognized stream source: {source!r}")
        gst = None
        if use_gstreamer:
            if stype != "rtsp":
                raise ValueError("GStreamer pipeline mode is only for RTSP sources")
            gst = build_gstreamer_pipeline(source, latency_ms)
        return cls(
            source=source,
            source_type=stype,
            latency_ms=latency_ms,
            use_gstreamer=use_gstreamer,
            gst_pipeline=gst,
            output_jsonl=output_jsonl,
            max_frames=max_frames,
            annotate_output=annotate_output,
        )

    def capture_argument(self):
        """Argument to hand to ``cv2.VideoCapture``.

        Device indices become ints; the GStreamer pipeline string is returned
        when enabled; otherwise the raw source string (file path or URL).
        """
        if self.use_gstreamer and self.gst_pipeline:
            return self.gst_pipeline
        if self.source_type == "device" and str(self.source).isdigit():
            return int(self.source)
        return self.source


def run_stream(
    config: StreamConfig,
    detector: Optional[Callable[["object"], List[dict]]] = None,
    *,
    show: bool = False,
) -> int:
    """Capture from the source, emit JSONL events, return the frame count.

    ``detector`` is an optional callable ``frame -> [detection dicts]``; when
    None the demo runs as a pure capture/throughput harness. OpenCV is imported
    here so config-only callers (and tests) never require a device.
    """
    import cv2  # local import: keeps module import hardware-free

    cap = cv2.VideoCapture(
        config.capture_argument(),
        cv2.CAP_GSTREAMER if config.use_gstreamer else cv2.CAP_ANY,
    )
    if not cap.isOpened():
        raise RuntimeError(f"could not open stream: {config.source!r}")

    writer = None
    jsonl = open(config.output_jsonl, "w", encoding="utf-8") if config.output_jsonl else None
    frames = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            detections = detector(frame) if detector else []
            if jsonl is not None:
                jsonl.write(json.dumps({
                    "ts": time.time(),
                    "frame_index": frames,
                    "source": config.source,
                    "detections": detections,
                }) + "\n")
            if config.annotate_output and writer is None:
                h, w = frame.shape[:2]
                writer = cv2.VideoWriter(
                    config.annotate_output, cv2.VideoWriter_fourcc(*"mp4v"),
                    25.0, (w, h))
            if writer is not None:
                writer.write(frame)
            if show:
                cv2.imshow("edge_stream_demo", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            frames += 1
            if config.max_frames and frames >= config.max_frames:
                break
    finally:
        cap.release()
        if writer is not None:
            writer.release()
        if jsonl is not None:
            jsonl.close()
        if show:
            cv2.destroyAllWindows()
    return frames


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Project_Cam edge streaming demo (BLM-disabled).")
    p.add_argument("--source", required=True, help="RTSP URL, video file, or device index")
    p.add_argument("--gstreamer", action="store_true", help="use a GStreamer pipeline (RTSP only)")
    p.add_argument("--latency-ms", type=int, default=100)
    p.add_argument("--output-jsonl", default=None)
    p.add_argument("--annotate-output", default=None)
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--show", action="store_true")
    # Present for clarity; the demo can never shoot regardless of this flag.
    p.add_argument("--no-blm", action="store_true", default=True,
                   help="BLM is always disabled in the streaming demo")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    config = StreamConfig.from_source(
        args.source, latency_ms=args.latency_ms, use_gstreamer=args.gstreamer,
        output_jsonl=args.output_jsonl, max_frames=args.max_frames,
        annotate_output=args.annotate_output)
    print(f"[edge-demo] source={config.source} type={config.source_type} "
          f"gstreamer={config.use_gstreamer} shoot_enabled={config.shoot_enabled}")
    n = run_stream(config, show=args.show)
    print(f"[edge-demo] processed {n} frames")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
