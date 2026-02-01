"""
Probe Detector - YOLO-based UI element detection
Detects clickable elements (buttons, links, inputs, menus, etc.)
"""

import numpy as np
import cv2
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ultralytics import YOLO
from config import (
    MODEL_PATH, CONFIDENCE_THRESHOLD, NMS_THRESHOLD,
    PROBE_CLASSES, VIEWPORT_WIDTH, VIEWPORT_HEIGHT
)


@dataclass
class Probe:
    """Detected UI element probe"""
    id: int  # Temporary ID, tracker assigns stable IDs
    x: float  # Center X (normalized 0-1)
    y: float  # Center Y (normalized 0-1)
    w: float  # Width (normalized 0-1)
    h: float  # Height (normalized 0-1)
    class_name: str  # button, link, input, etc.
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2) normalized
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cx": self.x,
            "cy": self.y,
            "w": self.w,
            "h": self.h,
            "type": self.class_name,
            "score": round(self.confidence, 3),
            "bbox": list(self.bbox)
        }
        

class ProbeDetector:
    def __init__(self, model_path: str = MODEL_PATH, use_pretrained: bool = True):
        """
        Initialize probe detector
        
        Args:
            model_path: Path to YOLO model weights
            use_pretrained: If True, use pretrained COCO model (fallback for quick start)
        """
        self.use_pretrained = use_pretrained
        
        if use_pretrained:
            # Use pretrained YOLOv8 - maps COCO classes to UI concepts
            self.model = YOLO("yolov8n.pt")
            self.class_mapping = self._create_coco_to_ui_mapping()
        else:
            # Use fine-tuned UI model
            self.model = YOLO(model_path)
            self.class_mapping = None
            
        self.probe_id_counter = 0
        
    def _create_coco_to_ui_mapping(self) -> Dict[int, str]:
        """Map COCO classes to UI-like probes (heuristic for quick start)"""
        # This is a rough mapping - fine-tuned model is better
        return {
            # Objects that might indicate interactive areas
            0: None,  # person - ignore
            # Most COCO classes won't map, but we can detect
            # rectangles and regions separately
        }
        
    def detect(self, frame: np.ndarray) -> List[Probe]:
        """
        Detect probes in frame
        
        Args:
            frame: BGR image (OpenCV format)
            
        Returns:
            List of detected probes
        """
        if frame is None:
            return []
            
        h, w = frame.shape[:2]
        
        if self.use_pretrained:
            # For pretrained model, also run heuristic detection
            probes = self._detect_ui_heuristics(frame)
        else:
            # Run YOLO inference
            results = self.model(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
            probes = self._parse_results(results[0], w, h)
            
        return probes
        
    def _detect_ui_heuristics(self, frame: np.ndarray) -> List[Probe]:
        """
        Heuristic UI detection for when we don't have fine-tuned model
        Uses edge detection + contour analysis to find button-like regions
        """
        h, w = frame.shape[:2]
        probes = []
        
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Dilate to connect edges
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=2)
        
        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            # Get bounding rect
            x, y, bw, bh = cv2.boundingRect(contour)
            
            # Filter by size - UI elements have reasonable sizes
            area = bw * bh
            aspect_ratio = bw / max(bh, 1)
            
            # Button-like: reasonable size, not too elongated
            if area < 500 or area > (w * h * 0.5):
                continue
            if aspect_ratio < 0.2 or aspect_ratio > 10:
                continue
            if bw < 20 or bh < 15:
                continue
                
            # Check if region has enough contrast (likely a control)
            roi = gray[y:y+bh, x:x+bw]
            if roi.size == 0:
                continue
            std = np.std(roi)
            if std < 10:  # Too uniform
                continue
                
            # Normalize coordinates
            cx = (x + bw/2) / w
            cy = (y + bh/2) / h
            nw = bw / w
            nh = bh / h
            
            # Classify by shape
            if aspect_ratio > 2.5:
                class_name = "link"
            elif aspect_ratio < 0.8:
                class_name = "menu"
            else:
                class_name = "button"
                
            self.probe_id_counter += 1
            probes.append(Probe(
                id=self.probe_id_counter,
                x=cx,
                y=cy,
                w=nw,
                h=nh,
                class_name=class_name,
                confidence=0.5 + (std / 100) * 0.3,  # Heuristic confidence
                bbox=(x/w, y/h, (x+bw)/w, (y+bh)/h)
            ))
            
        # Sort by confidence and limit
        probes.sort(key=lambda p: p.confidence, reverse=True)
        return probes[:50]  # Cap at 50 probes
        
    def _parse_results(self, result, img_w: int, img_h: int) -> List[Probe]:
        """Parse YOLO results into Probe objects"""
        probes = []
        
        if result.boxes is None:
            return probes
            
        boxes = result.boxes
        for i in range(len(boxes)):
            # Get box coordinates
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            conf = float(boxes.conf[i].cpu().numpy())
            cls = int(boxes.cls[i].cpu().numpy())
            
            # Normalize coordinates
            x1_n, y1_n = x1 / img_w, y1 / img_h
            x2_n, y2_n = x2 / img_w, y2 / img_h
            cx = (x1_n + x2_n) / 2
            cy = (y1_n + y2_n) / 2
            w = x2_n - x1_n
            h = y2_n - y1_n
            
            # Get class name
            class_name = PROBE_CLASSES[cls] if cls < len(PROBE_CLASSES) else "unknown"
            
            self.probe_id_counter += 1
            probes.append(Probe(
                id=self.probe_id_counter,
                x=cx,
                y=cy,
                w=w,
                h=h,
                class_name=class_name,
                confidence=conf,
                bbox=(x1_n, y1_n, x2_n, y2_n)
            ))
            
        return probes
        
    def detect_with_visualization(self, frame: np.ndarray) -> tuple:
        """Detect and return annotated frame for debugging"""
        probes = self.detect(frame)
        
        vis_frame = frame.copy()
        h, w = frame.shape[:2]
        
        for probe in probes:
            x1 = int(probe.bbox[0] * w)
            y1 = int(probe.bbox[1] * h)
            x2 = int(probe.bbox[2] * w)
            y2 = int(probe.bbox[3] * h)
            
            # Draw box
            color = (0, 255, 0) if probe.class_name == "button" else (255, 0, 0)
            cv2.rectangle(vis_frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label = f"{probe.class_name}: {probe.confidence:.2f}"
            cv2.putText(vis_frame, label, (x1, y1-5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                       
        return probes, vis_frame
