"""Non-blocking SMPL fitting for live viewers.

The live loop must never wait on an SMPL fit: one fit is 8+ Adam iterations
of a full body-model forward/backward (hundreds of ms on CPU), which would
stall capture, pose, ball tracking and rendering together. This wrapper runs
the fit in a daemon thread with a latest-only input slot: `submit()` replaces
any pending joints snapshot and returns immediately, `latest()` returns the
newest finished fit. Between fits the caller keeps the person "attached" to
the mesh by translating the last result to the current mid-hip
(`pelvis_from_coco` + vertex delta) — shape/pose trail by one fit, position
does not.

numpy-only at import time; torch is only touched inside the wrapped fitter.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

COCO_LEFT_HIP = 11
COCO_RIGHT_HIP = 12


def pelvis_from_coco(joints_mm) -> Optional[np.ndarray]:
    """Mid-hip point (mm) from a COCO-17 joint array, or None if hips are bad."""
    joints = np.asarray(joints_mm, dtype=np.float64)
    if joints.ndim != 2 or joints.shape[0] < 13 or joints.shape[1] < 3:
        return None
    left = joints[COCO_LEFT_HIP, :3]
    right = joints[COCO_RIGHT_HIP, :3]
    if not (np.isfinite(left).all() and np.isfinite(right).all()):
        return None
    return (left + right) / 2.0


def anchor_vertices(vertices_mm, fit_pelvis_mm, current_pelvis_mm) -> np.ndarray:
    """Translate fitted vertices so the fit-time pelvis lands on the current one."""
    verts = np.asarray(vertices_mm, dtype=np.float64)
    if fit_pelvis_mm is None or current_pelvis_mm is None:
        return verts
    delta = np.asarray(current_pelvis_mm, dtype=np.float64) - np.asarray(
        fit_pelvis_mm, dtype=np.float64
    )
    if not np.isfinite(delta).all():
        return verts
    return verts + delta.reshape(1, 3)


@dataclass(frozen=True)
class AsyncFitSnapshot:
    """One finished fit: the result plus the pelvis of the joints it was fit to."""

    result: Any
    pelvis_mm: Optional[np.ndarray]
    seq: int


class AsyncSmplFitter:
    """Latest-only background wrapper around a (Session)SmplFitter.

    submit() never blocks and never queues more than one snapshot; a slow fit
    simply skips intermediate frames, mirroring `ThreadedCapture.read_latest`.
    A fatal fitter exception is surfaced via `.error` (worker stops; caller
    decides to disable the avatar). ValueError ("not enough joints") is not
    fatal — the snapshot is skipped like a dropped frame.
    """

    def __init__(self, fitter):
        self._fitter = fitter
        self._cond = threading.Condition()
        self._pending: Optional[tuple[np.ndarray, Optional[np.ndarray]]] = None
        self._snapshot: Optional[AsyncFitSnapshot] = None
        self._error: Optional[str] = None
        self._stop = False
        self._seq = 0
        self._busy = False
        self._thread = threading.Thread(
            target=self._worker, name="smpl-fit", daemon=True
        )
        self._thread.start()

    def submit(self, joints_mm, confidences=None) -> None:
        """Replace the pending joints snapshot (copies inputs; non-blocking)."""
        joints = np.array(joints_mm, dtype=np.float64, copy=True)
        conf = None if confidences is None else np.array(confidences, copy=True)
        with self._cond:
            if self._stop or self._error is not None:
                return
            self._pending = (joints, conf)
            self._cond.notify()

    def latest(self) -> Optional[AsyncFitSnapshot]:
        """Newest finished fit (or None). Never blocks, never raises."""
        with self._cond:
            return self._snapshot

    @property
    def error(self) -> Optional[str]:
        with self._cond:
            return self._error

    @property
    def busy(self) -> bool:
        """True while a fit is running (useful to pace submissions/telemetry)."""
        with self._cond:
            return self._busy or self._pending is not None

    def close(self, timeout: float = 2.0) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        self._thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._stop:
                    self._cond.wait(timeout=0.25)
                if self._stop:
                    return
                joints, conf = self._pending
                self._pending = None
                self._busy = True
            try:
                result = self._fitter.fit(joints, conf)
            except ValueError:
                # Not enough reliable joints in this snapshot; skip it.
                with self._cond:
                    self._busy = False
                continue
            except Exception as exc:  # fatal: model/device problems
                with self._cond:
                    self._error = f"{type(exc).__name__}: {exc}"
                    self._busy = False
                return
            snapshot = AsyncFitSnapshot(
                result=result,
                pelvis_mm=pelvis_from_coco(joints),
                seq=self._seq + 1,
            )
            with self._cond:
                self._seq = snapshot.seq
                self._snapshot = snapshot
                self._busy = False
