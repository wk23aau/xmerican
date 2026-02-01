"""Debug viewport and coordinates - works on any page"""
import asyncio
import base64
import cv2
import numpy as np
from cdp_client import CDPClient

async def main():
    cdp = CDPClient()
    await cdp.connect()
    
    # Check viewport dimensions
    result = await cdp.send('Runtime.evaluate', {
        'expression': 'JSON.stringify({innerW: window.innerWidth, innerH: window.innerHeight})',
        'returnByValue': True
    })
    dims = result.get('result', {}).get('result', {}).get('value')
    print(f'DOM viewport: {dims}')
    
    # Take screenshot
    data = await cdp.screenshot()
    img_bytes = base64.b64decode(data)
    nparr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = frame.shape[:2]
    print(f'Screenshot: {w}x{h}')
    
    # Get ALL interactive elements
    js = """
    (function() {
        var results = [];
        var selectors = 'button, a, input, [role="button"]';
        var elements = document.querySelectorAll(selectors);
        
        elements.forEach(function(el, i) {
            if (i > 15) return; // Limit
            var rect = el.getBoundingClientRect();
            if (rect.width <= 0 || rect.height <= 0) return;
            
            var text = (el.innerText || el.value || el.placeholder || '').trim().substring(0, 30);
            var tag = el.tagName.toLowerCase();
            
            results.push({
                tag: tag,
                text: text,
                left: Math.round(rect.left),
                top: Math.round(rect.top),
                right: Math.round(rect.right),
                bottom: Math.round(rect.bottom),
                cx: Math.round(rect.left + rect.width/2),
                cy: Math.round(rect.top + rect.height/2)
            });
        });
        
        return results;
    })()
    """
    result = await cdp.send('Runtime.evaluate', {
        'expression': js,
        'returnByValue': True
    })
    elements = result.get('result', {}).get('result', {}).get('value') or []
    print(f'Found {len(elements)} elements:')
    
    colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255)]
    
    for i, el in enumerate(elements):
        color = colors[i % len(colors)]
        # Draw bounding box
        cv2.rectangle(frame, (el['left'], el['top']), (el['right'], el['bottom']), color, 2)
        # Draw center
        cv2.circle(frame, (el['cx'], el['cy']), 6, color, -1)
        # Draw label
        label = f"{el['tag']}: {el['text'][:15]}"
        cv2.putText(frame, label, (el['left'], el['top']-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
        print(f"  [{i}] {el['tag']}: '{el['text']}' @ ({el['cx']}, {el['cy']})")
    
    cv2.imshow('DOM Debug', frame)
    print("\nPress any key to close...")
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    
    await cdp.close()

asyncio.run(main())
