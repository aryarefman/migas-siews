"""
SIEWS+ 5.0 — Multi-Stage Detection Pipeline
Stage 1: Person Detection      (YOLOv8n — full frame)
Stage 2: PPE + Harness         (YOLOv8s — per-person crop)
Stage 3: Fire/Smoke            (YOLOv8n — full frame, parallel)
Stage 4: Infrastructure/Infra  (YOLOv8s — full frame, parallel)
Extra  : any future stage via register_extra_stage()

Falls back gracefully if custom-trained weights are not yet available.

# ── Extensibility ───────────────────────────────────────────────────────────
# Adding a new model stage requires only:
#
#   pipeline.register_extra_stage(
#       key="stage5",
#       model_path=MODELS_DIR / "stage5_custom.pt",
#       fallback="yolov8n.pt",
#       classes={0: "class_a", 1: "class_b"},
#       mode="full_frame",   # "full_frame" | "per_person_crop"
#       confidence=0.4,
#   )
#
# Results appear in pipeline.run(frame)["stage5"].
# ────────────────────────────────────────────────────────────────────────────

# ── Stage 2 Mapping Notes (Oil and Gas Safety dataset) ──────────────────────
# Source: Roboflow "Oil and Gas Safety.v3i" — 11K images, 8 classes
# Verified order (from dataset data.yaml):
#   0=hardhat      → helmet (0)
#   1=safety-vest  → safety_vest (2)
#   2=person       → SKIP (Stage 1 handles person)
#   3=no-hardhat   → no_helmet (1)
#   4=no-vest      → no_vest (3)
#   5=safety-harness → safety_harness (4)
#   6=no-harness   → no_harness (5)
#   7=boots        → boots (7)
# NOTE: If mAP on no_helmet/no_vest is low after training, swap ids 0↔3, 1↔4.
# ────────────────────────────────────────────────────────────────────────────
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
from ultralytics import YOLO

MODELS_DIR   = Path(__file__).parent / "models" /"New"
BACKEND_DIR  = Path(__file__).parent  # backend root (yolo26n.pt lives here)

# ── Stage 2: PPE — labeled_safety.v1i (best_stage2_labeled_safety.pt) ──────
# Classes from dataset data.yaml (verified):
#   0: unknown  (no instances — tidak dipakai)
#   1: belt     (safety belt / harness)
#   2: helmet
#   3: vest
PPE_CLASSES: Dict[int, str] = {
    0: "unknown",
    1: "belt",
    2: "helmet",
    3: "vest",
}

# ── Stage 3: Open Hole / Construction Safety (best_stage3_openhole.pt) ──────
ENV_CLASSES: Dict[int, str] = {
    0: "barricade",
    1: "hard-hat",
    2: "safety-cone",   # class 2 = cone
    3: "open-hole",     # class 3 = lubang
    4: "vest",
}

# ── Stage 4: Infrastructure + Vehicles + Equipment (stage4_infrastructure.yaml)
INFRA_CLASSES: Dict[int, str] = {
    0: "oil_storage_tank",
    1: "oil_tank_truck",
    2: "construction_equip",
    3: "open_hole",
    4: "pressure_gauge",
    5: "adr_plate",
    6: "truck",
    7: "cctv_anomaly",
}

# ── Stage 5: Road Damage / Pothole Detection (best_jalan_berlubang.pt) ──────
# Classes from dataset jalan berlubang.v3-tambahan-dataset:
#   0: lubang   (pothole)
#   1: retak    (crack)
#   2: tambalan (patch/repair)
ROAD_CLASSES: Dict[int, str] = {
    0: "lubang",
    1: "retak",
    2: "tambalan",
}

# PPE classes that represent a direct violation (absence-based, see _verify_ppe)
# labeled_safety detects PRESENCE only — violations inferred from absence
VIOLATION_PPE_CLASSES: set = set()  # no direct-violation classes in this dataset


# ── Extra-stage descriptor ───────────────────────────────────────────────────

@dataclass
class ExtraStage:
    """
    Descriptor for a custom stage registered at runtime.
    Allows adding new detection models without modifying this file.
    """
    key: str                     # result dict key, e.g. "stage5"
    model: YOLO                  # loaded YOLO model
    classes: Dict[int, str]      # {cls_id: class_name}
    mode: str = "full_frame"     # "full_frame" | "per_person_crop"
    confidence: float = 0.4


# ── Model loader ─────────────────────────────────────────────────────────────

def _load_model(
    preferred_path: Path,
    fallback: str,
    allow_generic_fallback: bool = True,
) -> Optional[YOLO]:
    """Load from preferred path; fall back to pretrained if not found.

    Args:
        preferred_path: Path to custom-trained weights.
        fallback: Filename of a pretrained model (e.g. 'yolov8n.pt').
        allow_generic_fallback: If False, do NOT fall back to a generic
            pretrained model when the custom weights are missing.  This
            prevents stages with custom class mappings from silently
            producing wrong labels using COCO class IDs.

    Returns:
        Loaded YOLO model, or None if unavailable.
    """
    if preferred_path.exists():
        print(f"[DETECTOR] Loading custom model: {preferred_path}")
        try:
            return YOLO(str(preferred_path))
        except Exception as e:
            print(f"[DETECTOR] WARNING: Failed to load {preferred_path.name}: {e}")
            print(f"[DETECTOR] Model may be incompatible with ultralytics version. Trying fallback...")
            if not allow_generic_fallback:
                print(f"[DETECTOR] Stage DISABLED (no compatible fallback).")
                return None

    if not allow_generic_fallback:
        print(f"[DETECTOR] {preferred_path.name} not found and generic fallback disabled.")
        print(f"[DETECTOR] Stage will be DISABLED until custom model is provided.")
        return None

    # 1. Check inside MODELS_DIR
    fallback_path = MODELS_DIR / fallback
    if fallback_path.exists():
        print(f"[DETECTOR] {preferred_path.name} not found — using local fallback: {fallback_path}")
        return YOLO(str(fallback_path))
    # 2. Check in backend root directory (e.g. yolo26n.pt downloaded there)
    root_fallback = BACKEND_DIR / fallback
    if root_fallback.exists():
        print(f"[DETECTOR] {preferred_path.name} not found — using root fallback: {root_fallback}")
        return YOLO(str(root_fallback))
    # 3. Try downloading from ultralytics hub
    try:
        print(f"[DETECTOR] {preferred_path.name} not found — downloading from ultralytics: {fallback}")
        return YOLO(fallback)
    except Exception as e:
        print(f"[DETECTOR] WARNING: Could not load {preferred_path.name} or fallback '{fallback}': {e}")
        print(f"[DETECTOR] Stage will be DISABLED until model is available.")
        return None


# ── Pipeline ─────────────────────────────────────────────────────────────────

class MultiStagePipeline:
    """
    Multi-stage detection pipeline for SIEWS+ safety monitoring.

    Built-in stages:
        S1 → person detection (full frame)
        S2 → PPE + harness (per-person crop)
        S3 → fire / smoke (full frame)
        S4 → infrastructure / vehicles (full frame)

    Custom stages:
        Call register_extra_stage() to add Stage 5, 6, etc. at runtime.
        Results appear in run(frame) under the registered key.

    Usage:
        pipeline = MultiStagePipeline(confidence=0.5)
        result   = pipeline.run(frame)
        persons  = result["persons"]
        env      = result["env"]
        infra    = result["infra"]
        custom   = result.get("stage5", [])
    """

    def __init__(self, confidence: float = 0.35, ppe_confidence: float = 0.3):
        self.confidence     = confidence
        self.ppe_confidence = ppe_confidence
        self._extra_stages: List[ExtraStage] = []

        # S1 — Person detection: official YOLO26n pretrained (COCO class 0 = person)
        self.model_s1 = _load_model(
            BACKEND_DIR / "yolo26n.pt",
            "yolo26n.pt",
        )

        # S2 — PPE: labeled_safety model (belt / helmet / vest)
        self.model_s2 = _load_model(
            MODELS_DIR / "best_stage2_labeled_safety.pt", # Sudah updateed 15 April 2026
            "yolo26n.pt",
            allow_generic_fallback=False,
        )

        # S3 — Open Hole / Construction Safety: best_stage3_openhole.pt (sudah jadi)
        self.model_s3 = _load_model(
            MODELS_DIR / "best_stage3_openhole.pt",
            "yolo26n.pt",
            allow_generic_fallback=False,
        )

        # S4 — Infrastructure: DISABLED — model sedang di-training
        self.model_s4 = None
        print("[DETECTOR] S4 (Infrastructure) DISABLED — menunggu model baru dari training.")

        # S5 — Road Damage / Pothole: jalan berlubang model (lubang/retak/tambalan)
        self.model_s5 = _load_model(
            MODELS_DIR / "best_jalan_berlubang.pt",
            "yolo26n.pt",
            allow_generic_fallback=False,
        )

        active = ["S1(person)", "S3(openhole)"]
        if self.model_s2: active.insert(1, "S2(PPE:belt/helmet/vest)")
        if self.model_s5: active.append("S5(road_damage)")
        print(f"[DETECTOR] MultiStagePipeline initialized — AKTIF: {' + '.join(active)}")

    # ── Extensibility API ──────────────────────────────────────────────────

    def register_extra_stage(
        self,
        key: str,
        model_path: Path,
        fallback: str,
        classes: Dict[int, str],
        mode: str = "full_frame",
        confidence: float = 0.4,
    ) -> None:
        """
        Register a new detection stage at runtime.

        Example — adding a Stage 5 gas leak detector:
            pipeline.register_extra_stage(
                key="stage5",
                model_path=MODELS_DIR / "stage5_gas_leak.pt",
                fallback="yolov8n.pt",
                classes={0: "gas_leak", 1: "vapor_cloud"},
                mode="full_frame",
                confidence=0.45,
            )
        """
        model = _load_model(Path(model_path), fallback)
        self._extra_stages.append(ExtraStage(
            key=key, model=model, classes=classes,
            mode=mode, confidence=confidence,
        ))
        print(f"[DETECTOR] Registered extra stage: {key}")

    # Core Stages 

    def _detect_persons(self, frame: np.ndarray) -> List[dict]:
        """S1: Person detection on full frame."""
        results = self.model_s1(frame, verbose=False, conf=self.confidence, classes=[0])
        persons = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                persons.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf,
                    "bottom_center": [(x1 + x2) / 2, float(y2)],
                    "ppe": {},
                    "ppe_violations": [],
                })
        return persons

    def _verify_ppe(self, frame: np.ndarray, person: dict) -> dict:
        """S2: Crop person bbox and run PPE + harness check."""
        if self.model_s2 is None:
            return person
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = person["bbox"]
        pad = 10
        crop = frame[max(0, y1 - pad):min(h, y2 + pad),
                     max(0, x1 - pad):min(w, x2 + pad)]
        if crop.size == 0:
            return person

        ppe_status: Dict[str, dict] = {}
        violations: List[str] = []
        all_detections = []
        for result in self.model_s2(crop, verbose=False, conf=self.ppe_confidence):
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id   = int(box.cls[0])
                cls_name = PPE_CLASSES.get(cls_id, f"cls_{cls_id}")
                conf     = float(box.conf[0])
                all_detections.append(f"{cls_name}:{conf:.2f}")
                if cls_name not in ppe_status or conf > ppe_status[cls_name]["confidence"]:
                    ppe_status[cls_name] = {
                        "confidence": conf,
                        "bbox_in_crop": [int(v) for v in box.xyxy[0].tolist()],
                    }
                if cls_name in VIOLATION_PPE_CLASSES:
                    violations.append(cls_name)

        # Absence-based violation: threshold beda per item PPE
        # Belt lebih rendah karena susah dideteksi dari sudut belakang/samping
        if ppe_status.get("helmet", {}).get("confidence", 0) < 0.35:
            violations.append("no_helmet")
        if ppe_status.get("vest", {}).get("confidence", 0) < 0.35:
            violations.append("no_vest")
        if "belt" not in ppe_status:  # hanya kalau sama sekali tidak terdeteksi
            violations.append("no_belt")

        print(f"[PPE] S2 detections: {all_detections if all_detections else 'NONE'} | violations={violations}")
        person["ppe"]            = ppe_status
        person["ppe_violations"] = list(set(violations))
        return person

    def _detect_full_frame(
        self,
        frame: np.ndarray,
        model: YOLO,
        classes: Dict[int, str],
        conf: Optional[float] = None,
    ) -> List[dict]:
        """Generic full-frame detection (used for S3, S4, and extra stages)."""
        conf = conf or self.confidence
        detections = []
        for result in model(frame, verbose=False, conf=conf):
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id   = int(box.cls[0])
                cls_name = classes.get(cls_id, f"cls_{cls_id}")
                conf_val = float(box.conf[0])
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                detections.append({
                    "class_id":   cls_id,
                    "class_name": cls_name,
                    "confidence": conf_val,
                    "bbox":       [x1, y1, x2, y2],
                })
        return detections

    def _detect_per_crop(
        self,
        frame: np.ndarray,
        persons: List[dict],
        model: YOLO,
        classes: Dict[int, str],
        conf: float,
    ) -> List[dict]:
        """Run a model on each person crop (for per-person extra stages)."""
        h, w = frame.shape[:2]
        detections = []
        for person in persons:
            x1, y1, x2, y2 = person["bbox"]
            crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
            if crop.size == 0:
                continue
            for det in self._detect_full_frame(crop, model, classes, conf):
                det["person_bbox"] = person["bbox"]
                detections.append(det)
        return detections

    # ── Main run ──────────────────────────────────────────────────────────

    def run(self, frame: np.ndarray) -> dict:
        """
        Run the full pipeline on a frame.

        Returns dict with keys:
            "persons" — Stage 1+2 results
            "env"     — Stage 3 fire/smoke
            "infra"   — Stage 4 infrastructure
            + any extra stage keys registered via register_extra_stage()
        """
        persons = self._detect_persons(frame)
        for i, person in enumerate(persons):
            persons[i] = self._verify_ppe(frame, person)

        result = {
            "persons": persons,
            "env":   self._detect_full_frame(frame, self.model_s3, ENV_CLASSES)   if self.model_s3 else [],
            "infra": self._detect_full_frame(frame, self.model_s4, INFRA_CLASSES) if self.model_s4 else [],
            "road":  self._detect_full_frame(frame, self.model_s5, ROAD_CLASSES) if self.model_s5 else [],
        }

        # Run any registered extra stages
        for stage in self._extra_stages:
            if stage.mode == "full_frame":
                result[stage.key] = self._detect_full_frame(
                    frame, stage.model, stage.classes, stage.confidence
                )
            elif stage.mode == "per_person_crop":
                result[stage.key] = self._detect_per_crop(
                    frame, persons, stage.model, stage.classes, stage.confidence
                )

        return result

    def run_persons_only(self, frame: np.ndarray) -> List[dict]:
        """Run only Stage 1 (person detection), skip PPE/env/infra."""
        return self._detect_persons(frame)
