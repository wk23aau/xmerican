---
name: Vision Analyst (YOLO Streaming)
description: Real-time vision agent using YOLO streaming probes for near-zero latency UI detection
---

# Vision Analyst (YOLO Streaming)

**YOLO = PERCEPTION ONLY.** The executor (agent) reads probes and performs actions.

> [!CAUTION]
> **YOLO DOES NOT TAKE ACTIONS**
> 
> YOLO only provides:
> - Probe coordinates (what to click)
> - Bounding boxes (where elements are)
> - Blocker detection (what's in the way)
> 
> The **executor** reads `output/yolo_probes.json` and acts via CDP REPL.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  YOLO PERCEPTION (30-60 Hz) - NO ACTIONS                            │
│                                                                     │
│  CDP Screencast → YOLO Detect → Track → output/yolo_probes.json    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼ (file read)
┌─────────────────────────────────────────────────────────────────────┐
│  EXECUTOR (Agent) - PERFORMS ACTIONS                                │
│                                                                     │
│  1. Read yolo_probes.json                                           │
│  2. Read DOM world state (optional)                                 │
│  3. Decide: which probe to click                                    │
│  4. Execute: CDP REPL click/type/scroll                             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## How to Use

### 1. Start YOLO Probe Server (perception only)
```bash
cd YOLO
python probe_server.py --debug
```

### 2. Probes stream to file in real-time
```
output/yolo_probes.json  (updates at 30 Hz)
```
```json
{
  "timestamp": 1738404000.123,
  "frame_count": 1542,
  "viewport": [1280, 720],
  "cursor_pos": [0.45, 0.32],
  "probes": [
    {
      "id": 1,
      "type": "button",
      "bbox": [0.12, 0.45, 0.28, 0.52],
      "cx": 0.20,
      "cy": 0.485,
      "score": 0.92,
      "velocity": [0.0, 0.0]
    }
  ],
  "blockers": [],
  "events": ["probes_appeared"],
  "mode": "normal"
}
```

---

## Probe Format

| Field | Description |
|-------|-------------|
| `id` | Stable tracking ID (persists across frames) |
| `type` | button, link, input, checkbox, icon, menu, dropdown, close |
| `bbox` | [x1, y1, x2, y2] normalized 0-1 |
| `cx, cy` | Center point normalized 0-1 |
| `score` | Detection confidence 0-1 |
| `velocity` | Movement vector for smooth tracking |

---

## Advantages Over Screenshot Analysis

| Feature | Screenshot Analysis | YOLO Streaming |
|---------|---------------------|----------------|
| Latency | 500-2000ms | <16ms |
| Frequency | On-demand | 30-60 Hz |
| Tracking | None | Stable IDs |
| Motion | Static | Velocity-aware |
| Blockers | Manual detection | Auto-detected |

---

## Integration with CDP REPL

The YOLO agent runs alongside CDP REPL:

1. **YOLO** handles vision (what to click)
2. **CDP REPL** handles actions (clicking, typing)
3. **World State** syncs both (probe → click coordinates)

```
YOLO detects: probe id=5 at cx=0.45, cy=0.32
         ↓
Convert:  x = 0.45 × 400 = 180
          y = 0.32 × 640 = 205
         ↓
CDP REPL: click 180 205
```

---

## Files

| File | Purpose |
|------|---------|
| `YOLO/main.py` | Main agent entry point |
| `YOLO/config.py` | Configuration (FPS, thresholds) |
| `YOLO/probe_detector.py` | YOLO detection logic |
| `YOLO/probe_tracker.py` | IOU tracking for stable IDs |
| `YOLO/world_state.py` | Live state management |
| `YOLO/debug_visualizer.py` | Bounding box overlay |

---

## Quick Commands

```bash
# Run with debug visualization
python YOLO/main.py --debug

# Run headless (no window)
python YOLO/main.py

# Navigate to URL
python YOLO/main.py --url "https://jobs.example.com"
```

Press **ESC** to quit debug window.

---

## Notes

- Probes are **pre-tracked** - no need to re-analyze between frames
- Use `world.probes` for current clickable elements
- Blockers (modals, overlays) auto-detected in `world.blockers`
- Near-zero latency when combined with DOM world state
