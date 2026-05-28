# GT Session 2026-03-03

This session is for absolute-error evaluation in the garage world frame (mm).

## Files
- `trials.csv`: 25 planned GT trials (15 ball + 10 joint-touch).
- `clips/`: store per-trial synchronized 4-camera clips.
- `reports/`: generated error/bias outputs.

## Capture Rules
- Use one subject only.
- Use flash marker at hold start/end.
- Hold target static for 2-3 seconds.
- Keep all camera settings fixed for all trials.

## Clip Naming
- `clips/B01/...`, `clips/B02/...`, ... `clips/B15/...`
- `clips/J01/...`, `clips/J02/...`, ... `clips/J10/...`

## Expected Report Outputs
- `reports/trial_errors.csv`
- `reports/summary_metrics.json`
- `reports/error_report.md`
- `reports/correction_model.json`
