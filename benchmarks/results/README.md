# Benchmark Results

CSV outputs from `benchmarks/*.py`. Result CSVs are git-ignored (local
artifacts); this README documents the schema and how to regenerate them.

## Schema

Every CSV shares the column set defined in `benchmarks/_bench_common.py`
(`COLUMNS`). The two provenance columns matter most:

- `mode` — `dry_run` (planned config, no hardware) or `measured` (real run).
- `measured` — `True` only for real measurements. **Never cite a `False` row as a
  result.**

## Regenerate (dry-run, no GPU/cameras)

```bash
python benchmarks/benchmark_camera_count.py --dry-run \
  --config-4 configs/cameras/cameras_4cam.yaml \
  --config-6 configs/cameras/cameras_6cam_usb.yaml \
  --output benchmarks/results/camera_count_dry_run.csv

python benchmarks/benchmark_inference.py --dry-run \
  --model models/ball/yolo26m-672.engine --backend tensorrt --batch-size 6 \
  --output benchmarks/results/ball_trt_usb6_dry_run.csv

python benchmarks/benchmark_pipeline.py --dry-run \
  --output benchmarks/results/pipeline_dry_run.csv
```

## Real runs (GPU + weights)

Drop `--dry-run` from `benchmark_inference.py` on the RTX box with the engines in
`models/`. Pipeline/camera-count real measurements come from the live rig's
`--perf-jsonl`. Summarize into `docs/performance_report.md`, keeping measured and
planned values clearly separated.
