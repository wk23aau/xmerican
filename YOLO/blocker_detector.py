"""
Blocker Detector - Detects modals, overlays, and blocking elements
Prevents clicking on covered elements
"""

import numpy as np
import cv2
from typing import List, Dict, Optional
from dataclasses import dataclass
from config import BLOCKER_OPACITY_THRESHOLD, BLOCKER_AREA_THRESHOLD


@dataclass
class Blocker:
    """A blocking overlay or modal"""
    bbox: tuple  # (x1, y1, x2, y2) normalized
    blocker_type: str  # "modal", "overlay", "dropdown"
    opacity: float
    
    def contains(self, x: float, y: float) -> bool:
        """Check if position is inside blocker"""
        return (self.bbox[0] <= x <= self.bbox[2] and 
                self.bbox[1] <= y <= self.bbox[3])
                
    def to_dict(self) -> Dict:
        return {
            "bbox": list(self.bbox),
            "type": self.blocker_type,
            "opacity": round(self.opacity, 2)
        }


class BlockerDetector:
    def __init__(self):
        self.prev_frame: Optional[np.ndarray] = None
        self.blocker_history: List[Blocker] = []
        
    def detect(self, frame: np.ndarray, frame_delta: Optional[np.ndarray] = None) -> List[Blocker]:
        """
        Detect blocking overlays in frame
        
        Uses multiple heuristics:
        1. Large semi-transparent regions (modal backdrop)
        2. Centered rectangles with distinct borders
        3. Sudden appearance of dark overlay (via frame delta)
        """
        blockers = []
        h, w = frame.shape[:2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Method 1: Detect dark semi-transparent overlay
        overlay_blocker = self._detect_dark_overlay(gray, w, h)
        if overlay_blocker:
            blockers.append(overlay_blocker)
            
        # Method 2: Detect modal (centered bright box on dark background)
        modal_blocker = self._detect_modal_pattern(gray, w, h)
        if modal_blocker:
            blockers.append(modal_blocker)
            
        # Method 3: Use frame delta to detect sudden overlays
        if frame_delta is not None:
            sudden_blockers = self._detect_sudden_overlay(frame_delta, w, h)
            blockers.extend(sudden_blockers)
            
        self.prev_frame = gray.copy()
        self.blocker_history = blockers
        
        return blockers
        
    def _detect_dark_overlay(self, gray: np.ndarray, w: int, h: int) -> Optional[Blocker]:
        """Detect dark semi-transparent backdrop (common for modals)"""
        # Check if large portion of image is dark and uniform
        mean_intensity = np.mean(gray)
        std_intensity = np.std(gray)
        
        # Threshold for "dark overlay"
        dark_mask = gray < 80
        dark_ratio = np.sum(dark_mask) / (w * h)
        
        # If >50% is dark and has low variance in dark regions
        if dark_ratio > BLOCKER_AREA_THRESHOLD:
            dark_std = np.std(gray[dark_mask]) if np.any(dark_mask) else 100
            if dark_std < 30:  # Uniform dark region = overlay
                # Find the overlay bounds
                rows_with_dark = np.any(dark_mask, axis=1)
                cols_with_dark = np.any(dark_mask, axis=0)
                
                if np.any(rows_with_dark) and np.any(cols_with_dark):
                    y1 = np.argmax(rows_with_dark) / h
                    y2 = (h - np.argmax(rows_with_dark[::-1])) / h
                    x1 = np.argmax(cols_with_dark) / w
                    x2 = (w - np.argmax(cols_with_dark[::-1])) / w
                    
                    return Blocker(
                        bbox=(x1, y1, x2, y2),
                        blocker_type="overlay",
                        opacity=1 - (mean_intensity / 255)
                    )
        return None
        
    def _detect_modal_pattern(self, gray: np.ndarray, w: int, h: int) -> Optional[Blocker]:
        """Detect centered modal box pattern"""
        # Look for a rectangular region that's brighter than surroundings
        # and roughly centered
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            
            # Check if it's a significant centered rectangle
            area_ratio = (bw * bh) / (w * h)
            center_x = (x + bw/2) / w
            center_y = (y + bh/2) / h
            
            # Modal-like: 10-70% of screen, roughly centered
            if 0.1 < area_ratio < 0.7:
                if 0.2 < center_x < 0.8 and 0.2 < center_y < 0.8:
                    # Check brightness difference
                    roi = gray[y:y+bh, x:x+bw]
                    outside_mask = np.ones_like(gray, dtype=bool)
                    outside_mask[y:y+bh, x:x+bw] = False
                    
                    if np.mean(roi) > np.mean(gray[outside_mask]) + 30:
                        return Blocker(
                            bbox=(x/w, y/h, (x+bw)/w, (y+bh)/h),
                            blocker_type="modal",
                            opacity=0.8
                        )
        return None
        
    def _detect_sudden_overlay(self, delta: np.ndarray, w: int, h: int) -> List[Blocker]:
        """Detect sudden large changes (overlay appearing)"""
        blockers = []
        
        # Check if delta shows a large uniform change
        delta_thresh = cv2.threshold(delta, 30, 255, cv2.THRESH_BINARY)[1]
        changed_ratio = np.sum(delta_thresh > 0) / (w * h)
        
        # If >40% of frame changed suddenly, might be overlay
        if changed_ratio > 0.4:
            # Find connected components
            n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(delta_thresh)
            
            for i in range(1, n_labels):
                x, y, bw, bh, area = stats[i]
                area_ratio = area / (w * h)
                
                if area_ratio > 0.3:
                    blockers.append(Blocker(
                        bbox=(x/w, y/h, (x+bw)/w, (y+bh)/h),
                        blocker_type="overlay",
                        opacity=0.5
                    ))
                    
        return blockers
        
    def is_blocked(self, x: float, y: float) -> bool:
        """Check if a position is blocked by any overlay"""
        for blocker in self.blocker_history:
            if blocker.contains(x, y):
                return True
        return False
        
    def get_close_button_region(self) -> Optional[tuple]:
        """Get likely close button region (top-right of modal)"""
        for blocker in self.blocker_history:
            if blocker.blocker_type == "modal":
                # Top-right corner of modal
                return (
                    blocker.bbox[2] - 0.05,  # x
                    blocker.bbox[1] + 0.02,  # y
                )
        return None
