"""List all CDP targets"""
import urllib.request
import json

targets = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())
print(f"Found {len(targets)} CDP targets:")
for i, t in enumerate(targets):
    ttype = t.get("type", "unknown")
    url = t.get("url", "")[:70]
    title = t.get("title", "")[:30]
    wsurl = t.get("webSocketDebuggerUrl", "")
    print(f"  [{i}] {ttype}: {title}")
    print(f"      URL: {url}")
    if wsurl:
        print(f"      WS: {wsurl}")
    print()
