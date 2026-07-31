# Remote task: in-domain ball dataset from the altai clips

Fully remote (laptop + browser + free Colab GPU). Attacks the one software
weakness that survived the 2026-07-02 tuning: per-camera detection of the
**motion-blurred ball**. This is the highest-value hands-on technical task
you can do away from the lab.

Source: `garage_lab_combined/test_clips/altai_dataset_20260701_125836/`
= 3 clips × 6 cameras × 511 frames @ 1280×720/30fps (~9,200 frames).

---

## Will it actually help? (honest scope)

**YES for per-camera recall on blur/clutter.** The current model
(`yolo26m-672`, "dataset-main", generic) has never seen this arena's
lighting, blur, climbing-wall/AprilTag/cone clutter, or your specific ball.
Fine-tuning on a few hundred in-domain frames is the textbook fix and will
raise detection rate on exactly the frames that fail today.

**NO, it will not fully fix fast-bounce 3D tracking.** Your own 2026-04-20
analysis proved the bounce gap is *partly structural*: at the bounce instant
only one camera reliably sees the ball; the others have it outside the
frustum or occluded, and no label fixes "the ball isn't in the frame." That
part needs the GigE global-shutter + hardware-sync upgrade (global shutter
also erases most of the blur you're about to label).

**So frame it as:** biggest software win still on the table + perfect remote
task + the labeling pipeline and clutter-negatives transfer to the GigE
cameras later. The blur-specific labels lose value once you have global
shutter — but you need the model working NOW for the demo/pilot, and the
arena/clutter learning is permanent.

---

## The one rule that matters most

**A blurred ball is a STREAK, not a circle. Box the WHOLE streak.**

Most people label only crisp round balls and skip the smears — which trains
the model to ignore the exact frames you care about. Do the opposite:
- Draw the bbox around the full motion-blur ellipse/smear, edge to edge.
- Label faint, partially-occluded, edge-of-frame, and near-the-body balls.
- If you can tell it's the ball, label it. If YOU can't tell, skip it.

Your logs already measured these streaks: aspect ratio 1.5–3.3 at speed.
Teaching the box to cover that aspect range is the entire point.

---

## Frame selection (don't label 9,200 frames)

Target **~400–800 labeled images** for a fine-tune (not from scratch).
Bias hard toward the informative frames:
- Prioritize frames where the ball is MOVING (toss, throw, bounce) — that is
  where the blur lives and where the model fails.
- Label the SAME moment across all 6 cameras — 6 blur signatures of one
  event, all different, all valuable.
- Include ~15–20% "hard-negative" frames: climbing wall, cones, AprilTags,
  shoes visible, NO ball present, labeled with zero boxes. This is what
  kills the false positives your audit flagged (cones/markers/body-as-ball).

Two ways to get frames in:
1. Roboflow ingests `.avi`/`.mp4` directly and samples frames (set ~2–4 fps).
   Simplest, all in-browser.
2. Extract locally, upload images:
   `ffmpeg -i camUsb02_1080P.avi -vf fps=3 out_%04d.jpg`

---

## Roboflow project setup

- Project type: **Object Detection**. Single class: `ball`.
- Upload frames; if you sample video, dedupe near-identical frames.
- **Split before augmenting**, and split by CLIP/moment, not randomly:
  put one whole clip (all 6 cams) in validation. Random split leaks
  near-identical frames across train/val and inflates mAP into a lie.
- Annotate with the streak rule above.

### Augmentation (Roboflow) — use these, avoid those
Use (physically realistic for this rig):
- **Motion blur** (Roboflow has it) — directly multiplies your blur examples.
- Brightness/exposure ±15% (the greenish garage lighting varies).
- Slight scale/crop (ball size varies with distance).
- Slight blur/noise.

Avoid (breaks realism or geometry):
- Vertical flip, large rotation (the arena has a fixed up; a ball is
  rotation-symmetric but the CLUTTER context isn't — over-rotation teaches
  nothing useful and can hurt).
- Heavy mosaic/cutout that fragments the tiny ball.
- Aim for ~2–3× augmented multiplier, not 10×.

---

## Train remotely (free GPU), validate on laptop

1. In Roboflow: **Export → YOLOv8 (PyTorch TXT)**. Get the download
   snippet / dataset version.
2. **Google Colab (free T4)** — fine-tune from the current weights, not
   from scratch:
   ```
   from ultralytics import YOLO
   m = YOLO("yolo26m-672.pt")          # upload your current .pt as the base
   m.train(data="data.yaml", epochs=60, imgsz=672, batch=16,
           patience=15, degrees=0, fliplr=0.0)  # keep aug physically sane
   ```
   (You are away from the 2080 Ti; Colab/Kaggle/any cloud T4 does this in
   ~30–60 min. Do NOT train from scratch — fine-tune the existing model.)
3. Download `best.pt`. On your laptop (CPU is fine for a few hundred val
   images) sanity-check detection rate vs the old model on the held-out clip:
   ```
   YOLO("best.pt")(val_images, conf=0.25, imgsz=672)
   ```
   Compare recall on the blurry frames specifically.

**TRT export waits for home** — the `.engine` build needs the 2080 Ti, and
per `.claude/rules/perf.md` you rebuild `.onnx`+`.engine` from scratch at the
locked imgsz (ball 672) with `--yolo-batch 6`, verified on a REAL frame vs
the `.pt`. The `.pt` is enough to prove the dataset worked.

---

## Acceptance (how you know it worked)

Run the in-repo offline analyzer at home on a recorded bounce/fast clip:
`Parallel_working/scripts/ball_detection_analyzer.py --mosaic <...>` — it
sweeps conf and reports per-cam detection rate. The new model should raise
per-camera rate on fast/bounce frames vs the 2026-04-20 baseline
(slow 65%, fast 46→52%, bounce 23→33%). If per-cam recall climbs and the
cone/AprilTag false positives drop, the dataset did its job.

---

## Optional stretch (same clips, if you want more)

- **Prone-pose fine-tune for YOLO-Pose.** The floor/push-up failures are
  partly that YOLO11m-pose rarely saw prone people. You can label keypoints
  on the floor-pose frames (Roboflow supports keypoint projects) and
  fine-tune the pose model the same way. Much more tedious than boxes
  (17 keypoints/person) — only if boxes are done and you have appetite.
- **Curate a clutter-negative pack** you keep forever: the climbing wall,
  cones, tags, cables with no ball. Reusable for every future ball model,
  including the GigE re-train.
