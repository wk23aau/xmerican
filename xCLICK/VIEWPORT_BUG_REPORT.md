# Viewport Discrepancy Bug Report

## Problem Summary

Chrome ignores `--window-size=1280,805` flag and runs at native resolution (~2560x1440), causing coordinate mismatch between YOLO detection and mouse clicks.

## Symptoms

```
Expected:  [vp] 1280x720 dpr=1.0
Actual:    [vp] browser=2560x1440 → capture=1280x720
```

## Impact

| Component | Space | Result |
|-----------|-------|--------|
| YOLO detection | 1280x720 (captured) | ✅ Works |
| Probe coordinates | 1280x720 | ✅ Works |
| CDP mouse click | Sent as 1280x720 | ❌ Wrong position |
| Browser expects | 2560x1440 | ❌ Mismatch! |

**Clicks land at ~50% of intended position** (1280/2560 = 0.5)

## Root Cause Analysis

### 1. Chrome --window-size Not Working

```powershell
# This is being ignored:
chrome.exe --window-size=1280,805 --remote-debugging-port=9222
```

**Why?** Chrome on Windows with existing profile ignores `--window-size`:
- Window manager restores previous position/size
- Multiple monitors cause conflicts
- Chrome may have zombie processes

### 2. Emulation.setDeviceMetricsOverride Ignored

```python
# cdp_client.py - Chrome ignores this when non-headless
await self.send("Emulation.setDeviceMetricsOverride", {
    "width": 1280,    # ← Ignored!
    "height": 720,
})
```

## Coordinate Flow Diagram

```
Browser Window: 2560x1440 (native)
    Button "Submit" at (800, 400)
              │
              ▼ (capture at 1280x720)
YOLO sees scaled image
    Button detected at (400, 200)  ← HALF!
              │
              ▼ (click sent)
CDP click at (400, 200)
    But browser expects (800, 400)!
    MISS by ~400px!
```

## Recommended Fix: Scale Coordinates

```python
# vision_module.py
self.scale_x = browser_width / VIEWPORT_WIDTH   # 2560/1280 = 2.0
self.scale_y = browser_height / VIEWPORT_HEIGHT # 1440/720 = 2.0

# xclick.py - scale before clicking
cx = int(probe.cx * self.vision_module.scale_x)
cy = int(probe.cy * self.vision_module.scale_y)
await self.cdp.mouse_click(cx, cy)
```

## Alternative Fixes

| Option | Pros | Cons |
|--------|------|------|
| Headless mode | Viewport works | No visible window |
| Scale coordinates | Works any size | Code changes |
| CDP Browser.setWindowBounds | Programmatic resize | Complex |
| Kill Chrome + fresh profile | Clean slate | Loses cookies |

## Files to Modify

- `vision_module.py` - Store scale factors
- `xclick.py` - Scale in vclick_text(), click()
- `streaming_vision.py` - Scale predicted positions
