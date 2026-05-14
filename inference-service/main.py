"""
SIEWS+ Inference Service — Python YOLO Detection
Exposes YOLO detection via HTTP API for Go backend to call.
"""
import os
import json
import base64
import threading
import time
import queue
import re
from pathlib import Path
from typing import List, Dict
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from ultralytics import YOLO
import cv2
import requests
import easyocr

app = FastAPI(title="SIEWS+ Inference Service")

# Global webcam capture
webcam = None
webcam_lock = threading.Lock()
webcam_running = False

# Real-time detection settings
GO_BACKEND_URL = os.getenv("GO_BACKEND_URL", "http://localhost:8000")
REALTIME_ENABLED = False
realtime_thread = None
realtime_alerts = queue.Queue(maxsize=50)
last_alert_time = {}  # Track last alert per violation type for cooldown
ALERT_COOLDOWN = 30  # seconds between same alerts

import os
MODEL_BASE = os.environ.get("MODEL_BASE", str(Path(__file__).parent.parent))

# Model paths
MODELS_DIR = Path(MODEL_BASE) / "model" / "New"
SERVICE_DIR = Path(MODEL_BASE)

# PPE Detection threshold - standardized across all endpoints
PPE_VIOLATION_THRESHOLD = 0.35
FIRE_SMOKE_THRESHOLD = 0.40
VEHICLE_THRESHOLD = 0.40


def calculate_iou(box1, box2):
    """Calculate Intersection over Union of two boxes [x1, y1, x2, y2]."""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    # Calculate intersection
    xi1 = max(x1_1, x1_2)
    yi1 = max(y1_1, y1_2)
    xi2 = min(x2_1, x2_2)
    yi2 = min(y2_1, y2_2)

    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0

    intersection = (xi2 - xi1) * (yi2 - yi1)

    # Calculate union
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


def detect_ppe_on_image(img, persons):
    """
    Run PPE detection on full image and assign detections to persons based on IoU.

    PPE model was trained on full images with people and their PPE. Running on cropped
    person regions produces poor results because the input doesn't match training distribution.

    Instead, we run detection on the full image and assign PPE detections to persons
    based on IoU overlap.
    """
    if not persons:
        return []

    # Run PPE detection on full image with very low threshold to catch all potential PPE
    ppe_detections = []
    for r in model_s2(img, verbose=False, conf=0.01):
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            if cls_id == 0:  # Skip 'unknown' class
                continue
            cls_name = PPE_CLASSES.get(cls_id, f"cls_{cls_id}")
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            ppe_detections.append({
                "bbox": [x1, y1, x2, y2],
                "class_name": cls_name,
                "confidence": conf,
            })

    # Assign PPE detections to persons based on IoU
    for person in persons:
        person_bbox = person["bbox"]
        ppe_status = {}

        for ppe in ppe_detections:
            iou = calculate_iou(person_bbox, ppe["bbox"])
            # If PPE bbox has significant overlap with person bbox
            if iou > 0.1:
                cls_name = ppe["class_name"]
                # Keep highest confidence for each PPE type
                if cls_name not in ppe_status or ppe["confidence"] > ppe_status[cls_name]:
                    ppe_status[cls_name] = ppe["confidence"]

        person["ppe"] = ppe_status

        # Determine violations based on PPE status
        violations = []
        if ppe_status.get("helmet", 0) < PPE_VIOLATION_THRESHOLD:
            violations.append("no_helmet")
        if ppe_status.get("vest", 0) < PPE_VIOLATION_THRESHOLD:
            violations.append("no_vest")
        if "belt" not in ppe_status:
            violations.append("no_belt")

        person["violations"] = violations

    return persons


def detect_env_hazards(img):
    """Run environment plus fire/smoke detection and return one hazard list."""
    env = []
    for r in model_s3(img, verbose=False, conf=0.4):
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = ENV_CLASSES.get(cls_id, f"cls_{cls_id}")
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            env.append({
                "class_id": cls_id,
                "class_name": cls_name,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
            })

    for r in model_fire_smoke(img, verbose=False, conf=FIRE_SMOKE_THRESHOLD):
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = FIRE_SMOKE_CLASSES.get(cls_id, f"cls_{cls_id}")
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            env.append({
                "class_id": cls_id,
                "class_name": cls_name,
                "label": cls_name,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
                "category": "fire_smoke",
            })

    return env


def detect_vehicles(img, confidence=VEHICLE_THRESHOLD):
    """Run vehicle detection and return vehicle detections."""
    vehicles = []
    for r in model_vehicle(img, verbose=False, conf=confidence):
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            cls_name = VEHICLE_CLASSES.get(cls_id, f"cls_{cls_id}")
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            vehicles.append({
                "class_id": cls_id,
                "class_name": cls_name,
                "label": cls_name,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
            })
    return vehicles

# Load all models
print("[Inference] Loading models...")
print(f"  - S1 person: yolo26n.pt")
model_s1 = YOLO(SERVICE_DIR / "yolo26n.pt")
print(f"  - S2 PPE: {MODELS_DIR / 'best_stage2_labeled_safety.pt'}")
model_s2 = YOLO(MODELS_DIR / "best_stage2_labeled_safety.pt")
print(f"  - S3 openhole: {MODELS_DIR / 'best_stage3_openhole.pt'}")
model_s3 = YOLO(MODELS_DIR / "best_stage3_openhole.pt")
print(f"  - S5 jalan berlubang: {MODELS_DIR / 'best_jalan_berlubang.pt'}")
model_s5 = YOLO(MODELS_DIR / 'best_jalan_berlubang.pt')
print(f"  - Fire/smoke: {MODELS_DIR / 'fire_smoke.pt'}")
model_fire_smoke = YOLO(MODELS_DIR / "fire_smoke.pt")
print(f"  - Vehicle: {MODELS_DIR / 'vehicle_best.pt'}")
model_vehicle = YOLO(MODELS_DIR / "vehicle_best.pt")
print("[Inference] All models loaded successfully")

# Initialize EasyOCR reader
print("[Inference] Loading EasyOCR...")
reader = easyocr.Reader(['en', 'id'], gpu=False)
print("[Inference] EasyOCR loaded successfully")


OCR_ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"


def preprocess_ocr_variants(img):
    """Create contrast variants that work better for small CCTV text."""
    h, w = img.shape[:2]
    scale = min(3.0, max(1.0, 900 / max(w, 1), 500 / max(h, 1)))
    if scale > 1.05:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (0, 0), 1.0)
    sharp = cv2.addWeighted(clahe, 1.7, blur, -0.7, 0)
    binary = cv2.adaptiveThreshold(
        sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 7
    )
    return [sharp, binary, cv2.bitwise_not(binary)]


def clean_ocr_text(text):
    cleaned = text.upper().strip().replace(" ", "").replace("_", "-")
    cleaned = re.sub(r"[^A-Z0-9-]", "", cleaned)
    return re.sub(r"-{2,}", "-", cleaned).strip("-")


def ocr_code_variants(text):
    cleaned = clean_ocr_text(text)
    if len(cleaned) < 2:
        return []

    digit_fix = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8"})
    variants = [cleaned, cleaned.translate(digit_fix)]
    if "-" in cleaned:
        variants.append(cleaned.replace("-", ""))

    out = []
    for value in variants:
        if value and value not in out:
            out.append(value)
    return out


def looks_like_uniform_code(text):
    patterns = [
        r"^[A-Z]{1,3}\d{1,5}$",
        r"^[A-Z]{2,4}-\d{2,5}$",
        r"^[A-Z]{1,4}\d{1,4}[A-Z]?$",
        r"^\d{2,5}[A-Z]{1,3}$",
        r"^\d{3,8}$",
    ]
    return any(re.match(pattern, text) for pattern in patterns)


def run_optimized_ocr(img):
    best = {}
    for variant in preprocess_ocr_variants(img):
        results = reader.readtext(
            variant,
            detail=1,
            paragraph=False,
            min_size=8,
            text_threshold=0.42,
            low_text=0.25,
            link_threshold=0.25,
            decoder="beamsearch",
            beamWidth=5,
            allowlist=OCR_ALLOWLIST,
        )
        for _, text, confidence in results:
            if confidence < 0.25:
                continue
            for code in ocr_code_variants(text):
                if not looks_like_uniform_code(code):
                    continue
                score = float(confidence) + (0.15 if any(c.isalpha() for c in code) and any(c.isdigit() for c in code) else 0)
                if code not in best or score > best[code]["score"]:
                    best[code] = {"text": code, "confidence": round(float(confidence), 3), "score": round(score, 3)}

    return sorted(best.values(), key=lambda item: item["score"], reverse=True)

# ACTUAL model classes (verified from best_stage2_labeled_safety.pt):
# Class 0: unknown (no PPE / background)
# Class 1: belt
# Class 2: helmet
# Class 3: vest
PPE_CLASSES = {
    0: "unknown",   # No PPE detected / background
    1: "belt",     # Safety belt/harness
    2: "helmet",   # Helmet
    3: "vest",     # Safety vest
}
ENV_CLASSES = {0: "barricade", 1: "hard-hat", 2: "safety-cone", 3: "open-hole", 4: "vest"}
ROAD_CLASSES = {0: "lubang", 1: "retak", 2: "tambalan"}  # Model only has 3 classes
FIRE_SMOKE_CLASSES = {0: "fire", 1: "smoke"}
VEHICLE_CLASSES = {0: "Truck", 1: "coupe", 2: "hatchback", 3: "pickup", 4: "sedan", 5: "suv", 6: "truck"}


class DetectionRequest(BaseModel):
    image_b64: str  # Base64 encoded image
    stages: List[str] = ["s1", "s2", "s3", "s5", "vehicle"]  # Which stages to run


class DetectionResponse(BaseModel):
    persons: List[Dict]
    env: List[Dict]
    road: List[Dict]
    vehicles: List[Dict] = []


@app.post("/detect", response_model=DetectionResponse)
async def detect(req: DetectionRequest):
    """Run YOLO detection on base64 image."""
    try:
        # Decode image
        img_data = base64.b64decode(req.image_b64)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image data")
        
        results = {}
        
        # S1: Person detection
        if "s1" in req.stages:
            persons = []
            for r in model_s1(img, verbose=False, conf=0.5):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id == 0:  # person class
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        conf = float(box.conf[0])
                        persons.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": conf,
                        })
            results["persons"] = persons
        
        # S2: PPE detection on full image with IoU assignment
        if "s2" in req.stages and "s1" in req.stages:
            results["persons"] = detect_ppe_on_image(img, results["persons"])

        # S3: Environment detection
        if "s3" in req.stages:
            results["env"] = detect_env_hazards(img)
        
        # S5: Road damage detection
        if "s5" in req.stages:
            road = []
            for r in model_s5(img, verbose=False, conf=0.4):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = ROAD_CLASSES.get(cls_id, f"cls_{cls_id}")
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    road.append({
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2],
                    })
            results["road"] = road

        if "vehicle" in req.stages or "vehicles" in req.stages:
            results["vehicles"] = detect_vehicles(img)
        
        return DetectionResponse(
            persons=results.get("persons", []),
            env=results.get("env", []),
            road=results.get("road", []),
            vehicles=results.get("vehicles", []),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


# =============================================================================
# Webcam Streaming
# =============================================================================

def init_webcam(device_id=0):
    """Initialize webcam capture."""
    global webcam, webcam_running
    with webcam_lock:
        if webcam is not None:
            webcam.release()
        webcam = cv2.VideoCapture(device_id)
        if not webcam.isOpened():
            return False
        webcam_running = True
        return True


def release_webcam():
    """Release webcam."""
    global webcam, webcam_running
    with webcam_lock:
        webcam_running = False
        if webcam is not None:
            webcam.release()
            webcam = None


def get_webcam_frame():
    """Get current frame from webcam with YOLO detection overlay."""
    global webcam, webcam_running
    with webcam_lock:
        if webcam is None or not webcam_running:
            return None
        
        ret, frame = webcam.read()
        if not ret:
            return None
        
        # Run YOLO detection on frame
        # S1: Person detection
        persons = []
        for r in model_s1(frame, verbose=False, conf=0.5):
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id == 0:  # person
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    conf = float(box.conf[0])
                    persons.append({"bbox": [x1, y1, x2, y2], "confidence": conf})

        # S2: PPE detection on full image with IoU assignment
        persons = detect_ppe_on_image(frame, persons)

        # Draw person boxes
        for person in persons:
            x1, y1, x2, y2 = person["bbox"]
            color = (0, 0, 255) if person["violations"] else (0, 255, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"Person {person['confidence']:.2f}"
            if person["violations"]:
                label += f" - {', '.join(person['violations'])}"
            cv2.putText(frame, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # S3 + fire/smoke: Environment detection
        for det in detect_env_hazards(frame):
            x1, y1, x2, y2 = det["bbox"]
            cls_name = det.get("class_name", "")
            conf = det.get("confidence", 0)
            color = (0, 0, 255) if det.get("category") == "fire_smoke" else (255, 0, 0)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{cls_name} {conf:.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Vehicle detection
        for det in detect_vehicles(frame):
            x1, y1, x2, y2 = det["bbox"]
            cls_name = det.get("class_name", "vehicle")
            conf = det.get("confidence", 0)
            color = (255, 0, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{cls_name} {conf:.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        return frame


def generate_frames():
    """Generator for MJPEG streaming."""
    global webcam_running
    while webcam_running:
        frame = get_webcam_frame()
        if frame is None:
            # Send blank frame if no webcam
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "No Camera", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')


@app.get("/webcam/start")
def webcam_start():
    """Start webcam capture."""
    device_id = 0  # Default webcam
    if init_webcam(device_id):
        return {"status": "started", "device": device_id}
    return {"status": "error", "message": "Failed to open webcam"}


@app.get("/webcam/stop")
def webcam_stop():
    """Stop webcam capture."""
    release_webcam()
    return {"status": "stopped"}


@app.get("/webcam/frame")
def webcam_frame():
    """Get single frame with detection."""
    frame = get_webcam_frame()
    if frame is None:
        return {"error": "No webcam available"}
    
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return {"error": "Failed to encode frame"}
    
    return {"image": base64.b64encode(buffer).decode('utf-8')}


@app.get("/stream")
def stream():
    """MJPEG streaming endpoint."""
    global webcam_running
    return StreamingResponse(generate_frames(), media_type='multipart/x-mixed-replace; boundary=frame')


@app.post("/analyze/image")
async def analyze_image(req: DetectionRequest):
    """Analyze image and return annotated image with detections - matches Python backend format."""
    try:
        # Decode image
        img_data = base64.b64decode(req.image_b64)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image data")
        
        results = {}
        h, w = img.shape[:2]
        
        # S1: Person detection
        if "s1" in req.stages:
            persons = []
            for r in model_s1(img, verbose=False, conf=0.5):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id == 0:  # person class
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        conf = float(box.conf[0])
                        persons.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": conf,
                        })
            results["persons"] = persons
        
        # S2: PPE detection on full image with IoU assignment
        if "s2" in req.stages and "s1" in req.stages:
            results["persons"] = detect_ppe_on_image(img, results["persons"])

        # S3: Environment detection
        if "s3" in req.stages:
            results["env"] = detect_env_hazards(img)
        
        # S5: Road damage detection
        if "s5" in req.stages:
            road = []
            for r in model_s5(img, verbose=False, conf=0.4):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = ROAD_CLASSES.get(cls_id, f"cls_{cls_id}")
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    road.append({
                        "class_id": cls_id,
                        "class_name": cls_name,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2],
                    })
            results["road"] = road

        if "vehicle" in req.stages or "vehicles" in req.stages:
            results["vehicles"] = detect_vehicles(img)
        
        # Draw detections on image
        annotated = img.copy()
        
        # Draw persons with labels
        for person in results.get("persons", []):
            x1, y1, x2, y2 = person["bbox"]
            violations = person.get("ppe_violations", [])
            color = (0, 255, 0) if len(violations) == 0 else (0, 0, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"Person {person.get('confidence', 0):.2f}"
            if violations:
                label += f" - {', '.join(violations)}"
            cv2.putText(annotated, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw environment with labels
        for det in results.get("env", []):
            x1, y1, x2, y2 = det["bbox"]
            cls = det.get("class_name", "")
            color = (255, 165, 0) if cls != "open-hole" else (0, 0, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, f"{cls} {det.get('confidence', 0):.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Draw road damage with labels
        for det in results.get("road", []):
            x1, y1, x2, y2 = det["bbox"]
            cls = det.get("class_name", "")
            if cls == "lubang":
                color = (255, 0, 0)
            elif cls == "retak":
                color = (0, 165, 255)
            else:
                color = (0, 255, 0)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, f"{cls} {det.get('confidence', 0):.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw vehicles with labels
        for det in results.get("vehicles", []):
            x1, y1, x2, y2 = det["bbox"]
            cls = det.get("class_name", "vehicle")
            color = (255, 0, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated, f"{cls} {det.get('confidence', 0):.2f}", (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Encode annotated image
        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
        annotated_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
        
        # Build detection summary matching Python backend format
        person_list = [
            {
                "bbox": p.get("bbox", []),
                "confidence": round(p.get("confidence", 0), 3),
                "violations": p.get("ppe_violations", []),
                "ppe_status": p.get("ppe", {}),
            }
            for p in results.get("persons", [])
        ]
        
        env_list = [
            {
                "label": e.get("class_name", e.get("label", "")),
                "confidence": round(e.get("confidence", 0), 3),
                "bbox": e.get("bbox", []),
            }
            for e in results.get("env", [])
        ]
        
        road_list = [
            {
                "label": r.get("class_name", ""),
                "confidence": round(r.get("confidence", 0), 3),
                "bbox": r.get("bbox", []),
            }
            for r in results.get("road", [])
        ]

        vehicle_list = [
            {
                "label": v.get("class_name", v.get("label", "")),
                "confidence": round(v.get("confidence", 0), 3),
                "bbox": v.get("bbox", []),
                "class_id": v.get("class_id"),
            }
            for v in results.get("vehicles", [])
        ]
        
        violation_indices = {i for i, p in enumerate(results.get("persons", [])) if p.get("ppe_violations")}
        
        return {
            "annotated_image": f"data:image/jpeg;base64,{annotated_b64}",
            "image_size": {"width": w, "height": h},
            "detections": {
                "persons": person_list,
                "env": env_list,
                "road": road_list,
                "vehicles": vehicle_list,
                "total_persons": len(person_list),
                "total_env": len(env_list),
                "total_road": len(road_list),
                "total_vehicles": len(vehicle_list),
                "violations_found": bool(violation_indices),
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")


@app.post("/ocr")
async def ocr_text(req: DetectionRequest):
    """Extract text from image using EasyOCR."""
    try:
        # Decode image
        img_data = base64.b64decode(req.image_b64)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            raise HTTPException(status_code=400, detail="Invalid image data")
        
        results = run_optimized_ocr(img)
        extracted_text = " ".join(item["text"] for item in results)

        return {"text": extracted_text, "results": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR error: {str(e)}")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "models_loaded": True,
        "ocr_loaded": True
    }


# =============================================================================
# Real-time Detection & Alert Broadcasting
# =============================================================================

def start_realtime_detection():
    """Start background thread for continuous detection."""
    global REALTIME_ENABLED, realtime_thread
    if REALTIME_ENABLED:
        return {"status": "already_running"}
    
    REALTIME_ENABLED = True
    realtime_thread = threading.Thread(target=realtime_detection_loop, daemon=True)
    realtime_thread.start()
    return {"status": "started"}


def stop_realtime_detection():
    """Stop background detection."""
    global REALTIME_ENABLED
    REALTIME_ENABLED = False
    return {"status": "stopped"}


def realtime_detection_loop():
    """Continuous detection loop - checks webcam frames and sends alerts."""
    global webcam, webcam_running, last_alert_time
    
    print("[REALTIME] Starting continuous detection loop...")
    
    while REALTIME_ENABLED:
        time.sleep(1)  # Check every second
        
        with webcam_lock:
            if webcam is None or not webcam_running:
                continue
            
            ret, frame = webcam.read()
            if not ret:
                continue

        fire_smoke_hazards = [
            h for h in detect_env_hazards(frame)
            if h.get("category") == "fire_smoke"
        ]
        if fire_smoke_hazards:
            labels = sorted({h.get("class_name", "fire_smoke") for h in fire_smoke_hazards})
            alert_key = "fire_smoke_" + "_".join(labels)
            current_time = time.time()
            if alert_key not in last_alert_time or (current_time - last_alert_time[alert_key]) > ALERT_COOLDOWN:
                last_alert_time[alert_key] = current_time
                send_hazard_alert_to_backend(fire_smoke_hazards, frame)
        
        # Run S1 person detection
        persons = []
        for r in model_s1(frame, verbose=False, conf=0.5):
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id == 0:
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    conf = float(box.conf[0])
                    persons.append({"bbox": [x1, y1, x2, y2], "confidence": conf})

        # Check for violations
        if not persons:
            continue

        # S2: PPE detection on full image with IoU assignment
        persons = detect_ppe_on_image(frame, persons)

        # Collect all violations from all persons
        violations_found = []
        for person in persons:
            if person.get("violations"):
                violations_found.extend(person["violations"])

        # Send alert if violations found (with cooldown)
        if violations_found:
            alert_key = f"person_violation_{len(persons)}"
            current_time = time.time()
            
            if alert_key not in last_alert_time or (current_time - last_alert_time[alert_key]) > ALERT_COOLDOWN:
                last_alert_time[alert_key] = current_time
                send_alert_to_backend(persons, violations_found, frame)


def send_alert_to_backend(persons, violations, frame):
    """Send alert to Go backend via HTTP POST."""
    try:
        # Create snapshot
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        snapshot_b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        
        alert_data = {
            "type": "alert",
            "alert_id": int(time.time() * 1000),
            "zone_id": 0,  # Default zone - frontend should handle zone matching
            "zone_name": "Monitoring Area",
            "risk_level": "high" if "no_helmet" in violations else "medium",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "confidence": max(p.get("confidence", 0) for p in persons),
            "snapshot_url": f"data:image/jpeg;base64,{snapshot_b64}",
            "shutdown_triggered": False,
            "persons_count": len(persons),
            "violation_type": ",".join(violations),
            "ppe_detail": persons[0].get("ppe", {}) if persons else {},
        }
        
        # Send to Go backend
        response = requests.post(
            f"{GO_BACKEND_URL}/api/alerts",
            json=alert_data,
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"[REALTIME] Alert sent: {len(persons)} persons with violations: {violations}")
        else:
            print(f"[REALTIME] Alert failed: {response.status_code}")
            
    except Exception as e:
        print(f"[REALTIME] Failed to send alert: {e}")


def send_hazard_alert_to_backend(hazards, frame):
    """Send direct fire/smoke hazard alert to Go backend via HTTP POST."""
    try:
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        snapshot_b64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
        labels = sorted({h.get("class_name", "fire_smoke") for h in hazards})

        alert_data = {
            "type": "alert",
            "alert_id": int(time.time() * 1000),
            "zone_id": 998,
            "zone_name": "Fire/Smoke Detected",
            "risk_level": "high",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "confidence": max(h.get("confidence", 0) for h in hazards),
            "snapshot_url": f"data:image/jpeg;base64,{snapshot_b64}",
            "shutdown_triggered": True,
            "persons_count": 0,
            "violation_type": "fire_smoke",
            "ppe_detail": {"hazards": labels},
        }

        response = requests.post(
            f"{GO_BACKEND_URL}/api/alerts",
            json=alert_data,
            timeout=5
        )

        if response.status_code == 200:
            print(f"[REALTIME] Fire/smoke alert sent: {labels}")
        else:
            print(f"[REALTIME] Fire/smoke alert failed: {response.status_code}")

    except Exception as e:
        print(f"[REALTIME] Failed to send fire/smoke alert: {e}")


@app.get("/realtime/status")
def realtime_status():
    """Get real-time detection status."""
    return {
        "enabled": REALTIME_ENABLED,
        "websocket_connected": True,
        "last_alerts": list(realtime_alerts.queue) if not realtime_alerts.empty() else []
    }


@app.post("/realtime/start")
def realtime_start():
    """Start real-time detection."""
    return start_realtime_detection()


@app.post("/realtime/stop")
def realtime_stop():
    """Stop real-time detection."""
    return stop_realtime_detection()


@app.get("/realtime/alerts")
def get_realtime_alerts():
    """Get recent real-time alerts from queue."""
    alerts = []
    while not realtime_alerts.empty():
        try:
            alerts.append(realtime_alerts.get_nowait())
        except:
            break
    return {"alerts": alerts, "count": len(alerts)}


# =============================================================================
# Audio Processing - MP4A Support
# =============================================================================

@app.post("/audio/analyze")
async def analyze_audio(request: Request):
    """
    Analyze audio file for sound detection.
    Supports: MP4A, MP3, WAV, OGG, M4A formats.
    """
    try:
        data = await request.json()
        audio_b64 = data.get("audio", "")
        format_type = data.get("format", "m4a").lower()
        
        if not audio_b64:
            raise HTTPException(status_code=400, detail="No audio provided")
        
        # Decode audio
        audio_data = base64.b64decode(audio_b64)
        
        # Save temp file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format_type}") as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent
            
            # Load audio file
            audio = AudioSegment.from_file(tmp_path)
            
            # Audio properties
            duration_ms = len(audio)
            duration_sec = duration_ms / 1000
            channels = audio.channels
            sample_rate = audio.frame_rate
            max_dbfs = audio.max_dBFS
            
            # Detect non-silent segments
            min_silence_len = 500  # ms
            silence_thresh = audio.dBFS - 16
            nonsilent_ranges = detect_nonsilent(audio, min_silence_len=min_silence_len, silence_thresh=silence_thresh)
            
            # Calculate loudness statistics
            avg_dbfs = audio.dBFS
            rms = audio.rms
            
            # Simple sound classification based on characteristics
            sound_events = []
            for start, end in nonsilent_ranges:
                seg_duration = (end - start) / 1000  # Convert to seconds
                seg_audio = audio[start:end]
                seg_dbfs = seg_audio.dBFS
                
                # Classify sound type
                if seg_dbfs > -6:
                    sound_type = "very_loud"  # Explosion, alarm, machinery
                elif seg_dbfs > -12:
                    sound_type = "loud"  # Voice, shouting
                elif seg_dbfs > -24:
                    sound_type = "moderate"  # Normal speech, activity
                else:
                    sound_type = "quiet"  # Background noise
                
                sound_events.append({
                    "start_ms": start,
                    "end_ms": end,
                    "duration_sec": round(seg_duration, 2),
                    "loudness_dbfs": round(seg_dbfs, 2),
                    "type": sound_type
                })
            
            # Alert detection - very loud sounds
            alert_sounds = [e for e in sound_events if e["type"] in ["very_loud", "loud"]]
            
            return {
                "audio_info": {
                    "duration_sec": round(duration_sec, 2),
                    "channels": channels,
                    "sample_rate": sample_rate,
                    "max_dbfs": round(max_dbfs, 2),
                    "avg_dbfs": round(avg_dbfs, 2),
                    "format": format_type
                },
                "sound_events": sound_events,
                "alert_sounds": alert_sounds,
                "alert_count": len(alert_sounds),
                "is_alert": len(alert_sounds) > 0
            }
            
        finally:
            os.unlink(tmp_path)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio analysis error: {str(e)}")


@app.post("/audio/classify")
async def classify_audio(request: Request):
    """
    Classify audio clip type.
    Returns classification for safety monitoring.
    """
    try:
        data = await request.json()
        audio_b64 = data.get("audio", "")
        format_type = data.get("format", "m4a").lower()
        
        if not audio_b64:
            raise HTTPException(status_code=400, detail="No audio provided")
        
        audio_data = base64.b64decode(audio_b64)
        
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{format_type}") as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            from pydub import AudioSegment
            
            audio = AudioSegment.from_file(tmp_path)
            
            # Extract features
            duration = len(audio) / 1000
            max_dbfs = audio.max_dBFS
            avg_dbfs = audio.dBFS
            rms = audio.rms
            tempo_estimate = audio.frame_rate / (audio.frame_count() / duration) if duration > 0 else 0
            
            # Simple classification rules for safety monitoring
            classifications = {
                "alarm": {"detected": max_dbfs > -3 and duration < 10, "confidence": min(1.0, (max_dbfs + 60) / 60)},
                "shouting": {"detected": avg_dbfs > -15 and duration < 5, "confidence": min(1.0, (avg_dbfs + 60) / 45)},
                "machinery": {"detected": rms > 5000 and duration > 3, "confidence": min(1.0, rms / 20000)},
                "explosion": {"detected": max_dbfs > 0, "confidence": min(1.0, (max_dbfs + 60) / 60)},
                "ambient": {"detected": avg_dbfs < -30, "confidence": min(1.0, (-30 - avg_dbfs) / 30)},
                "silence": {"detected": max_dbfs < -50, "confidence": min(1.0, (-50 - max_dbfs) / 30)}
            }
            
            # Filter detected classifications
            detected = {k: v for k, v in classifications.items() if v["detected"]}
            
            return {
                "audio_features": {
                    "duration_sec": round(duration, 2),
                    "max_dbfs": round(max_dbfs, 2),
                    "avg_dbfs": round(avg_dbfs, 2),
                    "rms": round(rms, 2),
                    "format": format_type
                },
                "classifications": detected,
                "primary_class": max(detected.keys(), key=lambda k: detected[k]["confidence"]) if detected else "unknown"
            }
            
        finally:
            os.unlink(tmp_path)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audio classification error: {str(e)}")


@app.get("/audio/formats")
def get_audio_formats():
    """Get supported audio formats."""
    return {
        "supported_formats": ["mp4a", "mp3", "wav", "ogg", "m4a", "aac", "flac"],
        "mime_types": {
            "mp4a": "audio/mp4",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "ogg": "audio/ogg",
            "m4a": "audio/mp4",
            "aac": "audio/aac",
            "flac": "audio/flac"
        },
        "max_duration_sec": 300,
        "recommended_bitrate": "128kbps"
    }


# =============================================================================
# Video Processing
# =============================================================================

@app.post("/video/analyze")
async def analyze_video(request: Request):
    """
    Analyze video file frame by frame.
    Returns detections for each processed frame.
    """
    try:
        data = await request.json()
        video_path = data.get("video_path", "")
        frame_interval = data.get("frame_interval", 5)  # Process every Nth frame
        max_frames = data.get("max_frames", 1000)  # Limit processing
        
        if not video_path:
            raise HTTPException(status_code=400, detail="No video path provided")
        
        if not os.path.exists(video_path):
            raise HTTPException(status_code=400, detail=f"Video file not found: {video_path}")
        
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot open video file")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        frame_results = []
        frame_idx = 0
        processed = 0
        
        while processed < max_frames:
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            
            # Only process every Nth frame
            if frame_idx % frame_interval != 0:
                continue
            
            # Run detection on frame
            # S1: Person detection
            persons = []
            for r in model_s1(frame, verbose=False, conf=0.5):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id == 0:  # person class
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        conf = float(box.conf[0])
                        persons.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": round(conf, 3),
                        })

            # S2: PPE detection on full image with IoU assignment
            persons = detect_ppe_on_image(frame, persons)

            # Convert violations to ppe_violations format for backward compatibility
            for person in persons:
                person["ppe_violations"] = person.get("violations", [])

            # S3: Environment detection
            env = [
                {
                    "class_name": d.get("class_name", d.get("label", "")),
                    "confidence": round(d.get("confidence", 0), 3),
                    "bbox": d.get("bbox", []),
                    "category": d.get("category"),
                }
                for d in detect_env_hazards(frame)
            ]
            
            # S5: Road damage detection
            road = []
            for r in model_s5(frame, verbose=False, conf=0.4):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = ROAD_CLASSES.get(cls_id, f"cls_{cls_id}")
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                    road.append({
                        "class_name": cls_name,
                        "confidence": round(conf, 3),
                        "bbox": [x1, y1, x2, y2],
                    })
            
            timestamp_sec = frame_idx / fps
            has_violation = any(p.get("ppe_violations") for p in persons) or len(env) > 0 or len(road) > 0
            
            frame_results.append({
                "frame": frame_idx,
                "timestamp_sec": round(timestamp_sec, 2),
                "persons": persons,
                "env": env,
                "road": road,
                "has_violation": has_violation,
            })
            processed += 1
        
        cap.release()
        
        return {
            "video_info": {
                "total_frames": total_frames,
                "fps": round(fps, 2),
                "width": width,
                "height": height,
                "processed_frames": processed,
            },
            "frames": frame_results,
            "summary": {
                "total_violation_frames": sum(1 for f in frame_results if f["has_violation"]),
                "total_persons_detected": sum(len(f["persons"]) for f in frame_results),
                "total_env_hazards": sum(len(f["env"]) for f in frame_results),
                "total_road_damage": sum(len(f["road"]) for f in frame_results),
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video analysis error: {str(e)}")


@app.post("/video/progress")
async def video_progress(request: Request):
    """
    Process video in chunks and return progress.
    This endpoint is designed to be called repeatedly for long videos.
    """
    try:
        data = await request.json()
        video_path = data.get("video_path", "")
        job_id = data.get("job_id", 0)
        start_frame = data.get("start_frame", 0)
        end_frame = data.get("end_frame", 100)  # Process up to this frame
        frame_interval = data.get("frame_interval", 5)
        
        if not video_path:
            raise HTTPException(status_code=400, detail="No video path provided")
        
        if not os.path.exists(video_path):
            raise HTTPException(status_code=400, detail=f"Video file not found: {video_path}")
        
        import cv2
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise HTTPException(status_code=400, detail="Cannot open video file")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        
        frame_results = []
        frame_idx = 0
        processed = 0
        
        while processed < (end_frame - start_frame):
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_idx += 1
            
            if frame_idx < start_frame:
                continue
            
            if frame_idx > end_frame:
                break
            
            # Only process every Nth frame
            if frame_idx % frame_interval != 0:
                continue
            
            # Run detection
            persons = []
            for r in model_s1(frame, verbose=False, conf=0.5):
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id == 0:
                        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                        conf = float(box.conf[0])
                        persons.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": round(conf, 3),
                        })

            # S2: PPE detection on full image with IoU assignment
            persons = detect_ppe_on_image(frame, persons)

            # Convert violations to ppe_violations format for backward compatibility
            for person in persons:
                person["ppe_violations"] = person.get("violations", [])

            env = [
                {
                    "class_name": d.get("class_name", d.get("label", "")),
                    "confidence": round(d.get("confidence", 0), 3),
                    "bbox": d.get("bbox", []),
                    "category": d.get("category"),
                }
                for d in detect_env_hazards(frame)
            ]
            
            timestamp_sec = frame_idx / fps
            has_violation = any(p.get("ppe_violations") for p in persons) or len(env) > 0
            
            frame_results.append({
                "frame": frame_idx,
                "timestamp_sec": round(timestamp_sec, 2),
                "persons": persons,
                "env": env,
                "has_violation": has_violation,
            })
            processed += 1
        
        cap.release()
        
        progress_pct = min(100, int((frame_idx / max(total_frames, 1)) * 100))
        
        return {
            "job_id": job_id,
            "status": "processing" if frame_idx < total_frames else "done",
            "progress": progress_pct,
            "current_frame": frame_idx,
            "total_frames": total_frames,
            "processed_frames": processed,
            "frames": frame_results,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video progress error: {str(e)}")


@app.get("/video/info")
def get_video_info(video_path: str):
    """Get video file information."""
    import cv2
    
    if not os.path.exists(video_path):
        raise HTTPException(status_code=400, detail="Video file not found")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise HTTPException(status_code=400, detail="Cannot open video file")
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_sec = total_frames / fps if fps > 0 else 0
    
    cap.release()
    
    return {
        "video_path": video_path,
        "total_frames": total_frames,
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "duration_sec": round(duration_sec, 2),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
