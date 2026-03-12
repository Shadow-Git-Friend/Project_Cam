import cv2
import time
import os
import sys
import threading
import queue
from datetime import datetime

# --- CONFIGURATION ---
CAM_ID_1 = 2
CAM_ID_2 = 4

# Resolution (1080p is heavy, ensure USB 3.0 or separate buses if possible)
FRAME_WIDTH = 1920
FRAME_HEIGHT = 1080
FPS = 30.0

# Output Directory
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "recordings_stereo")

class VideoWriterWidget:
    """
    Writes video frames in a separate thread to avoid blocking the capture loop.
    """
    def __init__(self, filename, width, height, fps, fourcc_code='mp4v'):
        self.filename = filename
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc_code = fourcc_code
        self.writer = None
        self.queue = queue.Queue()
        self.is_running = False
        self.thread = None
        self.frame_count = 0

    def start(self):
        fourcc = cv2.VideoWriter_fourcc(*self.fourcc_code)
        self.writer = cv2.VideoWriter(self.filename, fourcc, self.fps, (self.width, self.height))
        if not self.writer.isOpened():
            print(f"[ERROR] Could not open video writer: {self.filename}")
            return False
        
        self.is_running = True
        self.thread = threading.Thread(target=self._write_loop, daemon=True)
        self.thread.start()
        return True

    def write(self, frame):
        if self.is_running:
            self.queue.put(frame)

    def _write_loop(self):
        while self.is_running or not self.queue.empty():
            try:
                frame = self.queue.get(timeout=0.1)
                if frame is not None:
                    self.writer.write(frame)
                    self.frame_count += 1
            except queue.Empty:
                continue
    
    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join()
        if self.writer:
            self.writer.release()
        print(f"[writer] Saved {self.filename} ({self.frame_count} frames)")


class StereoCameraRecorder:
    def __init__(self, cam_id_1, cam_id_2):
        self.cam_id_1 = cam_id_1
        self.cam_id_2 = cam_id_2
        self.cap1 = None
        self.cap2 = None
        self.is_running = False
        self.is_recording = False
        
        # Writers (Threaded)
        self.writer1 = None
        self.writer2 = None

        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)

    def open_cameras(self):
        print(f"[INFO] Opening Camera {self.cam_id_1}...")
        self.cap1 = cv2.VideoCapture(self.cam_id_1)
        self.configure_cap(self.cap1)
        
        print(f"[INFO] Opening Camera {self.cam_id_2}...")
        self.cap2 = cv2.VideoCapture(self.cam_id_2)
        self.configure_cap(self.cap2)
        
        if not self.cap1.isOpened() or not self.cap2.isOpened():
            print("[ERROR] Failed to open one or both cameras.")
            return False
            
        print("[SUCCESS] Both cameras opened.")
        return True

    def configure_cap(self, cap):
        # 1. Set Format (MJPG is critical for 1080p USB bandwidth)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        
        # 2. Set Resolution
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, FPS)
        
        # 3. Disable Auto Exposure to fix low FPS in low light (Experimental)
        # 0.25 (manual) or 0.75 (auto). Value 1 or 0 might vary by driver.
        # Often -4, -5, -6 corresponds to exposure time powers of 2 (2^-4, etc)
        # cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25) 
        # cap.set(cv2.CAP_PROP_EXPOSURE, -5) # Try to force shorter exposure

    def start_recording(self):
        if self.is_recording: return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        f1 = os.path.join(OUTPUT_DIR, f"cam{self.cam_id_1}_{timestamp}.mp4")
        f2 = os.path.join(OUTPUT_DIR, f"cam{self.cam_id_2}_{timestamp}.mp4")

        self.writer1 = VideoWriterWidget(f1, FRAME_WIDTH, FRAME_HEIGHT, FPS)
        self.writer2 = VideoWriterWidget(f2, FRAME_WIDTH, FRAME_HEIGHT, FPS)
        
        if self.writer1.start() and self.writer2.start():
            self.is_recording = True
            print(f"[REC] Recording started...")
        else:
            print("[ERROR] Failed to start writers")
            self.stop_recording()

    def stop_recording(self):
        if not self.is_recording: return
        self.is_recording = False
        if self.writer1: self.writer1.stop()
        if self.writer2: self.writer2.stop()
        print(f"[STOP] Recording stopped.")

    def run(self):
        if not self.open_cameras(): return

        print("\n" + "="*50)
        print(" STEREO RECORDER v2 (Threaded)")
        print(" [SPACE]   - Start / Stop")
        print(" [Q]       - Quit")
        print(f" Resolution: {FRAME_WIDTH}x{FRAME_HEIGHT} @ {FPS} FPS")
        print("="*50 + "\n")

        self.is_running = True
        frames_in_period = 0
        last_time = time.time()
        
        while self.is_running:
            # --- 1. SYNC CAPTURE (Hardware Trigger) ---
            # grab() is fast and tells the camera to snap global shutter if possible
            self.cap1.grab()
            self.cap2.grab()
            
            # --- 2. DECODE ---
            # Sequential decode is usually fine if writing is threaded
            ret1, frame1 = self.cap1.retrieve()
            ret2, frame2 = self.cap2.retrieve()

            if not ret1 or not ret2:
                print(".", end="", flush=True) # Drop warning
                continue

            # --- 3. ASYNC WRITE ---
            if self.is_recording:
                self.writer1.write(frame1)
                self.writer2.write(frame2)
                
                # Visual Feedback
                cv2.circle(frame1, (30, 30), 10, (0, 0, 255), -1)
                cv2.circle(frame2, (30, 30), 10, (0, 0, 255), -1)

            # --- 4. DISPLAY ---
            # Only resize and show if we have CPU time, or skip some frames for display
            # Showing every frame at 1080p is expensive for imshow
            vis_small1 = cv2.resize(frame1, (0,0), fx=0.4, fy=0.4)
            vis_small2 = cv2.resize(frame2, (0,0), fx=0.4, fy=0.4)
            combined = getattr(cv2, 'hconcat', None)([vis_small1, vis_small2])
            
            cv2.imshow("Stereo Recorder", combined)

            # --- 5. FPS Counter ---
            frames_in_period += 1
            if time.time() - last_time >= 1.0:
                print(f"FPS: {frames_in_period}")
                frames_in_period = 0
                last_time = time.time()

            # --- 6. Input ---
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                self.stop_recording()
                self.is_running = False
            elif key == ord(' '):
                if self.is_recording: self.stop_recording()
                else: self.start_recording()

        self.cap1.release()
        self.cap2.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    app = StereoCameraRecorder(CAM_ID_1, CAM_ID_2)
    app.run()
