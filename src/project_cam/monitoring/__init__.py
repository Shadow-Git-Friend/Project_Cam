"""Operational monitoring for the Project_Cam service layer.

Exposes Prometheus-style metrics (FPS, latency, dropped frames, camera count,
reprojection error, safety-gate blocks) so the live pipeline and the API can be
observed the way a production video-analytics system is. The metric *names* are
always importable; the Prometheus client backend is optional, with a pure-Python
fallback so ``/metrics`` works on a minimal install.
"""

from .metrics import (
    METRIC_NAMES,
    METRIC_SPECS,
    PROMETHEUS_AVAILABLE,
    MetricsRegistry,
    get_metrics,
)

__all__ = [
    "METRIC_NAMES",
    "METRIC_SPECS",
    "PROMETHEUS_AVAILABLE",
    "MetricsRegistry",
    "get_metrics",
]
