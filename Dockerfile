# CPU image for the aim-only API service + CI smoke tests.
# Deliberately slim: no GPU, no torch/ultralytics/mmpose. It serves /health,
# /metrics, /v1/triangulate, /v1/predict, and the inference *contracts* (501).
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

# Install the light API deps first for better layer caching, then the package
# itself without re-resolving the heavy core extras.
COPY requirements-api.txt pyproject.toml README.md ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY src/ ./src/
COPY services/ ./services/
COPY configs/ ./configs/
RUN pip install --no-cache-dir --no-deps -e .

ENV PYTHONPATH=/app/src \
    PROJECT_CAM_CAMERA_PROFILE=usb6

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "services.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
