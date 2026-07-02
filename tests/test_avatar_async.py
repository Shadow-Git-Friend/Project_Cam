"""Tests for the non-blocking SMPL fit wrapper and pelvis anchor-follow."""

import time

import numpy as np
import pytest

from project_cam.avatar.async_fitter import (
    AsyncSmplFitter,
    anchor_vertices,
    pelvis_from_coco,
)


def make_joints(pelvis=(1000.0, 2000.0, 900.0)):
    joints = np.full((17, 3), np.nan, dtype=np.float64)
    joints[11] = np.asarray(pelvis) + [0.0, -100.0, 0.0]  # left hip
    joints[12] = np.asarray(pelvis) + [0.0, 100.0, 0.0]   # right hip
    return joints


class FakeFitter:
    """Stand-in for SmplSessionFitter: records calls, optional delay/failure."""

    def __init__(self, delay_s=0.0, fail_with=None):
        self.delay_s = delay_s
        self.fail_with = fail_with
        self.calls = 0
        self.last_joints = None

    def fit(self, joints_mm, confidences=None):
        self.calls += 1
        self.last_joints = np.asarray(joints_mm).copy()
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.fail_with is not None:
            raise self.fail_with
        return {"pelvis_x": float(np.asarray(joints_mm)[11, 0])}


def wait_until(predicate, timeout_s=3.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ------------------------------------------------------------------ geometry

def test_pelvis_from_coco_midhip():
    joints = make_joints(pelvis=(500.0, 700.0, 900.0))
    pelvis = pelvis_from_coco(joints)
    assert pelvis == pytest.approx([500.0, 700.0, 900.0])


def test_pelvis_from_coco_missing_hip_returns_none():
    joints = make_joints()
    joints[12] = np.nan
    assert pelvis_from_coco(joints) is None
    assert pelvis_from_coco(np.zeros((5, 3))) is None


def test_anchor_vertices_translates_by_pelvis_delta():
    verts = np.array([[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]])
    out = anchor_vertices(verts, fit_pelvis_mm=[1.0, 2.0, 3.0], current_pelvis_mm=[4.0, 2.0, 3.0])
    assert out == pytest.approx(verts + [3.0, 0.0, 0.0])
    # Missing pelvis -> unchanged
    assert anchor_vertices(verts, None, [1, 2, 3]) == pytest.approx(verts)


# ------------------------------------------------------------------ worker

def test_submit_is_nonblocking_and_latest_arrives():
    fitter = FakeFitter(delay_s=0.05)
    wrapper = AsyncSmplFitter(fitter)
    try:
        t0 = time.perf_counter()
        wrapper.submit(make_joints(), np.ones(17))
        assert (time.perf_counter() - t0) < 0.02  # returned before the fit ran
        assert wait_until(lambda: wrapper.latest() is not None)
        snap = wrapper.latest()
        assert snap.result["pelvis_x"] == pytest.approx(1000.0)
        assert snap.pelvis_mm == pytest.approx([1000.0, 2000.0, 900.0])
    finally:
        wrapper.close()


def test_latest_only_queue_skips_intermediate_submissions():
    fitter = FakeFitter(delay_s=0.05)
    wrapper = AsyncSmplFitter(fitter)
    try:
        n = 30
        for i in range(n):
            wrapper.submit(make_joints(pelvis=(float(i), 0.0, 0.0)))
        assert wait_until(lambda: not wrapper.busy)
        # A slow fitter must not process all 30 snapshots...
        assert fitter.calls < n
        # ...but the newest snapshot processed must be the final submission.
        assert wrapper.latest().result["pelvis_x"] == pytest.approx(float(n - 1))
    finally:
        wrapper.close()


def test_value_error_is_skipped_not_fatal():
    fitter = FakeFitter(fail_with=ValueError("not enough joints"))
    wrapper = AsyncSmplFitter(fitter)
    try:
        wrapper.submit(make_joints())
        assert wait_until(lambda: fitter.calls >= 1)
        assert wrapper.error is None
        # Worker still alive: a healthy fit afterwards succeeds.
        fitter.fail_with = None
        wrapper.submit(make_joints(pelvis=(7.0, 0.0, 0.0)))
        assert wait_until(lambda: wrapper.latest() is not None)
        assert wrapper.latest().result["pelvis_x"] == pytest.approx(7.0)
    finally:
        wrapper.close()


def test_fatal_error_surfaces_and_stops_worker():
    fitter = FakeFitter(fail_with=RuntimeError("CUDA out of memory"))
    wrapper = AsyncSmplFitter(fitter)
    try:
        wrapper.submit(make_joints())
        assert wait_until(lambda: wrapper.error is not None)
        assert "CUDA out of memory" in wrapper.error
        assert wrapper.latest() is None
    finally:
        wrapper.close()


def test_close_joins_worker_thread():
    wrapper = AsyncSmplFitter(FakeFitter())
    wrapper.close()
    assert not wrapper._thread.is_alive()
