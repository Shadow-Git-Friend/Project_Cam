"""MLOps API surface: model registry and evaluation gate."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from services.api.app.main import app  # noqa: E402

client = TestClient(app)


def test_models_endpoint_lists_registry_without_loading_weights():
    response = client.get("/v1/models")

    assert response.status_code == 200
    body = response.json()
    assert body["registry_version"] == 1
    assert body["default_models"]["ball_detection"]
    assert any(m["task"] == "ball_detection" for m in body["models"])
    assert all("checksum_status" in m for m in body["models"])


def test_evaluate_endpoint_passes_good_inline_pairs():
    pairs = [
        {"pred": [0, 0, 0], "gt": [0, 0, 0]},
        {"pred": [100, 0, 0], "gt": [95, 0, 0]},
        {"pred": [0, 100, 0], "gt": [0, 96, 0]},
        {"pred": [0, 0, 100], "gt": [0, 0, 94]},
        {"pred": [100, 100, 100], "gt": [104, 98, 101]},
    ]

    response = client.post("/v1/evaluate", json={"suite": "ball_static", "pairs": pairs})

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["suite"] == "ball_static"
    assert body["metrics"]["n"] == 5
    assert body["failures"] == []


def test_evaluate_endpoint_reports_failed_gate_as_payload_not_500():
    response = client.post(
        "/v1/evaluate",
        json={
            "suite": "ball_static",
            "metrics": {
                "n": 5,
                "mean_mm": 999.0,
                "median_mm": 999.0,
                "p95_mm": 1000.0,
                "max_mm": 1001.0,
                "rmse_mm": 999.0,
                "precision_mm": 1.0,
                "bias_mm": [0.0, 0.0, 0.0],
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert any("mean" in failure for failure in body["failures"])
