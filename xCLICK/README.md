# xCLICK - DOM-based Browser Automation + YOLO Vision

Zero-latency browser automation using DOM for perception and CDP for actions.
Now with **YOLO vision integration** for labeled probe detection!

## Features

- **DOM-first detection** - Queries DOM directly for interactive elements (buttons, links, inputs)
- **YOLO Vision mode** - Detects UI elements visually with labels (e.g., "button @ (x,y): Submit")
- **Visual click feedback** - Red circle animation shows exactly where clicks happen
- **Single process** - No viewport flickering from multiple processes
- **Pixel-accurate** - Uses `getBoundingClientRect()` for precise coordinates

## Requirements

- Chrome running with `--remote-debugging-port=9222`
- Python 3.8+
- `websockets`, `aiohttp` packages
- For vision mode: `ultralytics`, `opencv-python`, `pillow` packages

## Quick Start

1. Start Chrome with debug port:
   ```
   chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\chrome-debug https://example.com
   ```

2. Run xCLICK (DOM mode):
   ```
   python xclick.py
   ```

3. Run xCLICK with YOLO Vision:
   ```
   python xclick.py --vision
   ```

4. Use commands:
   ```
   >>> click Get started           # DOM-based click
   >>> vclick Submit               # Vision-based click (YOLO + DOM label)
   >>> vprobes                     # Show YOLO-detected elements with labels
   >>> vscan                       # Save annotated debug screenshot
   >>> type hello@example.com
   >>> press Enter
   ```

## Commands

| Command | Description |
|---------|-------------|
| `click <text>` | Click element containing text (DOM) |
| `click <x> <y>` | Click at pixel coordinates |
| `vclick <label>` | Click element by vision label (YOLO + DOM) |
| `vprobes` / `vp` | Show YOLO-detected elements with labels |
| `vscan` | Capture and save annotated debug screenshot |
| `vision` | Enable vision mode at runtime |
| `type <text>` | Type text into focused element |
| `press <key>` | Press key (Enter, Tab, Escape, etc) |
| `goto <url>` | Navigate to URL |
| `probes` / `p` | Show all DOM-detected elements |
| `scroll [amt]` | Scroll down |
| `tabs` / `tab <n>` | Tab management |
| `wait <sec>` | Wait for seconds |
| `exit` / `q` | Quit |

## Files

- `xclick.py` - Main automation module
- `cdp_client.py` - Chrome DevTools Protocol client
- `vision_module.py` - YOLO + DOM fusion for labeled detection
- `config.py` - Configuration (viewport, port, vision settings)

## Vision Mode Output

Without vision:
```
[0] button   'Submit' (150,300)
```

With vision:
```
[1] button   'Submit'                          (150,300) [0.92]
```

The vision mode shows:
- Element type detected by YOLO
- Label extracted from DOM (`aria-label`, `innerText`, etc.)
- Center coordinates in CSS pixels
- Detection confidence score

## API Usage

```python
from xclick import xClick

async def main():
    bot = xClick(vision=True)  # Enable vision mode
    await bot.connect()
    
    # DOM-based clicking
    await bot.click_text("Sign In")
    
    # Vision-based clicking (with labels)
    await bot.vclick_text("Submit Application")
    
    # Type and submit
    await bot.type_text("user@example.com")
    await bot.press("Tab")
    await bot.type_text("password123")
    await bot.press("Enter")
    
    await bot.close()
```

## Architecture

```
Vision proposes (YOLO boxes) → DOM explains (labels via elementFromPoint)

┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│ CDP Screenshot  │ ──> │ YOLO Detect  │ ──> │ DOM Query at    │
│ (PNG + metrics) │     │ (boxes+type) │     │ each box center │
└─────────────────┘     └──────────────┘     └─────────────────┘
                                                      │
                                                      v
                                            ┌─────────────────┐
                                            │ LabeledProbe    │
                                            │ (type + label)  │
                                            └─────────────────┘
```

