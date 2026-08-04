"""Cross-view association for a small number of people in the live arena.

The tracker deliberately owns no camera geometry.  The live viewer supplies
projection and two-view triangulation callbacks, while this module keeps stable
track IDs and enforces one candidate per camera/person.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

COCO_LEFT_HIP = 11
COCO_RIGHT_HIP = 12
COCO_TORSO = (5, 6, 11, 12)
MAX_TRACKED_PEOPLE = 8


def candidate_anchor_px(
    kpts: np.ndarray,
    scores: np.ndarray,
    min_conf: float = 0.3,
) -> Optional[np.ndarray]:
    """Return a stable 2D pelvis/torso anchor, or ``None`` if unavailable."""
    kpts = np.asarray(kpts, dtype=np.float64)
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    if kpts.ndim != 2 or kpts.shape[0] < 13 or kpts.shape[1] < 2 or len(scores) < 13:
        return None

    def valid(joint: int) -> bool:
        return bool(
            np.isfinite(scores[joint])
            and scores[joint] >= min_conf
            and np.isfinite(kpts[joint, :2]).all()
        )

    if valid(COCO_LEFT_HIP) and valid(COCO_RIGHT_HIP):
        return 0.5 * (kpts[COCO_LEFT_HIP, :2] + kpts[COCO_RIGHT_HIP, :2])
    torso = [kpts[joint, :2] for joint in COCO_TORSO if valid(joint)]
    if len(torso) >= 2:
        return np.mean(np.asarray(torso), axis=0)
    good = [kpts[joint, :2] for joint in range(min(len(scores), len(kpts))) if valid(joint)]
    if len(good) >= 3:
        return np.mean(np.asarray(good), axis=0)
    return None


@dataclass
class PersonTrack:
    tid: int
    pelvis_mm: np.ndarray
    last_seen_frame: int
    hits: int = 1
    name: Optional[str] = None
    name_score: float = 0.0
    color_idx: int = 0
    extras: dict = field(default_factory=dict)


class MultiPersonTracker:
    """Projected-pelvis tracker with optimal 2D matching and coherent spawning."""

    def __init__(
        self,
        max_people: int = 4,
        gate_px: float = 150.0,
        min_cams_spawn: int = 2,
        spawn_reproj_px: float = 60.0,
        min_separation_mm: float = 400.0,
        max_missed_frames: int = 30,
        anchor_min_conf: float = 0.3,
    ) -> None:
        if not 1 <= int(max_people) <= MAX_TRACKED_PEOPLE:
            raise ValueError(
                f"max_people must be in [1, {MAX_TRACKED_PEOPLE}]"
            )
        if float(gate_px) < 0:
            raise ValueError("gate_px must be >= 0")
        if int(min_cams_spawn) < 2:
            raise ValueError("min_cams_spawn must be >= 2")
        if float(spawn_reproj_px) < 0:
            raise ValueError("spawn_reproj_px must be >= 0")
        if float(min_separation_mm) <= 0:
            raise ValueError("min_separation_mm must be > 0")
        if int(max_missed_frames) < 0:
            raise ValueError("max_missed_frames must be >= 0")
        if not 0.0 <= float(anchor_min_conf) <= 1.0:
            raise ValueError("anchor_min_conf must be in [0, 1]")

        self.max_people = int(max_people)
        self.gate_px = float(gate_px)
        self.min_cams_spawn = int(min_cams_spawn)
        self.spawn_reproj_px = float(spawn_reproj_px)
        self.min_separation_mm = float(min_separation_mm)
        self.max_missed_frames = int(max_missed_frames)
        self.anchor_min_conf = float(anchor_min_conf)
        self.tracks: Dict[int, PersonTrack] = {}
        self.last_pruned_ids: List[int] = []
        self._next_tid = 1
        self._next_color = 0

    def step(
        self,
        frame_idx: int,
        per_cam_candidates: Dict[str, List[dict]],
        project_fn: Callable[[np.ndarray, str], Optional[Tuple[float, float]]],
        triangulate_fn: Callable[..., Optional[Tuple[np.ndarray, float]]],
    ) -> Dict[int, Dict[str, int]]:
        """Associate candidates and return ``{track_id: {camera: index}}``."""
        frame_idx = int(frame_idx)
        # Expiry happens before association so a person returning outside the
        # grace window receives a fresh ID instead of reviving stale identity.
        self.last_pruned_ids = self.prune(frame_idx)

        anchors: Dict[str, List[Optional[np.ndarray]]] = {
            cam: [
                candidate_anchor_px(c["kpts"], c["scores"], self.anchor_min_conf)
                for c in candidates
            ]
            for cam, candidates in per_cam_candidates.items()
        }

        pair_cache = {}

        def pair_for(cam_a, idx_a, cam_b, idx_b):
            """Triangulate one candidate pair at most once in this frame."""
            left = (cam_a, int(idx_a))
            right = (cam_b, int(idx_b))
            if right < left:
                left, right = right, left
            key = (left, right)
            if key not in pair_cache:
                pair_cache[key] = self._valid_pair(
                    left[0],
                    anchors[left[0]][left[1]],
                    right[0],
                    anchors[right[0]][right[1]],
                    triangulate_fn,
                )
            return pair_cache[key]

        camera_costs: Dict[str, Dict[Tuple[int, int], float]] = {
            cam: {} for cam in anchors
        }
        for tid, track in self.tracks.items():
            for cam, cam_anchors in anchors.items():
                projected = project_fn(track.pelvis_mm, cam)
                if projected is None:
                    continue
                projected = np.asarray(projected, dtype=np.float64).reshape(-1)
                if len(projected) < 2 or not np.isfinite(projected[:2]).all():
                    continue
                for candidate_idx, anchor in enumerate(cam_anchors):
                    if anchor is None:
                        continue
                    distance = float(np.linalg.norm(anchor - projected[:2]))
                    if distance <= self.gate_px:
                        camera_costs[cam][(tid, candidate_idx)] = distance

        assignments: Dict[int, Dict[str, int]] = {}
        costs: Dict[Tuple[int, str], float] = {}
        taken = set()
        for cam in sorted(anchors):
            matched = self._optimal_camera_assignment(camera_costs[cam])
            for tid, candidate_idx in matched.items():
                assignments.setdefault(tid, {})[cam] = candidate_idx
                costs[(tid, cam)] = camera_costs[cam][(tid, candidate_idx)]
                taken.add((cam, candidate_idx))

        # Remove cross-camera combinations that do not form a coherent 3D
        # hypothesis.  A single best 2D claim may remain for an occluded track,
        # but it cannot be triangulated into a chimera by the caller.
        for tid, per_cam in list(assignments.items()):
            kept = self._largest_coherent_subset(
                tid, per_cam, costs, pair_for
            )
            for cam, candidate_idx in per_cam.items():
                if cam not in kept:
                    taken.discard((cam, candidate_idx))
            if kept:
                assignments[tid] = kept
            else:
                del assignments[tid]

        if len(self.tracks) < self.max_people:
            self._spawn(frame_idx, anchors, taken, pair_for, assignments)
        return assignments

    @staticmethod
    def _optimal_camera_assignment(costs: Dict[Tuple[int, int], float]) -> Dict[int, int]:
        """Maximum-cardinality, then minimum-cost, matching for one camera.

        Arena mode tracks at most a handful of people, so bitmask dynamic
        programming is fast and avoids adding a SciPy dependency.
        """
        if not costs:
            return {}
        candidates_by_tid: Dict[int, List[Tuple[int, float]]] = {}
        for (tid, candidate_idx), cost in costs.items():
            candidates_by_tid.setdefault(tid, []).append((candidate_idx, cost))
        tids = sorted(candidates_by_tid, key=lambda tid: (len(candidates_by_tid[tid]), tid))
        for tid in tids:
            candidates_by_tid[tid].sort(key=lambda item: (item[1], item[0]))

        tid_bits = {tid: 1 << bit for bit, tid in enumerate(tids)}
        # Scan candidates and keep the cheapest mapping for each matched-track
        # bitmask. Complexity is O(candidates * 2**tracks * tracks), bounded by
        # track count rather than candidate count (important when YOLO emits
        # many false candidates in one frame).
        states = {0: (0.0, ())}
        for candidate_idx in sorted({idx for _tid, idx in costs}):
            next_states = dict(states)  # candidate may remain unused
            for mask, (total_cost, mapping) in states.items():
                for tid in tids:
                    bit = tid_bits[tid]
                    edge = costs.get((tid, candidate_idx))
                    if mask & bit or edge is None:
                        continue
                    new_mask = mask | bit
                    proposal = (
                        total_cost + edge,
                        tuple(sorted(mapping + ((tid, candidate_idx),))),
                    )
                    current = next_states.get(new_mask)
                    if (
                        current is None
                        or proposal[0] < current[0] - 1e-12
                        or (
                            abs(proposal[0] - current[0]) <= 1e-12
                            and proposal[1] < current[1]
                        )
                    ):
                        next_states[new_mask] = proposal
            states = next_states

        best_mask, (_best_cost, best_mapping) = min(
            states.items(),
            key=lambda item: (
                -item[0].bit_count(),
                item[1][0],
                item[1][1],
            ),
        )
        del best_mask
        return dict(best_mapping)

    def update(self, tid: int, pelvis_mm, frame_idx: int) -> None:
        """Confirm a track with a triangulated pelvis.

        A spawn already counts as the first hit.  A same-frame refinement may
        replace its seed position but must not count the frame twice.
        """
        track = self.tracks.get(int(tid))
        if track is None:
            return
        pelvis = np.asarray(pelvis_mm, dtype=np.float64).reshape(3)
        frame_idx = int(frame_idx)
        if not np.isfinite(pelvis).all() or frame_idx < track.last_seen_frame:
            return
        if frame_idx > track.last_seen_frame:
            track.hits += 1
        track.pelvis_mm = pelvis
        track.last_seen_frame = frame_idx

    def prune(self, frame_idx: int) -> List[int]:
        """Remove expired tracks and return their IDs."""
        dead = [
            tid
            for tid, track in self.tracks.items()
            if int(frame_idx) - track.last_seen_frame > self.max_missed_frames
        ]
        for tid in dead:
            del self.tracks[tid]
        return dead

    def _valid_pair(self, cam_a, uv_a, cam_b, uv_b, triangulate_fn):
        try:
            result = triangulate_fn(cam_a, uv_a, cam_b, uv_b)
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
            return None
        if result is None:
            return None
        point, error_px = result
        point = np.asarray(point, dtype=np.float64).reshape(3)
        error_px = float(error_px)
        if (
            not np.isfinite(point).all()
            or not np.isfinite(error_px)
            or error_px > self.spawn_reproj_px
        ):
            return None
        return point, error_px

    def _largest_coherent_subset(self, tid, per_cam, costs, pair_for):
        items = sorted(per_cam.items())
        if len(items) <= 1:
            return dict(items)
        merge_radius = 0.5 * self.min_separation_mm
        best = None
        for size in range(len(items), 1, -1):
            for subset in combinations(items, size):
                points = []
                errors = []
                valid = True
                for (cam_a, idx_a), (cam_b, idx_b) in combinations(subset, 2):
                    pair = pair_for(cam_a, idx_a, cam_b, idx_b)
                    if pair is None:
                        valid = False
                        break
                    point, error_px = pair
                    points.append(point)
                    errors.append(error_px)
                if not valid:
                    continue
                center = np.mean(np.asarray(points), axis=0)
                if any(np.linalg.norm(point - center) > merge_radius for point in points):
                    continue
                score = sum(costs[(tid, cam)] for cam, _ in subset) + sum(errors)
                candidate = (score, dict(subset))
                if best is None or candidate[0] < best[0]:
                    best = candidate
            if best is not None:
                return best[1]
        cam, candidate_idx = min(items, key=lambda item: costs[(tid, item[0])])
        return {cam: candidate_idx}

    def _spawn(self, frame_idx, anchors, taken, pair_for, assignments) -> None:
        free = [
            (cam, candidate_idx, anchor)
            for cam in sorted(anchors)
            for candidate_idx, anchor in enumerate(anchors[cam])
            if anchor is not None and (cam, candidate_idx) not in taken
        ]
        pair_seeds = []
        for left, right in combinations(free, 2):
            cam_a, idx_a, _uv_a = left
            cam_b, idx_b, _uv_b = right
            if cam_a == cam_b:
                continue
            pair = pair_for(cam_a, idx_a, cam_b, idx_b)
            if pair is None:
                continue
            point, error_px = pair
            pair_seeds.append(
                {
                    "members": {cam_a: idx_a, cam_b: idx_b},
                    "points": [point],
                    "error": error_px,
                }
            )

        hypotheses = {}
        merge_radius = 0.5 * self.min_separation_mm
        for seed in pair_seeds:
            members = dict(seed["members"])
            points = list(seed["points"])
            total_error = float(seed["error"])
            for cam in sorted(anchors):
                if cam in members:
                    continue
                choices = []
                for candidate_idx, candidate_uv in enumerate(anchors[cam]):
                    if candidate_uv is None or (cam, candidate_idx) in taken:
                        continue
                    candidate_points = []
                    candidate_error = 0.0
                    compatible = True
                    for member_cam, member_idx in members.items():
                        pair = pair_for(member_cam, member_idx, cam, candidate_idx)
                        if pair is None:
                            compatible = False
                            break
                        point, error_px = pair
                        candidate_points.append(point)
                        candidate_error += error_px
                    if not compatible:
                        continue
                    center = np.mean(np.asarray(points + candidate_points), axis=0)
                    if any(
                        np.linalg.norm(point - center) > merge_radius
                        for point in points + candidate_points
                    ):
                        continue
                    choices.append((candidate_error, candidate_idx, candidate_points))
                if choices:
                    error, candidate_idx, candidate_points = min(choices, key=lambda x: x[0])
                    members[cam] = candidate_idx
                    points.extend(candidate_points)
                    total_error += error
            key = tuple(sorted(members.items()))
            center = np.mean(np.asarray(points), axis=0)
            hypothesis = {
                "members": members,
                "point": center,
                "error": total_error,
            }
            previous = hypotheses.get(key)
            if previous is None or hypothesis["error"] < previous["error"]:
                hypotheses[key] = hypothesis

        ordered = sorted(
            hypotheses.values(),
            key=lambda item: (-len(item["members"]), item["error"]),
        )
        for hypothesis in ordered:
            if len(self.tracks) >= self.max_people:
                break
            members = hypothesis["members"]
            if len(members) < self.min_cams_spawn:
                continue
            if any((cam, idx) in taken for cam, idx in members.items()):
                continue
            point = hypothesis["point"]
            if any(
                np.linalg.norm(track.pelvis_mm - point) < self.min_separation_mm
                for track in self.tracks.values()
            ):
                continue
            tid = self._next_tid
            self._next_tid += 1
            self.tracks[tid] = PersonTrack(
                tid=tid,
                pelvis_mm=point.copy(),
                last_seen_frame=int(frame_idx),
                color_idx=self._next_color,
            )
            self._next_color += 1
            assignments[tid] = dict(sorted(members.items()))
            taken.update(members.items())
