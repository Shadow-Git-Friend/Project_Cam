"""Headless contracts for the Linux desktop control center."""

from __future__ import annotations

import importlib.util
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
