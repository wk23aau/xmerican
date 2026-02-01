"""
Scroll Controller - Smooth scrolling with visual feedback
Handles page and container scrolling at 60Hz
"""

import asyncio
from typing import Callable, Optional, Tuple
from config import SCROLL_DELTA_Y, SCROLL_INTERVAL_MS, MAX_SCROLL_DURATION_S


class ScrollController:
    def __init__(
        self,
        dispatch_scroll: Callable,
        get_frame_delta: Callable
    ):
        """
        Initialize scroll controller
        
        Args:
            dispatch_scroll: Async function to scroll (x, y, delta_y)
            get_frame_delta: Function that returns frame delta (for motion detection)
        """
        self.dispatch_scroll = dispatch_scroll
        self.get_frame_delta = get_frame_delta
        self.is_scrolling = False
        self._abort = False
        
    async def scroll_smooth(
        self,
        direction: str = "down",
        amount: float = 0.5,
        position: Tuple[float, float] = (0.5, 0.5),
        stop_condition: Callable = None
    ) -> bool:
        """
        Smooth scroll with visual feedback
        
        Args:
            direction: "down" or "up"
            amount: Fraction of viewport to scroll (0-1)
            position: Where to scroll from (normalized coords)
            stop_condition: Optional callback that returns True to stop
            
        Returns:
            True if completed, False if stopped early
        """
        self.is_scrolling = True
        self._abort = False
        
        delta = SCROLL_DELTA_Y if direction == "down" else -SCROLL_DELTA_Y
        interval = SCROLL_INTERVAL_MS / 1000
        max_steps = int(MAX_SCROLL_DURATION_S / interval)
        
        # Approximate steps based on amount
        target_steps = int(amount * 50)  # ~50 small scrolls per viewport
        
        no_motion_count = 0
        x, y = position
        
        for i in range(min(target_steps, max_steps)):
            if self._abort:
                break
                
            # Check stop condition
            if stop_condition and stop_condition():
                self.is_scrolling = False
                return True
                
            # Dispatch scroll
            await self.dispatch_scroll(x, y, delta)
            await asyncio.sleep(interval)
            
            # Check if page is actually scrolling
            frame_delta = self.get_frame_delta()
            if frame_delta is not None:
                import numpy as np
                motion = np.mean(frame_delta)
                
                if motion < 5:  # Low motion = not scrolling
                    no_motion_count += 1
                    if no_motion_count > 10:  # Stuck
                        break
                else:
                    no_motion_count = 0
                    
        self.is_scrolling = False
        return no_motion_count < 10
        
    async def scroll_until_visible(
        self,
        check_visible: Callable,
        direction: str = "down",
        max_scrolls: int = 10
    ) -> bool:
        """
        Scroll until target becomes visible
        
        Args:
            check_visible: Callback that returns True when target is visible
            direction: "down" or "up"
            max_scrolls: Maximum scroll attempts
            
        Returns:
            True if target found, False if max reached
        """
        for _ in range(max_scrolls):
            if check_visible():
                return True
                
            success = await self.scroll_smooth(
                direction=direction,
                amount=0.3,
                stop_condition=check_visible
            )
            
            if not success:
                # Page might be stuck, try opposite direction
                break
                
            await asyncio.sleep(0.2)  # Wait for content to load
            
        return check_visible()
        
    async def scroll_to_bottom(
        self,
        max_duration: float = 5.0
    ) -> bool:
        """Scroll to bottom of page"""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < max_duration:
            success = await self.scroll_smooth(
                direction="down",
                amount=0.5
            )
            
            if not success:
                return True  # Reached bottom (no more motion)
                
        return False
        
    async def scroll_to_top(self):
        """Scroll to top of page"""
        for _ in range(20):
            success = await self.scroll_smooth(
                direction="up",
                amount=0.5
            )
            if not success:
                return True
        return True
        
    async def page_down(self):
        """Scroll one page down"""
        await self.scroll_smooth(direction="down", amount=0.8)
        
    async def page_up(self):
        """Scroll one page up"""
        await self.scroll_smooth(direction="up", amount=0.8)
        
    def abort(self):
        """Stop current scrolling"""
        self._abort = True
