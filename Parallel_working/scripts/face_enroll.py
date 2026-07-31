#!/usr/bin/env python3
"""Enroll, list, or remove identities in the private local SFace gallery."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from project_cam.tracking import (  # noqa: E402
    FaceGallery,
    FaceIdentifier,
    default_face_gallery_path,
    validate_identity_name,
)


def parse_camera_source(raw: str):
    value = str(raw).strip()
    return int(value) if value.isdecimal() else value


def choose_enrollment_face(
    faces,
    *,
    frame_shape,
    min_face_px: float,
    min_det_score: float,
):
    """Pick the largest high-quality face away from extreme frame edges."""
    height, width = frame_shape[:2]
    accepted = []
    for face in faces:
        x, y, box_width, box_height = face.get("box", (0, 0, 0, 0))
        score = float(face.get("det_score", 0.0))
        center_x = x + box_width / 2.0
        center_y = y + box_height / 2.0
        if min(box_width, box_height) < float(min_face_px) or score < float(min_det_score):
            continue
        if not (0.08 * width <= center_x <= 0.92 * width):
            continue
        if not (0.08 * height <= center_y <= 0.92 * height):
            continue
        if "embedding" not in face:
            continue
        accepted.append((box_width * box_height, face))
    return max(accepted, key=lambda item: item[0])[1] if accepted else None


def list_gallery(path) -> int:
    try:
        gallery = FaceGallery.load(path)
    except (OSError, EOFError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"Gallery: {Path(path).expanduser()}")
    if not len(gallery):
        print("  (empty)")
        return 0
    for name, samples in sorted(gallery.people().items()):
        print(f"  {name}: {samples} sample(s)")
    return 0


def remove_identity(path, name: str) -> int:
    try:
        name = validate_identity_name(name)
        gallery = FaceGallery.load(path)
        removed = gallery.remove(name)
        if not removed:
            print(f"Identity not found: {name}")
            return 1
        saved = gallery.save(path)
    except (OSError, EOFError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"Removed {name}: {removed} sample(s); gallery={saved}")
    return 0


def embeddings_from_images(
    identifier,
    image_paths,
    *,
    min_face_px,
    min_det_score,
):
    import cv2

    embeddings = []
    for path in image_paths:
        frame = cv2.imread(str(path))
        if frame is None:
            print(f"[WARN] Cannot read image: {path}")
            continue
        face = choose_enrollment_face(
            identifier.detect_and_encode(frame),
            frame_shape=frame.shape,
            min_face_px=min_face_px,
            min_det_score=min_det_score,
        )
        if face is None:
            print(f"[WARN] No enrollment-quality face: {path}")
            continue
        embeddings.append(face["embedding"])
        print(f"[OK] Face accepted: {path}")
    return embeddings


def embeddings_from_camera(
    identifier,
    source,
    *,
    samples,
    min_face_px,
    min_det_score,
    preview,
    max_seconds,
):
    import cv2

    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise RuntimeError(f"cannot open camera/video source: {source}")
    # Ask for a larger, clearer preview (C920 / 1080P webcams support 720p).
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    collected = []
    started = time.monotonic()
    last_capture = 0.0
    capture_interval = 0.45   # seconds between accepted samples -> ~5s of capture
    warmup_seconds = 2.5      # let the window appear + user get positioned
    window = "Project Cam - Face Enrollment"

    GREEN = (80, 220, 120)
    GRAY = (110, 110, 110)
    YELLOW = (0, 222, 255)    # BGR, Kairat-ish
    WHITE = (240, 240, 240)

    if preview:
        # A real, on-top window so it is never lost behind the control center.
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        try:
            cv2.resizeWindow(window, 1000, 640)
            cv2.moveWindow(window, 160, 80)
        except cv2.error:
            pass
        try:
            cv2.setWindowProperty(window, cv2.WND_PROP_TOPMOST, 1.0)
        except (cv2.error, AttributeError):
            pass

    def draw_overlay(display, *, phase, countdown=None):
        h, w = display.shape[:2]
        cv2.rectangle(display, (0, 0), (w, 58), (18, 18, 18), -1)
        cv2.putText(display, "FACE ENROLLMENT", (16, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.85, YELLOW, 2, cv2.LINE_AA)
        if phase == "warmup":
            line1, line2 = "LOOK AT THE CAMERA", "smotrite v kameru"
        elif phase == "capture":
            line1, line2 = "MOVE YOUR HEAD IN A SLOW CIRCLE", "vrashchayte golovoy po krugu"
        else:
            line1, line2 = "ENROLLED", "gotovo"
        cv2.putText(display, line1, (16, h - 58), cv2.FONT_HERSHEY_SIMPLEX,
                    0.72, WHITE, 2, cv2.LINE_AA)
        cv2.putText(display, line2, (16, h - 36), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (170, 170, 170), 1, cv2.LINE_AA)
        # progress bar
        x0, x1, y = 16, w - 16, h - 22
        cv2.rectangle(display, (x0, y), (x1, y + 12), (60, 60, 60), 1)
        filled = int((x1 - x0) * (len(collected) / max(1, samples)))
        cv2.rectangle(display, (x0, y), (x0 + filled, y + 12), GREEN, -1)
        cv2.putText(display, f"{len(collected)}/{samples}   (press Q to cancel)",
                    (x1 - 260, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        # center guide so the user knows where to place the face
        cv2.ellipse(display, (w // 2, h // 2 + 6), (150, 200), 0, 0, 360, (75, 75, 75), 1)
        if countdown is not None:
            cv2.putText(display, str(countdown), (w // 2 - 22, h // 2 + 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.6, YELLOW, 3, cv2.LINE_AA)

    try:
        while len(collected) < samples and time.monotonic() - started < max_seconds:
            ok, frame = capture.read()
            if not ok:
                break
            now = time.monotonic()
            elapsed = now - started
            phase = "warmup" if elapsed < warmup_seconds else "capture"

            faces = identifier.detect_and_encode(frame)
            selected = choose_enrollment_face(
                faces,
                frame_shape=frame.shape,
                min_face_px=min_face_px,
                min_det_score=min_det_score,
            )
            # Pace captures by time (not frame count) so the 12 samples are spread
            # across the circular head motion instead of a 2s burst.
            if (
                phase == "capture"
                and selected is not None
                and (now - last_capture) >= capture_interval
            ):
                collected.append(selected["embedding"])
                last_capture = now
                print(f"[CAPTURE] {len(collected)}/{samples}")

            if preview:
                for face in faces:
                    x, y, width, height = map(int, face["box"])
                    color = GREEN if face is selected else GRAY
                    cv2.rectangle(frame, (x, y), (x + width, y + height), color, 3)
                display = cv2.flip(frame, 1)   # mirror -> feels like a selfie cam
                countdown = None
                if phase == "warmup":
                    countdown = max(1, int(warmup_seconds - elapsed) + 1)
                draw_overlay(display, phase=phase, countdown=countdown)
                cv2.imshow(window, display)
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                    break

        # Hold a "done" frame briefly so the window does not just vanish.
        if preview and len(collected) >= samples:
            ok, frame = capture.read()
            if ok:
                display = cv2.flip(frame, 1)
                draw_overlay(display, phase="done")
                cv2.imshow(window, display)
                cv2.waitKey(1300)
    finally:
        capture.release()
        if preview:
            cv2.destroyWindow(window)
            cv2.waitKey(1)
    return collected


# ---------------------------------------------------------------------------
# Multi-camera "walk in and turn 360 degrees" arena enrollment
# ---------------------------------------------------------------------------


def parse_arena_cameras(config_path):
    """Read (label, device) pairs from the 6-USB capture YAML without a yaml dep."""
    cameras = []
    label = None
    for raw in Path(config_path).read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        if stripped.startswith("device:"):
            device = stripped.split(":", 1)[1].strip()
            if label:
                cameras.append((label, device))
                label = None
        elif stripped.endswith(":") and stripped != "cameras:" and 1 <= indent <= 3:
            label = stripped[:-1].strip()
    return cameras


class _ThreadedCamera:
    """Open + stream one camera in a worker thread with a BOUNDED open.

    The open and the read loop both live in the worker thread, and __init__ only
    waits up to ``open_timeout`` for readiness. A flaky/unsupported camera that
    blocks forever inside ``cv2.VideoCapture`` (the generic 1080P units do this at
    1280x720) therefore can never hang the whole enrollment: it is simply marked
    not-ok and skipped, and its stuck daemon thread dies with the process.
    """

    def __init__(self, device, *, width, height, fourcc, fps=5):
        self.device = device
        self.ok = False
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._stop = False
        self._ready = threading.Event()
        self._cfg = (int(width), int(height), fourcc, int(fps))
        # Start the worker immediately but DO NOT block here: the caller waits on
        # all cameras together (shared deadline) so 6 opens run in parallel (~6s)
        # instead of summing to ~36s when several are slow.
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait_ready(self, timeout):
        self._ready.wait(timeout=max(0.0, timeout))
        return self.ok

    def _run(self):
        import cv2

        width, height, fourcc, fps = self._cfg
        try:
            cap = cv2.VideoCapture(os.path.realpath(self.device), cv2.CAP_V4L2)
            if cap.isOpened():
                if fourcc:
                    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
                cap.set(cv2.CAP_PROP_FPS, fps)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                self._cap = cap
                self.ok = True
        except Exception:
            self.ok = False
        finally:
            self._ready.set()
        if not self.ok:
            return
        while not self._stop:
            try:
                ok, frame = self._cap.read()
            except Exception:
                break
            if ok and frame is not None:
                with self._lock:
                    self._frame = frame
            else:
                time.sleep(0.02)
        try:
            self._cap.release()
        except Exception:
            pass

    def latest(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def release(self):
        self._stop = True

    def join(self, timeout=1.0):
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)


def _draw_arena_mosaic(
    tiles,
    *,
    collected,
    per_cam_counts,
    distinct,
    elapsed,
    window,
    done=False,
    cols=3,
    tile=(462, 260),
):
    import cv2
    import numpy as np

    GREEN, GRAY, YELLOW, WHITE = (80, 220, 120), (90, 90, 90), (0, 222, 255), (240, 240, 240)
    tw, th = tile
    rows = (len(tiles) + cols - 1) // cols
    header, footer = 46, 64
    canvas = np.zeros((rows * th + header + footer, cols * tw, 3), np.uint8)

    for i, (label, frame, boxes, selected, recent) in enumerate(tiles):
        r, c = divmod(i, cols)
        x0, y0 = c * tw, header + r * th
        if frame is None:
            cv2.putText(canvas, "NO SIGNAL", (x0 + tw // 2 - 70, y0 + th // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, GRAY, 2, cv2.LINE_AA)
        else:
            fh, fw = frame.shape[:2]
            canvas[y0:y0 + th, x0:x0 + tw] = cv2.resize(frame, (tw, th))
            sx, sy = tw / fw, th / fh
            for face in boxes:
                x, y, w, h = face["box"]
                color = GREEN if face is selected else GRAY
                cv2.rectangle(canvas,
                              (int(x0 + x * sx), int(y0 + y * sy)),
                              (int(x0 + (x + w) * sx), int(y0 + (y + h) * sy)),
                              color, 2)
        cv2.rectangle(canvas, (x0, y0), (x0 + tw - 1, y0 + th - 1),
                      GREEN if recent else (50, 50, 50), 2)
        cv2.rectangle(canvas, (x0, y0), (x0 + tw, y0 + 22), (20, 20, 20), -1)
        cv2.putText(canvas, f"{label}  [{per_cam_counts.get(label, 0)}]",
                    (x0 + 6, y0 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.45, WHITE, 1, cv2.LINE_AA)

    H, W = canvas.shape[:2]
    cv2.putText(canvas, "ARENA FACE ENROLLMENT", (14, 32),
                cv2.FONT_HERSHEY_SIMPLEX, 0.85, YELLOW, 2, cv2.LINE_AA)
    remaining = max(0.0, window - elapsed)
    prompt = ("SAVING..." if done
              else "WALK A FULL CIRCLE AROUND THE ARENA  /  hodite po krugu")
    cv2.putText(canvas, prompt, (max(14, W - 760), 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, GREEN if done else WHITE, 2 if done else 1, cv2.LINE_AA)
    msg = (f"keep moving - finishing in {remaining:.0f}s     "
           f"faces captured: {len(collected)}     cameras seeing you: {distinct}")
    cv2.putText(canvas, msg, (14, H - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, WHITE, 1, cv2.LINE_AA)
    x0b, x1b, yb = 14, W - 14, H - 16
    cv2.rectangle(canvas, (x0b, yb), (x1b, yb + 9), (60, 60, 60), 1)
    frac = min(1.0, elapsed / max(0.1, window))
    cv2.rectangle(canvas, (x0b, yb), (x0b + int((x1b - x0b) * frac), yb + 9), GREEN, -1)
    return canvas


def embeddings_from_cameras(
    identifier,
    cameras,
    *,
    min_duration,
    max_duration,
    target_samples,
    target_cameras,
    per_camera_interval,
    min_face_px,
    min_det_score,
    preview,
):
    """Capture embeddings from ALL cameras while the person turns a full circle.

    `cameras` is a list of (label, _ThreadedCamera). Returns (embeddings,
    per_camera_counts). Finishes when enough samples from enough distinct
    cameras have been gathered (after min_duration), or at max_duration.
    """
    import cv2

    collected = []
    per_cam_counts = {label: 0 for label, _ in cameras}
    last_capture = {label: 0.0 for label, _ in cameras}
    started = time.monotonic()
    sample_cap = max(target_samples * 2, 48)
    window = "Project Cam - Arena Face Enrollment"

    # STOP is handled globally in run_arena_enrollment (a hard os._exit on
    # SIGINT/SIGTERM that works in any phase), so this loop only implements the
    # normal time / coverage finish.
    if preview:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        try:
            cv2.resizeWindow(window, 1386, 700)
            cv2.moveWindow(window, 80, 40)
        except cv2.error:
            pass
        try:
            cv2.setWindowProperty(window, cv2.WND_PROP_TOPMOST, 1.0)
        except (cv2.error, AttributeError):
            pass

    try:
        while True:
            now = time.monotonic()
            elapsed = now - started
            tiles = []
            for label, reader in cameras:
                frame = reader.latest() if reader.ok else None
                boxes, selected, recent = [], None, False
                if frame is not None:
                    boxes = identifier.detect_and_encode(frame)
                    selected = choose_enrollment_face(
                        boxes,
                        frame_shape=frame.shape,
                        min_face_px=min_face_px,
                        min_det_score=min_det_score,
                    )
                    if (
                        selected is not None
                        and len(collected) < sample_cap
                        and (now - last_capture[label]) >= per_camera_interval
                    ):
                        collected.append(selected["embedding"])
                        per_cam_counts[label] += 1
                        last_capture[label] = now
                        recent = True
                        print(f"[CAPTURE] {label}: {per_cam_counts[label]} (total {len(collected)})")
                tiles.append((label, frame, boxes, selected, recent))

            distinct = sum(1 for v in per_cam_counts.values() if v > 0)
            done = (
                (elapsed >= min_duration
                 and len(collected) >= target_samples
                 and distinct >= target_cameras)
                or elapsed >= max_duration
            )

            if preview:
                mosaic = _draw_arena_mosaic(
                    tiles,
                    collected=collected,
                    per_cam_counts=per_cam_counts,
                    distinct=distinct,
                    elapsed=elapsed,
                    window=max_duration,
                    done=done,
                )
                cv2.imshow(window, mosaic)
                key = cv2.waitKey(700 if done else 1) & 0xFF
                if not done and key in (ord("q"), 27):
                    break
            elif not done:
                time.sleep(0.02)

            if done:
                break
    finally:
        if preview:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except cv2.error:
                pass
    return collected, per_cam_counts


def run_arena_enrollment(args) -> int:
    # STOP (SIGINT/SIGTERM from the control center) must terminate us INSTANTLY in
    # any phase -- opening cameras, the capture loop, or shutdown -- so the app's
    # RUNNING state always clears and STOP never appears to hang. A hard os._exit
    # is the only thing guaranteed to work while blocked in an OpenCV C call;
    # graceful save happens only on the normal window finish, not on STOP.
    def _hard_stop(_signum, _frame):
        os._exit(130)

    try:
        signal.signal(signal.SIGINT, _hard_stop)
        signal.signal(signal.SIGTERM, _hard_stop)
    except (ValueError, OSError):
        pass

    devices = parse_arena_cameras(args.arena_config)
    if not devices:
        print(f"[ERROR] no cameras found in {args.arena_config}", file=sys.stderr)
        return 1
    try:
        name = validate_identity_name(args.name)
        identifier = FaceIdentifier(
            args.models_dir.expanduser(), det_width=max(1, int(args.arena_det_width))
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    # Open every camera in PARALLEL with a shared deadline: a slow/unsupported unit
    # is skipped (not summed), so the mosaic appears in a few seconds instead of
    # after ~36s of sequential 6s timeouts.
    print("[INFO] opening cameras...", flush=True)
    open_started = time.monotonic()
    reso = {}
    readers = []
    for label, device in devices:
        # C920s stream 1280x720 for a bigger face crop; the generic 1080P units
        # choke/hang at 1280 on this USB-2 bus, so they run at the safe size.
        is_c920 = "c920" in label.lower()
        width = 1280 if is_c920 else args.capture_width
        height = 720 if is_c920 else args.capture_height
        reso[label] = (width, height)
        readers.append((label, _ThreadedCamera(
            device, width=width, height=height, fourcc=args.fourcc, fps=args.capture_fps)))
    open_deadline = time.monotonic() + 7.0
    opened = 0
    for label, reader in readers:
        ok = reader.wait_ready(open_deadline - time.monotonic())
        opened += 1 if ok else 0
        w, h = reso[label]
        print(f"[CAMERA] {label}: {'OPEN' if ok else 'FAILED'} ({w}x{h})", flush=True)
    if opened == 0:
        for _, reader in readers:
            reader.release()
        print("[ERROR] could not open any arena camera", file=sys.stderr)
        return 1
    print(f"[INFO] {opened}/{len(readers)} cameras open in "
          f"{time.monotonic() - open_started:.1f}s. Walk a full circle around the arena now.",
          flush=True)

    try:
        embeddings, per_cam = embeddings_from_cameras(
            identifier,
            readers,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            target_samples=args.target_samples,
            target_cameras=args.target_cameras,
            per_camera_interval=args.per_camera_interval,
            min_face_px=args.arena_min_face_px,
            min_det_score=args.arena_min_det_score,
            preview=not args.no_preview,
        )
    finally:
        for _, reader in readers:
            reader.release()
        for _, reader in readers:
            reader.join(timeout=1.0)

    min_save = 8
    if len(embeddings) < min_save:
        print(
            f"[ERROR] Only {len(embeddings)} face samples captured (need >= {min_save}). "
            "Move nearer the arena centre, make sure your face is lit, and turn more slowly.",
            file=sys.stderr,
        )
        return 1
    try:
        gallery = FaceGallery.load(args.gallery)
        if args.replace:
            gallery.remove(name)
        for embedding in embeddings:
            gallery.add(name, embedding)
        saved = gallery.save(args.gallery)
    except (OSError, EOFError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    covered = sum(1 for v in per_cam.values() if v > 0)
    print(f"[DONE] Enrolled {name}: {len(embeddings)} samples from {covered} camera(s) -> {saved}")
    print("Per-camera samples: " + ", ".join(f"{k}={v}" for k, v in per_cam.items()))
    print("Reminder: local face labels are not anti-spoof/liveness authentication.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage the private local Face-ID gallery. Identification labels are "
            "not liveness-tested authentication. No source images are stored."
        )
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--list", action="store_true", help="List enrolled names and exit.")
    action.add_argument("--remove", metavar="NAME", help="Remove all samples for NAME and exit.")
    parser.add_argument("--name", help="Display name to enroll.")
    parser.add_argument("--camera", default="0", help="Camera index, /dev/video path, or video file.")
    parser.add_argument(
        "--image", action="append", type=Path, default=[],
        help="Enroll from an image instead of a live camera (repeatable).",
    )
    parser.add_argument("--samples", type=int, default=12,
                        help="Accepted embeddings to capture (default 12).")
    parser.add_argument("--replace", action="store_true",
                        help="Delete existing samples for this name before adding new ones.")
    parser.add_argument("--no-preview", action="store_true",
                        help="Do not create an OpenCV preview window.")
    parser.add_argument("--max-seconds", type=float, default=120.0)
    parser.add_argument("--min-face-px", type=float, default=70.0)
    parser.add_argument("--min-det-score", type=float, default=0.80)
    parser.add_argument("--face-det-width", type=int, default=640)
    parser.add_argument("--models-dir", type=Path, default=REPO_ROOT / "models" / "face")
    parser.add_argument("--gallery", type=Path, default=default_face_gallery_path())
    # --- multi-camera arena enrollment ("walk in and turn 360 degrees") ---
    parser.add_argument("--arena-config", type=Path, default=None,
                        help="Enroll from ALL cameras in this 6-USB config while the person turns 360.")
    # Generic 1080P units run at this size (they hang at 1280 on USB-2); C920s
    # are bumped to 1280x720 in code for a bigger face crop.
    parser.add_argument("--capture-width", type=int, default=640)
    parser.add_argument("--capture-height", type=int, default=480)
    parser.add_argument("--capture-fps", type=int, default=5)
    parser.add_argument("--fourcc", default="MJPG")
    parser.add_argument("--min-duration", type=float, default=4.0,
                        help="Arena: do not finish before this many seconds.")
    parser.add_argument("--max-duration", type=float, default=30.0,
                        help="Arena: capture window; finishes here regardless (walk one lap).")
    parser.add_argument("--target-samples", type=int, default=24,
                        help="Arena: samples that allow an EARLY finish (else runs the window).")
    parser.add_argument("--target-cameras", type=int, default=1,
                        help="Arena: distinct cameras needed for an early finish.")
    parser.add_argument("--per-camera-interval", type=float, default=0.4,
                        help="Arena: minimum seconds between samples from one camera.")
    parser.add_argument("--arena-min-face-px", type=float, default=30.0)
    parser.add_argument("--arena-min-det-score", type=float, default=0.6)
    parser.add_argument("--arena-det-width", type=int, default=960)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        return list_gallery(args.gallery)
    if args.remove:
        return remove_identity(args.gallery, args.remove)
    if not args.name:
        print("[ERROR] --name is required for enrollment", file=sys.stderr)
        return 2

    if args.arena_config:
        try:
            code = run_arena_enrollment(args)
        except KeyboardInterrupt:
            code = 130
        except Exception as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            code = 1
        # OpenCV's V4L2 backend + our camera threads can std::terminate or sit in
        # do_wait during normal interpreter shutdown even after the gallery is
        # saved. Hard-exit on EVERY path to guarantee a clean, prompt exit code so
        # the app's RUNNING state always clears (START re-enables) and STOP is
        # instant.
        print(f"[EXIT] arena enrollment finished (code {code})", flush=True)
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(code)

    try:
        name = validate_identity_name(args.name)
        samples = max(1, int(args.samples))
        identifier = FaceIdentifier(
            args.models_dir.expanduser(), det_width=max(1, int(args.face_det_width))
        )
        if args.image:
            embeddings = embeddings_from_images(
                identifier,
                args.image,
                min_face_px=args.min_face_px,
                min_det_score=args.min_det_score,
            )
        else:
            embeddings = embeddings_from_camera(
                identifier,
                parse_camera_source(args.camera),
                samples=samples,
                min_face_px=args.min_face_px,
                min_det_score=args.min_det_score,
                preview=not args.no_preview,
                max_seconds=max(1.0, float(args.max_seconds)),
            )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if len(embeddings) < samples:
        print(
            f"[ERROR] Only {len(embeddings)}/{samples} quality samples captured; gallery unchanged.",
            file=sys.stderr,
        )
        return 1

    try:
        gallery = FaceGallery.load(args.gallery)
        if args.replace:
            gallery.remove(name)
        for embedding in embeddings[:samples]:
            gallery.add(name, embedding)
        saved = gallery.save(args.gallery)
    except (OSError, EOFError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[DONE] Enrolled {name}: {samples} samples -> {saved}")
    print("Reminder: local face labels are not anti-spoof/liveness authentication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
