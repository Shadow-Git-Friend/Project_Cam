"""API system endpoints over the FastAPI TestClient.

Skips when fastapi/httpx (the API extra) are not installed. None of these touch
cameras or a GPU.
"""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from services.api.app.main import app  # noqa: E402

client = TestClient(app)


def test_health_ok_without_hardware():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "project-cam-api"
    assert "version" in body


def test_system_info_reports_aim_only():
    r = client.get("/v1/system/info")
    assert r.status_code == 200
    body = r.json()
    assert body["shooting_enabled"] is False
    assert body["units"] == "mm"
    assert "fallback_profile" in body


def test_cameras_returns_configured_count():
    r = client.get("/v1/cameras", params={"profile": "usb6"})
    assert r.status_code == 200
    body = r.json()
    assert body["camera_count"] == 6
    assert len(body["cameras"]) == 6
    assert body["validated"] is False


def test_cameras_four_cam_profile():
    r = client.get("/v1/cameras", params={"profile": "4cam"})
    assert r.status_code == 200
    assert r.json()["camera_count"] == 4


def test_cameras_unknown_profile_404():
    r = client.get("/v1/cameras", params={"profile": "nope"})
    assert r.status_code == 404


def test_metrics_endpoint_exposes_names():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "project_cam_camera_count" in r.text


def test_detect_endpoints_are_501_not_500():
    assert client.post("/v1/detect/ball").status_code == 501
    assert client.post("/v1/detect/pose").status_code == 501


def test_api_has_no_shoot_route():
    paths = app.openapi()["paths"]
    assert not any("shoot" in p.lower() for p in paths)
    assert not any("fire" in p.lower() for p in paths)
