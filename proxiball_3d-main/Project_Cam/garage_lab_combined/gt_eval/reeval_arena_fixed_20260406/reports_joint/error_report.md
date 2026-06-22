# Joint Touch 3D GT Error Report

- Trials total: `81`
- Trials valid: `62`
- Trials missing/failed: `19`

## Error (mm)
- Mean: `178.98`
- Median: `181.17`
- RMSE: `183.69`
- P90: `227.35`
- P95: `243.77`
- Max: `271.13`

## Axis Bias (mm)
- ex mean: `82.72`
- ey mean: `72.31`
- ez mean: `-125.40`

## Detection Quality
- Mean detection ratio (window): `1.000`

## Precision (Static Hold)
- Mean std-norm (mm): `4.39`
- P95 std-norm (mm): `9.17`

## Per Joint
- `left_shoulder`: mean `203.09` mm, p95 `246.42` mm
- `right_hip`: mean `182.15` mm, p95 `218.12` mm
- `right_knee`: mean `148.44` mm, p95 `213.40` mm

## Outputs
- `trial_errors.csv`
- `summary_metrics.json`
- `correction_model.json`
