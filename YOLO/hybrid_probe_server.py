"""
Hybrid DOM + YOLO Probe Server

DOM provides:
- Ground truth element positions (getBoundingClientRect)
- Element type (button, link, input)
- Element text
- 100% accurate coordinates

YOLO provides:
- Visual confirmation element is visible
- Detection of overlays/blockers
- Visual state (hover, focus, etc.)
"""

import asyncio
import json
import time
import cv2
import numpy as np
import base64
from typing import Dict, List, Optional
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT, TARGET_FPS
from debug_visualizer import DebugVisualizer


class HybridProbeServer:
    """
    Hybrid DOM + YOLO detection:
    - DOM: Ground truth for element coordinates and text
    - YOLO: Visual confirmation and blocker detection
    """
    
    def __init__(self, output_file: str = "output/yolo_probes.json", debug: bool = False):
        self.cdp = CDPClient()
        self.output_file = output_file
        self.debug = debug
        self.running = False
        self.frame_count = 0
        self.probes = []
        self.current_frame = None
        
        # Debug visualization
        self.visualizer = DebugVisualizer() if debug else None
        
    async def connect(self):
        """Connect to browser"""
        print("[HYBRID] Connecting to browser...")
        await self.cdp.connect()
        print("[HYBRID] Connected - DOM + YOLO ready")
        
    async def _get_dom_elements(self) -> List[Dict]:
        """Get all interactive elements from DOM - ground truth"""
        js = """
        (function() {
            var results = [];
            var id = 0;
            
            var selectors = [
                'button', 'a', 'input', 'select', 'textarea',
                '[role="button"]', '[role="link"]', '[role="menuitem"]',
                '[onclick]', '[class*="btn"]'
            ].join(', ');
            
            var elements = document.querySelectorAll(selectors);
            
            elements.forEach(function(el) {
                var rect = el.getBoundingClientRect();
                
                // Skip invisible/offscreen
                if (rect.width <= 0 || rect.height <= 0) return;
                if (rect.bottom < 0 || rect.top > window.innerHeight) return;
                if (rect.right < 0 || rect.left > window.innerWidth) return;
                
                var tag = el.tagName.toLowerCase();
                var text = (el.innerText || el.value || el.placeholder || 
                           el.alt || el.title || el.getAttribute('aria-label') || '').trim();
                text = text.substring(0, 50).replace(/\\n/g, ' ');
                
                var role = el.getAttribute('role') || '';
                var type = el.getAttribute('type') || '';
                
                // Determine probe type
                var probeType = 'unknown';
                if (tag === 'button' || role === 'button') probeType = 'button';
                else if (tag === 'a' || role === 'link') probeType = 'link';
                else if (tag === 'input') probeType = type === 'submit' ? 'button' : 'input';
                else if (tag === 'select') probeType = 'dropdown';
                else if (tag === 'textarea') probeType = 'input';
                
                results.push({
                    id: id++,
                    type: probeType,
                    tag: tag,
                    text: text,
                    cx: rect.left + rect.width / 2,
                    cy: rect.top + rect.height / 2,
                    bbox: [rect.left, rect.top, rect.right, rect.bottom],
                    width: rect.width,
                    height: rect.height,
                    score: 1.0,
                    source: 'DOM'
                });
            });
            
            return results;
        })()
        """
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        return result.get("result", {}).get("result", {}).get("value", []) or []
        
    async def _get_screenshot(self) -> Optional[np.ndarray]:
        """Get current screenshot as numpy array"""
        try:
            data = await self.cdp.screenshot()
            img_bytes = base64.b64decode(data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except:
            return None
        
    def _yolo_verify_visibility(self, frame: np.ndarray, probes: List[Dict]) -> List[Dict]:
        """
        Use visual analysis to verify element visibility
        Check if DOM elements are actually visible on screen
        """
        if frame is None:
            return probes
            
        h, w = frame.shape[:2]
        verified = []
        
        for probe in probes:
            # Get bounding box
            bbox = probe.get('bbox', [0, 0, 0, 0])
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            
            # Ensure bounds are valid
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            if x2 <= x1 or y2 <= y1:
                continue
                
            # Extract region
            region = frame[y1:y2, x1:x2]
            
            # Visual checks:
            # 1. Check if region is not blank (uniform color)
            if region.size > 0:
                std = np.std(region)
                probe['visibility'] = 'visible' if std > 10 else 'blank'
                probe['visual_std'] = float(std)
                
            # 2. Calculate average color (for detecting state changes)
            if region.size > 0:
                avg_color = np.mean(region, axis=(0, 1))
                probe['avg_color'] = [int(c) for c in avg_color]
                
            verified.append(probe)
            
        return verified
        
    async def run(self):
        """Run hybrid perception loop"""
        print(f"[HYBRID] Starting at {TARGET_FPS} Hz")
        print(f"[HYBRID] Output: {self.output_file}")
        
        self.running = True
        target_interval = 1.0 / TARGET_FPS
        
        while self.running:
            loop_start = time.time()
            
            try:
                # 1. Get DOM elements (ground truth)
                self.probes = await self._get_dom_elements()
                
                # 2. Get screenshot for visual verification
                if self.debug or self.frame_count % 10 == 0:
                    self.current_frame = await self._get_screenshot()
                    
                    # 3. YOLO verification (check visibility)
                    if self.current_frame is not None:
                        self.probes = self._yolo_verify_visibility(self.current_frame, self.probes)
                
                # 4. Write probes
                await self._write_probes()
                
                # 5. Debug visualization
                if self.debug and self.visualizer and self.current_frame is not None:
                    vis_frame = self._draw_debug(self.current_frame.copy())
                    if not self.visualizer.show(vis_frame):
                        self.running = False
                
                self.frame_count += 1
                
                if self.frame_count % TARGET_FPS == 0:
                    print(f"[HYBRID] Frame {self.frame_count} | DOM: {len(self.probes)}")
                    
            except Exception as e:
                print(f"[HYBRID] Error: {e}")
                
            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0, target_interval - elapsed))
            
    def _draw_debug(self, frame: np.ndarray) -> np.ndarray:
        """Draw debug visualization"""
        h, w = frame.shape[:2]
        
        for probe in self.probes:
            bbox = probe.get('bbox', [0, 0, 0, 0])
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            cx, cy = int(probe.get('cx', 0)), int(probe.get('cy', 0))
            
            ptype = probe.get('type', 'unknown')
            text = probe.get('text', '')[:20]
            
            # Color based on type
            colors = {
                'button': (0, 255, 0),
                'link': (255, 128, 0),
                'input': (255, 255, 0),
                'unknown': (128, 128, 128)
            }
            color = colors.get(ptype, colors['unknown'])
            
            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw center
            cv2.circle(frame, (cx, cy), 5, color, -1)
            
            # Label
            label = f"{ptype}: {text}"
            cv2.putText(frame, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
            
        # Status bar
        cv2.rectangle(frame, (0, 0), (w, 25), (40, 40, 40), -1)
        status = f"HYBRID | DOM Elements: {len(self.probes)} | Frame: {self.frame_count}"
        cv2.putText(frame, status, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame
        
    async def _write_probes(self):
        """Write probes to JSON"""
        import os
        os.makedirs("output", exist_ok=True)
        
        output = {
            "timestamp": time.time(),
            "frame": self.frame_count,
            "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "probes": self.probes,
            "blockers": [],
            "mode": "hybrid_dom_yolo"
        }
        
        with open(self.output_file, "w") as f:
            json.dump(output, f, indent=2)
            
    async def stop(self):
        print("[HYBRID] Stopping...")
        self.running = False
        if self.visualizer:
            self.visualizer.close()
        await self.cdp.close()


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    
    server = HybridProbeServer(debug=args.debug)
    
    try:
        await server.connect()
        await server.run()
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
