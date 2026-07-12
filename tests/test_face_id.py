"""Pure decision-layer tests for local arena face identification."""

from __future__ import annotations

import os

import numpy as np
import pytest

from project_cam.tracking.face_id import (
    SFACE_DIM,
    FaceGallery,
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


def test_gallery_load_rejects_malformed_row_count(tmp_path):
    path = tmp_path / "broken.npz"
    with path.open("wb") as fh:
        np.savez(
            fh,
            names=np.array(["Alice"]),
            embeddings=np.stack([embedding(0), embedding(1)]),
            meta_json=np.array("{}"),
        )
    with pytest.raises(ValueError, match="names"):
        FaceGallery.load(path)


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


def test_default_gallery_uses_private_xdg_data_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_face_gallery_path() == tmp_path / "project-cam" / "face_gallery.npz"


@pytest.mark.parametrize("name", ["", "   ", "bad\nname", "x" * 65])
def test_identity_name_validation_rejects_unsafe_or_oversized_names(name):
    with pytest.raises(ValueError):
        validate_identity_name(name)


def test_identity_name_validation_preserves_unicode_and_trims_spaces():
    assert validate_identity_name("  Айша Өмір  ") == "Айша Өмір"
