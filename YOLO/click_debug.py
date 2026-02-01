"""Take fresh screenshot with click marker"""
import asyncio
import base64
import cv2
import numpy as np
from cdp_client import CDPClient

async def main():
    cdp = CDPClient()
    await cdp.connect()
    
    print("URL:", await cdp.get_url())
    
    # Take fresh screenshot
    data = await cdp.screenshot()
    img_bytes = base64.b64decode(data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    print(f"Screenshot: {img.shape[1]}x{img.shape[0]}")
    
    # Draw click marker at Get started button location
    click_x, click_y = 1146, 125
    
    # Draw crosshair
    cv2.drawMarker(img, (click_x, click_y), (0, 0, 255), cv2.MARKER_CROSS, 30, 3)
    cv2.circle(img, (click_x, click_y), 20, (0, 0, 255), 2)
    cv2.putText(img, f"CLICK ({click_x},{click_y})", (click_x-60, click_y-30), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    
    cv2.imwrite("output/click_debug.png", img)
    print("Saved: output/click_debug.png")
    
    # Also test a direct click
    print(f"\nTesting click at ({click_x}, {click_y})...")
    await cdp.mouse_click(click_x, click_y)
    print("Click sent!")
    
    await asyncio.sleep(2)
    
    # Take another screenshot after click
    data2 = await cdp.screenshot()
    img_bytes2 = base64.b64decode(data2)
    nparr2 = np.frombuffer(img_bytes2, np.uint8)
    img2 = cv2.imdecode(nparr2, cv2.IMREAD_COLOR)
    cv2.imwrite("output/after_click.png", img2)
    print("After click: output/after_click.png")
    
    print("New URL:", await cdp.get_url())
    
    await cdp.close()

asyncio.run(main())
