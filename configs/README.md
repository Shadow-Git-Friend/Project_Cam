# Configs

`configs/exercises/football_academy_u10.yaml` contains configurable coaching
rules for the offline athlete movement assessment MVP. These thresholds are
screening heuristics for reports, not medical diagnosis or talent ranking.

`configs/models.yaml` is the model registry/provenance file used by
`project_cam.models` and `GET /v1/models`.

`configs/eval_thresholds.yaml` contains hardware-free 3D accuracy regression
thresholds for `make eval-gate` and `POST /v1/evaluate`.
