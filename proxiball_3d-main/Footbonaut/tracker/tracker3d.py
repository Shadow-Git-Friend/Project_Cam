import numpy as np
import time

class Tracker3D:
    """
    3D Ball Tracker for computing metric speed from XYZ coordinates.
    Maintains a history of 3D positions with timestamps to calculate
    real-world velocity in meters per second.
    """
    
    def __init__(self, history_len=10, alpha_smooth=0.7):
        """
        Args:
            history_len: Number of recent 3D positions to store
            alpha_smooth: Smoothing factor for velocity (0-1, higher = more smoothing)
        """
        self.history_len = history_len
        self.alpha_smooth = alpha_smooth
        
        # History: list of (X, Y, Z, timestamp) tuples
        self.history = []
        
        # Current state
        self.position = None  # (X, Y, Z)
        self.velocity = 0.0   # m/s
        self.vx = 0.0         # m/s
        self.vy = 0.0         # m/s
        self.vz = 0.0         # m/s
        self.ax = 0.0         # m/s^2
        self.ay = 0.0
        self.az = 0.0
        self.accel = 0.0
        
    def update(self, pos_3d, timestamp=None):
        """
        Update tracker with new 3D position.
        
        Args:
            pos_3d: Tuple of (X, Y, Z) in meters
            timestamp: Time in seconds (uses time.time() if None)
            
        Returns:
            dict with current state including velocity
        """
        if pos_3d is None:
            return self.get_state()
            
        X, Y, Z = pos_3d
        
        if timestamp is None:
            timestamp = time.time()
            
        # Add to history
        self.history.append((X, Y, Z, timestamp))
        if len(self.history) > self.history_len:
            self.history.pop(0)
            
        self.position = (X, Y, Z)
        
        # Calculate velocity if we have at least 2 points
        if len(self.history) >= 2:
            # Use last two points for instantaneous velocity
            x1, y1, z1, t1 = self.history[-2]
            x2, y2, z2, t2 = self.history[-1]
            
            dt = t2 - t1
            
            if dt > 1e-6:  # Avoid division by zero
                # Instantaneous velocity components
                inst_vx = (x2 - x1) / dt
                inst_vy = (y2 - y1) / dt
                inst_vz = (z2 - z1) / dt
                inst_speed = np.sqrt(inst_vx**2 + inst_vy**2 + inst_vz**2)
                
                # Previous velocity for accel calc
                prev_vx = self.vx
                prev_vy = self.vy
                prev_vz = self.vz
                
                # Smooth velocity using EMA
                alpha = self.alpha_smooth
                self.vx = alpha * self.vx + (1 - alpha) * inst_vx
                self.vy = alpha * self.vy + (1 - alpha) * inst_vy
                self.vz = alpha * self.vz + (1 - alpha) * inst_vz
                self.velocity = alpha * self.velocity + (1 - alpha) * inst_speed
                
                # Acceleration (m/s^2) = (v_new - v_prev) / dt
                # Note: v_new here is the SMOOTHED velocity. 
                # Calculating accel from smoothed difference is often more stable than raw second derivative.
                inst_ax = (self.vx - prev_vx) / dt
                inst_ay = (self.vy - prev_vy) / dt
                inst_az = (self.vz - prev_vz) / dt
                inst_accel = np.sqrt(inst_ax**2 + inst_ay**2 + inst_az**2)
                
                self.ax = alpha * self.ax + (1 - alpha) * inst_ax
                self.ay = alpha * self.ay + (1 - alpha) * inst_ay
                self.az = alpha * self.az + (1 - alpha) * inst_az
                self.accel = alpha * self.accel + (1 - alpha) * inst_accel
                
        return self.get_state()
    
    def get_state(self):
        """
        Get current tracker state.
        
        Returns:
            dict with position, velocity, and velocity components
        """
        return {
            "position": self.position,
            "velocity": self.velocity,  # m/s
            "vx": self.vx,
            "vy": self.vy,
            "vz": self.vz,
            "accel": self.accel, # m/s^2
            "ax": self.ax,
            "ay": self.ay,
            "az": self.az,
            "history": [(x, y, z) for x, y, z, t in self.history],
        }
    
    def reset(self):
        """Reset tracker state."""
        self.history = []
        self.position = None
        self.velocity = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.ax = 0.0
        self.ay = 0.0
        self.az = 0.0
        self.accel = 0.0
