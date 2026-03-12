# import threading
# import time
# import logging
# import cv2
# import numpy as np

# # A thread to handle V4L2 device capture asynchronously.

# class CameraThread(threading.Thread):
#     def __init__(self, name, device, width, height, fps):
#         super().__init__()
#         self.name = name
#         self.device = device
#         self.width = width
#         self.height = height
#         self.fps = fps
#         self.logger = logging.getLogger(f"CameraThread:{name}")
#         self.stop_event = threading.Event()
#         self._frame = None
#         self.frame_lock = threading.Lock()
        
#     @property
#     def frame(self):
#         with self.frame_lock:
#             return self._frame

#     def run(self):
#         cap = cv2.VideoCapture(self.device)
        
#         if not cap.isOpened():
#             self.logger.error(f"❌ Failed to open camera device: {self.device}")
#             self.stop()
#             return

#         cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
#         cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
#         cap.set(cv2.CAP_PROP_FPS, self.fps)
        
#         actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
#         actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#         self.logger.info(f"🟢 Started {self.name} at {self.device}. Actual resolution: {actual_width}x{actual_height}")
        
#         while not self.stop_event.is_set():
#             ret, frame = cap.read()
            
#             if ret:
#                 # Ensure the frame is scaled if necessary (or copied for safety)
#                 # We'll just use the frame as-is, assuming it matches the expected config size
#                 with self.frame_lock:
#                     self._frame = frame
#             else:
#                 self.logger.warning(f"🔴 Could not read frame from {self.name}.")
#                 time.sleep(0.01)

#         cap.release()
#         self.logger.info(f"🛑 Thread stopped for {self.name}.")

#     def stop(self):
#         self.stop_event.set()
# src/capture/camera_thread.py

import threading
import time
import cv2
import logging

class CameraThread(threading.Thread):
    def __init__(self, name: str, url: str, width: int, height: int, fps: int):
        super().__init__(daemon=True)
        self.name = name
        self.url = url
        self.width = width
        self.height = height
        self.fps = fps
        self.logger = logging.getLogger(f"Cam-{name}")
        self.stop_event = threading.Event()
        self.frame = None
        self.lock = threading.Lock()

    def run(self):
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        if not cap.isOpened():
            self.logger.error(f"Не открыть {self.name}: {self.url}")
            return

        self.logger.info(f"{self.name} запущен")

        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if ret:
                with self.lock:
                    self.frame = frame.copy()
            else:
                time.sleep(0.01)

        cap.release()

    def get_frame(self):
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def stop(self):
        self.stop_event.set()
