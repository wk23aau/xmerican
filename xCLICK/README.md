# xCLICK v2.0

Visual browser automation with YOLO detection, smooth mouse movement, and real-time debugging.

## Architecture

```
xCLICK/
├── xclick.py           # Main entry point & REPL
├── perception/         # Vision (YOLO) + DOM detection
├── world/              # State tracking + ROI masking
├── execution/          # Mouse movement + CDP actions
├── ui/                 # Visual overlay rendering
│
├── cdp_client.py       # Chrome DevTools Protocol
├── vision_module.py    # YOLO inference + DOM fusion
├── motion_controller.py# 60Hz smooth cursor
├── world_state.py      # Object persistence + IoU
├── roi_mask.py         # Negative space filtering
├── overlay.py          # SVG bounding boxes
└── config.py           # Configuration
```

## Quick Start

```bash
# Start Chrome with debug port
chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\ChromeDebug

# Run xCLICK
python xclick.py --vision
```

## Commands

### Detection
| Command | Description |
|---------|-------------|
| `probes` / `p` | Show DOM elements |
| `vprobes` / `vp` | Show YOLO elements |
| `world` | Show tracked objects with stability |
| `facts` | Export as JSON |

### Actions
| Command | Description |
|---------|-------------|
| `click <text>` | Click by text (DOM) |
| `vclick <label>` | Click by vision |
| `smooth <text>` | Smooth move + click |
| `seek <text>` | Smooth move only |

### Visual
| Command | Description |
|---------|-------------|
| `show` | Draw bounding boxes |
| `hide` | Clear overlay |
| `overlay` | Toggle overlay |

### Filtering
| Command | Description |
|---------|-------------|
| `focus [%]` | Focus on center |
| `noads` | Exclude ad areas |
| `roi` | Show ROI status |
| `clearmask` | Clear filters |

## Features

- **Two-loop architecture**: Perception 5Hz, Control 60Hz
- **Smooth mouse movement**: EMA smoothing, SEEK→HOVER→CLICK
- **World state**: Persistent tracking with stability scoring
- **Live overlay**: Color-coded bounding boxes
- **ROI masking**: Ad detection, negative space

## ChatGPT Gaps Implemented

| # | Gap | Status |
|---|-----|--------|
| 1 | Real-time perception | ✅ 5Hz throttled |
| 2 | Vision+DOM fusion | ✅ IoU matching |
| 3 | World state model | ✅ `world_state.py` |
| 4 | Decoupled execution | ✅ Two-loop |
| 5 | Smooth cursor | ✅ 60Hz EMA |
| 6 | Negative space | ✅ `roi_mask.py` |
| 7 | YOLO model | ✅ yolov11l-ui |
| 8 | Live overlay | ✅ `overlay.py` |
| 9 | Project structure | ✅ Modular |
