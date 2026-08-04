# What is not in this tree, and where it went

**Read this before hunting for a file or a recording.** If something you expect
is missing, it is almost certainly listed below with the reason, and it is still
on disk in `~/Desktop/Project_Cam_ARCHIVE_20260804/`.

Written 2026-08-04, when the live system was moved out of a 51 GB tree that held
about 6 MB of source. The new tree is **1.7 GB** plus the venv.

## Why the split exists at all

Disk was never the problem. The problem was that a retired artifact sat beside a
current one and looked equally current: on 2026-08-04 a pose-backend A/B was run
against the **April 4-camera recordings** and their calibration before anyone
noticed the rig had changed. `.claude/worktrees/` additionally held 1.6 GB of
stale copies of the same source files.

So the rule this tree is built on: **if a recording, calibration or model is not
what the product currently uses, it does not live here.** Not renamed, not put in
a subfolder — moved out.

## Left behind deliberately

| What | Size | Why it is not here |
|---|---|---|
| 4-camera calibration (`garage_lab_combined/cal/intrinsics/`, `arena_fixed/`) | ~3 MB | The product runs the 6-USB mirrored rig. These are `camNorth/East/South/West` — a geometry the system no longer has. **This is the artifact that caused the incident.** |
| 4-camera recordings `walk_01`, `jog_01`, `jump_01` + `bounce_0*` (in `artifacts_local/`) | 2.4 GB | Same reason. They remain the only *pose ablation baseline* ever recorded, so if you need a historical comparison, take it from the archive **and label the number as 4-camera** |
| `garage_lab_combined/gt_eval/` | 3.6 GB | Ground-truth evaluation captures from the 4-camera era |
| `Remounted_West_East/` | 351 MB | The 2026-05 lateral-remount calibration bundle. Healthy, but superseded; `test_static_grid_goal_detector.py` skips one test without it |
| `archive/` | 6.3 GB | Already an archive before this move |
| `artifacts_local/` | 11 GB | Output dumps, old frame captures, ablation JSONs |
| `.claude/worktrees/` | 1.6 GB | Stale working-tree copies from interrupted sessions. The single worst source of "which copy am I reading?" |
| `docs/thesis_archive/` | 81 MB | Thesis PDFs; no code reads them |
| `docs/archive/` | 224 KB | Superseded notes (`plan.md`, `suggestions.md`, `new_complete.md`). Quoted by older CLAUDE.md log entries — read them there when a log entry refers to them |
| `kairat_pitch/` | 23 MB | Pitch deck assets |
| `proxiball_3d-main/` minus `projector/` | ~11 MB | Only `projector/` is referenced (the pending goal-game Phase 1 fix and its test) |
| `voice_commands/` | 48 KB | Old prototype, superseded by the Vosk UDP bridge |
| CVPR paper notes at the repo root (12 `.md` files) | ~1 MB | Reading notes on body-mesh papers. Research context, not the system |
| One-off scripts (`restructure_*.py`, `improve_defense_pptx*.py`) | — | Single-use presentation builders with hardcoded absolute paths to the old tree |
| `src-tauri/target/`, `dist/` | 5.9 GB | Build output. `rebuild.sh` regenerates it |
| `.git` (4 GB of objects) | 4 GB | History starts fresh here by choice; the old repository is intact in the archive, where `git log` works normally |

## Kept, but do not confuse them

* **`desktop/`** is the **retired** Tkinter control center. `project-cam-desktop/`
  is the product. `desktop/` travelled only because it still carries 39 tests and
  weighs 76 KB — deleting tests to make a migration look tidy is the wrong trade.
  Do not add features to it.
* **`garage_lab_combined/test_clips/altai_dataset_20260701_125836/`** is the only
  6-camera footage that exists: three 60 s synced clips, all six roles,
  1280×720, matching the `intrinsics_usb6_1280x720` calibration. Use these for
  any pose/ball comparison. The `.zip` duplicate was not copied.
* **`models/`** carries pose (YOLO11m-pose + RTMO s/m), ball and face weights.
  Four of them are `blocked` in `configs/models.yaml` — the registry, not the
  directory, is the authority on what may be used commercially.

## Environment

The venv **lives here now** (`ProjectCam/venv`, 17 GB) rather than being
symlinked into the archive, so this tree is self-contained and the archive can be
deleted whenever you like. Two things had to be repaired for that:

* all 62 console scripts in `venv/bin/` had a shebang hardcoded to the old
  absolute path;
* the editable install `.pth` pointed at `/home/hanush/Desktop/Project_Cam/src`.
  **This one matters:** while the old tree still existed under its old name, a
  subprocess doing `python -m project_cam...` would have silently imported the
  ARCHIVE's source. Renaming the old tree is what turned that into a loud
  failure. If you ever clone or move this tree again, check that `.pth` first.

`venv/bin/activate` still mentions the old path in a comment (harmless);
`_editable_impl_markitdown.pth` was already dangling before the move.

## If you need something from the archive

```bash
ls  ~/Desktop/Project_Cam_ARCHIVE_20260804/
git -C ~/Desktop/Project_Cam_ARCHIVE_20260804 log --oneline | head
```

Copy what you need **into this tree explicitly**, and if it is a recording or a
calibration, write down in the same commit which rig it came from. That single
habit is what this document exists to enforce.
