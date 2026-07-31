# Multi-Person Arena, Face ID, And Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add stable multi-person 3D tracking, local Face ID labels, and a one-click Linux desktop control center while preserving the current single-person path.

**Architecture:** Keep cross-view association and identity decisions in hardware-free `src/project_cam/tracking` modules. Adapt the current live viewer at narrow candidate-selection, triangulation, identity, and rendering seams. Keep model setup, enrollment, and desktop installation in standalone scripts.

**Tech Stack:** Python 3.10+, NumPy, OpenCV YuNet/SFace, pytest, tkinter, Bash, freedesktop `.desktop` files.

---

### Task 1: Recover And Test Cross-View Association

**Files:**
- Create: `tests/test_multi_person_tracking.py`
- Create: `src/project_cam/tracking/multi_person.py`
- Create: `src/project_cam/tracking/__init__.py`

- [ ] Write synthetic multi-camera tests that import the absent module and assert stable IDs, one-to-one claims, multi-camera spawning, pruning, and no double-counted hit on a spawn frame.
- [ ] Run `./venv/bin/python -m pytest tests/test_multi_person_tracking.py -q` and verify collection fails because `project_cam.tracking` is absent.
- [ ] Port the association module, making `update()` increment `hits` only when `frame_idx` advances.
- [ ] Re-run the focused test and expect all cases to pass.

### Task 2: Test And Implement Local Identity Decisions

**Files:**
- Create: `tests/test_face_id.py`
- Create: `src/project_cam/tracking/face_id.py`
- Modify: `src/project_cam/tracking/__init__.py`
- Modify: `.gitignore`

- [ ] Write tests for embedding validation/normalization, best-name aggregation, safe `.npz` persistence, voter lock/switch behavior, model-path errors, and gated one-to-one face/track assignment.
- [ ] Run `./venv/bin/python -m pytest tests/test_face_id.py -q` and verify it fails because the module/API is absent.
- [ ] Implement the pure gallery/voter/assignment layer and the lazy YuNet/SFace runtime; ignore `models/face/gallery.npz`.
- [ ] Re-run both tracking test files and expect them to pass.

### Task 3: Integrate The Current Live Viewer

**Files:**
- Create: `tests/test_live_multi_person_face_id.py`
- Modify: `Parallel_working/scripts/live_4cam_arena_view_parallel.py`

- [ ] Write import-level tests for new CLI arguments and renderer support, plus helper tests that do not open cameras.
- [ ] Run the new test and verify the required arguments/helpers are missing.
- [ ] Add opt-in CLI flags, collect all per-camera candidates, associate tracks, route primary candidates through the legacy path, triangulate secondary joints, apply stale/display state, and prune state.
- [ ] Add periodic Face ID attribution after 3D joints exist, update track labels, and render colored secondary skeletons plus an access roster.
- [ ] Run viewer-focused tests and the existing viewer regression tests.

### Task 4: Model Setup And Enrollment

**Files:**
- Create: `tests/test_face_cli.py`
- Create: `Parallel_working/scripts/download_face_models.py`
- Create: `Parallel_working/scripts/face_enroll.py`

- [ ] Write CLI/import tests for checksum-aware downloads, camera-source parsing, safe name validation, gallery append/remove/list operations, and headless `--help`.
- [ ] Verify tests fail because both scripts are absent.
- [ ] Implement atomic model downloads from OpenCV Zoo and an enrollment UI that captures several high-quality embeddings before saving the local gallery.
- [ ] Run CLI tests and compile both scripts.

### Task 5: Desktop Control Center And Icon

**Files:**
- Create: `tests/test_desktop_control_center.py`
- Create: `desktop/arena_control_center.py`
- Create: `desktop/project-cam.svg`
- Create: `desktop/project-cam.desktop.in`
- Create: `desktop/install_desktop_app.sh`

- [ ] Write headless tests for repo/venv resolution, launch command construction, single-process interlock helpers, and generated `.desktop` paths.
- [ ] Verify tests fail because the desktop package is absent.
- [ ] Port and split command construction from the partial control center so tests do not instantiate Tk; ensure every live launch uses the resolved venv through the run scripts' environment.
- [ ] Add a freedesktop installer that renders/copies the icon, substitutes absolute paths, marks the desktop entry executable, and supports `--dry-run`.
- [ ] Run headless tests, AST checks, and installer `--dry-run`.

### Task 6: Final Verification And Installation

**Files:** all files above plus existing viewer regressions.

- [ ] Run focused tests for tracking, Face ID, viewer, scripts, and desktop.
- [ ] Run `./venv/bin/python -m pytest -q` and record the exact result.
- [ ] Run Ruff on curated package/tests and AST/`--help` smoke checks on legacy scripts.
- [ ] Review the complete diff for accidental safety/UDP changes and get an independent code review.
- [ ] With user-approved filesystem elevation, run `bash desktop/install_desktop_app.sh` to place the application icon on the actual desktop.

