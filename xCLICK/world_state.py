"""
xCLICK World State Model
Persistent object tracking across frames with stability scoring
Now includes Kalman filter for smooth position prediction
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

# Kalman tracker for smooth predictions
from tracker import get_tracker, KalmanTracker


class ObjectSource(Enum):
    DOM = "dom"
    VISION = "vision"
    FUSED = "fused"


@dataclass
class TrackedObject:
    """A UI element tracked across frames with Kalman prediction"""
    id: int
    label: str
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2 in CSS pixels
    cx: float  # Center X (measured)
    cy: float  # Center Y (measured)
    obj_type: str  # button, input, link, etc.
    confidence: float
    source: ObjectSource
    
    # Tracking metadata
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    seen_count: int = 1
    stability_score: float = 1.0  # 0-1, higher = more stable
    
    # DOM-specific
    dom_id: Optional[str] = None
    tag: Optional[str] = None
    role: Optional[str] = None
    
    # Kalman-predicted position (updated by world state)
    _predicted_cx: Optional[float] = None
    _predicted_cy: Optional[float] = None
    
    @property
    def predicted_cx(self) -> float:
        """Get predicted X position (Kalman-smoothed) or measured if unavailable"""
        return self._predicted_cx if self._predicted_cx is not None else self.cx
    
    @property
    def predicted_cy(self) -> float:
        """Get predicted Y position (Kalman-smoothed) or measured if unavailable"""
        return self._predicted_cy if self._predicted_cy is not None else self.cy
    
    @property
    def predicted_position(self) -> Tuple[float, float]:
        """Get predicted (x, y) position for smooth motion targeting"""
        return (self.predicted_cx, self.predicted_cy)
    
    def update(self, new_bbox: Tuple[float, float, float, float], 
               new_confidence: float, new_label: Optional[str] = None):
        """Update object with new detection"""
        self.bbox = new_bbox
        self.cx = (new_bbox[0] + new_bbox[2]) / 2
        self.cy = (new_bbox[1] + new_bbox[3]) / 2
        self.confidence = new_confidence
        self.last_seen = time.time()
        self.seen_count += 1
        
        if new_label:
            self.label = new_label
        
        # Update stability based on consistency
        age = self.last_seen - self.first_seen
        if age > 0:
            self.stability_score = min(1.0, self.seen_count / (age * 10 + 1))
    
    @property
    def age_ms(self) -> float:
        """Time since first seen in milliseconds"""
        return (time.time() - self.first_seen) * 1000
    
    @property
    def stale_ms(self) -> float:
        """Time since last seen in milliseconds"""
        return (time.time() - self.last_seen) * 1000
    
    def to_dict(self) -> dict:
        """Export as structured UI object fact"""
        return {
            "type": "ui_object",
            "id": self.id,
            "label": self.label,
            "bbox": list(self.bbox),
            "center": [self.cx, self.cy],
            "obj_type": self.obj_type,
            "confidence": round(self.confidence, 3),
            "source": self.source.value,
            "stability": round(self.stability_score, 3),
            "seen_count": self.seen_count,
            "stale_ms": round(self.stale_ms, 1),
            "timestamp": self.last_seen
        }


@dataclass 
class CursorState:
    """Current cursor position and velocity"""
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    target_id: Optional[int] = None  # ID of object being targeted


@dataclass
class WorldState:
    """
    Persistent world state that survives frames.
    Tracks all UI objects, cursor, and viewport.
    """
    # Viewport
    viewport_width: int = 1280
    viewport_height: int = 720
    device_scale: float = 1.0
    
    # Cursor
    cursor: CursorState = field(default_factory=CursorState)
    
    # Tracked objects by ID
    objects: Dict[int, TrackedObject] = field(default_factory=dict)
    
    # ID counter
    _next_id: int = 1
    
    # Timing
    last_perception_time: float = 0.0
    last_control_time: float = 0.0
    frame_count: int = 0
    
    # Stale threshold (ms) - objects not seen in this time are removed
    STALE_THRESHOLD_MS: float = 2000.0
    
    # IoU threshold for matching existing objects
    IOU_THRESHOLD: float = 0.4
    
    def _next_object_id(self) -> int:
        """Generate next unique object ID"""
        obj_id = self._next_id
        self._next_id += 1
        return obj_id
    
    def _compute_iou(self, box1: Tuple[float, float, float, float], 
                     box2: Tuple[float, float, float, float]) -> float:
        """Compute Intersection over Union between two bboxes"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def _find_matching_object(self, bbox: Tuple[float, float, float, float], 
                               label: str) -> Optional[TrackedObject]:
        """Find existing object that matches new detection by IoU + label"""
        best_match = None
        best_score = 0.0
        
        for obj in self.objects.values():
            iou = self._compute_iou(bbox, obj.bbox)
            
            # Bonus for matching label
            label_match = 1.0 if label.lower() == obj.label.lower() else 0.5
            score = iou * label_match
            
            if score > best_score and iou >= self.IOU_THRESHOLD:
                best_score = score
                best_match = obj
        
        return best_match
    
    def update_from_detections(self, detections: List[dict], 
                                source: ObjectSource = ObjectSource.FUSED) -> List[TrackedObject]:
        """
        Update world state with new detections.
        Returns list of tracked objects (new + updated).
        
        Each detection should have: bbox, label, confidence, type
        """
        self.frame_count += 1
        self.last_perception_time = time.time()
        now = time.monotonic()
        
        # Get Kalman tracker singleton
        tracker = get_tracker()
        
        updated_objects = []
        
        for det in detections:
            bbox = tuple(det.get("bbox", (0, 0, 0, 0)))
            label = det.get("label", "")
            confidence = det.get("confidence", 0.5)
            obj_type = det.get("type", "unknown")
            
            # Try to match with existing object
            existing = self._find_matching_object(bbox, label)
            
            if existing:
                # Update existing object
                existing.update(bbox, confidence, label)
                existing.source = source
                
                # Update Kalman tracker with new measurement
                tracker.update(existing.id, existing.cx, existing.cy, now)
                
                # Get predicted position for smooth motion
                pred = tracker.predict(existing.id, now)
                if pred:
                    existing._predicted_cx, existing._predicted_cy = pred
                
                updated_objects.append(existing)
            else:
                # Create new tracked object
                cx = (bbox[0] + bbox[2]) / 2
                cy = (bbox[1] + bbox[3]) / 2
                
                new_obj = TrackedObject(
                    id=self._next_object_id(),
                    label=label,
                    bbox=bbox,
                    cx=cx,
                    cy=cy,
                    obj_type=obj_type,
                    confidence=confidence,
                    source=source,
                    dom_id=det.get("dom_id"),
                    tag=det.get("tag"),
                    role=det.get("role")
                )
                
                # Initialize Kalman tracker for new object
                tracker.update(new_obj.id, cx, cy, now)
                
                self.objects[new_obj.id] = new_obj
                updated_objects.append(new_obj)
        
        # Prune stale objects
        self._prune_stale()
        
        return updated_objects
    
    def _prune_stale(self):
        """Remove objects not seen recently"""
        stale_ids = [
            obj_id for obj_id, obj in self.objects.items()
            if obj.stale_ms > self.STALE_THRESHOLD_MS
        ]
        for obj_id in stale_ids:
            del self.objects[obj_id]
    
    def get_object_by_label(self, label: str) -> Optional[TrackedObject]:
        """Find object by label (partial match)"""
        label_lower = label.lower()
        for obj in sorted(self.objects.values(), 
                         key=lambda x: x.stability_score, reverse=True):
            if label_lower in obj.label.lower():
                return obj
        return None
    
    def get_object_at(self, x: float, y: float, tolerance: float = 10.0) -> Optional[TrackedObject]:
        """Find object at coordinates"""
        for obj in self.objects.values():
            if (obj.bbox[0] - tolerance <= x <= obj.bbox[2] + tolerance and
                obj.bbox[1] - tolerance <= y <= obj.bbox[3] + tolerance):
                return obj
        return None
    
    def get_stable_objects(self, min_stability: float = 0.5) -> List[TrackedObject]:
        """Get objects with stability above threshold"""
        return [obj for obj in self.objects.values() 
                if obj.stability_score >= min_stability]
    
    def export_facts(self) -> List[dict]:
        """Export all objects as structured UI facts"""
        return [obj.to_dict() for obj in self.objects.values()]
    
    def summary(self) -> str:
        """Quick summary of world state"""
        return (f"World: {len(self.objects)} objects, "
                f"cursor=({self.cursor.x:.0f},{self.cursor.y:.0f}), "
                f"frame={self.frame_count}")


# Singleton instance
_world_state: Optional[WorldState] = None

def get_world_state() -> WorldState:
    """Get or create the global world state"""
    global _world_state
    if _world_state is None:
        _world_state = WorldState()
    return _world_state

def reset_world_state():
    """Reset global world state"""
    global _world_state
    _world_state = WorldState()
