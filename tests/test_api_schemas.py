"""Pydantic schema validation (skips if the API extra is not installed)."""

import pytest

pytest.importorskip("pydantic")

from project_cam.api.schemas import (  # noqa: E402
    EvaluateRequest,
    ObservationIn,
    PredictRequest,
    TriangulateRequest,
)


def test_triangulate_request_accepts_six_cameras():
    req = TriangulateRequest(
        calibration_profile="usb6",
        observations={f"cam{i}": {"x": 0.01 * i, "y": -0.02} for i in range(6)},
    )
    assert len(req.observations) == 6


def test_triangulate_request_rejects_single_observation():
    with pytest.raises(Exception):
        TriangulateRequest(
            calibration_profile="usb6",
            observations={"camA": {"x": 0.0, "y": 0.0}},
        )


def test_triangulate_request_rejects_bad_projection_shape():
    with pytest.raises(Exception):
        TriangulateRequest(
            observations={"a": {"x": 0, "y": 0}, "b": {"x": 0.1, "y": 0.1}},
            projection_matrices={"a": [[1, 2, 3]]},  # not 3x4
        )


def test_observation_rejects_non_normalized_space():
    with pytest.raises(Exception):
        ObservationIn(x=0.0, y=0.0, space="pixels")


def test_predict_request_rejects_empty_track():
    with pytest.raises(Exception):
        PredictRequest(track=[])


def test_predict_request_rejects_short_point():
    with pytest.raises(Exception):
        PredictRequest(track=[[1.0, 2.0]])


def test_evaluate_request_requires_pairs_or_metrics():
    with pytest.raises(Exception):
        EvaluateRequest(suite="ball_static")


def test_evaluate_request_rejects_pairs_and_metrics_together():
    with pytest.raises(Exception):
        EvaluateRequest(
            suite="ball_static",
            pairs=[{"pred": [0, 0, 0], "gt": [0, 0, 0]}],
            metrics={"n": 1},
        )
