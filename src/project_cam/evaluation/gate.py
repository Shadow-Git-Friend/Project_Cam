"""Regression gate: block a model/calibration change that hurts 3D accuracy.

Compares computed error metrics against documented per-suite thresholds
(``configs/eval_thresholds.yaml``) and exits non-zero on regression, so it drops
straight into CI:

    python -m project_cam.evaluation.gate \
        --pairs tests/fixtures/eval_pairs_ball_static.json \
        --suite ball_static

Thresholds are upper bounds (``max_*``) plus an optional ``min_n`` so a gate can
never pass on too few samples.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import List, Union

import yaml

from .metrics import ErrorMetrics, compute_3d_error, load_pairs

_CHECKS = {
    "max_mean_mm": ("mean_mm", "mean"),
    "max_p95_mm": ("p95_mm", "p95"),
    "max_max_mm": ("max_mm", "max"),
    "max_rmse_mm": ("rmse_mm", "rmse"),
    "max_precision_mm": ("precision_mm", "precision"),
}


@dataclass(frozen=True)
class GateOutcome:
    passed: bool
    suite: str
    failures: List[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)

    def report(self) -> str:
        head = f"[eval-gate] suite={self.suite} -> {'PASS' if self.passed else 'FAIL'}"
        lines = [head]
        for k, (mkey, label) in _CHECKS.items():
            if k in self.thresholds and mkey in self.metrics:
                mark = "ok"
                if any(label in f for f in self.failures):
                    mark = "FAIL"
                lines.append(
                    f"  {label:9s} {self.metrics[mkey]:8.2f} mm  (max {self.thresholds[k]}) {mark}")
        for f in self.failures:
            lines.append(f"  ! {f}")
        return "\n".join(lines)


def _as_metrics_dict(metrics: Union[ErrorMetrics, dict]) -> dict:
    return metrics.to_dict() if isinstance(metrics, ErrorMetrics) else dict(metrics)


def evaluate_against_thresholds(
    metrics: Union[ErrorMetrics, dict], thresholds: dict, *, suite: str = ""
) -> GateOutcome:
    m = _as_metrics_dict(metrics)
    failures: List[str] = []

    min_n = thresholds.get("min_n")
    if min_n is not None and m.get("n", 0) < int(min_n):
        failures.append(f"n={m.get('n', 0)} below min_n={min_n}")

    for tkey, (mkey, label) in _CHECKS.items():
        if tkey not in thresholds:
            continue
        if mkey not in m:
            failures.append(f"metric {mkey!r} missing for threshold {tkey}")
            continue
        limit = float(thresholds[tkey])
        value = float(m[mkey])
        if value > limit:
            failures.append(f"{label} {value:.2f} mm exceeds max {limit:.2f} mm")

    return GateOutcome(
        passed=not failures, suite=suite, failures=failures,
        metrics=m, thresholds=dict(thresholds))


def load_thresholds(path: str, suite: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    suites = data.get("suites", data)
    if suite not in suites:
        raise KeyError(f"suite {suite!r} not in {path}; have {sorted(suites)}")
    return suites[suite]


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--pairs", help="JSON of predicted/GT point pairs")
    src.add_argument("--metrics", help="JSON of precomputed ErrorMetrics")
    p.add_argument("--thresholds", default="configs/eval_thresholds.yaml")
    p.add_argument("--suite", required=True)
    p.add_argument("--report", default=None, help="optional path to write the JSON report")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if args.pairs:
        pred, gt = load_pairs(args.pairs)
        metrics: Union[ErrorMetrics, dict] = compute_3d_error(pred, gt)
    else:
        with open(args.metrics, "r", encoding="utf-8") as fh:
            metrics = json.load(fh)
    thresholds = load_thresholds(args.thresholds, args.suite)
    outcome = evaluate_against_thresholds(metrics, thresholds, suite=args.suite)
    print(outcome.report())
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump({
                "passed": outcome.passed, "suite": outcome.suite,
                "failures": outcome.failures, "metrics": outcome.metrics,
                "thresholds": outcome.thresholds,
            }, fh, indent=2)
    return 0 if outcome.passed else 1


if __name__ == "__main__":
    sys.exit(main())
