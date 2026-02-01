"""
Interactive YOLO Executor - Real-time probes with CDP actions
Zero-latency browser automation
"""

import asyncio
import json
import time
import threading
import sys
from typing import Optional, Dict, List
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT


class RealtimeExecutor:
    """
    Interactive REPL with real-time YOLO probe updates
    """
    
    def __init__(self):
        self.cdp = CDPClient()
        self.probes_file = "output/yolo_probes.json"
        self.probes = []
        self.probe_lock = threading.Lock()
        self.running = True
        
        # Start probe watcher thread
        self.watcher_thread = threading.Thread(target=self._watch_probes, daemon=True)
        self.watcher_thread.start()
        
    def _watch_probes(self):
        """Background thread to watch probe file changes"""
        last_mtime = 0
        while self.running:
            try:
                import os
                mtime = os.path.getmtime(self.probes_file)
                if mtime > last_mtime:
                    with open(self.probes_file, "r") as f:
                        data = json.load(f)
                        with self.probe_lock:
                            self.probes = data.get("probes", [])
                    last_mtime = mtime
            except:
                pass
            time.sleep(0.05)  # 20Hz check
            
    def get_probes(self) -> List[Dict]:
        """Get current probes (thread-safe)"""
        with self.probe_lock:
            return list(self.probes)
            
    def find_probe(self, query: str) -> Optional[Dict]:
        """Find probe by text content (case insensitive)"""
        probes = self.get_probes()
        query_lower = query.lower()
        
        # First try exact text match
        for probe in probes:
            text = probe.get("text", "").lower()
            if query_lower in text:
                return probe
                
        # Then try partial match
        for probe in probes:
            text = probe.get("text", "").lower()
            if any(word in text for word in query_lower.split()):
                return probe
                
        return None
        
    def probe_to_pixels(self, probe: Dict) -> tuple:
        """Convert probe coords to pixels - handles both normalized and pixel coords"""
        cx = probe.get("cx", 0.5)
        cy = probe.get("cy", 0.5)
        
        # Check if coords are already in pixels (> 1) or normalized (0-1)
        if cx > 1 or cy > 1:
            # Already pixel coordinates
            x, y = int(cx), int(cy)
        else:
            # Normalized coordinates - multiply by viewport
            x = int(cx * VIEWPORT_WIDTH)
            y = int(cy * VIEWPORT_HEIGHT)
        return x, y
        
    async def click(self, x: int, y: int):
        """Click at coordinates"""
        await self.cdp.mouse_click(x, y)
        print(f"✓ click ({x}, {y})")
        
    async def click_probe(self, probe: Dict):
        """Click on a probe"""
        x, y = self.probe_to_pixels(probe)
        text = probe.get("text", probe.get("type", ""))
        await self.cdp.mouse_click(x, y)
        print(f"✓ click '{text}' ({x}, {y})")
        
    async def find_dom_element(self, query: str) -> Optional[dict]:
        """Find clickable element by text using DOM (most accurate)"""
        query_lower = query.lower()
        clickables = await self.cdp.get_all_clickables()
        
        # Exact match first
        for elem in clickables:
            text = elem.get("text", "").lower()
            if query_lower == text or query_lower in text:
                return elem
        
        # Partial word match
        for elem in clickables:
            text = elem.get("text", "").lower()
            if any(word in text for word in query_lower.split()):
                return elem
        
        return None
        
    async def click_text(self, query: str) -> bool:
        """Find and click element by text (tries DOM first, then YOLO)"""
        # Try DOM-based detection first (most accurate)
        elem = await self.find_dom_element(query)
        if elem:
            x, y = elem.get("cx", 0), elem.get("cy", 0)
            text = elem.get("text", "")[:30]
            await self.cdp.mouse_click(x, y)
            print(f"✓ click '{text}' ({x}, {y}) [DOM]")
            return True
        
        # Fall back to YOLO probes
        probe = self.find_probe(query)
        if probe:
            await self.click_probe(probe)
            return True
        
        print(f"✗ not found: '{query}'")
        self.show_probes()  # Show available probes
        return False
        
    async def type_text(self, text: str):
        """Type text"""
        await self.cdp.type_text(text)
        print(f"✓ type '{text}'")
        
    async def press(self, key: str):
        """Press a key"""
        await self.cdp.press_key(key)
        print(f"✓ press {key}")
        
    async def goto(self, url: str):
        """Navigate to URL"""
        if not url.startswith("http"):
            url = "https://" + url
        await self.cdp.navigate(url)
        print(f"✓ goto {url}")
        
    async def wait(self, seconds: float = 1):
        """Wait"""
        await asyncio.sleep(seconds)
        print(f"✓ wait {seconds}s")
        
    def show_probes(self):
        """Show current probes with text context"""
        probes = self.get_probes()
        print(f"\n─── {len(probes)} probes ───")
        for p in probes:
            x, y = self.probe_to_pixels(p)
            text = p.get("text", "")
            ptype = p.get("type", "?")
            if text:
                print(f"  [{p['id']:2}] {ptype:8} '{text[:25]}' ({x},{y})")
            else:
                print(f"  [{p['id']:2}] {ptype:8} ({x},{y})")
        print("───────────────\n")
        
    async def run_repl(self):
        """Interactive REPL"""
        print("\n╔═══════════════════════════════════════╗")
        print("║  YOLO Executor REPL                   ║")
        print("╠═══════════════════════════════════════╣")
        print("║ Commands:                             ║")
        print("║   goto <url>     - Navigate           ║")
        print("║   click <text>   - Click by text      ║")
        print("║   click <x> <y>  - Click coordinates  ║")
        print("║   type <text>    - Type text          ║")
        print("║   press <key>    - Press key          ║")
        print("║   probes / p     - Show probes        ║")
        print("║   wait <sec>     - Wait               ║")
        print("║   exit / q       - Quit               ║")
        print("╚═══════════════════════════════════════╝\n")
        
        while self.running:
            try:
                cmd = input(">>> ").strip()
                if not cmd:
                    continue
                    
                parts = cmd.split(maxsplit=1)
                action = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                
                if action in ("exit", "q", "quit"):
                    break
                elif action in ("probes", "p", "ls"):
                    self.show_probes()
                elif action == "goto":
                    await self.goto(arg)
                    await asyncio.sleep(2)
                    self.show_probes()
                elif action == "click":
                    # Check if coordinates or text
                    if " " in arg and arg.replace(" ", "").replace(",", "").isdigit():
                        coords = arg.replace(",", " ").split()
                        await self.click(int(coords[0]), int(coords[1]))
                    else:
                        await self.click_text(arg)
                elif action == "type":
                    await self.type_text(arg)
                elif action == "press":
                    await self.press(arg)
                elif action == "wait":
                    await self.wait(float(arg) if arg else 1)
                elif action == "w":  # Quick wait
                    await self.wait(1)
                    self.show_probes()
                else:
                    # Try as click text
                    await self.click_text(cmd)
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"✗ error: {e}")
                
        self.running = False
        

async def main():
    """Main entry"""
    print("Connecting to browser...")
    
    executor = RealtimeExecutor()
    # Don't set viewport - let probe server handle it (prevents flickering)
    await executor.cdp.connect(set_viewport=False)
    print(f"Connected to {executor.cdp.ws.remote_address if hasattr(executor.cdp, 'ws') else 'browser'}")
    
    # Show initial probes
    await asyncio.sleep(0.5)
    executor.show_probes()
    
    try:
        await executor.run_repl()
    finally:
        await executor.cdp.close()
        print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
