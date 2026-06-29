"""3D accuracy metrics from predicted-vs-ground-truth point pairs.

Mirrors the project's reported accuracy convention (see docs/model_card.md):

- **error** is the Euclidean distance ``||pred - gt||`` per pair (mm);
- **bias** is the mean signed residual per axis (a correctable systematic);
- **precision** is the per-axis std of the residual averaged over axes -- the
  repeatability that remains after the bias is removed.

Pure NumPy; no camera stack, no model weights.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import List, Tuple

import numpy as np


@dataclass(frozen=True)
class ErrorMetrics:
    n: int
    mean_mm: float
    median_mm: float
    p95_mm: float
    max_mm: float
    rmse_mm: float
    precision_mm: float
    bias_mm: Tuple[float, float, float]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bias_mm"] = list(self.bias_mm)
        return d


def compute_3d_error(pred: np.ndarray, gt: np.ndarray) -> ErrorMetrics:
    """Error statistics for paired predictions and ground-truth points (mm).

    ``pred`` and ``gt`` are ``(N, 3)`` arrays in the same world frame. Raises on
    empty input or a shape mismatch so an evaluation can never silently report on
    zero samples.
    """
    pred = np.asarray(pred, dtype=np.float64)
    gt = np.asarray(gt, dtype=np.float64)
    if pred.ndim != 2 or pred.shape[1] != 3:
        raise ValueError(f"pred must be (N, 3), got {pred.shape}")
    if pred.shape != gt.shape:
        raise ValueError(f"pred {pred.shape} and gt {gt.shape} must match")
    if pred.shape[0] == 0:
        raise ValueError("need at least one point pair")

    residual = pred - gt                      # (N, 3) signed
    dist = np.linalg.norm(residual, axis=1)   # (N,)
    bias = residual.mean(axis=0)              # per-axis systematic
    # repeatability: per-axis std averaged (independent of the bias)
    precision = float(np.mean(residual.std(axis=0)))
    return ErrorMetrics(
        n=int(pred.shape[0]),
        mean_mm=float(dist.mean()),
        median_mm=float(np.median(dist)),
        p95_mm=float(np.percentile(dist, 95)),
        max_mm=float(dist.max()),
        rmse_mm=float(np.sqrt(np.mean(dist ** 2))),
        precision_mm=precision,
        bias_mm=(float(bias[0]), float(bias[1]), float(bias[2])),
    )


def load_pairs(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """Load predicted/GT point pairs from a JSON file.

    Accepts either ``{"pairs": [{"pred": [x,y,z], "gt": [x,y,z]}, ...]}`` or a
    bare list of such pair objects.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    pairs = data["pairs"] if isinstance(data, dict) else data
    pred: List[list] = []
    gt: List[list] = []
    for i, pair in enumerate(pairs):
        try:
            pred.append([float(v) for v in pair["pred"]])
            gt.append([float(v) for v in pair["gt"]])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"pair[{i}] malformed: {exc}") from exc
    return np.asarray(pred, dtype=np.float64), np.asarray(gt, dtype=np.float64)
