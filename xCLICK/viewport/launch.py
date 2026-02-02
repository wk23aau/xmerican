"""
Chrome Viewport Launcher
========================
Launches Chrome with exact viewport size using CDP to override metrics.
"""

import subprocess
import sys
import os
import time
import urllib.request
import json
import asyncio

# Configuration
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
DEBUG_PORT = 9222
USER_DATA_DIR = os.path.join(os.environ.get('TEMP', '/tmp'), 'ChromeViewport')

def get_chrome_path():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Chrome not found")

def kill_chrome():
    if sys.platform == 'win32':
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'], capture_output=True, check=False)

async def set_viewport_via_cdp(width, height):
    """Use CDP to force exact viewport size"""
    import websockets
    
    data = json.loads(urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json").read())
    ws_url = data[0]["webSocketDebuggerUrl"]
    
    async with websockets.connect(ws_url) as ws:
        # Set device metrics override - force scale factor 1 for 1:1 screenshot
        await ws.send(json.dumps({
            "id": 1,
            "method": "Emulation.setDeviceMetricsOverride",
            "params": {
                "width": width,
                "height": height,
                "deviceScaleFactor": 1,  # Force 1:1 pixel ratio
                "mobile": False,
                "screenWidth": width,
                "screenHeight": height
            }
        }))
        await ws.recv()
        
        # Verify
        await ws.send(json.dumps({
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {"expression": "window.innerWidth + 'x' + window.innerHeight"}
        }))
        r = json.loads(await ws.recv())
        return r["result"]["result"]["value"]

def launch_chrome(url="https://www.google.com"):
    chrome_path = get_chrome_path()
    
    args = [
        chrome_path,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--window-size=1400,900",
        "--window-position=0,0",
        "--disable-extensions",
        "--no-first-run",
        url
    ]
    
    print(f"Launching Chrome...")
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    
    # Force viewport via CDP
    print(f"Setting viewport to {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT} via CDP...")
    result = asyncio.run(set_viewport_via_cdp(VIEWPORT_WIDTH, VIEWPORT_HEIGHT))
    print(f"✓ Viewport: {result}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="https://www.google.com")
    parser.add_argument("--kill", action="store_true")
    args = parser.parse_args()
    
    if args.kill:
        print("Killing Chrome...")
        kill_chrome()
        time.sleep(2)
    
    launch_chrome(args.url)
