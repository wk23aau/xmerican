"""
xCLICK OCR Module
Lightweight text extraction for canvas/WebGL elements when DOM labels fail
Uses EasyOCR (2026 best practice for lightweight OCR)
"""

import io
from typing import Optional, Tuple, List
from PIL import Image

# Lazy-loaded OCR reader
_ocr_reader = None
_ocr_available = None


def is_ocr_available() -> bool:
    """Check if OCR is available"""
    global _ocr_available
    if _ocr_available is None:
        try:
            import easyocr
            _ocr_available = True
        except ImportError:
            _ocr_available = False
    return _ocr_available


def get_ocr_reader():
    """Get or initialize lazy-loaded OCR reader"""
    global _ocr_reader
    if _ocr_reader is None and is_ocr_available():
        import easyocr
        # Initialize with English, GPU if available
        _ocr_reader = easyocr.Reader(['en'], gpu=True, verbose=False)
        print("✓ OCR reader initialized (EasyOCR)")
    return _ocr_reader


def extract_text_from_region(
    screenshot_bytes: bytes,
    bbox: Tuple[float, float, float, float],
    padding: int = 5
) -> Optional[str]:
    """
    Extract text from a specific region of a screenshot.
    
    Args:
        screenshot_bytes: PNG screenshot as bytes
        bbox: Bounding box (x1, y1, x2, y2) in CSS pixels
        padding: Extra pixels around bbox for context
        
    Returns:
        Extracted text or None if failed/empty
    """
    if not is_ocr_available():
        return None
        
    reader = get_ocr_reader()
    if reader is None:
        return None
        
    try:
        # Load image
        img = Image.open(io.BytesIO(screenshot_bytes))
        
        # Crop to bbox with padding
        x1, y1, x2, y2 = bbox
        crop_box = (
            max(0, int(x1 - padding)),
            max(0, int(y1 - padding)),
            min(img.width, int(x2 + padding)),
            min(img.height, int(y2 + padding))
        )
        cropped = img.crop(crop_box)
        
        # Convert to bytes for EasyOCR
        import numpy as np
        img_array = np.array(cropped)
        
        # Run OCR
        results = reader.readtext(img_array)
        
        if not results:
            return None
            
        # Concatenate all detected text
        texts = [r[1] for r in results if r[2] > 0.5]  # Confidence threshold
        return " ".join(texts).strip() if texts else None
        
    except Exception as e:
        print(f"  [OCR] Warning: {e}")
        return None


def batch_extract_text(
    screenshot_bytes: bytes,
    bboxes: List[Tuple[float, float, float, float]],
    padding: int = 5
) -> List[Optional[str]]:
    """
    Extract text from multiple regions efficiently.
    
    Args:
        screenshot_bytes: PNG screenshot as bytes
        bboxes: List of bounding boxes
        padding: Extra pixels around each bbox
        
    Returns:
        List of extracted texts (None for failed regions)
    """
    results = []
    for bbox in bboxes:
        text = extract_text_from_region(screenshot_bytes, bbox, padding)
        results.append(text)
    return results


# Quick test function
async def test_ocr():
    """Test OCR availability and basic functionality"""
    if not is_ocr_available():
        print("✗ OCR not available. Install: pip install easyocr")
        return False
        
    reader = get_ocr_reader()
    print(f"✓ OCR ready: {reader is not None}")
    return True
