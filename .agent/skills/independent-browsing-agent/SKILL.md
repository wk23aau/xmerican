---
name: Independent Browsing Agent
description: Autonomous browser automation combining YOLO streaming probes with DOM world state for near-zero latency actions
---

# Independent Browsing Agent

This skill enables the agent to operate as an **Independent Browsing Agent** that combines:
- **YOLO Streaming Probes** (30-60 Hz vision)
- **DOM World State** (structural awareness)
- **CDP REPL** (action execution)

## Near-Zero Latency Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     YOLO VISION LAYER (30-60 Hz)                    │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │ CDP Screen-  │───▶│ YOLO Probe   │───▶│ Probe        │          │
│  │ cast Frames  │    │ Detector     │    │ Tracker      │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     WORLD STATE (5-20 Hz)                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │ YOLO Probes  │ +  │ DOM Elements │ =  │ Merged World │          │
│  │ (visual)     │    │ (structural) │    │ State        │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     ACTION LAYER (Immediate)                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │ FSM Planner  │───▶│ Mouse/Scroll │───▶│ CDP Actions  │          │
│  │              │    │ Controller   │    │              │          │
│  └──────────────┘    └──────────────┘    └──────────────┘          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

| Setting | Value |
|---------|-------|
| Viewport | 400×640 (portrait) or 1280×720 |
| Debug Port | 9222 |
| Vision FPS | 30-60 Hz |
| Action Rate | 5-20 Hz |

---

## Quick Start

### 1. Start Chrome with Debugging
```powershell
$chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
Start-Process $chromePath -ArgumentList @(
    "--remote-debugging-port=9222",
    "--user-data-dir=$env:TEMP\chrome-debug-profile",
    "--window-size=400,640"
)
```

### 2. Run YOLO Agent with Debug Overlay
```bash
cd YOLO
python main.py --debug
```

### 3. Watch Bounding Boxes in Real-Time
A separate window shows:
- Green boxes = buttons
- Orange boxes = links
- Cyan boxes = inputs
- Red overlay = blockers/modals

---

## Dual World State

The agent combines **two perception sources**:

### YOLO Probes (Vision)
```json
{
  "id": 5,
  "type": "button",
  "bbox": [0.12, 0.45, 0.28, 0.52],
  "cx": 0.20,
  "cy": 0.485,
  "score": 0.92
}
```
- **Fast**: Updates every 16-33ms
- **Visual**: Detects anything that looks clickable
- **Robust**: Works on canvas, images, iframes

### DOM Elements (Structure)
```json
{
  "id": "el_3",
  "tag": "button",
  "label": "Submit Application",
  "role": "button",
  "center": {"x": 200, "y": 300},
  "state": {"disabled": false}
}
```
- **Semantic**: Has text labels and ARIA roles
- **State-aware**: Knows if disabled/checked
- **Accurate**: Exact element boundaries

### Merged Strategy
```
1. YOLO provides fast coordinates → "where to click"
2. DOM provides context → "what it means"
3. Agent matches probe to DOM element by overlap
4. Action: Click probe coordinates + verify DOM state
```

---

## Interactive CDP REPL

The CDP REPL is still available for direct control:

```bash
node scripts/cdp-repl.js
```

| Command | Description |
|---------|-------------|
| `world` | Get DOM elements (action map) |
| `ss` | Take screenshot |
| `click X Y` | Click at coordinates |
| `type TEXT` | Type text |
| `press KEY` | Press Enter, Tab, etc |

---

## Workflow: Job Application

```
┌─────────────────────────────────────────────────────────────────────┐
│  YOLO Vision Loop (runs continuously at 30-60 Hz)                   │
│                                                                     │
│  Frame → Detect Probes → Track → Update World State                │
│                                                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FSM Action Loop (runs at 5-10 Hz)                                  │
│                                                                     │
│  State: FIND_APPLY                                                  │
│    ├─ Score probes by keywords ["apply", "apply now"]               │
│    ├─ Best probe: id=5, score=8.2                                   │
│    └─ Action: CLICK probe at (0.45, 0.32)                           │
│                                                                     │
│  State: FILL_FORM                                                   │
│    ├─ Detect input fields                                           │
│    ├─ Match to DOM for labels                                       │
│    └─ Action: TYPE into input                                       │
│                                                                     │
│  State: SUBMIT                                                      │
│    ├─ Find submit button                                            │
│    └─ Action: CLICK                                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Latency Comparison

| Approach | Screenshot + LLM | DOM Query | YOLO Streaming |
|----------|------------------|-----------|----------------|
| Detection | 1-3 seconds | 50-100ms | <16ms |
| Per action | 2-5 seconds | 100-200ms | <50ms |
| Real-time | ❌ | ❌ | ✅ |
| Visual accuracy | Medium | N/A | High |
| Semantic context | High | High | Low (add DOM) |

**YOLO + DOM = Best of both worlds**

---

## Files

| File | Purpose |
|------|---------|
| `YOLO/main.py` | Main agent entry point |
| `YOLO/debug_visualizer.py` | Bounding box overlay |
| `YOLO/world_state.py` | Live state management |
| `YOLO/fsm.py` | Job application state machine |
| `scripts/cdp-repl.js` | Interactive browser control |

---

## Usage Examples

### Run with Debug Visualization
```bash
python YOLO/main.py --debug --url "https://linkedin.com/jobs"
```

### Get Current Probes (Python)
```python
from YOLO import VisionAgent
agent = VisionAgent(debug=True)
await agent.start()

# Access live probes
world = agent.world_manager.get_state()
for probe in world.probes:
    print(f"Probe {probe['id']}: {probe['type']} at ({probe['cx']}, {probe['cy']})")
```

### Combine with CDP REPL
```
# Terminal 1: Run YOLO agent
python YOLO/main.py --debug

# Terminal 2: Use CDP REPL for manual control
node scripts/cdp-repl.js
cdp> world        # Get DOM elements
cdp> click 200 300  # Click at probe location
```

---

## Notes

- YOLO runs as a **background process** streaming probes
- CDP REPL can run **alongside** for manual intervention
- Press **ESC** in debug window to stop
- Probes have **stable IDs** - same button keeps same ID across frames
