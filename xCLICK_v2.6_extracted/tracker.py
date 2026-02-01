"""
xCLICK Tracker Module
Kalman filter for smooth object tracking between detection frames
Provides sub-frame position prediction for human-like cursor movement
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List
import time


@dataclass
class KalmanState:
    """State for 2D position + velocity Kalman filter"""
    # State: [x, y, vx, vy]
    x: np.ndarray = field(default_factory=lambda: np.zeros(4))
    # Covariance matrix
    P: np.ndarray = field(default_factory=lambda: np.eye(4) * 100)
    # Last update time
    last_update: float = 0.0
    

class KalmanTracker:
    """
    Kalman filter for tracking UI element positions between YOLO frames.
    Predicts position at 60Hz+ even when detection runs at 5-15Hz.
    """
    
    def __init__(self, process_noise: float = 0.1, measurement_noise: float = 1.0):
        # Process noise (how much we expect position to change)
        self.q = process_noise
        # Measurement noise (how noisy YOLO detections are)
        self.r = measurement_noise
        
        # Tracked objects: id -> KalmanState
        self.tracks: Dict[int, KalmanState] = {}
        
        # Measurement matrix: we observe [x, y]
        self.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])
        
        # Measurement noise covariance
        self.R = np.eye(2) * self.r
        
    def _get_F(self, dt: float) -> np.ndarray:
        """State transition matrix for given time delta"""
        return np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
    
    def _get_Q(self, dt: float) -> np.ndarray:
        """Process noise covariance for given time delta"""
        q = self.q
        dt2 = dt * dt
        dt3 = dt2 * dt
        dt4 = dt3 * dt
        return np.array([
            [dt4/4, 0, dt3/2, 0],
            [0, dt4/4, 0, dt3/2],
            [dt3/2, 0, dt2, 0],
            [0, dt3/2, 0, dt2]
        ]) * q
    
    def update(self, obj_id: int, cx: float, cy: float, timestamp: Optional[float] = None):
        """
        Update tracker with new measurement from YOLO/DOM detection.
        Call this when you get a new detection (5-15 Hz).
        """
        now = timestamp or time.monotonic()
        
        if obj_id not in self.tracks:
            # Initialize new track
            state = KalmanState()
            state.x = np.array([cx, cy, 0.0, 0.0])
            state.last_update = now
            self.tracks[obj_id] = state
            return
        
        state = self.tracks[obj_id]
        dt = now - state.last_update
        if dt <= 0:
            dt = 0.016  # Assume ~60Hz if no time diff
        
        # Predict step
        F = self._get_F(dt)
        Q = self._get_Q(dt)
        x_pred = F @ state.x
        P_pred = F @ state.P @ F.T + Q
        
        # Update step with measurement
        z = np.array([cx, cy])
        y = z - self.H @ x_pred  # Innovation
        S = self.H @ P_pred @ self.H.T + self.R  # Innovation covariance
        K = P_pred @ self.H.T @ np.linalg.inv(S)  # Kalman gain
        
        state.x = x_pred + K @ y
        state.P = (np.eye(4) - K @ self.H) @ P_pred
        state.last_update = now
    
    def predict(self, obj_id: int, timestamp: Optional[float] = None) -> Optional[Tuple[float, float]]:
        """
        Predict current position for smooth cursor movement.
        Call this at 60Hz+ for smooth tracking.
        Returns (x, y) or None if object not tracked.
        """
        if obj_id not in self.tracks:
            return None
        
        state = self.tracks[obj_id]
        now = timestamp or time.monotonic()
        dt = now - state.last_update
        
        # Predict forward
        F = self._get_F(dt)
        x_pred = F @ state.x
        
        return (x_pred[0], x_pred[1])
    
    def get_velocity(self, obj_id: int) -> Optional[Tuple[float, float]]:
        """Get current velocity estimate for an object"""
        if obj_id not in self.tracks:
            return None
        state = self.tracks[obj_id]
        return (state.x[2], state.x[3])
    
    def get_smoothed_bbox(self, obj_id: int, original_bbox: Tuple[float, float, float, float],
                          timestamp: Optional[float] = None) -> Tuple[float, float, float, float]:
        """
        Get smoothed bounding box using Kalman-predicted center.
        Maintains original width/height but smooths center position.
        """
        pred = self.predict(obj_id, timestamp)
        if pred is None:
            return original_bbox
        
        x1, y1, x2, y2 = original_bbox
        w = x2 - x1
        h = y2 - y1
        cx, cy = pred
        
        return (cx - w/2, cy - h/2, cx + w/2, cy + h/2)
    
    def remove_stale(self, max_age: float = 2.0, timestamp: Optional[float] = None):
        """Remove tracks not updated recently"""
        now = timestamp or time.monotonic()
        stale = [oid for oid, state in self.tracks.items() 
                 if now - state.last_update > max_age]
        for oid in stale:
            del self.tracks[oid]
    
    def clear(self):
        """Clear all tracks"""
        self.tracks.clear()


# Singleton instance
_tracker: Optional[KalmanTracker] = None

def get_tracker() -> KalmanTracker:
    """Get global Kalman tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = KalmanTracker()
    return _tracker

def reset_tracker():
    """Reset global tracker"""
    global _tracker
    _tracker = None
