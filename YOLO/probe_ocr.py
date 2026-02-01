"""
OCR Module - Extract text from probe regions
Supports: PaddleOCR (best), EasyOCR, Tesseract
"""

import cv2
import numpy as np
from typing import List, Dict
import time
import os

# Suppress PaddleOCR logs
os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'

# Try OCR backends in order of preference
PADDLEOCR_AVAILABLE = False
EASYOCR_AVAILABLE = False
TESSERACT_AVAILABLE = False

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    pass

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    pass

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    pass


class ProbeOCR:
    """
    Extract text from probe bounding boxes
    Priority: PaddleOCR > EasyOCR > Tesseract
    """
    
    def __init__(self, use_gpu: bool = False, backend: str = "auto"):
        self.reader = None
        self.backend = None
        
        # Select backend (EasyOCR preferred due to better compatibility)
        if backend == "auto":
            if EASYOCR_AVAILABLE:
                self._init_easyocr(use_gpu)
            elif PADDLEOCR_AVAILABLE:
                self._init_paddleocr(use_gpu)
            elif TESSERACT_AVAILABLE:
                self._init_tesseract()
            else:
                print("[OCR] No backend available - install easyocr or pytesseract")
        elif backend == "paddle" and PADDLEOCR_AVAILABLE:
            self._init_paddleocr(use_gpu)
        elif backend == "easyocr" and EASYOCR_AVAILABLE:
            self._init_easyocr(use_gpu)
        elif backend == "tesseract" and TESSERACT_AVAILABLE:
            self._init_tesseract()
            
        # Cache to avoid re-OCR same regions
        self.cache: Dict[str, str] = {}
        self.cache_ttl = 2.0
        self.cache_times: Dict[str, float] = {}
        
    def _init_paddleocr(self, use_gpu: bool):
        """Initialize PaddleOCR - most accurate"""
        print("[OCR] Using PaddleOCR backend (most accurate)")
        try:
            # New PaddleOCR API (v3+)
            self.reader = PaddleOCR(lang='en')
            self.backend = "paddle"
        except Exception as e:
            print(f"[OCR] PaddleOCR init failed: {e}")
            if EASYOCR_AVAILABLE:
                self._init_easyocr(use_gpu)
        
    def _init_easyocr(self, use_gpu: bool):
        """Initialize EasyOCR"""
        print("[OCR] Using EasyOCR backend")
        self.reader = easyocr.Reader(['en'], gpu=use_gpu, verbose=False)
        self.backend = "easyocr"
        
    def _init_tesseract(self):
        """Initialize Tesseract"""
        print("[OCR] Using Tesseract backend")
        self.backend = "tesseract"
        
    def extract_text(self, frame: np.ndarray, bbox: List[float], padding: int = 3) -> str:
        """
        Extract text from a bounding box region
        """
        if self.backend is None:
            return ""
            
        h, w = frame.shape[:2]
        
        # Convert normalized bbox to pixels
        x1 = max(0, int(bbox[0] * w) - padding)
        y1 = max(0, int(bbox[1] * h) - padding)
        x2 = min(w, int(bbox[2] * w) + padding)
        y2 = min(h, int(bbox[3] * h) + padding)
        
        # Skip tiny regions
        if (x2 - x1) < 15 or (y2 - y1) < 10:
            return ""
            
        # Check cache
        cache_key = f"{x1},{y1},{x2},{y2}"
        now = time.time()
        if cache_key in self.cache:
            if now - self.cache_times[cache_key] < self.cache_ttl:
                return self.cache[cache_key]
                
        # Crop region
        roi = frame[y1:y2, x1:x2]
        
        # Preprocess
        roi = self._preprocess(roi)
        
        # OCR
        text = self._ocr_region(roi)
        
        # Cache
        self.cache[cache_key] = text
        self.cache_times[cache_key] = now
        
        return text
        
    def _preprocess(self, roi: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR accuracy"""
        if roi.size == 0:
            return roi
            
        # Upscale small images
        h, w = roi.shape[:2]
        if h < 30 or w < 50:
            scale = max(30 / h, 50 / w, 2.0)
            roi = cv2.resize(roi, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            
        # Increase contrast
        try:
            lab = cv2.cvtColor(roi, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            roi = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        except:
            pass
        
        return roi
        
    def _ocr_region(self, roi: np.ndarray) -> str:
        """OCR a cropped region"""
        if roi.size == 0:
            return ""
            
        try:
            if self.backend == "paddle":
                result = self.reader.ocr(roi)
                if result and result[0]:
                    texts = []
                    for line in result[0]:
                        if len(line) >= 2 and len(line[1]) >= 2:
                            text, conf = line[1][0], line[1][1]
                            if conf > 0.5:
                                texts.append(text)
                    return " ".join(texts).strip()
                return ""
                
            elif self.backend == "easyocr":
                results = self.reader.readtext(roi, detail=0, paragraph=True)
                return " ".join(results).strip()
                
            elif self.backend == "tesseract":
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                text = pytesseract.image_to_string(thresh, config='--psm 7 --oem 3')
                return text.strip()
                
        except Exception as e:
            return ""
            
        return ""
        
    def extract_all_probes(
        self,
        frame: np.ndarray,
        probes: List[Dict],
        max_probes: int = 15
    ) -> Dict[int, str]:
        """Extract text for multiple probes"""
        result = {}
        
        for probe in probes[:max_probes]:
            probe_id = probe.get("id")
            bbox = probe.get("bbox", [0, 0, 0, 0])
            
            text = self.extract_text(frame, bbox)
            if text:
                result[probe_id] = text
                
        return result
        
    def cleanup_cache(self):
        """Remove expired cache entries"""
        now = time.time()
        expired = [k for k, t in self.cache_times.items() 
                   if now - t > self.cache_ttl]
        for k in expired:
            del self.cache[k]
            del self.cache_times[k]
