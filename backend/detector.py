"""
SIEWS+ 5.0 YOLOv8 Detector
Clean multi-stage pipeline: Person -> PPE -> Environment -> Road -> Safety Cones
"""
import os
import numpy as np
from typing import List, Tuple
from ultralytics import YOLO

from detection_models import (
    ENV_CONFIDENCE_THRESHOLD,
    ENV_HAZARD_LABELS,
    FIRE_CONFIDENCE_THRESHOLD,
    FIRE_SMOKE_CONFIDENCE_THRESHOLD,
    FIRE_SMOKE_LABELS,
    OPEN_HOLE_CONFIDENCE_THRESHOLD,
    PPE_CONFIDENCE_THRESHOLD,
    ROAD_CONFIDENCE_THRESHOLD,
    SAFETY_CONE_CONFIDENCE,
    SMOKE_CONFIDENCE_THRESHOLD,
    PPE_IOU_THRESHOLD,
    VEHICLE_CONFIDENCE_THRESHOLD,
    VIOLATION_NO_HELMET,
    VIOLATION_NO_VEST,
    VIOLATION_NO_BELT,
)


def _select_device() -> str:
    """Auto-detect best available compute device: CUDA > MPS > CPU."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            print(f"[DETECTOR] GPU detected: {name} — using CUDA")
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            print("[DETECTOR] Apple MPS detected — using MPS")
            return "mps"
    except Exception:
        pass
    print("[DETECTOR] No GPU found — using CPU")
    return "cpu"

DEVICE = _select_device()


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


def bbox_area_ratio(box: List[float], frame: np.ndarray) -> float:
    """Return bbox area as a fraction of the full frame area."""
    x1, y1, x2, y2 = box
    frame_h, frame_w = frame.shape[:2]
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return area / max(float(frame_w * frame_h), 1.0)


def bbox_center_y_ratio(box: List[float], frame: np.ndarray) -> float:
    """Return bbox vertical center as a 0..1 ratio of frame height."""
    _, y1, _, y2 = box
    frame_h = frame.shape[0]
    return ((y1 + y2) / 2) / max(float(frame_h), 1.0)


def bbox_bottom_y_ratio(box: List[float], frame: np.ndarray) -> float:
    """Return bbox bottom as a 0..1 ratio of frame height."""
    return box[3] / max(float(frame.shape[0]), 1.0)


def is_valid_env_hazard(label: str, conf: float, bbox: List[float], frame: np.ndarray) -> bool:
    """Class-specific filters so normal objects do not become safety hazards."""
    normalized = label.lower()
    if normalized not in ENV_HAZARD_LABELS:
        return False

    if normalized == "open-hole":
        # Open holes are floor/ground hazards. Detections on ceilings/windows
        # are almost always false positives in dashboard camera feeds.
        if conf < OPEN_HOLE_CONFIDENCE_THRESHOLD:
            return False
        if bbox_center_y_ratio(bbox, frame) < 0.55 or bbox_bottom_y_ratio(bbox, frame) < 0.68:
            return False
        if bbox_area_ratio(bbox, frame) < 0.004:
            return False

    return True


def is_valid_fire_smoke_hazard(label: str, conf: float, bbox: List[float], frame: np.ndarray) -> bool:
    """Class-specific fire/smoke filters with adaptive threshold support."""
    normalized = label.lower()
    if normalized not in FIRE_SMOKE_LABELS:
        return False

    # Import here to avoid circular import; stream module owns adaptive state
    try:
        from stream import get_effective_threshold
    except ImportError:
        get_effective_threshold = lambda base, _: base

    area_ratio = bbox_area_ratio(bbox, frame)
    if normalized == "smoke":
        threshold = get_effective_threshold(SMOKE_CONFIDENCE_THRESHOLD, "smoke")
        return conf >= threshold and area_ratio >= 0.05  # smoke must cover ≥5% of frame

    threshold = get_effective_threshold(FIRE_CONFIDENCE_THRESHOLD, "fire")
    return conf >= threshold and area_ratio >= 0.03  # fire must cover ≥3% of frame


class UnifiedDetector:
    """
    YOLO detector: Person -> PPE -> Environment -> Road Damage -> Fire/Smoke -> Vehicles.

    Stage 1: Person detection (yolov8n.pt / yolo26n.pt)
    Stage 2: PPE verification (best_stage2_labeled_safety.pt - 4 classes)
    Stage 3: Environment hazards (best_stage3_openhole.pt)
    Stage 4: Road damage (best_jalan_berlubang.pt)
    Stage 5: Fire & smoke hazards (fire_smoke.pt)
    Vehicle: vehicle_best.pt
    """

    # PPE Classes (Stage 2)
    # Class 0: unknown (no PPE / background)
    # Class 1: belt
    # Class 2: helmet
    # Class 3: vest
    PPE_CLASSES = {0: "unknown", 1: "belt", 2: "helmet", 3: "vest"}

    def __init__(self, confidence: float = 0.25):
        # Root project dir is one level above backend/
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model_new = os.path.join(project_root, "model", "New")

        print("[DETECTOR] Initializing UnifiedDetector (5-Stage Pipeline + Vehicles)...")
        print(f"[DETECTOR] model_new={model_new}")

        # Stage 1: Person detection — yolo26n.pt lives in backend/
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        person_model_path = os.path.join(backend_dir, "yolo26n.pt")
        if not os.path.exists(person_model_path):
            person_model_path = os.path.join(backend_dir, "yolov8n.pt")
        self.person_model = YOLO(person_model_path)
        print(f"[DETECTOR]   Stage 1 (Person) ✓ — {os.path.basename(person_model_path)}")

        # Stage 2: PPE detection
        ppe_path = os.path.join(model_new, "best_stage2_labeled_safety.pt")
        self.ppe_model = YOLO(ppe_path)
        print(f"[DETECTOR]   Stage 2 (PPE)    ✓ - Classes: {self.ppe_model.names}")

        # Stage 3: Environment hazards
        env_path = os.path.join(model_new, "best_stage3_openhole.pt")
        self.env_model = YOLO(env_path)
        print("[DETECTOR]   Stage 3 (Env)    ✓")

        # Stage 4: Road damage
        road_path = os.path.join(model_new, "best_jalan_berlubang.pt")
        self.road_model = YOLO(road_path)
        print("[DETECTOR]   Stage 4 (Road)   ✓")

        # Stage 5: Fire & smoke detection
        fire_smoke_path = os.path.join(model_new, "fire_smoke.pt")
        if not os.path.exists(fire_smoke_path):
            print("[DETECTOR]   Stage 5 (Fire/Smoke) — model not found, skipping")
            self.fire_smoke_model = None
        else:
            self.fire_smoke_model = YOLO(fire_smoke_path)
            print(f"[DETECTOR]   Stage 5 (Fire/Smoke) ✓ - Classes: {self.fire_smoke_model.names}")

        # Vehicle detection
        vehicle_path = os.path.join(model_new, "vehicle_best.pt")
        if not os.path.exists(vehicle_path):
            print("[DETECTOR]   Vehicle model — model not found, skipping")
            self.vehicle_model = None
        else:
            self.vehicle_model = YOLO(vehicle_path)
            print(f"[DETECTOR]   Vehicle         ✓ - Classes: {self.vehicle_model.names}")

        print("[DETECTOR] All models loaded successfully!")
        self.confidence = confidence

    def detect_base(self, frame: np.ndarray, photo_mode: bool = False) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
        """
        Run base inference - People, Environment, Road, Safety Cones.
        Returns: (people, env_hazards, road_damage, safety_cones)

        photo_mode=True: Uses lower thresholds and relaxed area filters for
        static image analysis (uploaded photos). Live stream uses stricter
        thresholds to reduce false positives from camera noise/motion.
        """
        # ── Threshold selection ──────────────────────────────────────────────
        # Photo mode uses lower thresholds — static images have less noise
        env_conf = 0.35 if photo_mode else ENV_CONFIDENCE_THRESHOLD
        road_conf = 0.40 if photo_mode else ROAD_CONFIDENCE_THRESHOLD
        road_area_min = 0.001 if photo_mode else 0.003  # Relaxed area filter for photos

        # Stage 3: Environment hazards (includes safety cones)
        env_results = self.env_model(frame, verbose=False, conf=env_conf, device=DEVICE)
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
                bbox = [x1, y1, x2, y2]

                if conf < env_conf:
                    continue

                if label == "safety-cone" and conf >= SAFETY_CONE_CONFIDENCE:
                    safety_cones.append({
                        "bbox": bbox,
                        "label": label,
                        "class_name": label,
                        "confidence": conf
                    })
                elif photo_mode and label.lower() in ENV_HAZARD_LABELS:
                    # Photo mode: skip strict position/area filters
                    env_hazards.append({
                        "bbox": bbox,
                        "label": label,
                        "class_name": label,
                        "confidence": conf
                    })
                elif is_valid_env_hazard(label, conf, bbox, frame):
                    env_hazards.append({
                        "bbox": bbox,
                        "label": label,
                        "class_name": label,
                        "confidence": conf
                    })

        # Stage 4: Road damage
        road_results = self.road_model(frame, verbose=False, conf=road_conf, device=DEVICE)
        road_damage = []
        for r in road_results:
            if not r.boxes:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0])
                label = self.road_model.names[cls_id]
                conf = float(box.conf[0])
                bbox = [x1, y1, x2, y2]

                # Small road detections on non-road CCTV are usually false positives.
                # Photo mode uses relaxed area filter since the image is intentional.
                if conf < road_conf or bbox_area_ratio(bbox, frame) < road_area_min:
                    continue

                road_damage.append({
                    "bbox": bbox,
                    "label": label,
                    "class_name": label,
                    "confidence": conf
                })

        # Stage 5: Fire & smoke hazards (optional model)
        # Photo mode uses lower threshold — no live-stream noise to worry about
        fs_conf = 0.25 if photo_mode else FIRE_SMOKE_CONFIDENCE_THRESHOLD
        fire_smoke_results = self.fire_smoke_model(
            frame, verbose=False, conf=fs_conf, device=DEVICE
        ) if self.fire_smoke_model is not None else []
        for r in fire_smoke_results:
            if not r.boxes:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0])
                label = self.fire_smoke_model.names[cls_id]
                conf = float(box.conf[0])
                bbox = [x1, y1, x2, y2]

                # In photo mode skip area filter — static images can have small fire/smoke
                if photo_mode:
                    if label.lower() not in FIRE_SMOKE_LABELS:
                        continue
                elif not is_valid_fire_smoke_hazard(label, conf, bbox, frame):
                    continue

                env_hazards.append({
                    "bbox": bbox,
                    "label": label,
                    "class_name": label,
                    "confidence": conf,
                    "category": "fire_smoke",
                })

        # Stage 1: People
        person_results = self.person_model(frame, verbose=False, conf=self.confidence, device=DEVICE)
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

    def detect_vehicles(self, frame: np.ndarray, photo_mode: bool = False) -> List[dict]:
        """Run vehicle detection on the full frame."""
        if self.vehicle_model is None:
            return []

        vehicle_conf = 0.30 if photo_mode else VEHICLE_CONFIDENCE_THRESHOLD
        vehicles = []
        vehicle_results = self.vehicle_model(frame, verbose=False, conf=vehicle_conf, device=DEVICE)

        for r in vehicle_results:
            if not r.boxes:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cls_id = int(box.cls[0])
                label = self.vehicle_model.names[cls_id]
                conf = float(box.conf[0])

                if conf < vehicle_conf:
                    continue

                vehicles.append({
                    "bbox": [x1, y1, x2, y2],
                    "label": label,
                    "class_name": label,
                    "class_id": cls_id,
                    "confidence": conf,
                })

        return vehicles

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
        ppe_results = self.ppe_model(frame, verbose=False, conf=0.01, imgsz=640, device=DEVICE)

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
        vehicles = self.detect_vehicles(frame)
        if people:
            people = self.detect_ppe_full_frame(frame, people)

        return {
            "persons": people,
            "env": env_hazards,
            "road": road_damage,
            "safety_cones": safety_cones,
            "vehicles": vehicles,
        }

    def run_photo(self, frame: np.ndarray) -> dict:
        """Photo/image analysis — uses lower thresholds, no area/temporal filters."""
        people, env_hazards, road_damage, safety_cones = self.detect_base(frame, photo_mode=True)
        vehicles = self.detect_vehicles(frame, photo_mode=True)
        if people:
            people = self.detect_ppe_full_frame(frame, people)
        return {
            "persons": people,
            "env": env_hazards,
            "road": road_damage,
            "safety_cones": safety_cones,
            "vehicles": vehicles,
        }
