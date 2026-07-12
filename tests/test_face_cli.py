"""Headless tests for Face-ID model setup and enrollment CLIs."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from project_cam.tracking import SFACE_DIM, FaceGallery

DOWNLOAD = Path("Parallel_working/scripts/download_face_models.py")
ENROLL = Path("Parallel_working/scripts/face_enroll.py")


def load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_downloader_pins_official_model_size_and_sha256():
    module = load_script(DOWNLOAD, "download_face_models_contract")
    specs = {spec.filename: spec for spec in module.MODEL_SPECS}
    assert specs["face_detection_yunet_2023mar.onnx"].size == 232_589
    assert specs["face_detection_yunet_2023mar.onnx"].sha256 == (
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    )
    assert specs["face_recognition_sface_2021dec.onnx"].size == 38_696_353
    assert specs["face_recognition_sface_2021dec.onnx"].sha256 == (
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
    )


def test_atomic_download_verifies_hash_before_replacing_destination(tmp_path):
    module = load_script(DOWNLOAD, "download_face_models_atomic")
    payload = b"verified model bytes"
    spec = module.ModelSpec(
        filename="model.onnx",
        url="https://example.invalid/model.onnx",
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
    )
    target = tmp_path / spec.filename

    result = module.download_model(
        spec, tmp_path, opener=lambda *_args, **_kwargs: Response(payload)
    )

    assert result == target
    assert target.read_bytes() == payload
    assert not list(tmp_path.glob("*.part"))


def test_bad_download_does_not_replace_existing_valid_file(tmp_path):
    module = load_script(DOWNLOAD, "download_face_models_bad")
    target = tmp_path / "model.onnx"
    target.write_bytes(b"old")
    spec = module.ModelSpec(
        filename=target.name,
        url="https://example.invalid/model.onnx",
        sha256=hashlib.sha256(b"wanted").hexdigest(),
        size=6,
    )
    with pytest.raises(ValueError, match="SHA-256"):
        module.download_model(
            spec,
            tmp_path,
            opener=lambda *_args, **_kwargs: Response(b"tampered"),
            force=True,
        )
    assert target.read_bytes() == b"old"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0", 0), ("12", 12), ("/dev/video4", "/dev/video4"), ("clip.mp4", "clip.mp4")],
)
def test_enrollment_camera_source_parsing(raw, expected):
    module = load_script(ENROLL, f"face_enroll_source_{raw.replace('/', '_')}")
    assert module.parse_camera_source(raw) == expected


def test_enrollment_face_quality_gate_selects_largest_centered_face():
    module = load_script(ENROLL, "face_enroll_quality")
    faces = [
        {"box": (1, 1, 30, 30), "det_score": 0.99},
        {"box": (40, 30, 120, 120), "det_score": 0.91, "embedding": np.ones(SFACE_DIM)},
        {"box": (0, 0, 180, 180), "det_score": 0.4},
    ]
    selected = module.choose_enrollment_face(
        faces, frame_shape=(200, 240, 3), min_face_px=70, min_det_score=0.8
    )
    assert selected is faces[1]


def test_gallery_list_and_remove_actions_are_headless(tmp_path, capsys):
    module = load_script(ENROLL, "face_enroll_actions")
    path = tmp_path / "gallery.npz"
    gallery = FaceGallery()
    embedding = np.zeros(SFACE_DIM, dtype=np.float32)
    embedding[0] = 1.0
    gallery.add("Alice", embedding)
    gallery.save(path)

    assert module.list_gallery(path) == 0
    assert "Alice" in capsys.readouterr().out
    assert module.remove_identity(path, "Alice") == 0
    assert FaceGallery.load(path).people() == {}


@pytest.mark.parametrize("script", [DOWNLOAD, ENROLL])
def test_face_cli_help_is_headless(script):
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
