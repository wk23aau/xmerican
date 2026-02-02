"""
xCLICK Streaming Vision Module
Background continuous detection with Kalman-predicted positions.
Enables instant (<5ms) lookups instead of waiting ~750ms for YOLO.

Architecture:
  - Background async task runs detection every ~700ms
  - Each element is tracked with Kalman filter (position + velocity)
  - get_position(label) returns PREDICTED position instantly
  - World state always reflects latest predictions

Usage:
    streaming = StreamingVision(vision_module, tracker)
    await streaming.start()
    
    # Instant lookup (no waiting!)
    pos = streaming.get_position("Submit")  # Returns (x, y) in ~1ms
    
    await streaming.stop()
"""

import asyncio
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class TrackedElement:
    """Element being tracked with Kalman prediction"""
    tracker_id: int
    label: str
    element_type: str
    last_cx: float
    last_cy: float
    last_confidence: float
    last_update: float


class StreamingVision:
    """
    Background streaming vision loop with Kalman prediction.
    Provides instant (<5ms) position lookups for any labeled element.
    
    Key insight: YOLO inference takes ~600ms, but we can predict
    positions between frames using velocity. For static UIs, prediction
    is highly accurate. For moving elements, prediction smooths motion.
    
    IMPORTANT: All returned coordinates are in CSS pixel space (scaled by device_scale).
    This ensures clicks land correctly regardless of DPI/scaling settings.
    """
    
    def __init__(self, vision_module, tracker, update_interval: float = 0.8):
        """
        Args:
            vision_module: VisionModule instance (has detect_labeled_probes)
            tracker: KalmanTracker instance (has update/predict)
            update_interval: Time between YOLO updates (default 0.8s)
        """
        self._vision = vision_module
        self._tracker = tracker
        self._update_interval = update_interval
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Label → TrackedElement mapping (case-insensitive)
        self._elements: Dict[str, TrackedElement] = {}
        
        # Track ID counter (unique per element)
        self._next_id = 1000  # Start high to avoid collision with probe IDs
        
        # Stats
        self._update_count = 0
        self._last_update_time = 0.0
        self._last_update_duration = 0.0
        self._element_count = 0
        
    async def start(self):
        """Start background streaming detection"""
        if self._running:
            print("  [stream] Already running")
            return
            
        self._running = True
        self._task = asyncio.create_task(self._stream_loop())
        print(f"  [stream] Started @ {1/self._update_interval:.1f}Hz background detection")
        
    async def stop(self):
        """Stop background streaming"""
        if not self._running:
            return
            
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print(f"  [stream] Stopped after {self._update_count} updates, {len(self._elements)} elements tracked")
        
    async def _stream_loop(self):
        """Main background detection loop"""
        try:
            while self._running:
                t_start = time.monotonic()
                
                try:
                    # Run full YOLO detection
                    probes = await self._vision.detect_labeled_probes(verbose=False)
                    
                    # Update tracker with all detected elements
                    now = time.monotonic()
                    seen_labels = set()
                    
                    for probe in probes:
                        label_key = probe.label.lower().strip() if probe.label else ""
                        if not label_key:
                            continue  # Skip unlabeled elements
                            
                        seen_labels.add(label_key)
                        
                        # Get or create tracker ID for this label
                        if label_key in self._elements:
                            elem = self._elements[label_key]
                            tracker_id = elem.tracker_id
                        else:
                            tracker_id = self._next_id
                            self._next_id += 1
                            self._elements[label_key] = TrackedElement(
                                tracker_id=tracker_id,
                                label=probe.label,
                                element_type=probe.type,
                                last_cx=probe.cx,
                                last_cy=probe.cy,
                                last_confidence=probe.confidence,
                                last_update=now
                            )
                            
                        # Update Kalman tracker
                        self._tracker.update(tracker_id, probe.cx, probe.cy, now)
                        
                        # Update element record
                        elem = self._elements[label_key]
                        elem.last_cx = probe.cx
                        elem.last_cy = probe.cy
                        elem.last_confidence = probe.confidence
                        elem.last_update = now
                    
                    # Remove stale elements (not seen for 5+ seconds)
                    stale_threshold = 5.0
                    stale_keys = [k for k, e in self._elements.items() 
                                  if now - e.last_update > stale_threshold]
                    for key in stale_keys:
                        del self._elements[key]
                    
                    # Update stats
                    self._update_count += 1
                    self._last_update_time = now
                    self._last_update_duration = now - t_start
                    self._element_count = len(self._elements)
                    
                except Exception as e:
                    print(f"  [stream] Detection error: {e}")
                
                # Sleep for remaining interval
                elapsed = time.monotonic() - t_start
                sleep_time = max(0.01, self._update_interval - elapsed)
                await asyncio.sleep(sleep_time)
                
        except asyncio.CancelledError:
            pass
    
    @property
    def device_scale(self) -> float:
        """Get device scale factor from vision module for coordinate conversion."""
        return getattr(self._vision, 'device_scale', 1.0)
    
    def _scale_to_css(self, x: float, y: float) -> Tuple[float, float]:
        """Convert YOLO/screenshot coordinates to CSS pixel space."""
        scale = self.device_scale
        return (x / scale, y / scale)
            
    def get_position(self, label: str) -> Optional[Tuple[float, float]]:
        """
        Get PREDICTED position for label - instant, no waiting!
        
        Uses Kalman filter prediction to estimate current position
        based on last measurement and velocity.
        
        Args:
            label: Element label (case-insensitive, partial match)
            
        Returns:
            (cx, cy) predicted center coordinates in CSS pixels, or None if not found
            
        Note: Probes from detect_labeled_probes are already in CSS space,
        so no additional scaling is needed here.
        """
        label_lower = label.lower().strip()
        
        # Exact match first
        if label_lower in self._elements:
            elem = self._elements[label_lower]
            pred = self._tracker.predict(elem.tracker_id)
            return pred if pred else (elem.last_cx, elem.last_cy)
        
        # Partial match
        for key, elem in self._elements.items():
            if label_lower in key:
                pred = self._tracker.predict(elem.tracker_id)
                return pred if pred else (elem.last_cx, elem.last_cy)
                
        return None
        
    def get_element(self, label: str) -> Optional[TrackedElement]:
        """Get full element info by label"""
        label_lower = label.lower().strip()
        
        if label_lower in self._elements:
            return self._elements[label_lower]
            
        for key, elem in self._elements.items():
            if label_lower in key:
                return elem
                
        return None
        
    def get_all_predicted(self) -> List[Tuple[str, str, float, float, float]]:
        """
        Get all tracked elements with predicted positions in CSS pixels.
        
        Returns:
            List of (label, type, cx, cy, confidence) - coordinates are in CSS pixel space
            
        Note: Probes are already in CSS space from detect_labeled_probes.
        """
        now = time.monotonic()
        results = []
        
        for key, elem in self._elements.items():
            pred = self._tracker.predict(elem.tracker_id, now)
            if pred:
                cx, cy = pred
            else:
                cx, cy = elem.last_cx, elem.last_cy
            # No scaling needed - already CSS coords
            results.append((elem.label, elem.element_type, cx, cy, elem.last_confidence))
            
        return results
        
    def find_by_text(self, query: str) -> Optional[Tuple[str, float, float]]:
        """
        Find element by text query (case-insensitive partial match).
        
        Returns:
            (label, cx, cy) in CSS pixels, or None
        """
        pos = self.get_position(query)  # Already scaled to CSS by get_position
        if pos:
            elem = self.get_element(query)
            return (elem.label, pos[0], pos[1])
        return None
        
    @property
    def is_running(self) -> bool:
        return self._running
        
    @property 
    def element_count(self) -> int:
        return len(self._elements)
        
    def status(self) -> str:
        """Get streaming status string"""
        if not self._running:
            return "Streaming: STOPPED"
            
        since_update = time.monotonic() - self._last_update_time if self._last_update_time else 0
        return (f"Streaming: {self._update_count} updates, "
                f"last {since_update:.1f}s ago ({self._last_update_duration*1000:.0f}ms), "
                f"{len(self._elements)} elements tracked")
                
    def list_elements(self) -> str:
        """List all tracked elements for display"""
        if not self._elements:
            return "  No elements tracked yet"
            
        lines = []
        now = time.monotonic()
        
        for key, elem in sorted(self._elements.items()):
            pred = self._tracker.predict(elem.tracker_id, now)
            if pred:
                cx, cy = pred
            else:
                cx, cy = elem.last_cx, elem.last_cy
            age = now - elem.last_update
            lines.append(f"  [{elem.element_type:8}] '{elem.label[:25]:25}' ({cx:.0f},{cy:.0f}) [{elem.last_confidence:.2f}] {age:.1f}s ago")
            
        return "\n".join(lines)
