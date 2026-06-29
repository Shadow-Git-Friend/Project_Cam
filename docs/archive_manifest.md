# Archive Manifest

This file records the June 29, 2026 cleanup pass that moved historical,
generated, and local-only material out of the portfolio root without deleting
data. The active runtime, calibration truth, service code, tests, configs, and
portfolio docs remain in their normal locations.

## Active Portfolio Surface

Keep these paths in the root-level project surface:

```text
README.md
PROJECT_IMPROVEMENT_PLAN.md
CANONICAL.md
CLAUDE.md
pyproject.toml
Makefile
requirements*.txt
src/
tests/
configs/
services/
apps/
benchmarks/
deploy/
docs/
arena_fixed/
garage_lab_combined/config/
garage_lab_combined/cal/
garage_lab_combined/gt_eval/
Parallel_working/scripts/
```

## Thesis And Defense Archive

Moved to `docs/thesis_archive/`:

```text
root_thesis/
  5918_Yessimkhan_Orynbay_pre_final_622724_78420621.md
  MSc_Thesis1.docx
  Master_Thesis_3_.md
  thesis_defense_qa.md
  thesis_draft.md
  thesis_engineering_chapter.md
  thesis_report_bachelors.md
  yessimkhan_thesis.md

defense_decks/
  presentation_defense_improved_github_prioritized*.pptx

thesis_defense_presentation/
latex_old_version/
latex_revised/
latex_tevised_codex/
garage_lab_combined_thesis/
```

These files are useful evidence and thesis history, but they are not the first
thing a recruiter or engineering reviewer should see in the repository root.

## Legacy Notes

Moved to `docs/archive/legacy_notes/`:

```text
deep-research-report.md
gemini3.1pro.md
new_complete.md
plan.md
suggestions.md
```

These remain tracked reference documents. Current portfolio docs should link to
the concise `README.md`, `docs/architecture.md`, `docs/performance_report.md`,
and `PROJECT_IMPROVEMENT_PLAN.md` first.

## Local Artifacts

Moved to `artifacts_local/` and ignored by Git:

```text
codex_tmp/
raw_captures/usb6_frames/camUsb*/
raw_captures/root_recording_metadata/
generated/coverage_out/
generated/project_tree.md
outputs/Parallel_working_output/
outputs/garage_lab_combined_output/
outputs/garage_lab_combined_sync_frames/
outputs/garage_lab_combined_synchronized_video/
model_downloads/weights-20260413T135335Z-3-001/
calibration_backups/cal_backup/
local_notes/START_HERE.md
```

These are preserved locally but should not be part of normal Git diffs.

## Historical / External Repositories

Moved to ignored local archive paths:

```text
archive/historical_repos/proxiball_project_cam_duplicate_20260629/
archive/external_repos/markitdown/
```

The projector code under `proxiball_3d-main/projector/` remains in place because
current tests and documentation still reference it.

## Intentionally Left In Place

```text
cameras.md
control_12_full.ino
yolo11m-pose.engine
proxiball_3d-main/projector/
Remounted_West_East/
kairat_pitch/
voice_commands/
```

Reasons:

- `cameras.md` is still a current hardware/bandwidth reference used by docs.
- `control_12_full.ino` and `yolo11m-pose.engine` are referenced by live scripts
  and handoff docs.
- `proxiball_3d-main/projector/` is covered by tests.
- `Remounted_West_East/` is calibration/projector evidence.
- `kairat_pitch/` and `voice_commands/` are small enough to leave until a
  separate presentation/voice cleanup pass updates all references.

