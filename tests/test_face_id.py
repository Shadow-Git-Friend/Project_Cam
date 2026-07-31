"""Pure decision-layer tests for local arena face identification."""

from __future__ import annotations

import os
import sys
import types
import zipfile

import numpy as np
import pytest

from project_cam.tracking import face_id as face_id_module
from project_cam.tracking.face_id import (
    SFACE_DIM,
    FaceGallery,
    FaceIdentifier,
    NameVoter,
    associate_faces_to_tracks,
    default_face_gallery_path,
    resolve_face_model_paths,
    validate_identity_name,
)


def embedding(axis: int, amount: float = 1.0) -> np.ndarray:
    value = np.zeros(SFACE_DIM, dtype=np.float32)
    value[axis] = amount
    return value


def test_gallery_normalizes_matches_and_groups_multiple_samples_by_name():
    gallery = FaceGallery()
    gallery.add("Alice", embedding(0, 3.0))
    gallery.add("Alice", embedding(1))
    gallery.add("Bob", embedding(2))

    assert gallery.people() == {"Alice": 2, "Bob": 1}
    np.testing.assert_allclose(np.linalg.norm(gallery.embeddings, axis=1), 1.0)
    assert gallery.match(embedding(0), min_score=0.8) == ("Alice", pytest.approx(1.0))
    assert gallery.match(embedding(3), min_score=0.8) == (None, pytest.approx(0.0))


@pytest.mark.parametrize(
    "bad",
    [
        np.ones(3),
        np.zeros(SFACE_DIM),
        np.full(SFACE_DIM, np.nan),
        np.full(SFACE_DIM, np.inf),
    ],
)
def test_gallery_rejects_wrong_dimension_zero_and_nonfinite_embeddings(bad):
    gallery = FaceGallery()
    with pytest.raises(ValueError):
        gallery.add("Alice", bad)


def test_gallery_rejects_invalid_query_embedding():
    gallery = FaceGallery()
    gallery.add("Alice", embedding(0))
    with pytest.raises(ValueError):
        gallery.match(np.ones(3))


def test_gallery_suffixless_round_trip_is_atomic_private_and_not_truncated(tmp_path):
    gallery = FaceGallery()
    long_unicode_name = "Алиса-" + "ө" * 58
    gallery.add(long_unicode_name, embedding(0))
    gallery.meta["note"] = "x" * 12_000

    saved = gallery.save(tmp_path / "gallery")
    loaded = FaceGallery.load(tmp_path / "gallery")

    assert saved == tmp_path / "gallery.npz"
    assert saved.exists()
    assert os.stat(saved).st_mode & 0o777 == 0o600
    assert loaded.names == [long_unicode_name]
    assert loaded.meta["note"] == "x" * 12_000
    np.testing.assert_allclose(loaded.embeddings, gallery.embeddings)


@pytest.mark.parametrize(
    ("names", "embeddings", "meta_json", "cause_match"),
    [
        (["Alice"], np.ones((1, 3), dtype=np.float32), "{}", "shape"),
        (
            ["Alice"],
            np.stack([embedding(0), embedding(1)]),
            "{}",
            "row count",
        ),
        (
            ["Alice"],
            np.zeros((1, SFACE_DIM), dtype=np.float32),
            "{}",
            "zero vector",
        ),
        (
            ["Alice"],
            np.full((1, SFACE_DIM), np.nan, dtype=np.float32),
            "{}",
            "finite",
        ),
        (["Alice"], embedding(0)[None, :], "{", "Expecting"),
        (["Alice"], embedding(0)[None, :], "[]", "JSON object"),
    ],
    ids=[
        "embedding-shape",
        "row-count",
        "zero-embedding",
        "nonfinite-embedding",
        "metadata-json",
        "metadata-object",
    ],
)
def test_gallery_load_wraps_corrupt_gallery_data_with_path_and_cause(
    tmp_path, names, embeddings, meta_json, cause_match
):
    path = tmp_path / "broken.npz"
    with path.open("wb") as fh:
        np.savez(
            fh,
            names=np.asarray(names),
            embeddings=embeddings,
            meta_json=np.asarray(meta_json),
        )

    with pytest.raises(ValueError) as caught:
        FaceGallery.load(path)

    assert str(path) in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)
    assert cause_match in str(caught.value.__cause__)


def test_gallery_load_wraps_numpy_payload_that_is_not_an_npz_archive(tmp_path):
    path = tmp_path / "disguised.npz"
    with path.open("wb") as fh:
        np.save(fh, embedding(0))

    with pytest.raises(ValueError) as caught:
        FaceGallery.load(path)

    assert str(path) in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)
    assert "NPZ" in str(caught.value.__cause__)


@pytest.mark.parametrize(
    "names",
    [np.asarray("Alice"), np.asarray([["Alice"]])],
    ids=["scalar", "two-dimensional"],
)
def test_gallery_load_wraps_non_vector_names_array(tmp_path, names):
    path = tmp_path / "broken-names.npz"
    with path.open("wb") as fh:
        np.savez(
            fh,
            names=names,
            embeddings=embedding(0)[None, :],
            meta_json=np.asarray("{}"),
        )

    with pytest.raises(ValueError) as caught:
        FaceGallery.load(path)

    assert str(path) in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)
    assert "names" in str(caught.value.__cause__)


@pytest.mark.parametrize(
    "load_error",
    [
        OSError("read failed"),
        EOFError("truncated archive"),
        ValueError("invalid array data"),
        zipfile.BadZipFile("invalid zip archive"),
    ],
    ids=["os-error", "eof-error", "value-error", "bad-zip"],
)
def test_gallery_load_wraps_known_archive_errors_with_path_and_cause(
    monkeypatch, tmp_path, load_error
):
    path = tmp_path / "corrupt.npz"
    path.touch()

    def fail_load(*_args, **_kwargs):
        raise load_error

    monkeypatch.setattr(face_id_module.np, "load", fail_load)

    with pytest.raises(ValueError) as caught:
        FaceGallery.load(path)

    assert str(path) in str(caught.value)
    assert caught.value.__cause__ is load_error


def test_gallery_load_does_not_mask_unexpected_errors(monkeypatch, tmp_path):
    path = tmp_path / "gallery.npz"
    path.touch()
    unexpected = RuntimeError("unexpected loader failure")

    def fail_load(*_args, **_kwargs):
        raise unexpected

    monkeypatch.setattr(face_id_module.np, "load", fail_load)

    with pytest.raises(RuntimeError) as caught:
        FaceGallery.load(path)

    assert caught.value is unexpected


def test_remove_identity_and_empty_gallery_shape():
    gallery = FaceGallery()
    gallery.add("Alice", embedding(0))
    gallery.add("Alice", embedding(1))
    gallery.add("Bob", embedding(2))

    assert gallery.remove("Alice") == 2
    assert gallery.people() == {"Bob": 1}
    assert gallery.remove("Bob") == 1
    assert gallery.embeddings.shape == (0, SFACE_DIM)


def test_name_voter_requires_repeated_evidence_and_expires_after_misses():
    voter = NameVoter(lock_score=1.5, min_votes=3, margin=0.2, max_misses=2, decay=1.0)
    voter.add_vote("Alice", 1.0)
    voter.add_vote("Alice", 1.0)
    assert voter.current()[0] is None
    voter.add_vote("Alice", 1.0)
    assert voter.current() == ("Alice", pytest.approx(3.0))

    voter.add_vote(None)
    voter.add_vote(None)
    assert voter.current()[0] == "Alice"
    voter.add_vote(None)
    assert voter.current() == (None, 0.0)


def test_name_voter_challenger_needs_consistent_lead_to_switch():
    voter = NameVoter(lock_score=1.0, min_votes=2, margin=0.3, max_misses=10, decay=1.0)
    voter.add_vote("Alice", 0.8)
    voter.add_vote("Alice", 0.8)
    assert voter.current()[0] == "Alice"

    voter.add_vote("Bob", 1.0)
    assert voter.current()[0] == "Alice"
    voter.add_vote("Bob", 1.0)
    assert voter.current()[0] == "Bob"


def test_face_to_track_assignment_is_gated_and_one_to_one():
    faces = [
        {"center": np.array((10.0, 10.0))},
        {"center": np.array((35.0, 10.0))},
        {"center": np.array((500.0, 500.0))},
    ]
    heads = {1: np.array((12.0, 10.0)), 2: np.array((30.0, 10.0))}

    assigned = associate_faces_to_tracks(faces, heads, gate_px=20.0)

    assert assigned == {1: 0, 2: 1}
    assert len(set(assigned.values())) == len(assigned)


def test_face_assignment_maximizes_people_before_minimizing_distance():
    faces = [
        {"center": np.array((0.0, 0.0))},
        {"center": np.array((-2.0, 0.0))},
    ]
    heads = {
        1: np.array((0.0, 0.0)),   # can use either face
        2: np.array((1.0, 0.0)),   # can only use face 0 within the gate
    }

    assert associate_faces_to_tracks(faces, heads, gate_px=2.5) == {1: 1, 2: 0}


def test_model_path_error_names_missing_files(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        resolve_face_model_paths(tmp_path)
    message = str(exc.value)
    assert "face_detection_yunet_2023mar.onnx" in message
    assert "face_recognition_sface_2021dec.onnx" in message
    assert "download_face_models.py" in message


@pytest.mark.parametrize(
    ("failing_factory", "model_name", "path_index"),
    [
        ("detector", "YuNet", 0),
        ("recognizer", "SFace", 1),
    ],
)
def test_face_identifier_wraps_each_opencv_model_constructor_error(
    monkeypatch, tmp_path, failing_factory, model_name, path_index
):
    detector_path = tmp_path / "detector.onnx"
    recognizer_path = tmp_path / "recognizer.onnx"
    model_paths = (detector_path, recognizer_path)
    monkeypatch.setattr(
        face_id_module,
        "resolve_face_model_paths",
        lambda _models_dir: model_paths,
    )

    class FakeCvError(Exception):
        pass

    failure = FakeCvError("OpenCV constructor failed")
    fake_cv2 = types.ModuleType("cv2")
    fake_cv2.error = FakeCvError

    def create_detector(*_args):
        if failing_factory == "detector":
            raise failure
        return object()

    def create_recognizer(*_args):
        if failing_factory == "recognizer":
            raise failure
        return object()

    fake_cv2.FaceDetectorYN_create = create_detector
    fake_cv2.FaceRecognizerSF_create = create_recognizer
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    with pytest.raises(ValueError) as caught:
        FaceIdentifier(tmp_path)

    message = str(caught.value)
    assert model_name in message
    assert str(model_paths[path_index]) in message
    assert caught.value.__cause__ is failure


def test_default_gallery_uses_private_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_face_gallery_path() == tmp_path / "project-cam" / "face_gallery.npz"


@pytest.mark.parametrize("name", ["", "   ", "bad\nname", "x" * 65])
def test_identity_name_validation_rejects_unsafe_or_oversized_names(name):
    with pytest.raises(ValueError):
        validate_identity_name(name)


def test_identity_name_validation_preserves_unicode_and_trims_spaces():
    assert validate_identity_name("  Айша Өмір  ") == "Айша Өмір"
