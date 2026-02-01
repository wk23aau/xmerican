---
name: Independent Browsing Agent
description: An autonomous browser automation agent using Chrome DevTools Protocol (CDP) REPL for web interactions
---

# Independent Browsing Agent

This skill enables the agent to operate as an **Independent Browsing Agent** that controls Chrome browser via the Chrome DevTools Protocol (CDP) REPL.

## Configuration

| Setting | Value |
|---------|-------|
| Viewport | 400×640 (portrait) |
| Debug Port | 9222 |
| Profile | `$env:TEMP\chrome-debug-profile` |

## Prerequisites

- Google Chrome installed on the system
- Node.js with `ws` package (`npm install ws`)
- PowerShell available for process management

---

## Workflow

### Step 1: Kill All Previous Chrome Processes

Before starting a new browser session, terminate all existing Chrome processes to ensure a clean state.

```powershell
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
```

---

### Step 2: Start Chrome with Remote Debugging (400×640 Viewport)

Launch Chrome in **portrait mode** (400×640) with remote debugging enabled.

```powershell
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$debugPort = 9222
$userDataDir = "$env:TEMP\chrome-debug-profile"

Start-Process -FilePath $chromePath -ArgumentList @(
    "--remote-debugging-port=$debugPort",
    "--user-data-dir=$userDataDir",
    "--window-size=400,640",
    "--window-position=0,0",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "--disable-popup-blocking"
)
```

**Flags:**
- `--window-size=400,640`: Fixed portrait viewport
- `--remote-debugging-port=9222`: CDP connection port
- `--user-data-dir`: Non-default profile directory

---

### Step 3: Start Interactive CDP REPL Session

The CDP REPL **must be used interactively** for browser automation. Start the REPL session and keep it running.

**Install dependency first:**
```powershell
npm install ws
```

**Start interactive REPL:**
```powershell
node scripts/cdp-repl.js
```

This opens an interactive prompt:
```
cdp [tab-id]> 
```

---

## Interactive Commands

| Category | Command | Description |
|----------|---------|-------------|
| **Tabs** | `tabs` | List all open tabs |
| | `new [url]` | Open new tab |
| | `switch <id\|index>` | Switch to tab by ID or index |
| | `close [id]` | Close tab |
| **Navigation** | `goto <url>` | Navigate to URL |
| | `screenshot` | Save to `.agent/artifacts/capture.png` |
| | `viewport` | Get viewport size |
| **Input** | `click <x> <y>` | Click at coordinates |
| | `hover <x> <y>` | Move mouse |
| | `type <text>` | Type text |
| | `press <key>` | Press key (Enter, Tab, Escape, etc.) |
| | `scroll <x> <y>` | Scroll page |
| **Perception** | `world` | Scan page for interactive elements (Action Map) |
| **Other** | `eval <js>` | Execute JavaScript |
| | `wait <ms>` | Wait milliseconds |
| | `help` | Show all commands |
| | `exit` | Exit REPL |

**Shortcuts:** `ss` = screenshot, `nav` = goto, `vp` = viewport, `w` = world, `q` = exit

---

## World State (Action Map)

The `world` command scans the current page for **interactive elements** and outputs a structured **Action Map** to `output/world.json`.

### What it detects

- Buttons, links, inputs, selects, textareas
- Elements with interactive roles (`button`, `link`, `menuitem`, `tab`, `checkbox`, `radio`)
- Elements with `onclick` handlers or `tabindex`

### Output format

```json
{
  "timestamp": "2026-01-30T23:00:00Z",
  "viewport": { "width": 400, "height": 640 },
  "cursor": { "x": 0, "y": 0 },
  "elementCount": 15,
  "elements": [
    {
      "id": "el_0",
      "label": "Sign In",
      "role": "button",
      "type": "button",
      "rect": { "x": 100, "y": 200, "width": 80, "height": 30 },
      "center": { "x": 140, "y": 215 },
      "state": { "disabled": false, "checked": false, "expanded": false, "selected": false },
      "occluded": false,
      "tag": "button"
    }
  ]
}
```

### Key fields

| Field | Description |
|-------|-------------|
| `id` | Unique element ID (`el_0`, `el_1`, etc.) |
| `label` | Human-readable text (aria-label, title, innerText) |
| `role` | Element role (button, link, input, etc.) |
| `rect` | Pixel coordinates and size |
| `center` | Center point for clicking |
| `state` | Interactive states (disabled, checked, etc.) |
| `occluded` | True if element is blocked by another element |

---

## Screenshot Notes

- **Always saves to `.agent/artifacts/capture.png`** (replaces previous screenshot)
- Saved at **1x scale** (no modifications)
- Original aspect ratio preserved
- Format: PNG (lossless)
- Size: 400×640 pixels (matches viewport)

---

## Example Interactive Session

```
cdp [no tab]> tabs
📑 Open Tabs:
  [0] ABC123...
      Title: New Tab
      URL: chrome://newtab

cdp [no tab]> switch 0
✅ Switched to tab: ABC123...

cdp [ABC123...]> goto google.com
✅ Navigating to: https://google.com

cdp [ABC123...]> ss
✅ Screenshot saved: .agent/artifacts/capture.png (45678 bytes)

cdp [ABC123...]> click 200 300
✅ Clicked: (200, 300)

cdp [ABC123...]> type hello world
✅ Typed: "hello world"

cdp [ABC123...]> press Enter
✅ Pressed: Enter

cdp [ABC123...]> exit
👋 Goodbye!
```

---

## Single Command Mode (for scripting)

You can also run single commands non-interactively:
```powershell
node scripts/cdp-repl.js goto google.com
node scripts/cdp-repl.js ss
```

---

## Notes

- The REPL auto-connects to the first available tab on startup
- Use `switch` with tab index (0, 1, 2...) or full tab ID
- Screenshots are 1x scale with no modifications
- Viewport is fixed at 400×640 pixels (portrait)
