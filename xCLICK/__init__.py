"""
xCLICK - Visual Browser Automation
DOM-based automation with YOLO vision, smooth mouse movement, and live debugging

Architecture:
    perception/  - Vision (YOLO) and DOM detection
    world/       - Persistent state, object tracking, ROI masking  
    execution/   - Mouse movement, clicking, typing (CDP)
    ui/          - Visual overlay rendering

Usage:
    python xclick.py --vision    # Full mode with YOLO
    python xclick.py             # DOM-only mode
    
    # Or as package:
    from xclick import xClick
    
    async def main():
        x = xClick(vision=True)
        await x.connect()
        await x.click("Submit")
"""

__version__ = "2.0.0"
__author__ = "xCLICK"

# Core class
from xclick import xClick

# Modules for advanced usage
from perception import VisionModule, LabeledProbe
from world import WorldState, TrackedObject, ROIMask, get_world_state, get_roi_mask
from execution import MotionController, CDPClient
from ui import OverlayRenderer

__all__ = [
    'xClick',
    'VisionModule', 'LabeledProbe',
    'WorldState', 'TrackedObject', 'ROIMask', 'get_world_state', 'get_roi_mask',
    'MotionController', 'CDPClient',
    'OverlayRenderer'
]
