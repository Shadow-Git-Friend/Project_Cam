#!/usr/bin/env python3
"""
Fast Goal Detector - 2D Homography-based real-time goal detection.

This script provides fast (<20ms) goal detection using:
1. YOLO ball detection
2. Homography transformation to target wall plane
3. Point-in-polygon check for goal zones

Usage:
    python fast_goal_detector.py --camera 0 --homography config/homography.npy
    python fast_goal_detector.py --video test_kick.mp4 --calibrate  # To create homography
"""

import cv2
import numpy as np
import argparse
import time
import json
from pathlib import Path
from datetime import datetime

try:
    from ultralytics import YOLO
except ImportError:
    print("[ERROR] ultralytics not installed. Run: pip install ultralytics")
    exit(1)

# --- PATHS ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_DIR.mkdir(exist_ok=True)

# --- COLORS ---
GREEN = (0, 255, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
CYAN = (255, 255, 0)
WHITE = (255, 255, 255)


class GoalZone:
    """Represents a target zone on the wall."""
    def __init__(self, zone_id: int, corners: np.ndarray, name: str = ""):
        self.id = zone_id
        self.corners = np.array(corners, dtype=np.float32)  # 4 corners in wall coords
        self.name = name or f"Zone {zone_id}"
    
    def contains(self, point: np.ndarray) -> bool:
        """Check if point is inside zone polygon."""
        return cv2.pointPolygonTest(self.corners, tuple(point.flatten()), False) >= 0


class HomographyCalibrator:
    """Interactive tool to define homography by clicking 4 corners."""
    
    def __init__(self, frame: np.ndarray):
        self.frame = frame.copy()
        self.points = []
        self.window_name = "Click 4 corners of target wall (TL, TR, BR, BL)"
        
    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(self.points) < 4:
            self.points.append([x, y])
            cv2.circle(self.frame, (x, y), 5, GREEN, -1)
            if len(self.points) > 1:
                cv2.line(self.frame, tuple(self.points[-2]), tuple(self.points[-1]), GREEN, 2)
            if len(self.points) == 4:
                cv2.line(self.frame, tuple(self.points[3]), tuple(self.points[0]), GREEN, 2)
            cv2.imshow(self.window_name, self.frame)
    
    def calibrate(self, wall_width_m: float = 4.5, wall_height_m: float = 2.0) -> np.ndarray:
        """
        Interactive calibration. Click 4 corners of target wall.
        Returns homography matrix.
        """
        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self.mouse_callback)
        cv2.imshow(self.window_name, self.frame)
        
        print(f"[INFO] Click 4 corners of the target wall:")
        print("       1. Top-Left, 2. Top-Right, 3. Bottom-Right, 4. Bottom-Left")
        print("       Press 'r' to reset, 'q' to quit, Enter when done")
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('r'):
                self.points = []
                self.frame = self.frame.copy()
                cv2.imshow(self.window_name, self.frame)
            elif key == ord('q'):
                cv2.destroyAllWindows()
                return None
            elif key == 13 and len(self.points) == 4:  # Enter
                break
        
        cv2.destroyAllWindows()
        
        # Source points (image coordinates)
        src_pts = np.array(self.points, dtype=np.float32)
        
        # Destination points (wall coordinates in cm for precision)
        wall_w = wall_width_m * 100
        wall_h = wall_height_m * 100
        dst_pts = np.array([
            [0, 0],
            [wall_w, 0],
            [wall_w, wall_h],
            [0, wall_h]
        ], dtype=np.float32)
        
        H = cv2.getPerspectiveTransform(src_pts, dst_pts)
        return H


class FastGoalDetector:
    """Fast 2D homography-based goal detector."""
    
    def __init__(self, 
                 model_path: str = None,
                 homography_path: str = None,
                 conf_threshold: float = 0.5):
        
        # Load YOLO model
        if model_path is None:
            model_path = PROJECT_ROOT / "yolo11s_custom_ball.pt"
            if not model_path.exists():
                model_path = "yolov8n.pt"  # Fallback to pretrained
        
        print(f"[INFO] Loading model: {model_path}")
        self.model = YOLO(str(model_path))
        self.conf_threshold = conf_threshold
        
        # Ball class ID (0 for custom model, 32 for COCO sports ball)
        self.ball_class_id = 0
        
        # Homography matrix
        self.H = None
        if homography_path and Path(homography_path).exists():
            self.H = np.load(homography_path)
            print(f"[INFO] Loaded homography from {homography_path}")
        
        # Goal zones (default 3x3 grid)
        self.zones = []
        self.wall_width = 450  # cm
        self.wall_height = 200  # cm
        
        # Stats
        self.frame_times = []
        self.goal_events = []
        
    def setup_zones(self, grid_cols: int = 3, grid_rows: int = 3):
        """Create goal zones as a grid."""
        self.zones = []
        zone_w = self.wall_width / grid_cols
        zone_h = self.wall_height / grid_rows
        
        zone_id = 1
        for row in range(grid_rows):
            for col in range(grid_cols):
                x1 = col * zone_w
                y1 = row * zone_h
                corners = np.array([
                    [x1, y1],
                    [x1 + zone_w, y1],
                    [x1 + zone_w, y1 + zone_h],
                    [x1, y1 + zone_h]
                ], dtype=np.float32)
                self.zones.append(GoalZone(zone_id, corners))
                zone_id += 1
        
        print(f"[INFO] Created {len(self.zones)} goal zones ({grid_cols}x{grid_rows})")
    
    def detect_ball(self, frame: np.ndarray) -> tuple:
        """
        Detect ball in frame.
        Returns (center_x, center_y, confidence) or (None, None, None)
        """
        results = self.model.predict(
            frame, 
            verbose=False, 
            conf=self.conf_threshold,
            classes=[self.ball_class_id]
        )
        
        if not results or len(results[0].boxes) == 0:
            return None, None, None
        
        # Get best detection
        box = results[0].boxes[0]
        x, y, w, h = box.xywh[0].cpu().numpy()
        conf = float(box.conf[0].cpu().numpy())
        
        return int(x), int(y), conf
    
    def transform_to_wall(self, x: int, y: int) -> np.ndarray:
        """Transform image point to wall coordinates using homography."""
        if self.H is None:
            return None
        
        pt = np.array([[[x, y]]], dtype=np.float32)
        wall_pt = cv2.perspectiveTransform(pt, self.H)
        return wall_pt[0][0]
    
    def check_goal(self, wall_point: np.ndarray) -> GoalZone:
        """Check if wall point is inside any goal zone."""
        if wall_point is None:
            return None
        
        for zone in self.zones:
            if zone.contains(wall_point):
                return zone
        return None
    
    def process_frame(self, frame: np.ndarray) -> dict:
        """
        Process single frame for goal detection.
        Returns dict with detection results and timing.
        """
        start_time = time.perf_counter()
        
        result = {
            'ball_detected': False,
            'ball_pos': None,
            'wall_pos': None,
            'goal': False,
            'zone': None,
            'time_ms': 0
        }
        
        # Detect ball
        x, y, conf = self.detect_ball(frame)
        
        if x is not None:
            result['ball_detected'] = True
            result['ball_pos'] = (x, y)
            result['confidence'] = conf
            
            # Transform to wall coordinates
            wall_pt = self.transform_to_wall(x, y)
            if wall_pt is not None:
                result['wall_pos'] = wall_pt.tolist()
                
                # Check for goal
                zone = self.check_goal(wall_pt)
                if zone:
                    result['goal'] = True
                    result['zone'] = zone.id
        
        result['time_ms'] = (time.perf_counter() - start_time) * 1000
        self.frame_times.append(result['time_ms'])
        
        if result['goal']:
            event = {
                'timestamp': datetime.now().isoformat(),
                'zone': result['zone'],
                'wall_pos': result['wall_pos']
            }
            self.goal_events.append(event)
            print(f"[GOAL!] Zone {result['zone']} at {result['wall_pos']}")
        
        return result
    
    def draw_overlay(self, frame: np.ndarray, result: dict) -> np.ndarray:
        """Draw detection overlay on frame."""
        overlay = frame.copy()
        
        # Draw ball detection
        if result['ball_detected']:
            x, y = result['ball_pos']
            cv2.circle(overlay, (x, y), 10, YELLOW, 2)
            cv2.circle(overlay, (x, y), 3, YELLOW, -1)
            
            if result['goal']:
                cv2.putText(overlay, f"GOAL! Zone {result['zone']}", 
                           (x + 15, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.8, GREEN, 2)
            
            # Show wall coordinates
            if result['wall_pos']:
                wx, wy = result['wall_pos']
                cv2.putText(overlay, f"Wall: ({wx:.0f}, {wy:.0f}) cm", 
                           (x + 15, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.5, WHITE, 1)
        
        # Draw FPS and timing
        avg_time = np.mean(self.frame_times[-30:]) if self.frame_times else 0
        fps = 1000 / avg_time if avg_time > 0 else 0
        cv2.putText(overlay, f"FPS: {fps:.1f} | Latency: {result['time_ms']:.1f}ms", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, GREEN, 2)
        
        # Draw goal count
        cv2.putText(overlay, f"Goals: {len(self.goal_events)}", 
                   (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, CYAN, 2)
        
        return overlay
    
    def get_stats(self) -> dict:
        """Get performance statistics."""
        if not self.frame_times:
            return {}
        
        return {
            'avg_latency_ms': np.mean(self.frame_times),
            'min_latency_ms': np.min(self.frame_times),
            'max_latency_ms': np.max(self.frame_times),
            'fps': 1000 / np.mean(self.frame_times),
            'total_goals': len(self.goal_events),
            'goals_by_zone': self._count_goals_by_zone()
        }
    
    def _count_goals_by_zone(self) -> dict:
        counts = {}
        for event in self.goal_events:
            zone = event['zone']
            counts[zone] = counts.get(zone, 0) + 1
        return counts


def main():
    parser = argparse.ArgumentParser(description="Fast 2D Goal Detector")
    parser.add_argument("--camera", type=int, default=0, help="Camera ID")
    parser.add_argument("--video", type=str, help="Video file instead of camera")
    parser.add_argument("--model", type=str, help="YOLO model path")
    parser.add_argument("--homography", type=str, help="Homography matrix .npy file")
    parser.add_argument("--calibrate", action="store_true", help="Calibrate homography")
    parser.add_argument("--conf", type=float, default=0.5, help="Detection confidence")
    parser.add_argument("--zones", type=str, default="3x3", help="Zone grid (e.g., 3x3)")
    args = parser.parse_args()
    
    # Open video source
    if args.video:
        cap = cv2.VideoCapture(args.video)
        if not cap.isOpened():
            print(f"[ERROR] Cannot open video: {args.video}")
            return
    else:
        cap = cv2.VideoCapture(args.camera)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
    # Homography calibration mode
    if args.calibrate:
        print("[INFO] Calibration mode - capturing frame...")
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Cannot read frame")
            return
        
        calibrator = HomographyCalibrator(frame)
        H = calibrator.calibrate()
        
        if H is not None:
            save_path = CONFIG_DIR / "homography.npy"
            np.save(save_path, H)
            print(f"[SUCCESS] Homography saved to {save_path}")
        
        cap.release()
        return
    
    # Initialize detector
    homography_path = args.homography or (CONFIG_DIR / "homography.npy")
    detector = FastGoalDetector(
        model_path=args.model,
        homography_path=str(homography_path) if Path(homography_path).exists() else None,
        conf_threshold=args.conf
    )
    
    # Setup zones
    cols, rows = map(int, args.zones.split('x'))
    detector.setup_zones(cols, rows)
    
    if detector.H is None:
        print("[WARN] No homography loaded. Run with --calibrate first.")
        print("[INFO] Running in detection-only mode (no goal zones)")
    
    print("[INFO] Starting detection. Press 'q' to quit, 's' for stats")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            if args.video:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Loop video
                continue
            break
        
        result = detector.process_frame(frame)
        overlay = detector.draw_overlay(frame, result)
        
        cv2.imshow("Fast Goal Detector", overlay)
        
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            stats = detector.get_stats()
            print("\n--- Performance Stats ---")
            for k, v in stats.items():
                print(f"  {k}: {v}")
            print("-------------------------\n")
    
    cap.release()
    cv2.destroyAllWindows()
    
    # Final stats
    print("\n=== Final Statistics ===")
    stats = detector.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")
    
    # Save events
    if detector.goal_events:
        events_path = PROJECT_ROOT / f"goal_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(events_path, 'w') as f:
            json.dump(detector.goal_events, f, indent=2)
        print(f"[INFO] Events saved to {events_path}")


if __name__ == "__main__":
    main()
