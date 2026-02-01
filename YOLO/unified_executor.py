"""
Unified DOM Executor - Single process for perception + actions
No separate probe server needed - prevents viewport flickering
"""

import asyncio
import json
import base64
import argparse
from typing import Dict, List, Optional
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class UnifiedExecutor:
    """Single process executor with built-in DOM detection"""
    
    def __init__(self, debug: bool = False):
        self.cdp = CDPClient()
        self.probes: List[Dict] = []
        self.debug = debug and CV2_AVAILABLE
        self.last_click = None  # (x, y) of last click for visualization
        
    async def connect(self):
        """Connect to browser"""
        print("Connecting to browser...")
        await self.cdp.connect(set_viewport=True)  # Only one process sets viewport
        print("Connected!")
        
    async def refresh_probes(self):
        """Query DOM for all interactive elements"""
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
                
                if (rect.width <= 0 || rect.height <= 0) return;
                if (rect.bottom < 0 || rect.top > window.innerHeight) return;
                if (rect.right < 0 || rect.left > window.innerWidth) return;
                
                var tag = el.tagName.toLowerCase();
                var text = (el.innerText || el.value || el.placeholder || 
                           el.alt || el.title || el.getAttribute('aria-label') || '').trim();
                text = text.substring(0, 50).replace(/\\n/g, ' ');
                
                var role = el.getAttribute('role') || '';
                var type = el.getAttribute('type') || '';
                
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
                    cx: Math.round(rect.left + rect.width / 2),
                    cy: Math.round(rect.top + rect.height / 2),
                    bbox: [rect.left, rect.top, rect.right, rect.bottom]
                });
            });
            
            return results;
        })()
        """
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        self.probes = result.get("result", {}).get("result", {}).get("value", []) or []
        return self.probes
        
    def show_probes(self):
        """Display current probes"""
        print(f"\n─── {len(self.probes)} probes ───")
        for p in self.probes:
            text = p.get("text", "")
            ptype = p.get("type", "?")
            cx, cy = p.get("cx", 0), p.get("cy", 0)
            if text:
                print(f"  [{p['id']:2}] {ptype:8} '{text[:25]}' ({cx},{cy})")
            else:
                print(f"  [{p['id']:2}] {ptype:8} ({cx},{cy})")
        print("───────────────\n")
        
    def find_probe(self, query: str) -> Optional[Dict]:
        """Find probe by text"""
        query_lower = query.lower()
        for p in self.probes:
            text = p.get("text", "").lower()
            if query_lower in text:
                return p
        return None
        
    async def click(self, x: int, y: int):
        """Click at pixel coordinates"""
        self.last_click = (x, y)
        await self.cdp.mouse_click(x, y)
        print(f"✓ click ({x}, {y})")
        if self.debug:
            await self.show_debug()
        
    async def click_text(self, query: str):
        """Find and click element by text"""
        # First try from cached probes
        probe = self.find_probe(query)
        if probe:
            cx, cy = probe.get("cx", 0), probe.get("cy", 0)
            self.last_click = (cx, cy)
            await self.cdp.mouse_click(cx, cy)
            print(f"✓ click '{probe.get('text', '')[:25]}' ({cx}, {cy})")
            if self.debug:
                await self.show_debug()
            return True
            
        # Refresh probes and try again
        await self.refresh_probes()
        probe = self.find_probe(query)
        if probe:
            cx, cy = probe.get("cx", 0), probe.get("cy", 0)
            self.last_click = (cx, cy)
            await self.cdp.mouse_click(cx, cy)
            print(f"✓ click '{probe.get('text', '')[:25]}' ({cx}, {cy})")
            if self.debug:
                await self.show_debug()
            return True
            
        print(f"✗ not found: '{query}'")
        return False
        
    async def show_debug(self):
        """Show debug visualization with probes and click marker"""
        if not self.debug:
            return
            
        # Take screenshot
        try:
            data = await self.cdp.screenshot()
            img_bytes = base64.b64decode(data)
            nparr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except:
            return
            
        # Draw probes
        for probe in self.probes:
            cx, cy = probe.get("cx", 0), probe.get("cy", 0)
            bbox = probe.get("bbox", [0, 0, 0, 0])
            text = probe.get("text", "")[:20]
            ptype = probe.get("type", "unknown")
            
            # Color by type
            colors = {
                'button': (0, 255, 0),
                'link': (255, 128, 0),
                'input': (0, 255, 255),
            }
            color = colors.get(ptype, (128, 128, 128))
            
            # Draw bounding box
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw center
            cv2.circle(frame, (cx, cy), 5, color, -1)
            
            # Label
            cv2.putText(frame, f"{ptype}: {text}", (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        
        # Draw last click in RED
        if self.last_click:
            cx, cy = self.last_click
            cv2.circle(frame, (cx, cy), 20, (0, 0, 255), 3)
            cv2.drawMarker(frame, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 30, 3)
            cv2.putText(frame, f"CLICK ({cx}, {cy})", (cx + 25, cy), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        
        # Status bar
        cv2.rectangle(frame, (0, 0), (VIEWPORT_WIDTH, 25), (40, 40, 40), -1)
        status = f"DOM Probes: {len(self.probes)} | Press any key to continue"
        cv2.putText(frame, status, (10, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        cv2.imshow("DOM Debug", frame)
        cv2.waitKey(1)  # Quick update
        
    async def type_text(self, text: str):
        """Type text"""
        await self.cdp.type_text(text)
        print(f"✓ type '{text}'")
        
    async def press(self, key: str):
        """Press a key"""
        await self.cdp.press_key(key)
        print(f"✓ press '{key}'")
        
    async def goto(self, url: str):
        """Navigate to URL"""
        await self.cdp.navigate(url)
        await asyncio.sleep(2)
        await self.refresh_probes()
        print(f"✓ goto '{url}'")
        
    async def wait(self, seconds: float):
        """Wait"""
        await asyncio.sleep(seconds)
        print(f"✓ wait {seconds}s")
        
    async def run_repl(self):
        """Interactive REPL"""
        print("""
╔═══════════════════════════════════════╗
║  Unified DOM Executor REPL            ║
╠═══════════════════════════════════════╣
║ Commands:                             ║
║   goto <url>     - Navigate           ║
║   click <text>   - Click by text      ║
║   click <x> <y>  - Click coordinates  ║
║   type <text>    - Type text          ║
║   press <key>    - Press key          ║
║   probes / p     - Show probes        ║
║   wait <sec>     - Wait               ║
║   exit / q       - Quit               ║
╚═══════════════════════════════════════╝
""")
        
        while True:
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(None, input, ">>> ")
                cmd = cmd.strip()
                
                if not cmd:
                    continue
                    
                parts = cmd.split(maxsplit=1)
                action = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                if action in ("exit", "q"):
                    break
                elif action in ("probes", "p"):
                    await self.refresh_probes()
                    self.show_probes()
                elif action == "goto":
                    await self.goto(args)
                elif action == "click":
                    # Check if coords or text
                    try:
                        coords = args.split()
                        if len(coords) == 2:
                            x, y = int(coords[0]), int(coords[1])
                            await self.click(x, y)
                        else:
                            await self.click_text(args)
                    except ValueError:
                        await self.click_text(args)
                elif action == "type":
                    await self.type_text(args)
                elif action == "press":
                    await self.press(args)
                elif action == "wait":
                    try:
                        secs = float(args) if args else 1.0
                        await self.wait(secs)
                    except ValueError:
                        await self.wait(1.0)
                else:
                    print(f"Unknown command: {action}")
                    
            except EOFError:
                break
            except Exception as e:
                print(f"✗ error: {e}")
                
    async def close(self):
        """Close connection"""
        await self.cdp.close()
        print("Disconnected.")


async def main():
    parser = argparse.ArgumentParser(description="Unified DOM Executor")
    parser.add_argument("--debug", action="store_true", help="Enable debug visualization")
    args = parser.parse_args()
    
    executor = UnifiedExecutor(debug=args.debug)
    await executor.connect()
    
    # Get initial probes
    await executor.refresh_probes()
    executor.show_probes()
    
    # Show initial debug if enabled
    if executor.debug:
        await executor.show_debug()
    
    try:
        await executor.run_repl()
    finally:
        if CV2_AVAILABLE:
            cv2.destroyAllWindows()
        await executor.close()


if __name__ == "__main__":
    asyncio.run(main())
