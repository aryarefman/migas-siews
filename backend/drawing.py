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
    font_scale: float = 0.4
):
    """Draw person detections with name + PPE status (clean, minimal labels)."""
    for i, det in enumerate(persons):
        bbox = det["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        conf = det.get("confidence", 0)
        ppe_result = det.get("ppe_result", {})

        is_violation = i in violations
        color = COLOR_DANGER if is_violation else COLOR_SAFE

        # Build label: name or "Person"
        face_name = det.get("face_name", "")
        ocr_code = det.get("ocr_code", "")

        if face_name and face_name != "Unknown":
            label = f"{face_name} {conf:.0%}"
        elif ocr_code:
            label = f"{ocr_code} {conf:.0%}"
        else:
            label = f"Person {conf:.0%}"

        # Draw box
        thickness = 3 if is_violation else 2
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # Draw label (compact)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 3, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )

        # PPE status — only show if violation, compact single line below box
        if is_violation and ppe_result:
            parts = []
            if not ppe_result.get("has_helmet"):
                parts.append("Helmet:X")
            if not ppe_result.get("has_vest"):
                parts.append("Vest:X")
            if not ppe_result.get("has_belt"):
                parts.append("Belt:X")
            if parts:
                ppe_str = " ".join(parts)
                (tw2, th2), _ = cv2.getTextSize(ppe_str, cv2.FONT_HERSHEY_SIMPLEX, 0.3, 1)
                cv2.rectangle(frame, (x1, y2), (x1 + tw2 + 4, y2 + th2 + 4), (0, 0, 0), -1)
                cv2.putText(
                    frame, ppe_str, (x1 + 2, y2 + th2 + 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, COLOR_DANGER, 1, cv2.LINE_AA
                )


def draw_env_hazards(frame: np.ndarray, hazards: List[dict], font_scale: float = 0.4):
    """Draw environmental hazard detections with auto dynamic polygon overlay."""
    if not hazards:
        return

    overlay = frame.copy()

    for haz in hazards:
        bbox = haz["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        label_text = haz.get("label", haz.get("class_name", "Hazard"))
        conf = haz.get("confidence", 0)
        category = haz.get("category", "")

        # Fire/smoke gets special polygon treatment
        is_fire_smoke = category == "fire_smoke" or label_text.lower() in ("fire", "smoke")

        if is_fire_smoke:
            color = (0, 0, 255) if label_text.lower() == "fire" else (128, 0, 200)
            label = f"{label_text.upper()} {conf:.0%}"

            # Auto dynamic polygon — expanded area around detection
            pad_x = int((x2 - x1) * 0.1)
            pad_y = int((y2 - y1) * 0.1)
            poly_pts = np.array([
                [x1 - pad_x, y1 - pad_y],
                [x2 + pad_x, y1 - pad_y],
                [x2 + pad_x, y2 + pad_y],
                [x1 - pad_x, y2 + pad_y],
            ], dtype=np.int32)

            # Clip to frame bounds
            h, w = frame.shape[:2]
            poly_pts[:, 0] = np.clip(poly_pts[:, 0], 0, w - 1)
            poly_pts[:, 1] = np.clip(poly_pts[:, 1], 0, h - 1)

            # Semi-transparent danger zone fill
            cv2.fillPoly(overlay, [poly_pts], color)
            cv2.polylines(frame, [poly_pts], True, color, 2, cv2.LINE_AA)
        else:
            color = COLOR_DANGER
            label = f"{label_text.upper()} {conf:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        # Compact label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 5), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 2, y1 - 2),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )

    # Apply overlay with transparency for fire/smoke zones
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)


def draw_road_damage(frame: np.ndarray, road: List[dict], font_scale: float = 0.4):
    """Draw road damage detections with auto dynamic polygon (irregular shape)."""
    if not road:
        return

    overlay = frame.copy()

    for r in road:
        bbox = r["bbox"]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        label_text = r.get("label", r.get("class_name", "Road"))
        conf = r.get("confidence", 0)
        label = f"{label_text.upper()} {conf:.0%}"

        # Color based on damage type
        if label_text.lower() == "lubang":
            color = (0, 80, 255)  # Deep orange for potholes
        elif label_text.lower() == "retak":
            color = (0, 200, 255)  # Yellow for cracks
        else:
            color = COLOR_WARNING

        # Auto dynamic polygon — irregular shape around road damage
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        w_half = (x2 - x1) // 2
        h_half = (y2 - y1) // 2

        # Create irregular polygon (simulates road damage area)
        poly_pts = np.array([
            [x1 - int(w_half * 0.1), y1 + int(h_half * 0.2)],
            [cx - int(w_half * 0.3), y1 - int(h_half * 0.1)],
            [cx + int(w_half * 0.3), y1 - int(h_half * 0.1)],
            [x2 + int(w_half * 0.1), y1 + int(h_half * 0.2)],
            [x2 + int(w_half * 0.15), cy],
            [x2 + int(w_half * 0.1), y2 - int(h_half * 0.2)],
            [cx + int(w_half * 0.2), y2 + int(h_half * 0.1)],
            [cx - int(w_half * 0.2), y2 + int(h_half * 0.1)],
            [x1 - int(w_half * 0.1), y2 - int(h_half * 0.2)],
            [x1 - int(w_half * 0.15), cy],
        ], dtype=np.int32)

        # Clip to frame bounds
        h, w = frame.shape[:2]
        poly_pts[:, 0] = np.clip(poly_pts[:, 0], 0, w - 1)
        poly_pts[:, 1] = np.clip(poly_pts[:, 1], 0, h - 1)

        # Fill polygon with semi-transparent color
        cv2.fillPoly(overlay, [poly_pts], color)
        cv2.polylines(frame, [poly_pts], True, color, 2, cv2.LINE_AA)

        # Label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 2, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )

    # Apply overlay
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)


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


def draw_vehicles(frame: np.ndarray, vehicles: List[dict], font_scale: float = 0.4):
    """Draw vehicle detections with auto dynamic polygon."""
    if not vehicles:
        return

    overlay = frame.copy()

    for vehicle in vehicles:
        bbox = vehicle.get("bbox", [])
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        label_text = vehicle.get("label", vehicle.get("class_name", "vehicle"))
        conf = vehicle.get("confidence", 0)
        label = f"{label_text.upper()} {conf:.0%}"

        color = COLOR_VEHICLE

        # Auto dynamic polygon — vehicle-shaped (wider bottom, narrower top)
        pad = int((x2 - x1) * 0.05)
        poly_pts = np.array([
            [x1 + pad, y1],
            [x2 - pad, y1],
            [x2 + pad, y1 + int((y2 - y1) * 0.3)],
            [x2 + pad, y2 - pad],
            [x2 - pad, y2],
            [x1 + pad, y2],
            [x1 - pad, y2 - pad],
            [x1 - pad, y1 + int((y2 - y1) * 0.3)],
        ], dtype=np.int32)

        # Clip to frame bounds
        h, w = frame.shape[:2]
        poly_pts[:, 0] = np.clip(poly_pts[:, 0], 0, w - 1)
        poly_pts[:, 1] = np.clip(poly_pts[:, 1], 0, h - 1)

        # Semi-transparent fill
        cv2.fillPoly(overlay, [poly_pts], color)
        cv2.polylines(frame, [poly_pts], True, color, 2, cv2.LINE_AA)

        # Label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            frame, label, (x1 + 2, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA
        )

    # Apply overlay
    cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)


def draw_zones(frame: np.ndarray, zones: List[dict], violated_zones: set = None, time_ms: int = 0):
    """Draw zone polygons on the frame using custom zone color.

    Args:
        frame: Video frame (numpy array)
        zones: List of zone dicts with vertices, color, risk_level, name
        violated_zones: Set of zone IDs currently violated (these get highlighting)
        time_ms: Current time in ms for pulsing animation
    """
    import time as time_module
    from polygon import compute_centroid

    if violated_zones is None:
        violated_zones = set()

    if not zones:
        return

    h, w = frame.shape[:2]
    # 1. First pass: Draw all semi-transparent fills on a copy of the frame
    overlay = frame.copy()
    has_zones = False
    for zone in zones:
        vertices = zone.get("vertices", [])
        if not vertices or len(vertices) < 3:
            continue
        
        has_zones = True
        color_hex = zone.get("color", "#FF0000").lstrip("#")
        try:
            r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
            fill_color = (b, g, r)
        except:
            fill_color = (0, 0, 200)
            
        pts = np.array([[int(v[0] * w), int(v[1] * h)] for v in vertices], dtype=np.int32)
        cv2.fillPoly(overlay, [pts], fill_color)

    if has_zones:
        # Blend fills (0.3 opacity)
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

    # Draw solid borders and labels on top (always 100% opaque)
    for zone in zones:
        vertices = zone.get("vertices", [])
        if not vertices or len(vertices) < 3:
            continue

        zid = zone.get("id")
        risk = zone.get("risk_level", "high")
        name = zone.get("name", "Zone")
        color_hex = zone.get("color", "#FF0000")
        is_violated = zid in violated_zones

        try:
            color_hex = color_hex.lstrip("#")
            r_v = int(color_hex[0:2], 16)
            g_v = int(color_hex[2:4], 16)
            b_v = int(color_hex[4:6], 16)
            border_color = (b_v, g_v, r_v)
        except (ValueError, IndexError):
            border_color = (0, 0, 255) if risk == "high" else (0, 255, 255)

        pts = np.array([[int(v[0] * w), int(v[1] * h)] for v in vertices], dtype=np.int32)

        if is_violated:
            # Highlighted: brighter color + thicker border + pulsing
            pulse = 0.7 + 0.3 * abs(time_module.sin(time_module.time() * 3))
            r_b = min(255, int(r_v * (1 + 0.5 * pulse)))
            g_b = min(255, int(g_v * (1 + 0.5 * pulse)))
            b_b = min(255, int(b_v * (1 + 0.5 * pulse)))
            highlight_color = (b_b, g_b, r_b)
            cv2.polylines(frame, [pts], True, highlight_color, 3, cv2.LINE_AA)

            # Draw "!" warning badge
            cx_label = int(sum(v[0] for v in vertices) / len(vertices) * w)
            cy_label = int(sum(v[1] for v in vertices) / len(vertices) * h)
            cv2.circle(frame, (cx_label + 40, cy_label - 30), 12, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(frame, "!", (cx_label + 36, cy_label - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
        else:
            cv2.polylines(frame, [pts], True, border_color, 2, cv2.LINE_AA)

        # Draw Label
        centroid = compute_centroid(vertices)
        cx, cy = int(centroid[0] * w), int(centroid[1] * h)
        label = f"{name} ({risk.upper()})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

        cv2.rectangle(frame, (cx - tw // 2 - 4, cy - th - 6), (cx + tw // 2 + 4, cy + 4), (0, 0, 0), -1)
        cv2.putText(frame, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, border_color, 1, cv2.LINE_AA)


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
