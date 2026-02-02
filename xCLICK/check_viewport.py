import asyncio
import websockets
import json
import urllib.request

async def get_viewport():
    data = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())
    ws_url = data[0]["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": "JSON.stringify({outer: window.outerWidth + 'x' + window.outerHeight, inner: window.innerWidth + 'x' + window.innerHeight})"}
        }))
        r = json.loads(await ws.recv())
        print(r["result"]["result"]["value"])

asyncio.run(get_viewport())
