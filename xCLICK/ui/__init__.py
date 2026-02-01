"""
xCLICK UI Module
Handles visual feedback: overlay rendering
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from overlay import (
        OverlayRenderer,
        OVERLAY_INIT_JS,
        generate_update_js,
        generate_clear_js,
        generate_remove_js
    )
except ImportError:
    OverlayRenderer = None
    OVERLAY_INIT_JS = None
    generate_update_js = None
    generate_clear_js = None
    generate_remove_js = None

__all__ = [
    'OverlayRenderer',
    'OVERLAY_INIT_JS',
    'generate_update_js',
    'generate_clear_js', 
    'generate_remove_js'
]
