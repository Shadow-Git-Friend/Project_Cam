#!/usr/bin/env python3
"""Roadmap A5: is RTMO-m a usable replacement for YOLO11m-pose?

Why this exists: `yolo11m-pose` is the ONE commercially blocked model on the
academy drill product's critical path (the drill profile already runs with
`--no-track-ball`, Face ID is optional, and the SMPL capsule is off for drills),
so a clean pose backend is very nearly sufficient to make that product sellable.
RTMO's licence chain was verified from the checkpoint's own embedded training
config — COCO only, YOLOX-COCO backbone init, zero CrowdPose — so what remains is
whether it is fast enough and accurate enough on THIS rig.

The comparison is deliberately PyTorch-vs-PyTorch. The current engine is TRT
(6.2 ms) and RTMO has no engine yet (mmdeploy is not installed), so comparing
those two numbers would say more about the export than about the model. Both
models are therefore measured as `.pt` on the same real frames.

Measures, per model:
  * detections on real arena frames (never blank frames — a blank frame yields
    zero detections at any size and passes trivially)
  * per-image latency at batch 1 and at the rig's real batch (4 or 6)
  * pixel agreement between the two backends on the same frame, which is what
    decides whether the downstream 3D chain would even notice a swap

Usage:
  ./venv/bin/python Parallel_working/scripts/bench_rtmo_vs_yolopose.py \
      --sequence artifacts_local/outputs/Parallel_working_output/test_sequences/walk_01 \
      --frames 40 --out Parallel_working/output/rtmo_eval/walk_01_latency.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
RTMO_CFG = (REPO / "venv/lib/python3.10/site-packages/mmpose/.mim/configs/"
            "body_2d_keypoint/rtmo/coco/rtmo-m_16xb16-600e_coco-640x640.py")
RTMO_CKPT = REPO / "models/pose/rtmo-m_coco.pth"

#: COCO-17 order, shared by both backends, so keypoints are directly comparable.
COCO_17 = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]


def load_frames(sequence: Path, count: int, stride: int = 4):
    """Real arena frames, one list per camera, taken from the middle of the clip.

    The middle matters: the first frames of a recording often have the athlete
    still walking into view, and measuring detection rate on empty frames says
    nothing about the model.
    """
    cameras = sorted(d.name for d in sequence.iterdir() if d.is_dir())
    frames = {}
    for camera in cameras:
        names = sorted((sequence / camera).glob("frame_*.jpg"))
        if not names:
            continue
        start = max(0, len(names) // 3)
        picked = names[start::stride][:count]
        frames[camera] = [cv2.imread(str(p)) for p in picked]
    return frames


# --------------------------------------------------------------------- models

class RtmoBackend:
    """RTMO through mmpose, with the test pipeline built ONCE and a real batch.

    `mmpose.apis.inference_bottomup` is a single-image convenience wrapper that
    also reconstructs `Compose(pipeline)` on every call, so using it in a loop
    measures neither batching nor the model. It stays available as
    ``mode="apis"`` because that is the number a reader would get from the
    documented API, and the difference between the two is worth showing.
    """

    licence = "clear: Apache-2.0 code + COCO-only weights"

    def __init__(self, config=RTMO_CFG, checkpoint=RTMO_CKPT, device="cuda:0",
                 score_thr=0.3, mode="batched", label="rtmo-m"):
        from mmengine.dataset import pseudo_collate
        from mmpose.apis import init_model

        self.model = init_model(str(config), str(checkpoint), device=device)
        self.score_thr = float(score_thr)
        self.device = device
        self.mode = mode
        self.name = f"{label} (mmpose, .pt, {mode})"
        self._collate = pseudo_collate
        self._pipeline = None

    def params_m(self):
        return sum(p.numel() for p in self.model.parameters()) / 1e6

    def pipeline(self):
        if self._pipeline is None:
            from mmengine.dataset import Compose

            self._pipeline = Compose(self.model.cfg.test_dataloader.dataset.pipeline)
        return self._pipeline

    def infer(self, images):
        """[(keypoints(17,2) or None, score)] — the best-scoring person per image."""
        import torch

        if self.mode == "apis":
            from mmpose.apis import inference_bottomup

            return [self._best(inference_bottomup(self.model, image))
                    for image in images]

        pipeline = self.pipeline()
        items = []
        for image in images:
            info = dict(img=image)
            info.update(self.model.dataset_meta)
            items.append(pipeline(info))
        batch = self._collate(items)
        with torch.no_grad():
            results = self.model.test_step(batch)
        return [self._best([sample]) for sample in results]

    def _best(self, samples):
        if not samples:
            return None, 0.0
        pred = samples[0].pred_instances
        scores = np.asarray(getattr(pred, "bbox_scores", []), dtype=np.float64)
        keypoints = np.asarray(pred.keypoints, dtype=np.float64)
        if keypoints.size == 0:
            return None, 0.0
        if scores.size == 0:
            scores = np.ones(len(keypoints))
        best = int(np.argmax(scores))
        if float(scores[best]) < self.score_thr:
            return None, float(scores[best])
        return keypoints[best], float(scores[best])


class YoloPoseBackend:
    name = "yolo11m-pose (ultralytics, .pt)"
    licence = "BLOCKED: Ultralytics AGPL-3.0"

    def __init__(self, weights, device="cuda:0", conf=0.3, imgsz=640):
        from ultralytics import YOLO

        self.model = YOLO(str(weights))
        self.device = device
        self.conf = float(conf)
        self.imgsz = int(imgsz)

    def params_m(self):
        return sum(p.numel() for p in self.model.model.parameters()) / 1e6

    def infer(self, images):
        results = self.model.predict(images, device=self.device, conf=self.conf,
                                     imgsz=self.imgsz, verbose=False)
        out = []
        for result in results:
            keypoints = result.keypoints
            boxes = result.boxes
            if keypoints is None or keypoints.xy is None or len(keypoints.xy) == 0:
                out.append((None, 0.0))
                continue
            scores = (boxes.conf.cpu().numpy() if boxes is not None
                      else np.ones(len(keypoints.xy)))
            best = int(np.argmax(scores))
            out.append((keypoints.xy[best].cpu().numpy().astype(np.float64),
                        float(scores[best])))
        return out


# ------------------------------------------------------------------ measuring

def time_batches(backend, images, batch, repeats=3, warmup=2):
    """ms per IMAGE at the given batch size, best of `repeats`."""
    batches = [images[i:i + batch] for i in range(0, len(images), batch)]
    batches = [b for b in batches if len(b) == batch]
    if not batches:
        return None
    for _ in range(warmup):
        backend.infer(batches[0])
    best = None
    for _ in range(repeats):
        start = time.perf_counter()
        for chunk in batches:
            backend.infer(chunk)
        elapsed = time.perf_counter() - start
        per_image = elapsed / (len(batches) * batch) * 1000.0
        best = per_image if best is None else min(best, per_image)
    return best


def detection_rate(backend, frames):
    """Per-camera share of frames where a person was found, plus mean score."""
    per_camera, all_scores = {}, []
    for camera, images in frames.items():
        found, scores = 0, []
        for keypoints, score in backend.infer(images):
            if keypoints is not None:
                found += 1
                scores.append(score)
        per_camera[camera] = {
            "frames": len(images),
            "detected": found,
            "rate": round(found / max(1, len(images)), 4),
            "mean_score": round(float(np.mean(scores)), 4) if scores else None,
        }
        all_scores.extend(scores)
    total = sum(v["frames"] for v in per_camera.values())
    hit = sum(v["detected"] for v in per_camera.values())
    return {
        "per_camera": per_camera,
        "overall_rate": round(hit / max(1, total), 4),
        "mean_score": round(float(np.mean(all_scores)), 4) if all_scores else None,
    }


def keypoint_agreement(a_results, b_results):
    """Per-keypoint pixel distance where BOTH backends found a person.

    This is the number that decides whether a swap is visible downstream: the 3D
    chain consumes 2D keypoints, so a backend that agrees within a few pixels
    cannot move the triangulated skeleton much, whatever its COCO AP says.
    """
    distances = {name: [] for name in COCO_17}
    paired = 0
    for (ka, _sa), (kb, _sb) in zip(a_results, b_results):
        if ka is None or kb is None:
            continue
        paired += 1
        for index, name in enumerate(COCO_17):
            distances[name].append(float(np.linalg.norm(ka[index] - kb[index])))
    summary = {}
    pooled = []
    for name, values in distances.items():
        if not values:
            continue
        pooled.extend(values)
        summary[name] = {
            "median_px": round(float(np.median(values)), 2),
            "p95_px": round(float(np.percentile(values, 95)), 2),
        }
    return {
        "paired_frames": paired,
        "per_keypoint": summary,
        "pooled_median_px": round(float(np.median(pooled)), 2) if pooled else None,
        "pooled_p95_px": round(float(np.percentile(pooled, 95)), 2) if pooled else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--frames", type=int, default=40,
                        help="frames per camera")
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--yolopose-weights",
                        default="models/pose/yolo11m-pose.pt")
    parser.add_argument("--yolopose-imgsz", type=int, default=640,
                        help="must match the engine's export size in production")
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--batches", default="1,4,6")
    parser.add_argument("--rtmo", default="m",
                        help="comma-separated RTMO sizes to measure: s,m,l")
    parser.add_argument("--rtmo-mode", default="batched",
                        choices=("batched", "apis"),
                        help="'batched' = one test_step per batch with a cached "
                             "pipeline; 'apis' = the documented per-image "
                             "inference_bottomup wrapper, for comparison")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    sequence = Path(args.sequence)
    frames = load_frames(sequence, args.frames, args.stride)
    if not frames:
        raise SystemExit(f"no frames under {sequence}")
    flat = [image for images in frames.values() for image in images]
    print(f"[frames] {len(frames)} cameras x {len(next(iter(frames.values())))} "
          f"= {len(flat)} real frames from {sequence.name}")

    report = {"sequence": sequence.name, "frames_per_camera": args.frames,
              "cameras": sorted(frames), "backends": {}}
    results_by_backend = {}

    backends = []
    for variant in [v.strip() for v in args.rtmo.split(",") if v.strip()]:
        checkpoint = REPO / "models/pose" / f"rtmo-{variant}_coco.pth"
        config = (RTMO_CFG.parent /
                  {"s": "rtmo-s_8xb32-600e_coco-640x640.py",
                   "m": "rtmo-m_16xb16-600e_coco-640x640.py",
                   "l": "rtmo-l_16xb16-600e_coco-640x640.py"}[variant])
        if not checkpoint.exists():
            print(f"[warn] {checkpoint} missing — skipping rtmo-{variant}")
            continue
        backends.append(RtmoBackend(config=config, checkpoint=checkpoint,
                                    device=args.device, mode=args.rtmo_mode,
                                    label=f"rtmo-{variant}"))
    weights = Path(args.yolopose_weights)
    if weights.exists():
        backends.append(YoloPoseBackend(weights, device=args.device,
                                        imgsz=args.yolopose_imgsz))
    else:
        print(f"[warn] {weights} missing — RTMO measured alone, no A/B")

    for backend in backends:
        print(f"\n=== {backend.name} ===")
        print(f"    licence: {backend.licence}")
        entry = {"licence": backend.licence,
                 "params_m": round(backend.params_m(), 2), "latency_ms": {}}
        detection = detection_rate(backend, frames)
        entry["detection"] = detection
        print(f"    params: {entry['params_m']} M | detection "
              f"{detection['overall_rate'] * 100:.1f}% "
              f"(mean score {detection['mean_score']})")
        for camera, row in detection["per_camera"].items():
            print(f"      {camera:10s} {row['detected']}/{row['frames']} "
                  f"= {row['rate'] * 100:.1f}%")
        for batch in [int(b) for b in args.batches.split(",") if b.strip()]:
            millis = time_batches(backend, flat, batch)
            if millis is None:
                continue
            entry["latency_ms"][str(batch)] = round(millis, 2)
            print(f"      batch {batch}: {millis:.2f} ms/image "
                  f"({1000.0 / millis:.0f} img/s)")
        report["backends"][backend.name] = entry
        results_by_backend[backend.name] = backend.infer(flat)

    yolo = next((n for n in results_by_backend if "yolo" in n), None)
    rtmo = next((n for n in results_by_backend if "rtmo" in n), None)
    if yolo and rtmo:
        report["agreement"] = keypoint_agreement(results_by_backend[rtmo],
                                                 results_by_backend[yolo])
        agreement = report["agreement"]
        print(f"\n=== 2D agreement on {agreement['paired_frames']} paired frames ===")
        print(f"    pooled median {agreement['pooled_median_px']} px, "
              f"p95 {agreement['pooled_p95_px']} px")
        worst = sorted(agreement["per_keypoint"].items(),
                       key=lambda kv: -kv[1]["median_px"])[:5]
        for name, row in worst:
            print(f"      {name:16s} median {row['median_px']:6.2f} px  "
                  f"p95 {row['p95_px']:7.2f} px")

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
