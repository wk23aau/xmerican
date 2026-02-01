"""
LLM Planner - Optional high-level decision making
Consults LLM when FSM is uncertain
"""

import json
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass


@dataclass
class LLMAction:
    """Action returned by LLM"""
    action_type: str  # click_probe, scroll, type, wait, ask_user
    probe_id: Optional[int] = None
    text: Optional[str] = None
    direction: Optional[str] = None
    confidence: float = 0.0
    reasoning: str = ""
    

class LLMPlanner:
    """
    LLM Planner for high-level decisions
    
    Only called when FSM is uncertain or needs semantic understanding.
    Does NOT handle coordinates or real-time control.
    """
    
    def __init__(self, llm_call: Callable = None):
        """
        Initialize LLM planner
        
        Args:
            llm_call: Async function that takes prompt and returns response
                      If None, uses mock responses
        """
        self.llm_call = llm_call
        self.history: List[Dict] = []
        
    async def decide(
        self,
        world_summary: Dict,
        top_probes: List[Dict],
        current_goal: str = "apply to job",
        context: str = ""
    ) -> LLMAction:
        """
        Ask LLM to decide next action
        
        Args:
            world_summary: Current world state summary
            top_probes: Top scored probes with text hints
            current_goal: What we're trying to do
            context: Additional context
            
        Returns:
            LLMAction with decision
        """
        prompt = self._build_prompt(world_summary, top_probes, current_goal, context)
        
        if self.llm_call:
            response = await self.llm_call(prompt)
            action = self._parse_response(response)
        else:
            # Mock response - just pick highest scored probe
            action = self._mock_decide(top_probes)
            
        self.history.append({
            "prompt_summary": current_goal,
            "probe_count": len(top_probes),
            "action": action.action_type,
            "probe_id": action.probe_id
        })
        
        return action
        
    def _build_prompt(
        self,
        world_summary: Dict,
        top_probes: List[Dict],
        goal: str,
        context: str
    ) -> str:
        """Build prompt for LLM"""
        
        probe_list = "\n".join([
            f"  {i+1}. ID={p['id']} type={p.get('type','?')} "
            f"text=\"{p.get('text_hint', 'unknown')[:30]}\" "
            f"score={p.get('rank_score', 0):.1f}"
            for i, p in enumerate(top_probes[:8])
        ])
        
        prompt = f"""You are a browser automation assistant. Your goal: {goal}

Current state:
- Mode: {world_summary.get('mode', 'normal')}
- Blockers: {world_summary.get('blockers_count', 0)}
- Events: {world_summary.get('events', [])}
{context}

Available probes (UI elements):
{probe_list}

Instructions:
- Choose ONE action: click_probe, scroll_down, scroll_up, wait, or ask_user
- If clicking, specify the probe ID
- Respond in JSON format:
  {{"action": "click_probe", "probe_id": <id>, "reasoning": "<why>"}}
  {{"action": "scroll_down", "reasoning": "<why>"}}
  {{"action": "ask_user", "question": "<what to ask>"}}

Your response (JSON only):"""
        
        return prompt
        
    def _parse_response(self, response: str) -> LLMAction:
        """Parse LLM response into action"""
        try:
            # Try to extract JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                    
            data = json.loads(response)
            
            return LLMAction(
                action_type=data.get("action", "wait"),
                probe_id=data.get("probe_id"),
                text=data.get("text"),
                direction=data.get("direction", "down"),
                confidence=data.get("confidence", 0.7),
                reasoning=data.get("reasoning", "")
            )
        except (json.JSONDecodeError, KeyError):
            # Failed to parse - default to wait
            return LLMAction(
                action_type="wait",
                confidence=0.1,
                reasoning="Failed to parse LLM response"
            )
            
    def _mock_decide(self, top_probes: List[Dict]) -> LLMAction:
        """Mock decision when no LLM available"""
        if not top_probes:
            return LLMAction(
                action_type="scroll_down",
                confidence=0.5,
                reasoning="No probes found, scrolling to find more"
            )
            
        best = top_probes[0]
        return LLMAction(
            action_type="click_probe",
            probe_id=best["id"],
            confidence=min(best.get("rank_score", 0) / 10, 1.0),
            reasoning=f"Selecting highest scored probe: {best.get('text_hint', 'unknown')[:20]}"
        )
        
    async def should_consult(
        self,
        world_summary: Dict,
        fsm_confidence: float
    ) -> bool:
        """
        Decide whether to consult LLM
        
        Args:
            world_summary: Current state
            fsm_confidence: FSM's confidence in its decision (0-1)
            
        Returns:
            True if LLM should be consulted
        """
        # Consult LLM if:
        # 1. FSM confidence is low
        if fsm_confidence < 0.3:
            return True
            
        # 2. Modal appeared (need semantic understanding)
        if world_summary.get("mode") == "modal":
            return True
            
        # 3. Multiple equally good options
        # (Would need probe scores to check this)
        
        return False
        
    def get_history(self) -> List[Dict]:
        """Get decision history for debugging"""
        return self.history
        
    def clear_history(self):
        """Clear decision history"""
        self.history = []


class SimpleLLMClient:
    """
    Simple LLM client wrapper
    Can be extended to support different providers
    """
    
    def __init__(self, provider: str = "mock"):
        self.provider = provider
        
    async def call(self, prompt: str) -> str:
        """Call LLM with prompt"""
        if self.provider == "mock":
            return self._mock_response(prompt)
        else:
            raise NotImplementedError(f"Provider {self.provider} not implemented")
            
    def _mock_response(self, prompt: str) -> str:
        """Generate mock response"""
        # Extract probe list from prompt and pick first one
        if "probe_id" in prompt.lower():
            return '{"action": "click_probe", "probe_id": 1, "reasoning": "mock decision"}'
        return '{"action": "scroll_down", "reasoning": "mock - no probes mentioned"}'
