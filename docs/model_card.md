# Model Card

## Models in the pipeline

Machine-readable provenance is tracked in
[`configs/models.yaml`](../configs/models.yaml) and exposed by `GET /v1/models`.

| Role | Model | Backend | Commercial use | Notes |
|---|---|---|---|---|
| Ball detection | YOLO26m (`models/ball/yolo26m-672.engine`) | TensorRT FP16, dynamic batch | **blocked** (AGPL) | trained on dataset-main, 100 epochs |
| Pose (primary) | YOLO11m-Pose | TensorRT FP16 / `.pt` | **blocked** (AGPL) | COCO-17, ≈6× faster than MMPose |
| Pose (fallback) | RTMDet-m + RTMPose-m (MMPose) | PyTorch | **blocked** (AI Challenger) | slower; **not** the AGPL escape route — see below |
| Pose (clean target) | RTMO-m (MMPose) | PyTorch, not yet exported | **clear** | one-stage, bottom-up, COCO-only; candidate |
| Face detect / recognize | YuNet + SFace (OpenCV Zoo) | ONNX Runtime | **blocked** (training data) | identification labels only, never authorization |
| Prediction | Constant-velocity 3D Kalman filter | NumPy | n/a (not learned) | tuned PN/MN |

## Licensing (audited 2026-07-30, face models traced to their data 2026-08-03)

Each artifact is audited across **three layers — code, weights, training data —**
recorded per-model in [`configs/models.yaml`](../configs/models.yaml) and exposed
by `GET /v1/models`. The layers routinely disagree, and the third one does not
appear in a repository badge.

**No active model in this pipeline is currently cleared for commercial use.**
That is pinned by `tests/test_model_licensing.py`, so clearing one is a deliberate
edit rather than a drift.

- **Ultralytics (ball + primary pose): AGPL-3.0.** The *data* is fine — the ball
  detector is fine-tuned on our own garage imagery, and YOLO11m-pose uses COCO —
  the framework licence is the obstacle. The ball path is the harder half: it has
  no in-repo permissive alternative. Candidates are RF-DETR detection (Apache-2.0)
  retrained on this dataset, or LibreYOLO (MIT).
- **MMPose / RTMPose was believed to be the AGPL escape and is not.** MMPose code
  is Apache-2.0, but every published RTMPose checkpoint (tiny/s/m/l, *including*
  those named `simcc-coco`) is pretrained on **AI Challenger**, which is
  research-only. Verified in the installed package metafile.
- **RTMO is the verified clean replacement and already ships in the installed
  MMPose.** Read from the config, not the model-zoo table:
  `rtmo-s_8xb32-600e_coco-640x640.py` trains on `CocoDataset` /
  `person_keypoints_train2017` and initialises its backbone from
  `yolox_s_8x8_300e_coco`. Chain: MMPose → MMDetection → YOLOX (all Apache-2.0)
  → COCO (CC-BY-4.0). Use the `coco/` configs only; `crowdpose/` and `body7/` are
  separate, contaminated families. Not yet exported or benchmarked.
- **YuNet / SFace are blocked by their TRAINING DATA, not by their code**
  (verified 2026-08-03 by reading each per-model `LICENSE`, which the repository
  badge does not cover). Both permissive layers are genuinely permissive —
  **YuNet is MIT, SFace is Apache-2.0** — so an auditor who stops at the LICENSE
  clears them by mistake. One layer deeper:
  - YuNet trains on **WIDER FACE = CC BY-NC-ND 4.0**: non-commercial *and*
    no-derivatives, the strictest dataset term in this project. Chain: OpenCV Zoo
    README → `ShiqiYu/libfacedetection.train` → WIDER FACE terms.
  - SFace trains on **CASIA-WebFace, VGGFace2 and MS-Celeb-1M**
    (arXiv:2205.12010) — all research-only, and MS-Celeb-1M was retracted by
    Microsoft in 2019. The Zoo model card names no dataset at all, so the
    provenance had to be traced through the paper.

  This is the third distinct licence blocker in the project (after Ultralytics
  AGPL at the code layer and AI Challenger at the data layer) and the first where
  code *and* weights are clean. Biometric consent, retention and deletion
  obligations apply regardless of the model licence. A commercially clean Face ID
  needs a model whose training data is documented and permissive, or a vendor
  warranty (e.g. an NVIDIA TAO face model marked "ready for commercial use").
- **SMPL** (`--avatar-body`, opt-in) is non-commercial and is excluded from the
  pilot.

## Intended use
Markerless 3D ball/pose tracking in a calibrated indoor arena for predictive
targeting research and athlete movement assessment. **Not** for medical diagnosis
and **not** for autonomous unsafe actuation — firing is human-supervised and
safety-gated.

## Training / evaluation data
Garage-arena imagery and a project ball dataset (see [data_card.md](data_card.md)).
3D accuracy is evaluated against measured millimeter ground-truth points (static
ball and joint-touch protocols).

## Metrics (measured, 4-camera `arena_fixed`)
| Metric | Ball (static) | Joint (touch) |
|---|---|---|
| Mean error | 156.9 mm | 179.0 mm |
| P95 error | 288.3 mm | 243.8 mm |
| Precision (std) | 3.1 mm | 4.4 mm |
| Systematic bias | X+60, Z−104 mm | X+83, Z−125 mm |

Bias is a correctable systematic (linear correction model); precision is
excellent. 6-camera accuracy is **not yet measured** — see
[performance_report.md](performance_report.md).

## Latency (measured, RTX 2080 Ti)
YOLO ball 8.1 ms (TRT FP16) · YOLO-Pose 6.2 ms (TRT FP16) · MMPose 38.5 ms/image ·
cv2 3D renderer ≈2 ms.

## Known failure modes
- **Fast / bouncing ball**: motion blur and frustum geometry — at the bounce
  moment often only one camera sees the ball; resolution (`--ball-imgsz 960`) and
  the single-camera fallback help, camera placement is the real fix.
- **Supine poses**: generic RGB pose models are weaker lying down; left/right leg
  labels can swap (mitigated by the leg-raise identity lock + segment priors).
- **Oblique pose views**: YOLO-Pose detection ~94% vs MMPose ~100%.
- **Kalman on jumps**: constant-velocity model is ~neutral on jump motion.

## Runtime backends / export
Export TensorRT engines with `dynamic=True, batch=N`; static batch=1 engines fail
on batched multi-cam inference. After any `.pt` swap, rebuild the `.engine` from
scratch.

## Regression control
Model or calibration changes must pass the 3D accuracy gate:

```bash
make eval-gate
```

Thresholds live in [`configs/eval_thresholds.yaml`](../configs/eval_thresholds.yaml).
The gate is hardware-free and runs in CI; it is a guard against silently shipping
a worse model/calibration pair.

## Ethical / safety notes
See [safety_boundaries.md](safety_boundaries.md). The API and edge demo cannot
fire the launcher.
