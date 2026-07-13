"""Local YuNet/SFace identity helpers for the arena viewer.

This module is an identification convenience layer, not an authentication or
liveness system.  Embeddings stay local and the default gallery is stored in a
private XDG data directory rather than in the Git checkout.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
SFACE_DIM = 128
SFACE_COSINE_THRESHOLD = 0.363


def validate_identity_name(name: str) -> str:
    """Normalize a display name and reject control characters/oversized data."""
    value = str(name).strip()
    if not value:
        raise ValueError("identity name must not be empty")
    if len(value) > 64:
        raise ValueError("identity name must be at most 64 characters")
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("identity name must not contain control characters")
    return value


def _gallery_path(path) -> Path:
    result = Path(path).expanduser()
    if result.suffix.lower() != ".npz":
        result = result.with_name(result.name + ".npz")
    return result


def default_face_gallery_path() -> Path:
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "project-cam" / "face_gallery.npz"


def _normalize_embedding(value) -> np.ndarray:
    embedding = np.asarray(value, dtype=np.float32).reshape(-1)
    if embedding.shape != (SFACE_DIM,):
        raise ValueError(
            f"SFace embedding must have {SFACE_DIM} values, got {embedding.size}"
        )
    if not np.isfinite(embedding).all():
        raise ValueError("SFace embedding must contain only finite values")
    norm = float(np.linalg.norm(embedding))
    if norm <= 1e-12:
        raise ValueError("SFace embedding must not be a zero vector")
    return embedding / norm


def _load_gallery_data(source: Path) -> Tuple[List[str], np.ndarray, dict]:
    loaded = np.load(source, allow_pickle=False)
    if not isinstance(loaded, np.lib.npyio.NpzFile):
        raise ValueError("gallery must be an NPZ archive")
    with loaded as data:
        if "names" not in data or "embeddings" not in data:
            raise ValueError("gallery must contain names and embeddings")
        names_raw = np.asarray(data["names"])
        if names_raw.ndim != 1:
            raise ValueError(
                f"gallery names must be a one-dimensional array, got {names_raw.shape}"
            )
        names = [validate_identity_name(str(name)) for name in names_raw]
        embeddings = np.asarray(data["embeddings"], dtype=np.float32)
        meta_raw = str(data["meta_json"]) if "meta_json" in data else "{}"

    if embeddings.ndim != 2 or embeddings.shape[1:] != (SFACE_DIM,):
        raise ValueError(
            f"gallery embeddings must have shape (N, {SFACE_DIM}), got {embeddings.shape}"
        )
    if len(names) != embeddings.shape[0]:
        raise ValueError("gallery names row count must match embeddings row count")
    normalized = [_normalize_embedding(row) for row in embeddings]
    loaded_embeddings = (
        np.asarray(normalized, dtype=np.float32)
        if normalized
        else np.zeros((0, SFACE_DIM), dtype=np.float32)
    )
    meta = json.loads(meta_raw)
    if not isinstance(meta, dict):
        raise ValueError("gallery metadata must be a JSON object")
    return names, loaded_embeddings, meta


class FaceGallery:
    """A local set of normalized SFace embeddings grouped by display name."""

    def __init__(self) -> None:
        self.names: List[str] = []
        self.embeddings = np.zeros((0, SFACE_DIM), dtype=np.float32)
        self.meta: dict = {}

    @classmethod
    def load(cls, path) -> "FaceGallery":
        gallery = cls()
        source = _gallery_path(path)
        if not source.exists():
            return gallery
        try:
            names, embeddings, meta = _load_gallery_data(source)
        except (OSError, EOFError, ValueError, zipfile.BadZipFile) as exc:
            raise ValueError(f"cannot load face gallery {source}: {exc}") from exc
        gallery.names = names
        gallery.embeddings = embeddings
        gallery.meta = meta
        return gallery

    def save(self, path) -> Path:
        """Atomically write the gallery with owner-only permissions."""
        target = _gallery_path(path)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        self.meta.setdefault("created_at", now)
        self.meta["updated_at"] = now
        self.meta["people"] = self.people()
        payload = json.dumps(self.meta, ensure_ascii=False, separators=(",", ":"))

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                np.savez(
                    stream,
                    names=np.asarray(self.names, dtype=str),
                    embeddings=self.embeddings.astype(np.float32),
                    meta_json=np.asarray(payload),
                )
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
            os.chmod(target, 0o600)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        return target

    def add(self, name: str, embedding) -> None:
        name = validate_identity_name(name)
        normalized = _normalize_embedding(embedding)
        self.names.append(name)
        self.embeddings = np.vstack((self.embeddings, normalized[None, :]))

    def remove(self, name: str) -> int:
        name = validate_identity_name(name)
        keep = [index for index, current in enumerate(self.names) if current != name]
        removed = len(self.names) - len(keep)
        self.names = [self.names[index] for index in keep]
        self.embeddings = (
            self.embeddings[keep]
            if keep
            else np.zeros((0, SFACE_DIM), dtype=np.float32)
        )
        return removed

    def people(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for name in self.names:
            counts[name] = counts.get(name, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self.names)

    def match(
        self,
        embedding,
        min_score: float = SFACE_COSINE_THRESHOLD,
    ) -> Tuple[Optional[str], float]:
        query = _normalize_embedding(embedding)
        if not self.names:
            return None, 0.0
        similarities = self.embeddings @ query
        best_index = int(np.argmax(similarities))
        score = float(similarities[best_index])
        return (self.names[best_index] if score >= float(min_score) else None, score)


class NameVoter:
    """Turn noisy face matches into a stable, expiring per-track name."""

    def __init__(
        self,
        lock_score: float = 1.5,
        min_votes: int = 3,
        margin: float = 0.3,
        decay: float = 0.92,
        max_misses: int = 30,
    ) -> None:
        if int(min_votes) < 1:
            raise ValueError("min_votes must be >= 1")
        if int(max_misses) < 0:
            raise ValueError("max_misses must be >= 0")
        if not 0.0 < float(decay) <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        self.lock_score = float(lock_score)
        self.min_votes = int(min_votes)
        self.margin = float(margin)
        self.decay = float(decay)
        self.max_misses = int(max_misses)
        self.buckets: Dict[str, float] = {}
        self.vote_counts: Dict[str, int] = {}
        self.locked_name: Optional[str] = None
        self.total_votes = 0
        self.misses = 0

    def add_vote(self, name: Optional[str], score: float = 0.0) -> None:
        for current in list(self.buckets):
            self.buckets[current] *= self.decay
            if self.buckets[current] < 1e-6:
                del self.buckets[current]

        finite_positive = bool(np.isfinite(score) and float(score) > 0.0)
        if name is None or not finite_positive:
            self.misses += 1
            if self.misses > self.max_misses:
                self.locked_name = None
                self.buckets.clear()
                self.vote_counts.clear()
            return

        name = validate_identity_name(name)
        self.misses = 0
        self.total_votes += 1
        self.buckets[name] = self.buckets.get(name, 0.0) + float(score)
        self.vote_counts[name] = self.vote_counts.get(name, 0) + 1
        self._refresh_lock()

    def _refresh_lock(self) -> None:
        if not self.buckets:
            return
        ranked = sorted(self.buckets.items(), key=lambda item: (-item[1], item[0]))
        top_name, top_score = ranked[0]
        runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
        if (
            self.vote_counts.get(top_name, 0) >= self.min_votes
            and top_score >= self.lock_score
            and top_score - runner_score >= self.margin
        ):
            self.locked_name = top_name

    def current(self) -> Tuple[Optional[str], float]:
        if self.locked_name is None:
            return None, 0.0
        return self.locked_name, float(self.buckets.get(self.locked_name, 0.0))


def associate_faces_to_tracks(faces, track_heads_px, gate_px: float) -> Dict[int, int]:
    """Assign faces one-to-one, maximizing people before total proximity."""
    if float(gate_px) < 0:
        raise ValueError("gate_px must be >= 0")
    costs = {}
    for track_id, head in track_heads_px.items():
        head = np.asarray(head, dtype=np.float64).reshape(-1)
        if len(head) < 2 or not np.isfinite(head[:2]).all():
            continue
        for face_index, face in enumerate(faces):
            center = np.asarray(face.get("center"), dtype=np.float64).reshape(-1)
            if len(center) < 2 or not np.isfinite(center[:2]).all():
                continue
            distance = float(np.linalg.norm(center[:2] - head[:2]))
            if distance <= float(gate_px):
                costs[(int(track_id), face_index)] = distance
    if not costs:
        return {}

    track_ids = sorted({track_id for track_id, _face_index in costs})
    track_bits = {
        track_id: 1 << bit for bit, track_id in enumerate(track_ids)
    }
    states = {0: (0.0, ())}
    for face_index in sorted({face_index for _track_id, face_index in costs}):
        next_states = dict(states)
        for mask, (total_cost, mapping) in states.items():
            for track_id in track_ids:
                bit = track_bits[track_id]
                edge = costs.get((track_id, face_index))
                if mask & bit or edge is None:
                    continue
                new_mask = mask | bit
                proposal = (
                    total_cost + edge,
                    tuple(sorted(mapping + ((track_id, face_index),))),
                )
                current = next_states.get(new_mask)
                if (
                    current is None
                    or proposal[0] < current[0] - 1e-12
                    or (
                        abs(proposal[0] - current[0]) <= 1e-12
                        and proposal[1] < current[1]
                    )
                ):
                    next_states[new_mask] = proposal
        states = next_states

    _mask, (_cost, mapping) = min(
        states.items(),
        key=lambda item: (
            -item[0].bit_count(),
            item[1][0],
            item[1][1],
        ),
    )
    return dict(mapping)


def resolve_face_model_paths(models_dir) -> Tuple[Path, Path]:
    directory = Path(models_dir).expanduser()
    detector = directory / YUNET_FILE
    recognizer = directory / SFACE_FILE
    missing = [str(path) for path in (detector, recognizer) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Face ID models missing: "
            + ", ".join(missing)
            + " — run: ./venv/bin/python "
            "Parallel_working/scripts/download_face_models.py"
        )
    return detector, recognizer


class FaceIdentifier:
    """Lazy OpenCV YuNet detector plus SFace embedding runtime."""

    def __init__(
        self,
        models_dir,
        score_thresh: float = 0.7,
        nms_thresh: float = 0.3,
        det_width: int = 640,
        top_k: int = 16,
    ) -> None:
        if int(det_width) <= 0:
            raise ValueError("det_width must be > 0")
        import cv2

        detector_path, recognizer_path = resolve_face_model_paths(models_dir)
        self._cv2 = cv2
        self.det_width = int(det_width)
        try:
            self.detector = cv2.FaceDetectorYN_create(
                str(detector_path),
                "",
                (self.det_width, self.det_width),
                float(score_thresh),
                float(nms_thresh),
                int(top_k),
            )
        except cv2.error as exc:
            raise ValueError(
                f"cannot load YuNet face detector model {detector_path}: {exc}"
            ) from exc
        try:
            self.recognizer = cv2.FaceRecognizerSF_create(str(recognizer_path), "")
        except cv2.error as exc:
            raise ValueError(
                f"cannot load SFace face recognizer model {recognizer_path}: {exc}"
            ) from exc
        self._input_size = None

    def detect_and_encode(self, frame_bgr: np.ndarray) -> List[dict]:
        cv2 = self._cv2
        frame = np.asarray(frame_bgr)
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame_bgr must have shape (height, width, 3)")
        height, width = frame.shape[:2]
        if height <= 0 or width <= 0:
            return []
        scale = self.det_width / float(width)
        detector_height = max(1, int(round(height * scale)))
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
        small = cv2.resize(
            frame, (self.det_width, detector_height), interpolation=interpolation
        )
        size = (self.det_width, detector_height)
        if size != self._input_size:
            self.detector.setInputSize(size)
            self._input_size = size
        _status, detected = self.detector.detect(small)
        if detected is None:
            return []

        inverse_scale = 1.0 / scale
        results = []
        for raw in detected:
            face = np.asarray(raw, dtype=np.float32).copy()
            if face.size < 15 or not np.isfinite(face[:15]).all():
                continue
            face[:14] *= inverse_scale
            x, y, box_width, box_height = face[:4]
            if box_width < 12 or box_height < 12:
                continue
            try:
                aligned = self.recognizer.alignCrop(frame, face)
                feature = self.recognizer.feature(aligned)
                encoded = _normalize_embedding(feature)
            except (cv2.error, ValueError):
                continue
            results.append(
                {
                    "box": (float(x), float(y), float(box_width), float(box_height)),
                    "center": np.array(
                        (x + box_width / 2.0, y + box_height / 2.0),
                        dtype=np.float64,
                    ),
                    "det_score": float(face[14]),
                    "embedding": encoded,
                }
            )
        return results
