# A5 — RTMO vs YOLO11m-pose on the 6-camera rig

**Question.** `yolo11m-pose` is the one commercially blocked model on the academy
drill product's critical path. Can RTMO replace it?

**Measured 2026-08-04** on the current 6-USB rig, not on the retired 4-camera
April sequences. Raw results: `Parallel_working/output/rtmo_eval/`.

---

## Why the drill product needs exactly one clean model

Of the four models the registry marks `blocked`, only the pose model is on the
drill path:

| model | blocker | on the drill path? |
|---|---|---|
| `pose_yolo11m_trt` | Ultralytics AGPL (code layer) | **yes** |
| `ball_yolo26m_672_trt` | Ultralytics AGPL (code layer) | no — the drill profile runs `--no-track-ball` (`run_live_usb6_mirrored_skeleton.sh:32`), so the detector is never loaded (`ball_needed` gate, `live_4cam_arena_view_parallel.py:3754`) |
| `face_detect_yunet_2023mar` | WIDER FACE CC BY-NC-ND (data layer) | optional by design, and already prohibited for academy athletes until D1/D2 |
| `face_recognize_sface_2021dec` | CASIA/VGGFace2/MS-Celeb-1M (data layer) | same |

SMPL is also off for drills (the wrapper appends `--no-avatar-body
--no-avatar-markers`). So a clean pose backend is close to sufficient for that
product — which is more than the roadmap claimed for A5.

## Licence: clean, verified from the artifact rather than a table

The published `rtmo-*_coco-640x640` **metafile is wrong**: it lists
`Metadata: Training Data: CrowdPose` and reports AP under a `CrowdPose` heading.
Those AP values (0.673 / 0.709 / 0.724 for s/m/l) are RTMO's published **COCO**
numbers, and the folder is `rtmo/coco/`. An audit that trusts the metafile would
reject a clean model; one that trusts the config alone would be relying on a file
that need not describe the published weights.

Settled by reading the **checkpoint's own embedded training config**
(`meta['cfg']` inside the `.pth`):

* `experiment_name: m_coco_20231018_173858`, epoch 600
* `CocoDataset` ×4, `person_keypoints_train2017.json` ×2
* `CrowdPoseDataset` ×0, `crowdpose` ×0
* backbone init `yolox_m_8x8_300e_coco` → MMDetection (Apache-2.0) → COCO
* `dataset_meta: coco`, 17 keypoints
* the three `aic` substring hits are `Mosaic` augmentation, and the project's own
  `non_commercial_markers()` correctly returns **NONE** — the word-boundary rule
  in `models/registry.py` was written for exactly this false positive

Chain: MMPose Apache-2.0 → MMDetection Apache-2.0 → YOLOX Apache-2.0 → COCO
CC-BY-4.0. **Clean end to end.**

## Detection — RTMO is equal or better, including on the worst camera

Full clips, 6 cameras, every second frame (30 fps clip → the rig's ~15 Hz).

`altai_sync_002`, 252 frames × 6 cameras:

| camera | rtmo-s | rtmo-m | yolo11m-pose |
|---|---|---|---|
| camUsb01_C920 | 100% | 100% | 99% |
| camUsb02_1080P | 100% | 99% | 100% |
| camUsb03_C920 | 95% | 97% | 94% |
| camUsb04_1080P | 100% | 100% | 100% |
| camUsb05_1080P | 100% | 100% | 100% |
| **camUsb06_1080P** | **95%** | **91%** | **82%** |

`altai_sync_003`, 248 frames × 6 cameras: rtmo-s **94.7%** overall vs yolo-pose
**92.6%**, with camUsb01 88% → 99% in RTMO's favour.

camUsb06 is the hard view — the athlete is cropped at the frame edge. A pose
backend that holds 95% there instead of 82% directly raises the camera count
entering triangulation, which is the quantity `robust_triangulate_joint` needs
most.

## 3D jitter — RTMO is consistently noisier, and this is the cost

Same ablation metric as the archived April runs (frame-to-frame displacement of
triangulated joints), so the comparison is like-for-like within a clip. Both
backends run through the identical triangulation path.

| clip | backend | jitter @ EMA 0.25 | P95 | raw (no EMA) |
|---|---|---|---|---|
| sync_002 | yolo11m-pose | **66.8 mm** | **173.8** | **130.0** |
| sync_002 | rtmo-m | 72.8 mm (+9%) | 181.4 | 167.8 (+29%) |
| sync_002 | rtmo-s | 77.6 mm (+16%) | 201.3 | 202.7 (+56%) |
| sync_003 | yolo11m-pose | **77.6 mm** | **166.2** | **142.6** |
| sync_003 | rtmo-s | 84.8 mm (+9%) | 187.6 | 188.0 (+32%) |

Reproduced on two independent clips, same direction both times. RTMO finds the
person more often but places the keypoints less precisely frame to frame; the
biggest 2D disagreements are ankles and knees (median 7–13 px, P95 47–71 px),
which are also the joints the L/R split machinery already fights over.

**Not an accuracy verdict.** Jitter is repeatability, and 2D agreement between
two models is symmetric — neither number says which model is *closer to the
truth*. There is still no end-to-end pose ground truth (blocker 4), so "noisier"
is measured and "worse" is not established.

## Latency — RTMO-s fits the drill profile in plain PyTorch

Best-of-3 on real 6-camera frames, `.pt` vs `.pt` (RTMO has no engine yet, so
comparing it against the 6.2 ms TRT engine would measure the export, not the
model):

| backend | params | batch 1 | batch 6 | img/s at batch 6 |
|---|---|---|---|---|
| yolo11m-pose | 20.9 M | 12.2 ms | **7.8 ms** | 128 |
| rtmo-s | 9.9 M | 19.7 ms | 13.0 ms | 77 |
| rtmo-m | 22.5 M | 23.0 ms | 16.2 ms | 62 |

Against the rig's real budget:

* **drill profile — 6 cameras × 10 fps = 60 img/s:** rtmo-s passes with ~28%
  headroom, rtmo-m is borderline.
* **15 fps target — 90 img/s:** only YOLO-pose passes.

Two measurement notes worth keeping. `mmpose.apis.inference_bottomup` rebuilds
`Compose(pipeline)` on every call and takes one image, so using it in a loop
measures the wrapper: RTMO-m read 22.5 ms/image that way versus 16.2 ms with the
pipeline cached and a real batch. And holding three models resident OOMs the
11 GB card at batch 6 — benchmark one backend per process.

## Verdict

**RTMO-s is a viable licence-clean replacement for the drill product at its
current 10 fps profile, at a measured cost of ~9–16% more post-EMA jitter.** It
needs no TensorRT work to get there, which was the assumed prerequisite.

Do not swap it in blind. Three things stand between this and production:

1. **Run it through the real chain.** This ablation uses bare
   `triangulate_multi`; production adds `robust_triangulate_joint`
   reprojection rejection, the L/R split, EMA, KF and the display clamp. More
   detections plus per-joint outlier rejection may absorb most of the extra
   noise — untested either way.
2. **Check `balance` specifically.** It reports pelvis sway in mm, so a noisier
   backend inflates the one metric with the least headroom. Its 2026-08-01
   session already needed a plausibility gate.
3. **Viewer integration is small but real:** `--pose-backend` currently accepts
   `{mmpose, yolopose}` and dispatches at three places
   (`live_4cam_arena_view_parallel.py:3868/3870/4379`). The batched RTMO wrapper
   already exists in `ablation_ema_adaptive.py:init_rtmo/run_rtmo_frame`.

TensorRT stays optional and is an optimisation, not a blocker: it needs mmdeploy
(not installed), and the project's engine rules then apply unchanged — export
`dynamic=True`, profile batch = camera count, inference imgsz locked to export
imgsz, verified on real frames against the `.pt`.

## Reproduce

```bash
# licence chain, from the checkpoint itself
./venv/bin/python -c "
import torch; ck=torch.load('models/pose/rtmo-m_coco.pth', map_location='cpu')
print(ck['meta']['experiment_name']); print(ck['meta']['cfg'])"

# detection + 3D jitter, 6 cameras
./venv/bin/python Parallel_working/scripts/ablation_ema_adaptive.py \
  --sequence garage_lab_combined/test_clips/altai_dataset_20260701_125836/altai_sync_002 \
  --cam-order camUsb01_C920,camUsb02_1080P,camUsb03_C920,camUsb04_1080P,camUsb05_1080P,camUsb06_1080P \
  --frame-step 2 \
  --intrinsics-dir garage_lab_combined/cal/intrinsics_usb6_1280x720 \
  --extrinsics garage_lab_combined/cal/extrinsics_usb6/extrinsics_usb6.json \
  --pose-backend rtmo --rtmo-size s \
  --output Parallel_working/output/rtmo_eval/sync002_rtmo_s.json

# latency + 2D agreement (one backend pair per process — three models OOM the card)
./venv/bin/python Parallel_working/scripts/bench_rtmo_vs_yolopose.py \
  --sequence <dir of per-camera frame_*.jpg> --rtmo s --batches 1,6
```
