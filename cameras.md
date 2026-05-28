## 2026-05-25 remount update

After remounting camEast and camWest, all four attached DS-E12 cameras were
queried directly with `v4l2-ctl`. The maximum practical calibrated mode is:

- `1920x1080`
- `MJPG`
- `30 FPS`

Do not use uncompressed `YUYV` or `NV12` for FullHD capture: those modes only
advertise `5 FPS` at `1920x1080` on this hardware. The active runtime and
calibration defaults now target `1920x1080 MJPG @ 30 FPS`, and intrinsics must
be regenerated for that resolution before geometry validation.

● Good research. Your analysis of the latency chain is correct. Here's my honest assessment:

  Do You Need New Cameras?

  Not for the thesis. Your accuracy results (95mm ball, 143mm joint) already meet your RQ1/RQ2 targets. The DS-E12 cameras are sufficient to prove the concept, which is the thesis goal.

  Yes, for any post-thesis deployment or continued development. The DS-E12 cameras are the weakest link in the long-term pipeline, and here's specifically why:

  What the DS-E12 Actually Costs You

  ┌───────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────┐
  │        Problem        │                                                Impact                                                 │                        Can Software Fix It?                        │
  ├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ 15 FPS max            │ 66.7ms minimum between frames — a person walking at 1.5 m/s moves 100mm between frames                │ No                                                                 │
  ├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ No hardware sync      │ 4 cameras capture at different moments — up to ±33ms offset at 15 FPS, causing triangulation error on │ No — your flash-sync protocol handles static GT but not live       │
  │                       │  moving targets                                                                                       │ motion                                                             │
  ├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Auto-exposure hunting │ Brightness shifts cause detection confidence drops                                                    │ Partially — can lock exposure via V4L2, but DS-E12 doesn't always  │
  │                       │                                                                                                       │ respect it                                                         │
  ├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Internal MJPG         │ Camera-side buffer adds 30-60ms before the frame even reaches USB                                     │ No                                                                 │
  │ buffering             │                                                                                                       │                                                                    │
  ├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ USB 2.0 bandwidth     │ 4 × 720p MJPG streams saturate a single USB controller                                                │ Only by reducing resolution, which breaks your calibrated          │
  │                       │                                                                                                       │ intrinsics                                                         │
  ├───────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────┤
  │ Rolling shutter       │ Fast ball motion produces skewed detections                                                           │ No                                                                 │
  └───────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────┘

  The critical insight from your research is correct: the largest latency contributor is probably not your code — it's the camera-to-USB-to-software path. Your threaded capture + buffer-size-1 strategy
  mitigates software-side buffering, but cannot fix camera-internal delays.

## USB Bandwidth Engineering (Hardware-Systems Note for the Committee)

**Confirmed empirically 2026-04-17** via `lsusb -t`, `lsusb`, and `v4l2-ctl --list-formats-ext`.

### Hardware

| Item | Measured / Confirmed Value |
|---|---|
| Cameras | 4× Hikvision DS-E12, USB Vendor:Product `2bdf:0289`, labelled "1080P USB Camera" |
| USB class at negotiation | **USB 2.0 High-Speed, 480 Mbps per camera** (`lsusb -t` reports `Driver=uvcvideo, 480M` on all four devices) |
| Host controller | Single Intel xHCI at PCI `0000:00:14.0`, all 4 cameras share it |
| Cables | 2× 5 m + 2× 10 m USB 3.0 **active** (built-in signal repeater). Supplier: `https://mobile.yangkeduo.com/goods.html?ps=RVFvfdXjWm` |
| Supported formats | MJPG / YUYV / NV12 at 1280×720. MJPG advertises up to 30 FPS. |
| Live operating point | **1280×720 MJPG @ 15 FPS** |

### Design Choice: Long-Reach 4-Camera Deployment

The lab and target deployment (Academy Kairat pitch-scale) both require cameras **placed at the arena/pitch corners, not at the PC**. Passive USB 2.0 cables are specified to ~5 m; passive USB 3.0 to ~3 m. Both fall short of the ≥10 m runs required by any realistic multi-camera sports rig. The active USB 3.0 extension cables (with an in-cable signal-repeater IC) were selected specifically to meet this physical-reach requirement while preserving UVC compatibility on Linux.

An important subtlety — verified after physical deployment — is that the **cables cannot upgrade the device class of the camera**. The DS-E12 is a USB 2.0 device by firmware class, so the active cables correctly re-drive the USB 2.0 signal across 10 m but do not negotiate a USB 3.0 SuperSpeed link. This was confirmed by inspecting the link speed in `lsusb -t`: every DS-E12 sits on a 480 Mbps endpoint, not a 5 Gbps one. The active cables did their job (reach), but the aggregate pipeline bandwidth is therefore capped by USB 2.0, not by the cable spec printed on the jacket.

### Bandwidth Budget and the MJPG Decision

With four cameras sharing one USB 2.0 controller, the effective isochronous budget is approximately 320 Mbps (USB 2.0 reserves ~80% of the raw 480 Mbps for isochronous endpoints with protocol overhead).

| Pixel format | Per-cam rate @ 1280×720, 15 FPS | Aggregate (×4) | Fits USB 2.0? |
|---|---|---|---|
| YUYV (uncompressed, 2 B/px) | 221 Mbps | 884 Mbps | **No** |
| NV12 (uncompressed, 1.5 B/px) | 166 Mbps | 663 Mbps | **No** |
| MJPG (in-camera JPEG, ~10× compression) | ~20 Mbps | ~80 Mbps | **Yes, with ample margin** |

**MJPG was not a stylistic preference; it was the only format that fits four simultaneous streams on one USB 2.0 controller at our operating resolution.** The cost paid for this is CPU cycles — every frame is JPEG-decoded by the host-side capture thread (`cv2.imdecode`). This is budgeted inside the threaded capture stage and is invisible to the downstream geometry pipeline.

### Why the Operating Point Is 15 FPS

At 1280×720 MJPG the camera firmware advertises 30 FPS per device. In practice the system is limited by two compounding ceilings:

1. **USB 2.0 isochronous scheduling on a shared xHCI controller.** When four UVC devices share one host controller, frame delivery is subject to bus-wide microframe allocation and the camera-internal MJPG encoding pipeline. In our measurements this caps stable aggregate capture at ~15–18 FPS across all four cameras, well below what the raw Mbps budget alone would suggest. This contention pattern is a well-known limitation of multi-camera UVC on a single host controller and is the documented motivation for industrial machine-vision cameras to use USB 3.0 or GigE Vision.
2. **Inference throughput.** Batched 4-camera YOLO + pose inference on the RTX 2080 Ti with TensorRT FP16 also saturates near 15 FPS.

The two limits meet at approximately the same operating point, which is why the pipeline is explicitly configured with `--fps 15` rather than allowed to free-run.

### Why This Is Acceptable for the Thesis

The thesis claims were validated at this operating point:
- Precision post-correction: 4.4 mm (joint-touch), 3.1 mm (rigid ball GT).
- Pose-to-aim latency: ~50 ms.
- Shot accuracy verified on the integrated live test (2026-04-09) at multiple joints.

The research questions are about the method — multi-view triangulation, pose-guided ballistic targeting, safety FSM on the BLM — not about maximising frame rate. The 15 FPS operating point is therefore an **honest, documented operating envelope**, not an unmitigated weakness.

### Documented Upgrade Path (Future-Work Chapter)

For deployment at Academy Kairat (full-pitch scale, faster ball speeds, harder motion blur) the camera layer is the first thing to upgrade, not the software:

- **Move to USB 3.0 native machine-vision cameras** (e.g. Basler ace 2 USB3 Mono global-shutter, FLIR Blackfly S USB3). These negotiate SuperSpeed links (5 Gbps) per camera and expose manual exposure + external trigger, directly addressing the rolling-shutter + auto-exposure motion-blur limitations documented in the ball-tracking observations.
- **The active-cable infrastructure partly carries over.** USB 3.0 active cables of the same class can be re-used, though SuperSpeed integrity over 10 m typically requires a re-driver at both ends or a fibre-optical USB 3.0 extender — a known and specified upgrade, not a redesign.
- **For pitch-scale (≥50 m runs)**: GigE Vision with PoE+ is the industry-standard answer and fits the same software abstraction through `aravis-viewer`/`harvester` UVC-like wrappers.

The engineering point to the committee is this: the current system has been **characterised down to the link layer**, the operating point has been **justified with bandwidth math**, and the upgrade path is **specific and costed** rather than vague.

---

  What Would Actually Help (Ranked by Impact per Dollar)

  Tier 1: Same Budget, Better Camera (~$40-60 each)

  Logitech C920/C922 or similar
  - 30 FPS at 720p (2× your current frame rate)
  - Better USB UVC compliance — more predictable buffering
  - Manual exposure lock works reliably via V4L2
  - Still no hardware sync, still USB 2.0, still rolling shutter
  - Expected gain: frame interval drops from 67ms to 33ms, halving the motion-induced triangulation error

  This is the highest value upgrade — double the temporal resolution for ~$120 total (4 cameras). Your existing intrinsics calibration would need to be redone, but extrinsics and the entire pipeline
  remain identical.

  Tier 2: Moderate Budget (~$100-200 each)

  Global shutter USB3 industrial cameras (e.g., FLIR Blackfly S, Basler ace 2, Allied Vision Alvium)
  - 60-120 FPS at 720p
  - Global shutter — no rolling shutter distortion on fast objects
  - USB 3.0 — much higher bandwidth, lower transfer latency
  - Hardware trigger input — can be synced with an Arduino/ESP32 pulse
  - Manual exposure, gain, white balance — fully controllable
  - Expected gain: frame interval drops to 8-16ms, hardware sync eliminates inter-camera timing error entirely

  This is what a "production" version of your system needs. At $400-800 for 4 cameras, it's still 100× cheaper than OptiTrack/Vicon. Hardware sync alone would eliminate your flash-sync protocol and
  improve moving-target accuracy significantly.

  Tier 3: What NOT to Buy

  - Depth cameras (RealSense, Azure Kinect) — different paradigm, doesn't integrate with your multi-view triangulation pipeline, limited range
  - 4K webcams — more pixels ≠ better for your use case. Higher resolution increases inference time without proportional accuracy gain at your arena distances (3-5m). Your 720p resolution is appropriate
  - IP cameras / RTSP cameras — add 200-500ms network latency, worse than USB for real-time
  - Action cameras (GoPro etc.) — high latency, no programmatic control, expensive

  What to Do Before Buying Anything

  Run this diagnostic first to prove whether cameras are actually the bottleneck:

  # Test 1: Raw camera latency (no processing)
  # Wave your hand in front of one camera, observe lag in raw feed
  python -c "
  import cv2, time
  cap = cv2.VideoCapture('/dev/v4l/by-path/pci-0000:00:14.0-usb-0:11.1:1.0-video-index0')
  cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
  cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
  cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
  cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
  while True:
      ret, f = cap.read()
      if ret:
          cv2.putText(f, f'{time.time():.3f}', (10,30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
          cv2.imshow('raw', f)
      if cv2.waitKey(1) & 0xFF == ord('q'): break
  "

  # Test 2: Measure actual delivered FPS per camera
  python -c "
  import cv2, time
  for path in [
      'pci-0000:00:14.0-usb-0:11.1:1.0-video-index0',
      'pci-0000:00:14.0-usb-0:13.1:1.0-video-index0',
      'pci-0000:00:14.0-usb-0:7.1.1:1.0-video-index0',
      'pci-0000:00:14.0-usb-0:5.1.1:1.0-video-index0',
  ]:
      cap = cv2.VideoCapture(f'/dev/v4l/by-path/{path}')
      cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
      cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
      cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
      cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
      t0 = time.time()
      count = 0
      while time.time() - t0 < 5.0:
          ret, _ = cap.read()
          if ret: count += 1
      cap.release()
      print(f'{path.split(\"usb-0:\")[1]}: {count/5.0:.1f} FPS actual')
  "

  # Test 3: Check USB controller distribution
  lsusb -t | grep -A2 "Camera\|Hikvision\|video"
  # If all 4 cameras are on the same USB host controller,
  # they share bandwidth — this alone can halve effective FPS

  If Test 1 shows visible lag even on the raw feed, cameras are the bottleneck. If Test 2 shows actual FPS well below 15, USB bandwidth is the constraint. If Test 3 shows all cameras on one controller,
  redistribution across USB controllers (if your motherboard has multiple) is a free fix.

  My Recommendation

  For the thesis (now): Keep the DS-E12 cameras. Implement the 3D Safe First optimization plan. Your accuracy numbers are already strong, and the system works. Spending time on camera upgrades doesn't add
   to your thesis contributions.

  For future work / Section 6.4: Note in the thesis that hardware-synchronized global-shutter cameras at 60+ FPS would eliminate the temporal synchronization limitation and enable the moving-target
  prediction described in Section 6.4.1. This is honest, forward-looking, and shows engineering maturity.

  If you continue the project post-thesis: Buy 4× Logitech C922 ($40 each) as an immediate upgrade, recalibrate intrinsics, and measure the improvement. If you want to go further, 4× FLIR Blackfly S with
  an Arduino trigger board is the proper engineering solution.

