# Footbonaut Master Implementation To-Do List

This document comprehensively outlines the immediate execution priorities for `Footbonaut_v6_frozen`. It combines the required architecture upgrades across the 2D Tracker (ROI Recovery) and the larger 3D System (Metrics, Safety, & Scalability Roadmap).

---

## PART 1: ROI Tracking Implementation Tasks

### Core Strategy 
**Goal**: Implement ROI (Region of Interest) patching without losing multi-ball detection.
**Concept**: Full-frame YOLO handles discovery implicitly. ROI executes locally as a recovery/refinement step solely when a track is missed, uncertainty shifts, or targets travel extremely fast.

### [ ] Step 1: Implement Discovery Pass
* [ ] Implement `discovery_every_frames` override inside the core `run_detection` logic.
* [ ] Verify conceptually that full-frame passes execute periodically regardless of heavy generic skipping algorithms.

### [ ] Step 2: Add Dynamic ROI Box Builder Function
* [ ] Implement builder function: `build_roi(track, W, H)` returning localized ROI bounding coordinates.
* [ ] Utilize Track momentum mapping logic:
  * `pred_cx = cx + vx * roi_predict_frames`
  * `pred_cy = cy + vy * roi_predict_frames`
  * `scale = roi_base_scale + (roi_speed_scale * min(s, s_cap)) + (roi_missed_scale * track.missed)`
  * Extract: `ROI_width = bw * scale`, `ROI_height = bh * scale`
* [ ] Enforce boundaries `roi_x1 = clamp(pred_cx - ROI_width/2, 0, W-1)` wrapping up to frame limits.
* [ ] Block sub-macro elements natively: `roi_min_size_px` >= 128.
* [ ] Block full-frame bleed over-reach: `roi_max_fraction_of_frame` <= 0.4.
* [ ] Output/Visualize test ROI geometries via cv2 rect grids explicitly mapping visual debugging elements.

### [ ] Step 3: Run YOLO on ROI Regions (For "Lost" Tracks)
* [ ] Trigger Check: Map `if track.missed >= 1:` (or `speed >= target threshold`), execute standard YOLO internally on bounded ROI crops.
* [ ] Target Execution: Extract `roi_img = frame[roi_y1:roi_y2, roi_x1:roi_x2]` and execute localized `model.predict(roi_img, conf=roi_conf)`.
* [ ] Reprojection: Reproject array predictions natively into full-frame mapping logic (`full_x1 = roi_x1 + det_x1`). 
* [ ] De-Duplication Merge: Check `dets_roi` against `dets_full`. Sweep `IoU > merge_iou_thresh`. For equivalent tracks, enforce the highest baseline confidence. 
* [ ] Update: Feed `combined_dets` cleanly into the `tracker.update(combined_dets)` function. 

### [ ] Step 3.5 (CRITICAL): TensorRT Dimensionality & Padding
* [ ] **The TensorRT Batch Constraint**: TensorRT `.engine` models are strictly optimized for fixed memory allocations (e.g., $832 \times 832$). Dynamic crop geometries will crash GPU pipeline execution.
* [ ] **Padding Solution**: Modify Python logic to instantly pad the dynamic $160 \times 160$ ROI crop arrays with zero-byte pixels (pure black bounds) out to the fixed $(832, 832)$ dimensionality before passing the tensor bounding into Inference.
* [ ] **Secondary Engine Solution**: Export an entirely independent secondary `.engine` explicitly compiled at a smaller fixed ROI constraint (e.g., $256 \times 256$) strictly designated for rescue sequences. 

### [ ] Step 4: Budget Execution Guardrails
* [ ] Add compute safety caps natively. Do *not* run ROI blocks exceeding limits (e.g., `max_rois_per_frame = 3`).
* [ ] Filter target arrays proactively ranking ID queues descending by `missed` status, followed by physical `speed`.

### [ ] Step 5: Test Baseline Configuration (Simple Recommended State)
* [ ] Set `detect_every` to `3`.
* [ ] Set `discovery_every_frames` strictly to `15`.
* [ ] Set `roi_trigger_missed` strictly to `1`.
* [ ] Implement ROI max size `bbox_width * 3`, enlarging aggressively against velocity arrays.

### [ ] Step 6: ROI Validation Checklist
* [ ] **Multi-Ball Discovery**: Ensure discovery sweeps natively detect 2nd targets while Tracker 1 runs localized ROIs. 
* [ ] **Missed Recoveries**: Simulate blur conditions. Certify ROI predictions quickly intercept coasting target trajectories natively mapping lost sequences accurately.
* [ ] **Zero-Duplicates**: Actively evaluate duplicate objects dropping identically. If duplicate sequences crash IDs, structurally lift `merge_iou_thresh` boundaries.
* [ ] **FPS Thresholds Check**: Monitor standard overheads evaluating if ROI iterations dynamically stall main threaded throughput.

---

## PART 2: Core System Target Upgrades & Roadmap (`v6_frozen`)

### [ ] Phase A: Data & Outputs Formatting
* [ ] 0. Dynamically save target video files producing explicit differing names natively avoiding loop overwriting. 
* [ ] 1. Generate core variable metric extractions routing perfectly towards JSON schemas:
    - [ ] 2D ball speed from camA and camB (px/frame)
    - [ ] 3D ball speed ($m/s$)
    - [ ] 2D ball positions mapped to Cam A and B ($px$)
    - [ ] 3D ball array position vector ($x, y, z$) mapping ($m$)
    - [ ] 2D acceleration derived independently (px/frame²)
    - [ ] 3D ball temporal acceleration vector ($m/s^2$)
* [ ] 12. Structure standard `JSON metadata output write` files enforcing structured variables: `[3d position, velocity, acceleration, timestamp, ball id]`.

### [ ] Phase B: Rendering & Visualization Execution
* [ ] 3. Render 3D tracking trails disappearing automatically targeting isolated exactly 2-second decay spans native avoiding visual artifact trails.
* [ ] 11. Refactor grid visualizations cleanly swapping to pure 3D Isometric Field Views producing exactly 10x10 metric arenas (bypassing raw legacy 10x20 parameters). Make the virtual arena topologically visually larger.

### [ ] Phase C: System Optimizations & Hardware Limits
* [ ] 2. Build adaptive frame skipping explicitly dependent directly against measured 3D speed. (If 0m/s: `detect every 3rd frame`. If moving: `detect every frame`). 
* [ ] 13. Disable unreliable 3D direct-prediction arrays, switching fallback confidence solely onto native robust 2D tracking heuristics bridging gaps natively. 
* [ ] 6. Observe output blocks tracing why standard thread structures hard-cap outputs artificially to 50fps. 
* [ ] 7. Experiment structurally tuning varied skip parameters elevating total framerates. 
* [ ] 8. Replace standard buffer arrays switching experimentally onto exact Mutex Semaphore locking parameters.
* [ ] 9. Audit and transition standard script components completely onto asynchronous threaded workloads. 
* [ ] 10. Process localized Tensor workloads routing batch limits natively checking FP16 engine latency optimizations dynamically.

### [ ] Phase D: Production Safety & Freezing Actions
* [ ] **Hard Hardware Interlocks**:
    - [ ] Restrict structural execution pathways preventing Out-Of-Memory (OOM) sequence exceptions dynamically.
    - [ ] Deploy strict watchdogs avoiding overheating thermal spikes native tracing Jetson boards. 
    - [ ] Disallow excessive generic hardware component over-stress mapping target loads consistently. 
    - [ ] Guard specific structural space flooding eliminating legacy MP4 diagnostic sweeps locally resolving device storage caps actively.
    - [ ] Delete strictly temporary cache logic natively.
* [ ] 4. Perform an active audit deleting redundant structural codes + files tracing root folders. 
* [ ] 5. System Freeze protocol establishing `Footbonaut_v6_frozen`:
    - [ ] Lock structural models & datasets permanently.
    - [ ] Version and copy crucial executable configurations logically. 
    - [ ] Standardize the final execution format matching `README.md`. 
* [ ] 14. Synthesize data outputs summarizing standard evaluations (e.g., benchmark comparison tables isolating skipping techniques) structuring final system wrap-ups definitively mapping explicitly into `report.md`.
