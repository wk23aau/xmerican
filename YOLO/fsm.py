"""
Finite State Machine for Job Application Flow
Handles navigation through application process
"""

import asyncio
from typing import Dict, Optional, Callable, List
from enum import Enum, auto
from dataclasses import dataclass
from config import FSMState


@dataclass
class StateTransition:
    """Defines a state transition"""
    from_state: str
    to_state: str
    condition: str  # Description of condition
    
    
class JobApplicationFSM:
    """
    FSM for navigating job application flows
    
    States:
    - IDLE: Not started
    - FIND_APPLY: Looking for Apply button
    - CLICK_APPLY: Clicking the Apply button
    - HANDLE_LOGIN: Dealing with login/SSO
    - FILL_FORM: Filling application form
    - UPLOAD_CV: Uploading resume/CV
    - SUBMIT: Submitting application
    - RECOVER: Error recovery
    - DONE: Completed
    """
    
    def __init__(
        self,
        get_world_state: Callable,
        scorer: 'ProbeScorer',
        mouse: 'MouseController',
        scroll: 'ScrollController'
    ):
        self.get_world_state = get_world_state
        self.scorer = scorer
        self.mouse = mouse
        self.scroll = scroll
        
        self.current_state = FSMState.IDLE
        self.state_history: List[str] = []
        self.retry_count = 0
        self.max_retries = 3
        
        # State-specific data
        self.target_probe_id: Optional[int] = None
        self.last_url: str = ""
        
        # Keywords for each state
        self.state_keywords = {
            FSMState.FIND_APPLY: ["apply", "apply now", "start application"],
            FSMState.CLICK_APPLY: ["apply", "apply now"],
            FSMState.HANDLE_LOGIN: ["sign in", "login", "log in", "email", "password"],
            FSMState.FILL_FORM: ["next", "continue", "save", "proceed"],
            FSMState.UPLOAD_CV: ["upload", "resume", "cv", "attach", "file"],
            FSMState.SUBMIT: ["submit", "send", "finish", "complete"],
        }
        
    def transition(self, new_state: str, reason: str = ""):
        """Transition to new state"""
        self.state_history.append(f"{self.current_state} -> {new_state}: {reason}")
        self.current_state = new_state
        self.retry_count = 0
        
    async def step(self, text_hints: Dict[int, str] = None) -> Dict:
        """
        Execute one step of the FSM
        
        Returns:
            Action dict with type (click_probe, scroll, wait, done, error)
        """
        world = self.get_world_state()
        
        # Check for modal blockers first
        if world.is_blocked and world.mode == "modal":
            return await self._handle_modal(world)
            
        # State-specific logic
        if self.current_state == FSMState.IDLE:
            self.transition(FSMState.FIND_APPLY, "starting")
            return {"type": "continue"}
            
        elif self.current_state == FSMState.FIND_APPLY:
            return await self._find_apply(world, text_hints)
            
        elif self.current_state == FSMState.CLICK_APPLY:
            return await self._click_apply(world)
            
        elif self.current_state == FSMState.HANDLE_LOGIN:
            return await self._handle_login(world, text_hints)
            
        elif self.current_state == FSMState.FILL_FORM:
            return await self._fill_form(world, text_hints)
            
        elif self.current_state == FSMState.UPLOAD_CV:
            return await self._upload_cv(world, text_hints)
            
        elif self.current_state == FSMState.SUBMIT:
            return await self._submit(world, text_hints)
            
        elif self.current_state == FSMState.RECOVER:
            return await self._recover(world)
            
        elif self.current_state == FSMState.DONE:
            return {"type": "done", "message": "Application complete"}
            
        return {"type": "error", "message": f"Unknown state: {self.current_state}"}
        
    async def _find_apply(self, world, text_hints: Dict = None) -> Dict:
        """Find and select Apply button"""
        keywords = self.state_keywords[FSMState.FIND_APPLY]
        
        # Score probes
        scored = self.scorer.score_probes(
            world.probes,
            text_hints=text_hints,
            target_keywords=keywords,
            blockers=world.blockers
        )
        
        if scored and scored[0]["rank_score"] > 5:
            # Found likely Apply button
            self.target_probe_id = scored[0]["id"]
            self.transition(FSMState.CLICK_APPLY, f"found probe {self.target_probe_id}")
            return {
                "type": "click_probe",
                "probe_id": self.target_probe_id,
                "probe": scored[0]
            }
            
        # Not found - try scrolling
        self.retry_count += 1
        if self.retry_count < self.max_retries:
            return {"type": "scroll", "direction": "down", "amount": 0.5}
        else:
            self.transition(FSMState.RECOVER, "apply button not found")
            return {"type": "error", "message": "Could not find Apply button"}
            
    async def _click_apply(self, world) -> Dict:
        """Click the Apply button"""
        # Check if probe still exists
        probe = world.get_probe_by_id(self.target_probe_id)
        
        if probe:
            return {
                "type": "click_probe",
                "probe_id": self.target_probe_id,
                "probe": probe,
                "on_success": lambda: self.transition(FSMState.FILL_FORM, "clicked apply")
            }
        else:
            # Probe disappeared, go back to find
            self.transition(FSMState.FIND_APPLY, "probe lost")
            return {"type": "continue"}
            
    async def _handle_login(self, world, text_hints: Dict = None) -> Dict:
        """Handle login/SSO page"""
        # Look for input fields
        input_probes = [p for p in world.probes if p.get("type") == "input"]
        
        if input_probes:
            # Found input - needs user intervention or credentials
            return {
                "type": "needs_input",
                "message": "Login required",
                "probes": input_probes
            }
            
        # Look for SSO/OAuth buttons
        scored = self.scorer.score_probes(
            world.probes,
            text_hints=text_hints,
            target_keywords=["google", "linkedin", "facebook", "continue with"],
            blockers=world.blockers
        )
        
        if scored and scored[0]["rank_score"] > 3:
            return {
                "type": "click_probe",
                "probe_id": scored[0]["id"],
                "probe": scored[0]
            }
            
        self.transition(FSMState.FILL_FORM, "no login detected")
        return {"type": "continue"}
        
    async def _fill_form(self, world, text_hints: Dict = None) -> Dict:
        """Navigate through form pages"""
        keywords = self.state_keywords[FSMState.FILL_FORM]
        
        # Check for upload section
        upload_keywords = ["upload", "resume", "cv", "attach"]
        for probe in world.probes:
            hint = text_hints.get(probe["id"], "") if text_hints else ""
            if any(kw in hint.lower() for kw in upload_keywords):
                self.transition(FSMState.UPLOAD_CV, "found upload section")
                return {"type": "continue"}
                
        # Check for submit
        submit_keywords = ["submit", "send application", "finish"]
        for probe in world.probes:
            hint = text_hints.get(probe["id"], "") if text_hints else ""
            if any(kw in hint.lower() for kw in submit_keywords):
                self.transition(FSMState.SUBMIT, "found submit button")
                return {"type": "continue"}
                
        # Look for Next/Continue
        scored = self.scorer.score_probes(
            world.probes,
            text_hints=text_hints,
            target_keywords=keywords,
            blockers=world.blockers
        )
        
        if scored and scored[0]["rank_score"] > 3:
            return {
                "type": "click_probe",
                "probe_id": scored[0]["id"],
                "probe": scored[0]
            }
            
        # Might need to scroll
        return {"type": "scroll", "direction": "down", "amount": 0.3}
        
    async def _upload_cv(self, world, text_hints: Dict = None) -> Dict:
        """Handle CV/resume upload"""
        keywords = self.state_keywords[FSMState.UPLOAD_CV]
        
        scored = self.scorer.score_probes(
            world.probes,
            text_hints=text_hints,
            target_keywords=keywords,
            blockers=world.blockers
        )
        
        if scored and scored[0]["rank_score"] > 3:
            return {
                "type": "click_probe",
                "probe_id": scored[0]["id"],
                "probe": scored[0],
                "expects": "file_dialog",
                "on_success": lambda: self.transition(FSMState.FILL_FORM, "upload clicked")
            }
            
        # If no upload found, continue to form
        self.transition(FSMState.FILL_FORM, "no upload button")
        return {"type": "continue"}
        
    async def _submit(self, world, text_hints: Dict = None) -> Dict:
        """Submit the application"""
        keywords = self.state_keywords[FSMState.SUBMIT]
        
        scored = self.scorer.score_probes(
            world.probes,
            text_hints=text_hints,
            target_keywords=keywords,
            blockers=world.blockers
        )
        
        if scored and scored[0]["rank_score"] > 5:
            return {
                "type": "click_probe",
                "probe_id": scored[0]["id"],
                "probe": scored[0],
                "on_success": lambda: self.transition(FSMState.DONE, "submitted")
            }
            
        # Fall back to looking for any primary button
        return {"type": "scroll", "direction": "down", "amount": 0.3}
        
    async def _handle_modal(self, world) -> Dict:
        """Handle modal dialogs"""
        # Look for close button or accept
        close_keywords = ["close", "×", "x", "ok", "accept", "got it"]
        
        scored = self.scorer.score_probes(
            world.probes,
            target_keywords=close_keywords,
            blockers=[]  # Don't filter by blockers when handling modal
        )
        
        if scored:
            return {
                "type": "click_probe",
                "probe_id": scored[0]["id"],
                "probe": scored[0],
                "reason": "closing modal"
            }
            
        return {"type": "wait", "duration": 0.5}
        
    async def _recover(self, world) -> Dict:
        """Error recovery"""
        self.retry_count += 1
        
        if self.retry_count > 5:
            return {"type": "error", "message": "Recovery failed"}
            
        # Try scrolling to top and restarting
        if self.retry_count == 1:
            return {"type": "scroll", "direction": "up", "amount": 1.0}
        elif self.retry_count == 2:
            self.transition(FSMState.FIND_APPLY, "retry from start")
            return {"type": "continue"}
        else:
            return {"type": "needs_help", "message": "Stuck, need assistance"}
            
    def get_status(self) -> Dict:
        """Get current FSM status"""
        return {
            "state": self.current_state,
            "retry_count": self.retry_count,
            "target_probe": self.target_probe_id,
            "history_length": len(self.state_history)
        }
        
    def reset(self):
        """Reset FSM to initial state"""
        self.current_state = FSMState.IDLE
        self.state_history = []
        self.retry_count = 0
        self.target_probe_id = None
