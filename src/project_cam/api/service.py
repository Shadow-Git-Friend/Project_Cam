"""Business logic for the API, independent of the web framework.

Every handler returns a plain ``dict`` and raises ``ServiceError`` on bad input
or unconfigured features. ``main.py`` maps those to HTTP responses. Keeping this
layer framework-free means the logic is unit-testable without spinning up a
server and without pydantic/fastapi installed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import numpy as np

from project_cam.evaluation import compute_3d_error, evaluate_against_thresholds, load_thresholds
from project_cam.models import load_model_registry

from . import API_VERSION
from .pipeline_adapter import (
    DEFAULT_PROFILE,
    FALLBACK_PROFILE,
    list_profiles,
    load_camera_profile,
    run_kalman_track,
    triangulate_observations,
)

SERVICE_NAME = "project-cam-api"


class ServiceError(Exception):
    """Raised for client/handler errors with an HTTP-friendly status code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "version": API_VERSION}


def system_info() -> dict:
    try:
        active = load_camera_profile(DEFAULT_PROFILE)
        camera_count = active.camera_count
        profile_name = active.profile
    except Exception:
        # System info must never fail just because a profile file is missing.
        camera_count = None
        profile_name = DEFAULT_PROFILE
    return {
        "service": SERVICE_NAME,
        "version": API_VERSION,
        "camera_profile": profile_name,
        "camera_count": camera_count,
        "fallback_profile": FALLBACK_PROFILE,
        "units": "mm",
        "shooting_enabled": False,  # the API can NEVER fire the launcher.
        "available_profiles": list_profiles(),
    }


def cameras(profile: Optional[str] = None) -> dict:
    name = profile or DEFAULT_PROFILE
    try:
        prof = load_camera_profile(name)
    except (KeyError, FileNotFoundError) as exc:
        raise ServiceError(404, "profile_not_found", str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise ServiceError(400, "profile_invalid", str(exc)) from exc

    cam_list = []
    for cam_id, info in prof.cameras.items():
        info = info or {}
        cam_list.append({
            "camera_id": cam_id,
            "device": info.get("device"),
            "role": info.get("role"),
            "calibrated": bool(info.get("calibrated", False)),
        })
    return {
        "profile": prof.profile,
        "camera_count": prof.camera_count,
        "status": prof.status,
        "validated": prof.validated,
        "cameras": cam_list,
    }


def triangulate(
    observations: Dict[str, dict],
    *,
    calibration_profile: str = DEFAULT_PROFILE,
    projection_matrices: Optional[Dict[str, list]] = None,
) -> dict:
    """Triangulate a world point from >= 2 normalized observations.

    ``observations`` maps camera id -> ``{"x", "y", "space"}``. Projection
    matrices come from the request (``projection_matrices``, each a 3x4 ``[R|t]``)
    -- the self-contained path used in tests and by callers that already hold
    calibration. When omitted, the endpoint reports that server-side calibration
    loading is not configured (501) rather than guessing.
    """
    if len(observations) < 2:
        raise ServiceError(
            422, "insufficient_observations",
            "triangulation requires at least 2 camera observations")

    for cam, obs in observations.items():
        space = (obs or {}).get("space", "normalized")
        if space != "normalized":
            raise ServiceError(
                422, "bad_observation_space",
                f"{cam}: only normalized undistorted observations are supported "
                f"(got space={space!r})")

    if not projection_matrices:
        raise ServiceError(
            501, "calibration_not_configured",
            "server-side calibration loading is not enabled; supply "
            "'projection_matrices' (3x4 [R|t] per camera) in the request")

    obs_xy = {c: (float(o["x"]), float(o["y"])) for c, o in observations.items()}
    t0 = time.perf_counter()
    try:
        point, contributing = triangulate_observations(obs_xy, projection_matrices)
    except ValueError as exc:
        raise ServiceError(422, "bad_projection_matrix", str(exc)) from exc
    latency_ms = (time.perf_counter() - t0) * 1000.0

    if point is None:
        raise ServiceError(
            422, "degenerate_geometry",
            "triangulation failed: fewer than 2 usable cameras or a degenerate "
            "configuration")

    return {
        "point_mm": [float(v) for v in point],
        "contributing_cameras": contributing,
        "camera_count": len(contributing),
        "calibration_profile": calibration_profile,
        "latency_ms": round(latency_ms, 4),
    }


def predict(
    track: List[List[float]],
    *,
    dt: float = 1.0 / 15.0,
    process_noise: float = 500.0,
    measurement_noise: float = 10.0,
    predict_ahead_ms: float = 400.0,
) -> dict:
    if not track:
        raise ServiceError(422, "empty_track", "track must contain >= 1 point")
    try:
        return run_kalman_track(
            track, dt=dt, process_noise=process_noise,
            measurement_noise=measurement_noise, predict_ahead_ms=predict_ahead_ms)
    except ValueError as exc:
        raise ServiceError(422, "bad_track", str(exc)) from exc


def detect_stub(kind: str) -> dict:
    """Detection endpoints exist as contracts but need model weights + GPU.

    Returns a 501 so the route shape is real while staying honest that live
    inference is not wired into the stateless API container.
    """
    raise ServiceError(
        501, "detector_not_configured",
        f"{kind} detection is not configured in the API container; run the live "
        f"pipeline (Parallel_working/) for GPU inference")


def session_report(input_path: Optional[str], exercise: str = "squat") -> dict:
    """Wrap the offline assessment report generator for a recorded JSONL.

    Lazily imports the assessment stack (matplotlib/jinja/ezc3d) so the base API
    stays light. Missing file -> 400; missing deps -> 501.
    """
    if not input_path:
        raise ServiceError(422, "missing_input", "input_path is required")
    import os

    if not os.path.exists(input_path):
        raise ServiceError(404, "input_not_found", f"no such file: {input_path}")
    try:
        from project_cam.assessment.offline_assess import summarize_session  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on optional assess deps
        raise ServiceError(
            501, "assessment_not_configured",
            f"assessment stack unavailable: {exc}; use the CLI "
            f"`python -m project_cam.assessment.offline_assess`") from exc
    try:
        return summarize_session(input_path, exercise=exercise)  # pragma: no cover
    except Exception as exc:  # pragma: no cover
        raise ServiceError(500, "assessment_failed", str(exc)) from exc


def models() -> dict:
    """Return registered model artifacts and provenance without loading weights."""
    try:
        registry = load_model_registry()
        return registry.to_dict(include_checksum_status=True)
    except (OSError, ValueError, KeyError) as exc:
        raise ServiceError(500, "model_registry_invalid", str(exc)) from exc


def evaluate(
    *,
    suite: str,
    pairs: Optional[List[dict]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> dict:
    """Run the configured 3D accuracy regression gate."""
    if (pairs is None) == (metrics is None):
        raise ServiceError(422, "bad_evaluation_request", "provide exactly one of pairs or metrics")

    try:
        thresholds = load_thresholds("configs/eval_thresholds.yaml", suite)
    except KeyError as exc:
        raise ServiceError(404, "evaluation_suite_not_found", str(exc)) from exc
    except OSError as exc:
        raise ServiceError(500, "evaluation_thresholds_missing", str(exc)) from exc

    if pairs is not None:
        try:
            pred = np.asarray([pair["pred"] for pair in pairs], dtype=np.float64)
            gt = np.asarray([pair["gt"] for pair in pairs], dtype=np.float64)
            gate_metrics: Any = compute_3d_error(pred, gt)
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceError(422, "bad_evaluation_pairs", str(exc)) from exc
    else:
        gate_metrics = dict(metrics or {})

    outcome = evaluate_against_thresholds(gate_metrics, thresholds, suite=suite)
    return {
        "passed": outcome.passed,
        "suite": outcome.suite,
        "failures": outcome.failures,
        "metrics": outcome.metrics,
        "thresholds": outcome.thresholds,
    }
