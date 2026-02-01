"""
xCLICK Live Overlay - Visual debug overlay showing detected elements
Renders bounding boxes, labels, and cursor position directly on the page
"""

# JavaScript for creating and updating the overlay
OVERLAY_INIT_JS = """
(function() {
    // Remove existing overlay
    var old = document.getElementById('__xclick_overlay__');
    if (old) old.remove();
    
    // Create overlay container
    var overlay = document.createElement('div');
    overlay.id = '__xclick_overlay__';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 999990;
    `;
    
    // Create SVG for drawing boxes
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = '__xclick_svg__';
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
    `;
    overlay.appendChild(svg);
    
    // Create labels container
    var labels = document.createElement('div');
    labels.id = '__xclick_labels__';
    labels.style.cssText = `
        position: absolute;
        top: 0;
        left: 0;
    `;
    overlay.appendChild(labels);
    
    document.body.appendChild(overlay);
    
    // Store reference
    window.__xclick_overlay = {
        container: overlay,
        svg: svg,
        labels: labels
    };
    
    return true;
})();
"""

def generate_update_js(objects: list, show_labels: bool = True) -> str:
    """Generate JavaScript to update overlay with detected objects"""
    
    # Build box and label HTML
    boxes_svg = []
    labels_html = []
    
    for i, obj in enumerate(objects):
        bbox = obj.get("bbox", [0, 0, 0, 0])
        label = obj.get("label", "")[:20]
        obj_type = obj.get("type", "unknown")
        confidence = obj.get("confidence", 0)
        source = obj.get("source", "dom")
        
        x1, y1, x2, y2 = bbox
        width = x2 - x1
        height = y2 - y1
        
        # Color based on source
        if source == "vision":
            color = "#00ff00"  # Green for vision
        elif source == "fused":
            color = "#ffff00"  # Yellow for fused
        else:
            color = "#00ffff"  # Cyan for DOM
        
        # Opacity based on confidence
        opacity = max(0.3, min(0.9, confidence))
        
        # SVG rectangle
        boxes_svg.append(f'''
            <rect x="{x1}" y="{y1}" width="{width}" height="{height}" 
                  fill="none" stroke="{color}" stroke-width="2" 
                  stroke-opacity="{opacity}" />
        ''')
        
        # Label
        if show_labels and label:
            labels_html.append(f'''
                <div style="
                    position: absolute;
                    left: {x1}px;
                    top: {max(0, y1 - 18)}px;
                    background: {color};
                    color: #000;
                    font-size: 10px;
                    font-family: monospace;
                    padding: 1px 4px;
                    border-radius: 2px;
                    white-space: nowrap;
                    opacity: {opacity};
                ">{obj_type}: {label}</div>
            ''')
    
    boxes_svg_str = "".join(boxes_svg).replace("\n", " ").replace("'", "\\'")
    labels_html_str = "".join(labels_html).replace("\n", " ").replace("'", "\\'")
    
    return f"""
    (function() {{
        var overlay = window.__xclick_overlay;
        if (!overlay) return false;
        
        overlay.svg.innerHTML = '{boxes_svg_str}';
        overlay.labels.innerHTML = '{labels_html_str}';
        
        return true;
    }})();
    """


def generate_clear_js() -> str:
    """Generate JavaScript to clear the overlay"""
    return """
    (function() {
        var overlay = window.__xclick_overlay;
        if (overlay) {
            overlay.svg.innerHTML = '';
            overlay.labels.innerHTML = '';
        }
        return true;
    })();
    """


def generate_remove_js() -> str:
    """Generate JavaScript to remove the overlay completely"""
    return """
    (function() {
        var overlay = document.getElementById('__xclick_overlay__');
        if (overlay) overlay.remove();
        window.__xclick_overlay = null;
        return true;
    })();
    """


class OverlayRenderer:
    """Manages live overlay rendering on the page"""
    
    def __init__(self, cdp_client):
        self.cdp = cdp_client
        self.enabled = False
        self.show_labels = True
    
    async def init(self):
        """Initialize the overlay on the page"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": OVERLAY_INIT_JS
        })
        self.enabled = True
        print("✓ Overlay initialized")
    
    async def update(self, objects: list):
        """Update overlay with current detected objects"""
        if not self.enabled:
            await self.init()
        
        js = generate_update_js(objects, self.show_labels)
        await self.cdp.send("Runtime.evaluate", {
            "expression": js
        })
    
    async def clear(self):
        """Clear all boxes from overlay"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": generate_clear_js()
        })
    
    async def remove(self):
        """Remove overlay from page"""
        await self.cdp.send("Runtime.evaluate", {
            "expression": generate_remove_js()
        })
        self.enabled = False
        print("✓ Overlay removed")
    
    async def toggle(self):
        """Toggle overlay on/off"""
        if self.enabled:
            await self.remove()
        else:
            await self.init()
        return self.enabled
    
    async def toggle_labels(self):
        """Toggle label display"""
        self.show_labels = not self.show_labels
        return self.show_labels
