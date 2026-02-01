"""
YOLO Vision Agent - Main Entry Point
Runs the 3-layer streaming vision agent for browser automation
"""

import asyncio
import time
import argparse
import traceback
from typing import Optional

# Import all modules
from config import TARGET_FPS, VIEWPORT_WIDTH, VIEWPORT_HEIGHT, FSMState
from cdp_client import CDPClient
from frame_capture import FrameCapture
from probe_detector import ProbeDetector
from probe_tracker import ProbeTracker
from blocker_detector import BlockerDetector
from world_state import WorldStateManager
from probe_scorer import ProbeScorer
from mouse_controller import MouseController
from scroll_controller import ScrollController
from fsm import JobApplicationFSM
from llm_planner import LLMPlanner, SimpleLLMClient
from debug_visualizer import DebugVisualizer


class VisionAgent:
    """
    Main vision agent class
    Coordinates all components in the 3-layer architecture
    """
    
    def __init__(self, use_pretrained: bool = True, headless: bool = False, debug: bool = False):
        # CDP connection
        self.cdp = CDPClient()
        
        # Layer A: Vision/Reflex (30-60 Hz)
        self.frame_capture = FrameCapture()
        self.detector = ProbeDetector(use_pretrained=use_pretrained)
        self.tracker = ProbeTracker()
        self.blocker_detector = BlockerDetector()
        
        # Layer B: State engine
        self.world_manager = WorldStateManager()
        self.scorer = ProbeScorer()
        
        # Controllers
        self.mouse: Optional[MouseController] = None
        self.scroll: Optional[ScrollController] = None
        
        # Layer C: Planning
        self.fsm: Optional[JobApplicationFSM] = None
        self.llm = LLMPlanner(llm_call=None)  # Start without LLM
        
        # Debug visualization
        self.debug = debug
        self.visualizer = DebugVisualizer() if debug else None
        
        # Runtime state
        self.running = False
        self.frame_count = 0
        self.last_frame_time = 0
        self.text_hints = {}  # probe_id -> text hint
        
    async def connect(self, target_url: str = None):
        """Connect to browser and initialize components"""
        print("Connecting to browser...")
        await self.cdp.connect(target_url)
        
        # Initialize controllers with CDP dispatch
        self.mouse = MouseController(
            dispatch_move=self.cdp.mouse_move,
            dispatch_click=self.cdp.mouse_click
        )
        
        self.scroll = ScrollController(
            dispatch_scroll=self.cdp.scroll,
            get_frame_delta=self.frame_capture.compute_frame_delta
        )
        
        # Initialize FSM
        self.fsm = JobApplicationFSM(
            get_world_state=self.world_manager.get_state,
            scorer=self.scorer,
            mouse=self.mouse,
            scroll=self.scroll
        )
        
        # Start screencast
        await self.cdp.start_screencast(self.frame_capture.on_frame)
        print("Connected and screencast started")
        
    async def run_vision_loop(self):
        """
        Run the main vision loop (Layer A)
        Runs at 30-60 Hz
        """
        print("Starting vision loop...")
        target_interval = 1.0 / TARGET_FPS
        
        while self.running:
            loop_start = time.time()
            
            # Get current frame
            frame = self.frame_capture.get_current_frame()
            
            if frame is not None:
                # Detect probes
                probes = self.detector.detect(frame)
                
                # Track probes
                tracks = self.tracker.update(probes)
                
                # Detect blockers
                frame_delta = self.frame_capture.compute_frame_delta()
                blockers = self.blocker_detector.detect(frame, frame_delta)
                
                # Update world state
                cursor_pos = self.mouse.get_position() if self.mouse else (0.5, 0.5)
                self.world_manager.update(
                    tracks=tracks,
                    blockers=blockers,
                    cursor_pos=cursor_pos
                )
                
                # Debug visualization
                if self.debug and self.visualizer:
                    world = self.world_manager.get_state()
                    vis_frame = self.visualizer.draw_probes(
                        frame=frame,
                        probes=world.probes,
                        blockers=world.blockers,
                        cursor_pos=cursor_pos,
                        state=self.fsm.current_state if self.fsm else "init",
                        hovered_id=world.hovered_probe_id
                    )
                    if not self.visualizer.show(vis_frame):
                        self.running = False  # ESC pressed
                
                self.frame_count += 1
                
            # Maintain target FPS
            elapsed = time.time() - loop_start
            sleep_time = max(0, target_interval - elapsed)
            await asyncio.sleep(sleep_time)
            
    async def run_action_loop(self):
        """
        Run the action loop (Layer B + C)
        Runs at 5-10 Hz
        """
        print("Starting action loop...")
        
        while self.running:
            try:
                # Get action from FSM
                action = await self.fsm.step(text_hints=self.text_hints)
                
                # Execute action
                await self._execute_action(action)
                
                # Log progress
                if self.frame_count % 30 == 0:
                    status = self.fsm.get_status()
                    world = self.world_manager.get_state()
                    print(f"State: {status['state']}, Probes: {len(world.probes)}, "
                          f"Blockers: {len(world.blockers)}")
                
            except Exception as e:
                print(f"Action loop error: {e}")
                traceback.print_exc()
                
            await asyncio.sleep(0.1)  # 10 Hz
            
    async def _execute_action(self, action: dict):
        """Execute an action from FSM or LLM"""
        action_type = action.get("type", "wait")
        
        if action_type == "click_probe":
            probe = action.get("probe")
            if probe:
                await self.mouse.click_probe(probe)
                self.world_manager.record_action(action, "clicked")
                
                # Call success callback if provided
                if "on_success" in action and callable(action["on_success"]):
                    action["on_success"]()
                    
        elif action_type == "scroll":
            direction = action.get("direction", "down")
            amount = action.get("amount", 0.5)
            await self.scroll.scroll_smooth(direction=direction, amount=amount)
            self.world_manager.record_action(action, "scrolled")
            
        elif action_type == "wait":
            duration = action.get("duration", 0.5)
            await asyncio.sleep(duration)
            
        elif action_type == "continue":
            pass  # Just continue to next step
            
        elif action_type == "done":
            print(f"Task complete: {action.get('message', '')}")
            self.running = False
            
        elif action_type == "error":
            print(f"Error: {action.get('message', 'Unknown error')}")
            
        elif action_type == "needs_input":
            print(f"Needs input: {action.get('message', '')}")
            # Could pause here for user input
            
        elif action_type == "needs_help":
            print(f"Needs help: {action.get('message', '')}")
            # Could trigger LLM consultation
            
    async def start(self, target_url: str = None):
        """Start the vision agent"""
        await self.connect(target_url)
        self.running = True
        
        # Run both loops concurrently
        await asyncio.gather(
            self.run_vision_loop(),
            self.run_action_loop()
        )
        
    async def stop(self):
        """Stop the vision agent"""
        print("Stopping agent...")
        self.running = False
        if self.visualizer:
            self.visualizer.close()
        await self.cdp.stop_screencast()
        await self.cdp.close()
        
    def set_target_url(self, url: str):
        """Navigate to URL"""
        asyncio.create_task(self.cdp.navigate(url))
        
    def get_status(self) -> dict:
        """Get current agent status"""
        return {
            "running": self.running,
            "frame_count": self.frame_count,
            "fsm_state": self.fsm.get_status() if self.fsm else None,
            "world": self.world_manager.get_state().to_dict() if self.world_manager else None
        }


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="YOLO Vision Agent")
    parser.add_argument("--url", type=str, help="Target URL to navigate to")
    parser.add_argument("--pretrained", action="store_true", default=True,
                       help="Use pretrained model (default)")
    parser.add_argument("--no-pretrained", dest="pretrained", action="store_false",
                       help="Use fine-tuned model")
    parser.add_argument("--debug", action="store_true",
                       help="Show debug visualization window with bounding boxes")
    args = parser.parse_args()
    
    agent = VisionAgent(use_pretrained=args.pretrained, debug=args.debug)
    
    if args.debug:
        print("Debug visualization enabled - press ESC to quit")
    
    try:
        await agent.start(target_url=args.url)
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        await agent.stop()
        

if __name__ == "__main__":
    asyncio.run(main())
