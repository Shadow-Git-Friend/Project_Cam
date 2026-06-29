"""Continuous evaluation for 3D tracking accuracy.

The project's value is metric-3D accuracy, and that accuracy silently depends on
the model weights, the intrinsics, and the extrinsics. Swapping any of them can
regress accuracy with no visible error. This package turns accuracy into a
first-class, testable signal:

- ``metrics`` -- pure 3D error statistics (mean / P95 / RMSE / bias / precision)
  from predicted-vs-ground-truth point pairs.
- ``gate``    -- a regression gate that compares metrics against documented
  thresholds and exits non-zero on regression, so CI can block a bad model or
  calibration swap.

Everything operates on plain NumPy arrays and JSON, so it runs in CI without a
GPU, cameras, or the live stack.
"""

from .metrics import ErrorMetrics, compute_3d_error, load_pairs

__all__ = [
    "ErrorMetrics",
    "compute_3d_error",
    "load_pairs",
    "GateOutcome",
    "evaluate_against_thresholds",
    "load_thresholds",
]


def __getattr__(name: str):
    """Lazy-export gate symbols without preloading the CLI module.

    Importing ``project_cam.evaluation.gate`` from here causes
    ``python -m project_cam.evaluation.gate`` to emit a runpy RuntimeWarning.
    Keeping the export lazy preserves the public import surface while allowing
    the gate to run as a clean CLI.
    """
    if name in {"GateOutcome", "evaluate_against_thresholds", "load_thresholds"}:
        from .gate import GateOutcome, evaluate_against_thresholds, load_thresholds

        return {
            "GateOutcome": GateOutcome,
            "evaluate_against_thresholds": evaluate_against_thresholds,
            "load_thresholds": load_thresholds,
        }[name]
    raise AttributeError(name)
