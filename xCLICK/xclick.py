"""
xCLICK - DOM-based browser automation with visual feedback
Single process for perception + actions - no viewport flickering

Now with YOLO vision integration for labeled probe detection!

Usage:
    python xclick.py --debug    # With visual debug window
    python xclick.py            # Without debug
    python xclick.py --vision   # Enable YOLO vision mode
    
Commands:
    click <text>     - Click element by text (DOM)
    click <x> <y>    - Click at coordinates
    vclick <label>   - Click element by vision label (YOLO+DOM)
    vprobes / vp     - Show YOLO-detected elements with labels
    vscan            - Capture and save annotated debug image
    type <text>      - Type text
    press <key>      - Press key (Enter, Tab, etc)
    goto <url>       - Navigate to URL
    probes / p       - Show DOM-detected elements
    wait <seconds>   - Wait
    exit / q         - Quit
"""

import asyncio
import argparse
import os
from typing import Dict, List, Optional
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT, YOLO_MODEL_PATH, USE_OCR_FALLBACK, VISION_MODEL_TYPE


class xClick:
    """DOM-based browser automation with visual click feedback + YOLO vision"""
    
    def __init__(self, debug: bool = False, vision: bool = False):
        self.cdp = CDPClient()
        self.probes: List[Dict] = []
        self.vision_probes: List = []  # LabeledProbe objects from vision
        self.debug = debug
        self.vision_enabled = vision
        self.vision_module = None
        
    async def connect(self):
        """Connect to browser"""
        print("Connecting to browser...")
        await self.cdp.connect(set_viewport=True)
        print("Connected!")
        
        # Initialize vision module if enabled
        if self.vision_enabled:
            await self.init_vision()
            
    async def init_vision(self):
        """Initialize YOLO vision module"""
        try:
            from vision_module import VisionModule
            self.vision_module = VisionModule(
                self.cdp,
                model_path=YOLO_MODEL_PATH,
                use_ocr=USE_OCR_FALLBACK,
                model_type=VISION_MODEL_TYPE
            )
            await self.vision_module.init_model()
            self.vision_enabled = True
            print("✓ Vision module initialized")
        except ImportError as e:
            print(f"✗ Vision module not available: {e}")
            self.vision_enabled = False
        except Exception as e:
            print(f"✗ Vision init failed: {e}")
            self.vision_enabled = False
        
    async def refresh_probes(self) -> List[Dict]:
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
            
            document.querySelectorAll(selectors).forEach(function(el) {
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
        
    async def show_probes(self, show_tabs=True):
        """Display detected elements with tab awareness"""
        # Get tab info for world state
        tab_info = ""
        if show_tabs:
            tabs = await self.get_tabs()
            current_tab = 0  # We're always on the first in list after switch
            for i, t in enumerate(tabs):
                if t.get("attached"):
                    current_tab = i
                    break
            tab_info = f" [Tab {current_tab+1}/{len(tabs)}]"
        
        print(f"\n─── {len(self.probes)} elements{tab_info} ───")
        for p in self.probes:
            text = p.get("text", "")
            ptype = p.get("type", "?")
            cx, cy = p.get("cx", 0), p.get("cy", 0)
            if text:
                print(f"  [{p['id']:2}] {ptype:8} '{text[:30]}' ({cx},{cy})")
            else:
                print(f"  [{p['id']:2}] {ptype:8} ({cx},{cy})")
        print("───────────────\n")
        
    # ================== VISION METHODS ==================
    
    async def refresh_vision_probes(self):
        """Detect elements using YOLO + DOM fusion"""
        if not self.vision_enabled or not self.vision_module:
            print("✗ Vision not enabled. Run with --vision flag")
            return []
            
        self.vision_probes = await self.vision_module.detect_labeled_probes()
        return self.vision_probes
        
    async def show_vision_probes(self, show_tabs=True):
        """Display YOLO-detected elements with labels and tab info"""
        # Get tab info for world state
        tab_info = ""
        if show_tabs:
            tabs = await self.get_tabs()
            tab_info = f" [Tab 1/{len(tabs)}]"
        
        print(f"\n─── VISION: {len(self.vision_probes)} elements{tab_info} ───")
        for p in self.vision_probes:
            label_str = f"'{p.label[:30]}'" if p.label else ""
            print(f"  [{p.id:2}] {p.type:8} {label_str:32} ({p.cx:.0f},{p.cy:.0f}) [{p.confidence:.2f}]")
        print("─────────────────────────────\n")
        
    async def vclick_text(self, query: str) -> bool:
        """Find and click element by vision label"""
        if not self.vision_enabled or not self.vision_module:
            print("✗ Vision not enabled. Run with --vision flag")
            return False
            
        # Refresh if no probes
        if not self.vision_probes:
            await self.refresh_vision_probes()
            
        # Find by label
        probe = self.vision_module.find_probe_by_label(self.vision_probes, query)
        
        if not probe:
            # Retry with fresh detection
            await self.refresh_vision_probes()
            probe = self.vision_module.find_probe_by_label(self.vision_probes, query)
            
        if probe:
            cx, cy = int(probe.cx), int(probe.cy)
            await self.cdp.mouse_click(cx, cy)
            label_str = f"'{probe.label}'" if probe.label else f"({probe.type})"
            print(f"✓ vclick {label_str} ({cx}, {cy})")
            return True
            
        print(f"✗ not found: '{query}'")
        return False
        
    async def save_vision_scan(self, path: str = None):
        """Capture annotated screenshot for debugging"""
        if not self.vision_enabled or not self.vision_module:
            print("✗ Vision not enabled. Run with --vision flag")
            return
            
        # Detect probes
        probes = await self.vision_module.detect_labeled_probes()
        self.vision_probes = probes
        
        # Get annotated frame
        png_data = await self.vision_module.get_annotated_frame(probes)
        
        if png_data:
            path = path or "vision_scan.png"
            with open(path, "wb") as f:
                f.write(png_data)
            print(f"✓ Saved annotated scan to {path}")
            print(f"  Detected {len(probes)} elements")
        else:
            print("✗ Failed to capture annotated frame")
            
    # ================== END VISION METHODS ==================
        
    def find_probe(self, query: str) -> Optional[Dict]:
        """Find element by text"""
        query_lower = query.lower()
        for p in self.probes:
            if query_lower in p.get("text", "").lower():
                return p
        return None
        
    async def click(self, x: int, y: int):
        """Click at pixel coordinates"""
        await self.cdp.mouse_click(x, y)
        print(f"✓ click ({x}, {y})")
        
    async def click_text(self, query: str) -> bool:
        """Find and click element by text"""
        probe = self.find_probe(query)
        if not probe:
            await self.refresh_probes()
            probe = self.find_probe(query)
            
        if probe:
            cx, cy = probe.get("cx", 0), probe.get("cy", 0)
            await self.cdp.mouse_click(cx, cy)
            print(f"✓ click '{probe.get('text', '')[:30]}' ({cx}, {cy})")
            return True
            
        print(f"✗ not found: '{query}'")
        return False
        
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
        
    async def wait(self, seconds: float = 1.0):
        """Wait"""
        await asyncio.sleep(seconds)
        print(f"✓ wait {seconds}s")
        
    async def scroll(self, amount: int = 500):
        """Scroll down the page"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": f"window.scrollBy(0, {amount})"
        })
        await asyncio.sleep(0.3)
        print(f"✓ scroll {amount}px")
        
    async def scroll_up(self, amount: int = 500):
        """Scroll up the page"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": f"window.scrollBy(0, -{amount})"
        })
        await asyncio.sleep(0.3)
        print(f"✓ scroll up {amount}px")
        
    async def get_tabs(self) -> list:
        """Get all open browser tabs"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{self.cdp.host}:{self.cdp.port}/json") as resp:
                targets = await resp.json()
        tabs = [t for t in targets if t.get("type") == "page"]
        return tabs
        
    async def show_tabs(self):
        """Display all open tabs"""
        tabs = await self.get_tabs()
        print(f"\n─── {len(tabs)} tabs ───")
        for i, tab in enumerate(tabs):
            title = tab.get("title", "Untitled")[:40]
            url = tab.get("url", "")[:50]
            print(f"  [{i}] {title}")
            print(f"      {url}")
        print("───────────────\n")
        return tabs
        
    async def switch_tab(self, index: int):
        """Switch to a different tab by index"""
        tabs = await self.get_tabs()
        if 0 <= index < len(tabs):
            target = tabs[index]
            # Close current connection and connect to new tab
            await self.cdp.close()
            self.cdp = CDPClient()
            
            # Connect to specific target
            ws_url = target["webSocketDebuggerUrl"]
            import websockets
            self.cdp.ws = await websockets.connect(ws_url)
            self.cdp._listen_task = asyncio.create_task(self.cdp._listen())
            
            print(f"✓ switched to tab {index}: {target.get('title', '')[:30]}")
            await self.refresh_probes()
        else:
            print(f"✗ invalid tab index: {index}")
            
    async def new_tab(self, url: str = "about:blank"):
        """Open a new tab"""
        await self.cdp.send("Target.createTarget", {"url": url})
        await asyncio.sleep(1)
        # Switch to the new tab
        tabs = await self.get_tabs()
        if tabs:
            await self.switch_tab(len(tabs) - 1)
        print(f"✓ new tab: {url}")
        
    async def close_tab(self):
        """Close current tab"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": "window.close()"
        })
        await asyncio.sleep(0.5)
        # Switch to remaining tab
        tabs = await self.get_tabs()
        if tabs:
            await self.switch_tab(0)
        print("✓ closed tab")
        
    async def run_repl(self):
        """Interactive REPL"""
        vision_str = " + YOLO Vision" if self.vision_enabled else ""
        print(f"""
╔═══════════════════════════════════════════╗
║  xCLICK - DOM Browser Automation{vision_str:11} ║
╠═══════════════════════════════════════════╣
║ DOM Commands:                             ║
║   click <text>   - Click by text (DOM)    ║
║   click <x> <y>  - Click coordinates      ║
║   probes / p     - Show DOM elements      ║
║                                           ║
║ Vision Commands: {'(enabled)' if self.vision_enabled else '(--vision)':14}          ║
║   vprobes / vp   - Show YOLO elements     ║
║   vclick <label> - Click by vision label  ║
║   vscan          - Save debug screenshot  ║
║   vision         - Enable vision mode     ║
║                                           ║
║ Other:                                    ║
║   type <text>    - Type text              ║
║   press <key>    - Press key              ║
║   goto <url>     - Navigate               ║
║   scroll [amt]   - Scroll down            ║
║   tabs / tab <n> - Tab management         ║
║   exit / q       - Quit                   ║
╚═══════════════════════════════════════════╝
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
                    await self.show_probes()
                elif action == "goto":
                    await self.goto(args)
                elif action == "click":
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
                    secs = float(args) if args else 1.0
                    await self.wait(secs)
                elif action == "scroll":
                    amt = int(args) if args else 500
                    await self.scroll(amt)
                elif action == "scrollup":
                    amt = int(args) if args else 500
                    await self.scroll_up(amt)
                elif action == "tabs":
                    await self.show_tabs()
                elif action == "tab":
                    idx = int(args) if args else 0
                    await self.switch_tab(idx)
                elif action == "newtab":
                    url = args if args else "about:blank"
                    await self.new_tab(url)
                elif action == "closetab":
                    await self.close_tab()
                # ===== VISION COMMANDS =====
                elif action in ("vprobes", "vp"):
                    await self.refresh_vision_probes()
                    await self.show_vision_probes()
                elif action == "vclick":
                    await self.vclick_text(args)
                elif action == "vscan":
                    path = args if args else None
                    await self.save_vision_scan(path)
                elif action == "vision":
                    if not self.vision_enabled:
                        await self.init_vision()
                    else:
                        print("✓ Vision already enabled")
                # ===== END VISION COMMANDS =====
                else:
                    print(f"Unknown: {action}")
                    
            except EOFError:
                break
            except Exception as e:
                print(f"✗ error: {e}")
                
    async def close(self):
        """Close connection"""
        await self.cdp.close()
        print("Disconnected.")


async def main():
    parser = argparse.ArgumentParser(description="xCLICK - DOM Browser Automation + YOLO Vision")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--vision", action="store_true", help="Enable YOLO vision mode")
    args = parser.parse_args()
    
    xclick = xClick(debug=args.debug, vision=args.vision)
    await xclick.connect()
    
    await xclick.refresh_probes()
    await xclick.show_probes()
    
    # Also show vision probes if enabled
    if xclick.vision_enabled:
        await xclick.refresh_vision_probes()
        await xclick.show_vision_probes()
    
    try:
        await xclick.run_repl()
    finally:
        await xclick.close()


if __name__ == "__main__":
    asyncio.run(main())
