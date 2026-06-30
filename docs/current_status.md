# Current Status

Last updated: 2026-06-30

This page is the short trust snapshot for reviewers. It should be updated after
each GitHub Actions run or hardware validation pass.

## Public GitHub state

- Repository: `Shadow-Git-Friend/Project_Cam`
- Public `main` commit checked via GitHub API: `18b3baba5b2799b8777940a061101fd6f8d9a8a4`
- Public `main` on 2026-06-30 (before this branch lands): `ci` failed at
  `Tests (hardware-free)`; `docker-smoke` built the image but the container
  failed to start. **Both are now diagnosed and fixed on branch
  `projector-goal-detection-fixes-20260528`.**
- Branch `projector-goal-detection-fixes-20260528` @ `8fd49734`: GitHub Actions
  `ci` -> **success** and `docker-smoke` -> **success** (verified via the Actions
  API on 2026-06-30). Public `main` goes green once this branch merges.

### Root causes fixed on the branch (2026-06-30)
1. `/v1/session/report` returned `501`: the route imported a non-existent
   `summarize_session` from `offline_assess`. Added the helper (`2137da0f`).
2. `ci` `Tests` step + `3D accuracy regression gate` failed on a fresh checkout:
   `.gitignore` `*.json` silently ignored the CI test fixtures, so a clean clone
   had no `tests/fixtures/*.json`. Committed the fixtures + `docs/openapi.json`
   (a previously dead README link) + the Grafana dashboard via `.gitignore`
   negations (`cb707c7a`).
3. `docker-smoke` container crash at boot: the API import chain reaches
   `triangulation` -> `import cv2`, but `requirements-api.txt` never installed
   OpenCV. Added `opencv-python-headless` (capped `<4.13` for the `numpy<2` pin)
   (`a56e7e0f`).
4. `ci` `Tests` step exit code `2` (collection error, not a test failure): CI
   runs the bare `pytest` console script, which does not put the CWD on
   `sys.path`, so the four API tests doing `from services.api.app.main import app`
   failed collection (`services/` lives at the repo root, outside `src/`). Set
   `pythonpath = ["src", "."]` (`8fd49734`).
- Each fix was reproduced in a clean Python 3.11 venv mirroring the CI install
  (pytest 9.1.1, numpy 2.4.6, cv2 4.13) and against a fresh `git clone` of the
  pushed commit, then confirmed green by the GitHub Actions runners themselves.

## Local branch state

- Local branch: `projector-goal-detection-fixes-20260528`
- Local HEAD before this working-tree pass: `3b7d63b6`
- The exact CI test subset passed locally in both the repo `venv` (Python 3.10.12) and a clean temporary Python 3.11.15 environment: `123 passed`.
- Full local test suite in the repo `venv`: `276 passed`.
- Production-surface Ruff check: all checks passed.
- Hardware-free 3D accuracy gate: `ball_static` passed.
- `/v1/session/report` is covered by a route-level regression test in this working tree.
- Docker is not installed on this machine, so Docker smoke must be verified on GitHub Actions or another Docker host.

## Trust caveats

- The 4-camera `arena_fixed` rig remains the validated commercial baseline.
- The 6-camera rig remains a prototype direction until USB topology and static 3D GT gates are closed in `configs/calibration/usb6_manifest.yaml`.
- The API is aim-only. It must not expose a `shoot` or `fire` route.
- Public-facing materials should not use the historical `269 passed` local test claim as a current trust signal until GitHub Actions is green.
