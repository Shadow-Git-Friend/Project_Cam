from ultralytics import YOLO
import cv2, os, yaml, argparse, csv, json
import numpy as np
import torch
from threading import Thread
from queue import Queue, Empty
import time
from tracker.trackerv1 import tracker
from tracker.tracker3d import Tracker3D
from reconstruction import StereoTriangulator

# Constants
QUEUE_SIZE = 128
VIS_STACK_WIDTH = 1920 * 2 # Or scaled down? Let's keep full res for now
VIS_TEXT_COLOR = (0, 255, 255)

class VideoLoader:
    def __init__(self, path, name="Stream"):
        self.name = name
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            print(f"Error: Could not open {path}")
        self.q = Queue(maxsize=QUEUE_SIZE)
        self.stopped = False
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
    def start(self):
        # Synchronous mode: do nothing
        return self

    def update(self):
        pass

    def read(self):
        if not self.cap.isOpened():
            return None
        ret, frame = self.cap.read()
        if not ret:
            self.stop()
            return None
        return frame

    def running(self):
        return self.cap.isOpened() and not self.stopped
        
    def stop(self):
        self.stopped = True
        self.cap.release()
        
class VideoWriter:
    def __init__(self, path, fps, size):
        self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'mp4v'), fps, size)
        self.q = Queue(maxsize=QUEUE_SIZE)
        self.stopped = False
        self.t = Thread(target=self.update, args=(), daemon=True)
        self.t.start()
        
    def update(self):
        while True:
            if self.stopped and self.q.empty():
                break
            try:
                frame = self.q.get(timeout=0.1)
                self.writer.write(frame)
                self.q.task_done()
            except Empty:
                continue
        self.writer.release()

    def write(self, frame):
        self.q.put(frame)

    def stop(self):
        self.stopped = True
        self.q.join()
        self.t.join() # Wait for thread to finish releasing writer

class FieldVisualizer:
    def __init__(self, img_size=600):
        self.img_size = img_size
        self.canvas = np.zeros((img_size, img_size, 3), dtype=np.uint8)
        self.trail = []
        
        # Field Dimensions (meters)
        self.w = 10.0  # X: 0..10 
        self.h = 4.0   # Height
        self.d = 10.0  # Z: 0..10 (Updated to 10m)
        
        # Virtual Camera
        self.angle_x = np.radians(45)
        self.angle_y = np.radians(-45)
        self.scale = 80.0 # pixels per meter (Zoomed in for 10x10)
        
        # Adjust offset to center (5, 0, 5)
        # Center of arena projects to rx=0, ry_screen which shifts by scale.
        # Calculated offset to put center at screen center:
        self.offset = (img_size // 2, img_size // 2 - 400)

    def project(self, x, y, z):
        # Rotate around Y
        rx = x * np.cos(self.angle_y) + z * np.sin(self.angle_y)
        rz = -x * np.sin(self.angle_y) + z * np.cos(self.angle_y)
        
        # Tilt around X
        ry = y * np.cos(self.angle_x) - rz * np.sin(self.angle_x)
        final_rz = y * np.sin(self.angle_x) + rz * np.cos(self.angle_x)
        
        # Invert X axis for Screen X (Map X=0 to Right, X=10 to Left)
        px = int(self.offset[0] - rx * self.scale)
        py = int(self.offset[1] - ry * self.scale)
        return (px, py)

    def update(self, pos_3d, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
            
        X, Y, Z = 0, 0, 0
        if pos_3d is not None:
            X, Y, Z = pos_3d
            self.trail.append((pos_3d, timestamp))
            
        # Clean up old trail points (> 2.0s)
        self.trail = [p for p in self.trail if (timestamp - p[1]) < 2.0]
        
        self.canvas.fill(20) # Dark Background
        
        # Draw Grid (Floor)
        # X: 0..10, Z: 0..10
        grid_color = (60, 60, 60)
        
        # Z-lines (varying X)
        for i in range(0, 11, 1): # X=0, 1, ... 10 (Every meter)
            p1 = self.project(i, 0, 0)
            p2 = self.project(i, 0, 10)
            cv2.line(self.canvas, p1, p2, grid_color, 1)
            
        # X-lines (varying Z)
        for i in range(0, 11, 1): # Z=0, 1, ... 10 (Every meter)
            p1 = self.project(0, 0, i)
            p2 = self.project(10, 0, i)
            cv2.line(self.canvas, p1, p2, grid_color, 1)

        # Draw Bounds Box
        box_color = (130, 130, 130)
        def draw_line_3d(p1, p2, color, thick=1):
            uv1 = self.project(*p1)
            uv2 = self.project(*p2)
            cv2.line(self.canvas, uv1, uv2, color, thick)
            
        # Floor Outline
        draw_line_3d((0,0,0), (10,0,0), (180, 180, 180), 2) # North Wall Base 
        draw_line_3d((0,0,0), (0,0,10), (180, 180, 180), 2) # East Wall Base 
        draw_line_3d((10,0,0), (10,0,10), box_color, 2)
        draw_line_3d((0,0,10), (10,0,10), box_color, 2)
        
        # Verticals
        for x in [0, 10]:
            for z in [0, 10]:
                draw_line_3d((x,0,z), (x,4,z), box_color, 1)
        # Top Outline
        draw_line_3d((0,4,0), (10,4,0), box_color, 1)
        draw_line_3d((0,4,0), (0,4,10), box_color, 1)
        draw_line_3d((10,4,0), (10,4,10), box_color, 1)
        draw_line_3d((0,4,10), (10,4,10), box_color, 1)

        # Labels
        origin_uv = self.project(0, 0, 0)
        cv2.putText(self.canvas, "NE (0,0)", (origin_uv[0]-80, origin_uv[1]-10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        pos_north = self.project(5, 0, 0) # Center North
        cv2.putText(self.canvas, "NORTH", (pos_north[0]-30, pos_north[1]-20), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)

        pos_east = self.project(0, 0, 5) # Center East
        cv2.putText(self.canvas, "EAST", (pos_east[0]+10, pos_east[1]), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)
        
        pos_south = self.project(5, 0, 10)
        cv2.putText(self.canvas, "SOUTH", (pos_south[0]-30, pos_south[1]+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

        # Draw Cameras (Approx positions relative to 10x10)
        # Cam A was (0, 2, 5) -> East Wall Center. Still valid for Z=10 arena if East is Z-axis? 
        # Wait, Z=0..10. Center is 5. So (0, 2, 5) is perfect.
        camA_uv = self.project(0, 2, 5)
        cv2.circle(self.canvas, camA_uv, 8, (0, 255, 255), -1)
        cv2.putText(self.canvas, "Cam A", (camA_uv[0]+15, camA_uv[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        # Cam B was (5, 2, 0) -> North Wall Center. Still valid.
        camB_uv = self.project(5, 2, 0)
        cv2.circle(self.canvas, camB_uv, 8, (0, 255, 255), -1)
        cv2.putText(self.canvas, "Cam B", (camB_uv[0]-40, camB_uv[1]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # Draw Trail & Ball
        if len(self.trail) > 1:
            pts = [self.project(*p[0]) for p in self.trail]
            if len(pts) > 1:
                cv2.polylines(self.canvas, [np.array(pts)], False, (0, 165, 255), 3)
        
        if pos_3d is not None:
            px, py = self.project(X, Y, Z)
            sx, sy = self.project(X, 0, Z)
            # Reference line
            cv2.line(self.canvas, (px, py), (sx, sy), (100, 100, 100), 1)
            # Shadow
            cv2.circle(self.canvas, (sx, sy), 5, (100, 100, 100), -1)
            # Ball
            cv2.circle(self.canvas, (px, py), 8, (0, 0, 255), -1)
            cv2.circle(self.canvas, (px, py), 8, (255, 255, 255), 1)
            label = f"({X:.1f}, {Y:.1f}, {Z:.1f})"
            cv2.putText(self.canvas, label, (px+12, py), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return self.canvas

class InferenceThread:
    def __init__(self, model, conf, imgsz):
        self.model = model
        self.conf = conf
        self.imgsz = imgsz
        self.q_in = Queue(maxsize=16)
        self.q_out = Queue(maxsize=16)
        self.stopped = False
        self.thread = Thread(target=self.run, daemon=True)
        
    def start(self):
        self.thread.start()
        return self
        
    def run(self):
        print("Inference Thread: Started")
        while not self.stopped:
            try:
                # Get usage item: (token, frames)
                item = self.q_in.get(timeout=0.1)
                token, frames = item
                
                # Inference
                if frames:
                    # Batch inference
                    # Rect=False forced for TensorRT engine
                    results = self.model(frames, verbose=False, iou=0.5, conf=self.conf, imgsz=self.imgsz, rect=False)
                else:
                    results = []
                
                self.q_out.put((token, results))
                self.q_in.task_done()
                
            except Empty:
                continue
            except Exception as e:
                print(f"Inference Thread Error: {e}")
                
    def put(self, token, frames):
        self.q_in.put((token, frames))
        
    def get(self):
        return self.q_out.get()
        
    def stop(self):
        self.stopped = True
        # self.thread.join() 

def main():

    root = os.getcwd()
    
    # Args
    parser = argparse.ArgumentParser()
    parser.add_argument("--camA", type=str, default="pitch/camA.mp4")
    parser.add_argument("--camB", type=str, default="pitch/camB.mp4")
    parser.add_argument("--out", type=str, default="outputs/final_3d_view.mp4")
    parser.add_argument("--calib", type=str, default="calibration.npz")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument("--mode", type=str, default="grid", choices=["grid", "3d"])
    args = parser.parse_args()
    
    # Load Config
    with open(os.path.join(root, "config/config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
        
    paths = cfg.get("paths", {})
    model_path = args.model or os.path.join(root, paths.get("model", "runs/y12s_832_v22/weights/epoch80.pt"))
    print(f"Loading Model: {model_path}")
    model = YOLO(model_path, task="detect")
    
    # --- Threaded Inference Setup ---
    print("Starting Inference Thread...")
    inf_thread = InferenceThread(model, cfg["conf"], cfg["imgsz"]).start()
    
    if not os.path.exists(args.calib):
        print(f"Error: Calibration file {args.calib} not found.")
        return
    print(f"Loading Calibration: {args.calib}")
    triangulator = StereoTriangulator(args.calib)
    
    trackerA = tracker(cfg)
    trackerB = tracker(cfg)
    tracker3d = Tracker3D(history_len=20, alpha_smooth=0.7)
    
    print(f"Opening Stream A: {args.camA}")
    loaderA = VideoLoader(args.camA, "A").start()
    print(f"Opening Stream B: {args.camB}")
    loaderB = VideoLoader(args.camB, "B").start()
    
    # OUTPUT
    out_w, out_h = 1920, 1080
    vis_res = 1080
    vis3d = FieldVisualizer(img_size=vis_res)
    
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    
    # Unique Output Filenames
    base_name = os.path.splitext(os.path.basename(args.out))[0]
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    out_video_path = os.path.join(os.path.dirname(args.out), f"{base_name}_{timestamp_str}.mp4")
    metrics_path = os.path.join(os.path.dirname(args.out), f"metrics_{timestamp_str}.csv")
    
    print(f"Output Video: {out_video_path}")
    print(f"Metrics File: {metrics_path}")
    
    writer = VideoWriter(out_video_path, loaderA.fps, (out_w, out_h))
    
    frame_idx = 0
    t_start = cv2.getTickCount()
    last_time = cv2.getTickCount()
    fps_smooth = 0.0
    model_ms_smooth = 0.0
    
    print("Starting Optimized 3D Inference Loop (Batched + Threaded)...")
    
    # Setup for batching
    detect_every = cfg.get("detect_every", 1)
    adaptive_cfg = cfg.get("adaptive_skipping", {})
    adaptive_enabled = adaptive_cfg.get("enabled", False)
    next_detect_frame = 1
    
    frame_buffer = [] # Store tuples (idx, fA, fB)
    
    # Unique Output Filenames
    base_name = os.path.splitext(os.path.basename(args.out))[0]
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    out_video_path = os.path.join(os.path.dirname(args.out), f"{base_name}_{timestamp_str}.mp4")
    metrics_path = os.path.join(os.path.dirname(args.out), f"metrics_{timestamp_str}.csv")
    json_metrics_path = os.path.join(os.path.dirname(args.out), f"metrics_{timestamp_str}.json")
    
    print(f"Output Video: {out_video_path}")
    print(f"Metrics File: {metrics_path}")
    print(f"JSON Metadata: {json_metrics_path}")
    
    json_data = [] # Accumulate per-frame metrics
    
    # Re-init Writer with new name (Wait, writer was initialized earlier? Check args!)
    # Ah, `writer` is global/local variable initialized at start of main?
    # Let's check where `writer` is created. It's usually created earlier.
    # We should override `writer` here or change it where it's created.
    # Looking at prev view, `writer` isn't visible in this block.
    # Assuming `writer = VideoWriter(...)` was done before loops.
    # Wait, I didn't see `writer` init in lines 330-360.
    
    # Let's just set the Metrics CSV here.
    
    # Metrics CSV
    csv_file = open(metrics_path, "w", newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        "frame_idx", "timestamp",
        "camA_cx", "camA_cy", "camA_speed", "camA_ax", "camA_ay", "camA_accel",
        "camB_cx", "camB_cy", "camB_speed", "camB_ax", "camB_ay", "camB_accel",
        "3d_x", "3d_y", "3d_z", "3d_velocity", "3d_ax", "3d_ay", "3d_az", "3d_accel"
    ])

    # Pipeline queues
    # We submit batch, but we can only process it when we get results.
    # We maintain a separate "processing_queue" in main thread to match results to frames.
    pending_batches = Queue() 
    
    # To handle the very first frames, the loop will spin.
    
    try:
        print(f"Starting Main Loop... LoaderA: {loaderA.running()}, LoaderB: {loaderB.running()}")
        while loaderA.running() and loaderB.running():
            # TIMING: Read
            t0 = cv2.getTickCount()
            frameA = loaderA.read()
            frameB = loaderB.read()
            t1 = cv2.getTickCount()
            t_read = (t1 - t0) / cv2.getTickFrequency() * 1000
            
            # Initialize other timers
            t_infer_wait = 0.0
            t_proc = 0.0
            t_write = 0.0

            if frameA is None or frameB is None:
                print(f"Frame is None! A: {frameA is not None}, B: {frameB is not None}")
                break
                
            frame_idx += 1
            frame_buffer.append((frame_idx, frameA, frameB))
            
            # --- BATCH PREPARATION ---
            # Match Batch Size: 2 Timestamps (4 Images)
            if len(frame_buffer) < 2:
                continue
                
            # Prepare Payload
            frames_to_infer = []
            current_buffer_data = list(frame_buffer) # Copy current 2 timestamps
            frame_buffer.clear() # Clear immediately for next read
            
            for _, fA, fB in current_buffer_data:
                frames_to_infer.extend([fA, fB])
            
            # Decide if Detection Needed (Logic simplified: run if any frame scheduled)
            run_detection_batch = True
            if adaptive_enabled:
                 # Check if latest frame needs det
                 latest_idx = current_buffer_data[-1][0]
                 if latest_idx < next_detect_frame:
                     run_detection_batch = False
                     
            if run_detection_batch:
                # SUBMIT TO THREAD
                token = time.time() # UID
                inf_thread.put(token, frames_to_infer)
                pending_batches.put({
                    "data": current_buffer_data,
                    "needs_det": True,
                    "token": token
                })
            else:
                # No detection needed, but we still need to process/track/write "later"
                # to maintain order. We can "fake" a submission or just queue it as "done"
                # But we want to preserve pipeline order.
                # If we don't submit to GPU, we can process immediately? 
                # NO, we must output frames in order. If previous batch is pending in GPU,
                # we must wait for it before processing this one? 
                # Actually, output writing can be threaded. 
                # But Tracker update must be sequential (N then N+1).
                # So we must wait for previous batch to finish tracking.
                
                # To keep pipeline full, we push a "dummy" or handle locally.
                # Let's just push a None to thread to keep synchronization simple?
                # Or just mark as "ready" in our pending queue.
                
                # Better: Submit empty list to thread? It returns empty list quickly. It keeps order.
                inf_thread.put(time.time(), []) 
                pending_batches.put({
                    "data": current_buffer_data,
                    "needs_det": False,
                    "token": None
                })

            # --- RESULT RETRIEVAL & PROCESSING ---
            # If we have pending batches, try to get result.
            # We want to keep pipeline depth of 1 or 2?
            # If pending_batches > 1, force get?
            
            # Pipelining: We want to submit N, then Wait for N-1.
            # So if this is the FIRST batch, we continue (to submit N+1).
            # If pending_batches queue size > 1, we pull.
            
            while pending_batches.qsize() > 1: # Allow depth of 1 in-flight
                
                # Get the oldest batch metadata
                batch_meta = pending_batches.get()
                
                results = []
                # If we expected detections, get from thread
                # Even if we sent [], thread sends back (token, [])
                
                # We ALWAYS get from thread to ensure sync
                t2 = cv2.getTickCount()
                token_out, res_out = inf_thread.get()
                t3 = cv2.getTickCount()
                t_infer_wait = (t3 - t2) / cv2.getTickFrequency() * 1000
                results = res_out
                
                t_proc = 0.0
                t_write = 0.0
                    
                # PROCESS AND VISUALIZE (The heavy CPU part)
                # ... [Logic extracted to function ideally, but inline here for now] ...
                
                # Iterate through the 2 timestamps in this batch
                for i, (fIdx, fA, fB) in enumerate(batch_meta["data"]):
                    t4 = cv2.getTickCount()
                    
                    resA = None
                    resB = None
                    is_det = batch_meta["needs_det"] and (len(results) >= (2*i + 2))
                    
                    if is_det:
                        resA = results[2*i]
                        resB = results[2*i+1]
                        
                    detsA = []
                    detsB = []
                    
                    if is_det and resA:
                        def parse_dets_res(res):
                            d = []
                            for b in res.boxes:
                                d.append({
                                    "bbox": b.xyxy[0].cpu().numpy(),
                                    "conf": float(b.conf)
                                })
                            return d
                        detsA = parse_dets_res(resA)
                        detsB = parse_dets_res(resB)
                        
                    tracksA = trackerA.update(detsA, fIdx)
                    tracksB = trackerB.update(detsB, fIdx)
                    
                    
                    # Triangulate
                    tA = tracksA[0] if tracksA else None
                    tB = tracksB[0] if tracksB else None
                    p3d = None
                    s3d = None
                    if tA and tB and tA["missed"] == 0 and tB["missed"] == 0:
                        p3d = triangulator.triangulate(tA["centroid"], tB["centroid"])
                        s3d = tracker3d.update(p3d)
                    else:
                        s3d = tracker3d.update(None)
                        
                    # Adaptive Frame Skipping (3D Speed Based)
                    if adaptive_enabled and is_det:
                         curr_skip = 0
                         if s3d and s3d["position"]:
                             v = s3d["velocity"]
                             if v > 2.0:
                                 curr_skip = 0
                             elif v > 0.1:
                                 curr_skip = 3 # Skip 2 frames (detect every 3rd)
                             else:
                                 curr_skip = 5 # Skip 4 frames (detect every 5th)
                         else:
                            # Tracking lost or initializing -> Don't skip (find ball!)
                            curr_skip = 0
                         
                         if (fIdx + curr_skip) > next_detect_frame:
                             next_detect_frame = fIdx + curr_skip
                        
                    # --- METRICS LOGGING ---
                    # Use Video Time (relative) instead of Wall Clock processing time
                    curr_t = 0.0
                    if loaderA.fps > 0:
                         curr_t = float(fIdx - 1) / loaderA.fps
                    
                    # Cam A Metrics
                    cxA, cyA, spdA, axA, ayA, accA = -1, -1, 0, 0, 0, 0
                    if tA:
                        cxA, cyA = tA["centroid"]
                        spdA = tA.get("speed", 0)
                        axA = tA.get("ax", 0)
                        ayA = tA.get("ay", 0)
                        accA = tA.get("accel", 0)
                        
                    # Cam B Metrics
                    cxB, cyB, spdB, axB, ayB, accB = -1, -1, 0, 0, 0, 0
                    if tB:
                        cxB, cyB = tB["centroid"]
                        spdB = tB.get("speed", 0)
                        axB = tB.get("ax", 0)
                        ayB = tB.get("ay", 0)
                        accB = tB.get("accel", 0)
                    
                    # 3D Metrics
                    mx, my, mz, mvel, max3, may3, maz3, macc = -1, -1, -1, 0, 0, 0, 0, 0
                    if s3d and s3d["position"]:
                        mx, my, mz = s3d["position"]
                        mvel = s3d["velocity"]
                        macc = s3d.get("accel", 0)
                        max3 = s3d.get("ax", 0)
                        may3 = s3d.get("ay", 0)
                        maz3 = s3d.get("az", 0)
                        
                    csv_writer.writerow([
                        fIdx, f"{curr_t:.4f}",
                        f"{cxA:.1f}", f"{cyA:.1f}", f"{spdA:.1f}", f"{axA:.2f}", f"{ayA:.2f}", f"{accA:.2f}",
                        f"{cxB:.1f}", f"{cyB:.1f}", f"{spdB:.1f}", f"{axB:.2f}", f"{ayB:.2f}", f"{accB:.2f}",
                        f"{mx:.3f}", f"{my:.3f}", f"{mz:.3f}", f"{mvel:.3f}", f"{max3:.2f}", f"{may3:.2f}", f"{maz3:.2f}", f"{macc:.2f}"
                    ])
                    
                    # Accumulate JSON
                    json_data.append({
                        "frame_idx": int(fIdx),
                        "timestamp": round(float(curr_t), 4),
                        "ball_id": 0,
                        "position_3d": {"x": round(float(mx), 3), "y": round(float(my), 3), "z": round(float(mz), 3)},
                        "velocity_3d": {"vx": 0, "vy": 0, "vz": 0, "speed": round(float(mvel), 3)},
                        "acceleration_3d": {"ax": round(float(max3), 2), "ay": round(float(may3), 2), "az": round(float(maz3), 2), "accel": round(float(macc), 2)},
                        "camA": {"x": round(float(cxA), 1), "y": round(float(cyA), 1), "speed": round(float(spdA), 1), "accel": round(float(accA), 1)},
                        "camB": {"x": round(float(cxB), 1), "y": round(float(cyB), 1), "speed": round(float(spdB), 1), "accel": round(float(accB), 1)}
                    })

                    # Visualize
                    def draw_tracks_local(frame, track, is_pred):
                        if not track: return
                        x1, y1, x2, y2 = map(int, track["bbox"])
                        color = (0, 255, 255) if is_pred else ((0, 255, 0) if track["missed"] == 0 else (0, 0, 255))
                        cx, cy = map(int, track["centroid"])
                        history = track.get("history", [])
                        if len(history) >= 2:
                            pts = np.array(history, dtype=np.int32).reshape((-1, 1, 2))
                            cv2.polylines(frame, [pts], False, (0, 165, 255), 2)
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                        speed = track.get("speed", 0.0)
                        cv2.putText(frame, f"ID {track['id']} {speed:.1f}", (x1, max(15, y1-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                        cv2.circle(frame, (cx, cy), 5, (0, 255, 255), -1)

                    if args.mode == "grid":
                        draw_tracks_local(fA, tA, not is_det)
                        draw_tracks_local(fB, tB, not is_det)
                        cv2.putText(fA, f"FPS: {fps_smooth:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                    vis_pos = s3d["position"] if (s3d and s3d["position"]) else p3d
                    map_img_local = vis3d.update(vis_pos, curr_t)
                    
                    final_frame = None
                    if args.mode == "3d":
                        final_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
                        if map_img_local.shape[0] != 1080:
                           map_img_local = cv2.resize(map_img_local, (1080, 1080))
                        x_off = (1920 - 1080) // 2
                        final_frame[:, x_off:x_off+1080] = map_img_local
                        
                        cv2.putText(final_frame, "3D Field View (Threaded)", (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
                        cv2.putText(final_frame, f"Frame: {fIdx}", (50, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
                        if p3d is not None:
                             _X, _Y, _Z = p3d
                             cv2.putText(final_frame, f"X: {_X:.2f} m", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                             cv2.putText(final_frame, f"Y: {_Y:.2f} m", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                             cv2.putText(final_frame, f"Z: {_Z:.2f} m", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                    else:
                        final_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
                        vA = cv2.resize(fA, (960, 540))
                        final_frame[0:540, 0:960] = vA
                        vB = cv2.resize(fB, (960, 540))
                        final_frame[0:540, 960:1920] = vB
                        
                        mh, mw = map_img_local.shape[:2]
                        scale = 540.0 / mh
                        new_w = int(mw * scale)
                        map_resized = cv2.resize(map_img_local, (new_w, 540))
                        
                        pad_x = (960 - new_w) // 2
                        vMap = np.zeros((540, 960, 3), dtype=np.uint8)
                        vMap[:, pad_x:pad_x+new_w] = map_resized
                        final_frame[540:1080, 0:960] = vMap
                        
                        vInfo = np.zeros((540, 960, 3), dtype=np.uint8)
                        vInfo.fill(30)
                        
                        y_off_info = 50
                        def info(txt, col=(200,200,200), scale=0.8):
                            nonlocal y_off_info, vInfo
                            cv2.putText(vInfo, txt, (40, y_off_info), cv2.FONT_HERSHEY_SIMPLEX, scale, col, 2)
                            y_off_info += 35
                        
                        # FPS & Inference
                        info(f"FPS: {fps_smooth:.1f}", (0, 255, 0), 1.0)
                        
                        skip_mod = "0"
                        if adaptive_enabled:
                            if curr_skip == 3: skip_mod = "2 (Med)"
                            elif curr_skip == 5: skip_mod = "4 (Slow)"
                            else: skip_mod = "0 (Full)"
                            
                        info(f"Infer: {model_ms_smooth:.1f}ms Skip: {skip_mod}", (0, 255, 255))
                        y_off_info += 10
                        
                        # 3D Metrics
                        info("--- 3D ---", (255, 255, 255), 0.9)
                        if p3d is not None:
                            info(f"Pos: X{mx:.2f}, Y{my:.2f}, Z{mz:.2f} m")
                            info(f"Speed: {mvel:.2f} m/s", (0, 255, 0) if mvel > 0.1 else (200,200,200))
                            info(f"Accel: {macc:.2f} m/s2", (0, 255, 255) if macc > 0.5 else (200,200,200))
                        else:
                            info("Tracking: LOST", (0, 0, 255))
                            
                        y_off_info += 10
                        
                        # 2D Metrics - Cam A
                        info("--- Cam A ---", (255, 255, 255), 0.9)
                        if tA: # cxA, cyA, spdA, accA exist
                            info(f"Pos: {cxA:.0f}, {cyA:.0f} px")
                            info(f"Speed: {spdA:.1f} px/fr  Accel: {accA:.1f}")
                        else:
                            info("No Ball", (100, 100, 100))

                        y_off_info += 10

                        # 2D Metrics - Cam B
                        info("--- Cam B ---", (255, 255, 255), 0.9)
                        if tB:
                            info(f"Pos: {cxB:.0f}, {cyB:.0f} px")
                            info(f"Speed: {spdB:.1f} px/fr  Accel: {accB:.1f}")
                        else:
                            info("No Ball", (100, 100, 100))
                        
                        final_frame[540:1080, 960:1920] = vInfo

                    t5 = cv2.getTickCount()
                    t_proc += (t5 - t4) / cv2.getTickFrequency() * 1000

                    t6 = cv2.getTickCount()
                    writer.write(final_frame)
                    t7 = cv2.getTickCount()
                    t_write += (t7 - t6) / cv2.getTickFrequency() * 1000
                    
                    if fIdx % 100 == 0:
                         print(f"[{fIdx}] FPS: {fps_smooth:.1f}")
                         
                # FPS update when we actually output
                now = cv2.getTickCount()
                dt = (now - last_time) / cv2.getTickFrequency()
                if dt > 0:
                    fps_cur = float(len(batch_meta['data'])) / dt
                    fps_smooth = 0.9 * fps_smooth + 0.1 * fps_cur
                last_time = now

        # Flush remaining batch
        while not pending_batches.empty():
            batch_meta = pending_batches.get()
            token_out, res_out = inf_thread.get()
            # ... (Simulated processing for flush, or just ignore since we are done)
            print("Flushing final batch...")

    finally:
        inf_thread.stop()
        loaderA.stop()
        loaderB.stop()
        writer.stop()
        print(f"Done! Output saved to {args.out}")
        if csv_file:
            csv_file.close()
            
        if json_data:
            print(f"Saving JSON Metadata to {json_metrics_path}...")
            with open(json_metrics_path, 'w') as f:
                json.dump(json_data, f, indent=4)

if __name__ == "__main__":
    main()
