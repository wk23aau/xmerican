"""Generate probes debug visualization"""
import json
import cv2
import numpy as np
from PIL import Image

# Load screenshot
img = cv2.imread("output/screenshot.png")
h, w = img.shape[:2]

# Load probes
with open("output/yolo_probes.json", "r") as f:
    data = json.load(f)

probes = data.get("probes", [])
viewport = data.get("viewport", [w, h])

print(f"Viewport: {viewport}")
print(f"Image size: {w}x{h}")
print(f"Probes: {len(probes)}")

# Draw each probe
for probe in probes:
    bbox = probe.get("bbox", [0, 0, 0, 0])
    text = probe.get("text", "")
    ptype = probe.get("type", "unknown")
    
    # Convert normalized bbox to pixels
    x1 = int(bbox[0] * w)
    y1 = int(bbox[1] * h)
    x2 = int(bbox[2] * w)
    y2 = int(bbox[3] * h)
    
    # Color by type
    if ptype == "button":
        color = (0, 255, 0)  # Green
    elif ptype == "link":
        color = (255, 0, 0)  # Blue
    elif ptype == "input":
        color = (0, 255, 255)  # Yellow
    else:
        color = (200, 200, 200)  # Gray
    
    # Draw bounding box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
    
    # Draw label
    label = text[:15] if text else ptype
    cv2.putText(img, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

# Save debug image
cv2.imwrite("output/probes.png", img)
print(f"Saved to output/probes.png")
