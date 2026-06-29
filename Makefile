# Project_Cam developer entrypoints. The core + API surface installs and tests
# without a GPU or cameras.
PYTHON ?= $(if $(wildcard ./venv/bin/python),./venv/bin/python,python)
VENV_PY ?= ./venv/bin/python

.PHONY: help install install-api test test-core lint format api docker-build \
        docker-smoke benchmark-dry eval-gate clean

help:
	@echo "install       - editable install with api+dev extras"
	@echo "install-api   - light API runtime deps only (requirements-api.txt)"
	@echo "test          - run the full pytest suite"
	@echo "lint          - ruff check the production surface"
	@echo "format        - ruff format the production surface"
	@echo "api           - run the FastAPI service locally on :8000"
	@echo "docker-build  - build the CPU API image"
	@echo "docker-smoke  - build CPU image, curl /health, tear down"
	@echo "benchmark-dry - run all benchmarks in --dry-run mode"
	@echo "eval-gate     - run the hardware-free 3D accuracy regression gate"

install:
	$(PYTHON) -m pip install -e ".[api,dev]"

install-api:
	$(PYTHON) -m pip install -r requirements-api.txt

test:
	$(PYTHON) -m pytest

test-core:
	$(PYTHON) -m pytest tests/test_triangulation.py tests/test_kalman.py \
		tests/test_camera_profiles.py tests/test_monitoring_metrics.py \
		tests/test_model_registry.py tests/test_frame_quality.py \
		tests/test_eval_gate_cli.py tests/test_api_mlops.py \
		tests/test_leg_raise_mode.py tests/test_limb_identity.py \
		tests/test_limb_constraints.py tests/test_rtsp_source_config.py \
		tests/test_benchmark_dry_run.py

lint:
	$(PYTHON) -m ruff check src tests services benchmarks

format:
	$(PYTHON) -m ruff format src tests services benchmarks

api:
	PYTHONPATH=src $(PYTHON) -m uvicorn services.api.app.main:app --reload --port 8000

docker-build:
	docker build -t project-cam-api:cpu .

docker-smoke:
	docker build -t project-cam-api:cpu .
	docker run -d --rm --name project-cam-smoke -p 8000:8000 project-cam-api:cpu
	@echo "waiting for API..."; sleep 6
	curl -fsS http://127.0.0.1:8000/health && echo
	curl -fsS http://127.0.0.1:8000/metrics | head -n 5
	docker stop project-cam-smoke

benchmark-dry:
	$(PYTHON) benchmarks/benchmark_camera_count.py --dry-run --output benchmarks/results/camera_count_dry_run.csv
	$(PYTHON) benchmarks/benchmark_inference.py --dry-run --output benchmarks/results/inference_dry_run.csv
	$(PYTHON) benchmarks/benchmark_pipeline.py --dry-run --output benchmarks/results/pipeline_dry_run.csv

eval-gate:
	$(PYTHON) -m project_cam.evaluation.gate \
		--pairs tests/fixtures/eval_pairs_ball_static.json \
		--suite ball_static

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache **/__pycache__ build dist *.egg-info
