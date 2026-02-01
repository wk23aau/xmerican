# xCLICK - DOM-based Browser Automation

Zero-latency browser automation using DOM for perception and CDP for actions.

## Features

- **DOM-first detection** - Queries DOM directly for interactive elements (buttons, links, inputs)
- **Visual click feedback** - Red circle animation shows exactly where clicks happen
- **Single process** - No viewport flickering from multiple processes
- **Pixel-accurate** - Uses `getBoundingClientRect()` for precise coordinates

## Requirements

- Chrome running with `--remote-debugging-port=9222`
- Python 3.8+
- `websockets`, `aiohttp` packages

## Quick Start

1. Start Chrome with debug port:
   ```
   chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\chrome-debug https://example.com
   ```

2. Run xCLICK:
   ```
   python xclick.py
   ```

3. Use commands:
   ```
   >>> click Get started
   >>> type hello@example.com
   >>> press Enter
   >>> probes
   ```

## Commands

| Command | Description |
|---------|-------------|
| `click <text>` | Click element containing text |
| `click <x> <y>` | Click at pixel coordinates |
| `type <text>` | Type text into focused element |
| `press <key>` | Press key (Enter, Tab, Escape, etc) |
| `goto <url>` | Navigate to URL |
| `probes` / `p` | Show all detected elements |
| `wait <sec>` | Wait for seconds |
| `exit` / `q` | Quit |

## Files

- `xclick.py` - Main automation module
- `cdp_client.py` - Chrome DevTools Protocol client
- `config.py` - Configuration (viewport, port)

## API Usage

```python
from xclick import xClick

async def main():
    bot = xClick()
    await bot.connect()
    
    await bot.click_text("Sign In")
    await bot.type_text("user@example.com")
    await bot.press("Tab")
    await bot.type_text("password123")
    await bot.press("Enter")
    
    await bot.close()
```
