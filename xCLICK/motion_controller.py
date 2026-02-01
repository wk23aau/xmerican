"""
Motion Controller Module for xCLICK
Two-loop architecture: Perception (1-10 Hz) + Control (30-60 Hz)
Implements smooth mouse movement with state machine and exponential smoothing.
"""

import asyncio
import time
import random
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Callable, Awaitable

# ============================================================
# Configuration Parameters (ChatGPT recommended values)
# ============================================================

class MotionConfig:
    """Motion controller configuration"""
    # Loop rates
    PERCEPTION_HZ: float = 5.0       # YOLO update rate (1-10 Hz)
    CONTROL_HZ: float = 60.0         # Mouse move rate (30-120 Hz)
    
    # Motion smoothing
    SMOOTHING_FACTOR: float = 0.25   # EMA alpha (0.2-0.35)
    MAX_SPEED: float = 2000.0        # px/sec (1200-2500)
    MIN_SPEED: float = 50.0          # px/sec minimum
    
    # Deadzone & precision
    DEADZONE: float = 3.0            # px (2-4) - stop micro-jitter
    ARRIVAL_THRESHOLD: float = 5.0   # px - consider "arrived"
    
    # Hover behavior
    HOVER_JITTER: float = 4.0        # ±px (2-6) micro-movement
    HOVER_DURATION_MS: float = 400.0 # ms (300-600)
    HOVER_JITTER_HZ: float = 10.0    # micro-jitter rate
    
    # Click timing
    CLICK_DELAY_MS: float = 50.0     # ms before click
    DOUBLE_CLICK_DELAY_MS: float = 80.0


# ============================================================
# State Machine
# ============================================================

class MotionState(Enum):
    """Cursor state machine states"""
    IDLE = auto()       # No target, cursor stationary
    SEEK = auto()       # Moving toward target smoothly
    HOVER = auto()      # At target, micro-jitter to keep hover alive
    CLICK = auto()      # About to click
    COMPLETE = auto()   # Action completed


@dataclass
class CursorState:
    """Current cursor physics state"""
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0  # velocity x
    vy: float = 0.0  # velocity y
    
    def distance_to(self, tx: float, ty: float) -> float:
        """Distance to target"""
        return math.sqrt((tx - self.x) ** 2 + (ty - self.y) ** 2)


@dataclass
class Target:
    """Target for cursor to seek"""
    x: float
    y: float
    label: str = ""
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.monotonic)
    
    @property
    def age_ms(self) -> float:
        """Time since target was set"""
        return (time.monotonic() - self.timestamp) * 1000


# ============================================================
# Motion Controller
# ============================================================

class MotionController:
    """
    Two-loop motion controller for human-like cursor movement.
    
    Perception loop (slow, 1-10 Hz):
        - Receives targets from vision/DOM probes
        - Updates target coordinates
        
    Control loop (fast, 30-60 Hz):
        - Interpolates cursor toward target
        - Dispatches mouse events
        - Handles state transitions
    """
    
    def __init__(
        self,
        move_callback: Callable[[float, float], Awaitable[None]],
        click_callback: Callable[[float, float], Awaitable[None]],
        config: Optional[MotionConfig] = None
    ):
        """
        Args:
            move_callback: Async function to dispatch mouse move (x, y)
            click_callback: Async function to dispatch mouse click (x, y)
            config: Motion configuration
        """
        self.config = config or MotionConfig()
        self.move_callback = move_callback
        self.click_callback = click_callback
        
        # State
        self.cursor = CursorState()
        self.target: Optional[Target] = None
        self.state = MotionState.IDLE
        
        # Timing
        self.hover_start_time: float = 0.0
        self.last_jitter_time: float = 0.0
        self.running = False
        
        # Control loop task
        self._control_task: Optional[asyncio.Task] = None
    
    # --------------------------------------------------------
    # Target Management (called from perception loop)
    # --------------------------------------------------------
    
    def set_target(self, x: float, y: float, label: str = "", confidence: float = 1.0):
        """Set new target for cursor to seek"""
        self.target = Target(x=x, y=y, label=label, confidence=confidence)
        if self.state == MotionState.IDLE:
            self.state = MotionState.SEEK
        print(f"  [motion] Target set: ({x:.0f}, {y:.0f}) '{label}' conf={confidence:.2f}")
    
    def clear_target(self):
        """Clear current target and stop seeking"""
        self.target = None
        self.state = MotionState.IDLE
    
    def set_cursor_position(self, x: float, y: float):
        """Initialize cursor position (e.g., from current mouse location)"""
        self.cursor.x = x
        self.cursor.y = y
    
    # --------------------------------------------------------
    # Control Loop (runs at CONTROL_HZ)
    # --------------------------------------------------------
    
    async def start(self):
        """Start the control loop"""
        if self.running:
            return
        self.running = True
        self._control_task = asyncio.create_task(self._control_loop())
        print(f"  [motion] Control loop started @ {self.config.CONTROL_HZ} Hz")
    
    async def stop(self):
        """Stop the control loop"""
        self.running = False
        if self._control_task:
            self._control_task.cancel()
            try:
                await self._control_task
            except asyncio.CancelledError:
                pass
        print("  [motion] Control loop stopped")
    
    async def _control_loop(self):
        """Main control loop - runs at CONTROL_HZ"""
        dt = 1.0 / self.config.CONTROL_HZ
        
        while self.running:
            loop_start = time.monotonic()
            
            try:
                await self._update(dt)
            except Exception as e:
                print(f"  [motion] Error in control loop: {e}")
            
            # Maintain loop rate
            elapsed = time.monotonic() - loop_start
            sleep_time = max(0, dt - elapsed)
            await asyncio.sleep(sleep_time)
    
    async def _update(self, dt: float):
        """Single control loop iteration"""
        
        if self.state == MotionState.IDLE:
            return
        
        if self.target is None:
            self.state = MotionState.IDLE
            return
        
        # ---- SEEK state ----
        if self.state == MotionState.SEEK:
            await self._update_seek(dt)
        
        # ---- HOVER state ----
        elif self.state == MotionState.HOVER:
            await self._update_hover(dt)
        
        # ---- CLICK state ----
        elif self.state == MotionState.CLICK:
            await self._update_click()
    
    async def _update_seek(self, dt: float):
        """Update cursor during SEEK state - smooth movement toward target"""
        if self.target is None:
            return
        
        tx, ty = self.target.x, self.target.y
        distance = self.cursor.distance_to(tx, ty)
        
        # Check if arrived
        if distance < self.config.ARRIVAL_THRESHOLD:
            self.state = MotionState.HOVER
            self.hover_start_time = time.monotonic()
            print(f"  [motion] Arrived at target, entering HOVER")
            return
        
        # Calculate desired velocity toward target
        dx = tx - self.cursor.x
        dy = ty - self.cursor.y
        
        # Normalize and apply speed
        speed = min(self.config.MAX_SPEED, max(self.config.MIN_SPEED, distance * 3))
        
        # Apply exponential smoothing (EMA)
        target_vx = (dx / distance) * speed
        target_vy = (dy / distance) * speed
        
        alpha = self.config.SMOOTHING_FACTOR
        self.cursor.vx = alpha * target_vx + (1 - alpha) * self.cursor.vx
        self.cursor.vy = alpha * target_vy + (1 - alpha) * self.cursor.vy
        
        # Update position
        new_x = self.cursor.x + self.cursor.vx * dt
        new_y = self.cursor.y + self.cursor.vy * dt
        
        # Deadzone - don't micro-move if very close
        if distance > self.config.DEADZONE:
            self.cursor.x = new_x
            self.cursor.y = new_y
            
            # Dispatch mouse move
            await self.move_callback(self.cursor.x, self.cursor.y)
    
    async def _update_hover(self, dt: float):
        """Update cursor during HOVER state - micro-jitter to keep hover alive"""
        if self.target is None:
            return
        
        hover_elapsed_ms = (time.monotonic() - self.hover_start_time) * 1000
        
        # Check if hover duration complete → proceed to CLICK
        if hover_elapsed_ms >= self.config.HOVER_DURATION_MS:
            self.state = MotionState.CLICK
            print(f"  [motion] Hover complete, entering CLICK")
            return
        
        # Apply micro-jitter at HOVER_JITTER_HZ
        jitter_interval = 1.0 / self.config.HOVER_JITTER_HZ
        now = time.monotonic()
        
        if now - self.last_jitter_time >= jitter_interval:
            self.last_jitter_time = now
            
            # Random jitter within ±HOVER_JITTER pixels
            jitter_x = random.uniform(-self.config.HOVER_JITTER, self.config.HOVER_JITTER)
            jitter_y = random.uniform(-self.config.HOVER_JITTER, self.config.HOVER_JITTER)
            
            move_x = self.target.x + jitter_x
            move_y = self.target.y + jitter_y
            
            await self.move_callback(move_x, move_y)
    
    async def _update_click(self):
        """Execute click and complete action"""
        if self.target is None:
            return
        
        # Small delay before click
        await asyncio.sleep(self.config.CLICK_DELAY_MS / 1000)
        
        # Execute click
        await self.click_callback(self.target.x, self.target.y)
        print(f"  [motion] Clicked at ({self.target.x:.0f}, {self.target.y:.0f})")
        
        # Complete
        self.state = MotionState.COMPLETE
        self.target = None
    
    # --------------------------------------------------------
    # High-level actions
    # --------------------------------------------------------
    
    async def seek_and_click(self, x: float, y: float, label: str = "") -> bool:
        """
        Smoothly move to target and click.
        Returns True when complete.
        """
        self.set_target(x, y, label)
        
        # Wait for completion
        while self.state not in (MotionState.COMPLETE, MotionState.IDLE):
            await asyncio.sleep(0.01)
        
        # Reset for next action
        completed = self.state == MotionState.COMPLETE
        self.state = MotionState.IDLE
        return completed
    
    async def seek_only(self, x: float, y: float, label: str = "") -> bool:
        """
        Smoothly move to target but don't click.
        Useful for hover interactions.
        """
        self.set_target(x, y, label)
        
        # Wait for hover state (arrived but before click)
        while self.state == MotionState.SEEK:
            await asyncio.sleep(0.01)
        
        # Stay in hover, don't proceed to click
        self.state = MotionState.IDLE
        return True
    
    # --------------------------------------------------------
    # Utility
    # --------------------------------------------------------
    
    @property
    def is_moving(self) -> bool:
        """Check if cursor is currently moving"""
        return self.state == MotionState.SEEK
    
    @property
    def is_hovering(self) -> bool:
        """Check if cursor is in hover state"""
        return self.state == MotionState.HOVER
    
    def get_state_str(self) -> str:
        """Get human-readable state string"""
        return f"{self.state.name} @ ({self.cursor.x:.0f}, {self.cursor.y:.0f})"


# ============================================================
# Confidence Fusion (ChatGPT recommended)
# ============================================================

def fuse_confidence(vision_conf: float, dom_conf: float = 1.0) -> float:
    """
    Fuse vision and DOM confidence scores.
    
    Formula: final = vision * 0.6 + dom * 0.4
    
    - Vision lies under blur
    - DOM lies under overlays
    - Fusion provides arbitration
    """
    return vision_conf * 0.6 + dom_conf * 0.4


# ============================================================
# Coordinate Normalization (ChatGPT recommended)
# ============================================================

def normalize_coords(x: float, y: float, viewport_w: float, viewport_h: float) -> tuple[float, float]:
    """
    Normalize coordinates to viewport space (0-1).
    
    YOLO runs in image space, CDP clicks in CSS pixel space.
    Normalize to avoid device scale factor issues.
    """
    return x / viewport_w, y / viewport_h


def denormalize_coords(nx: float, ny: float, viewport_w: float, viewport_h: float) -> tuple[float, float]:
    """
    Convert normalized coords back to viewport pixels.
    """
    return nx * viewport_w, ny * viewport_h
