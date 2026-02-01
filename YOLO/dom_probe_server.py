"""
DOM-First Probe Server - Uses DOM for detection, YOLO for visual confirmation
More accurate than vision-only detection for web automation
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Callable
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT, TARGET_FPS


class DOMProbeServer:
    """
    DOM-first detection approach:
    - Query DOM for all interactive elements (buttons, links, inputs)
    - DOM provides: tag, text, coordinates, role - 100% accurate
    - No OCR needed, no YOLO uncertainty
    """
    
    def __init__(self, output_file: str = "output/yolo_probes.json", debug: bool = False):
        self.cdp = CDPClient()
        self.output_file = output_file
        self.debug = debug
        self.running = False
        self.frame_count = 0
        self.probes = []
        
    async def connect(self):
        """Connect to browser"""
        print("[DOM] Connecting to browser...")
        await self.cdp.connect()
        print("[DOM] Connected - ready for DOM queries")
        
    async def _get_dom_probes(self) -> List[Dict]:
        """
        Get all interactive elements from DOM with coordinates
        This is the primary detection method - 100% accurate
        """
        js = """
        (function() {
            var results = [];
            var id = 0;
            
            // Interactive element selectors
            var selectors = [
                'button', 'a', 'input', 'select', 'textarea',
                '[role="button"]', '[role="link"]', '[role="menuitem"]',
                '[role="tab"]', '[role="checkbox"]', '[role="radio"]',
                '[onclick]', '[class*="btn"]', '[class*="button"]'
            ].join(', ');
            
            var elements = document.querySelectorAll(selectors);
            
            elements.forEach(function(el) {
                var rect = el.getBoundingClientRect();
                
                // Skip invisible elements
                if (rect.width <= 0 || rect.height <= 0) return;
                if (rect.bottom < 0 || rect.top > window.innerHeight) return;
                if (rect.right < 0 || rect.left > window.innerWidth) return;
                
                // Get element info
                var tag = el.tagName.toLowerCase();
                var text = (el.innerText || el.value || el.placeholder || 
                           el.alt || el.title || el.getAttribute('aria-label') || '').trim();
                text = text.substring(0, 50).replace(/\\n/g, ' ');
                
                var role = el.getAttribute('role') || '';
                var type = el.getAttribute('type') || '';
                var href = el.getAttribute('href') || '';
                
                // Determine probe type
                var probeType = 'unknown';
                if (tag === 'button' || role === 'button') probeType = 'button';
                else if (tag === 'a' || role === 'link') probeType = 'link';
                else if (tag === 'input') {
                    if (type === 'submit' || type === 'button') probeType = 'button';
                    else if (type === 'checkbox') probeType = 'checkbox';
                    else if (type === 'radio') probeType = 'radio';
                    else probeType = 'input';
                }
                else if (tag === 'select') probeType = 'dropdown';
                else if (tag === 'textarea') probeType = 'input';
                else if (role === 'menuitem') probeType = 'menu';
                else if (role === 'tab') probeType = 'button';
                
                // Calculate normalized coordinates
                var cx = (rect.left + rect.width / 2) / window.innerWidth;
                var cy = (rect.top + rect.height / 2) / window.innerHeight;
                
                results.push({
                    id: id++,
                    type: probeType,
                    tag: tag,
                    text: text,
                    role: role,
                    href: href ? true : false,
                    cx: cx,
                    cy: cy,
                    bbox: [
                        rect.left / window.innerWidth,
                        rect.top / window.innerHeight,
                        rect.right / window.innerWidth,
                        rect.bottom / window.innerHeight
                    ],
                    pixelCenter: [
                        Math.round(rect.left + rect.width / 2),
                        Math.round(rect.top + rect.height / 2)
                    ],
                    score: 1.0  // DOM detection is 100% confident
                });
            });
            
            return results;
        })()
        """
        
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        
        probes = result.get("result", {}).get("result", {}).get("value", [])
        return probes or []
        
    async def run(self):
        """Run DOM-based perception loop"""
        print(f"[DOM] Starting DOM detection at {TARGET_FPS} Hz")
        print(f"[DOM] Probes written to: {self.output_file}")
        
        self.running = True
        target_interval = 1.0 / TARGET_FPS
        
        while self.running:
            loop_start = time.time()
            
            try:
                # Get probes from DOM (primary detection)
                self.probes = await self._get_dom_probes()
                
                # Write to output file
                await self._write_probes()
                
                self.frame_count += 1
                
                # Log every second
                if self.frame_count % TARGET_FPS == 0:
                    print(f"[DOM] Frame {self.frame_count} | Probes: {len(self.probes)}")
                    
            except Exception as e:
                print(f"[DOM] Error: {e}")
                
            # Maintain FPS
            elapsed = time.time() - loop_start
            await asyncio.sleep(max(0, target_interval - elapsed))
            
    async def _write_probes(self):
        """Write probes to JSON file"""
        import os
        os.makedirs("output", exist_ok=True)
        
        output = {
            "timestamp": time.time(),
            "frame": self.frame_count,
            "viewport": [VIEWPORT_WIDTH, VIEWPORT_HEIGHT],
            "probes": self.probes,
            "blockers": [],
            "events": [],
            "mode": "dom_first"
        }
        
        with open(self.output_file, "w") as f:
            json.dump(output, f, indent=2)
            
    async def stop(self):
        """Stop server"""
        print("[DOM] Stopping...")
        self.running = False
        await self.cdp.close()


async def main():
    """Run DOM probe server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DOM-First Probe Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()
    
    server = DOMProbeServer(debug=args.debug)
    
    try:
        await server.connect()
        await server.run()
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
