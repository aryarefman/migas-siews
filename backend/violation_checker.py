"""
SIEWS+ Violation Checker
Analyzes detection results and identifies zone/PPE violations.
"""
import asyncio
import time
from typing import List, Set, Dict, Optional
from dataclasses import dataclass

from detection_models import FIRE_SMOKE_LABELS


@dataclass
class Violation:
    """Represents a detected violation."""
    zone_id: int
    zone_name: str
    risk_level: str
    violation_type: str
    confidence: float
    person_name: str = "Unknown"
    uniform_code: str = None
    ppe_detail: dict = None  # {helmet: bool, vest: bool, belt: bool}


class ViolationChecker:
    """
    Analyzes detection results and identifies violations.
    Checks for:
    - PPE violations (missing helmet, vest, belt)
    - Zone violations (person inside restricted area)
    - Hazard violations (person overlapping with environmental hazard)
    """

    def __init__(self, cooldown_seconds: int = 5):
        self._cooldown_seconds = cooldown_seconds
        self._zone_cooldowns: Dict[int, float] = {}

    def check_ppe_violations(self, persons: List[dict]) -> List[Violation]:
        """
        Check for PPE violations in detected persons.
        Returns list of violations found.
        
        Each person gets a unique zone_id based on their identity so cooldown
        works per-person, not globally. This makes alerts feel "live".
        """
        violations = []

        for i, det in enumerate(persons):
            ppe = det.get("ppe_result", {})
            has_helmet = ppe.get("has_helmet", False)
            has_vest = ppe.get("has_vest", False)
            has_belt = ppe.get("has_belt", False)

            if not has_helmet or not has_vest or not has_belt:
                missing = []
                if not has_helmet:
                    missing.append("NO HELMET")
                if not has_vest:
                    missing.append("NO VEST")
                if not has_belt:
                    missing.append("NO BELT")

                # Generate stable key per person for cooldown tracking
                person_key = det.get("face_name", "") or ""
                if person_key == "Unknown" or person_key == "":
                    # Use OCR code if available
                    person_key = det.get("ocr_code", "") or ""
                if not person_key or person_key == "Unknown":
                    # Fallback: use bbox grid position (stable across frames)
                    # Quantize to 100px grid so small movements don't create new keys
                    bbox = det.get("bbox", [0, 0, 0, 0])
                    cx = (bbox[0] + bbox[2]) // 200  # grid cell X
                    cy = (bbox[1] + bbox[3]) // 200  # grid cell Y
                    person_key = f"pos_{cx}_{cy}"
                
                violations.append(Violation(
                    zone_id=hash(person_key) % 10000,  # Unique per-person
                    zone_name=f"PPE Violation ({', '.join(missing)})",
                    risk_level="high",  # PPE violations are always high risk in industrial safety
                    violation_type="ppe_violation",
                    confidence=det.get("confidence", 0),
                    person_name=det.get("face_name", "Unknown"),
                    uniform_code=det.get("ocr_code"),
                    ppe_detail={"helmet": has_helmet, "vest": has_vest, "belt": has_belt},
                ))

        return violations

    def check_zone_violations(
        self,
        persons: List[dict],
        zones: List[dict],
        frame_width: int,
        frame_height: int
    ) -> List[Violation]:
        """
        Check if any persons are inside restricted zones.
        Uses head, chest, and feet points for better detection.
        """
        from polygon import point_in_polygon

        violations = []

        for i, det in enumerate(persons):
            bbox = det["bbox"]
            x1, y1, x2, y2 = bbox

            # Normalize bbox to [0-1]
            nx1 = x1 / frame_width
            ny1 = y1 / frame_height
            nx2 = x2 / frame_width
            ny2 = y2 / frame_height
            ncx = (nx1 + nx2) / 2
            ncy = (ny1 + ny2) / 2

            # Sample grid of points across the person bbox (9 points)
            body_points = [
                [ncx, ny1 + (ny2 - ny1) * 0.15],   # head center
                [ncx, ncy],                          # chest center
                [ncx, ny2 - 0.005],                  # feet center
                [nx1 + (nx2-nx1)*0.25, ny1 + (ny2-ny1)*0.2],  # head left
                [nx1 + (nx2-nx1)*0.75, ny1 + (ny2-ny1)*0.2],  # head right
                [nx1 + (nx2-nx1)*0.25, ncy],         # chest left
                [nx1 + (nx2-nx1)*0.75, ncy],         # chest right
                [nx1 + (nx2-nx1)*0.25, ny2 - 0.005], # feet left
                [nx1 + (nx2-nx1)*0.75, ny2 - 0.005], # feet right
                # Bbox corners for maximum coverage
                [nx1, ny1],  # top-left
                [nx2, ny1],  # top-right
                [nx1, ny2],  # bottom-left
                [nx2, ny2],  # bottom-right
            ]

            for z in zones:
                if len(z.get("vertices", [])) < 3:
                    continue
                # Check if any body point is inside zone
                is_inside = any(
                    point_in_polygon(pt, z["vertices"]) for pt in body_points
                )

                if is_inside:
                    violations.append(Violation(
                        zone_id=z["id"],
                        zone_name=z["name"],
                        risk_level=z["risk_level"],
                        violation_type="zone_violation",
                        confidence=det.get("confidence", 0),
                        person_name=det.get("face_name", "Unknown"),
                        uniform_code=det.get("ocr_code"),
                    ))
                    break  # One violation per person per check

        return violations

    def check_hazard_violations(
        self,
        persons: List[dict],
        hazards: List[dict]
    ) -> List[Violation]:
        """
        Check if any person overlaps with environmental hazards.
        A violation occurs when the person's center is inside a hazard zone.
        """
        violations = []

        for i, det in enumerate(persons):
            bbox = det["bbox"]
            x1, y1, x2, y2 = bbox
            person_center_x = (x1 + x2) / 2
            person_center_y = (y1 + y2) / 2

            for haz in hazards:
                label = haz.get("label", haz.get("class_name", "")).lower()
                if label in FIRE_SMOKE_LABELS:
                    continue

                hx1, hy1, hx2, hy2 = haz["bbox"]

                if hx1 <= person_center_x <= hx2 and hy1 <= person_center_y <= hy2:
                    violations.append(Violation(
                        zone_id=999,
                        zone_name=f"Area Berbahaya ({haz['label']})",
                        risk_level="high",
                        violation_type="hazard_violation",
                        confidence=det.get("confidence", 0),
                        person_name=det.get("face_name", "Unknown"),
                        uniform_code=det.get("ocr_code"),
                    ))

        return violations

    def check_fire_smoke_violations(self, hazards: List[dict]) -> List[Violation]:
        """
        Fire/smoke is a direct facility hazard, so it should alert even when
        no person is visible in the frame.
        """
        violations = []

        for haz in hazards:
            label = haz.get("label", haz.get("class_name", "")).lower()
            if label not in FIRE_SMOKE_LABELS:
                continue

            zone_id = 998 if label == "fire" else 997
            display_label = label.replace("_", " ").title()
            violations.append(Violation(
                zone_id=zone_id,
                zone_name=f"{display_label} Detected",
                risk_level="high",
                violation_type="fire_smoke",
                confidence=haz.get("confidence", 0),
            ))

        return violations

    def check_all_violations(
        self,
        persons: List[dict],
        hazards: List[dict],
        zones: List[dict],
        frame_width: int,
        frame_height: int,
        road_detections: List[dict] = None,
    ) -> List[Violation]:
        """Run all violation checks and return combined results."""
        all_violations = []

        all_violations.extend(self.check_fire_smoke_violations(hazards))
        all_violations.extend(self.check_ppe_violations(persons))
        all_violations.extend(self.check_hazard_violations(persons, hazards))
        all_violations.extend(self.check_zone_violations(persons, zones, frame_width, frame_height))

        # Auto-zone: road damage is always a violation when detected
        if road_detections:
            all_violations.extend(self.check_road_damage_violations(road_detections))

        # Auto-zone: env hazards (open hole) inside manual zones
        all_violations.extend(self.check_hazard_in_zone_violations(hazards, zones, frame_width, frame_height))

        return all_violations

    def check_road_damage_violations(self, road_detections: List[dict]) -> List[Violation]:
        """
        Road damage (pothole/lubang jalan) is always a violation when detected.
        Auto-generates a dynamic zone around the detection.
        """
        violations = []
        for i, road in enumerate(road_detections):
            label = road.get("class_name", road.get("label", "pothole"))
            conf = road.get("confidence", 0)
            display_name = label.replace("_", " ").upper()
            violations.append(Violation(
                zone_id=900 + i,
                zone_name=f"DANGER: {display_name}",
                risk_level="high",
                violation_type="road_damage",
                confidence=conf,
            ))
        return violations

    def check_hazard_in_zone_violations(
        self,
        hazards: List[dict],
        zones: List[dict],
        frame_width: int,
        frame_height: int,
    ) -> List[Violation]:
        """
        Check if env hazards (open hole, etc.) are inside manual zones.
        Fire/smoke is handled separately, so skip those here.
        """
        from polygon import point_in_polygon

        violations = []
        for haz in hazards:
            label = haz.get("label", haz.get("class_name", "")).lower()
            if label in FIRE_SMOKE_LABELS:
                continue

            bbox = haz.get("bbox", [0, 0, 0, 0])
            x1, y1, x2, y2 = bbox
            center_pt = ((x1 + x2) / 2 / frame_width, (y1 + y2) / 2 / frame_height)

            for z in zones:
                vertices = z.get("vertices", [])
                if len(vertices) < 3:
                    continue
                if point_in_polygon(center_pt, vertices):
                    violations.append(Violation(
                        zone_id=z["id"],
                        zone_name=f"{z['name']} ({label})",
                        risk_level=z["risk_level"],
                        violation_type="hazard_in_zone",
                        confidence=haz.get("confidence", 0),
                    ))
                    break
        return violations

    def get_violation_indices(self, persons: List[dict], violations: List[Violation]) -> Set[int]:
        """Get indices of persons that have violations."""
        if not violations:
            return set()

        indices = set()

        for i, det in enumerate(persons):
            ppe = det.get("ppe_result", {})
            if not ppe.get("has_helmet", False) or not ppe.get("has_vest", False) or not ppe.get("has_belt", False):
                indices.add(i)

        return indices

    def get_violated_zone_ids(self, persons: List[dict], zones: List[dict], violations: List[Violation]) -> Set[int]:
        """
        Return zone IDs currently occupied by persons with violations.
        Uses polygon point-in-zone test for each person.
        """
        from polygon import point_in_polygon

        violated = set()

        for v in violations:
            if v.violation_type == "zone_violation":
                violated.add(v.zone_id)

        # Also check: if a person is inside any zone, highlight that zone
        for det in persons:
            bbox = det.get("bbox", [])
            if len(bbox) != 4:
                continue
            # Normalize to 0-1 range (zones use normalized coords)
            frame_w = det.get("_frame_w", 640)
            frame_h = det.get("_frame_h", 480)
            px = ((bbox[0] + bbox[2]) / 2) / frame_w
            py = ((bbox[1] + bbox[3]) / 2) / frame_h

            for z in zones:
                zid = z.get("id")
                vertices = z.get("vertices", [])
                if zid is None or not vertices or len(vertices) < 3:
                    continue

                if point_in_polygon([px, py], vertices):
                    violated.add(zid)

        return violated

    def should_alert(self, zone_id: int, violation_type: str = "") -> bool:
        """
        Check if alert should be sent (respects cooldown).
        
        ALL violation types use the same cooldown from settings (notify_cooldown).
        This ensures WhatsApp notifications are sent at the configured interval
        regardless of violation type (PPE, fire, zone, hazard).
        """
        now = time.time()
        last_alert = self._zone_cooldowns.get(zone_id, 0)

        # All violations use the same configured cooldown
        cooldown = self._cooldown_seconds

        if now - last_alert < cooldown:
            return False

        self._zone_cooldowns[zone_id] = now
        return True

    def clear_cooldown(self, zone_id: int):
        """Clear cooldown for a specific zone."""
        if zone_id in self._zone_cooldowns:
            del self._zone_cooldowns[zone_id]
