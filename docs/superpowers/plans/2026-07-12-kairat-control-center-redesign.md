# Kairat-Style Arena Control Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish and verify a Kairat-inspired native desktop dashboard with CONTROL, ANALYTICS, and MATCHES views while preserving all existing launcher behavior.

**Architecture:** Keep Tk as the offline desktop shell. Isolate artifact parsing and readiness inspection in pure functions, render three views from those contracts, and label demo data explicitly. Do not modify tracking, UDP, or launcher safety code.

**Tech Stack:** Python 3.10, tkinter/ttk, JSON/JSONL, pytest, Xvfb, Pillow ImageGrab, SVG/freedesktop desktop entry.

---

### Task 1: Lock Data-Honesty Contracts

**Files:**
- Modify: `tests/test_desktop_control_center.py`
- Modify: `desktop/arena_control_center.py`

- [ ] Add a failing test proving a partial live analytics profile does not inherit missing demo KPI values.

```python
def test_partial_live_analytics_never_inherits_demo_metrics(tmp_path):
    module = load_app()
    target = tmp_path / "output/analytics/athlete_profile.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"athlete": "AISHA", "level": 7}))
    data = module.load_analytics(tmp_path)
    assert data["demo"] is False
    assert data["level"] == 7
    assert data["exactness_pct"] is None
    assert data["quickness_s"] is None
```

- [ ] Run the focused test and confirm it fails because `load_analytics()` currently merges `DEMO_ANALYTICS` into live data.

Run:

```bash
./venv/bin/python -m pytest tests/test_desktop_control_center.py::test_partial_live_analytics_never_inherits_demo_metrics -q
```

Expected: FAIL because missing metrics equal preview values.

- [ ] Return an explicit live analytics record with missing fields set to `None` and source metadata retained.

```python
data = {key: raw.get(key) for key in ANALYTICS_FIELDS}
data.update(demo=False, source=str(path), updated_at=_source_mtime(path))
```

- [ ] Add safe KPI formatting helpers and verify the test passes.

```python
def format_metric(value, pattern):
    return "—" if not isinstance(value, (int, float)) else pattern.format(value)
```

### Task 2: Complete Match Schema

**Files:**
- Modify: `tests/test_desktop_control_center.py`
- Modify: `desktop/arena_control_center.py`

- [ ] Add failing assertions that demo and parsed live match rows expose `spin`.

```python
assert all("spin" in row for row in module.load_matches(tmp_path)["rows"])
assert row["spin"] == "-2"
```

- [ ] Verify failure against the current six-field row schema.

Run:

```bash
./venv/bin/python -m pytest tests/test_desktop_control_center.py::test_load_matches_demo_fallback tests/test_desktop_control_center.py::test_load_matches_parses_shot_jsonl -q
```

Expected: FAIL with missing `spin`.

- [ ] Parse the exact supported fields `spin`, `spin_rps`, and `ball_spin`; render `—` when all are absent.

```python
spin = next(
    (record[key] for key in ("spin", "spin_rps", "ball_spin")
     if isinstance(record.get(key), (int, float))),
    None,
)
row["spin"] = "—" if spin is None else f"{spin:g}"
```

- [ ] Add the SPIN Treeview column and verify focused tests pass.

```python
columns = ("num", "gun", "target", "speed", "angle", "spin", "result", "time")
```

### Task 3: Add Honest Readiness State

**Files:**
- Modify: `tests/test_desktop_control_center.py`
- Modify: `desktop/arena_control_center.py`

- [ ] Write a failing pure-function test using a temporary repo with controlled config, model, gallery, and device inputs.

```python
def test_readiness_reports_only_real_local_state(tmp_path):
    module = load_app()
    state = module.load_readiness(tmp_path, device_paths=[])
    assert state["cameras"]["status"] == "NOT CONNECTED"
    assert state["face_models"]["ready"] is False
```

- [ ] Implement `load_readiness()` without opening cameras or importing model runtimes.

```python
def load_readiness(repo_root=REPO_ROOT, device_paths=None):
    root = Path(repo_root)
    devices = list(device_paths) if device_paths is not None else sorted(Path("/dev").glob("video*"))
    models = root / "models/face"
    calibration_ready = any((root / "garage_lab_combined/cal").glob("*.json"))
    model_ready = all((models / name).is_file() for name in FACE_MODEL_FILES)
    gallery = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "project-cam/face_gallery.npz"
    return {
        "cameras": {"ready": bool(devices), "status": f"{len(devices)} FOUND" if devices else "NOT CONNECTED"},
        "calibration": {"ready": calibration_ready, "status": "AVAILABLE" if calibration_ready else "NOT FOUND"},
        "face_models": {"ready": model_ready, "status": "READY" if model_ready else "NOT FOUND"},
        "gallery": {"ready": gallery.is_file(), "status": "AVAILABLE" if gallery.is_file() else "EMPTY"},
    }
```

- [ ] Render a compact readiness strip above the CONTROL columns.

```python
for label, item in readiness.items():
    self._readiness_card(strip, label.upper(), item["status"], item["ready"])
```

- [ ] Verify missing hardware displays `NOT CONNECTED`, never a fabricated ready state.

### Task 4: Refine Typography And Screen Layout

**Files:**
- Modify: `desktop/arena_control_center.py`
- Modify: `desktop/project-cam.svg`

- [ ] Preserve condensed sans-serif for product UI and monospace only for technical log/value surfaces.

Use `self.ui_font` for forms/table text and `self.mono_font` only for the mission log, command field, source paths, and timestamps.

- [ ] Keep black/yellow semantic palette and ensure STOP/miss remain red.
- [ ] Ensure ANALYTICS cards, trend, radar, and demo banner resize at 1280×820.
- [ ] Ensure MATCHES contains all target columns and readable result states.

Render command:

```bash
xvfb-run -a -s '-screen 0 1440x920x24' env SNAP_OUT=/tmp/project_cam_ui_snaps \
  ./venv/bin/python /tmp/project_cam_snap_views.py
```

### Task 5: Visual And Regression Verification

**Files:**
- Test: `tests/test_desktop_control_center.py`
- Test: `tests/test_face_cli.py`
- Test: `tests/test_live_multi_person_face_id.py`

- [ ] Run `./venv/bin/python -m py_compile desktop/arena_control_center.py`.
- [ ] Run `./venv/bin/python -m pytest tests/test_desktop_control_center.py -q`.
- [ ] Run the related Face ID and viewer contract tests.
- [ ] Render CONTROL, ANALYTICS, and MATCHES via Xvfb and inspect all PNGs.
- [ ] Run `desktop-file-validate` and reinstall the desktop entry with `desktop/install_desktop_app.sh`.
- [ ] Review `git diff --check` and the final scoped diff.

Expected final evidence:

```text
desktop tests: all passed
related Face ID/viewer tests: all passed
three PNG screenshots present and visually inspected
desktop-file-validate: exit 0
git diff --check: exit 0
```
