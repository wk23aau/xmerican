"""
xCLICK World Module
Handles persistent state, object tracking, and ROI masking
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from world_state import (
        WorldState, 
        TrackedObject, 
        CursorState,
        ObjectSource,
        get_world_state, 
        reset_world_state
    )
except ImportError:
    WorldState = None
    TrackedObject = None
    CursorState = None
    ObjectSource = None
    get_world_state = None
    reset_world_state = None

try:
    from roi_mask import (
        ROIMask,
        Region,
        RegionType,
        get_roi_mask,
        reset_roi_mask
    )
except ImportError:
    ROIMask = None
    Region = None
    RegionType = None
    get_roi_mask = None
    reset_roi_mask = None

__all__ = [
    'WorldState', 'TrackedObject', 'CursorState', 'ObjectSource',
    'get_world_state', 'reset_world_state',
    'ROIMask', 'Region', 'RegionType', 'get_roi_mask', 'reset_roi_mask'
]
