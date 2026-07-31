#!/usr/bin/env python3
"""Download pinned OpenCV Zoo YuNet/SFace models with SHA-256 verification."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    filename: str
    url: str
    sha256: str
    size: int


MODEL_SPECS = (
    ModelSpec(
        filename="face_detection_yunet_2023mar.onnx",
        url=(
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_detection_yunet/face_detection_yunet_2023mar.onnx"
        ),
        sha256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        size=232_589,
    ),
    ModelSpec(
        filename="face_recognition_sface_2021dec.onnx",
        url=(
            "https://github.com/opencv/opencv_zoo/raw/main/models/"
            "face_recognition_sface/face_recognition_sface_2021dec.onnx"
        ),
        sha256="0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        size=38_696_353,
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_model(path: Path, spec: ModelSpec) -> bool:
    path = Path(path)
    return (
        path.is_file()
        and path.stat().st_size == spec.size
        and sha256_file(path) == spec.sha256
    )


def download_model(
    spec: ModelSpec,
    output_dir: Path,
    *,
    opener=urllib.request.urlopen,
    force: bool = False,
) -> Path:
    """Download one model to a sibling temp file, verify, then atomically replace."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / spec.filename
    if target.exists() and not force and verify_model(target, spec):
        print(f"[OK] {spec.filename}: already verified")
        return target

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{spec.filename}.", suffix=".part", dir=output_dir
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        print(f"[GET] {spec.url}")
        with opener(spec.url, timeout=120) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        actual_size = temporary.stat().st_size
        actual_sha256 = sha256_file(temporary)
        if actual_size != spec.size or actual_sha256 != spec.sha256:
            raise ValueError(
                f"SHA-256/size verification failed for {spec.filename}: "
                f"size={actual_size} sha256={actual_sha256}"
            )
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
        print(f"[OK] {target} ({actual_size:,} bytes, sha256={actual_sha256})")
        return target
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parent.parent.parent
    parser = argparse.ArgumentParser(
        description="Download SHA-256-pinned YuNet and SFace models from OpenCV Zoo."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "models" / "face",
        help="Destination directory (default: <repo>/models/face).",
    )
    parser.add_argument("--force", action="store_true", help="Download again even if valid.")
    parser.add_argument(
        "--verify-only", action="store_true", help="Do not use the network; verify existing files."
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    failures = []
    for spec in MODEL_SPECS:
        target = args.output_dir.expanduser() / spec.filename
        if args.verify_only:
            if verify_model(target, spec):
                print(f"[OK] {target}")
            else:
                failures.append(spec.filename)
                print(f"[FAIL] {target}")
            continue
        try:
            download_model(spec, args.output_dir.expanduser(), force=args.force)
        except (OSError, ValueError) as exc:
            failures.append(spec.filename)
            print(f"[FAIL] {exc}")
    if failures:
        print("Missing/invalid models: " + ", ".join(failures))
        return 1
    print("Face models are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
