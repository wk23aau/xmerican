# xCLICK Configuration

# CDP Connection
CDP_HOST = "127.0.0.1"
CDP_PORT = 9222

# Viewport
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720

# Vision Settings
# Model type options:
#   'ui'      - Pre-trained UI detection model (macpaw-research/yolov11l) [RECOMMENDED]
#   'yolo26n' - YOLO26 nano (fastest, Jan 2026)
#   'yolo26s' - YOLO26 small (balanced)
#   'yolo26m' - YOLO26 medium (most accurate)
VISION_MODEL_TYPE = "ui"  # Use pre-trained UI detection model
YOLO_MODEL_PATH = "../YOLO/yolov8n.pt"  # Fallback if HuggingFace model unavailable
VISION_CONFIDENCE_THRESHOLD = 0.25  # Detection confidence threshold
VISION_NMS_THRESHOLD = 0.45  # Non-max suppression threshold
USE_OCR_FALLBACK = True  # Use OCR when DOM gives no label (for canvas elements)
