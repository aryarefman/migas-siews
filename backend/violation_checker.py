"""
SIEWS+ Violation Checker
Analyzes detection results and identifies zone/PPE violations.
"""
import asyncio
import time
from typing import List, Set, Dict, Optional
from dataclasses import dataclass


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
        """
        violations = []

        for det in persons:
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

                violations.append(Violation(
                    zone_id=0,
                    zone_name=f"PPE Violation ({', '.join(missing)})",
                    risk_level="low",
                    violation_type="ppe_violation",
                    confidence=det.get("confidence", 0),
                    person_name=det.get("face_name", "Unknown"),
                    uniform_code=det.get("ocr_code"),
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

            # Calculate body points (normalized)
            head_p = [(x1 + x2) / 2 / frame_width, (y1 + (y2 - y1) * 0.2) / frame_height]
            chest_p = [(x1 + x2) / 2 / frame_width, (y1 + y2) / 2 / frame_height]
            feet_p = [(x1 + x2) / 2 / frame_width, (y2 - 2) / frame_height]

            for z in zones:
                # Check if any body part is inside zone
                is_inside = (
                    point_in_polygon(head_p, z["vertices"]) or
                    point_in_polygon(chest_p, z["vertices"]) or
                    point_in_polygon(feet_p, z["vertices"])
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

    def check_all_violations(
        self,
        persons: List[dict],
        hazards: List[dict],
        zones: List[dict],
        frame_width: int,
        frame_height: int
    ) -> List[Violation]:
        """Run all violation checks and return combined results."""
        all_violations = []

        if zones:
            all_violations.extend(self.check_ppe_violations(persons))
        all_violations.extend(self.check_hazard_violations(persons, hazards))
        all_violations.extend(self.check_zone_violations(persons, zones, frame_width, frame_height))

        return all_violations

    def get_violation_indices(self, persons: List[dict], violations: List[Violation]) -> Set[int]:
        """Get indices of persons that have violations."""
        indices = set()

        for i, det in enumerate(persons):
            ppe = det.get("ppe_result", {})
            if not ppe.get("has_helmet", False) or not ppe.get("has_vest", False) or not ppe.get("has_belt", False):
                indices.add(i)

        return indices

    def should_alert(self, zone_id: int) -> bool:
        """Check if alert should be sent (respects cooldown)."""
        now = time.time()
        last_alert = self._zone_cooldowns.get(zone_id, 0)

        if now - last_alert < self._cooldown_seconds:
            return False

        self._zone_cooldowns[zone_id] = now
        return True

    def clear_cooldown(self, zone_id: int):
        """Clear cooldown for a specific zone."""
        if zone_id in self._zone_cooldowns:
            del self._zone_cooldowns[zone_id]
