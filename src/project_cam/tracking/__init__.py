"""Multi-person tracking and local identity helpers."""

from .face_id import (
    SFACE_COSINE_THRESHOLD,
    SFACE_DIM,
    FaceGallery,
    FaceIdentifier,
    NameVoter,
    associate_faces_to_tracks,
    default_face_gallery_path,
    resolve_face_model_paths,
    validate_identity_name,
)
from .multi_person import (
    MAX_TRACKED_PEOPLE,
    MultiPersonTracker,
    PersonTrack,
    candidate_anchor_px,
)

__all__ = [
    "FaceGallery",
    "FaceIdentifier",
    "MAX_TRACKED_PEOPLE",
    "MultiPersonTracker",
    "NameVoter",
    "PersonTrack",
    "SFACE_COSINE_THRESHOLD",
    "SFACE_DIM",
    "associate_faces_to_tracks",
    "candidate_anchor_px",
    "default_face_gallery_path",
    "resolve_face_model_paths",
    "validate_identity_name",
]
