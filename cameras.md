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


