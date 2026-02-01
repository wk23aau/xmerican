"""Verify all dimensions match"""
import json
import asyncio
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT

async def verify():
    print("=" * 50)
    print("DIMENSION VERIFICATION")
    print("=" * 50)
    
    # 1. Config settings
    print(f"\n[CONFIG] Viewport: {VIEWPORT_WIDTH} x {VIEWPORT_HEIGHT}")
    
    # 2. Browser actual size via CDP
    cdp = CDPClient()
    await cdp.connect()
    
    result = await cdp.send("Page.getLayoutMetrics")
    metrics = result.get("result", {})
    layout = metrics.get("layoutViewport", {})
    visual = metrics.get("visualViewport", {})
    
    browser_w = layout.get("clientWidth")
    browser_h = layout.get("clientHeight")
    print(f"\n[BROWSER] Layout viewport: {browser_w} x {browser_h}")
    print(f"[BROWSER] Visual viewport: {visual.get('clientWidth')} x {visual.get('clientHeight')}")
    
    # 3. YOLO probe output
    try:
        with open("output/yolo_probes.json", "r") as f:
            data = json.load(f)
            vp = data.get("viewport", [0, 0])
            print(f"\n[YOLO JSON] Viewport: {vp[0]} x {vp[1]}")
    except Exception as e:
        print(f"\n[YOLO JSON] Error: {e}")
    
    # 4. Comparison
    print("\n" + "=" * 50)
    print("COMPARISON:")
    config_match = (VIEWPORT_WIDTH == browser_w and VIEWPORT_HEIGHT == browser_h)
    print(f"  Config matches Browser: {'✓ YES' if config_match else '✗ NO - MISMATCH!'}")
    
    if not config_match:
        print(f"\n  Recommended fix:")
        print(f"    VIEWPORT_WIDTH = {browser_w}")
        print(f"    VIEWPORT_HEIGHT = {browser_h}")
    
    await cdp.close()

asyncio.run(verify())
