"""
SIEWS+ 5.0 YOLOv8 Detector
Wrapper for YOLOv8n model: load, inference, return bounding boxes.
"""
from ultralytics import YOLO
from typing import List, Tuple
from face_manager import face_manager
import cv2
import numpy as np


class UnifiedDetector:
    """Three-stage YOLO detector: Person -> PPE -> Environment."""

    def __init__(self, confidence: float = 0.25):
        try:
            print("[DETECTOR] Initializing UnifiedDetector (3-Stage Pipeline)...")
            # Stage 1: Person detection — use standard yolov8n for reliable detection
            self.person_model = YOLO("yolov8n.pt")
            print("[DETECTOR]   Stage 1 (Person) ✓")
            # Stage 2: PPE verification — custom model
            self.ppe_model = YOLO("Model/stage2_ppe_harness.pt")
            print("[DETECTOR]   Stage 2 (PPE)    ✓")
            # Stage 3: Environment hazards — custom model
            self.env_model = YOLO("Model/stage3_environment.pt")
            print("[DETECTOR]   Stage 3 (Hazard) ✓")
            print("[DETECTOR] All 3 models loaded successfully!")
        except Exception as e:
            print(f"[DETECTOR] Error loading models: {e}")
            raise e
        self.confidence = confidence

    def detect_base(self, frame: np.ndarray) -> Tuple[List[dict], List[dict]]:
        """
        Run base inference (People and Hazards).
        """
        # 1. Detect Environment / Hazards (Fire, Smoke)
        env_results = self.env_model(frame, verbose=False, conf=self.confidence)
        hazards = []
        for r in env_results:
            if r.boxes:
                for box in r.boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    cls_id = int(box.cls[0])
                    label = self.env_model.names[cls_id]
                    hazards.append({
                        "bbox": [x1, y1, x2, y2],
                        "label": label,
                        "confidence": float(box.conf[0])
                    })

        # 2. Detect People
        person_results = self.person_model(frame, verbose=False, conf=self.confidence)
        people = []
        for r in person_results:
            if r.boxes:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    # Ensure we are catching persons (often class 0 in COCO)
                    if cls_id == 0: 
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        people.append({
                            "bbox": [x1, y1, x2, y2],
                            "confidence": float(box.conf[0]),
                            "bottom_center": [(x1 + x2) / 2, y2],
                            "center": [(x1 + x2) / 2, (y1 + y2) / 2],
                            "ppe": []
                        })
        
        if len(people) > 0 or len(hazards) > 0:
            print(f"[DETECTOR] Detected: {len(people)} people, {len(hazards)} hazards")
            
        return people, hazards

    def detect_ppe_full_frame(self, frame: np.ndarray, people: List[dict]) -> List[dict]:
        """
        Run PPE detection on FULL FRAME and match PPE items to detected persons.
        
        This is more reliable than cropping because:
        - CCTV cameras capture people at a distance
        - Cropped images are often too small for the PPE model
        
        PPE Model classes:
          0: helmet, 1: no_helmet, 2: safety_vest, 3: no_vest,
          4: safety_harness, 5: no_harness, 6: gloves, 7: boots, 8: goggles
        """
        # Aggressive Preprocessing: Sharpen the image to help the model see details better
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(frame, -1, kernel)
        
        # Run PPE model with high resolution and TTA (Test Time Augmentation)
        results = self.ppe_model(sharpened, verbose=False, conf=0.03, imgsz=1024, augment=True)
        
        # Collect all PPE detections
        ppe_items = []
        for r in results:
            if r.boxes:
                for b in r.boxes:
                    cls_id = int(b.cls[0])
                    label = self.ppe_model.names[cls_id]
                    conf = float(b.conf[0])
                    bx1, by1, bx2, by2 = b.xyxy[0].tolist()
                    cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
                    ppe_items.append({
                        "label": label,
                        "conf": conf,
                        "bbox": [bx1, by1, bx2, by2],
                        "center": [cx, cy]
                    })
        
        if ppe_items:
            labels_str = [f"{p['label']}({p['conf']:.0%})" for p in ppe_items]
            print(f"[PPE] Aggressive detect: {labels_str}")
        
        # Match PPE items to persons
        for person in people:
            px1, py1, px2, py2 = person["bbox"]
            # Extreme expansion for close up
            expand = 100 
            ex1, ey1 = px1 - expand, py1 - expand
            ex2, ey2 = px2 + expand, py2 + expand
            
            ppe_result = {
                "has_helmet": False,
                "has_vest": False,
                "has_harness": False,
                "raw_labels": []
            }
            
            for item in ppe_items:
                cx, cy = item["center"]
                # Check if PPE item center is within expanded person bbox
                if ex1 <= cx <= ex2 and ey1 <= cy <= ey2:
                    ppe_result["raw_labels"].append(f"{item['label']}({item['conf']:.0%})")
                    
                    if item["label"] == "helmet":
                        ppe_result["has_helmet"] = True
                    elif item["label"] == "safety_vest":
                        ppe_result["has_vest"] = True
                    elif item["label"] == "safety_harness":
                        ppe_result["has_harness"] = True
            
            person["ppe_result"] = ppe_result
        
        return people


class MultiStagePipeline(UnifiedDetector):
    """Alias/Wrapper for UnifiedDetector to match imports in other modules."""
    def __init__(self, confidence: float = 0.25, ppe_confidence: float = 0.25):
        super().__init__(confidence=confidence)
        # In this simplified wrapper, we use the same confidence for both
        # but the UnifiedDetector internals use self.confidence
    
    def run(self, frame: np.ndarray) -> dict:
        """Standard entry point used by stream and video processor."""
        people, hazards = self.detect_base(frame)
        if people:
            people = self.detect_ppe_full_frame(frame, people)
        
        return {
            "persons": people,
            "env": hazards
        }
