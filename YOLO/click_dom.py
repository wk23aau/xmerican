"""Click at DOM coordinates"""
import asyncio
from cdp_client import CDPClient

async def main():
    cdp = CDPClient()
    await cdp.connect()
    
    # First click Agree to dismiss cookie banner
    print("Clicking Agree at (1132, 38)...")
    await cdp.mouse_click(1132, 38)
    await asyncio.sleep(1)
    
    # Now click Get started
    print("Clicking Get started at (1146, 125)...")
    await cdp.mouse_click(1146, 125)
    print("Clicked!")
    
    await asyncio.sleep(3)
    print("URL:", await cdp.get_url())
    
    await cdp.close()

asyncio.run(main())
