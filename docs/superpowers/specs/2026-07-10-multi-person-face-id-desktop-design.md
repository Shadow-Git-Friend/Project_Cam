# Multi-Person Arena, Local Face ID, And Desktop App — Design Spec

**Date:** 2026-07-10
**Status:** Approved by the user's request to continue the existing implementation
**Scope:** live pose viewer, local identity gallery, and Linux desktop launcher

## Goal

Extend Project Cam from one selected athlete to several stable 3D people, label
known entrants from a local face gallery, and expose the system through one
desktop application icon. The existing single-person geometry and safety path
must remain the default and must not change when the new flags are disabled.

## Chosen Approach

Port the partial feature from the stale Claude worktree into the current branch
as small, testable modules. Do not copy the stale live viewer wholesale: the
current viewer is 25 commits newer and contains camera, batching, left/right,
avatar, and latency fixes that must be preserved.

Alternatives rejected:

- Merging the stale viewer directly risks losing 786 newer lines and 64 fixes.
- Creating a second live viewer would duplicate camera ownership, geometry,
  safety-sensitive UDP behavior, and future maintenance.

## Architecture

### Cross-view association

`src/project_cam/tracking/multi_person.py` owns only person association. A track
stores a stable integer ID and the last confirmed 3D pelvis. The live viewer
provides calibrated projection and two-view triangulation callbacks. Existing
tracks use maximum-cardinality/minimum-cost per-camera pelvis matching; new
tracks require coherent agreement from at least two cameras. IDs are never
reused during a session.

The selected primary track continues through the existing EMA, Kalman, coach,
BLM, and UDP pipeline. Secondary tracks are triangulated into independent state
and rendered only. `--multi-person 1` is the unchanged legacy path.

### Local Face ID

`src/project_cam/tracking/face_id.py` contains:

- a pickle-free NumPy gallery of normalized SFace embeddings;
- a decaying per-track name voter so one blurred frame cannot rename a person;
- one-to-one face-to-track assignment by projected 3D head position;
- a lazy OpenCV YuNet/SFace runtime.

Recognition is local; there is no Facebook lookup or cloud upload. The gallery
is biometric data and remains git-ignored. Face ID provides a convenience label,
not iPhone-grade liveness or access-control security.

Face inference runs periodically on one camera at a time. The nearest projected
head within a pixel gate receives the gallery vote. A requested
`--primary-person NAME` may become primary only after its identity voter locks.

### Desktop application

`desktop/arena_control_center.py` launches one existing run script at a time,
shows its log, appends multi-person/Face-ID display flags, and sends SIGINT to
the child process group for clean recording shutdown. The repository-owned SVG
icon is referenced directly by `desktop/install_desktop_app.sh`, which installs
a `.desktop` entry in the user's application menu and on the desktop.

Face enrollment and model download are separate CLI scripts so the GUI stays
fast and import-safe. Launch commands always resolve the main checkout's venv,
including when invoked from a worktree.

## Data Flow

```
camera frames -> all 2D pose candidates -> cross-view association
              -> per-track joint triangulation
              -> primary: existing EMA/KF/coach/UDP/BLM path
              -> secondary: independent display state -> tinted skeletons

one round-robin frame -> YuNet -> SFace embedding -> local gallery match
                     -> nearest projected track head -> temporal name voter
                     -> name badge / optional primary selection
```

## Error Handling And Safety

- Missing Face ID models disables only Face ID and prints the exact downloader.
- Empty galleries label entrants as unknown without stopping pose tracking.
- A face is assigned to at most one track and a track receives at most one face
  per inference tick.
- Track pruning clears secondary display and identity voter state.
- Multi-person mode does not add launcher actuation, alter the UDP schema, or
  bypass any existing launcher safety gate.
- The desktop STOP action never sends SIGKILL, allowing MP4 finalization.

## Verification

- Pure NumPy synthetic tests for births, motion, one-to-one claims, occlusion,
  pruning, ID non-reuse, and same-frame hit counting.
- Pure tests for gallery normalization/persistence/matching, name voting, and
  one-to-one face/track assignment.
- Import/CLI tests for viewer flags, downloader, enrollment, and desktop command
  construction without requiring cameras, a display, or ONNX models.
- Focused pytest, AST/compile checks, viewer `--help`, and full regression suite.

## Out Of Scope

- Biometric liveness detection or security certification.
- Cloud/Facebook identity lookup.
- Changing launcher firing behavior or safety gates.
- Replacing the existing pose detector with a re-identification neural network.
