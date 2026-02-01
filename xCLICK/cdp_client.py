"""
xCLICK CDP Client - Browser automation via Chrome DevTools Protocol
Handles connection, input dispatch, and visual click feedback
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
        self.responses: Dict[int, Any] = {}
        self.frame_callback: Optional[Callable] = None
        self._listen_task: Optional[asyncio.Task] = None
        
    async def connect(self, target_url: Optional[str] = None, set_viewport: bool = True):
        """Connect to Chrome DevTools Protocol"""
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
                if "id" in data:
                    self.responses[data["id"]] = data
                elif "method" in data:
                    await self._handle_event(data)
        except websockets.exceptions.ConnectionClosed:
            pass
            
    async def _handle_event(self, event: Dict[str, Any]):
        """Handle CDP events"""
        method = event.get("method", "")
        params = event.get("params", {})
        
        if method == "Page.screencastFrame":
            if self.frame_callback:
                frame_data = params.get("data", "")
                self.frame_callback(frame_data)
            await self.send_no_wait("Page.screencastFrameAck", {
                "sessionId": params.get("sessionId")
            })
            
    async def send(self, method: str, params: Dict[str, Any] = None) -> Dict:
        """Send CDP command and wait for response"""
        self.message_id += 1
        msg_id = self.message_id
        
        message = {"id": msg_id, "method": method}
        if params:
            message["params"] = params
            
        await self.ws.send(json.dumps(message))
        
        # Wait for response
        for _ in range(100):
            if msg_id in self.responses:
                return self.responses.pop(msg_id)
            await asyncio.sleep(0.01)
        return {}
        
    async def send_no_wait(self, method: str, params: Dict[str, Any] = None):
        """Send CDP command without waiting for response"""
        self.message_id += 1
        message = {"id": self.message_id, "method": method}
        if params:
            message["params"] = params
        await self.ws.send(json.dumps(message))
        
    async def screenshot(self) -> str:
        """Capture screenshot as base64"""
        result = await self.send("Page.captureScreenshot", {"format": "png"})
        return result.get("result", {}).get("data", "")
        
    async def mouse_click(self, x: int, y: int, button: str = "left", show_marker: bool = True):
        """Click at pixel coordinates with visual feedback"""
        # Draw visual click marker on the page
        if show_marker:
            await self.send("Runtime.evaluate", {
                "expression": f"""
                (function() {{
                    var old = document.getElementById('__click_marker__');
                    if (old) old.remove();
                    
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
                    
                    setTimeout(function() {{
                        marker.style.transform = 'scale(2)';
                        marker.style.opacity = '0';
                        marker.style.transition = 'all 0.3s';
                    }}, 100);
                    setTimeout(function() {{ marker.remove(); }}, 500);
                }})();
                """
            })
        
        # Mouse events
        await self.send_no_wait("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })
        
        await asyncio.sleep(0.05)
        
        await self.send_no_wait("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x,
            "y": y,
            "button": button,
            "clickCount": 1
        })
        
    async def type_text(self, text: str):
        """Type text"""
        await self.send("Input.insertText", {"text": text})
        
    async def press_key(self, key: str):
        """Press a key"""
        key_codes = {
            "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8,
            "ArrowUp": 38, "ArrowDown": 40, "ArrowLeft": 37, "ArrowRight": 39
        }
        
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": key,
            "code": f"Key{key}" if len(key) == 1 else key,
            "windowsVirtualKeyCode": key_codes.get(key, ord(key[0].upper()) if key else 0)
        })
        await self.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": key
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
        
    async def close(self):
        """Close CDP connection"""
        if self._listen_task:
            self._listen_task.cancel()
        if self.ws:
            await self.ws.close()
