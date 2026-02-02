"""
Test YOLO detection on 1280x720 screenshot
Verifies coordinates match CSS viewport 1:1
"""
import urllib.request
import json
import asyncio
import websockets
import base64
from PIL import Image, ImageDraw
import io
import os

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720

# Same model as vision_module.py
HF_REPO = "macpaw-research/yolov11l-ui-elements-detection"
HF_FILE = "ui-elements-detection.pt"

async def capture_screenshot():
    """Capture and resize to 1280x720"""
    data = json.loads(urllib.request.urlopen("http://localhost:9222/json").read())
    ws_url = data[0]["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({
            "id": 1,
            "method": "Page.captureScreenshot",
            "params": {"format": "png"}
        }))
        r = json.loads(await ws.recv())
        img_data = base64.b64decode(r["result"]["data"])
        
        img = Image.open(io.BytesIO(img_data))
        original_size = f"{img.width}x{img.height}"
        img_resized = img.resize((VIEWPORT_WIDTH, VIEWPORT_HEIGHT), Image.LANCZOS)
        return img_resized, original_size

def download_model():
    """Download model from HuggingFace"""
    from huggingface_hub import hf_hub_download
    
    cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    print(f"Downloading model from {HF_REPO}...")
    model_path = hf_hub_download(
        repo_id=HF_REPO,
        filename=HF_FILE,
        cache_dir=cache_dir
    )
    return model_path

def run_yolo(img):
    """Run YOLO detection on image"""
    from ultralytics import YOLO
    
    # Save temp image for YOLO
    img.save("viewport/temp.png")
    
    # Download and load model
    model_path = download_model()
    print(f"Loading model from {model_path}")
    model = YOLO(model_path)
    
    # Run detection
    print("Running detection...")
    results = model.predict("viewport/temp.png", conf=0.25, verbose=False)
    
    detections = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            conf = box.conf[0].item()
            cls = int(box.cls[0].item())
            label = r.names[cls]
            detections.append({
                "label": label,
                "cx": cx,
                "cy": cy,
                "bbox": (x1, y1, x2, y2),
                "conf": conf
            })
    
    return detections

def draw_detections(img, detections):
    """Draw boxes on image"""
    draw = ImageDraw.Draw(img)
    
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        cx, cy = det["cx"], det["cy"]
        
        # Draw box
        draw.rectangle([x1, y1, x2, y2], outline="lime", width=2)
        
        # Draw center
        draw.ellipse([cx-3, cy-3, cx+3, cy+3], fill="red")
        
        # Draw label
        label = f"{det['label']} ({cx:.0f},{cy:.0f})"
        draw.text((x1, y1-12), label, fill="lime")
    
    return img

async def main():
    print(f"=== YOLO TEST @ {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT} ===\n")
    
    # Capture
    img, original_size = await capture_screenshot()
    print(f"Screenshot: {original_size} → resized to {img.width}x{img.height}")
    
    # YOLO
    detections = run_yolo(img)
    
    print(f"\n=== DETECTIONS ({len(detections)}) ===")
    print(f"Image: {img.width}x{img.height}")
    print("-" * 50)
    for det in sorted(detections, key=lambda x: -x["conf"])[:15]:
        print(f"  {det['label']:15} ({det['cx']:6.1f}, {det['cy']:6.1f})  conf={det['conf']:.2f}")
    print("-" * 50)
    
    # Draw and save
    annotated = draw_detections(img.copy(), detections)
    annotated.save("viewport/yolo_test.png")
    print(f"\nSaved: viewport/yolo_test.png")

if __name__ == "__main__":
    asyncio.run(main())
