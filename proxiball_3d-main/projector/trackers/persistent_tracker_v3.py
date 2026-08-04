import math
from scipy.optimize import linear_sum_assignment


def box_center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


class PersistentTrackerV3:
    """
    Frame-based multi-ball tracker (ported from pipeline_infer.docx).

    - IoU + distance cost matrix, solved with Hungarian algorithm
    - Jitter suppression: moves smaller than jitter_thresh count as 0 speed
    - Re-ID gate: detections further than reid_gate_px are never matched
    - Tracks survive up to max_missed_frames consecutive missed frames
    - Track IDs are unique and never reused
    """

    def __init__(self, cfg):
        self.jitter_thresh  = cfg.get("jitter_thresh",    5.0)
        self.reid_gate      = cfg.get("reid_gate_px",     150)
        self.max_missed     = cfg.get("max_missed_frames", 20)
        self.tracks         = []
        self.next_id        = 1

    # ── IoU ───────────────────────────────────────────────────────────────────
    @staticmethod
    def iou(a, b):
        xA, yA = max(a[0], b[0]), max(a[1], b[1])
        xB, yB = min(a[2], b[2]), min(a[3], b[3])
        inter  = max(0, xB - xA) * max(0, yB - yA)
        areaA  = (a[2] - a[0]) * (a[3] - a[1])
        areaB  = (b[2] - b[0]) * (b[3] - b[1])
        union  = areaA + areaB - inter
        return inter / union if union > 0 else 0.0

    # ── Cost matrix ───────────────────────────────────────────────────────────
    def _assoc_cost(self, dets, tracks):
        n, m = len(dets), len(tracks)
        C = [[0.0] * m for _ in range(n)]
        for i, d in enumerate(dets):
            dc = box_center(d["bbox"])
            for j, t in enumerate(tracks):
                tc   = t["centroid"]
                dist = math.hypot(dc[0] - tc[0], dc[1] - tc[1])
                iouv = self.iou(d["bbox"], t["bbox"])
                C[i][j] = -(iouv + max(0.0, 1.0 - dist / max(1.0, self.reid_gate)))
        return C

    # ── Update ────────────────────────────────────────────────────────────────
    def update(self, detections):
        if not detections:
            for t in self.tracks:
                t["missed"] += 1
            self.tracks = [t for t in self.tracks if t["missed"] <= self.max_missed]
            return self.tracks

        if not self.tracks:
            for d in detections:
                c = box_center(d["bbox"])
                self.tracks.append({
                    "id":       self.next_id,
                    "bbox":     d["bbox"],
                    "centroid": c,
                    "speed":    0.0,
                    "missed":   0,
                })
                self.next_id += 1
            return self.tracks

        C    = self._assoc_cost(detections, self.tracks)
        rows, cols = linear_sum_assignment(C)
        matched_dets = set()
        matched_trks = set()

        for r, c in zip(rows, cols):
            d    = detections[r]
            t    = self.tracks[c]
            dc   = box_center(d["bbox"])
            tc   = t["centroid"]
            dist = math.hypot(dc[0] - tc[0], dc[1] - tc[1])
            if dist <= self.reid_gate:
                speed = 0.0 if dist <= self.jitter_thresh else dist
                t["bbox"]     = d["bbox"]
                t["centroid"] = dc
                t["speed"]    = speed
                t["missed"]   = 0
                matched_dets.add(r)
                matched_trks.add(c)

        for i, d in enumerate(detections):
            if i not in matched_dets:
                c = box_center(d["bbox"])
                self.tracks.append({
                    "id":       self.next_id,
                    "bbox":     d["bbox"],
                    "centroid": c,
                    "speed":    0.0,
                    "missed":   0,
                })
                self.next_id += 1

        for j in range(len(self.tracks)):
            if j not in matched_trks:
                self.tracks[j]["missed"] += 1

        self.tracks = [t for t in self.tracks if t["missed"] <= self.max_missed]
        return self.tracks
