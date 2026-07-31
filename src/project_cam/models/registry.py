"""Hardware-free model registry with provenance, checksum and licence checks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "configs" / "models.yaml"

#: Allowed values for ``Licensing.commercial_use``.
#:
#: ``undeclared`` is the default on purpose: a record that says nothing must read
#: as a gap, never as permission.
COMMERCIAL_VERDICTS = ("clear", "blocked", "unverified", "undeclared")

#: Markers that make a licence layer non-commercial. Matched with word
#: boundaries so ``aic`` hits ``pt-aic-coco`` but not ``mosaic``.
#:
#: This list is the memory of every blocker found so far. ``aic`` is here because
#: a permissive repository badge hid it: MMPose is Apache-2.0, but every published
#: RTMPose checkpoint is pretrained on AI Challenger, which is research-only.
NON_COMMERCIAL_MARKERS = (
    r"agpl",
    r"aic\b",
    r"ai[ -]challenger",
    r"mpii",
    r"crowdpose",
    r"halpe",
    r"body[78]\b",
    r"smpl",
    r"cc[- ]by[- ]nc",
    r"non[- ]commercial",
    r"research[- ]only",
)

_MARKER_RE = re.compile(
    "|".join(rf"(?<![0-9a-z]){pattern}" for pattern in NON_COMMERCIAL_MARKERS),
    re.IGNORECASE,
)


def non_commercial_markers(text: Optional[str]) -> List[str]:
    """Return the non-commercial markers found in a licence-layer string.

    Empty list means "nothing recognised", which is NOT the same as "clean" — an
    unrecognised licence name is simply unverified.
    """
    if not text:
        return []
    return sorted({match.group(0).lower() for match in _MARKER_RE.finditer(text)})


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Return the SHA-256 digest for a file without loading it all at once."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _as_pair(value: Any, *, field_name: str) -> Tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field_name} must be a 2-item [height, width] list")
    return int(value[0]), int(value[1])


@dataclass(frozen=True)
class Licensing:
    """Three-layer licence record for one model artifact.

    The layers are separate because they routinely disagree, and the third one is
    invisible in a repository badge:

    * ``code`` — the framework's licence (Apache-2.0, AGPL-3.0, ...).
    * ``weights`` — the checkpoint's own licence, which can differ from the code's.
    * ``training_data`` — the datasets the checkpoint absorbed. This is where every
      blocker so far has lived, and it does not appear in either of the above.

    ``commercial_use`` is the verdict a human recorded after checking all three,
    with ``evidence`` naming *where* it was checked (a config path, a licence file,
    a vendor statement). Defaults are deliberately pessimistic.
    """

    code: Optional[str] = None
    weights: Optional[str] = None
    training_data: Optional[str] = None
    commercial_use: str = "undeclared"
    blocker: Optional[str] = None
    evidence: Optional[str] = None
    verified_on: Optional[str] = None

    def __post_init__(self) -> None:
        if self.commercial_use not in COMMERCIAL_VERDICTS:
            raise ValueError(
                f"commercial_use must be one of {COMMERCIAL_VERDICTS}, "
                f"got {self.commercial_use!r}"
            )
        if self.commercial_use == "clear":
            found = self.detected_markers()
            if found:
                raise ValueError(
                    "commercial_use='clear' contradicts non-commercial markers "
                    f"{found} in the licence layers"
                )

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Licensing":
        if not data:
            return cls()
        return cls(
            code=data.get("code"),
            weights=data.get("weights"),
            training_data=data.get("training_data"),
            commercial_use=str(data.get("commercial_use", "undeclared")),
            blocker=data.get("blocker"),
            evidence=data.get("evidence"),
            verified_on=str(data["verified_on"]) if data.get("verified_on") else None,
        )

    def undeclared_layers(self) -> List[str]:
        """Names of the layers this record leaves blank."""
        return [
            name
            for name in ("code", "weights", "training_data")
            if not getattr(self, name)
        ]

    def detected_markers(self) -> List[str]:
        """Non-commercial markers found across all three layers."""
        found: List[str] = []
        for layer in (self.code, self.weights, self.training_data):
            found.extend(non_commercial_markers(layer))
        return sorted(set(found))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "weights": self.weights,
            "training_data": self.training_data,
            "commercial_use": self.commercial_use,
            "blocker": self.blocker,
            "evidence": self.evidence,
            "verified_on": self.verified_on,
            "undeclared_layers": self.undeclared_layers(),
            "detected_markers": self.detected_markers(),
        }


@dataclass(frozen=True)
class ModelRecord:
    """One model artifact and the metadata needed to reason about deployment."""

    model_id: str
    task: str
    version: str
    backend: str
    artifact_format: str
    path: str
    input_size: Tuple[int, int]
    status: str
    checksum_sha256: Optional[str] = None
    source: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = None
    licensing: Licensing = field(default_factory=Licensing)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelRecord":
        required = [
            "model_id",
            "task",
            "version",
            "backend",
            "artifact_format",
            "path",
            "input_size",
            "status",
        ]
        missing = [name for name in required if name not in data]
        if missing:
            raise ValueError(f"model record missing required fields: {missing}")
        return cls(
            model_id=str(data["model_id"]),
            task=str(data["task"]),
            version=str(data["version"]),
            backend=str(data["backend"]),
            artifact_format=str(data["artifact_format"]),
            path=str(data["path"]),
            input_size=_as_pair(data["input_size"], field_name="input_size"),
            status=str(data["status"]),
            checksum_sha256=data.get("checksum_sha256") or None,
            source=data.get("source"),
            metrics=dict(data.get("metrics") or {}),
            notes=data.get("notes"),
            licensing=Licensing.from_dict(data.get("licensing")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "task": self.task,
            "version": self.version,
            "backend": self.backend,
            "artifact_format": self.artifact_format,
            "path": self.path,
            "input_size": list(self.input_size),
            "status": self.status,
            "checksum_sha256": self.checksum_sha256,
            "source": self.source,
            "metrics": self.metrics,
            "notes": self.notes,
            # Always present, even when the YAML says nothing: a missing licence
            # must read as an explicit gap in the API response, not as an absent
            # field a consumer can overlook.
            "licensing": self.licensing.to_dict(),
        }


class ModelRegistry:
    """Collection of model records plus default deployment choices."""

    def __init__(
        self,
        *,
        registry_version: int,
        models: List[ModelRecord],
        project_root: str | Path,
        default_models: Optional[Dict[str, str]] = None,
    ) -> None:
        self.registry_version = int(registry_version)
        self.project_root = Path(project_root)
        self.default_models = dict(default_models or {})
        self._models = {m.model_id: m for m in models}
        if len(self._models) != len(models):
            raise ValueError("duplicate model_id in registry")
        for task, model_id in self.default_models.items():
            if model_id not in self._models:
                raise ValueError(f"default model for {task!r} points to unknown {model_id!r}")

    @property
    def models(self) -> List[ModelRecord]:
        return list(self._models.values())

    def get(self, model_id: str) -> ModelRecord:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown model_id: {model_id!r}") from exc

    def active_models(self) -> List[ModelRecord]:
        return [m for m in self.models if m.status == "active"]

    def commercial_blockers(self, *, statuses: Tuple[str, ...] = ("active",)) -> List[Dict[str, Any]]:
        """Models in ``statuses`` that are not cleared for commercial use.

        Returns one row per problem model so the gap is queryable rather than
        remembered. ``undeclared`` counts as a blocker: an unaudited artifact is
        not a clean one, which is the whole lesson of the AI Challenger finding.
        """
        rows: List[Dict[str, Any]] = []
        for model in self.models:
            if model.status not in statuses:
                continue
            licence = model.licensing
            if licence.commercial_use == "clear":
                continue
            rows.append(
                {
                    "model_id": model.model_id,
                    "task": model.task,
                    "commercial_use": licence.commercial_use,
                    "blocker": licence.blocker,
                    "undeclared_layers": licence.undeclared_layers(),
                    "detected_markers": licence.detected_markers(),
                }
            )
        return rows

    def default_model(self, task: str) -> ModelRecord:
        try:
            model_id = self.default_models[task]
        except KeyError as exc:
            raise KeyError(f"no default model registered for task {task!r}") from exc
        return self.get(model_id)

    def resolve_path(self, model_id: str) -> Path:
        record = self.get(model_id)
        path = Path(record.path)
        return path if path.is_absolute() else self.project_root / path

    def checksum_status(self, model_id: str) -> Dict[str, Optional[str]]:
        record = self.get(model_id)
        path = self.resolve_path(model_id)
        expected = record.checksum_sha256
        if not path.exists():
            return {
                "status": "missing_file",
                "sha256": None,
                "expected_sha256": expected,
            }
        if not expected:
            return {
                "status": "unregistered",
                "sha256": None,
                "expected_sha256": None,
            }
        actual = sha256_file(path)
        return {
            "status": "ok" if actual == expected else "mismatch",
            "sha256": actual,
            "expected_sha256": expected,
        }

    def to_dict(self, *, include_checksum_status: bool = False) -> Dict[str, Any]:
        records = []
        for model in self.models:
            data = model.to_dict()
            if include_checksum_status:
                data["checksum_status"] = self.checksum_status(model.model_id)
            records.append(data)
        return {
            "registry_version": self.registry_version,
            "default_models": dict(self.default_models),
            "models": records,
        }


def load_model_registry(
    path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    project_root: str | Path = REPO_ROOT,
) -> ModelRegistry:
    """Load a model registry YAML file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    models = [ModelRecord.from_dict(item) for item in data.get("models", [])]
    return ModelRegistry(
        registry_version=int(data.get("registry_version", 1)),
        models=models,
        project_root=project_root,
        default_models=data.get("default_models") or {},
    )
