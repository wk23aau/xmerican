"""
Configuration for YOLO Vision Agent
"""

# Frame capture settings - MUST match actual browser viewport
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
TARGET_FPS = 30
FRAME_BUFFER_SIZE = 5

# Model settings
MODEL_PATH = "yolov8n.pt"  # Start with pretrained, fine-tune later
CONFIDENCE_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4

# Probe classes (UI elements)
PROBE_CLASSES = [
    "button",
    "link", 
    "input",
    "menu",
    "dropdown",
    "close",
    "checkbox",
    "icon",
]

# Priority keywords for job applications
PRIORITY_KEYWORDS = [
    "apply", "submit", "next", "continue", "upload",
    "sign in", "login", "email", "password", "cv", "resume"
]

# Tracking settings
IOU_THRESHOLD = 0.3
MAX_AGE = 30  # Frames before losing track
MIN_HITS = 3  # Frames before confirming track

# Mouse control
MOUSE_SPEED = 0.5  # seconds for full movement
EASING_STEPS = 20
CLICK_DELAY_MS = 50

# Scroll settings
SCROLL_DELTA_Y = 15  # Small increments for smooth scroll
SCROLL_INTERVAL_MS = 16  # ~60 Hz
MAX_SCROLL_DURATION_S = 5

# Blocker detection
BLOCKER_OPACITY_THRESHOLD = 0.3
BLOCKER_AREA_THRESHOLD = 0.5  # % of viewport

# CDP settings
CDP_HOST = "localhost"
CDP_PORT = 9222

# State machine states
class FSMState:
    IDLE = "idle"
    FIND_APPLY = "find_apply"
    CLICK_APPLY = "click_apply"
    HANDLE_LOGIN = "handle_login"
    FILL_FORM = "fill_form"
    UPLOAD_CV = "upload_cv"
    SUBMIT = "submit"
    RECOVER = "recover"
    DONE = "done"
