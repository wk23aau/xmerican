"""
xCLICK Perception Module
Handles vision (YOLO) and DOM detection
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..vision_module import VisionModule

# Re-export from parent directory
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from vision_module import VisionModule, LabeledProbe
except ImportError:
    VisionModule = None
    LabeledProbe = None

__all__ = ['VisionModule', 'LabeledProbe']
