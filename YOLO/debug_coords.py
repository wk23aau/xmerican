"""Debug DOM coordinates"""
import asyncio
from cdp_client import CDPClient

async def main():
    cdp = CDPClient()
    await cdp.connect()
    
    # Check actual viewport size in DOM
    result = await cdp.send('Runtime.evaluate', {
        'expression': 'JSON.stringify({innerWidth: window.innerWidth, innerHeight: window.innerHeight})',
        'returnByValue': True
    })
    print('Window dimensions:', result.get('result', {}).get('result', {}).get('value'))
    
    # Get email input position
    js = """
    (function() {
        var el = document.querySelector('input');
        if (!el) return 'No input found';
        var rect = el.getBoundingClientRect();
        return JSON.stringify({
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height,
            centerX: Math.round(rect.left + rect.width/2),
            centerY: Math.round(rect.top + rect.height/2)
        });
    })()
    """
    result = await cdp.send('Runtime.evaluate', {
        'expression': js,
        'returnByValue': True
    })
    print('Email input rect:', result.get('result', {}).get('result', {}).get('value'))
    
    # Get Next button position
    js2 = """
    (function() {
        var buttons = document.querySelectorAll('button');
        for (var btn of buttons) {
            if (btn.innerText.includes('Next')) {
                var rect = btn.getBoundingClientRect();
                return JSON.stringify({
                    text: btn.innerText,
                    left: rect.left,
                    top: rect.top,
                    centerX: Math.round(rect.left + rect.width/2),
                    centerY: Math.round(rect.top + rect.height/2)
                });
            }
        }
        return 'No Next button';
    })()
    """
    result = await cdp.send('Runtime.evaluate', {
        'expression': js2,
        'returnByValue': True
    })
    print('Next button rect:', result.get('result', {}).get('result', {}).get('value'))
    
    await cdp.close()

asyncio.run(main())
