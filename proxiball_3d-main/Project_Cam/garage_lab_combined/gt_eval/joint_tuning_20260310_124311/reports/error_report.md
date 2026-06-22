# Joint Touch 3D GT Error Report

- Trials total: `81`
- Trials valid: `62`
- Trials missing/failed: `19`

## Error (mm)
- Mean: `143.38`
- Median: `148.90`
- RMSE: `147.73`
- P90: `182.04`
- P95: `198.73`
- Max: `217.34`

## Axis Bias (mm)
- ex mean: `50.68`
- ey mean: `46.57`
- ez mean: `-106.98`

## Detection Quality
- Mean detection ratio (window): `1.000`

## Precision (Static Hold)
- Mean std-norm (mm): `4.32`
- P95 std-norm (mm): `8.97`

## Per Joint
- `left_shoulder`: mean `164.38` mm, p95 `199.54` mm
- `right_hip`: mean `150.38` mm, p95 `172.31` mm
- `right_knee`: mean `110.03` mm, p95 `170.75` mm

## Outputs
- `trial_errors.csv`
- `summary_metrics.json`
- `correction_model.json`
