"""
SIEWS+ Drawing Utilities
Clean separation of bounding box drawing functions for detection visualization.
"""
import cv2
import numpy as np
from typing import List, Set


# Colors in BGR
COLOR_DANGER = (0, 0, 255)      # Red
COLOR_SAFE = (0, 255, 0)         # Green
COLOR_WARNING = (0, 165, 255)     # Orange
COLOR_INFO = (255, 165, 0)       # Cyan/Orange
COLOR_HAZARD = (255, 0, 0)       # Blue
COLOR_VEHICLE = (255, 0, 255)    # Magenta


def draw_bounding_box(
    frame: np.ndarray,
    bbox: List[float],
    label: str,
    color: tuple,
    thickness: int = 2,
    font_scale: float = 0.5,
):
    """Draw a labeled bounding box on the frame."""
    x1, y1, x2, y2 = [int(v) for v in bbox]

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
    cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
    cv2.putText(
        frame, label, (x1 + 2, y1 - 3),
        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
    )


def draw_persons(
    frame: np.ndarray,
    persons: List[dict],
    violations: Set[int],
    font_scale: float = 0.5
):
    """Draw person detections with PPE status."""
    for i, det in enumerate(persons):
        bbox = det["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        conf = det.get("confidence", 0)
        ppe_result = det.get("ppe_result", {})

        is_violation = i in violations
        color = COLOR_DANGER if is_violation else COLOR_SAFE

        # Build explicit PPE status string.
        if ppe_result:
            ppe_str = (
                f"Helmet:{'OK' if ppe_result.get('has_helmet') else 'MISS'} "
                f"Vest:{'OK' if ppe_result.get('has_vest') else 'MISS'} "
                f"Belt:{'OK' if ppe_result.get('has_belt') else 'MISS'}"
            )
        else:
            ppe_str = "PPE: not checked"

        # Build label
        face_name = det.get("face_name", "")
        ocr_code = det.get("ocr_code", "")
        id_str = ""
        if face_name and face_name != "Unknown":
            id_str = f" [{face_name}]"
        elif ocr_code:
            id_str = f" [{ocr_code}]"

        label = f"Person {conf:.0%}{id_str}" if not is_violation else f"BAHAYA {conf:.0%}{id_str}"

        # Draw box
        thickness = 4 if is_violation else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # Draw main label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 4, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )

        # Draw PPE status below box
        (tw2, th2), _ = cv2.getTextSize(ppe_str, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
        cv2.rectangle(frame, (x1, y2), (x1 + tw2 + 6, y2 + th2 + 6), (0, 0, 0), -1)
        ppe_color = COLOR_DANGER if is_violation else COLOR_SAFE
        cv2.putText(
            frame, ppe_str, (x1 + 3, y2 + th2 + 3),
            cv2.FONT_HERSHEY_SIMPLEX, 0.35, ppe_color, 1, cv2.LINE_AA
        )


def draw_env_hazards(frame: np.ndarray, hazards: List[dict], font_scale: float = 0.5):
    """Draw environmental hazard detections (dangerous areas, barricades, etc.)."""
    for haz in hazards:
        bbox = haz["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        label_text = haz.get("label", haz.get("class_name", "Hazard"))
        conf = haz.get("confidence", 0)
        label = f"DANGER: {label_text.upper()} {conf:.0%}"

        color = COLOR_DANGER
        thickness = 2

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 8, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 4, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )


def draw_road_damage(frame: np.ndarray, road: List[dict], font_scale: float = 0.5):
    """Draw road damage detections (potholes, cracks, patches)."""
    for r in road:
        bbox = r["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        label_text = r.get("label", r.get("class_name", "Road"))
        conf = r.get("confidence", 0)
        label = f"ROAD: {label_text.upper()} {conf:.0%}"

        color = COLOR_WARNING

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 2, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )


def draw_safety_cones(frame: np.ndarray, safety_cones: List[dict], font_scale: float = 0.5):
    """Draw safety cone detections (green boxes)."""
    for cone in safety_cones:
        bbox = cone.get("bbox", [])
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        conf = cone.get("confidence", 0)
        label = f"Safety-cone {conf:.0%}"

        color = COLOR_SAFE

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 2, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), 1, cv2.LINE_AA
        )


def draw_vehicles(frame: np.ndarray, vehicles: List[dict], font_scale: float = 0.5):
    """Draw vehicle detections."""
    for vehicle in vehicles:
        bbox = vehicle.get("bbox", [])
        if len(bbox) != 4:
            continue
        label_text = vehicle.get("label", vehicle.get("class_name", "vehicle"))
        conf = vehicle.get("confidence", 0)
        label = f"VEHICLE: {label_text.upper()} {conf:.0%}"
        draw_bounding_box(frame, bbox, label, COLOR_VEHICLE, thickness=2, font_scale=font_scale)


def draw_zones(frame: np.ndarray, zones: List[dict]):
    """Draw zone polygons on the frame."""
    from polygon import point_in_polygon, compute_centroid

    h, w = frame.shape[:2]
    overlay = frame.copy()

    for zone in zones:
        vertices = zone["vertices"]
        if not vertices:
            continue

        risk = zone["risk_level"]
        name = zone["name"]

        # Convert normalized coords to pixel coords
        pts = np.array(
            [[int(v[0] * w), int(v[1] * h)] for v in vertices],
            dtype=np.int32
        )

        if risk == "high":
            fill_color = (0, 0, 200)
            border_color = (0, 0, 255)
        else:
            fill_color = (0, 200, 200)
            border_color = (0, 255, 255)

        # Semi-transparent fill
        cv2.fillPoly(overlay, [pts], fill_color)
        cv2.polylines(frame, [pts], True, border_color, 2, cv2.LINE_AA)

        # Zone name at centroid
        centroid = compute_centroid(vertices)
        cx, cy = int(centroid[0] * w), int(centroid[1] * h)
        label = f"{name} ({risk.upper()})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(
            frame,
            (cx - tw // 2 - 4, cy - th - 6),
            (cx + tw // 2 + 4, cy + 4),
            (0, 0, 0), -1
        )
        cv2.putText(
            frame, label, (cx - tw // 2, cy),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, border_color, 1, cv2.LINE_AA
        )

    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)


def draw_detections(
    frame: np.ndarray,
    persons: List[dict],
    violations: Set[int],
    hazards: List[dict],
    road: List[dict] = None,
    safety_cones: List[dict] = None,
    vehicles: List[dict] = None,
):
    """
    Draw all detection types on the frame.
    Convenience function that calls all individual draw functions.
    """
    # Safety cones first (green, lowest priority)
    if safety_cones:
        draw_safety_cones(frame, safety_cones)

    # Vehicles (magenta)
    if vehicles:
        draw_vehicles(frame, vehicles)

    # Road damage (orange)
    if road:
        draw_road_damage(frame, road)

    # Environmental hazards (red)
    draw_env_hazards(frame, hazards)

    # Persons (green/red based on violation)
    draw_persons(frame, persons, violations)
