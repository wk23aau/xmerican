import urllib.request
import json
import asyncio
import websockets
import base64
from PIL import Image
import io

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720

async def main():
    data = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())
    ws_url = data[0]["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({
            "id": 1,
            "method": "Page.captureScreenshot",
            "params": {"format": "png"}
        }))
        r = json.loads(await ws.recv())
        img_data = base64.b64decode(r["result"]["data"])
        
        # Resize to match CSS viewport (1:1 with viewport)
        img = Image.open(io.BytesIO(img_data))
        img_resized = img.resize((VIEWPORT_WIDTH, VIEWPORT_HEIGHT), Image.LANCZOS)
        img_resized.save("viewport/screenshot.png")
        print(f"Screenshot: {img_resized.width}x{img_resized.height}")

asyncio.run(main())
