"""
Probe Scorer - Scores probes for job application flow
Uses keywords, position, appearance to rank click candidates
"""

import re
from typing import List, Dict, Optional
from config import PRIORITY_KEYWORDS


class ProbeScorer:
    def __init__(self):
        # Keywords organized by priority and category
        self.keyword_weights = {
            # High priority - direct apply actions
            "apply": 10.0,
            "submit": 9.0,
            "apply now": 10.0,
            "submit application": 9.5,
            
            # Medium-high - navigation
            "next": 7.0,
            "continue": 7.0,
            "proceed": 6.5,
            
            # Medium - form actions
            "upload": 6.0,
            "upload cv": 8.0,
            "upload resume": 8.0,
            "attach": 5.5,
            
            # Login related
            "sign in": 5.0,
            "login": 5.0,
            "log in": 5.0,
            
            # Close/dismiss - useful for modals
            "close": 4.0,
            "dismiss": 3.5,
            "cancel": 2.0,
            "×": 4.5,  # Close button
            "x": 3.0,
            
            # Negative indicators
            "no thanks": -5.0,
            "decline": -3.0,
            "skip": -2.0,
        }
        
        # Position preferences (normalized coords)
        # Primary CTA often in certain positions
        self.position_weights = {
            "center_bottom": 2.0,  # Modal confirm buttons
            "right_bottom": 1.5,   # Next/Continue buttons
            "top_right": 1.0,      # Close buttons
            "center": 0.5,
        }
        
    def score_probes(
        self,
        probes: List[Dict],
        text_hints: Dict[int, str] = None,
        target_keywords: List[str] = None,
        blockers: List[Dict] = None
    ) -> List[Dict]:
        """
        Score and rank probes
        
        Args:
            probes: List of probe dicts from world state
            text_hints: Optional dict mapping probe_id to extracted text
            target_keywords: Optional specific keywords to prioritize
            blockers: List of blocker regions to penalize inside
            
        Returns:
            Probes sorted by score (highest first) with 'rank_score' added
        """
        scored = []
        
        for probe in probes:
            score = self._score_probe(probe, text_hints, target_keywords, blockers)
            probe_copy = probe.copy()
            probe_copy["rank_score"] = score
            scored.append(probe_copy)
            
        # Sort by score
        scored.sort(key=lambda p: p["rank_score"], reverse=True)
        
        return scored
        
    def _score_probe(
        self,
        probe: Dict,
        text_hints: Dict[int, str] = None,
        target_keywords: List[str] = None,
        blockers: List[Dict] = None
    ) -> float:
        """Calculate score for a single probe"""
        score = probe.get("score", 0.5) * 5  # Base: detection confidence
        
        # 1. Type bonus
        probe_type = probe.get("type", "")
        type_bonus = {
            "button": 2.0,
            "link": 1.0,
            "input": 0.5,
            "close": 1.5,
            "dropdown": 0.3,
        }
        score += type_bonus.get(probe_type, 0)
        
        # 2. Keyword matching
        text = ""
        if text_hints and probe.get("id") in text_hints:
            text = text_hints[probe["id"]].lower()
        elif "text_hint" in probe:
            text = probe["text_hint"].lower()
            
        if text:
            # Check against weight table
            for keyword, weight in self.keyword_weights.items():
                if keyword.lower() in text:
                    score += weight
                    
            # Check against target keywords
            if target_keywords:
                for kw in target_keywords:
                    if kw.lower() in text:
                        score += 5.0
                        
        # 3. Position scoring
        cx = probe.get("cx", 0.5)
        cy = probe.get("cy", 0.5)
        
        # Center-bottom (modal confirm)
        if 0.3 < cx < 0.7 and cy > 0.6:
            score += self.position_weights["center_bottom"]
            
        # Right-bottom (next/continue)
        if cx > 0.6 and cy > 0.6:
            score += self.position_weights["right_bottom"]
            
        # Top-right (close button)
        if cx > 0.8 and cy < 0.2:
            score += self.position_weights["top_right"]
            
        # 4. Size scoring - prefer reasonably sized buttons
        w = probe.get("w", 0.1)
        h = probe.get("h", 0.05)
        area = w * h
        
        # Sweet spot for buttons
        if 0.01 < area < 0.1:
            score += 1.0
        elif area > 0.2:
            score -= 1.0  # Too big, probably not a button
            
        # 5. Blocker penalty
        if blockers:
            for blocker in blockers:
                bbox = blocker.get("bbox", [0, 0, 0, 0])
                if bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]:
                    # Inside blocker - might still be clickable (modal buttons)
                    if blocker.get("type") == "modal":
                        score += 0.5  # Slight bonus for modal interior
                    elif blocker.get("type") == "overlay":
                        score -= 3.0  # Penalty for overlay-blocked
                        
        # 6. Confirmation bonus
        if probe.get("confirmed", False):
            score += 0.5
            
        return score
        
    def get_best_probe(
        self,
        probes: List[Dict],
        text_hints: Dict[int, str] = None,
        target_keywords: List[str] = None,
        blockers: List[Dict] = None,
        min_score: float = 0
    ) -> Optional[Dict]:
        """Get the highest scoring probe above minimum threshold"""
        scored = self.score_probes(probes, text_hints, target_keywords, blockers)
        
        if scored and scored[0]["rank_score"] > min_score:
            return scored[0]
        return None
        
    def filter_by_keywords(
        self,
        probes: List[Dict],
        text_hints: Dict[int, str],
        keywords: List[str]
    ) -> List[Dict]:
        """Filter probes to only those matching keywords"""
        result = []
        keywords_lower = [k.lower() for k in keywords]
        
        for probe in probes:
            text = ""
            if probe.get("id") in text_hints:
                text = text_hints[probe["id"]].lower()
            elif "text_hint" in probe:
                text = probe["text_hint"].lower()
                
            for kw in keywords_lower:
                if kw in text:
                    result.append(probe)
                    break
                    
        return result
