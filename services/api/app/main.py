"""FastAPI entrypoint for the Project_Cam service.

Aim-only by design: this service exposes inference contracts, triangulation,
Kalman prediction, session reports, health, and Prometheus metrics. It can NEVER
send a ``shoot`` command -- BLM firing lives only in the safety-gated launcher
runtime (docs/safety_boundaries.md).

Run:
    uvicorn services.api.app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from project_cam.api import service
from project_cam.api.schemas import (
    CamerasResponse,
    EvaluateRequest,
    EvaluateResponse,
    HealthResponse,
    ModelsResponse,
    PredictRequest,
    PredictResponse,
    SessionReportRequest,
    SystemInfoResponse,
    TriangulateRequest,
    TriangulateResponse,
)
from project_cam.api.service import ServiceError
from project_cam.monitoring import get_metrics

app = FastAPI(
    title="Project_Cam API",
    version=service.API_VERSION,
    summary="Aim-only multi-camera 3D tracking service (triangulation, "
            "prediction, reports, metrics).",
)

_metrics = get_metrics()


@app.exception_handler(ServiceError)
async def _service_error_handler(_request, exc: ServiceError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> dict:
    """Liveness check. Never touches cameras or GPU."""
    return service.health()


@app.get("/v1/system/info", response_model=SystemInfoResponse, tags=["system"])
def system_info() -> dict:
    return service.system_info()


@app.get("/v1/cameras", response_model=CamerasResponse, tags=["system"])
def cameras(profile: str | None = None) -> dict:
    return service.cameras(profile)


@app.post("/v1/triangulate", response_model=TriangulateResponse, tags=["geometry"])
def triangulate(req: TriangulateRequest) -> dict:
    observations = {c: o.model_dump() for c, o in req.observations.items()}
    result = service.triangulate(
        observations,
        calibration_profile=req.calibration_profile,
        projection_matrices=req.projection_matrices,
    )
    profile = req.calibration_profile
    _metrics.observe(
        "project_cam_triangulation_latency_ms",
        result["latency_ms"], camera_profile=profile)
    return result


@app.post("/v1/predict", response_model=PredictResponse, tags=["geometry"])
def predict(req: PredictRequest) -> dict:
    return service.predict(
        req.track, dt=req.dt, process_noise=req.process_noise,
        measurement_noise=req.measurement_noise,
        predict_ahead_ms=req.predict_ahead_ms)


@app.post("/v1/detect/ball", tags=["inference"])
def detect_ball() -> dict:
    return service.detect_stub("ball")


@app.post("/v1/detect/pose", tags=["inference"])
def detect_pose() -> dict:
    return service.detect_stub("pose")


@app.post("/v1/session/report", tags=["assessment"])
def session_report(req: SessionReportRequest) -> dict:
    return service.session_report(req.input_path, exercise=req.exercise)


@app.get("/v1/models", response_model=ModelsResponse, tags=["mlops"])
def models() -> dict:
    return service.models()


@app.post("/v1/evaluate", response_model=EvaluateResponse, tags=["mlops"])
def evaluate(req: EvaluateRequest) -> dict:
    pairs = [p.model_dump() for p in req.pairs] if req.pairs is not None else None
    return service.evaluate(suite=req.suite, pairs=pairs, metrics=req.metrics)


@app.get("/metrics", tags=["system"])
def metrics() -> Response:
    content_type, payload = _metrics.render()
    return Response(content=payload, media_type=content_type)


# Map any stray HTTPException-style 501 contract cleanly (defensive; handlers
# above already raise ServiceError which the handler converts).
@app.get("/", include_in_schema=False)
def root() -> dict:
    raise HTTPException(status_code=404, detail="see /docs")
