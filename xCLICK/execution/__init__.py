"""
xCLICK Execution Module
Handles actions: mouse movement, clicking, typing, navigation
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from motion_controller import (
        MotionController,
        MotionConfig,
        MotionState,
        Target
    )
except ImportError:
    MotionController = None
    MotionConfig = None
    MotionState = None
    Target = None

try:
    from cdp_client import CDPClient
except ImportError:
    CDPClient = None

__all__ = [
    'MotionController', 'MotionConfig', 'MotionState', 'Target',
    'CDPClient'
]
