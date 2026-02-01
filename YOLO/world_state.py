"""
World State - Maintains the current state of the browser environment
Central state for vision loop, FSM, and LLM planner
"""

import time
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from probe_tracker import TrackedProbe
from blocker_detector import Blocker


@dataclass
class WorldState:
    """Complete world state at a point in time"""
    
    # Time
    timestamp: float = 0.0
    frame_count: int = 0
    
    # Viewport
    viewport_width: int = 400
    viewport_height: int = 640
    
    # Cursor
    cursor_x: float = 0.5
    cursor_y: float = 0.5
    
    # Probes (tracked UI elements)
    probes: List[Dict] = field(default_factory=list)
    hovered_probe_id: Optional[int] = None
    
    # Blockers
    blockers: List[Dict] = field(default_factory=list)
    is_blocked: bool = False
    
    # Events (things that happened since last update)
    events: List[str] = field(default_factory=list)
    
    # Mode
    mode: str = "normal"  # normal, menu_open, modal, typing, scrolling
    
    # Last action
    last_action: Optional[Dict] = None
    last_action_result: Optional[str] = None
    
    # URL (optional, from CDP)
    url: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)
        
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
        
    def get_probe_by_id(self, probe_id: int) -> Optional[Dict]:
        """Get probe by ID"""
        for probe in self.probes:
            if probe.get("id") == probe_id:
                return probe
        return None
        
    def get_top_probes(self, n: int = 10, exclude_blocked: bool = True) -> List[Dict]:
        """Get top N probes by score"""
        sorted_probes = sorted(self.probes, key=lambda p: p.get("score", 0), reverse=True)
        
        if exclude_blocked:
            result = []
            for probe in sorted_probes:
                if not self._is_probe_blocked(probe):
                    result.append(probe)
                    if len(result) >= n:
                        break
            return result
        else:
            return sorted_probes[:n]
            
    def _is_probe_blocked(self, probe: Dict) -> bool:
        """Check if probe is inside a blocker"""
        px, py = probe.get("cx", 0), probe.get("cy", 0)
        for blocker in self.blockers:
            bbox = blocker.get("bbox", [0, 0, 0, 0])
            if bbox[0] <= px <= bbox[2] and bbox[1] <= py <= bbox[3]:
                return True
        return False


class WorldStateManager:
    """Manages world state updates from vision loop"""
    
    def __init__(self):
        self.state = WorldState()
        self.prev_state: Optional[WorldState] = None
        self.state_history: List[WorldState] = []
        self.max_history = 30
        
    def update(
        self,
        tracks: List[TrackedProbe],
        blockers: List[Blocker],
        cursor_pos: tuple = None,
        url: str = None
    ) -> WorldState:
        """
        Update world state with new detection results
        
        Args:
            tracks: Tracked probes from ProbeTracker
            blockers: Detected blockers
            cursor_pos: Current cursor position (x, y) normalized
            url: Current page URL
            
        Returns:
            Updated world state
        """
        # Save previous state
        self.prev_state = WorldState(**asdict(self.state))
        
        # Update time
        self.state.timestamp = time.time()
        self.state.frame_count += 1
        
        # Update probes
        old_probe_ids = {p["id"] for p in self.state.probes}
        self.state.probes = [t.to_dict() for t in tracks]
        new_probe_ids = {p["id"] for p in self.state.probes}
        
        # Detect events
        self.state.events = []
        
        # New probes appeared
        appeared = new_probe_ids - old_probe_ids
        if appeared:
            self.state.events.append(f"probes_appeared:{len(appeared)}")
            
        # Probes disappeared
        disappeared = old_probe_ids - new_probe_ids
        if disappeared:
            self.state.events.append(f"probes_disappeared:{len(disappeared)}")
            
        # Update blockers
        old_blocked = self.state.is_blocked
        self.state.blockers = [b.to_dict() for b in blockers]
        self.state.is_blocked = len(blockers) > 0
        
        if self.state.is_blocked and not old_blocked:
            # Determine blocker type
            blocker_types = [b.blocker_type for b in blockers]
            if "modal" in blocker_types:
                self.state.events.append("modal_appeared")
                self.state.mode = "modal"
            else:
                self.state.events.append("overlay_appeared")
                
        elif not self.state.is_blocked and old_blocked:
            self.state.events.append("blocker_closed")
            self.state.mode = "normal"
            
        # Update cursor
        if cursor_pos:
            self.state.cursor_x, self.state.cursor_y = cursor_pos
            
            # Check if hovering a probe
            self.state.hovered_probe_id = None
            for probe in self.state.probes:
                bbox = probe.get("bbox", [0, 0, 0, 0])
                if (bbox[0] <= self.state.cursor_x <= bbox[2] and
                    bbox[1] <= self.state.cursor_y <= bbox[3]):
                    self.state.hovered_probe_id = probe["id"]
                    break
                    
        # Update URL
        if url:
            if url != self.state.url:
                self.state.events.append("url_changed")
            self.state.url = url
            
        # Store in history
        self.state_history.append(WorldState(**asdict(self.state)))
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)
            
        return self.state
        
    def record_action(self, action: Dict, result: str = None):
        """Record an action taken"""
        self.state.last_action = action
        self.state.last_action_result = result
        
    def get_state(self) -> WorldState:
        """Get current state"""
        return self.state
        
    def get_diff(self) -> Dict:
        """Get difference from previous state"""
        if not self.prev_state:
            return {"type": "initial", "events": self.state.events}
            
        diff = {
            "type": "update",
            "events": self.state.events,
            "probes_count": len(self.state.probes),
            "blockers_count": len(self.state.blockers),
        }
        
        if self.state.mode != self.prev_state.mode:
            diff["mode_changed"] = self.state.mode
            
        return diff
        
    def save_to_file(self, path: str):
        """Save current state to JSON file"""
        with open(path, "w") as f:
            f.write(self.state.to_json())
            
    def has_event(self, event_name: str) -> bool:
        """Check if an event occurred"""
        return any(event_name in e for e in self.state.events)
