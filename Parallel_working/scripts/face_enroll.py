#!/usr/bin/env python3
"""Enroll, list, or remove identities in the private local SFace gallery."""

from __future__ import annotations

import argparse
import sys
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
    gallery = FaceGallery.load(path)
    print(f"Gallery: {Path(path).expanduser()}")
    if not len(gallery):
        print("  (empty)")
        return 0
    for name, samples in sorted(gallery.people().items()):
        print(f"  {name}: {samples} sample(s)")
    return 0


def remove_identity(path, name: str) -> int:
    name = validate_identity_name(name)
    gallery = FaceGallery.load(path)
    removed = gallery.remove(name)
    if not removed:
        print(f"Identity not found: {name}")
        return 1
    saved = gallery.save(path)
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
    collected = []
    frame_index = 0
    started = time.monotonic()
    window = "Project Cam — Local Face Enrollment"
    try:
        while len(collected) < samples and time.monotonic() - started < max_seconds:
            ok, frame = capture.read()
            if not ok:
                break
            frame_index += 1
            faces = identifier.detect_and_encode(frame)
            selected = choose_enrollment_face(
                faces,
                frame_shape=frame.shape,
                min_face_px=min_face_px,
                min_det_score=min_det_score,
            )
            # Sample periodically so the gallery contains natural small pose
            # changes instead of a burst of nearly identical adjacent frames.
            if selected is not None and frame_index % 5 == 0:
                collected.append(selected["embedding"])
                print(f"[CAPTURE] {len(collected)}/{samples}")

            if preview:
                for face in faces:
                    x, y, width, height = map(int, face["box"])
                    color = (80, 220, 120) if face is selected else (100, 100, 100)
                    cv2.rectangle(frame, (x, y), (x + width, y + height), color, 2)
                cv2.putText(
                    frame,
                    f"Samples {len(collected)}/{samples} | turn slightly | Q cancel",
                    (16, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (80, 220, 120),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow(window, frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
    finally:
        capture.release()
        if preview:
            cv2.destroyWindow(window)
    return collected


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

    gallery = FaceGallery.load(args.gallery)
    if args.replace:
        gallery.remove(name)
    for embedding in embeddings[:samples]:
        gallery.add(name, embedding)
    saved = gallery.save(args.gallery)
    print(f"[DONE] Enrolled {name}: {samples} samples -> {saved}")
    print("Reminder: local face labels are not anti-spoof/liveness authentication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
