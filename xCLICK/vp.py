import urllib.request
import json
import asyncio
import websockets

async def main():
    data = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())
    ws_url = data[0]["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"id":1,"method":"Runtime.evaluate","params":{"expression":"window.innerWidth + 'x' + window.innerHeight"}}))
        r = json.loads(await ws.recv())
        print("VIEWPORT:", r["result"]["result"]["value"])

asyncio.run(main())
