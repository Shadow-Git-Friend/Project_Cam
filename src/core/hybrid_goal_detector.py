#!/usr/bin/env python3
"""
Hybrid Goal Detector - 2D Trigger + 3D Confirmation

This script combines:
1. Fast 2D detection (homography) for quick trigger (~10ms)
2. 3D triangulation for accurate confirmation (~15ms additional)

Lab Testing Mode:
- Works without physical targets
- Define virtual 3D zones in space
- Test with any ball/object thrown in the air

Usage:
    # Lab testing (no targets, just 3D tracking)
    python hybrid_goal_detector.py --mode lab --cameras 0,2

    # 2D only (fast, single camera)
    python hybrid_goal_detector.py --mode 2d --camera 0

    # Hybrid (2D trigger + 3D confirm)
    python hybrid_goal_detector.py --mode hybrid --cameras 0,2,4,6

    # Full 3D (all triangulation)
    python hybrid_goal_detector.py --mode 3d --cameras 0,2
"""

import cv2
import numpy as np
import argparse
import time
import json
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from collections import deque

try:
    from ultralytics import YOLO
except ImportError:
    print("[ERROR] ultralytics not installed. Run: pip install ultralytics")
    exit(1)

# --- PATHS ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CAL_DIR = PROJECT_ROOT / "cal" / "calibration_v2"
CONFIG_DIR.mkdir(exist_ok=True)

# --- COLORS ---
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
CYAN = (255, 255, 0)
WHITE = (255, 255, 255)
ORANGE = (0, 165, 255)
PURPLE = (255, 0, 255)


@dataclass
class CameraConfig:
    """Camera configuration with calibration data."""
    id: int
    cap: cv2.VideoCapture
    intrinsics: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    extrinsics: Optional[np.ndarray] = None  # 4x4 transform to world
    homography: Optional[np.ndarray] = None  # For 2D mode
    
    
@dataclass
class Detection3D:
    """3D detection result."""
    position: np.ndarray  # [x, y, z] in mm
    confidence: float
    timestamp: float
    cameras_used: List[int]
    reprojection_error: float


@dataclass
class GoalZone3D:
    """3D goal zone (box in space)."""
    id: int
    name: str
    center: np.ndarray  # [x, y, z] center in mm
    size: np.ndarray    # [width, height, depth] in mm
    normal: np.ndarray  # Wall normal direction
    
    def contains(self, point: np.ndarray) -> bool:
        """Check if 3D point is inside zone."""
        relative = point - self.center
        half = self.size / 2
        return (abs(relative[0]) <= half[0] and 
                abs(relative[1]) <= half[1] and 
                abs(relative[2]) <= half[2])
    
    def distance_to_plane(self, point: np.ndarray) -> float:
        """Distance from point to zone plane."""
        relative = point - self.center
        return np.dot(relative, self.normal)


class Triangulator:
    """3D triangulation from multiple camera views."""
    
    def __init__(self):
        self.projection_matrices: Dict[int, np.ndarray] = {}
        
    def add_camera(self, cam_id: int, K: np.ndarray, extrinsics: np.ndarray):
        """Add camera with intrinsics K and extrinsics (4x4 world-to-camera)."""
        # Projection matrix P = K @ [R|t]
        R = extrinsics[:3, :3]
        t = extrinsics[:3, 3]
        Rt = np.hstack([R, t.reshape(3, 1)])
        P = K @ Rt
        self.projection_matrices[cam_id] = P
        
    def triangulate(self, observations: Dict[int, Tuple[float, float]]) -> Optional[Detection3D]:
        """
        Triangulate 3D point from 2D observations.
        observations: {cam_id: (x, y)} pixel coordinates
        """
        if len(observations) < 2:
            return None
            
        cam_ids = list(observations.keys())
        
        # Build DLT matrix
        A = []
        for cam_id in cam_ids:
            if cam_id not in self.projection_matrices:
                continue
            P = self.projection_matrices[cam_id]
            x, y = observations[cam_id]
            A.append(x * P[2] - P[0])
            A.append(y * P[2] - P[1])
        
        if len(A) < 4:
            return None
            
        A = np.array(A)
        
        # SVD solution
        _, _, Vt = np.linalg.svd(A)
        X = Vt[-1]
        X = X[:3] / X[3]  # Dehomogenize
        
        # Calculate reprojection error
        errors = []
        for cam_id in cam_ids:
            if cam_id not in self.projection_matrices:
                continue
            P = self.projection_matrices[cam_id]
            proj = P @ np.append(X, 1)
            proj = proj[:2] / proj[2]
            obs = np.array(observations[cam_id])
            errors.append(np.linalg.norm(proj - obs))
        
        return Detection3D(
            position=X,
            confidence=1.0 / (1.0 + np.mean(errors)),
            timestamp=time.time(),
            cameras_used=cam_ids,
            reprojection_error=np.mean(errors)
        )


class HybridGoalDetector:
    """Hybrid 2D/3D goal detection system."""
    
    def __init__(self, 
                 mode: str = "hybrid",
                 model_path: str = None,
                 conf_threshold: float = 0.4):
        
        self.mode = mode  # "2d", "3d", "hybrid", "lab"
        self.conf_threshold = conf_threshold
        
        # Load YOLO model
        if model_path is None:
            model_path = PROJECT_ROOT / "yolo11s_custom_ball.pt"
            if not model_path.exists():
                model_path = "yolov8n.pt"
        
        print(f"[INFO] Loading model: {model_path}")
        self.model = YOLO(str(model_path))
        self.ball_class_id = 0  # Adjust based on model
        
        # Cameras
        self.cameras: Dict[int, CameraConfig] = {}
        
        # 3D triangulation
        self.triangulator = Triangulator()
        
        # Goal zones (3D)
        self.zones_3d: List[GoalZone3D] = []
        
        # 2D zones (for single-camera mode)
        self.zones_2d = []
        self.homography = None
        
        # Tracking
        self.ball_history: deque = deque(maxlen=30)
        self.last_3d_position: Optional[np.ndarray] = None
        
        # Stats
        self.frame_times = []
        self.goal_events = []
        
        # Threading for async 3D
        self.pending_3d_check = None
        self.lock = threading.Lock()
        
    def add_camera(self, cam_id: int, width: int = 1280, height: int = 720) -> bool:
        """Add and initialize a camera."""
        cap = cv2.VideoCapture(cam_id)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open camera {cam_id}")
            return False
            
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce latency
        
        config = CameraConfig(id=cam_id, cap=cap)
        
        # Try to load calibration
        self._load_camera_calibration(config)
        
        self.cameras[cam_id] = config
        print(f"[INFO] Camera {cam_id} added ({width}x{height})")
        return True
        
    def _load_camera_calibration(self, config: CameraConfig):
        """Load intrinsics and extrinsics for camera."""
        cam_name = f"cam_{config.id}" # Note: JSON uses cam_0, cam_2
        
        # Path to new unified calibration file
        cal_path = PROJECT_ROOT / "cal" / "calibration_full.json"
        
        if cal_path.exists():
            try:
                with open(cal_path) as f:
                    data = json.load(f)
                
                if cam_name in data:
                    cam_data = data[cam_name]
                    
                    # Intrinsics
                    config.intrinsics = np.array(cam_data["K"], dtype=np.float64)
                    config.dist_coeffs = np.array(cam_data["D"], dtype=np.float64)
                    
                    # Extrinsics (R|T)
                    # We need 4x4 matrix
                    R = np.array(cam_data["R"], dtype=np.float64)
                    T = np.array(cam_data["T"], dtype=np.float64)
                    
                    # Convert to 4x4 Homogeneous
                    ext_mat = np.eye(4)
                    ext_mat[:3, :3] = R
                    ext_mat[:3, 3] = T.flatten()
                    
                    config.extrinsics = ext_mat
                    
                    # Add to triangulator
                    self.triangulator.add_camera(
                        config.id, 
                        config.intrinsics, 
                        config.extrinsics
                    )
                    print(f"[INFO] Loaded calibration for {cam_name} from {cal_path.name}")
                    return # Success
                    
            except Exception as e:
                print(f"[WARN] Failed to load calibration for {cam_name}: {e}")

        # --- OLD LEGACY LOADING (Fallback) ---
        print(f"[WARN] New calibration (cam_{config.id}) not found, trying legacy...")
        
        # Load intrinsics
        intrinsics_path = CAL_DIR / f"cam{config.id}_intrinsics.json"
        if intrinsics_path.exists():
            try:
                with open(intrinsics_path) as f:
                    data = json.load(f)
                config.intrinsics = np.array(data["camera_matrix"], dtype=np.float64)
                config.dist_coeffs = np.array(data["distortion_coefficients"], dtype=np.float64)
                print(f"[INFO] Loaded intrinsics for cam{config.id}")
            except Exception as e:
                print(f"[WARN] Failed to load intrinsics: {e}")
        
        # Load extrinsics
        extrinsics_path = CAL_DIR / "extrinsics.json"
        if extrinsics_path.exists() and config.intrinsics is not None:
             pass # Legacy logic omitted for brevity as we want to succeed with new file
        
        # Load homography (for 2D mode)
        homography_path = CONFIG_DIR / f"cam{config.id}_homography.npy"
        if homography_path.exists():
            config.homography = np.load(homography_path)
            print(f"[INFO] Loaded homography for cam{config.id}")
    
    def setup_lab_zones(self, field_size: Tuple[float, float, float] = (3000, 3000, 2000)):
        """
        Set up virtual 3D zones for lab testing.
        Creates a grid of zones in 3D space to test tracking.
        field_size: (width, depth, height) in mm
        """
        self.zones_3d = []
        
        # Create 4 wall zones (one on each side of field)
        w, d, h = field_size
        
        # Front wall (Z+)
        self.zones_3d.append(GoalZone3D(
            id=1, name="Front",
            center=np.array([0, d/2, h/2]),
            size=np.array([1000, 100, 1000]),  # 1m x 1m target, 10cm thick
            normal=np.array([0, -1, 0])
        ))
        
        # Back wall (Z-)
        self.zones_3d.append(GoalZone3D(
            id=2, name="Back",
            center=np.array([0, -d/2, h/2]),
            size=np.array([1000, 100, 1000]),
            normal=np.array([0, 1, 0])
        ))
        
        # Left wall (X-)
        self.zones_3d.append(GoalZone3D(
            id=3, name="Left",
            center=np.array([-w/2, 0, h/2]),
            size=np.array([100, 1000, 1000]),
            normal=np.array([1, 0, 0])
        ))
        
        # Right wall (X+)
        self.zones_3d.append(GoalZone3D(
            id=4, name="Right",
            center=np.array([w/2, 0, h/2]),
            size=np.array([100, 1000, 1000]),
            normal=np.array([-1, 0, 0])
        ))
        
        print(f"[INFO] Created {len(self.zones_3d)} lab test zones")
        
    def setup_target_zones(self, 
                           wall_position: np.ndarray,
                           wall_normal: np.ndarray,
                           grid_cols: int = 3,
                           grid_rows: int = 3,
                           zone_size: Tuple[float, float] = (1000, 666)):
        """
        Set up 3D target zones on a wall.
        wall_position: Center of wall in 3D [x, y, z] mm
        wall_normal: Direction wall faces (into field)
        zone_size: (width, height) of each zone in mm
        """
        self.zones_3d = []
        
        # Calculate up and right vectors for wall
        up = np.array([0, 0, 1])
        right = np.cross(wall_normal, up)
        right = right / np.linalg.norm(right)
        
        total_width = grid_cols * zone_size[0]
        total_height = grid_rows * zone_size[1]
        
        zone_id = 1
        for row in range(grid_rows):
            for col in range(grid_cols):
                # Calculate zone center
                x_offset = (col - grid_cols/2 + 0.5) * zone_size[0]
                z_offset = (row - grid_rows/2 + 0.5) * zone_size[1]
                
                center = wall_position + right * x_offset + up * z_offset
                
                self.zones_3d.append(GoalZone3D(
                    id=zone_id,
                    name=f"Zone {zone_id}",
                    center=center,
                    size=np.array([zone_size[0], 200, zone_size[1]]),  # 20cm depth
                    normal=wall_normal
                ))
                zone_id += 1
        
        print(f"[INFO] Created {len(self.zones_3d)} target zones on wall")
        
    def detect_ball_2d(self, frame: np.ndarray) -> Optional[Tuple[int, int, float]]:
        """Fast 2D ball detection. Returns (x, y, conf) or None."""
        results = self.model.predict(
            frame, 
            verbose=False, 
            conf=self.conf_threshold,
            classes=[self.ball_class_id]
        )
        
        if not results or len(results[0].boxes) == 0:
            return None
            
        box = results[0].boxes[0]
        x, y, w, h = box.xywh[0].cpu().numpy()
        conf = float(box.conf[0].cpu().numpy())
        
        return int(x), int(y), conf
        
    def detect_ball_all_cameras(self) -> Dict[int, Tuple[int, int, float]]:
        """Detect ball in all cameras (for 3D triangulation)."""
        observations = {}
        frames = {}
        
        # Capture from all cameras
        for cam_id, config in self.cameras.items():
            ret, frame = config.cap.read()
            if ret:
                frames[cam_id] = frame
                
        # Detect in each frame
        for cam_id, frame in frames.items():
            result = self.detect_ball_2d(frame)
            if result:
                observations[cam_id] = (result[0], result[1])
                
        return observations, frames
        
    def triangulate_ball(self, observations: Dict[int, Tuple[int, int]]) -> Optional[Detection3D]:
        """Triangulate ball from 2D observations."""
        return self.triangulator.triangulate(observations)
        
    def check_goal_3d(self, position: np.ndarray) -> Optional[GoalZone3D]:
        """Check if 3D position is inside any goal zone."""
        for zone in self.zones_3d:
            if zone.contains(position):
                return zone
        return None
        
    def check_crossing(self, current: np.ndarray, previous: np.ndarray) -> Optional[GoalZone3D]:
        """Check if ball crossed any zone plane between frames."""
        if previous is None:
            return None
            
        for zone in self.zones_3d:
            # Check sign change in distance to plane
            d_curr = zone.distance_to_plane(current)
            d_prev = zone.distance_to_plane(previous)
            
            if d_curr * d_prev < 0:  # Crossed the plane
                # Interpolate crossing point
                t = d_prev / (d_prev - d_curr)
                crossing_point = previous + t * (current - previous)
                
                # Check if crossing is within zone bounds
                if zone.contains(crossing_point):
                    return zone
                    
        return None
        
    def process_frame_2d(self, frame: np.ndarray) -> dict:
        """Process single frame in 2D mode."""
        start = time.perf_counter()
        
        result = {
            'ball_detected': False,
            'ball_pos': None,
            'goal': False,
            'zone': None,
            'time_ms': 0
        }
        
        detection = self.detect_ball_2d(frame)
        if detection:
            x, y, conf = detection
            result['ball_detected'] = True
            result['ball_pos'] = (x, y)
            result['confidence'] = conf
            
            # 2D goal check via homography
            if self.homography is not None:
                pt = np.array([[[x, y]]], dtype=np.float32)
                wall_pt = cv2.perspectiveTransform(pt, self.homography)[0][0]
                result['wall_pos'] = wall_pt.tolist()
                
                # Check 2D zones
                # (simplified - would check point in polygon)
                
        result['time_ms'] = (time.perf_counter() - start) * 1000
        return result
        
    def process_frame_3d(self) -> dict:
        """Process all cameras for 3D detection."""
        start = time.perf_counter()
        
        result = {
            'ball_detected': False,
            'position_3d': None,
            'goal': False,
            'zone': None,
            'cameras': [],
            'time_ms': 0
        }
        
        observations, frames = self.detect_ball_all_cameras()
        
        if len(observations) >= 2:
            detection = self.triangulate_ball(observations)
            
            if detection and detection.reprojection_error < 50:  # Max 50px error
                result['ball_detected'] = True
                result['position_3d'] = detection.position.tolist()
                result['cameras'] = detection.cameras_used
                result['confidence'] = detection.confidence
                result['reprojection_error'] = detection.reprojection_error
                
                # Check for goal
                zone = self.check_goal_3d(detection.position)
                if zone:
                    result['goal'] = True
                    result['zone'] = zone.id
                    result['zone_name'] = zone.name
                    
                # Check for plane crossing
                crossing_zone = self.check_crossing(detection.position, self.last_3d_position)
                if crossing_zone:
                    result['goal'] = True 
                    result['zone'] = crossing_zone.id
                    result['zone_name'] = crossing_zone.name
                    result['crossing'] = True
                    
                self.last_3d_position = detection.position
                self.ball_history.append(detection.position)
                
        result['time_ms'] = (time.perf_counter() - start) * 1000
        result['frames'] = frames
        return result
        
    def process_frame_hybrid(self, primary_cam: int = None) -> dict:
        """
        Hybrid processing: fast 2D check, then 3D if needed.
        """
        start = time.perf_counter()
        
        # If no primary, use first camera
        if primary_cam is None:
            primary_cam = list(self.cameras.keys())[0]
            
        result = {
            'mode': 'hybrid',
            'ball_detected': False,
            'position_3d': None,
            'goal': False,
            'zone': None,
            'time_ms': 0,
            'time_2d_ms': 0,
            'time_3d_ms': 0
        }
        
        # Step 1: Fast 2D detection on primary camera
        t_2d_start = time.perf_counter()
        ret, frame = self.cameras[primary_cam].cap.read()
        if not ret:
            return result
            
        detection_2d = self.detect_ball_2d(frame)
        result['time_2d_ms'] = (time.perf_counter() - t_2d_start) * 1000
        
        if detection_2d:
            x, y, conf = detection_2d
            result['ball_detected'] = True
            result['ball_pos_2d'] = (x, y)
            result['primary_frame'] = frame
            
            # Step 2: 3D triangulation for confirmation
            t_3d_start = time.perf_counter()
            
            # Get detections from other cameras
            observations = {primary_cam: (x, y)}
            frames = {primary_cam: frame}
            
            for cam_id, config in self.cameras.items():
                if cam_id == primary_cam:
                    continue
                ret, other_frame = config.cap.read()
                if ret:
                    frames[cam_id] = other_frame
                    other_det = self.detect_ball_2d(other_frame)
                    if other_det:
                        observations[cam_id] = (other_det[0], other_det[1])
            
            # Triangulate
            if len(observations) >= 2:
                detection_3d = self.triangulate_ball(observations)
                
                if detection_3d and detection_3d.reprojection_error < 50:
                    result['position_3d'] = detection_3d.position.tolist()
                    result['cameras'] = detection_3d.cameras_used
                    result['reprojection_error'] = detection_3d.reprojection_error
                    
                    # Check goals
                    zone = self.check_goal_3d(detection_3d.position)
                    if zone:
                        result['goal'] = True
                        result['zone'] = zone.id
                        result['zone_name'] = zone.name
                        
                    crossing = self.check_crossing(detection_3d.position, self.last_3d_position)
                    if crossing:
                        result['goal'] = True
                        result['zone'] = crossing.id
                        result['zone_name'] = crossing.name
                        result['crossing'] = True
                        
                    self.last_3d_position = detection_3d.position
                    
            result['time_3d_ms'] = (time.perf_counter() - t_3d_start) * 1000
            result['frames'] = frames
            
        result['time_ms'] = (time.perf_counter() - start) * 1000
        self.frame_times.append(result['time_ms'])
        
        if result['goal']:
            event = {
                'timestamp': datetime.now().isoformat(),
                'zone': result['zone'],
                'zone_name': result.get('zone_name', ''),
                'position_3d': result.get('position_3d'),
                'mode': 'hybrid'
            }
            self.goal_events.append(event)
            print(f"[GOAL!] {result.get('zone_name', 'Zone ' + str(result['zone']))}")
            
        return result
        
    def draw_overlay(self, frame: np.ndarray, result: dict, cam_id: int = 0) -> np.ndarray:
        """Draw detection overlay."""
        overlay = frame.copy()
        h, w = overlay.shape[:2]
        
        # Draw ball detection
        if result.get('ball_pos_2d'):
            x, y = result['ball_pos_2d']
            color = GREEN if result.get('goal') else YELLOW
            cv2.circle(overlay, (x, y), 15, color, 3)
            cv2.circle(overlay, (x, y), 5, color, -1)
            
        # Draw 3D position
        if result.get('position_3d'):
            pos = result['position_3d']
            text = f"3D: X={pos[0]:.0f} Y={pos[1]:.0f} Z={pos[2]:.0f} mm"
            cv2.putText(overlay, text, (10, h - 60), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, CYAN, 2)
                       
        # Draw goal notification
        if result.get('goal'):
            zone_name = result.get('zone_name', f"Zone {result['zone']}")
            cv2.putText(overlay, f"GOAL! {zone_name}", (w//2 - 100, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.2, GREEN, 3)
                       
        # Draw timing info
        timing_text = f"Mode: {self.mode.upper()} | "
        if 'time_2d_ms' in result:
            timing_text += f"2D: {result['time_2d_ms']:.1f}ms | "
        if 'time_3d_ms' in result:
            timing_text += f"3D: {result['time_3d_ms']:.1f}ms | "
        timing_text += f"Total: {result['time_ms']:.1f}ms"
        
        avg_time = np.mean(self.frame_times[-30:]) if self.frame_times else 0
        fps = 1000 / avg_time if avg_time > 0 else 0
        
        cv2.putText(overlay, timing_text, (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
        cv2.putText(overlay, f"FPS: {fps:.1f} | Goals: {len(self.goal_events)}", 
                   (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)
                   
        # Draw camera info
        if result.get('cameras'):
            cam_text = f"Cameras: {result['cameras']}"
            cv2.putText(overlay, cam_text, (10, h - 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1)
                       
        return overlay
        
    def run(self, show_all_cameras: bool = False):
        """Main detection loop."""
        print(f"\n[INFO] Running in {self.mode.upper()} mode")
        print("[INFO] Press 'q' to quit, 's' for stats, 'm' to change mode")
        
        while True:
            if self.mode == "2d":
                # 2D mode - single camera
                cam_id = list(self.cameras.keys())[0]
                ret, frame = self.cameras[cam_id].cap.read()
                if not ret:
                    continue
                result = self.process_frame_2d(frame)
                result['primary_frame'] = frame
                
            elif self.mode == "3d":
                result = self.process_frame_3d()
                
            elif self.mode in ["hybrid", "lab"]:
                result = self.process_frame_hybrid()
                
            else:
                print(f"[ERROR] Unknown mode: {self.mode}")
                break
                
            # Display
            if 'primary_frame' in result:
                overlay = self.draw_overlay(result['primary_frame'], result)
                cv2.imshow(f"Hybrid Goal Detector - {self.mode.upper()}", overlay)
                
            # Show all cameras if requested
            if show_all_cameras and 'frames' in result:
                for cam_id, frame in result['frames'].items():
                    cv2.imshow(f"Camera {cam_id}", frame)
                    
            # Handle keys
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                self._print_stats()
            elif key == ord('m'):
                # Cycle modes
                modes = ["2d", "hybrid", "3d", "lab"]
                idx = modes.index(self.mode)
                self.mode = modes[(idx + 1) % len(modes)]
                print(f"[INFO] Switched to {self.mode.upper()} mode")
                
        self.cleanup()
        
    def _print_stats(self):
        """Print performance statistics."""
        if not self.frame_times:
            print("[INFO] No data yet")
            return
            
        print("\n=== Performance Stats ===")
        print(f"  Mode: {self.mode}")
        print(f"  Avg latency: {np.mean(self.frame_times):.1f}ms")
        print(f"  Min latency: {np.min(self.frame_times):.1f}ms")
        print(f"  Max latency: {np.max(self.frame_times):.1f}ms")
        print(f"  FPS: {1000 / np.mean(self.frame_times):.1f}")
        print(f"  Total goals: {len(self.goal_events)}")
        print("=========================\n")
        
    def cleanup(self):
        """Release resources."""
        for config in self.cameras.values():
            config.cap.release()
        cv2.destroyAllWindows()
        
        # Save events
        if self.goal_events:
            path = PROJECT_ROOT / f"goal_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(path, 'w') as f:
                json.dump(self.goal_events, f, indent=2)
            print(f"[INFO] Events saved to {path}")


def main():
    parser = argparse.ArgumentParser(description="Hybrid 2D/3D Goal Detector")
    parser.add_argument("--mode", type=str, default="lab",
                       choices=["2d", "3d", "hybrid", "lab"],
                       help="Detection mode")
    parser.add_argument("--cameras", type=str, default="0",
                       help="Comma-separated camera IDs (e.g., 0,2,4)")
    parser.add_argument("--model", type=str, help="YOLO model path")
    parser.add_argument("--conf", type=float, default=0.4, help="Detection confidence")
    parser.add_argument("--show-all", action="store_true", help="Show all camera feeds")
    parser.add_argument("--width", type=int, default=1280, help="Camera width")
    parser.add_argument("--height", type=int, default=720, help="Camera height")
    args = parser.parse_args()
    
    # Parse camera IDs
    cam_ids = [int(x.strip()) for x in args.cameras.split(",")]
    
    # Check mode requirements
    if args.mode in ["3d", "hybrid", "lab"] and len(cam_ids) < 2:
        print("[WARN] 3D/hybrid modes work best with 2+ cameras")
        print("[INFO] Falling back to 2D mode")
        args.mode = "2d"
        
    # Initialize detector
    detector = HybridGoalDetector(
        mode=args.mode,
        model_path=args.model,
        conf_threshold=args.conf
    )
    
    # Add cameras
    for cam_id in cam_ids:
        if not detector.add_camera(cam_id, args.width, args.height):
            print(f"[ERROR] Failed to add camera {cam_id}")
            return
            
    # Setup zones
    if args.mode == "lab":
        detector.setup_lab_zones()
    else:
        # Default wall at Y=5000mm (5m away)
        detector.setup_target_zones(
            wall_position=np.array([0, 5000, 1000]),
            wall_normal=np.array([0, -1, 0]),
            grid_cols=3,
            grid_rows=3
        )
        
    # Run
    detector.run(show_all_cameras=args.show_all)


if __name__ == "__main__":
    main()
