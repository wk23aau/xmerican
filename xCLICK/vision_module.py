"""
Vision Module - YOLO + DOM fusion for labeled probe detection
Combines visual detection (where) with DOM semantics (what)

Supports:
- YOLO26 (latest, January 2026) - best for edge deployment
- Pre-trained UI detection model from HuggingFace
- Custom fine-tuned models

Output: "button @ (x,y): Submit" instead of just "button @ (x,y)"
"""

import asyncio
import base64
import time
import numpy as np
from io import BytesIO
from PIL import Image
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import sys
import os

# Import motion controller utilities
from motion_controller import fuse_confidence, normalize_coords, denormalize_coords

# Add YOLO directory to path for imports
YOLO_DIR = os.path.join(os.path.dirname(__file__), "..", "YOLO")
if YOLO_DIR not in sys.path:
    sys.path.insert(0, YOLO_DIR)

# Pre-trained UI detection model from HuggingFace
HF_UI_MODEL_REPO = "macpaw-research/yolov11l-ui-elements-detection"
HF_UI_MODEL_FILE = "ui-elements-detection.pt"


@dataclass
class LabeledProbe:
    """A detected UI element with visual box and DOM label"""
    id: int
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2 in CSS pixels
    cx: float  # center x (CSS pixels)
    cy: float  # center y (CSS pixels)
    type: str  # "button", "input", "link", "dropdown", etc.
    label: str  # "Submit", "Email", "Sign In", etc.
    confidence: float
    label_source: str  # "dom" | "ocr" | "none"
    tag: Optional[str] = None  # HTML tag
    dom_id: Optional[str] = None  # DOM element ID
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    def __str__(self) -> str:
        if self.label:
            return f"{self.type} @ ({self.cx:.0f},{self.cy:.0f}): {self.label}"
        return f"{self.type} @ ({self.cx:.0f},{self.cy:.0f})"


class VisionModule:
    """
    YOLO + DOM fusion for labeled probe detection
    
    Pipeline:
    1. Capture viewport screenshot
    2. Run YOLO inference → boxes with type
    3. For each box, query DOM at center → get label
    4. Return LabeledProbe list
    
    Model options:
    - 'yolo26n' / 'yolo26s' / 'yolo26m' - YOLO26 (latest, Jan 2026)
    - 'ui' - Pre-trained UI detection model from HuggingFace
    - Path to custom .pt file
    """
    
    # Map HuggingFace UI model classes to our types
    HF_UI_CLASS_MAP = {
        "AXButton": "button",
        "AXDisclosureTriangle": "dropdown",
        "AXImage": "image",
        "AXLink": "link",
        "AXTextArea": "input",
        "AXTextField": "input",
        "AXCheckBox": "checkbox",
        "AXRadioButton": "radio",
        "AXPopUpButton": "dropdown",
        "AXSlider": "slider",
        "AXTabGroup": "tab",
        "AXMenuItem": "menu",
    }
    
    # UI element classes
    UI_CLASSES = ["button", "input", "link", "dropdown", "checkbox", 
                  "radio", "tab", "menu", "icon", "modal", "image", "slider"]
    
    def __init__(self, cdp_client, model_path: str = None, use_ocr: bool = True, 
                 model_type: str = "ui", inference_hz: float = 15.0):
        """
        Initialize vision module
        
        Args:
            cdp_client: CDPClient instance for browser communication
            model_path: Path to YOLO model (optional)
            use_ocr: Whether to use OCR fallback when DOM gives no label
            model_type: 'ui' (pre-trained UI model), 'yolo26n/s/m', or path to .pt
            inference_hz: YOLO inference rate (10-30 Hz) - boxes are Kalman-smoothed between updates
        """
        self.cdp = cdp_client
        self.model_path = model_path
        self.use_ocr = use_ocr
        self.model_type = model_type
        self.model = None
        self.is_ui_model = False  # Whether using UI-specific classes
        self.dpr = 1.0  # Device pixel ratio
        self.viewport_w = 400
        self.viewport_h = 640
        self._probe_id_counter = 0
        
        # Throttled inference (ChatGPT recommendation)
        self.inference_hz = inference_hz
        self._inference_interval = 1.0 / inference_hz
        self._last_inference_time = 0.0
        self._cached_boxes: List[Dict] = []
        self._cached_probes: List[LabeledProbe] = []
        
    async def init_model(self):
        """Initialize YOLO model"""
        try:
            from ultralytics import YOLO
            
            # Option 1: Pre-trained UI detection model from HuggingFace
            if self.model_type == "ui":
                model_path = await self._download_ui_model()
                if model_path:
                    print(f"Loading UI detection model from HuggingFace...")
                    self.model = YOLO(model_path)
                    self.is_ui_model = True
                    print("✓ UI detection model loaded (macpaw-research/yolov11l)")
                    return True
                    
            # Option 2: YOLO26 (latest)
            elif self.model_type.startswith("yolo26"):
                print(f"Loading {self.model_type} model...")
                self.model = YOLO(f"{self.model_type}.pt")
                print(f"✓ {self.model_type.upper()} model loaded")
                return True
                
            # Option 3: Custom model path
            elif self.model_path and os.path.exists(self.model_path):
                print(f"Loading custom model from {self.model_path}")
                self.model = YOLO(self.model_path)
                print("✓ Custom YOLO model loaded")
                return True
                
            # Fallback: Try local YOLO directory
            else:
                default_path = os.path.join(YOLO_DIR, "yolov8n.pt")
                if os.path.exists(default_path):
                    print(f"Loading fallback model from {default_path}")
                    self.model = YOLO(default_path)
                else:
                    print("Downloading YOLO26n (latest)...")
                    self.model = YOLO("yolo26n.pt")
                    
            print("✓ YOLO model loaded")
            return True
            
        except ImportError:
            print("✗ ultralytics not installed. Run: pip install ultralytics")
            return False
        except Exception as e:
            print(f"✗ Failed to load YOLO model: {e}")
            return False
            
    async def _download_ui_model(self) -> Optional[str]:
        """Download pre-trained UI detection model from HuggingFace"""
        try:
            from huggingface_hub import hf_hub_download
            
            cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            model_path = hf_hub_download(
                repo_id=HF_UI_MODEL_REPO,
                filename=HF_UI_MODEL_FILE,
                cache_dir=cache_dir
            )
            return model_path
            
        except ImportError:
            print("✗ huggingface_hub not installed. Run: pip install huggingface_hub")
            print("  Falling back to YOLO26n...")
            return None
        except Exception as e:
            print(f"✗ Failed to download UI model: {e}")
            print("  Falling back to YOLO26n...")
            return None
            
    async def capture_viewport(self) -> Tuple[Optional[bytes], float, int, int]:
        """
        Capture viewport screenshot with metrics
        
        Returns:
            (png_bytes, device_pixel_ratio, css_width, css_height)
        """
        # Get viewport metrics
        try:
            metrics = await self.cdp.send("Page.getLayoutMetrics")
            visual = metrics.get("result", {}).get("visualViewport", {})
            self.viewport_w = int(visual.get("clientWidth", 400))
            self.viewport_h = int(visual.get("clientHeight", 640))
            self.dpr = float(visual.get("scale", 1.0))
        except:
            pass  # Use defaults
            
        # Capture screenshot
        result = await self.cdp.send("Page.captureScreenshot", {
            "format": "png",
            "clip": {
                "x": 0,
                "y": 0,
                "width": self.viewport_w,
                "height": self.viewport_h,
                "scale": 1
            }
        })
        
        data = result.get("result", {}).get("data", "")
        if not data:
            return None, self.dpr, self.viewport_w, self.viewport_h
            
        png_bytes = base64.b64decode(data)
        return png_bytes, self.dpr, self.viewport_w, self.viewport_h
        
    def detect_objects(self, png_bytes: bytes, confidence: float = 0.25) -> List[Dict]:
        """
        Run YOLO inference on image
        
        Args:
            png_bytes: PNG image bytes
            confidence: Detection confidence threshold
            
        Returns:
            List of detected boxes: {bbox, type, confidence, px_center}
        """
        if not self.model:
            return self._detect_heuristic(png_bytes)
            
        # Convert to numpy array
        img = Image.open(BytesIO(png_bytes))
        frame = np.array(img)
        
        # Run YOLO
        results = self.model(frame, conf=confidence, verbose=False)
        
        boxes = []
        for result in results:
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                
                # Get class name
                class_name = result.names.get(cls_id, "unknown")
                
                # Map to UI type based on model
                if self.is_ui_model:
                    # Using pre-trained UI model - map HF classes
                    ui_type = self.HF_UI_CLASS_MAP.get(class_name, "element")
                else:
                    # Generic model - use class name if it matches UI types
                    if class_name.lower() in [c.lower() for c in self.UI_CLASSES]:
                        ui_type = class_name.lower()
                    else:
                        ui_type = "element"
                
                boxes.append({
                    "bbox_px": (float(x1), float(y1), float(x2), float(y2)),
                    "type": ui_type,
                    "confidence": conf,
                    "px_cx": float((x1 + x2) / 2),
                    "px_cy": float((y1 + y2) / 2),
                    "class_name": class_name,  # Original class name
                })
                
        return boxes
        
    def _detect_heuristic(self, png_bytes: bytes) -> List[Dict]:
        """
        Heuristic UI detection when YOLO is not available
        Uses edge detection + contour analysis to find button-like regions
        """
        try:
            import cv2
        except ImportError:
            return []
            
        img = Image.open(BytesIO(png_bytes))
        frame = np.array(img)
        
        # Convert to grayscale
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        else:
            gray = frame
            
        # Edge detection
        edges = cv2.Canny(gray, 50, 150)
        
        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter by size (button-like proportions)
            if w < 30 or h < 15 or w > 500 or h > 200:
                continue
            if w / h > 10 or h / w > 5:  # Too elongated
                continue
                
            boxes.append({
                "bbox_px": (float(x), float(y), float(x + w), float(y + h)),
                "type": "element",
                "confidence": 0.5,
                "px_cx": float(x + w / 2),
                "px_cy": float(y + h / 2),
            })
            
        return boxes[:50]  # Limit to 50 boxes
        
    async def probe_dom_at(self, css_x: float, css_y: float) -> Dict[str, Any]:
        """
        Query DOM element at CSS coordinates
        
        Returns:
            {tag, id, classes, label, rect}
        """
        js = f"""
        (function() {{
            var el = document.elementFromPoint({css_x}, {css_y});
            if (!el) return null;
            
            var rect = el.getBoundingClientRect();
            
            // Get label from various sources
            var label = 
                el.getAttribute('aria-label') ||
                el.getAttribute('title') ||
                (el.innerText || '').trim().substring(0, 50) ||
                (el.value || '').trim() ||
                (el.placeholder || '').trim() ||
                el.getAttribute('alt') ||
                null;
                
            // Clean up label
            if (label) {{
                label = label.replace(/\\n/g, ' ').trim();
            }}
            
            return {{
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                classes: el.className || null,
                label: label,
                role: el.getAttribute('role') || null,
                type: el.getAttribute('type') || null,
                rect: {{
                    x: rect.left,
                    y: rect.top,
                    w: rect.width,
                    h: rect.height
                }}
            }};
        }})()
        """
        
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        
        value = result.get("result", {}).get("result", {}).get("value")
        return value or {}
        
    def px_to_css(self, px_x: float, px_y: float) -> Tuple[float, float]:
        """Convert pixel coordinates to CSS coordinates"""
        return px_x / self.dpr, px_y / self.dpr
        
    def css_to_px(self, css_x: float, css_y: float) -> Tuple[float, float]:
        """Convert CSS coordinates to pixel coordinates"""
        return css_x * self.dpr, css_y * self.dpr
        
    async def detect_labeled_probes(self, confidence: float = 0.25) -> List[LabeledProbe]:
        """
        Main detection pipeline: YOLO + DOM fusion
        
        Returns:
            List of LabeledProbe objects with visual boxes and DOM labels
        """
        # Initialize model if needed
        if not self.model:
            await self.init_model()
            
        # Capture viewport
        png_bytes, dpr, css_w, css_h = await self.capture_viewport()
        if not png_bytes:
            return []
            
        self.dpr = dpr
        
        # Run YOLO detection
        boxes = self.detect_objects(png_bytes, confidence)
        
        # Fuse with DOM labels
        probes = []
        for box in boxes:
            # Convert pixel center to CSS coords
            css_cx, css_cy = self.px_to_css(box["px_cx"], box["px_cy"])
            
            # Convert pixel bbox to CSS bbox
            px_bbox = box["bbox_px"]
            css_bbox = (
                px_bbox[0] / dpr,
                px_bbox[1] / dpr,
                px_bbox[2] / dpr,
                px_bbox[3] / dpr,
            )
            
            # Query DOM at center point
            dom_info = await self.probe_dom_at(css_cx, css_cy)
            
            # Determine element type from DOM if possible
            ui_type = box["type"]
            if dom_info:
                tag = dom_info.get("tag", "")
                role = dom_info.get("role", "")
                elem_type = dom_info.get("type", "")
                
                if tag == "button" or role == "button":
                    ui_type = "button"
                elif tag == "a" or role == "link":
                    ui_type = "link"
                elif tag == "input":
                    ui_type = "button" if elem_type == "submit" else "input"
                elif tag == "select":
                    ui_type = "dropdown"
                elif tag == "textarea":
                    ui_type = "input"
                elif role == "menuitem":
                    ui_type = "menu"
                elif role == "checkbox":
                    ui_type = "checkbox"
                elif role == "tab":
                    ui_type = "tab"
                    
            # Get label
            label = ""
            label_source = "none"
            
            if dom_info and dom_info.get("label"):
                label = dom_info["label"][:50]  # Truncate
                label_source = "dom"
            elif self.use_ocr:
                # TODO: OCR fallback for canvas elements
                pass
                
            # Create labeled probe
            self._probe_id_counter += 1
            probe = LabeledProbe(
                id=self._probe_id_counter,
                bbox=css_bbox,
                cx=css_cx,
                cy=css_cy,
                type=ui_type,
                label=label,
                confidence=box["confidence"],
                label_source=label_source,
                tag=dom_info.get("tag") if dom_info else None,
                dom_id=dom_info.get("id") if dom_info else None,
            )
            probes.append(probe)
            
        # Cache for throttled access
        self._cached_probes = probes
        return probes
    
    async def detect_throttled(self, confidence: float = 0.25, force: bool = False) -> List[LabeledProbe]:
        """
        Throttled detection - runs YOLO at inference_hz rate, reuses cached boxes otherwise.
        
        This is the recommended method for real-time loops:
        - Perception loop calls this at desired rate
        - YOLO only runs when interval elapsed
        - Between updates, cached probes are returned
        
        Args:
            confidence: Detection confidence threshold
            force: Force fresh detection (ignore throttle)
            
        Returns:
            List of LabeledProbe (may be cached)
        """
        now = time.monotonic()
        time_since_last = now - self._last_inference_time
        
        # Check if we should run fresh detection
        if force or time_since_last >= self._inference_interval or not self._cached_probes:
            self._last_inference_time = now
            return await self.detect_labeled_probes(confidence)
        
        # Return cached probes
        return self._cached_probes
    
    def apply_confidence_fusion(self, probes: List[LabeledProbe]) -> List[LabeledProbe]:
        """
        Apply confidence fusion to probes (ChatGPT recommendation).
        
        Formula: final_conf = vision_conf * 0.6 + dom_conf * 0.4
        
        - Vision confidence from YOLO
        - DOM confidence: 1.0 if label found, 0.5 otherwise
        """
        for probe in probes:
            vision_conf = probe.confidence
            dom_conf = 1.0 if probe.label_source == "dom" else 0.5
            probe.confidence = fuse_confidence(vision_conf, dom_conf)
        return probes
    
    def get_normalized_coords(self, probe: LabeledProbe) -> Tuple[float, float]:
        """
        Get normalized coordinates (0-1) for a probe.
        Useful for avoiding device scale factor issues.
        """
        return normalize_coords(probe.cx, probe.cy, self.viewport_w, self.viewport_h)
        
    def find_probe_by_label(self, probes: List[LabeledProbe], query: str) -> Optional[LabeledProbe]:
        """Find a probe by label text (case-insensitive partial match)"""
        query_lower = query.lower()
        
        # Exact match first
        for probe in probes:
            if probe.label.lower() == query_lower:
                return probe
                
        # Partial match
        for probe in probes:
            if query_lower in probe.label.lower():
                return probe
                
        return None
        
    async def get_annotated_frame(self, probes: List[LabeledProbe] = None) -> Optional[bytes]:
        """
        Get viewport screenshot with probe annotations
        For debugging/visualization
        """
        try:
            import cv2
        except ImportError:
            return None
            
        # Capture frame
        png_bytes, dpr, _, _ = await self.capture_viewport()
        if not png_bytes:
            return None
            
        # Detect if not provided
        if probes is None:
            probes = await self.detect_labeled_probes()
            
        # Load image
        img = Image.open(BytesIO(png_bytes))
        frame = np.array(img)
        
        # Convert RGB to BGR for OpenCV
        if len(frame.shape) == 3 and frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
        # Draw boxes
        for probe in probes:
            x1, y1, x2, y2 = probe.bbox
            # Scale back to pixels
            x1, y1 = int(x1 * dpr), int(y1 * dpr)
            x2, y2 = int(x2 * dpr), int(y2 * dpr)
            
            # Color by type
            colors = {
                "button": (0, 255, 0),
                "link": (255, 0, 0),
                "input": (0, 255, 255),
                "dropdown": (255, 255, 0),
            }
            color = colors.get(probe.type, (128, 128, 128))
            
            # Draw rectangle
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw label
            label_text = f"{probe.type}: {probe.label}" if probe.label else probe.type
            cv2.putText(frame, label_text[:30], (x1, y1 - 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
                       
        # Encode to PNG
        _, png_data = cv2.imencode('.png', frame)
        return png_data.tobytes()
