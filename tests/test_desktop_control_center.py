"""Headless contracts for the Linux desktop control center."""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path("desktop/arena_control_center.py")
INSTALLER = Path("desktop/install_desktop_app.sh")
TEMPLATE = Path("desktop/project-cam.desktop.in")
ICON = Path("desktop/project-cam.svg")


def load_app():
    spec = importlib.util.spec_from_file_location("arena_control_center_contract", APP)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_resolve_venv_python_prefers_checkout_venv(tmp_path):
    module = load_app()
    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.touch()
    assert module.resolve_venv_python(tmp_path, fallback="fallback") == str(python)


def test_live_command_is_argv_safe_and_includes_selected_features(tmp_path):
    module = load_app()
    script = "Parallel_working/run_live_usb6_mirrored_skeleton.sh"
    command = module.build_live_command(
        repo_root=tmp_path,
        script=script,
        multi_people=4,
        face_id=True,
        auto_orbit=True,
        limb_heat=False,
        primary_person="Айша & Bob",
    )
    assert command == [
        "bash",
        str(tmp_path / script),
        "--multi-person",
        "4",
        "--face-id",
        "--primary-person",
        "Айша & Bob",
        "--auto-orbit",
    ]


def test_face_commands_keep_name_as_one_argument(tmp_path):
    module = load_app()
    enroll = module.build_face_enroll_command(
        repo_root=tmp_path,
        python="/venv/python",
        name="Alice; touch /tmp/nope",
        camera="0",
    )
    assert enroll[-1] == "Alice; touch /tmp/nope"
    assert enroll[:2] == ["/venv/python", str(tmp_path / "Parallel_working/scripts/face_enroll.py")]
    setup = module.build_model_setup_command(tmp_path, "/venv/python")
    assert setup[:2] == [
        "/venv/python",
        str(tmp_path / "Parallel_working/scripts/download_face_models.py"),
    ]


def test_control_center_check_mode_is_headless():
    result = subprocess.run(
        [sys.executable, str(APP), "--check"], text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert "Project Cam control center" in result.stdout
    assert "DISPLAY" in result.stdout


def test_desktop_installer_dry_run_is_side_effect_free(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), XDG_DATA_HOME=str(tmp_path / "xdg"))
    result = subprocess.run(
        ["bash", str(INSTALLER), "--dry-run"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "[Desktop Entry]" in result.stdout
    assert str(Path.cwd()) in result.stdout
    assert "project-cam.svg" in result.stdout
    assert not (tmp_path / "xdg").exists()
    assert not (home / "Desktop").exists()


def test_desktop_template_and_vector_icon_have_required_identity():
    template = TEMPLATE.read_text()
    assert "StartupWMClass=project-cam" in template
    assert "Terminal=false" in template
    assert "@REPO_ROOT@" in template
    icon = ICON.read_text()
    assert "<svg" in icon
    assert "PROJECT CAM" in icon


def test_load_analytics_demo_fallback_is_complete(tmp_path):
    module = load_app()
    data = module.load_analytics(tmp_path)
    assert data["demo"] is True
    for key in ("level", "exactness_pct", "quickness_s", "progress_pct", "rating"):
        assert key in data
    assert len(data["trend"]) >= 2
    assert len(data["radar"]) >= 3


def test_load_analytics_reads_live_profile(tmp_path):
    module = load_app()
    profile = {
        "athlete": "HANUSH",
        "level": 7,
        "exactness_pct": 91.5,
        "trend": [{"label": "01.08", "value": 60}, {"label": "02.08", "value": 72}],
        "radar": {"level": 0.9, "exactness": 0.91, "quickness": 0.5},
    }
    target = tmp_path / "output" / "analytics" / "athlete_profile.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(profile))
    data = module.load_analytics(tmp_path)
    assert data["demo"] is False
    assert data["level"] == 7
    assert data["exactness_pct"] == 91.5
    assert [p["label"] for p in data["trend"]] == ["01.08", "02.08"]
    assert set(data["radar"]) == {"LEVEL", "EXACTNESS", "QUICKNESS"}


def test_partial_live_analytics_never_inherits_demo_metrics(tmp_path):
    module = load_app()
    target = tmp_path / "output" / "analytics" / "athlete_profile.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"athlete": "AISHA", "level": 7}))

    data = module.load_analytics(tmp_path)

    assert data["demo"] is False
    assert data["athlete"] == "AISHA"
    assert data["level"] == 7
    assert data["exactness_pct"] is None
    assert data["quickness_s"] is None
    assert data["trend"] == []
    assert data["radar"] == {}


def test_malformed_live_analytics_types_are_safe_and_explicitly_unavailable(tmp_path):
    module = load_app()
    target = tmp_path / "output" / "analytics" / "athlete_profile.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({
        "athlete": ["not", "a", "name"],
        "exactness_pct": "91.5",
        "quickness_s": float("nan"),
        "trend": None,
        "radar": [],
    }))

    data = module.load_analytics(tmp_path)

    assert data["demo"] is False
    assert data["athlete"] == "UNNAMED ATHLETE"
    assert data["exactness_pct"] is None
    assert data["quickness_s"] is None
    assert data["trend"] == []
    assert data["radar"] == {}
    assert module.format_metric(data["exactness_pct"], "{:.0f} %") == "—"


def test_load_matches_demo_fallback(tmp_path):
    module = load_app()
    data = module.load_matches(tmp_path)
    assert data["demo"] is True
    assert data["rows"]
    for row in data["rows"]:
        for key in ("gun", "target", "speed", "angle", "spin", "result", "time"):
            assert key in row


def test_load_matches_parses_shot_jsonl(tmp_path):
    module = load_app()
    log_dir = tmp_path / "garage_lab_combined" / "output" / "blm_logs"
    log_dir.mkdir(parents=True)
    lines = [
        json.dumps({"event": "aim", "joint": "nose"}),
        json.dumps({"event": "shoot", "joint": "right_shoulder", "rpm": 800,
                    "pitch": 15, "spin": -2, "hit": True, "t": 1_780_000_000}),
        "not json at all",
    ]
    (log_dir / "s4_live.jsonl").write_text("\n".join(lines))
    data = module.load_matches(tmp_path)
    assert data["demo"] is False
    assert len(data["rows"]) == 1
    row = data["rows"][0]
    assert row["target"] == "RIGHT_SHOULDER"
    assert row["speed"] == "800 RPM"
    assert row["angle"] == "15°"
    assert row["spin"] == "-2"
    assert row["result"] == "✓"


def test_load_matches_parses_real_live_aim_nested_schema(tmp_path):
    module = load_app()
    log_dir = tmp_path / "garage_lab_combined" / "output" / "blm_logs"
    log_dir.mkdir(parents=True)
    record = {
        "action": "shoot",
        "joint": "right_knee",
        "wheel_rpm": 825,
        "angles_clamped": {"pitch_deg": 12.4, "yaw_deg": -3.0},
        "visual_check": "n",
        "timestamp": "aim-time",
        "shoot_timestamp": "shot-time",
    }
    (log_dir / "live_aim.jsonl").write_text(json.dumps(record) + "\n")

    data = module.load_matches(tmp_path)

    assert data["demo"] is False
    assert data["rows"] == [{
        "gun": "BLM-1",
        "target": "RIGHT_KNEE",
        "speed": "825 RPM",
        "angle": "12°",
        "spin": "—",
        "result": "✗",
        "time": "shot-time",
    }]


def test_load_matches_reads_only_bounded_tail_of_large_logs(tmp_path):
    module = load_app()
    log_dir = tmp_path / "garage_lab_combined" / "output" / "blm_logs"
    log_dir.mkdir(parents=True)
    path = log_dir / "large.jsonl"
    old_shot = json.dumps({"action": "shoot", "joint": "nose"}) + "\n"
    path.write_text(old_shot + (json.dumps({"action": "aim"}) + "\n") * 200)

    data = module.load_matches(tmp_path, max_bytes=256)
    assert data["demo"] is True

    with path.open("a") as stream:
        stream.write(json.dumps({"action": "shoot", "joint": "left_wrist"}) + "\n")
    data = module.load_matches(tmp_path, max_bytes=256)
    assert data["demo"] is False
    assert data["rows"][-1]["target"] == "LEFT_WRIST"


def test_readiness_reports_only_real_local_state(tmp_path):
    module = load_app()
    gallery = tmp_path / "private" / "face_gallery.npz"

    missing = module.load_readiness(
        tmp_path, device_paths=[], gallery_path=gallery
    )
    assert missing["cameras"] == {"ready": False, "status": "NOT CONNECTED"}
    assert missing["calibration"]["ready"] is False
    assert missing["face_models"]["ready"] is False
    assert missing["gallery"] == {"ready": False, "status": "EMPTY"}

    device = tmp_path / "dev" / "camera0"
    device.parent.mkdir()
    device.touch()
    for relative in module.READINESS_CALIBRATION_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    models = tmp_path / "models" / "face"
    models.mkdir(parents=True)
    for filename in module.FACE_MODEL_FILES:
        (models / filename).touch()
    gallery.parent.mkdir()
    gallery.touch()

    ready = module.load_readiness(
        tmp_path, device_paths=[device], gallery_path=gallery
    )
    assert ready["cameras"] == {"ready": True, "status": "1 DEVICE"}
    assert ready["calibration"] == {"ready": True, "status": "AVAILABLE"}
    assert ready["face_models"] == {"ready": True, "status": "READY"}
    assert ready["gallery"] == {"ready": True, "status": "AVAILABLE"}


def test_heavy_views_are_built_lazily():
    module = load_app()
    source = inspect.getsource(module.ArenaControlCenter._build)
    assert "builder(frame)" not in source
    assert hasattr(module.ArenaControlCenter, "_ensure_view")


def test_check_mode_reports_data_sources():
    result = subprocess.run(
        [sys.executable, str(APP), "--check"], text=True, capture_output=True
    )
    assert result.returncode == 0, result.stderr
    assert "analytics=" in result.stdout
    assert "matches=" in result.stdout
