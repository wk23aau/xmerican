"""
Simple probe debug viewer - takes screenshot and draws probes
"""
import cv2
import json
import asyncio
from cdp_client import CDPClient
import base64
import numpy as np

async def main():
    cdp = CDPClient()
    await cdp.connect()
    
    # Take screenshot
    screenshot_data = await cdp.screenshot()
    img_bytes = base64.b64decode(screenshot_data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Load probes
    with open('output/yolo_probes.json') as f:
        data = json.load(f)
    
    h, w = frame.shape[:2]
    print(f'Screenshot: {w}x{h}')
    print(f'Probes: {len(data["probes"])}')
    
    # Draw probes
    for probe in data['probes']:
        px, py = probe.get('pixelCenter', [0, 0])
        text = probe.get('text', '')[:20]
        ptype = probe.get('type', 'unknown')
        
        # Draw circle and label
        cv2.circle(frame, (px, py), 10, (0, 255, 0), 2)
        cv2.putText(frame, f'{ptype}: {text}', (px+15, py), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        print(f'  [{probe.get("id")}] {ptype}: {text} at ({px}, {py})')
        
    cv2.imshow('Probe Debug', frame)
    print("\nPress any key in the window to close...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    await cdp.close()

if __name__ == "__main__":
    asyncio.run(main())
