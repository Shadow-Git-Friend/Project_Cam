"""Triangulate + predict endpoints (skips without the API extra).

Confirms the endpoint reuses the geometry core (recovers a synthetic point) and
enforces the >= 2 observation rule and the normalized-only convention.
"""

import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from services.api.app.main import app  # noqa: E402

client = TestClient(app)

TARGET = np.array([1500.0, 800.0, 900.0])


def look_at(center, target, up=(0.0, 0.0, 1.0)):
    center = np.asarray(center, float)
    target = np.asarray(target, float)
    up = np.asarray(up, float)
    z = target - center
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.column_stack([x, y, z]).T
    t = -R @ center
    return R, t


def _payload(centers):
    obs, proj = {}, {}
    for name, c in centers.items():
        R, t = look_at(c, TARGET)
        Xc = R @ TARGET + t
        obs[name] = {"x": float(Xc[0] / Xc[2]), "y": float(Xc[1] / Xc[2]),
                     "space": "normalized"}
        proj[name] = np.hstack([R, t.reshape(3, 1)]).tolist()
    return {"calibration_profile": "usb6", "observations": obs,
            "projection_matrices": proj}


def test_triangulate_recovers_point():
    body = _payload({"a": [0, 0, 1500], "b": [3000, 0, 1500],
                     "c": [0, 3000, 1400], "d": [3000, 3000, 1600]})
    r = client.post("/v1/triangulate", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert np.allclose(out["point_mm"], TARGET, atol=1e-3)
    assert out["camera_count"] == 4
    assert "latency_ms" in out


def test_triangulate_rejects_single_observation():
    body = {"calibration_profile": "usb6",
            "observations": {"a": {"x": 0.0, "y": 0.0}}}
    r = client.post("/v1/triangulate", json=body)
    assert r.status_code == 422


def test_triangulate_without_projection_is_501():
    body = {"calibration_profile": "usb6",
            "observations": {"a": {"x": 0.0, "y": 0.0},
                             "b": {"x": 0.1, "y": 0.1}}}
    r = client.post("/v1/triangulate", json=body)
    assert r.status_code == 501
    assert r.json()["code"] == "calibration_not_configured"


def test_predict_endpoint_leads_forward():
    track = [[float(i) * 100.0, 0.0, 1000.0] for i in range(8)]
    r = client.post("/v1/predict", json={"track": track, "predict_ahead_ms": 400})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["predicted_position_mm"][0] > 700.0
    assert out["samples"] == 8
