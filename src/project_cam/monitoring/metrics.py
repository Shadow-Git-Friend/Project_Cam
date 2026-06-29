"""Prometheus metrics with a dependency-free fallback.

Why a fallback: ``prometheus_client`` is an optional dependency (the ``api``
extra). The metric contract -- names, types, allowed labels -- is part of the
service interface and must be testable and exposable even on a minimal install.
When the real client is present it is used (proper histograms, shared registry);
otherwise a small in-process store renders valid Prometheus text exposition so
``GET /metrics`` still returns the documented series.

Label cardinality is kept low on purpose (see ``ALLOWED_LABELS``): never put a
frame id, timestamp, file path, or raw session id on a metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Tuple

try:  # optional backend
    import prometheus_client as _prom

    PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when the extra is absent
    _prom = None
    PROMETHEUS_AVAILABLE = False


# Labels we permit on any metric. Anything outside this set is rejected so we do
# not accidentally introduce a high-cardinality dimension.
ALLOWED_LABELS = {
    "camera_profile",
    "camera_id",
    "stage",
    "model_name",
    "backend",
    "gate_reason",
    "quality_reason",
}


@dataclass(frozen=True)
class MetricSpec:
    name: str
    kind: str  # "counter" | "gauge" | "histogram"
    help: str
    labelnames: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        bad = set(self.labelnames) - ALLOWED_LABELS
        if bad:
            raise ValueError(f"{self.name} uses disallowed labels: {sorted(bad)}")
        if self.kind not in {"counter", "gauge", "histogram"}:
            raise ValueError(f"{self.name} has unknown kind {self.kind!r}")


# The exact metric contract documented in docs/monitoring.md.
METRIC_SPECS: List[MetricSpec] = [
    MetricSpec("project_cam_camera_count", "gauge",
               "Number of cameras in the active profile.", ("camera_profile",)),
    MetricSpec("project_cam_frames_total", "counter",
               "Frames captured per camera.", ("camera_profile", "camera_id")),
    MetricSpec("project_cam_dropped_frames_total", "counter",
               "Frames dropped per camera (stale / queue overflow).",
               ("camera_profile", "camera_id")),
    MetricSpec("project_cam_capture_latency_ms", "histogram",
               "Per-camera capture latency in milliseconds.",
               ("camera_profile", "camera_id")),
    MetricSpec("project_cam_inference_latency_ms", "histogram",
               "Model inference latency in milliseconds.",
               ("camera_profile", "stage", "model_name", "backend")),
    MetricSpec("project_cam_triangulation_latency_ms", "histogram",
               "Multi-view triangulation latency in milliseconds.",
               ("camera_profile",)),
    MetricSpec("project_cam_pipeline_latency_ms", "histogram",
               "End-to-end pipeline latency in milliseconds.",
               ("camera_profile",)),
    MetricSpec("project_cam_gpu_memory_mb", "gauge",
               "GPU memory in use, megabytes.", ()),
    MetricSpec("project_cam_pose_camera_count", "gauge",
               "Cameras currently contributing to the pose solve.",
               ("camera_profile",)),
    MetricSpec("project_cam_ball_reprojection_error_px", "histogram",
               "Ball triangulation reprojection error, pixels.",
               ("camera_profile",)),
    MetricSpec("project_cam_joint_reprojection_error_px", "histogram",
               "Joint triangulation reprojection error, pixels.",
               ("camera_profile",)),
    MetricSpec("project_cam_safety_gate_blocked_total", "counter",
               "Targets blocked by a safety gate, by reason.", ("gate_reason",)),
    MetricSpec("project_cam_event_logger_dropped_total", "counter",
               "Event-log records dropped by the non-blocking writer.", ()),
    MetricSpec("project_cam_frame_brightness", "gauge",
               "Mean frame brightness per camera on a 0-255 scale.",
               ("camera_profile", "camera_id")),
    MetricSpec("project_cam_frame_blur_laplacian_var", "gauge",
               "Variance of a Laplacian focus metric per camera.",
               ("camera_profile", "camera_id")),
    MetricSpec("project_cam_frame_quality_bad_total", "counter",
               "Frames failing input-quality checks by reason.",
               ("camera_profile", "camera_id", "quality_reason")),
]

METRIC_NAMES: List[str] = [s.name for s in METRIC_SPECS]
_SPEC_BY_NAME: Dict[str, MetricSpec] = {s.name: s for s in METRIC_SPECS}


# --------------------------------------------------------------------------- #
# Dependency-free fallback store
# --------------------------------------------------------------------------- #
@dataclass
class _FallbackSeries:
    spec: MetricSpec
    # keyed by the ordered label-value tuple
    values: Dict[Tuple[str, ...], float] = field(default_factory=dict)
    counts: Dict[Tuple[str, ...], int] = field(default_factory=dict)  # histograms


class _FallbackRegistry:
    """Minimal store that renders valid Prometheus text exposition.

    Counters/gauges render as their kind. Histograms render as a summary
    (``_count`` + ``_sum``) -- valid exposition without per-bucket fidelity; the
    real ``prometheus_client`` backend provides full buckets when installed.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._series = {s.name: _FallbackSeries(s) for s in METRIC_SPECS}

    def _key(self, spec: MetricSpec, labels: Dict[str, str]) -> Tuple[str, ...]:
        return tuple(str(labels.get(name, "")) for name in spec.labelnames)

    def inc(self, spec: MetricSpec, amount: float, labels: Dict[str, str]) -> None:
        with self._lock:
            s = self._series[spec.name]
            k = self._key(spec, labels)
            s.values[k] = s.values.get(k, 0.0) + amount

    def set(self, spec: MetricSpec, value: float, labels: Dict[str, str]) -> None:
        with self._lock:
            self._series[spec.name].values[self._key(spec, labels)] = float(value)

    def observe(self, spec: MetricSpec, value: float, labels: Dict[str, str]) -> None:
        with self._lock:
            s = self._series[spec.name]
            k = self._key(spec, labels)
            s.values[k] = s.values.get(k, 0.0) + float(value)  # _sum
            s.counts[k] = s.counts.get(k, 0) + 1

    def render(self) -> bytes:
        lines: List[str] = []
        with self._lock:
            for name in METRIC_NAMES:
                s = self._series[name]
                spec = s.spec
                text_type = "summary" if spec.kind == "histogram" else spec.kind
                lines.append(f"# HELP {name} {spec.help}")
                lines.append(f"# TYPE {name} {text_type}")
                if spec.kind == "histogram":
                    for k, total in s.values.items():
                        lbl = self._fmt_labels(spec, k)
                        lines.append(f"{name}_sum{lbl} {total}")
                        lines.append(f"{name}_count{lbl} {s.counts.get(k, 0)}")
                    if not s.values:
                        lines.append(f"{name}_sum 0.0")
                        lines.append(f"{name}_count 0")
                else:
                    if s.values:
                        for k, val in s.values.items():
                            lines.append(f"{name}{self._fmt_labels(spec, k)} {val}")
                    else:
                        lines.append(f"{name} 0.0")
        return ("\n".join(lines) + "\n").encode("utf-8")

    @staticmethod
    def _fmt_labels(spec: MetricSpec, key: Tuple[str, ...]) -> str:
        if not spec.labelnames:
            return ""
        parts = [f'{n}="{v}"' for n, v in zip(spec.labelnames, key)]
        return "{" + ",".join(parts) + "}"


# --------------------------------------------------------------------------- #
# Public registry
# --------------------------------------------------------------------------- #
class MetricsRegistry:
    """Backend-agnostic facade over the metric contract.

    Use ``inc`` / ``set`` / ``observe`` with keyword labels. Unknown metric names
    or labels raise immediately, turning a monitoring typo into a test failure
    rather than a silent missing series.
    """

    CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

    def __init__(self) -> None:
        if PROMETHEUS_AVAILABLE:
            self._registry = _prom.CollectorRegistry()
            self._prom_metrics = self._build_prom()
            self._fallback = None
        else:
            self._registry = None
            self._prom_metrics = None
            self._fallback = _FallbackRegistry()

    def _build_prom(self) -> Dict[str, object]:
        out: Dict[str, object] = {}
        for spec in METRIC_SPECS:
            if spec.kind == "counter":
                out[spec.name] = _prom.Counter(
                    spec.name, spec.help, spec.labelnames, registry=self._registry)
            elif spec.kind == "gauge":
                out[spec.name] = _prom.Gauge(
                    spec.name, spec.help, spec.labelnames, registry=self._registry)
            else:
                out[spec.name] = _prom.Histogram(
                    spec.name, spec.help, spec.labelnames, registry=self._registry)
        return out

    def _spec(self, name: str) -> MetricSpec:
        try:
            return _SPEC_BY_NAME[name]
        except KeyError as exc:
            raise KeyError(f"unknown metric: {name!r}") from exc

    @staticmethod
    def _check_labels(spec: MetricSpec, labels: Dict[str, str]) -> None:
        if set(labels) != set(spec.labelnames):
            raise ValueError(
                f"{spec.name} expects labels {sorted(spec.labelnames)}, "
                f"got {sorted(labels)}")

    def _prom_handle(self, spec: MetricSpec, labels: Dict[str, str]):
        m = self._prom_metrics[spec.name]
        return m.labels(**labels) if spec.labelnames else m

    def inc(self, name: str, amount: float = 1.0, **labels: str) -> None:
        spec = self._spec(name)
        if spec.kind != "counter":
            raise TypeError(f"{name} is a {spec.kind}, not a counter")
        self._check_labels(spec, labels)
        if PROMETHEUS_AVAILABLE:
            self._prom_handle(spec, labels).inc(amount)
        else:
            self._fallback.inc(spec, amount, labels)

    def set(self, name: str, value: float, **labels: str) -> None:
        spec = self._spec(name)
        if spec.kind != "gauge":
            raise TypeError(f"{name} is a {spec.kind}, not a gauge")
        self._check_labels(spec, labels)
        if PROMETHEUS_AVAILABLE:
            self._prom_handle(spec, labels).set(value)
        else:
            self._fallback.set(spec, value, labels)

    def observe(self, name: str, value: float, **labels: str) -> None:
        spec = self._spec(name)
        if spec.kind != "histogram":
            raise TypeError(f"{name} is a {spec.kind}, not a histogram")
        self._check_labels(spec, labels)
        if PROMETHEUS_AVAILABLE:
            self._prom_handle(spec, labels).observe(value)
        else:
            self._fallback.observe(spec, value, labels)

    def render(self) -> Tuple[str, bytes]:
        """Return ``(content_type, payload)`` for the ``/metrics`` endpoint."""
        if PROMETHEUS_AVAILABLE:
            return _prom.CONTENT_TYPE_LATEST, _prom.generate_latest(self._registry)
        return self.CONTENT_TYPE, self._fallback.render()


_SINGLETON: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """Process-wide metrics registry (created on first use)."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = MetricsRegistry()
    return _SINGLETON
