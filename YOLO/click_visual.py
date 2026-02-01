"""Click with visual indicator on webpage"""
import asyncio
import base64
from cdp_client import CDPClient

async def main():
    cdp = CDPClient()
    await cdp.connect()
    
    click_x, click_y = 1146, 125
    
    # Inject visual click indicator
    js = f"""
    (function() {{
        // Create click marker
        var marker = document.createElement('div');
        marker.id = 'click-marker';
        marker.style.cssText = `
            position: fixed;
            left: {click_x - 25}px;
            top: {click_y - 25}px;
            width: 50px;
            height: 50px;
            border: 4px solid red;
            border-radius: 50%;
            background: rgba(255, 0, 0, 0.3);
            pointer-events: none;
            z-index: 999999;
            animation: pulse 0.5s ease-out;
        `;
        
        // Add pulse animation
        var style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {{
                0% {{ transform: scale(0.5); opacity: 1; }}
                100% {{ transform: scale(2); opacity: 0; }}
            }}
        `;
        document.head.appendChild(style);
        document.body.appendChild(marker);
        
        // Show crosshair
        var cross = document.createElement('div');
        cross.style.cssText = `
            position: fixed;
            left: {click_x}px;
            top: {click_y}px;
            width: 20px;
            height: 20px;
            margin: -10px 0 0 -10px;
            border: 3px solid red;
            background: yellow;
            border-radius: 50%;
            pointer-events: none;
            z-index: 999999;
        `;
        document.body.appendChild(cross);
        
        // Add label
        var label = document.createElement('div');
        label.textContent = 'CLICK HERE ({click_x}, {click_y})';
        label.style.cssText = `
            position: fixed;
            left: {click_x + 30}px;
            top: {click_y - 10}px;
            background: red;
            color: white;
            padding: 5px 10px;
            font-weight: bold;
            z-index: 999999;
            pointer-events: none;
        `;
        document.body.appendChild(label);
        
        return 'Click indicator added at ({click_x}, {click_y})';
    }})()
    """
    
    result = await cdp.send("Runtime.evaluate", {"expression": js})
    print("Injected click marker:", result.get("result", {}).get("result", {}).get("value", ""))
    
    # Take screenshot with marker
    await asyncio.sleep(0.5)
    data = await cdp.screenshot()
    with open("output/click_visual.png", "wb") as f:
        f.write(base64.b64decode(data))
    print("Screenshot with marker: output/click_visual.png")
    
    # Now do the actual click
    print(f"\nSending click to ({click_x}, {click_y})...")
    
    # Try with mousePressed and mouseReleased separately
    await cdp.send_no_wait("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": click_x,
        "y": click_y,
        "button": "left",
        "clickCount": 1
    })
    await asyncio.sleep(0.1)
    await cdp.send_no_wait("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": click_x,
        "y": click_y,
        "button": "left",
        "clickCount": 1
    })
    
    print("Click sent!")
    
    await asyncio.sleep(2)
    
    # Check URL after
    url = await cdp.get_url()
    print(f"URL after click: {url}")
    
    # Screenshot after click
    data2 = await cdp.screenshot()
    with open("output/after_click.png", "wb") as f:
        f.write(base64.b64decode(data2))
    print("After click: output/after_click.png")
    
    await cdp.close()

asyncio.run(main())
