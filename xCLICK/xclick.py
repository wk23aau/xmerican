"""
xCLICK - DOM-based browser automation with visual feedback
Single process for perception + actions - no viewport flickering

Now with YOLO vision integration for labeled probe detection!

Usage:
    python xclick.py --debug    # With visual debug window
    python xclick.py            # Without debug
    python xclick.py --vision   # Enable YOLO vision mode
    
Commands:
    click <text>     - Click element by text (DOM)
    click <x> <y>    - Click at coordinates
    vclick <label>   - Click element by vision label (YOLO+DOM)
    vprobes / vp     - Show YOLO-detected elements with labels
    vscan            - Capture and save annotated debug image
    type <text>      - Type text
    press <key>      - Press key (Enter, Tab, etc)
    goto <url>       - Navigate to URL
    probes / p       - Show DOM-detected elements
    wait <seconds>   - Wait
    exit / q         - Quit
"""

import asyncio
import argparse
import os
from typing import Dict, List, Optional
from cdp_client import CDPClient
from config import VIEWPORT_WIDTH, VIEWPORT_HEIGHT, YOLO_MODEL_PATH, USE_OCR_FALLBACK, VISION_MODEL_TYPE
from motion_controller import MotionController, MotionConfig, MotionState
from world_state import WorldState, get_world_state, ObjectSource
from overlay import OverlayRenderer
from roi_mask import ROIMask, get_roi_mask
from perception_loop import PerceptionLoop, create_perception_loop
from tracker import get_tracker
from streaming_vision import StreamingVision


class xClick:
    """DOM-based browser automation with visual click feedback + YOLO vision"""
    
    def __init__(self, debug: bool = False, vision: bool = False):
        self.cdp = CDPClient()
        self.probes: List[Dict] = []
        self.vision_probes: List = []  # LabeledProbe objects from vision
        self.debug = debug
        self.vision_enabled = vision
        self.vision_module = None
        self.motion_controller: Optional[MotionController] = None
        self.world = get_world_state()  # Persistent world state
        self.overlay: Optional[OverlayRenderer] = None  # Live visual overlay
        self.roi = get_roi_mask()  # Region of interest filtering
        self.perception_loop: Optional[PerceptionLoop] = None  # Continuous perception
        self.streaming_vision: Optional[StreamingVision] = None  # Background streaming for instant reflexes
        
    async def connect(self):
        """Connect to browser"""
        print("Connecting to browser...")
        # Don't set viewport - Chrome is launched with correct --window-size
        await self.cdp.connect(set_viewport=False)
        print("Connected!")
        
        # Initialize visual cursor (green circle follows mouse)
        await self.cdp.init_cursor_visual()
        print("✓ Visual cursor enabled")
        
        # Validate viewport matches expectations
        await self._validate_viewport()
        
        # Initialize vision module if enabled
        if self.vision_enabled:
            await self.init_vision()
        
        # Initialize motion controller for smooth movement
        await self.init_motion_controller()
        
        # Initialize overlay renderer for visual debugging
        self.overlay = OverlayRenderer(self.cdp)
            
    async def init_vision(self):
        """Initialize YOLO vision module with streaming for instant reflexes"""
        try:
            from vision_module import VisionModule
            self.vision_module = VisionModule(
                self.cdp,
                model_path=YOLO_MODEL_PATH,
                use_ocr=USE_OCR_FALLBACK,
                model_type=VISION_MODEL_TYPE,
                inference_hz=5.0  # ChatGPT recommendation: 3-6 Hz
            )
            await self.vision_module.init_model()
            self.vision_enabled = True
            print("✓ Vision module initialized")
            
            # Initialize streaming vision for instant reflexes
            tracker = get_tracker()
            self.streaming_vision = StreamingVision(
                self.vision_module, 
                tracker,
                update_interval=0.8  # YOLO every ~800ms, predict between
            )
            await self.streaming_vision.start()
            print("✓ Streaming vision started (instant reflexes enabled)")
            
        except ImportError as e:
            print(f"✗ Vision module not available: {e}")
            self.vision_enabled = False
        except Exception as e:
            print(f"✗ Vision init failed: {e}")
            self.vision_enabled = False
    
    async def _validate_viewport(self):
        """Validate viewport matches config expectations, warn if mismatch"""
        try:
            metrics = await self.cdp.send("Page.getLayoutMetrics")
            visual = metrics.get("result", {}).get("visualViewport", {})
            actual_w = int(visual.get("clientWidth", 0))
            actual_h = int(visual.get("clientHeight", 0))
            
            if abs(actual_w - VIEWPORT_WIDTH) > 50 or abs(actual_h - VIEWPORT_HEIGHT) > 50:
                print(f"⚠️  VIEWPORT MISMATCH: Expected {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}, got {actual_w}x{actual_h}")
                print(f"   Clicks may land incorrectly. Try resizing Chrome window or relaunch.")
        except Exception as e:
            print(f"⚠️  Could not validate viewport: {e}")
    
    async def init_motion_controller(self):
        """Initialize motion controller for smooth mouse movement"""
        async def move_callback(x: float, y: float):
            """Dispatch mouse move to browser with visual cursor"""
            await self.cdp.mouse_move(x, y, update_visual=True)
        
        async def click_callback(x: float, y: float):
            """Dispatch mouse click to browser"""
            await self.click(int(x), int(y))
        
        self.motion_controller = MotionController(
            move_callback=move_callback,
            click_callback=click_callback,
            config=MotionConfig()
        )
        print("✓ Motion controller initialized")
        
    async def refresh_probes(self) -> List[Dict]:
        """Query DOM for all interactive elements"""
        js = """
        (function() {
            var results = [];
            var id = 0;
            
            var selectors = [
                'button', 'a', 'input', 'select', 'textarea',
                '[role="button"]', '[role="link"]', '[role="menuitem"]',
                '[onclick]', '[class*="btn"]'
            ].join(', ');
            
            document.querySelectorAll(selectors).forEach(function(el) {
                var rect = el.getBoundingClientRect();
                
                if (rect.width <= 0 || rect.height <= 0) return;
                if (rect.bottom < 0 || rect.top > window.innerHeight) return;
                if (rect.right < 0 || rect.left > window.innerWidth) return;
                
                var tag = el.tagName.toLowerCase();
                var text = (el.innerText || el.value || el.placeholder || 
                           el.alt || el.title || el.getAttribute('aria-label') || '').trim();
                text = text.substring(0, 50).replace(/\\n/g, ' ');
                
                var role = el.getAttribute('role') || '';
                var type = el.getAttribute('type') || '';
                
                var probeType = 'unknown';
                if (tag === 'button' || role === 'button') probeType = 'button';
                else if (tag === 'a' || role === 'link') probeType = 'link';
                else if (tag === 'input') probeType = type === 'submit' ? 'button' : 'input';
                else if (tag === 'select') probeType = 'dropdown';
                else if (tag === 'textarea') probeType = 'input';
                
                results.push({
                    id: id++,
                    type: probeType,
                    tag: tag,
                    text: text,
                    cx: Math.round(rect.left + rect.width / 2),
                    cy: Math.round(rect.top + rect.height / 2),
                    bbox: [rect.left, rect.top, rect.right, rect.bottom]
                });
            });
            
            return results;
        })()
        """
        result = await self.cdp.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        self.probes = result.get("result", {}).get("result", {}).get("value", []) or []
        
        # Update world state with DOM detections
        detections = []
        for p in self.probes:
            detections.append({
                "bbox": p.get("bbox", [0, 0, 0, 0]),
                "label": p.get("text", ""),
                "confidence": 1.0,  # DOM is high confidence
                "type": p.get("type", "unknown"),
                "tag": p.get("tag"),
                "dom_id": p.get("id")
            })
        self.world.update_from_detections(detections, ObjectSource.DOM)
        
        return self.probes
        
    async def show_probes(self, show_tabs=True):
        """Display detected elements with tab awareness"""
        # Get tab info for world state
        tab_info = ""
        if show_tabs:
            tabs = await self.get_tabs()
            current_tab = 0  # We're always on the first in list after switch
            for i, t in enumerate(tabs):
                if t.get("attached"):
                    current_tab = i
                    break
            tab_info = f" [Tab {current_tab+1}/{len(tabs)}]"
        
        print(f"\n─── {len(self.probes)} elements{tab_info} ───")
        for p in self.probes:
            text = p.get("text", "")
            ptype = p.get("type", "?")
            cx, cy = p.get("cx", 0), p.get("cy", 0)
            if text:
                print(f"  [{p['id']:2}] {ptype:8} '{text[:30]}' ({cx},{cy})")
            else:
                print(f"  [{p['id']:2}] {ptype:8} ({cx},{cy})")
        print("───────────────\n")
        
    # ================== VISION METHODS ==================
    
    async def refresh_vision_probes(self):
        """Detect elements using YOLO + DOM fusion, update world state"""
        if not self.vision_enabled or not self.vision_module:
            print("✗ Vision not enabled. Run with --vision flag")
            return []
            
        self.vision_probes = await self.vision_module.detect_labeled_probes()
        
        # Update world state with vision detections (ChatGPT gap fix)
        detections = []
        for p in self.vision_probes:
            detections.append({
                "bbox": [p.bbox[0], p.bbox[1], p.bbox[2], p.bbox[3]] if hasattr(p, 'bbox') else [0, 0, 0, 0],
                "label": p.label if hasattr(p, 'label') else "",
                "confidence": p.confidence if hasattr(p, 'confidence') else 0.5,
                "type": p.type if hasattr(p, 'type') else "unknown",
                "dom_id": p.dom_id if hasattr(p, 'dom_id') else None
            })
        self.world.update_from_detections(detections, ObjectSource.VISION)
        
        return self.vision_probes
        
    async def show_vision_probes(self, show_tabs=True):
        """Display YOLO-detected elements with labels and tab info"""
        # Get tab info for world state
        tab_info = ""
        if show_tabs:
            tabs = await self.get_tabs()
            tab_info = f" [Tab 1/{len(tabs)}]"
        
        print(f"\n─── VISION: {len(self.vision_probes)} elements{tab_info} ───")
        for p in self.vision_probes:
            label_str = f"'{p.label[:30]}'" if p.label else ""
            print(f"  [{p.id:2}] {p.type:8} {label_str:32} ({p.cx:.0f},{p.cy:.0f}) [{p.confidence:.2f}]")
        print("─────────────────────────────\n")
        
    async def vclick_text(self, query: str) -> bool:
        """Find and click element by vision label - uses streaming for instant reflexes!"""
        if not self.vision_enabled or not self.vision_module:
            print("✗ Vision not enabled. Run with --vision flag")
            return False
        
        # INSTANT PATH: Use streaming prediction if available
        if self.streaming_vision and self.streaming_vision.is_running:
            import time
            t_start = time.perf_counter()
            result = self.streaming_vision.find_by_text(query)
            t_lookup = (time.perf_counter() - t_start) * 1000
            
            if result:
                label, cx_css, cy_css = result  # Already CSS-scaled by streaming_vision
                await self.cdp.mouse_click(int(cx_css), int(cy_css))
                print(f"✓ vclick '{label}' ({cx_css:.0f}, {cy_css:.0f}) [instant: {t_lookup:.1f}ms]")
                return True
            else:
                # Element not in streaming cache - wait for next detection
                print(f"  [stream] '{query}' not cached, waiting for detection...")
                await asyncio.sleep(1.0)  # Wait for streaming to pick it up
                result = self.streaming_vision.find_by_text(query)
                if result:
                    label, cx_css, cy_css = result  # Already CSS-scaled
                    await self.cdp.mouse_click(int(cx_css), int(cy_css))
                    print(f"✓ vclick '{label}' ({cx_css:.0f}, {cy_css:.0f})")
                    return True
            
        # FALLBACK: Full detection if streaming not available
        if not self.vision_probes:
            await self.refresh_vision_probes()
            
        probe = self.vision_module.find_probe_by_label(self.vision_probes, query)
        
        if not probe:
            await self.refresh_vision_probes()
            probe = self.vision_module.find_probe_by_label(self.vision_probes, query)
            
        if probe:
            # Convert YOLO coords (screenshot space) to CSS coords for clicks
            device_scale = getattr(self.vision_module, 'device_scale', 1.0)
            cx = int(probe.cx / device_scale)
            cy = int(probe.cy / device_scale)
            await self.cdp.mouse_click(cx, cy)
            label_str = f"'{probe.label}'" if probe.label else f"({probe.type})"
            if device_scale != 1.0:
                print(f"✓ vclick {label_str} ({cx}, {cy}) [/{device_scale:.1f}x]")
            else:
                print(f"✓ vclick {label_str} ({cx}, {cy})")
            return True
            
        print(f"✗ not found: '{query}'")
        return False
        
    async def save_vision_scan(self, path: str = None):
        """Capture annotated screenshot for debugging"""
        if not self.vision_enabled or not self.vision_module:
            print("✗ Vision not enabled. Run with --vision flag")
            return
            
        # Detect probes
        probes = await self.vision_module.detect_labeled_probes()
        self.vision_probes = probes
        
        # Get annotated frame
        png_data = await self.vision_module.get_annotated_frame(probes)
        
        if png_data:
            path = path or "vision_scan.png"
            with open(path, "wb") as f:
                f.write(png_data)
            print(f"✓ Saved annotated scan to {path}")
            print(f"  Detected {len(probes)} elements")
        else:
            print("✗ Failed to capture annotated frame")
            
    # ================== END VISION METHODS ==================
        
    def find_probe(self, query: str) -> Optional[Dict]:
        """Find element by text"""
        query_lower = query.lower()
        for p in self.probes:
            if query_lower in p.get("text", "").lower():
                return p
        return None
        
    async def click(self, x: int, y: int):
        """Click at pixel coordinates"""
        await self.cdp.mouse_click(x, y)
        print(f"✓ click ({x}, {y})")
        
    async def click_text(self, query: str) -> bool:
        """Find and click element by text"""
        probe = self.find_probe(query)
        if not probe:
            await self.refresh_probes()
            probe = self.find_probe(query)
            
        if probe:
            cx, cy = probe.get("cx", 0), probe.get("cy", 0)
            await self.cdp.mouse_click(cx, cy)
            print(f"✓ click '{probe.get('text', '')[:30]}' ({cx}, {cy})")
            return True
            
        print(f"✗ not found: '{query}'")
        return False
        
    async def type_text(self, text: str):
        """Type text"""
        await self.cdp.type_text(text)
        print(f"✓ type '{text}'")
        
    async def press(self, key: str):
        """Press a key"""
        await self.cdp.press_key(key)
        print(f"✓ press '{key}'")
        
    async def goto(self, url: str):
        """Navigate to URL"""
        await self.cdp.navigate(url)
        await asyncio.sleep(2)
        await self.refresh_probes()
        print(f"✓ goto '{url}'")
        
    async def wait(self, seconds: float = 1.0):
        """Wait"""
        await asyncio.sleep(seconds)
        print(f"✓ wait {seconds}s")
        
    async def scroll(self, amount: int = 500):
        """Scroll down the page"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": f"window.scrollBy(0, {amount})"
        })
        await asyncio.sleep(0.3)
        print(f"✓ scroll {amount}px")
        
    async def scroll_up(self, amount: int = 500):
        """Scroll up the page"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": f"window.scrollBy(0, -{amount})"
        })
        await asyncio.sleep(0.3)
        print(f"✓ scroll up {amount}px")
        
    async def get_tabs(self) -> list:
        """Get all open browser tabs"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{self.cdp.host}:{self.cdp.port}/json") as resp:
                targets = await resp.json()
        tabs = [t for t in targets if t.get("type") == "page"]
        return tabs
        
    async def show_tabs(self):
        """Display all open tabs"""
        tabs = await self.get_tabs()
        print(f"\n─── {len(tabs)} tabs ───")
        for i, tab in enumerate(tabs):
            title = tab.get("title", "Untitled")[:40]
            url = tab.get("url", "")[:50]
            print(f"  [{i}] {title}")
            print(f"      {url}")
        print("───────────────\n")
        return tabs
        
    async def switch_tab(self, index: int):
        """Switch to a different tab by index"""
        tabs = await self.get_tabs()
        if 0 <= index < len(tabs):
            target = tabs[index]
            # Close current connection and connect to new tab
            await self.cdp.close()
            self.cdp = CDPClient()
            
            # Connect to specific target
            ws_url = target["webSocketDebuggerUrl"]
            import websockets
            self.cdp.ws = await websockets.connect(ws_url)
            self.cdp._listen_task = asyncio.create_task(self.cdp._listen())
            
            print(f"✓ switched to tab {index}: {target.get('title', '')[:30]}")
            await self.refresh_probes()
        else:
            print(f"✗ invalid tab index: {index}")
            
    async def new_tab(self, url: str = "about:blank"):
        """Open a new tab"""
        await self.cdp.send("Target.createTarget", {"url": url})
        await asyncio.sleep(1)
        # Switch to the new tab
        tabs = await self.get_tabs()
        if tabs:
            await self.switch_tab(len(tabs) - 1)
        print(f"✓ new tab: {url}")
        
    async def close_tab(self):
        """Close current tab"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": "window.close()"
        })
        await asyncio.sleep(0.5)
        # Switch to remaining tab
        tabs = await self.get_tabs()
        if tabs:
            await self.switch_tab(0)
        print("✓ closed tab")
        
    async def run_repl(self):
        """Interactive REPL"""
        vision_str = " + YOLO Vision" if self.vision_enabled else ""
        print(f"""
╔═══════════════════════════════════════════╗
║  xCLICK - DOM Browser Automation{vision_str:11} ║
╠═══════════════════════════════════════════╣
║ DOM Commands:                             ║
║   click <text>   - Click by text (DOM)    ║
║   click <x> <y>  - Click coordinates      ║
║   probes / p     - Show DOM elements      ║
║                                           ║
║ Vision Commands: {'(enabled)' if self.vision_enabled else '(--vision)':14}          ║
║   vprobes / vp   - Show YOLO elements     ║
║   vclick <label> - Click by vision label  ║
║   vscan          - Save debug screenshot  ║
║   timing         - Show latency stats     ║
║   vision         - Enable vision mode     ║
║   stream [cmd]   - Streaming vision ctrl  ║
║                                           ║
║ Instant Reflexes: (background streaming)  ║
║   stream status  - Show streaming status  ║
║   stream list    - List tracked elements  ║
║   stream predict - Predict element pos    ║
║                                           ║
║ Smooth Motion: (human-like movement)      ║
║   seek <text>    - Smooth move to element ║
║   smooth <text>  - Smooth move + click    ║
║                                           ║
║ Other:                                    ║
║   type <text>    - Type text              ║
║   press <key>    - Press key              ║
║   goto <url>     - Navigate               ║
║   scroll [amt]   - Scroll down            ║
║   tabs / tab <n> - Tab management         ║
║                                           ║
║ World State: (persistent tracking)        ║
║   world          - Show tracked objects   ║
║   facts          - Export UI facts (JSON) ║
║                                           ║
║ Visual Overlay: (debug rendering)         ║
║   show           - Draw boxes on page     ║
║   hide           - Clear overlay          ║
║   overlay        - Toggle overlay         ║
║                                           ║
║ ROI Filter: (negative space)              ║
║   focus [%]      - Focus center, ignore edges ║
║   noads          - Exclude ads/sidebars   ║
║   roi            - Show ROI status        ║
║   clearmask      - Clear all ROI filters  ║
║                                           ║
║   exit / q       - Quit                   ║
╚═══════════════════════════════════════════╝
""")
        
        while True:
            try:
                cmd = await asyncio.get_event_loop().run_in_executor(None, input, ">>> ")
                cmd = cmd.strip()
                
                if not cmd:
                    continue
                    
                parts = cmd.split(maxsplit=1)
                action = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""
                
                if action in ("exit", "q"):
                    break
                elif action in ("probes", "p"):
                    await self.refresh_probes()
                    await self.show_probes()
                elif action == "goto":
                    await self.goto(args)
                elif action == "click":
                    try:
                        coords = args.split()
                        if len(coords) == 2:
                            x, y = int(coords[0]), int(coords[1])
                            await self.click(x, y)
                        else:
                            await self.click_text(args)
                    except ValueError:
                        await self.click_text(args)
                elif action == "type":
                    await self.type_text(args)
                elif action == "press":
                    await self.press(args)
                elif action == "wait":
                    secs = float(args) if args else 1.0
                    await self.wait(secs)
                elif action == "scroll":
                    amt = int(args) if args else 500
                    await self.scroll(amt)
                elif action == "scrollup":
                    amt = int(args) if args else 500
                    await self.scroll_up(amt)
                elif action == "tabs":
                    await self.show_tabs()
                elif action == "tab":
                    idx = int(args) if args else 0
                    await self.switch_tab(idx)
                elif action == "newtab":
                    url = args if args else "about:blank"
                    await self.new_tab(url)
                elif action == "closetab":
                    await self.close_tab()
                # ===== VISION COMMANDS =====
                elif action in ("vprobes", "vp"):
                    await self.refresh_vision_probes()
                    await self.show_vision_probes()
                elif action == "vclick":
                    await self.vclick_text(args)
                elif action == "vscan":
                    path = args if args else None
                    await self.save_vision_scan(path)
                elif action == "timing":
                    # Show latency timing stats from last vision detection
                    if self.vision_enabled and self.vision_module:
                        if hasattr(self.vision_module, '_last_timing') and self.vision_module._last_timing:
                            t = self.vision_module._last_timing
                            print(f"\n─── LATENCY STATS ───")
                            print(f"  Viewport Capture: {t['capture_ms']:6.1f} ms")
                            print(f"  YOLO Inference:   {t['yolo_ms']:6.1f} ms")
                            print(f"  DOM Fusion:       {t['fusion_ms']:6.1f} ms")
                            print(f"  ─────────────────────────")
                            print(f"  TOTAL:            {t['total_ms']:6.1f} ms  ({t['num_detections']} elements)")
                            print(f"───────────────\n")
                        else:
                            print("✗ No timing data yet. Run 'vp' first.")
                    else:
                        print("✗ Vision not enabled. Run with --vision flag")
                elif action == "vision":
                    if not self.vision_enabled:
                        await self.init_vision()
                    else:
                        print("✓ Vision already enabled")
                # ===== STREAMING COMMANDS (instant reflexes) =====
                elif action == "stream":
                    if not self.vision_enabled:
                        print("✗ Vision not enabled. Run with --vision flag")
                    elif not self.streaming_vision:
                        print("✗ Streaming not initialized")
                    else:
                        subargs = args.split()
                        subcmd = subargs[0] if subargs else "status"
                        
                        if subcmd == "start":
                            if not self.streaming_vision.is_running:
                                await self.streaming_vision.start()
                            else:
                                print("✓ Streaming already running")
                        elif subcmd == "stop":
                            await self.streaming_vision.stop()
                        elif subcmd == "status":
                            print(f"\n─── STREAMING STATUS ───")
                            print(f"  {self.streaming_vision.status()}")
                            print(f"───────────────\n")
                        elif subcmd in ("list", "show"):
                            print(f"\n─── TRACKED ELEMENTS ───")
                            print(self.streaming_vision.list_elements())
                            print(f"───────────────\n")
                        elif subcmd == "predict":
                            # Show predicted position for a label
                            label = " ".join(subargs[1:]) if len(subargs) > 1 else ""
                            if label:
                                pos = self.streaming_vision.get_position(label)
                                if pos:
                                    print(f"  '{label}' → ({pos[0]:.0f}, {pos[1]:.0f})")
                                else:
                                    print(f"  '{label}' not found")
                            else:
                                print("  Usage: stream predict <label>")
                        else:
                            print("  Usage: stream [start|stop|status|list|predict <label>]")
                # ===== SMOOTH MOTION COMMANDS (ChatGPT recommendation) =====
                elif action == "seek":
                    # Smoothly move to element without clicking
                    if self.motion_controller:
                        await self.motion_controller.start()
                        try:
                            # Try to parse as coordinates first
                            coords = args.split()
                            try:
                                if len(coords) == 2:
                                    x, y = float(coords[0]), float(coords[1])
                                    await self.motion_controller.seek_only(x, y)
                                else:
                                    raise ValueError("Not coordinates")
                            except ValueError:
                                # Find by label in world state for continuously-updated targeting
                                obj = self.world.get_object_by_label(args)
                                if obj:
                                    obj_id = obj.id
                                    last_xy = [obj.cx, obj.cy]

                                    def provider():
                                        o = self.world.objects.get(obj_id)
                                        if o is None:
                                            return (last_xy[0], last_xy[1])
                                        x, y = o.predicted_position
                                        last_xy[0], last_xy[1] = x, y
                                        return (x, y)

                                    await self.motion_controller.seek_only_provider(provider, obj.label)
                                else:
                                    print(f"✗ not found in world: {args}")
                        finally:
                            await self.motion_controller.stop()
                        print(f"✓ seek '{args}'")
                elif action == "smooth":
                    # Smooth click with SEEK → HOVER → CLICK state machine
                    if self.motion_controller:
                        await self.motion_controller.start()
                        try:
                            # Try to parse as coordinates first
                            coords = args.split()
                            try:
                                if len(coords) == 2:
                                    x, y = float(coords[0]), float(coords[1])
                                    await self.motion_controller.seek_and_click(x, y)
                                else:
                                    raise ValueError("Not coordinates")
                            except ValueError:
                                # Find by label in world state for continuously-updated targeting
                                obj = self.world.get_object_by_label(args)
                                if obj:
                                    obj_id = obj.id
                                    last_xy = [obj.cx, obj.cy]

                                    def provider():
                                        o = self.world.objects.get(obj_id)
                                        if o is None:
                                            return (last_xy[0], last_xy[1])
                                        x, y = o.predicted_position
                                        last_xy[0], last_xy[1] = x, y
                                        return (x, y)

                                    await self.motion_controller.seek_and_click_provider(provider, obj.label)
                                else:
                                    print(f"✗ not found in world: {args}")
                        finally:
                            await self.motion_controller.stop()
                        print(f"✓ smooth click '{args}'")
                # ===== WORLD STATE COMMANDS =====
                elif action == "world":
                    # Show world state summary
                    print(f"\n─── {self.world.summary()} ───")
                    for obj in sorted(self.world.objects.values(), key=lambda x: -x.stability_score):
                        stale = f"stale:{obj.stale_ms:.0f}ms" if obj.stale_ms > 100 else "fresh"
                        print(f"  [{obj.id:3}] {obj.obj_type:8} '{obj.label[:25]:25}' "
                              f"({obj.cx:.0f},{obj.cy:.0f}) stab={obj.stability_score:.2f} {stale}")
                    print("───────────────\n")
                elif action == "facts":
                    # Export structured UI facts as JSON
                    import json
                    facts = self.world.export_facts()
                    print(f"\n─── {len(facts)} UI Facts ───")
                    for fact in facts[:10]:  # Show first 10
                        print(json.dumps(fact, indent=2))
                    if len(facts) > 10:
                        print(f"  ... and {len(facts) - 10} more")
                    print("───────────────\n")
                # ===== OVERLAY COMMANDS =====
                elif action == "show":
                    # Show overlay with current world objects
                    if self.overlay:
                        objects = [obj.to_dict() for obj in self.world.objects.values()]
                        await self.overlay.update(objects)
                        print(f"✓ Overlay showing {len(objects)} boxes")
                elif action == "hide":
                    # Hide overlay
                    if self.overlay:
                        await self.overlay.clear()
                        print("✓ Overlay hidden")
                elif action == "overlay":
                    # Toggle overlay
                    if self.overlay:
                        enabled = await self.overlay.toggle()
                        print(f"✓ Overlay {'enabled' if enabled else 'disabled'}")
                # ===== ROI MASK COMMANDS =====
                elif action == "focus":
                    # Focus on center, ignore edges
                    margin = int(args) if args else 15
                    self.roi.viewport_width = VIEWPORT_WIDTH
                    self.roi.viewport_height = VIEWPORT_HEIGHT
                    self.roi.focus_center(margin)
                    print(f"✓ Focused on center ({margin}% margin)")
                elif action == "roi":
                    # Show ROI status
                    print(f"\n─── ROI Filter: {self.roi.get_focus_summary()} ───")
                    for r in self.roi.include_regions:
                        print(f"  [INCLUDE] ({r.x1:.0f},{r.y1:.0f})-({r.x2:.0f},{r.y2:.0f}) {r.label}")
                    for r in self.roi.exclude_regions:
                        print(f"  [EXCLUDE] ({r.x1:.0f},{r.y1:.0f})-({r.x2:.0f},{r.y2:.0f}) {r.label}")
                    for r in self.roi.detected_ads:
                        print(f"  [AD] ({r.x1:.0f},{r.y1:.0f})-({r.x2:.0f},{r.y2:.0f}) {r.label}")
                    print("───────────────\n")
                elif action == "clearmask":
                    # Clear ROI mask
                    self.roi.clear()
                    print("✓ ROI mask cleared")
                elif action == "noads":
                    # Add standard ad exclusions
                    self.roi.add_standard_exclusions()
                    print("✓ Standard exclusions added (edges, sidebar)")
                # ===== PERCEPTION LOOP COMMANDS (ChatGPT Gap C) =====
                elif action == "startloop":
                    # Start continuous perception loop
                    if self.perception_loop and self.perception_loop.is_running:
                        print("✓ Perception loop already running")
                    else:
                        refresh_vision = self.refresh_vision_probes if self.vision_enabled else None
                        self.perception_loop = create_perception_loop(
                            self.refresh_probes, refresh_vision,
                            dom_hz=10.0, vision_hz=15.0
                        )
                        await self.perception_loop.start()
                elif action == "stoploop":
                    # Stop perception loop
                    if self.perception_loop and self.perception_loop.is_running:
                        await self.perception_loop.stop()
                        print("✓ Perception loop stopped")
                    else:
                        print("✗ Perception loop not running")
                elif action == "loopstat":
                    # Show perception loop status
                    if self.perception_loop:
                        print(self.perception_loop.status())
                    else:
                        print("Perception loop: NOT INITIALIZED")
                else:
                    print(f"Unknown: {action}")
                    
            except EOFError:
                break
            except Exception as e:
                print(f"✗ error: {e}")
                
    async def close(self):
        """Close connection"""
        await self.cdp.close()
        print("Disconnected.")


async def main():
    parser = argparse.ArgumentParser(description="xCLICK - DOM Browser Automation + YOLO Vision")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--vision", action="store_true", help="Enable YOLO vision mode")
    args = parser.parse_args()
    
    xclick = xClick(debug=args.debug, vision=args.vision)
    await xclick.connect()
    
    await xclick.refresh_probes()
    await xclick.show_probes()
    
    # Also show vision probes if enabled
    if xclick.vision_enabled:
        await xclick.refresh_vision_probes()
        await xclick.show_vision_probes()
    
    try:
        await xclick.run_repl()
    finally:
        await xclick.close()


if __name__ == "__main__":
    asyncio.run(main())
