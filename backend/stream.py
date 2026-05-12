"""
SIEWS+ 5.0 — MJPEG Stream + YOLO Inference + Zone Violation Check
Core detection and streaming pipeline.
Clean architecture: StreamManager orchestrates, modules handle specific concerns.
"""
import os
import cv2
import json
import time
import asyncio
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional, Set

from detector import MultiStagePipeline
from drawing import draw_detections, draw_zones
from violation_checker import ViolationChecker
from polygon import parse_vertices
from face_manager import face_manager
from ocr_engine import ocr_engine
from database import SessionLocal
from models import Zone, Alert, Setting
from config import SNAPSHOT_DIR


class StreamManager:
    """
    Manages camera stream, YOLO detection, and zone violation pipeline.

    Responsibilities:
    - Camera capture and frame management
    - Detection orchestration (delegate to detector)
    - Violation checking (delegate to ViolationChecker)
    - MJPEG stream generation
    - WebSocket client management
    - Alert handling and notification
    """

    def __init__(self):
        self.detector: Optional[MultiStagePipeline] = None
        self.pipeline: Optional[MultiStagePipeline] = None
        self.violation_checker = ViolationChecker(cooldown_seconds=5)
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.ws_clients: Set = set()
        self.running = False

        # Detection results (shared state)
        self._last_persons: List[dict] = []
        self._last_hazards: List[dict] = []
        self._last_road: List[dict] = []
        self._last_safety_cones: List[dict] = []

        # Settings
        self._camera_source = "0"
        self._confidence = 0.5
        self._detection_interval = 3
        self._notify_cooldown = 5

        # Simulation mode
        self.simulation_frame: Optional[np.ndarray] = None
        self.simulation_cap: Optional[cv2.VideoCapture] = None

        # Current JPEG frame (for MJPEG)
        self.frame: Optional[bytes] = None

    def load_settings(self):
        """Load settings from database."""
        db = SessionLocal()
        try:
            settings = {s.key: s.value for s in db.query(Setting).all()}
            self._camera_source = settings.get("camera_source", "0")
            self._confidence = float(settings.get("confidence_threshold", "0.5"))
            self._detection_interval = int(settings.get("detection_interval", "3"))
        finally:
            db.close()

    def init_detector(self):
        """Initialize or reinitialize the YOLO detector."""
        self.detector = MultiStagePipeline(confidence=self._confidence)
        self.pipeline = self.detector

    def init_pipeline(self):
        """Alias for init_detector."""
        self.init_detector()

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

    # =========================================================================
    # MJPEG Streaming
    # =========================================================================

    def get_frame(self) -> bytes:
        """Returns the current frame as encoded JPEG bytes."""
        if self.frame is None:
            black = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(black, "INITIALIZING...", (180, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            _, jp = cv2.imencode(".jpg", black)
            return jp.tobytes()
        return self.frame

    def generate_frames(self):
        """Generator for MJPEG video stream."""
        print("[STREAM] MJPEG Stream client connected")
        while True:
            frame = self.get_frame()
            if not frame:
                time.sleep(0.1)
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
            )
            time.sleep(0.04)  # ~25 FPS

    # =========================================================================
    # Zone Management
    # =========================================================================

    def get_active_zones(self) -> List[dict]:
        """Get all active zones from database."""
        db = SessionLocal()
        try:
            zones = db.query(Zone).filter(Zone.active == True).all()
            return [
                {
                    "id": z.id,
                    "name": z.name,
                    "vertices": parse_vertices(z.vertices_json),
                    "color": z.color,
                    "risk_level": z.risk_level,
                }
                for z in zones
            ]
        finally:
            db.close()

    # =========================================================================
    # Detection
    # =========================================================================

    def _run_detection(self, frame: np.ndarray):
        """
        Run full detection pipeline on a frame.
        Updates internal state with detection results.
        """
        h, w = frame.shape[:2]

        # Phase 1: Base detection (person, env, road, safety cones)
        (self._last_persons, self._last_hazards,
         self._last_road, self._last_safety_cones) = self.detector.detect_base(frame)

        # Phase 2: OCR scan (always run)
        all_found_codes = ocr_engine.read_all_codes_multi(frame)
        matched_codes = set()

        if self._last_persons:
            # Phase 3: PPE detection for persons
            self._last_persons = self.detector.detect_ppe_full_frame(frame, self._last_persons)

            # Face recognition
            person_bboxes = [p["bbox"] for p in self._last_persons]
            face_results = face_manager.recognize_faces(frame, person_bboxes)

            # Assign face/OCR identity to each person
            for i, det in enumerate(self._last_persons):
                det["face_name"] = "Unknown"
                det["ocr_code"] = None

                if i < len(face_results):
                    det["face_name"] = face_results[i].get("name", "Unknown")

                # Find matching OCR for this person
                px1, py1, px2, py2 = det["bbox"]
                for code_entry in all_found_codes:
                    cx1, cy1, cx2, cy2 = code_entry["bbox"]
                    if px1 <= (cx1 + cx2) / 2 <= px2 and py1 <= (cy1 + cy2) / 2 <= py2:
                        det["ocr_code"] = code_entry["code"]
                        matched_codes.add(code_entry["code"])
                        break

                # Smart fallback: lookup name from code
                if det["face_name"] == "Unknown" and det["ocr_code"]:
                    for p in face_manager._registered:
                        if p.get("code") == det["ocr_code"]:
                            det["face_name"] = p["name"]
                            break

            # Phase 4: Create virtual persons for unmatched OCR codes
            for code_entry in all_found_codes:
                if code_entry["code"] not in matched_codes:
                    v_name = "Unknown"
                    for p in face_manager._registered:
                        if p.get("code") == code_entry["code"]:
                            v_name = p["name"]
                            break

                    self._last_persons.append({
                        "bbox": code_entry["bbox"],
                        "label": "person",
                        "confidence": code_entry["confidence"],
                        "face_name": v_name,
                        "ocr_code": code_entry["code"],
                        "ppe_result": {}
                    })
                    matched_codes.add(code_entry["code"])

        # Log detection summary (only if something detected)
        if (self._last_persons or self._last_hazards or
                self._last_road or self._last_safety_cones):
            print(f"[DETECTOR] Detected: "
                  f"{len(self._last_persons)} people, "
                  f"{len(self._last_hazards)} env, "
                  f"{len(self._last_road)} road, "
                  f"{len(self._last_safety_cones)} safety-cones")

    # =========================================================================
    # Violation Handling
    # =========================================================================

    async def _handle_violation(self, frame: np.ndarray, violation):
        """Handle a detected violation: save snapshot, log alert, notify."""
        zone_id = violation.zone_id
        zone_name = violation.zone_name
        risk_level = violation.risk_level

        # Check cooldown
        if not self.violation_checker.should_alert(zone_id):
            return

        try:
            # Save snapshot
            now_utc = datetime.now(timezone.utc)
            timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"{timestamp_str}_{zone_id}.jpg"
            snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_filename)
            cv2.imwrite(snapshot_path, frame)
            print(f"[ALERT-FLOW] Snapshot saved: {snapshot_path}")

            # Log to database
            shutdown_triggered = (risk_level == "high")
            db = SessionLocal()
            alert_id = 0
            try:
                alert = Alert(
                    zone_id=zone_id,
                    confidence=violation.confidence,
                    snapshot_path=f"static/snapshots/{snapshot_filename}",
                    timestamp=now_utc,
                    shutdown_triggered=shutdown_triggered,
                    resolved=False,
                    violation_type=violation.violation_type,
                    person_name=violation.person_name,
                    uniform_code=violation.uniform_code,
                )
                db.add(alert)
                db.commit()
                db.refresh(alert)
                alert_id = alert.id
                print(f"[ALERT-FLOW] DB Logged (ID: {alert_id})")

                if shutdown_triggered:
                    from shutdown import log_shutdown, trigger_relay
                    log_shutdown(db, zone_id, trigger_source="auto")
                    trigger_relay(zone_name)
                    print(f"[ALERT-FLOW] Shutdown triggered")

                settings = {s.key: s.value for s in db.query(Setting).all()}
            except Exception as dbe:
                print(f"[ALERT-FLOW] DB Error: {dbe}")
                db.rollback()
                settings = {}
            finally:
                db.close()

            # WhatsApp notification
            fonnte_token = settings.get("fonnte_token", "")
            recipients = settings.get("recipients", "")
            facility_name = settings.get("facility_name", "Offshore Platform A")
            recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]

            if violation.person_name and violation.person_name != "Unknown":
                for p in face_manager._registered:
                    if p["name"].lower() == violation.person_name.lower() and p.get("phone"):
                        if p["phone"] not in recipient_list:
                            recipient_list.append(p["phone"])

            asyncio.create_task(self._send_notifications(
                recipient_list, zone_name, risk_level, violation.confidence,
                shutdown_triggered, facility_name, snapshot_filename,
                violation.person_name, violation.uniform_code
            ))

            # WebSocket broadcast
            ws_event = {
                "type": "alert",
                "alert_id": alert_id,
                "zone_name": zone_name,
                "zone_id": zone_id,
                "risk_level": risk_level,
                "timestamp": now_utc.isoformat(),
                "confidence": violation.confidence,
                "snapshot_url": f"/static/snapshots/{snapshot_filename}",
                "shutdown_triggered": shutdown_triggered,
                "person_name": violation.person_name,
                "uniform_code": violation.uniform_code,
            }
            await self._broadcast_to_ws(ws_event)

        except Exception as e:
            print(f"[ALERT-FLOW] !!! CRITICAL FAIL: {e}")
            import traceback
            traceback.print_exc()

    async def _send_notifications(self, recipients, zone_name, risk_level,
                                   confidence, shutdown_triggered, facility_name,
                                   snapshot_filename, person_name, uniform_code):
        """Send WhatsApp notifications to recipients."""
        from notifier import send_to_all_recipients
        try:
            await send_to_all_recipients(
                ",".join(recipients), zone_name, risk_level, confidence,
                shutdown_triggered, facility_name, "",
                snapshot_url=f"/static/snapshots/{snapshot_filename}",
                person_name=person_name, uniform_code=uniform_code
            )
        except Exception as e:
            print(f"[ALERT-FLOW] Notification error: {e}")

    async def _broadcast_to_ws(self, event):
        """Broadcast event to all WebSocket clients."""
        dead_clients = set()
        for ws in self.ws_clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead_clients.add(ws)
        self.ws_clients -= dead_clients

    # =========================================================================
    # Main Stream Loop
    # =========================================================================

    async def start(self):
        """
        Main generator: capture frames, detect, check violations, yield MJPEG.
        """
        print("[STREAM] Starting stream generator...")
        self.load_settings()

        if not self.detector:
            print("[STREAM] Initializing detector...")
            self.init_detector()

        if not self.open_camera():
            print("[STREAM] Camera opening failed.")
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "KAMERA OFFLINE", (120, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, "Mencoba reconnect...", (150, 270),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA)
            _, jpeg = cv2.imencode(".jpg", frame)
            self.frame = jpeg.tobytes()

        print("[STREAM] Entering main loop...")
        self.running = True
        reconnect_attempts = 0

        while self.running:
            try:
                # Get frame (live, simulation, or offline placeholder)
                ret, frame = self._capture_frame()
                if not ret:
                    reconnect_attempts += 1
                    if reconnect_attempts > 5:
                        self.open_camera()
                        reconnect_attempts = 0
                    await asyncio.sleep(0.5)
                    continue

                reconnect_attempts = 0
                self.frame_count += 1
                h, w = frame.shape[:2]

                # Run detection every N frames
                if self.frame_count % 5 == 0:
                    try:
                        self._run_detection(frame)
                    except Exception as e:
                        print(f"[STREAM] Detection error: {e}")

                # Check violations and trigger alerts
                if self._last_persons and self.frame_count % 5 == 0:
                    violations = self.violation_checker.check_all_violations(
                        self._last_persons, self._last_hazards,
                        self.get_active_zones(), w, h
                    )
                    for v in violations:
                        asyncio.create_task(self._handle_violation(frame.copy(), v))

                # Draw overlays
                zones = self.get_active_zones()
                violation_indices = self.violation_checker.get_violation_indices(
                    self._last_persons, []
                )

                draw_zones(frame, zones)
                draw_detections(
                    frame, self._last_persons, violation_indices,
                    self._last_hazards, self._last_road, self._last_safety_cones
                )

                # Encode and store frame
                _, jpeg = cv2.imencode('.jpg', frame)
                self.frame = jpeg.tobytes()
                await asyncio.sleep(0.01)

            except Exception as e:
                print(f"[STREAM] Main Loop Critical Error: {e}")
                await asyncio.sleep(1)

        if self.cap:
            self.cap.release()

    def _capture_frame(self):
        """Capture a frame from camera, simulation, or return offline frame."""
        if self.simulation_frame is not None:
            return True, self.simulation_frame.copy()

        if self.simulation_cap is not None:
            ret, frame = self.simulation_cap.read()
            if not ret:
                self.simulation_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.simulation_cap.read()
            return ret, frame

        if self.cap is None or not self.cap.isOpened():
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "KAMERA OFFLINE", (120, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, "Mencoba reconnect...", (150, 270),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA)
            return True, frame

        return self.cap.read()


# Singleton instance
stream_manager = StreamManager()
