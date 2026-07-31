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
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    fourcc: Optional[str] = None
    buffer_size: Optional[int] = None
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
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        fourcc: Optional[str] = None,
        buffer_size: Optional[int] = None,
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
            width=width,
            height=height,
            fps=fps,
            fourcc=fourcc,
            buffer_size=buffer_size,
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
    fullscreen: bool = False,
) -> int:
    """Capture from the source, emit JSONL events, return the frame count.

    ``detector`` is an optional callable ``frame -> [detection dicts]``; when
    None the demo runs as a pure capture/throughput harness. OpenCV is imported
    here so config-only callers (and tests) never require a device.
    """
    import cv2  # local import: keeps module import hardware-free

    backend = cv2.CAP_V4L2 if (
        config.source_type == "device" and str(config.source).startswith("/dev/")
    ) else cv2.CAP_ANY
    cap = cv2.VideoCapture(
        config.capture_argument(),
        cv2.CAP_GSTREAMER if config.use_gstreamer else backend,
    )
    if not cap.isOpened():
        raise RuntimeError(f"could not open stream: {config.source!r}")

    if config.fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*config.fourcc))
    if config.width:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
    if config.height:
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
    if config.fps:
        cap.set(cv2.CAP_PROP_FPS, config.fps)
    if config.buffer_size:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, config.buffer_size)

    writer = None
    jsonl = open(config.output_jsonl, "w", encoding="utf-8") if config.output_jsonl else None
    window_name = "edge_stream_demo"
    if show:
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        if fullscreen:
            cv2.setWindowProperty(
                window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
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
                cv2.imshow(window_name, frame)
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
    p.add_argument("--fullscreen", action="store_true",
                   help="show the preview window fullscreen")
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--fps", type=float, default=None)
    p.add_argument("--fourcc", default=None)
    p.add_argument("--buffer-size", type=int, default=None)
    # Present for clarity; the demo can never shoot regardless of this flag.
    p.add_argument("--no-blm", action="store_true", default=True,
                   help="BLM is always disabled in the streaming demo")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    config = StreamConfig.from_source(
        args.source, latency_ms=args.latency_ms, use_gstreamer=args.gstreamer,
        output_jsonl=args.output_jsonl, max_frames=args.max_frames,
        annotate_output=args.annotate_output, width=args.width, height=args.height,
        fps=args.fps, fourcc=args.fourcc, buffer_size=args.buffer_size)
    print(f"[edge-demo] source={config.source} type={config.source_type} "
          f"gstreamer={config.use_gstreamer} shoot_enabled={config.shoot_enabled}")
    n = run_stream(config, show=args.show, fullscreen=args.fullscreen)
    print(f"[edge-demo] processed {n} frames")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
