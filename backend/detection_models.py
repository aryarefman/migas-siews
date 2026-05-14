"""
SIEWS+ Detection Models & Constants
Centralized model class definitions for all detection stages.
This ensures consistency between inference-service and backend detector.
"""
from typing import Dict, List
from dataclasses import dataclass, field
from enum import Enum


# =============================================================================
# Model Class Definitions
# =============================================================================

class PPEClass(Enum):
    """PPE Stage (Stage 2) - best_stage2_labeled_safety.pt"""
    UNKNOWN = 0   # No PPE detected / background
    BELT = 1      # Safety belt/harness
    HELMET = 2    # Safety helmet
    VEST = 3      # Safety vest


class EnvClass(Enum):
    """Environment Stage (Stage 3) - best_stage3_openhole.pt"""
    BARRICADE = 0
    HARD_HAT = 1
    SAFETY_CONE = 2
    OPEN_HOLE = 3
    VEST_ENV = 4  # Note: vest is also in env model


class RoadClass(Enum):
    """Road Damage Stage (Stage 5) - best_jalan_berlubang.pt"""
    LUBANG = 0    # Hole/pothole
    RETAK = 1     # Crack
    TAMBALAN = 2  # Patch


class FireSmokeClass(Enum):
    """Fire & Smoke Stage - fire_smoke.pt"""
    FIRE = 0
    SMOKE = 1


# =============================================================================
# Detection Result Dataclasses
# =============================================================================

@dataclass
class BBox:
    """Bounding box representation."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def as_list(self) -> List[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    @property
    def center(self) -> tuple:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def bottom_center(self) -> tuple:
        return ((self.x1 + self.x2) / 2, self.y2)


@dataclass
class PersonDetection:
    """Result of person detection with PPE status."""
    bbox: List[float]
    confidence: float
    face_name: str = "Unknown"
    ocr_code: str = None
    ppe_result: Dict = field(default_factory=lambda: {
        "has_helmet": False,
        "has_vest": False,
        "has_belt": False,
        "helmet_conf": 0.0,
        "vest_conf": 0.0,
        "belt_conf": 0.0,
        "raw_labels": [],
    })
    ppe_violations: List[str] = field(default_factory=list)


@dataclass
class EnvDetection:
    """Result of environment hazard detection."""
    bbox: List[float]
    label: str
    class_name: str
    confidence: float


@dataclass
class RoadDetection:
    """Result of road damage detection."""
    bbox: List[float]
    label: str
    class_name: str
    confidence: float


@dataclass
class SafetyConeDetection:
    """Safety cone detection (subset of env)."""
    bbox: List[float]
    label: str = "safety-cone"
    class_name: str = "safety-cone"
    confidence: float = 0.0


@dataclass
class DetectionResult:
    """Combined result from all detection stages."""
    persons: List[PersonDetection] = field(default_factory=list)
    env: List[EnvDetection] = field(default_factory=list)
    road: List[RoadDetection] = field(default_factory=list)
    safety_cones: List[SafetyConeDetection] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "persons": [
                {
                    "bbox": p.bbox,
                    "confidence": p.confidence,
                    "face_name": p.face_name,
                    "ocr_code": p.ocr_code,
                    "ppe_result": p.ppe_result,
                    "ppe_violations": p.ppe_violations,
                }
                for p in self.persons
            ],
            "env": [
                {
                    "bbox": e.bbox,
                    "label": e.label,
                    "class_name": e.class_name,
                    "confidence": e.confidence,
                }
                for e in self.env
            ],
            "road": [
                {
                    "bbox": r.bbox,
                    "label": r.label,
                    "class_name": r.class_name,
                    "confidence": r.confidence,
                }
                for r in self.road
            ],
            "safety_cones": [
                {
                    "bbox": s.bbox,
                    "label": s.label,
                    "class_name": s.class_name,
                    "confidence": s.confidence,
                }
                for s in self.safety_cones
            ],
        }


# =============================================================================
# Configuration Constants
# =============================================================================

# Confidence thresholds
PERSON_CONFIDENCE_THRESHOLD = 0.50  # Person detection
PPE_CONFIDENCE_THRESHOLD = 0.35    # PPE violation threshold
ENV_CONFIDENCE_THRESHOLD = 0.55    # Environment hazards
ROAD_CONFIDENCE_THRESHOLD = 0.65   # Road damage
SAFETY_CONE_CONFIDENCE = 0.50      # Safety cone minimum (higher to reduce FP)
FIRE_SMOKE_CONFIDENCE_THRESHOLD = 0.65  # YOLO-level filter for live stream
FIRE_CONFIDENCE_THRESHOLD = 0.70        # Post-filter for fire
SMOKE_CONFIDENCE_THRESHOLD = 0.70       # Post-filter for smoke (very prone to FP indoors)
FIRE_SMOKE_LABELS = {"fire", "smoke"}
ENV_HAZARD_LABELS = {"open-hole", "barricade"}
OPEN_HOLE_CONFIDENCE_THRESHOLD = 0.88

# PPE IoU assignment threshold
PPE_IOU_THRESHOLD = 0.10

# Violation types
VIOLATION_NO_HELMET = "NO HELMET"
VIOLATION_NO_VEST = "NO VEST"
VIOLATION_NO_BELT = "NO BELT"


# =============================================================================
# Helper Functions
# =============================================================================

def get_ppe_class_name(cls_id: int) -> str:
    """Get PPE class name from class ID."""
    try:
        return PPEClass(cls_id).name.lower()
    except ValueError:
        return f"cls_{cls_id}"


def get_env_class_name(cls_id: int) -> str:
    """Get environment class name from class ID."""
    try:
        return EnvClass(cls_id).name.lower()
    except ValueError:
        return f"cls_{cls_id}"


def get_road_class_name(cls_id: int) -> str:
    """Get road damage class name from class ID."""
    try:
        return RoadClass(cls_id).name.lower()
    except ValueError:
        return f"cls_{cls_id}"


def get_fire_smoke_class_name(cls_id: int) -> str:
    """Get fire/smoke class name from class ID."""
    try:
        return FireSmokeClass(cls_id).name.lower()
    except ValueError:
        return f"cls_{cls_id}"


def check_ppe_violations(ppe_result: Dict) -> List[str]:
    """Determine PPE violations from PPE result."""
    violations = []
    if ppe_result.get("helmet_conf", 0) < PPE_CONFIDENCE_THRESHOLD:
        violations.append(VIOLATION_NO_HELMET)
    if ppe_result.get("vest_conf", 0) < PPE_CONFIDENCE_THRESHOLD:
        violations.append(VIOLATION_NO_VEST)
    if not ppe_result.get("has_belt", False):
        violations.append(VIOLATION_NO_BELT)
    return violations
