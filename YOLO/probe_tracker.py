"""
Probe Tracker - Maintains stable probe IDs across frames
Uses IOU-based tracking with velocity smoothing
"""

import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from probe_detector import Probe
from config import IOU_THRESHOLD, MAX_AGE, MIN_HITS


@dataclass
class TrackedProbe:
    """A probe being tracked across frames"""
    track_id: int
    probe: Probe
    age: int = 0  # Frames since last detection
    hits: int = 1  # Number of detections
    velocity: tuple = (0.0, 0.0)  # (vx, vy) per frame
    history: List[tuple] = field(default_factory=list)
    
    def update(self, probe: Probe):
        """Update track with new detection"""
        # Compute velocity
        vx = probe.x - self.probe.x
        vy = probe.y - self.probe.y
        
        # Smooth velocity
        alpha = 0.3
        self.velocity = (
            alpha * vx + (1 - alpha) * self.velocity[0],
            alpha * vy + (1 - alpha) * self.velocity[1]
        )
        
        # Update probe
        self.probe = probe
        self.probe.id = self.track_id  # Maintain stable ID
        self.age = 0
        self.hits += 1
        
        # Store history
        self.history.append((probe.x, probe.y))
        if len(self.history) > 30:
            self.history.pop(0)
            
    def predict(self) -> tuple:
        """Predict next position based on velocity"""
        px = self.probe.x + self.velocity[0]
        py = self.probe.y + self.velocity[1]
        return (px, py)
        
    def is_confirmed(self) -> bool:
        """Track is confirmed if seen enough times"""
        return self.hits >= MIN_HITS
        
    def is_expired(self) -> bool:
        """Track is expired if not seen for too long"""
        return self.age > MAX_AGE
        
    def to_dict(self) -> Dict:
        """Convert to dictionary for world state"""
        return {
            "id": self.track_id,
            "cx": self.probe.x,
            "cy": self.probe.y,
            "w": self.probe.w,
            "h": self.probe.h,
            "type": self.probe.class_name,
            "score": self.probe.confidence,
            "bbox": list(self.probe.bbox),
            "velocity": list(self.velocity),
            "confirmed": self.is_confirmed()
        }


class ProbeTracker:
    def __init__(self, iou_threshold: float = IOU_THRESHOLD):
        self.iou_threshold = iou_threshold
        self.tracks: List[TrackedProbe] = []
        self.next_track_id = 1
        self.frame_count = 0
        
    def update(self, detections: List[Probe]) -> List[TrackedProbe]:
        """
        Update tracks with new detections
        
        Args:
            detections: List of probes detected in current frame
            
        Returns:
            List of active tracked probes
        """
        self.frame_count += 1
        
        if not self.tracks:
            # Initialize tracks from first detections
            for det in detections:
                self._create_track(det)
            return self.get_active_tracks()
            
        # Compute IOU matrix
        iou_matrix = self._compute_iou_matrix(detections)
        
        # Greedy matching
        matched_tracks = set()
        matched_dets = set()
        
        # Sort by IOU (highest first)
        pairs = []
        for i, track in enumerate(self.tracks):
            for j, det in enumerate(detections):
                if iou_matrix[i, j] > self.iou_threshold:
                    pairs.append((iou_matrix[i, j], i, j))
                    
        pairs.sort(reverse=True)
        
        for iou, track_idx, det_idx in pairs:
            if track_idx in matched_tracks or det_idx in matched_dets:
                continue
            # Match track to detection
            self.tracks[track_idx].update(detections[det_idx])
            matched_tracks.add(track_idx)
            matched_dets.add(det_idx)
            
        # Age unmatched tracks
        for i, track in enumerate(self.tracks):
            if i not in matched_tracks:
                track.age += 1
                
        # Create new tracks for unmatched detections
        for j, det in enumerate(detections):
            if j not in matched_dets:
                self._create_track(det)
                
        # Remove expired tracks
        self.tracks = [t for t in self.tracks if not t.is_expired()]
        
        return self.get_active_tracks()
        
    def _compute_iou_matrix(self, detections: List[Probe]) -> np.ndarray:
        """Compute IOU between all tracks and detections"""
        n_tracks = len(self.tracks)
        n_dets = len(detections)
        iou_matrix = np.zeros((n_tracks, n_dets))
        
        for i, track in enumerate(self.tracks):
            for j, det in enumerate(detections):
                iou_matrix[i, j] = self._compute_iou(track.probe, det)
                
        return iou_matrix
        
    def _compute_iou(self, probe1: Probe, probe2: Probe) -> float:
        """Compute Intersection over Union between two probes"""
        x1_1, y1_1, x2_1, y2_1 = probe1.bbox
        x1_2, y1_2, x2_2, y2_2 = probe2.bbox
        
        # Intersection
        xi1 = max(x1_1, x1_2)
        yi1 = max(y1_1, y1_2)
        xi2 = min(x2_1, x2_2)
        yi2 = min(y2_1, y2_2)
        
        if xi2 <= xi1 or yi2 <= yi1:
            return 0.0
            
        inter_area = (xi2 - xi1) * (yi2 - yi1)
        
        # Union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union_area = area1 + area2 - inter_area
        
        if union_area <= 0:
            return 0.0
            
        return inter_area / union_area
        
    def _create_track(self, probe: Probe):
        """Create a new track from detection"""
        track = TrackedProbe(
            track_id=self.next_track_id,
            probe=probe
        )
        probe.id = self.next_track_id
        self.next_track_id += 1
        self.tracks.append(track)
        
    def get_active_tracks(self) -> List[TrackedProbe]:
        """Get all confirmed, non-expired tracks"""
        return [t for t in self.tracks if t.is_confirmed() and not t.is_expired()]
        
    def get_track_by_id(self, track_id: int) -> Optional[TrackedProbe]:
        """Get specific track by ID"""
        for track in self.tracks:
            if track.track_id == track_id:
                return track
        return None
        
    def get_probe_at_position(self, x: float, y: float, radius: float = 0.05) -> Optional[TrackedProbe]:
        """Find probe near a position"""
        for track in self.get_active_tracks():
            dx = track.probe.x - x
            dy = track.probe.y - y
            if (dx*dx + dy*dy) < radius*radius:
                return track
        return None
        
    def reset(self):
        """Clear all tracks"""
        self.tracks = []
        self.next_track_id = 1
        self.frame_count = 0
