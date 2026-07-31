"""Hardware-free tests for cross-view multi-person association."""

from __future__ import annotations

import time

import numpy as np

from project_cam.tracking.multi_person import (
    MultiPersonTracker,
    PersonTrack,
    candidate_anchor_px,
)

OFFSETS = np.array(
    [
        (0, -100), (-8, -110), (8, -110), (-15, -105), (15, -105),
        (-35, -55), (35, -55), (-45, -20), (45, -20), (-50, 10),
        (50, 10), (-25, 0), (25, 0), (-25, 70), (25, 70),
        (-25, 140), (25, 140),
    ],
    dtype=np.float64,
)


def candidate(anchor, scores=None):
    anchor = np.asarray(anchor, dtype=np.float64)
    return {
        "kpts": anchor[None, :] + OFFSETS,
        "scores": np.full(17, 0.9) if scores is None else np.asarray(scores),
    }


class Arena:
    def __init__(self):
        self.people = {}

    def set(self, pid, xyz):
        self.people[pid] = np.asarray(xyz, dtype=np.float64)

    def project(self, point, cam):
        x, y, z = np.asarray(point)
        if cam == "A":
            return np.array((0.5 * x, 0.5 * z))
        if cam == "B":
            return np.array((0.5 * y, 0.5 * z))
        if cam == "C":
            return np.array((0.25 * (x + y), 0.5 * z))
        return None

    def identify(self, cam, uv):
        ranked = sorted(
            (np.linalg.norm(self.project(pos, cam) - uv), pid)
            for pid, pos in self.people.items()
        )
        return ranked[0][1] if ranked and ranked[0][0] < 1e-6 else None

    def triangulate(self, cam_a, uv_a, cam_b, uv_b):
        pa = self.identify(cam_a, uv_a)
        pb = self.identify(cam_b, uv_b)
        if pa is None or pb is None:
            return None
        if pa != pb:
            return 0.5 * (self.people[pa] + self.people[pb]), 500.0
        return self.people[pa].copy(), 0.0

    def frame(self, order):
        return {
            cam: [candidate(self.project(self.people[pid], cam)) for pid in pids]
            for cam, pids in order.items()
        }


def tid_at(tracker, xyz):
    xyz = np.asarray(xyz)
    return next(
        tid for tid, track in tracker.tracks.items()
        if np.linalg.norm(track.pelvis_mm - xyz) < 1e-6
    )


def test_candidate_anchor_prefers_mid_hips_and_falls_back_to_torso():
    cand = candidate((400, 300))
    np.testing.assert_allclose(
        candidate_anchor_px(cand["kpts"], cand["scores"]), (400, 300)
    )

    scores = cand["scores"].copy()
    scores[11:13] = 0.0
    np.testing.assert_allclose(
        candidate_anchor_px(cand["kpts"], scores), (400, 245)
    )


def test_anchorless_candidates_do_not_spawn():
    scores = np.zeros(17)
    tracker = MultiPersonTracker()
    frame = {"A": [candidate((10, 10), scores)], "B": [candidate((20, 20), scores)]}
    assert tracker.step(0, frame, lambda *_: None, lambda *_: None) == {}
    assert tracker.tracks == {}


def test_two_people_spawn_from_two_camera_consensus_with_different_orders():
    arena = Arena()
    p1 = np.array((1000.0, 1200.0, 900.0))
    p2 = np.array((4000.0, 3200.0, 950.0))
    arena.set(1, p1)
    arena.set(2, p2)
    tracker = MultiPersonTracker()

    assignments = tracker.step(
        0,
        arena.frame({"A": [1, 2], "B": [2, 1]}),
        arena.project,
        arena.triangulate,
    )

    t1, t2 = tid_at(tracker, p1), tid_at(tracker, p2)
    assert assignments[t1] == {"A": 0, "B": 1}
    assert assignments[t2] == {"A": 1, "B": 0}
    claimed = [(cam, idx) for per_cam in assignments.values() for cam, idx in per_cam.items()]
    assert len(claimed) == len(set(claimed))


def test_spawn_reuses_each_cross_camera_pair_triangulation_once_per_frame():
    arena = Arena()
    arena.set(1, (1000, 1200, 900))
    arena.set(2, (4000, 3200, 950))
    calls = 0

    def counted_triangulate(*args):
        nonlocal calls
        calls += 1
        return arena.triangulate(*args)

    tracker = MultiPersonTracker()
    tracker.step(
        0,
        arena.frame({"A": [1, 2], "B": [2, 1], "C": [1, 2]}),
        arena.project,
        counted_triangulate,
    )

    # Three camera pairs x two-by-two candidate pairs.  Hypothesis expansion
    # must reuse those results instead of repeating expensive SVD work.
    assert calls <= 12
    assert len(tracker.tracks) == 2


def test_single_camera_and_cross_person_pairs_do_not_spawn():
    arena = Arena()
    arena.set(1, (1000, 1200, 900))
    arena.set(2, (4000, 3200, 950))
    tracker = MultiPersonTracker()

    assert tracker.step(
        0, arena.frame({"A": [1]}), arena.project, arena.triangulate
    ) == {}
    assert tracker.step(
        1, {"A": arena.frame({"A": [1]})["A"], "B": arena.frame({"B": [2]})["B"]},
        arena.project,
        arena.triangulate,
    ) == {}
    assert tracker.tracks == {}


def test_three_camera_spawn_rejects_conflicting_candidates_from_same_camera():
    """Two close 2-view seeds that disagree on cam A are not 3-view consensus."""
    tracker = MultiPersonTracker(min_cams_spawn=3, min_separation_mm=400)

    def tri(cam_a, uv_a, cam_b, uv_b):
        key = frozenset(((cam_a, int(uv_a[0])), (cam_b, int(uv_b[0]))))
        if key == frozenset((("A", 0), ("B", 20))):
            return np.array((0.0, 0.0, 1000.0)), 0.0
        if key == frozenset((("A", 10), ("C", 30))):
            return np.array((100.0, 0.0, 1000.0)), 0.0
        return None

    frame = {
        "A": [candidate((0, 0)), candidate((10, 0))],
        "B": [candidate((20, 0))],
        "C": [candidate((30, 0))],
    }
    assert tracker.step(0, frame, lambda *_: None, tri) == {}
    assert tracker.tracks == {}


def test_same_frame_spawn_confirmation_does_not_double_count_hit():
    arena = Arena()
    p1 = np.array((1000.0, 1200.0, 900.0))
    arena.set(1, p1)
    tracker = MultiPersonTracker()
    tracker.step(7, arena.frame({"A": [1], "B": [1]}), arena.project, arena.triangulate)
    tid = tid_at(tracker, p1)

    tracker.update(tid, p1 + (1, 0, 0), 7)

    assert tracker.tracks[tid].hits == 1
    np.testing.assert_allclose(tracker.tracks[tid].pelvis_mm, p1 + (1, 0, 0))


def test_motion_keeps_ids_and_candidate_claims_one_to_one():
    arena = Arena()
    arena.set(1, (1000, 1200, 900))
    arena.set(2, (4000, 3200, 950))
    tracker = MultiPersonTracker()
    tracker.step(0, arena.frame({"A": [1, 2], "B": [1, 2]}), arena.project, arena.triangulate)
    tids = {pid: tid_at(tracker, pos) for pid, pos in arena.people.items()}

    for frame_idx in range(1, 6):
        arena.people[1] += (40, 30, 0)
        arena.people[2] += (-35, 25, 0)
        order = {"A": [2, 1], "B": [1, 2]} if frame_idx % 2 else {"A": [1, 2], "B": [2, 1]}
        assignments = tracker.step(
            frame_idx, arena.frame(order), arena.project, arena.triangulate
        )
        for pid, tid in tids.items():
            expected = {cam: pids.index(pid) for cam, pids in order.items()}
            assert assignments[tid] == expected
            tracker.update(tid, arena.people[pid], frame_idx)


def test_per_camera_assignment_maximizes_number_of_matched_tracks():
    """The closest edge must not consume another track's only candidate."""
    tracker = MultiPersonTracker(max_people=2, gate_px=2.1)
    tracker.tracks = {
        1: PersonTrack(1, np.array((0.0, 0.0, 0.0)), 0),
        2: PersonTrack(2, np.array((2.5, 0.0, 0.0)), 0),
    }
    frame = {"A": [candidate((1.0, 0.0)), candidate((0.0, 2.0))]}

    assignments = tracker.step(
        1,
        frame,
        lambda point, _cam: np.asarray(point)[:2],
        lambda *_: None,
    )

    assert assignments == {1: {"A": 1}, 2: {"A": 0}}


def test_dense_six_person_assignment_finishes_within_live_frame_budget():
    costs = {
        (track_id, candidate_idx): abs(track_id * 2 - candidate_idx) + candidate_idx * 0.01
        for track_id in range(6)
        for candidate_idx in range(16)
    }
    started = time.perf_counter()
    matched = MultiPersonTracker._optimal_camera_assignment(costs)
    elapsed = time.perf_counter() - started

    assert len(matched) == 6
    assert elapsed < 1.0, f"dense assignment took {elapsed:.3f}s"


def test_prune_removes_missed_track_and_ids_are_not_reused():
    arena = Arena()
    p1 = np.array((1000.0, 1200.0, 900.0))
    p2 = np.array((4000.0, 3200.0, 950.0))
    arena.set(1, p1)
    arena.set(2, p2)
    tracker = MultiPersonTracker(max_missed_frames=2)
    tracker.step(0, arena.frame({"A": [1, 2], "B": [1, 2]}), arena.project, arena.triangulate)
    live_tid = tid_at(tracker, p1)
    old_tid = tid_at(tracker, p2)

    assert tracker.prune(2) == []
    tracker.update(live_tid, p1, 2)
    assert tracker.prune(3) == [old_tid]

    arena.set(3, (5200, 500, 1000))
    tracker.step(4, arena.frame({"A": [1, 3], "B": [1, 3]}), arena.project, arena.triangulate)
    assert old_tid not in tracker.tracks
    assert max(tracker.tracks) > old_tid


def test_expired_track_cannot_revive_when_person_returns_on_expiry_frame():
    arena = Arena()
    p1 = np.array((1000.0, 1200.0, 900.0))
    arena.set(1, p1)
    tracker = MultiPersonTracker(max_missed_frames=2)
    tracker.step(0, arena.frame({"A": [1], "B": [1]}), arena.project, arena.triangulate)
    old_tid = tid_at(tracker, p1)

    assignments = tracker.step(
        3, arena.frame({"A": [1], "B": [1]}), arena.project, arena.triangulate
    )

    assert old_tid not in tracker.tracks
    assert set(assignments) == {old_tid + 1}


def test_invalid_constructor_values_fail_fast():
    for kwargs in (
        {"max_people": 0},
        {"max_people": 9},
        {"gate_px": -1},
        {"spawn_reproj_px": -1},
        {"min_separation_mm": 0},
        {"max_missed_frames": -1},
    ):
        try:
            MultiPersonTracker(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {kwargs}")
