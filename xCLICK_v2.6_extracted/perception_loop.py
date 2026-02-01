"""
xCLICK Perception Loop
Continuous background perception at 15Hz
Updates world state without blocking main thread
"""

import asyncio
import time
from typing import Optional, Callable, Awaitable
from world_state import get_world_state, ObjectSource
from tracker import get_tracker


class PerceptionLoop:
    """
    Always-on perception loop running at configurable Hz.
    Updates world state continuously, executor doesn't wait.
    
    ChatGPT Gap C fix: "continuous 10-30Hz perception loop"
    """
    
    def __init__(self, 
                 refresh_dom: Callable[[], Awaitable],
                 refresh_vision: Optional[Callable[[], Awaitable]] = None,
                 dom_hz: float = 10.0,
                 vision_hz: float = 15.0):
        """
        Args:
            refresh_dom: Async function to refresh DOM probes
            refresh_vision: Async function to refresh vision probes (optional)
            dom_hz: DOM detection rate (default 10Hz)
            vision_hz: YOLO detection rate (default 15Hz)
        """
        self.refresh_dom = refresh_dom
        self.refresh_vision = refresh_vision
        self.dom_hz = dom_hz
        self.vision_hz = vision_hz
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._dom_interval = 1.0 / dom_hz
        self._vision_interval = 1.0 / vision_hz
        
        # Timing
        self._last_dom_time = 0.0
        self._last_vision_time = 0.0
        self._frame_count = 0
        self._start_time = 0.0
        
        # World state and tracker
        self.world = get_world_state()
        self.tracker = get_tracker()
        
    async def start(self):
        """Start the perception loop"""
        if self._running:
            return
            
        self._running = True
        self._start_time = time.monotonic()
        self._task = asyncio.create_task(self._run_loop())
        print(f"  [perception] Started @ DOM {self.dom_hz}Hz, Vision {self.vision_hz}Hz")
        
    async def stop(self):
        """Stop the perception loop"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        elapsed = time.monotonic() - self._start_time
        if elapsed > 0:
            print(f"  [perception] Stopped. {self._frame_count} frames in {elapsed:.1f}s ({self._frame_count/elapsed:.1f} fps)")
            
    async def _run_loop(self):
        """Main perception loop - runs continuously"""
        try:
            while self._running:
                now = time.monotonic()
                
                # Check if DOM refresh is due
                if now - self._last_dom_time >= self._dom_interval:
                    try:
                        await self.refresh_dom()
                        self._last_dom_time = now
                    except Exception as e:
                        print(f"  [perception] DOM error: {e}")
                
                # Check if vision refresh is due
                if self.refresh_vision and now - self._last_vision_time >= self._vision_interval:
                    try:
                        await self.refresh_vision()
                        self._last_vision_time = now
                    except Exception as e:
                        print(f"  [perception] Vision error: {e}")
                
                self._frame_count += 1
                
                # Small sleep to prevent CPU spin
                await asyncio.sleep(0.001)
                
        except asyncio.CancelledError:
            pass
            
    @property
    def is_running(self) -> bool:
        return self._running
        
    @property
    def fps(self) -> float:
        """Current effective FPS"""
        elapsed = time.monotonic() - self._start_time
        return self._frame_count / elapsed if elapsed > 0 else 0.0
        
    def status(self) -> str:
        """Get perception loop status"""
        if not self._running:
            return "Perception loop: STOPPED"
        return (f"Perception loop: RUNNING @ {self.fps:.1f} fps "
                f"(DOM {self.dom_hz}Hz, Vision {self.vision_hz}Hz)")


# Singleton instance
_perception_loop: Optional[PerceptionLoop] = None

def get_perception_loop() -> Optional[PerceptionLoop]:
    """Get the global perception loop"""
    return _perception_loop

def create_perception_loop(refresh_dom, refresh_vision=None, 
                           dom_hz=10.0, vision_hz=15.0) -> PerceptionLoop:
    """Create and register global perception loop"""
    global _perception_loop
    _perception_loop = PerceptionLoop(refresh_dom, refresh_vision, dom_hz, vision_hz)
    return _perception_loop
