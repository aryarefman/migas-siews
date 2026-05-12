"""
SIEWS+ 5.0 YOLOv8 Detector
Clean multi-stage pipeline: Person -> PPE -> Environment -> Road -> Safety Cones
"""
import os
import numpy as np
from typing import List, Tuple
from ultralytics import YOLO

from detection_models import (
    PPE_CONFIDENCE_THRESHOLD,
    SAFETY_CONE_CONFIDENCE,
    PPE_IOU_THRESHOLD,
    VIOLATION_NO_HELMET,
    VIOLATION_NO_VEST,
    VIOLATION_NO_BELT,
)


def calculate_iou(box1: List[float], box2: List[float]) -> float:
    """Calculate Intersection over Union of two boxes [x1, y1, x2, y2]."""
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    xi1 = max(x1_1, x1_2)
    yi1 = max(y1_1, y1_2)
    xi2 = min(x2_1, x2_2)
    yi2 = min(y2_1, y2_2)

    if xi2 <= xi1 or yi2 <= yi1:
        return 0.0

    intersection = (xi2 - xi1) * (yi2 - yi1)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


class UnifiedDetector:
    """
    Four-stage YOLO detector: Person -> PPE -> Environment -> Road Damage.

    Stage 1: Person detection (yolov8n.pt / yolo26n.pt)
    Stage 2: PPE verification (best_stage2_labeled_safety.pt - 4 classes)
    Stage 3: Environment hazards (best_stage3_openhole.pt)
    Stage 4: Road damage (best_jalan_berlubang.pt)
    """

    # PPE Classes (Stage 2)
    # Class 0: unknown (no PPE / background)
    # Class 1: belt
    # Class 2: helmet
    # Class 3: vest
    PPE_CLASSES = {0: "unknown", 1: "belt", 2: "helmet", 3: "vest"}

    def __init__(self, confidence: float = 0.25):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        print("[DETECTOR] Initializing UnifiedDetector (4-Stage Pipeline)...")

        # Stage 1: Person detection
        person_model_path = os.path.join(project_root, "yolo26n.pt")
        if not os.path.exists(person_model_path):
            person_model_path = os.path.join(project_root, "yolov8n.pt")
        self.person_model = YOLO(person_model_path)
        print("[DETECTOR]   Stage 1 (Person) ✓")

        # Stage 2: PPE detection
        ppe_path = os.path.join(project_root, "model", "New", "best_stage2_labeled_safety.pt")
        self.ppe_model = YOLO(ppe_path)
        print(f"[DETECTOR]   Stage 2 (PPE)    ✓ - Classes: {self.ppe_model.names}")

        # Stage 3: Environment hazards
        env_path = os.path.join(project_root, "model", "New", "best_stage3_openhole.pt")
        self.env_model = YOLO(env_path)
        print("[DETECTOR]   Stage 3 (Env)    ✓")

        # Stage 4: Road damage
        road_path = os.path.join(project_root, "model", "New", "best_jalan_berlubang.pt")
        self.road_model = YOLO(road_path)
        print("[DETECTOR]   Stage 4 (Road)   ✓")

        print("[DETECTOR] All models loaded successfully!")
        self.confidence = confidence

    def detect_base(self, frame: np.ndarray) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
        """
        Run base inference - People, Environment, Road, Safety Cones.
        Returns: (people, env_hazards, road_damage, safety_cones)
        """
        # Stage 3: Environment hazards (includes safety cones)
        env_results = self.env_model(frame, verbose=False, conf=self.confidence)
        env_hazards = []
        safety_cones = []

        for r in env_results:
            if not r.boxes:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0])
                label = self.env_model.names[cls_id]
                conf = float(box.conf[0])

                if label == "safety-cone" and conf >= SAFETY_CONE_CONFIDENCE:
                    safety_cones.append({
                        "bbox": [x1, y1, x2, y2],
                        "label": label,
                        "class_name": label,
                        "confidence": conf
                    })
                else:
                    env_hazards.append({
                        "bbox": [x1, y1, x2, y2],
                        "label": label,
                        "class_name": label,
                        "confidence": conf
                    })

        # Stage 4: Road damage
        road_results = self.road_model(frame, verbose=False, conf=self.confidence)
        road_damage = []
        for r in road_results:
            if not r.boxes:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0])
                label = self.road_model.names[cls_id]
                road_damage.append({
                    "bbox": [x1, y1, x2, y2],
                    "label": label,
                    "class_name": label,
                    "confidence": float(box.conf[0])
                })

        # Stage 1: People
        person_results = self.person_model(frame, verbose=False, conf=self.confidence)
        people = []
        for r in person_results:
            if not r.boxes:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id == 0:  # person class in COCO
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    people.append({
                        "bbox": [x1, y1, x2, y2],
                        "confidence": float(box.conf[0]),
                        "bottom_center": [(x1 + x2) / 2, y2],
                        "center": [(x1 + x2) / 2, (y1 + y2) / 2],
                        "ppe": []
                    })

        return people, env_hazards, road_damage, safety_cones

    def detect_ppe_full_frame(self, frame: np.ndarray, people: List[dict]) -> List[dict]:
        """
        Run PPE detection on FULL IMAGE and assign detections to persons using IoU.

        The PPE model was trained on full images with people and their PPE.
        Running on cropped person regions produces poor results because the input
        doesn't match the training distribution.
        """
        if not people:
            return people

        # Run PPE detection with very low threshold to catch all potential PPE
        ppe_detections = []
        ppe_results = self.ppe_model(frame, verbose=False, conf=0.01, imgsz=640)

        for r in ppe_results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id == 0:  # Skip 'unknown' class
                    continue
                label = self.ppe_model.names[cls_id]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                ppe_detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "label": label,
                    "confidence": conf
                })

        # Assign PPE detections to persons based on IoU
        for person in people:
            person_bbox = person["bbox"]
            ppe_result = {
                "has_helmet": False,
                "has_vest": False,
                "has_belt": False,
                "helmet_conf": 0.0,
                "vest_conf": 0.0,
                "belt_conf": 0.0,
                "raw_labels": []
            }

            for ppe in ppe_detections:
                iou = calculate_iou(person_bbox, ppe["bbox"])
                if iou > PPE_IOU_THRESHOLD:
                    label = ppe["label"]
                    conf = ppe["confidence"]
                    ppe_result["raw_labels"].append(f"{label}({conf:.0%})")

                    if label == "helmet":
                        ppe_result["has_helmet"] = True
                        ppe_result["helmet_conf"] = max(ppe_result["helmet_conf"], conf)
                    elif label == "vest":
                        ppe_result["has_vest"] = True
                        ppe_result["vest_conf"] = max(ppe_result["vest_conf"], conf)
                    elif label == "belt":
                        ppe_result["has_belt"] = True
                        ppe_result["belt_conf"] = max(ppe_result.get("belt_conf", 0.0), conf)

            person["ppe_result"] = ppe_result

            # Calculate violations
            violations = []
            if ppe_result["helmet_conf"] < PPE_CONFIDENCE_THRESHOLD:
                violations.append(VIOLATION_NO_HELMET)
            if ppe_result["vest_conf"] < PPE_CONFIDENCE_THRESHOLD:
                violations.append(VIOLATION_NO_VEST)
            if not ppe_result["has_belt"]:
                violations.append(VIOLATION_NO_BELT)
            person["ppe_violations"] = violations

        return people


class MultiStagePipeline(UnifiedDetector):
    """
    Alias/Wrapper for UnifiedDetector to match imports in other modules.
    Standard entry point used by stream and video processor.
    """

    def __init__(self, confidence: float = 0.25, ppe_confidence: float = 0.30):
        super().__init__(confidence=confidence)
        self.ppe_confidence = ppe_confidence

    def run(self, frame: np.ndarray) -> dict:
        """Standard entry point - runs full detection pipeline."""
        people, env_hazards, road_damage, safety_cones = self.detect_base(frame)
        if people:
            people = self.detect_ppe_full_frame(frame, people)

        return {
            "persons": people,
            "env": env_hazards,
            "road": road_damage,
            "safety_cones": safety_cones
        }
