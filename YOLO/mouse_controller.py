"""
Mouse Controller - Smooth cursor movement with easing
Handles human-like mouse movements and click execution
"""

import asyncio
import math
from typing import Tuple, Optional, Callable
from config import MOUSE_SPEED, EASING_STEPS, CLICK_DELAY_MS


class MouseController:
    def __init__(self, dispatch_move: Callable, dispatch_click: Callable):
        """
        Initialize mouse controller
        
        Args:
            dispatch_move: Async function to move mouse (x, y)
            dispatch_click: Async function to click (x, y)
        """
        self.dispatch_move = dispatch_move
        self.dispatch_click = dispatch_click
        self.current_x = 0.5
        self.current_y = 0.5
        self.target_x = 0.5
        self.target_y = 0.5
        self.is_moving = False
        self._abort = False
        
    def ease_out_quad(self, t: float) -> float:
        """Quadratic ease-out for natural deceleration"""
        return 1 - (1 - t) ** 2
        
    def ease_in_out_cubic(self, t: float) -> float:
        """Cubic ease-in-out for smooth movement"""
        if t < 0.5:
            return 4 * t * t * t
        else:
            return 1 - pow(-2 * t + 2, 3) / 2
            
    async def move_to(
        self,
        x: float,
        y: float,
        duration: float = MOUSE_SPEED,
        check_abort: Callable = None
    ) -> bool:
        """
        Move cursor to position with easing
        
        Args:
            x: Target X (normalized 0-1)
            y: Target Y (normalized 0-1)
            duration: Movement duration in seconds
            check_abort: Optional callback that returns True to abort
            
        Returns:
            True if completed, False if aborted
        """
        self.target_x = x
        self.target_y = y
        self.is_moving = True
        self._abort = False
        
        start_x = self.current_x
        start_y = self.current_y
        
        steps = max(int(duration * 60), 5)  # ~60 fps
        step_delay = duration / steps
        
        for i in range(steps + 1):
            if self._abort or (check_abort and check_abort()):
                self.is_moving = False
                return False
                
            # Calculate eased position
            t = i / steps
            eased_t = self.ease_in_out_cubic(t)
            
            # Interpolate
            self.current_x = start_x + (x - start_x) * eased_t
            self.current_y = start_y + (y - start_y) * eased_t
            
            # Dispatch move
            await self.dispatch_move(self.current_x, self.current_y)
            
            if i < steps:
                await asyncio.sleep(step_delay)
                
        self.is_moving = False
        return True
        
    async def move_to_probe(
        self,
        probe: dict,
        offset: Tuple[float, float] = (0, 0),
        check_abort: Callable = None
    ) -> bool:
        """
        Move to a probe's center
        
        Args:
            probe: Probe dict with cx, cy
            offset: Optional (dx, dy) offset from center
            check_abort: Optional abort check callback
        """
        x = probe.get("cx", 0.5) + offset[0]
        y = probe.get("cy", 0.5) + offset[1]
        
        # Clamp to viewport
        x = max(0.01, min(0.99, x))
        y = max(0.01, min(0.99, y))
        
        return await self.move_to(x, y, check_abort=check_abort)
        
    async def click(self, x: float = None, y: float = None) -> bool:
        """
        Click at position (or current position if not specified)
        """
        if x is not None and y is not None:
            # Move first
            await self.move_to(x, y, duration=0.2)
            
        await asyncio.sleep(CLICK_DELAY_MS / 1000)
        await self.dispatch_click(self.current_x, self.current_y)
        return True
        
    async def click_probe(
        self,
        probe: dict,
        verify_position: Callable = None
    ) -> bool:
        """
        Click on a probe
        
        Args:
            probe: Probe to click
            verify_position: Optional callback to verify probe still valid
        """
        # Move to probe
        success = await self.move_to_probe(probe)
        if not success:
            return False
            
        # Verify position if callback provided
        if verify_position:
            if not verify_position(probe, self.current_x, self.current_y):
                return False
                
        # Small delay then click
        await asyncio.sleep(0.05)
        await self.dispatch_click(self.current_x, self.current_y)
        return True
        
    async def hover_and_wait(
        self,
        x: float,
        y: float,
        wait_time: float = 0.3
    ):
        """
        Move to position and wait (for hover menus)
        """
        await self.move_to(x, y)
        await asyncio.sleep(wait_time)
        
    async def maintain_hover_in_corridor(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        corridor_width: float = 0.05,
        duration: float = 1.0
    ):
        """
        Keep cursor in a corridor between two points
        Useful for hover menu navigation
        """
        sx, sy = start
        ex, ey = end
        
        # Move along corridor
        steps = int(duration * 30)
        for i in range(steps):
            t = i / steps
            
            # Position along line
            x = sx + (ex - sx) * t
            y = sy + (ey - sy) * t
            
            # Small random perturbation within corridor
            import random
            x += random.uniform(-corridor_width/2, corridor_width/2)
            y += random.uniform(-corridor_width/2, corridor_width/2)
            
            await self.dispatch_move(x, y)
            self.current_x = x
            self.current_y = y
            await asyncio.sleep(duration / steps)
            
    def abort(self):
        """Abort current movement"""
        self._abort = True
        
    def get_position(self) -> Tuple[float, float]:
        """Get current cursor position"""
        return (self.current_x, self.current_y)
        
    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance from current position to target"""
        dx = x - self.current_x
        dy = y - self.current_y
        return math.sqrt(dx*dx + dy*dy)
