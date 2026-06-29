"""Model registry/provenance behavior.

The registry is intentionally hardware-free: it records what model artifacts are
expected, where they live, and whether a file's checksum matches the registered
provenance. It must not import YOLO/TensorRT.
"""

from __future__ import annotations

import hashlib

from project_cam.models.registry import load_model_registry, sha256_file


def test_registry_loads_models_and_verifies_checksum(tmp_path):
    artifact = tmp_path / "toy.engine"
    artifact.write_bytes(b"toy model artifact")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    config = tmp_path / "models.yaml"
    config.write_text(
        f"""
registry_version: 1
default_models:
  ball_detection: toy_ball_trt
models:
  - model_id: toy_ball_trt
    task: ball_detection
    version: "2026-06-29"
    backend: tensorrt
    artifact_format: engine
    path: toy.engine
    input_size: [672, 672]
    status: active
    checksum_sha256: {digest}
    source: synthetic-test
""",
        encoding="utf-8",
    )

    registry = load_model_registry(config, project_root=tmp_path)

    record = registry.get("toy_ball_trt")
    assert record.task == "ball_detection"
    assert record.backend == "tensorrt"
    assert record.input_size == (672, 672)
    assert registry.default_model("ball_detection").model_id == "toy_ball_trt"
    assert registry.checksum_status("toy_ball_trt") == {
        "status": "ok",
        "sha256": digest,
        "expected_sha256": digest,
    }
    assert sha256_file(artifact) == digest


def test_registry_reports_missing_artifact_without_crashing(tmp_path):
    config = tmp_path / "models.yaml"
    config.write_text(
        """
registry_version: 1
models:
  - model_id: missing_pose
    task: pose_estimation
    version: "2026-06-29"
    backend: tensorrt
    artifact_format: engine
    path: missing.engine
    input_size: [640, 640]
    status: planned
""",
        encoding="utf-8",
    )

    registry = load_model_registry(config, project_root=tmp_path)

    assert registry.checksum_status("missing_pose") == {
        "status": "missing_file",
        "sha256": None,
        "expected_sha256": None,
    }


def test_real_project_registry_has_active_default_ball_model():
    registry = load_model_registry()

    default_ball = registry.default_model("ball_detection")
    assert default_ball.status == "active"
    assert default_ball.model_id in {m.model_id for m in registry.active_models()}
    assert default_ball.path.startswith("models/")
