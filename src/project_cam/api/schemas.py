"""Pydantic request/response models for the API.

Imported only where pydantic is available (the ``api`` extra). The triangulate
request enforces the >= 2 observation rule at the schema boundary so malformed
requests fail with 422 before reaching the geometry core. Camera counts are never
hardcoded -- observations are an open mapping, so 4-, 6-, or N-camera payloads all
validate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "project-cam-api"
    version: str


class SystemInfoResponse(BaseModel):
    service: str
    version: str
    camera_profile: str
    camera_count: Optional[int] = None
    fallback_profile: str
    units: str = "mm"
    shooting_enabled: bool = False
    available_profiles: List[str] = Field(default_factory=list)


class CameraInfo(BaseModel):
    camera_id: str
    device: Optional[str] = None
    role: Optional[str] = None
    calibrated: bool = False


class CamerasResponse(BaseModel):
    profile: str
    camera_count: int
    status: str
    validated: bool
    cameras: List[CameraInfo]


class ObservationIn(BaseModel):
    x: float
    y: float
    space: Literal["normalized"] = "normalized"


class TriangulateRequest(BaseModel):
    calibration_profile: str = "usb6"
    observations: Dict[str, ObservationIn]
    # Optional per-camera 3x4 [R|t] extrinsic projection (NOT K @ [R|t]).
    projection_matrices: Optional[Dict[str, List[List[float]]]] = None

    @field_validator("observations")
    @classmethod
    def _need_two(cls, v: Dict[str, ObservationIn]) -> Dict[str, ObservationIn]:
        if len(v) < 2:
            raise ValueError("triangulation requires at least 2 observations")
        return v

    @field_validator("projection_matrices")
    @classmethod
    def _check_shape(cls, v):
        if v is None:
            return v
        for cam, mat in v.items():
            if len(mat) != 3 or any(len(row) != 4 for row in mat):
                raise ValueError(f"{cam}: projection matrix must be 3x4 [R|t]")
        return v


class TriangulateResponse(BaseModel):
    point_mm: List[float]
    contributing_cameras: List[str]
    camera_count: int
    calibration_profile: str
    latency_ms: float


class PredictRequest(BaseModel):
    track: List[List[float]] = Field(..., description="N x [x, y, z] in mm")
    dt: float = 1.0 / 15.0
    process_noise: float = 500.0
    measurement_noise: float = 10.0
    predict_ahead_ms: float = 400.0

    @field_validator("track")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("track must contain at least one [x, y, z] point")
        for i, pt in enumerate(v):
            if len(pt) < 3:
                raise ValueError(f"track[{i}] must have 3 coordinates")
        return v


class PredictResponse(BaseModel):
    filtered_position_mm: List[float]
    velocity_mm_s: List[float]
    predicted_position_mm: List[float]
    prediction_uncertainty_mm: float
    predict_ahead_ms: float
    samples: int


class SessionReportRequest(BaseModel):
    input_path: str
    exercise: str = "squat"


class ModelRecordResponse(BaseModel):
    model_id: str
    task: str
    version: str
    backend: str
    artifact_format: str
    path: str
    input_size: List[int]
    status: str
    checksum_sha256: Optional[str] = None
    checksum_status: Dict[str, Optional[str]]
    source: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class ModelsResponse(BaseModel):
    registry_version: int
    default_models: Dict[str, str]
    models: List[ModelRecordResponse]


class EvaluationPairIn(BaseModel):
    pred: List[float]
    gt: List[float]

    @field_validator("pred", "gt")
    @classmethod
    def _point3(cls, v: List[float]) -> List[float]:
        if len(v) != 3:
            raise ValueError("evaluation points must be [x, y, z]")
        return v


class EvaluateRequest(BaseModel):
    suite: str
    pairs: Optional[List[EvaluationPairIn]] = None
    metrics: Optional[Dict[str, Any]] = None

    @field_validator("pairs")
    @classmethod
    def _non_empty_pairs(cls, v):
        if v is not None and not v:
            raise ValueError("pairs must contain at least one pair")
        return v

    @field_validator("metrics")
    @classmethod
    def _non_empty_metrics(cls, v):
        if v is not None and not v:
            raise ValueError("metrics cannot be empty")
        return v

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if (self.pairs is None) == (self.metrics is None):
            raise ValueError("provide exactly one of pairs or metrics")
        return self


class EvaluateResponse(BaseModel):
    passed: bool
    suite: str
    failures: List[str]
    metrics: Dict[str, Any]
    thresholds: Dict[str, Any]


class ErrorResponse(BaseModel):
    code: str
    message: str
