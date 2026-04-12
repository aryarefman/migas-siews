"""
SIEWS+ 5.0 MJPEG Stream + YOLO Inference + Zone Violation Check
Core detection and streaming pipeline.
"""
import cv2
import json
import time
import asyncio
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional, Set
from detector import PersonDetector
from polygon import point_in_polygon, parse_vertices, compute_centroid
from notifier import send_to_all_recipients
from shutdown import trigger_relay, log_shutdown
from database import SessionLocal
from models import Zone, Alert, Setting


class StreamManager:
    """Manages camera stream, YOLO detection, and zone violation pipeline."""

    def __init__(self):
        self.detector: Optional[PersonDetector] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.zone_cooldowns: dict = {}  # zone_id -> last_alert_timestamp
        self.ws_clients: Set = set()
        self.running = False
        self._last_detections: List[dict] = []
        self._camera_source = "0"
        self._confidence = 0.5
        self._detection_interval = 3
        self._notify_cooldown = 300

    def load_settings(self):
        """Load settings from database."""
        db = SessionLocal()
        try:
            settings = {s.key: s.value for s in db.query(Setting).all()}
            self._camera_source = settings.get("camera_source", "0")
            self._confidence = float(settings.get("confidence_threshold", "0.5"))
            self._detection_interval = int(settings.get("detection_interval", "3"))
            self._notify_cooldown = int(settings.get("notify_cooldown", "300"))
        finally:
            db.close()

    def init_detector(self):
        """Initialize or reinitialize the YOLO detector."""
        self.detector = PersonDetector(confidence=self._confidence)

    def open_camera(self):
        """Open or reopen the camera source."""
        if self.cap is not None:
            self.cap.release()

        source = self._camera_source
        if source.isdigit():
            source = int(source)

        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            print(f"[STREAM] Failed to open camera source: {self._camera_source}")
            self.cap = None
            return False

        print(f"[STREAM] Camera opened: {self._camera_source}")
        return True

    def get_active_zones(self) -> List[dict]:
        """Get all active zones from DB."""
        db = SessionLocal()
        try:
            zones = db.query(Zone).filter(Zone.active == True).all()
            result = []
            for z in zones:
                result.append({
                    "id": z.id,
                    "name": z.name,
                    "vertices": parse_vertices(z.vertices_json),
                    "color": z.color,
                    "risk_level": z.risk_level,
                })
            return result
        finally:
            db.close()

    def draw_zones(self, frame: np.ndarray, zones: List[dict]):
        """Draw all active zone polygons on the frame."""
        h, w = frame.shape[:2]
        overlay = frame.copy()

        for zone in zones:
            vertices = zone["vertices"]
            risk = zone["risk_level"]
            name = zone["name"]

            # Convert normalized coords to pixel coords
            pts = np.array([[int(v[0] * w), int(v[1] * h)] for v in vertices], dtype=np.int32)

            if risk == "high":
                fill_color = (0, 0, 200)     # Red BGR
                border_color = (0, 0, 255)
            else:
                fill_color = (0, 200, 200)    # Yellow BGR
                border_color = (0, 255, 255)

            # Semi-transparent fill
            cv2.fillPoly(overlay, [pts], fill_color)
            # Border
            cv2.polylines(frame, [pts], True, border_color, 2, cv2.LINE_AA)

            # Zone name label at centroid
            centroid = compute_centroid(vertices)
            cx, cy = int(centroid[0] * w), int(centroid[1] * h)
            label = f"{name} ({risk.upper()})"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (cx - tw // 2 - 4, cy - th - 6), (cx + tw // 2 + 4, cy + 4), (0, 0, 0), -1)
            cv2.putText(frame, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, border_color, 1, cv2.LINE_AA)

        # Blend overlay with transparency
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

    def draw_detections(self, frame: np.ndarray, detections: List[dict], violations: set):
        """Draw bounding boxes on frame. Red for violations, green for safe."""
        for i, det in enumerate(detections):
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            conf = det["confidence"]

            if i in violations:
                color = (0, 0, 255)  # Red
                label = f"BAHAYA {conf:.0%}"
                # Draw thicker box for violations
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                # Label background
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), (0, 0, 255), -1)
                cv2.putText(frame, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            else:
                color = (0, 255, 0)  # Green
                label = f"Person {conf:.0%}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), (0, 0, 0), -1)
                cv2.putText(frame, label, (x1 + 2, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    async def handle_violation(self, frame: np.ndarray, zone: dict, confidence: float):
        """Handle a zone violation: save snapshot, log alert, notify, trigger shutdown."""
        zone_id = zone["id"]
        zone_name = zone["name"]
        risk_level = zone["risk_level"]
        now = time.time()

        # Check cooldown
        last_alert = self.zone_cooldowns.get(zone_id, 0)
        if now - last_alert < self._notify_cooldown:
            return

        self.zone_cooldowns[zone_id] = now

        # Save snapshot
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        snapshot_filename = f"{timestamp_str}_{zone_id}.jpg"
        snapshot_path = f"static/snapshots/{snapshot_filename}"

        from config import SNAPSHOT_DIR
        import os
        full_path = os.path.join(SNAPSHOT_DIR, snapshot_filename)
        cv2.imwrite(full_path, frame)

        # Determine if shutdown should be triggered
        shutdown_triggered = (risk_level == "high")

        # Log to database
        db = SessionLocal()
        try:
            alert = Alert(
                zone_id=zone_id,
                confidence=confidence,
                snapshot_path=snapshot_path,
                timestamp=datetime.now(timezone.utc),
                shutdown_triggered=shutdown_triggered,
                resolved=False,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            alert_id = alert.id

            # Log shutdown if high risk
            if shutdown_triggered:
                log_shutdown(db, zone_id, trigger_source="auto")
                trigger_relay(zone_name)

            # Get settings for notification
            settings = {s.key: s.value for s in db.query(Setting).all()}
        finally:
            db.close()

        # Send WhatsApp notification (async, non-blocking)
        fonnte_token = settings.get("fonnte_token", "")
        recipients = settings.get("recipients", "")
        facility_name = settings.get("facility_name", "Offshore Platform A")

        asyncio.create_task(
            send_to_all_recipients(
                recipients, zone_name, risk_level, confidence,
                shutdown_triggered, facility_name, fonnte_token
            )
        )

        # Broadcast WebSocket event
        snapshot_url = f"/static/snapshots/{snapshot_filename}"
        ws_event = {
            "type": "alert",
            "alert_id": alert_id,
            "zone_name": zone_name,
            "zone_id": zone_id,
            "risk_level": risk_level,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence": confidence,
            "snapshot_url": snapshot_url,
            "shutdown_triggered": shutdown_triggered,
        }

        dead_clients = set()
        for ws in self.ws_clients:
            try:
                await ws.send_json(ws_event)
            except Exception:
                dead_clients.add(ws)
        self.ws_clients -= dead_clients

    async def generate_frames(self):
        """
        Main generator: capture frames, detect, check zones, yield MJPEG.
        """
        self.load_settings()
        self.init_detector()

        if not self.open_camera():
            # Yield a "no camera" frame
            while True:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, "KAMERA OFFLINE", (120, 220),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
                cv2.putText(frame, "Mencoba reconnect...", (150, 270),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA)
                _, jpeg = cv2.imencode(".jpg", frame)
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                )
                await asyncio.sleep(2)
                if self.open_camera():
                    break

        self.running = True
        reconnect_attempts = 0

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                reconnect_attempts += 1
                print(f"[STREAM] Frame read failed, attempt {reconnect_attempts}")
                if reconnect_attempts > 10:
                    # Try reopening camera
                    self.open_camera()
                    reconnect_attempts = 0
                await asyncio.sleep(0.5)
                continue

            reconnect_attempts = 0
            self.frame_count += 1
            h, w = frame.shape[:2]

            # Get active zones
            zones = self.get_active_zones()

            # Run detection on every Nth frame
            if self.frame_count % self._detection_interval == 0:
                self._last_detections = self.detector.detect(frame)

            # Check zone violations
            violations = set()  # indices of detections that violate zones
            for i, det in enumerate(self._last_detections):
                # Normalize bottom-center to 0-1
                bcx = det["bottom_center"][0] / w
                bcy = det["bottom_center"][1] / h
                normalized_point = (bcx, bcy)

                for zone in zones:
                    if point_in_polygon(normalized_point, zone["vertices"]):
                        violations.add(i)
                        # Handle violation
                        await self.handle_violation(frame, zone, det["confidence"])

            # Draw zones on frame
            self.draw_zones(frame, zones)

            # Draw detections
            self.draw_detections(frame, self._last_detections, violations)

            # Add SIEWS+ watermark
            cv2.putText(frame, "SIEWS+ 5.0", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            cv2.putText(frame, ts, (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

            # Encode and yield JPEG
            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            )

            # ~30 FPS cap
            await asyncio.sleep(0.033)


# Singleton
stream_manager = StreamManager()
