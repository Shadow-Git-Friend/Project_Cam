# Current Status

Last updated: 2026-06-30

This page is the short trust snapshot for reviewers. It should be updated after
each GitHub Actions run or hardware validation pass.

## Public GitHub state

- Repository: `Shadow-Git-Friend/Project_Cam`
- Public `main` commit checked via GitHub API: `18b3baba5b2799b8777940a061101fd6f8d9a8a4`
- Latest public `main` CI run checked on 2026-06-30: failed at `Tests (hardware-free)`.
- Latest public `main` Docker smoke run checked on 2026-06-30: image build passed, container startup failed.
- Raw GitHub Actions logs require admin access, so the exact public stack traces were not available from this machine.

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
