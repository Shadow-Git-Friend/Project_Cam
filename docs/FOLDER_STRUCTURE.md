# Folder Structure

## Full Project_Cam Structure To Share

This describes the full workspace (not only `garage_lab_combined`).

```text
Project_Cam/
├── README.md
├── requirements.txt
├── .gitignore
├── plan
├── plan.txt/
├── docs/
│   ├── PROJECT_OVERVIEW_FOR_CHATGPT.md
│   ├── FOLDER_STRUCTURE.md
│   ├── REPO_SHARING_CHECKLIST.md
│   └── CHATGPT_HANDOFF_PROMPT.md
├── src/
│   ├── calibration/
│   ├── capture/
│   ├── core/
│   ├── experiments/
│   ├── tools/
│   └── legacy/
├── config/
├── scripts/
├── GARAGE_CAMERAS/
├── garage-20260217T113109Z-3-001/
├── garage_lab_combined/
│   ├── README.md
│   ├── config/
│   ├── scripts/
│   ├── cal/
│   ├── gt_eval/
│   └── thesis/
├── cal/
├── data/
├── output/
├── runs/
├── pitch/
├── Sport_center/
├── CAMERA1/
├── CAMERA2/
├── Camera Roll/
├── Intrinsicsdec17/
└── venv/
```

## What Each Part Does

- `README.md`: top-level overview, architecture summary, and entry points.
- `docs/`: handoff docs for ChatGPT and thesis-assistant workflows.
- `src/`: foundational algorithm layer (capture, calibration, triangulation, rendering, legacy baselines).
- `config/`: local camera device map for early pipeline scripts.
- `scripts/`: standalone project utilities (calibration helpers and dataset tools).
- `GARAGE_CAMERAS/`: practical multi-camera capture tooling and synchronization helpers.
- `garage-20260217T113109Z-3-001/`: imported baseline assets and reference workflows.
- `garage_lab_combined/`: latest integrated 4-camera research pipeline.
- `garage_lab_combined/config/`: stable camera-role mapping and runtime settings.
- `garage_lab_combined/cal/`: calibration artifacts (intrinsics, extrinsics, board specs).
- `garage_lab_combined/scripts/`: end-to-end scripts (capture, process, evaluate, render, live view).
- `garage_lab_combined/gt_eval/`: evaluation protocols, session outputs, and reports.
- `garage_lab_combined/thesis/`: thesis drafts, selected figures, and submission assets.
- `cal/`, `Intrinsicsdec17/`: earlier calibration outputs and archives.
- `data/`, `output/`, `runs/`, `pitch/`: datasets, generated outputs, experiments, and render artifacts.
- `CAMERA1/`, `CAMERA2/`, `Camera Roll/`: raw camera captures and recordings.
- `Sport_center/`: sport-center specific capture/calibration subset.
- `venv/`: local Python environment (not for sharing).

## Share Strategy

- Include the whole `Project_Cam` codebase and documentation structure.
- Exclude heavy raw/generated artifacts and local environments via `.gitignore`.
- For required large binaries (models/datasets), use Git LFS or external storage links.
