"""Headless contracts for the Linux desktop control center."""

from __future__ import annotations

import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


class ValueBox:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class WidgetBox:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


class RootScheduler:
    def __init__(self):
        self.jobs = []
        self.cancelled = []
        self.destroyed = False

    def after(self, delay, callback, *args):
        job = {
            "id": len(self.jobs) + 1,
            "delay": delay,
            "callback": callback,
            "args": args,
        }
        self.jobs.append(job)
        return job["id"]

    def after_cancel(self, job_id):
        self.cancelled.append(job_id)

    def run(self, job):
        job["callback"](*job["args"])

    def destroy(self):
        self.destroyed = True


class ProcessBox:
    def __init__(self, pid, *, poll_result=None, wait_result=0, stdout=()):
        self.pid = pid
        self.poll_result = poll_result
        self.wait_result = wait_result
        self.stdout = stdout

    def poll(self):
        return self.poll_result

    def wait(self):
        return self.wait_result


def make_process_center(module, process, *, generation=1):
    center = module.ArenaControlCenter.__new__(module.ArenaControlCenter)
    center.root = RootScheduler()
    center.proc = process
    center.proc_pgid = process.pid if process is not None else None
    center.proc_exit_code = None
    center.proc_title = "VIEWER"
    center.proc_generation = generation
    center.shutdown_stage = 0
    center.shutdown_timer = None
    center.messages = module.queue.Queue()
    center.closing = False
    center.status = ValueBox("RUNNING")
    center.status_label = WidgetBox()
    center.stop_button = WidgetBox()
    center.launch_buttons = []
    center.logs = []
    center._log = lambda message, tag=None: center.logs.append((message, tag))
    center._render_readiness = lambda: None
    return center


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


def test_parse_multi_people_ignores_raw_value_when_disabled():
    module = load_app()

    assert module.parse_multi_people("not a number", enabled=False) == 1


@pytest.mark.parametrize("raw", ["", "four", "2.5"])
def test_parse_multi_people_rejects_empty_or_non_integer_values(raw):
    module = load_app()

    with pytest.raises(ValueError):
        module.parse_multi_people(raw, enabled=True)


@pytest.mark.parametrize("raw", ["1", "7", "-2"])
def test_parse_multi_people_rejects_values_outside_two_through_six(raw):
    module = load_app()

    with pytest.raises(ValueError):
        module.parse_multi_people(raw, enabled=True)


@pytest.mark.parametrize(("raw", "expected"), [("2", 2), (" 4 ", 4), ("6", 6)])
def test_parse_multi_people_accepts_two_through_six(raw, expected):
    module = load_app()

    assert module.parse_multi_people(raw, enabled=True) == expected


def test_multi_people_control_constructs_a_string_variable(monkeypatch):
    module = load_app()
    variables = []

    class Variable(ValueBox):
        def __init__(self, kind, value):
            super().__init__(value)
            self.kind = kind

    class Root(RootScheduler):
        def title(self, _value):
            pass

        def geometry(self, _value):
            pass

        def minsize(self, _width, _height):
            pass

        def configure(self, **_kwargs):
            pass

        def protocol(self, _name, _callback):
            pass

    def variable_factory(kind):
        def create(_root=None, value=None):
            variable = Variable(kind, value)
            variables.append(variable)
            return variable

        return create

    monkeypatch.setattr(module.tk, "BooleanVar", variable_factory("boolean"))
    monkeypatch.setattr(module.tk, "IntVar", variable_factory("integer"))
    monkeypatch.setattr(module.tk, "StringVar", variable_factory("string"))
    monkeypatch.setattr(module.ArenaControlCenter, "_family", lambda *_args: "Sans")
    monkeypatch.setattr(module.ArenaControlCenter, "_style_ttk", lambda _self: None)
    monkeypatch.setattr(module.ArenaControlCenter, "_build", lambda _self: None)
    monkeypatch.setattr(module.ArenaControlCenter, "_log", lambda *_args: None)

    center = module.ArenaControlCenter(Root())

    assert center.multi_people.kind == "string"
    assert center.multi_people.get() == "4"
    assert center.multi_people in variables


def test_launch_live_logs_invalid_people_count_without_spawning():
    module = load_app()
    center = module.ArenaControlCenter.__new__(module.ArenaControlCenter)
    center.multi_enabled = ValueBox(True)
    center.multi_people = ValueBox("")
    center.face_id = ValueBox(False)
    center.auto_orbit = ValueBox(False)
    center.limb_heat = ValueBox(False)
    center.primary_person = ValueBox("")
    logs = []
    spawns = []
    center._log = lambda message, tag=None: logs.append((message, tag))
    center._spawn = lambda command, title: spawns.append((command, title))

    center.launch_live(module.LAUNCHES[0])

    assert spawns == []
    assert logs
    assert logs[-1][1] == "err"
    assert "people" in logs[-1][0].lower()


def test_spawn_decodes_child_output_as_utf8_with_replacement(monkeypatch):
    module = load_app()
    center = module.ArenaControlCenter.__new__(module.ArenaControlCenter)
    center.proc = None
    center.command = ValueBox("")
    center._set_status_running = lambda _title: None
    center._log = lambda _message, _tag=None: None
    center._set_interlock = lambda _running: None
    center._show_view = lambda _name: None
    options = {}

    class Process:
        pid = 100
        stdout = []

        def poll(self):
            return None

    class Thread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            pass

    def popen(_command, **kwargs):
        options.update(kwargs)
        return Process()

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(module.threading, "Thread", Thread)

    center._spawn(["viewer", "--live"], "VIEWER")

    assert options["encoding"] == "utf-8"
    assert options["errors"] == "replace"


def test_spawn_assigns_a_new_generation_to_the_reader(monkeypatch):
    module = load_app()
    center = module.ArenaControlCenter.__new__(module.ArenaControlCenter)
    center.proc = None
    center.proc_generation = 8
    center.shutdown_stage = 3
    center.shutdown_timer = None
    center.command = ValueBox("")
    center._set_status_running = lambda _title: None
    center._log = lambda _message, _tag=None: None
    center._set_interlock = lambda _running: None
    center._show_view = lambda _name: None
    process = ProcessBox(101)
    thread_args = []

    class Thread:
        def __init__(self, *, target, args, daemon):
            thread_args.append((target, args, daemon))

        def start(self):
            pass

    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: process)
    monkeypatch.setattr(module.threading, "Thread", Thread)

    center._spawn(["viewer"], "VIEWER")

    assert center.proc_generation == 9
    assert center.proc_pgid == process.pid
    assert thread_args == [(center._read_child, (process, 9), True)]


def test_stop_deadlines_escalate_sigint_to_sigterm_to_sigkill(monkeypatch):
    module = load_app()
    process = ProcessBox(201)
    center = make_process_center(module, process)
    signals = []
    center.proc_pgid = 1201

    def killpg(process_group, sig):
        if sig != 0:
            signals.append((process_group, sig))

    monkeypatch.setattr(module.os, "killpg", killpg)

    center.stop()
    interrupt_timer = center.root.jobs[-1]
    assert interrupt_timer["delay"] == 10_000
    center.root.run(interrupt_timer)
    terminate_timer = center.root.jobs[-1]
    assert terminate_timer["delay"] == 3_000
    center.root.run(terminate_timer)

    assert signals == [
        (1201, module.signal.SIGINT),
        (1201, module.signal.SIGTERM),
        (1201, module.signal.SIGKILL),
    ]


def test_repeated_stop_escalates_immediately_and_old_timer_is_harmless(monkeypatch):
    module = load_app()
    process = ProcessBox(202)
    center = make_process_center(module, process)
    signals = []
    monkeypatch.setattr(
        module.os, "killpg", lambda _group, sig: signals.append(sig) if sig != 0 else None
    )

    center.stop()
    interrupt_timer = center.root.jobs[-1]
    center.stop()
    center.root.run(interrupt_timer)
    center.stop()

    assert signals == [
        module.signal.SIGINT,
        module.signal.SIGTERM,
        module.signal.SIGKILL,
    ]


def test_shutdown_timer_from_old_generation_cannot_signal_new_process(monkeypatch):
    module = load_app()
    old_process = ProcessBox(203)
    center = make_process_center(module, old_process, generation=4)
    signals = []
    monkeypatch.setattr(
        module.os,
        "killpg",
        lambda process_group, sig: signals.append((process_group, sig))
        if sig != 0
        else None,
    )

    center.stop()
    old_timer = center.root.jobs[-1]
    center.proc = ProcessBox(204)
    center.proc_generation = 5
    center.shutdown_stage = 0
    center.shutdown_timer = None
    center.root.run(old_timer)

    assert signals == [(203, module.signal.SIGINT)]


def test_exit_message_from_old_generation_cannot_clear_current_process():
    module = load_app()
    process = ProcessBox(205)
    center = make_process_center(module, process, generation=6)

    center._read_child(process, 5)
    center._pump()

    assert center.proc is process
    assert center.proc_generation == 6
    assert center.status.get() == "RUNNING"


def test_close_waits_for_live_process_exit_and_keeps_pumping(monkeypatch):
    module = load_app()
    process = ProcessBox(206)
    center = make_process_center(module, process, generation=7)
    signals = []
    group_alive = [True]

    def killpg(_group, sig):
        if sig == 0:
            if group_alive[0]:
                return
            raise ProcessLookupError
        signals.append(sig)

    monkeypatch.setattr(module.os, "killpg", killpg)

    center.close()

    assert center.closing is True
    assert center.root.destroyed is False
    assert signals == [module.signal.SIGINT]

    center._pump()
    assert any(job["delay"] == 60 for job in center.root.jobs)
    assert center.root.destroyed is False

    group_alive[0] = False
    center._read_child(process, 7)
    center._pump()

    assert center.proc is None
    assert center.root.destroyed is True


@pytest.mark.parametrize("process", [None, ProcessBox(207, poll_result=0)])
def test_close_destroys_immediately_without_a_live_process(process, monkeypatch):
    module = load_app()
    center = make_process_center(module, process)

    def missing_group(_group, sig):
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(module.os, "killpg", missing_group)

    center.close()

    assert center.root.destroyed is True


def test_dead_leader_keeps_live_group_managed_until_group_disappears(monkeypatch):
    module = load_app()
    process = ProcessBox(208, poll_result=0)
    center = make_process_center(module, process, generation=8)
    probe_state = ["permission"]
    signals = []

    def killpg(process_group, sig):
        if sig == 0:
            if probe_state[0] == "permission":
                raise PermissionError
            raise ProcessLookupError
        signals.append((process_group, sig))

    monkeypatch.setattr(module.os, "killpg", killpg)
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("live process group was replaced"),
    )

    center._read_child(process, 8)
    center._pump()

    assert center.proc is process
    assert center.proc_pgid == 208
    assert center.status.get() == "RUNNING"
    center._spawn(["replacement"], "REPLACEMENT")
    assert center.proc is process

    center.stop()
    interrupt_timer = center.root.jobs[-1]
    center.root.run(interrupt_timer)
    center.close()

    assert signals == [
        (208, module.signal.SIGINT),
        (208, module.signal.SIGTERM),
        (208, module.signal.SIGKILL),
    ]
    assert center.root.destroyed is False

    probe_state[0] = "missing"
    center._pump()

    assert center.proc is None
    assert center.proc_pgid is None
    assert center.root.destroyed is True


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
