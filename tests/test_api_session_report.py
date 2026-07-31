"""Session report API contract tests."""

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402
from services.api.app.main import app  # noqa: E402

client = TestClient(app)


def test_session_report_generates_assessment_from_fixture():
    fixture = Path("tests/fixtures/motion_capture_data_garage.json")

    r = client.post(
        "/v1/session/report",
        json={"input_path": str(fixture), "exercise": "squat"},
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema_version"] == "project_cam.assessment.v1"
    assert body["exercise"] == "squat"
    assert body["session"]["frame_count"] > 0
    assert "quality" in body
    assert "metrics" in body


def test_session_report_missing_input_is_404():
    r = client.post(
        "/v1/session/report",
        json={"input_path": "tests/fixtures/no_such_motion.json", "exercise": "squat"},
    )

    assert r.status_code == 404
    assert r.json()["code"] == "input_not_found"
