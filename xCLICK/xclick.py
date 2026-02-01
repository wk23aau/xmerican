"""
xCLICK - DOM-based browser automation with visual feedback
Single process for perception + actions - no viewport flickering

Usage:
    python xclick.py --debug    # With visual debug window
    python xclick.py            # Without debug
    
Commands:
    click <text>     - Click element by text
    click <x> <y>    - Click at coordinates
    type <text>      - Type text
    press <key>      - Press key (Enter, Tab, etc)
    goto <url>       - Navigate to URL
    probes / p       - Show detected elements
    wait <seconds>   - Wait
    exit / q         - Quit
"""

import asyncio
import argparse
from typing import Dict, List, Optional
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT


class xClick:
    """DOM-based browser automation with visual click feedback"""
    
    def __init__(self, debug: bool = False):
        self.cdp = CDPClient()
        self.probes: List[Dict] = []
        self.debug = debug
        
    async def connect(self):
        """Connect to browser"""
        print("Connecting to browser...")
        await self.cdp.connect(set_viewport=True)
        print("Connected!")
        
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
        
    def show_probes(self):
        """Display detected elements"""
        print(f"\n─── {len(self.probes)} elements ───")
        for p in self.probes:
            text = p.get("text", "")
            ptype = p.get("type", "?")
            cx, cy = p.get("cx", 0), p.get("cy", 0)
            if text:
                print(f"  [{p['id']:2}] {ptype:8} '{text[:30]}' ({cx},{cy})")
            else:
                print(f"  [{p['id']:2}] {ptype:8} ({cx},{cy})")
        print("───────────────\n")
        
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
        print("""
╔═══════════════════════════════════════╗
║  xCLICK - DOM Browser Automation      ║
╠═══════════════════════════════════════╣
║ Commands:                             ║
║   click <text>   - Click by text      ║
║   click <x> <y>  - Click coordinates  ║
║   type <text>    - Type text          ║
║   press <key>    - Press key          ║
║   goto <url>     - Navigate           ║
║   probes / p     - Show elements      ║
║   scroll [amt]   - Scroll down        ║
║   scrollup [amt] - Scroll up          ║
║   tabs           - List all tabs      ║
║   tab <n>        - Switch to tab n    ║
║   newtab [url]   - Open new tab       ║
║   closetab       - Close current tab  ║
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
    parser = argparse.ArgumentParser(description="xCLICK - DOM Browser Automation")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()
    
    xclick = xClick(debug=args.debug)
    await xclick.connect()
    
    await xclick.refresh_probes()
    xclick.show_probes()
    
    try:
        await xclick.run_repl()
    finally:
        await xclick.close()


if __name__ == "__main__":
    asyncio.run(main())
