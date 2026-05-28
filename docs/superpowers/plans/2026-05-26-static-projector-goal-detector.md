# Static Projector Goal Detector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone `camNorth` detector that scores ball impacts against the static 3x3 south-wall projector grid.

**Architecture:** Put pure geometry and goal-state logic in `proxiball_3d-main/projector/static_grid_goal_logic.py` so it can be unit tested without a camera. Put the OpenCV/YOLO runtime in `proxiball_3d-main/projector/static_grid_goal_detector.py`, using the existing calibration files, `PersistentTrackerV3`, and `models/ball/yolo26m-672.engine` with `.pt` fallback.

**Tech Stack:** Python, OpenCV, NumPy, PyYAML, Ultralytics YOLO, pytest.

---

### Task 1: Testable Grid, Wall Mapping, And Goal Logic

**Files:**
- Create: `tests/test_static_grid_goal_detector.py`
- Create: `proxiball_3d-main/projector/static_grid_goal_logic.py`

- [ ] **Step 1: Write failing tests**

Add tests covering the 3x3 grid coordinates, ray intersection with the south-wall plane, sudden-deceleration goal triggering inside a rectangle, and cooldown suppression.

- [ ] **Step 2: Verify tests fail**

Run: `pytest tests/test_static_grid_goal_detector.py -q`
Expected: FAIL because `static_grid_goal_logic.py` does not exist yet.

- [ ] **Step 3: Implement pure logic**

Implement `WallRect`, `GoalEvent`, `StaticGridGoalLogic`, `target_grid_rectangles`, `find_rect_for_uv`, `intersect_ray_with_world_x`, and calibration helpers needed by the runtime.

- [ ] **Step 4: Verify tests pass**

Run: `pytest tests/test_static_grid_goal_detector.py -q`
Expected: PASS.

### Task 2: Standalone Live Detector

**Files:**
- Create: `proxiball_3d-main/projector/static_grid_goal_detector.py`

- [ ] **Step 1: Add live script**

Create a CLI that opens `camNorth`, runs the YOLO ball detector, maps the tracked ball center to the south wall, feeds the deceleration goal logic, draws the 9 grid rectangles and ball trail on the camera preview, logs goals, and exits with `q`.

- [ ] **Step 2: Verify import/CLI**

Run: `python -m py_compile proxiball_3d-main/projector/static_grid_goal_detector.py proxiball_3d-main/projector/static_grid_goal_logic.py`
Expected: exit code 0.

### Task 3: Final Verification

**Files:**
- Test: `tests/test_static_grid_goal_detector.py`
- Compile: `proxiball_3d-main/projector/static_grid_goal_detector.py`

- [ ] **Step 1: Run focused test suite**

Run: `pytest tests/test_static_grid_goal_detector.py -q`
Expected: PASS.

- [ ] **Step 2: Compile runtime files**

Run: `python -m py_compile proxiball_3d-main/projector/static_grid_goal_detector.py proxiball_3d-main/projector/static_grid_goal_logic.py`
Expected: exit code 0.
