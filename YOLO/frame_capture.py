"""
Frame Capture Module
Receives frames from CDP screencast and maintains a ring buffer
"""

import asyncio
import numpy as np
import cv2
from collections import deque
from typing import Optional, Tuple, Dict, Any
from io import BytesIO
from PIL import Image
from config import FRAME_BUFFER_SIZE, TARGET_FPS


class FrameCapture:
    def __init__(self, buffer_size: int = FRAME_BUFFER_SIZE):
        self.buffer_size = buffer_size
        self.frame_buffer: deque = deque(maxlen=buffer_size)
        self.current_frame: Optional[np.ndarray] = None
        self.frame_metadata: Optional[Dict[str, Any]] = None
        self.frame_count = 0
        self.last_frame_time = 0
        self._lock = asyncio.Lock()
        
    async def on_frame(self, frame_data: bytes, metadata: Dict[str, Any]):
        """Callback for CDP screencast frames"""
        async with self._lock:
            # Decode JPEG to numpy array
            img = Image.open(BytesIO(frame_data))
            frame = np.array(img)
            
            # Convert RGB to BGR for OpenCV
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            
            self.current_frame = frame
            self.frame_metadata = metadata
            self.frame_count += 1
            self.last_frame_time = metadata.get("timestamp", 0)
            
            # Store in ring buffer
            self.frame_buffer.append({
                "frame": frame.copy(),
                "metadata": metadata,
                "count": self.frame_count
            })
            
    def get_current_frame(self) -> Optional[np.ndarray]:
        """Get the most recent frame"""
        return self.current_frame
        
    def get_frame_with_metadata(self) -> Tuple[Optional[np.ndarray], Optional[Dict]]:
        """Get current frame with its metadata"""
        return self.current_frame, self.frame_metadata
        
    def get_recent_frames(self, n: int = 3) -> list:
        """Get last N frames for temporal analysis"""
        return list(self.frame_buffer)[-n:]
        
    def compute_frame_delta(self) -> Optional[np.ndarray]:
        """Compute difference between last two frames (for motion/change detection)"""
        if len(self.frame_buffer) < 2:
            return None
            
        frames = list(self.frame_buffer)[-2:]
        f1 = cv2.cvtColor(frames[0]["frame"], cv2.COLOR_BGR2GRAY)
        f2 = cv2.cvtColor(frames[1]["frame"], cv2.COLOR_BGR2GRAY)
        
        delta = cv2.absdiff(f1, f2)
        return delta
        
    def get_fps(self) -> float:
        """Calculate actual FPS from recent frames"""
        if len(self.frame_buffer) < 2:
            return 0.0
            
        frames = list(self.frame_buffer)
        if len(frames) < 2:
            return 0.0
            
        t1 = frames[0]["metadata"].get("timestamp", 0)
        t2 = frames[-1]["metadata"].get("timestamp", 0)
        
        if t2 - t1 <= 0:
            return 0.0
            
        return (len(frames) - 1) / (t2 - t1)
        
    def clear(self):
        """Clear the frame buffer"""
        self.frame_buffer.clear()
        self.current_frame = None
        self.frame_metadata = None
