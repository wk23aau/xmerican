"""
Debug Visualization - Shows detected probes with bounding boxes
"""

import cv2
import numpy as np
from typing import List, Dict, Optional
import time


class DebugVisualizer:
    """
    Visualizes probe detections with bounding boxes
    Can show in a window or save frames
    """
    
    def __init__(self, window_name: str = "YOLO Vision Agent - Debug"):
        self.window_name = window_name
        self.window_created = False
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.fps = 0
        
        # Colors for different probe types (BGR)
        self.colors = {
            "button": (0, 255, 0),      # Green
            "link": (255, 128, 0),      # Orange
            "input": (255, 255, 0),     # Cyan
            "menu": (255, 0, 255),      # Magenta
            "dropdown": (128, 0, 255),  # Purple
            "close": (0, 0, 255),       # Red
            "checkbox": (0, 255, 255),  # Yellow
            "icon": (128, 128, 255),    # Pink
            "unknown": (128, 128, 128), # Gray
        }
        
    def draw_probes(
        self,
        frame: np.ndarray,
        probes: List[Dict],
        blockers: List[Dict] = None,
        cursor_pos: tuple = None,
        state: str = "",
        hovered_id: int = None
    ) -> np.ndarray:
        """
        Draw bounding boxes and labels on frame
        
        Args:
            frame: BGR image
            probes: List of probe dicts with bbox, type, score, id
            blockers: List of blocker dicts
            cursor_pos: (x, y) normalized cursor position
            state: Current FSM state
            hovered_id: ID of currently hovered probe
            
        Returns:
            Annotated frame
        """
        vis = frame.copy()
        h, w = frame.shape[:2]
        
        # Draw blockers first (semi-transparent overlay)
        if blockers:
            overlay = vis.copy()
            for blocker in blockers:
                bbox = blocker.get("bbox", [0, 0, 0, 0])
                x1 = int(bbox[0] * w)
                y1 = int(bbox[1] * h)
                x2 = int(bbox[2] * w)
                y2 = int(bbox[3] * h)
                
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 128), -1)
                
            cv2.addWeighted(overlay, 0.3, vis, 0.7, 0, vis)
            
            # Draw blocker border
            for blocker in blockers:
                bbox = blocker.get("bbox", [0, 0, 0, 0])
                x1 = int(bbox[0] * w)
                y1 = int(bbox[1] * h)
                x2 = int(bbox[2] * w)
                y2 = int(bbox[3] * h)
                
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(vis, f"BLOCKER: {blocker.get('type', 'unknown')}", 
                           (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        
        # Draw probes
        for probe in probes:
            bbox = probe.get("bbox", [0, 0, 0, 0])
            x1 = int(bbox[0] * w)
            y1 = int(bbox[1] * h)
            x2 = int(bbox[2] * w)
            y2 = int(bbox[3] * h)
            
            probe_type = probe.get("type", "unknown")
            color = self.colors.get(probe_type, self.colors["unknown"])
            
            # Highlight hovered probe
            thickness = 3 if probe.get("id") == hovered_id else 2
            if probe.get("id") == hovered_id:
                color = (255, 255, 255)  # White for hovered
                
            # Draw bounding box
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, thickness)
            
            # Draw center point
            cx = int(probe.get("cx", 0.5) * w)
            cy = int(probe.get("cy", 0.5) * h)
            cv2.circle(vis, (cx, cy), 4, color, -1)
            
            # Draw label
            score = probe.get("score", 0)
            probe_id = probe.get("id", "?")
            label = f"#{probe_id} {probe_type} ({score:.2f})"
            
            # Background for label
            (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            cv2.rectangle(vis, (x1, y1 - label_h - 6), (x1 + label_w + 4, y1), color, -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 4), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)
        
        # Draw cursor
        if cursor_pos:
            cx = int(cursor_pos[0] * w)
            cy = int(cursor_pos[1] * h)
            cv2.circle(vis, (cx, cy), 8, (255, 255, 255), 2)
            cv2.circle(vis, (cx, cy), 3, (0, 255, 0), -1)
            
        # Draw status bar
        self._draw_status_bar(vis, state, len(probes), len(blockers or []))
        
        return vis
        
    def _draw_status_bar(self, frame: np.ndarray, state: str, probe_count: int, blocker_count: int):
        """Draw status bar at top of frame"""
        h, w = frame.shape[:2]
        
        # Background
        cv2.rectangle(frame, (0, 0), (w, 30), (40, 40, 40), -1)
        
        # Calculate FPS
        self.frame_count += 1
        now = time.time()
        if now - self.last_fps_time >= 1.0:
            self.fps = self.frame_count / (now - self.last_fps_time)
            self.frame_count = 0
            self.last_fps_time = now
            
        # Status text
        status = f"State: {state} | Probes: {probe_count} | Blockers: {blocker_count} | FPS: {self.fps:.1f}"
        cv2.putText(frame, status, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Legend (right side)
        legend_x = w - 200
        legend_items = [("button", (0, 255, 0)), ("link", (255, 128, 0)), ("input", (255, 255, 0))]
        for i, (name, color) in enumerate(legend_items):
            x = legend_x + i * 65
            cv2.rectangle(frame, (x, 5), (x + 10, 15), color, -1)
            cv2.putText(frame, name, (x + 12, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
            
    def show(self, frame: np.ndarray) -> bool:
        """
        Show frame in window
        
        Returns:
            False if window was closed (ESC or X button)
        """
        if not self.window_created:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_name, 600, 960)
            self.window_created = True
            
        cv2.imshow(self.window_name, frame)
        
        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            return False
        return True
        
    def save_frame(self, frame: np.ndarray, path: str):
        """Save frame to file"""
        cv2.imwrite(path, frame)
        
    def close(self):
        """Close visualization window"""
        if self.window_created:
            cv2.destroyWindow(self.window_name)
            self.window_created = False


def create_debug_overlay_html() -> str:
    """
    Generate HTML/CSS for browser-side overlay (alternative approach)
    Inject this into the page via CDP
    """
    return """
    <style>
        .yolo-debug-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            z-index: 999999;
        }
        .yolo-probe-box {
            position: absolute;
            border: 2px solid #00ff00;
            background: rgba(0, 255, 0, 0.1);
            pointer-events: none;
        }
        .yolo-probe-label {
            position: absolute;
            top: -20px;
            left: 0;
            background: #00ff00;
            color: black;
            font-size: 10px;
            padding: 2px 4px;
            font-family: monospace;
        }
        .yolo-cursor {
            position: absolute;
            width: 16px;
            height: 16px;
            border: 2px solid white;
            border-radius: 50%;
            background: rgba(0, 255, 0, 0.5);
            transform: translate(-50%, -50%);
            pointer-events: none;
        }
    </style>
    <div id="yolo-debug-overlay" class="yolo-debug-overlay"></div>
    <script>
        window.YOLO_DEBUG = {
            updateProbes: function(probes) {
                const overlay = document.getElementById('yolo-debug-overlay');
                overlay.innerHTML = '';
                probes.forEach(p => {
                    const box = document.createElement('div');
                    box.className = 'yolo-probe-box';
                    box.style.left = (p.bbox[0] * 100) + '%';
                    box.style.top = (p.bbox[1] * 100) + '%';
                    box.style.width = ((p.bbox[2] - p.bbox[0]) * 100) + '%';
                    box.style.height = ((p.bbox[3] - p.bbox[1]) * 100) + '%';
                    
                    const label = document.createElement('div');
                    label.className = 'yolo-probe-label';
                    label.textContent = '#' + p.id + ' ' + p.type;
                    box.appendChild(label);
                    
                    overlay.appendChild(box);
                });
            }
        };
    </script>
    """
