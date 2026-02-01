"""
YOLO Probe Server - Perception Only
Streams probe detections to external consumers (no actions)
"""

import asyncio
import time
import json
import os
from typing import Optional, Callable, Dict

from config import TARGET_FPS, VIEWPORT_WIDTH, VIEWPORT_HEIGHT
from cdp_client import CDPClient
from frame_capture import FrameCapture
from probe_detector import ProbeDetector
from probe_tracker import ProbeTracker
from blocker_detector import BlockerDetector
from world_state import WorldStateManager
from debug_visualizer import DebugVisualizer

# Try to import OCR
try:
    from probe_ocr import ProbeOCR
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("[YOLO] OCR not available - probes will not have text context")


class YOLOProbeServer:
    """
    YOLO Perception Layer - Streams probes, NO actions
    
    The executor (agent) reads probes and performs actions via CDP REPL.
    """
    
    def __init__(self, debug: bool = False, output_file: str = "output/yolo_probes.json", enable_ocr: bool = True):
        # CDP connection (for screencast only)
        self.cdp = CDPClient()
        
        # Vision components
        self.frame_capture = FrameCapture()
        self.detector = ProbeDetector(use_pretrained=True)
        self.tracker = ProbeTracker()
        self.blocker_detector = BlockerDetector()
        
        # OCR for probe text
        self.ocr = None
        if enable_ocr and OCR_AVAILABLE:
            self.ocr = ProbeOCR(use_gpu=False)
        self.probe_texts: Dict[int, str] = {}
        
        # State (perception only)
        self.world_manager = WorldStateManager()
        
        # Debug visualization
        self.debug = debug
        self.visualizer = DebugVisualizer() if debug else None
        
        # Output
        self.output_file = output_file
        self.on_probes_callback: Optional[Callable] = None
        
        # Runtime
        self.running = False
        self.frame_count = 0
        self.current_frame = None  # Store for OCR
        
    async def connect(self):
        """Connect to browser for screencast"""
        print("[YOLO] Connecting to browser...")
        await self.cdp.connect()
        await self.cdp.start_screencast(self.frame_capture.on_frame)
        print("[YOLO] Connected - streaming frames")
        
    async def run(self):
        """Run perception loop - outputs probes, no actions"""
        print(f"[YOLO] Starting perception loop at {TARGET_FPS} Hz")
        print(f"[YOLO] Probes written to: {self.output_file}")
        
        self.running = True
        target_interval = 1.0 / TARGET_FPS
        
        while self.running:
            loop_start = time.time()
            
            frame = self.frame_capture.get_current_frame()
            
            if frame is not None:
                self.current_frame = frame  # Store for OCR
                
                # Detect and track
                probes = self.detector.detect(frame)
                tracks = self.tracker.update(probes)
                
                # Detect blockers
                frame_delta = self.frame_capture.compute_frame_delta()
                blockers = self.blocker_detector.detect(frame, frame_delta)
                
                # Update world state (no cursor - we don't control it)
                self.world_manager.update(
                    tracks=tracks,
                    blockers=blockers,
                    cursor_pos=(0.5, 0.5)  # Placeholder
                )
                
                # OCR extraction (every 10 frames to save CPU)
                if self.ocr and self.frame_count % 10 == 0:
                    world = self.world_manager.get_state()
                    self.probe_texts = self.ocr.extract_all_probes(frame, world.probes, max_probes=15)
                
                # Output probes to file
                await self._write_probes()
                
                # Callback if set
                if self.on_probes_callback:
                    world = self.world_manager.get_state()
                    self.on_probes_callback(world.probes, world.blockers)
                
                # Debug visualization
                if self.debug and self.visualizer:
                    world = self.world_manager.get_state()
                    vis_frame = self.visualizer.draw_probes(
                        frame=frame,
                        probes=world.probes,
                        blockers=world.blockers,
                        cursor_pos=None,
                        state="perception",
                        hovered_id=None
                    )
                    if not self.visualizer.show(vis_frame):
                        self.running = False
                
                self.frame_count += 1
                
                # Log every second
                if self.frame_count % TARGET_FPS == 0:
                    world = self.world_manager.get_state()
                    ocr_count = len(self.probe_texts)
                    print(f"[YOLO] Frame {self.frame_count} | Probes: {len(world.probes)} | OCR: {ocr_count} | Blockers: {len(world.blockers)}")
            
            # Maintain FPS
            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0, target_interval - elapsed))
            
    async def _write_probes(self):
        """Write current probes to JSON file with OCR text"""
        world = self.world_manager.get_state()
        
        # Add text to each probe
        probes_with_text = []
        for probe in world.probes:
            probe_copy = dict(probe)
            probe_id = probe.get("id")
            if probe_id in self.probe_texts:
                probe_copy["text"] = self.probe_texts[probe_id]
            probes_with_text.append(probe_copy)
        
        output = {
            "timestamp": time.time(),
            "frame": self.frame_count,
            "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "probes": probes_with_text,
            "blockers": [{"type": b.get("type"), "bbox": b.get("bbox")} for b in world.blockers],
            "events": world.events,
            "mode": world.mode
        }
        
        import os
        os.makedirs("output", exist_ok=True)
        
        with open(self.output_file, "w") as f:
            json.dump(output, f, indent=2, default=str)
            
    def get_probes(self):
        """Get current probes (for programmatic access)"""
        return self.world_manager.get_state().probes
        
    def get_world(self):
        """Get full world state"""
        return self.world_manager.get_state()
        
    async def stop(self):
        """Stop perception"""
        print("[YOLO] Stopping...")
        self.running = False
        if self.visualizer:
            self.visualizer.close()
        await self.cdp.stop_screencast()
        await self.cdp.close()


async def main():
    """Run YOLO as standalone perception server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="YOLO Probe Server (Perception Only)")
    parser.add_argument("--debug", action="store_true", help="Show debug visualization")
    parser.add_argument("--output", type=str, default="output/yolo_probes.json", 
                       help="Output file for probes")
    args = parser.parse_args()
    
    server = YOLOProbeServer(debug=args.debug, output_file=args.output)
    
    try:
        await server.connect()
        await server.run()
    except KeyboardInterrupt:
        print("\n[YOLO] Interrupted")
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
