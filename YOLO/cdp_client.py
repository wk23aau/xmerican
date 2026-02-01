"""
CDP WebSocket Client for browser control
Handles connection, screencast, and input dispatch
"""

import asyncio
import json
import base64
import websockets
from typing import Optional, Callable, Dict, Any
from config import CDP_HOST, CDP_PORT, VIEWPORT_WIDTH, VIEWPORT_HEIGHT


class CDPClient:
    def __init__(self, host: str = CDP_HOST, port: int = CDP_PORT):
        self.host = host
        self.port = port
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.message_id = 0
        self.pending_responses: Dict[int, asyncio.Future] = {}
        self.frame_callback: Optional[Callable] = None
        self._listen_task: Optional[asyncio.Task] = None
        
    async def connect(self, target_url: Optional[str] = None, set_viewport: bool = True):
        """Connect to Chrome DevTools Protocol
        
        Args:
            target_url: Optional URL to filter target pages
            set_viewport: If True, set viewport to config dimensions. Set to False
                         if another process is managing viewport (prevents flickering)
        """
        # Get available targets
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{self.host}:{self.port}/json") as resp:
                targets = await resp.json()
        
        # Find page target
        page_target = None
        for target in targets:
            if target.get("type") == "page":
                if target_url is None or target_url in target.get("url", ""):
                    page_target = target
                    break
        
        if not page_target:
            raise Exception("No suitable page target found")
        
        ws_url = page_target["webSocketDebuggerUrl"]
        self.ws = await websockets.connect(ws_url)
        self._listen_task = asyncio.create_task(self._listen())
        print(f"Connected to {page_target['url']}")
        
        # Set exact viewport size to match config (only if requested)
        if set_viewport:
            await self.send("Emulation.setDeviceMetricsOverride", {
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
                "deviceScaleFactor": 1,
                "mobile": False
            })
            print(f"Viewport set to {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}")
        
    async def _listen(self):
        """Listen for CDP messages"""
        try:
            async for message in self.ws:
                data = json.loads(message)
                
                # Handle response to our commands
                if "id" in data:
                    msg_id = data["id"]
                    if msg_id in self.pending_responses:
                        self.pending_responses[msg_id].set_result(data)
                
                # Handle events
                if "method" in data:
                    await self._handle_event(data)
                    
        except websockets.exceptions.ConnectionClosed:
            print("CDP connection closed")
            
    async def _handle_event(self, event: Dict[str, Any]):
        """Handle CDP events"""
        method = event["method"]
        params = event.get("params", {})
        
        if method == "Page.screencastFrame":
            # Decode frame and pass to callback
            if self.frame_callback:
                frame_data = base64.b64decode(params["data"])
                await self.frame_callback(frame_data, params["metadata"])
            
            # Acknowledge frame (fire and forget)
            await self.send_no_wait("Page.screencastFrameAck", {
                "sessionId": params["sessionId"]
            })
            
    async def send(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send CDP command and wait for response"""
        self.message_id += 1
        msg_id = self.message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        future = asyncio.get_event_loop().create_future()
        self.pending_responses[msg_id] = future
        
        await self.ws.send(json.dumps(message))
        
        try:
            result = await asyncio.wait_for(future, timeout=10.0)
            return result
        finally:
            del self.pending_responses[msg_id]
            
    async def send_no_wait(self, method: str, params: Dict[str, Any] = None):
        """Send CDP command without waiting for response (for input events)"""
        self.message_id += 1
        msg_id = self.message_id
        
        message = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        await self.ws.send(json.dumps(message))
            
    async def start_screencast(self, callback: Callable, quality: int = 100):
        """Start receiving screen frames"""
        self.frame_callback = callback
        await self.send("Page.startScreencast", {
            "format": "png",  # PNG for best quality
            "quality": quality,
            "maxWidth": VIEWPORT_WIDTH,
            "maxHeight": VIEWPORT_HEIGHT
        })
        
    async def stop_screencast(self):
        """Stop receiving screen frames"""
        await self.send("Page.stopScreencast")
        
    async def screenshot(self) -> str:
        """Capture screenshot as base64"""
        result = await self.send("Page.captureScreenshot", {"format": "png"})
        return result.get("result", {}).get("data", "")
        self.frame_callback = None
        
    async def mouse_move(self, x: float, y: float):
        """Move mouse to position (normalized 0-1 coords)"""
        await self.send_no_wait("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": int(x * VIEWPORT_WIDTH),
            "y": int(y * VIEWPORT_HEIGHT)
        })
        
    async def mouse_click(self, x: int, y: int, button: str = "left", show_marker: bool = True):
        """Click at position (pixel coordinates)
        
        Args:
            x: X pixel coordinate
            y: Y pixel coordinate
            button: Mouse button (left/right/middle)
            show_marker: If True, draw a visual marker at click location
        """
        # Draw visual click marker on the page
        if show_marker:
            await self.send("Runtime.evaluate", {
                "expression": f"""
                (function() {{
                    // Remove old marker
                    var old = document.getElementById('__click_marker__');
                    if (old) old.remove();
                    
                    // Create marker
                    var marker = document.createElement('div');
                    marker.id = '__click_marker__';
                    marker.style.cssText = `
                        position: fixed;
                        left: {x - 15}px;
                        top: {y - 15}px;
                        width: 30px;
                        height: 30px;
                        border: 3px solid red;
                        border-radius: 50%;
                        pointer-events: none;
                        z-index: 999999;
                        box-shadow: 0 0 10px red;
                    `;
                    document.body.appendChild(marker);
                    
                    // Animate and remove
                    setTimeout(function() {{
                        marker.style.transform = 'scale(2)';
                        marker.style.opacity = '0';
                        marker.style.transition = 'all 0.3s';
                    }}, 100);
                    setTimeout(function() {{ marker.remove(); }}, 500);
                }})();
                """
            })
        
        # Mouse down
        await self.send_no_wait("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })
        
        await asyncio.sleep(0.05)
        
        # Mouse up
        await self.send_no_wait("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })
        
    async def scroll(self, x: float, y: float, delta_y: int):
        """Scroll at position (normalized 0-1 coords)"""
        await self.send_no_wait("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": int(x * VIEWPORT_WIDTH),
            "y": int(y * VIEWPORT_HEIGHT),
            "deltaX": 0,
            "deltaY": delta_y
        })
        
    async def type_text(self, text: str):
        """Type text using insertText (most reliable)"""
        # Use insertText for bulk text entry
        await self.send("Input.insertText", {"text": text})
            
    async def press_key(self, key: str):
        """Press a special key (Enter, Tab, Escape, etc.)"""
        key_codes = {
            "Enter": 13,
            "Tab": 9,
            "Escape": 27,
            "Backspace": 8,
            "ArrowDown": 40,
            "ArrowUp": 38,
        }
        
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key,
            "windowsVirtualKeyCode": key_codes.get(key, 0)
        })
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key,
            "windowsVirtualKeyCode": key_codes.get(key, 0)
        })
        
    async def navigate(self, url: str):
        """Navigate to URL"""
        await self.send("Page.navigate", {"url": url})
        
    async def get_url(self) -> str:
        """Get current page URL"""
        result = await self.send("Runtime.evaluate", {
            "expression": "window.location.href"
        })
        return result.get("result", {}).get("result", {}).get("value", "")
    
    async def get_element_at(self, x: int, y: int) -> dict:
        """Get element info at coordinates using DOM"""
        js = f"""
            (function() {{
                var el = document.elementFromPoint({x}, {y});
                if (!el) return null;
                var rect = el.getBoundingClientRect();
                return {{
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || el.value || el.placeholder || el.alt || el.title || '').trim().substring(0, 50),
                    role: el.getAttribute('role') || '',
                    type: el.getAttribute('type') || '',
                    href: el.getAttribute('href') || '',
                    bbox: [rect.left, rect.top, rect.right, rect.bottom]
                }};
            }})()
        """
        result = await self.send("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return result.get("result", {}).get("result", {}).get("value", {})
    
    async def get_all_clickables(self) -> list:
        """Get all clickable elements with text from DOM"""
        js = """
            (function() {
                var results = [];
                var selectors = 'button, a, input, [role="button"], [onclick], [class*="btn"]';
                var elements = document.querySelectorAll(selectors);
                elements.forEach(function(el) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        var text = (el.innerText || el.value || el.placeholder || el.alt || el.title || el.getAttribute('aria-label') || '').trim().substring(0, 50);
                        if (text || el.tagName === 'INPUT') {
                            results.push({
                                tag: el.tagName.toLowerCase(),
                                text: text,
                                cx: Math.round(rect.left + rect.width/2),
                                cy: Math.round(rect.top + rect.height/2),
                                bbox: [rect.left, rect.top, rect.right, rect.bottom]
                            });
                        }
                    }
                });
                return results;
            })()
        """
        result = await self.send("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return result.get("result", {}).get("result", {}).get("value", [])
        
    async def close(self):
        """Close CDP connection"""
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()

