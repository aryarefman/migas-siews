"""
SIEWS+ 5.0 MJPEG Stream + YOLO Inference + Zone Violation Check
Core detection and streaming pipeline.
"""
import os
import cv2
import json
import time
import asyncio
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional, Set
from detector import UnifiedDetector
from polygon import point_in_polygon, parse_vertices, compute_centroid
from notifier import send_to_all_recipients
from face_manager import face_manager
from ocr_engine import ocr_engine
from go_polygon_client import batch_check_violations_sync
from shutdown import trigger_relay, log_shutdown
from database import SessionLocal
from models import Zone, Alert, Setting
from config import SNAPSHOT_DIR


class StreamManager:
    """Manages camera stream, YOLO detection, and zone violation pipeline."""

    def __init__(self):
        self.detector: Optional[UnifiedDetector] = None
        self.pipeline: Optional[UnifiedDetector] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.zone_cooldowns: dict = {}  # zone_id -> last_alert_timestamp
        self.ws_clients: Set = set()
        self.running = False
        self._last_persons: List[dict] = []
        self._last_hazards: List[dict] = []
        self._camera_source = "0"
        self._confidence = 0.5
        self._detection_interval = 3
        self._notify_cooldown = 300
        self.frame = None  # Storage for the current JPEG frame
        self.simulation_frame: Optional[np.ndarray] = None  # For test simulation
        self.simulation_cap: Optional[cv2.VideoCapture] = None  # For video simulation
        self.simulation_path: Optional[str] = None

    def load_settings(self):
        """Load settings from database."""
        db = SessionLocal()
        try:
            settings = {s.key: s.value for s in db.query(Setting).all()}
            self._camera_source = settings.get("camera_source", "0")
            self._confidence = float(settings.get("confidence_threshold", "0.5"))
            self._detection_interval = int(settings.get("detection_interval", "3"))
            self._notify_cooldown = 5  # Force 5 seconds for testing
        finally:
            db.close()

    def init_detector(self):
        """Initialize or reinitialize the YOLO detector."""
        from detector import MultiStagePipeline
        self.detector = MultiStagePipeline(confidence=self._confidence)
        self.pipeline = self.detector

    def init_pipeline(self):
        """Alias for init_detector for compatibility."""
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

    def get_frame(self):
        """Returns the current frame as encoded bytes."""
        if self.frame is None:
            # Placeholder for black frame
            black = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(black, "INITIALIZING...", (180, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2)
            _, jp = cv2.imencode(".jpg", black)
            return jp.tobytes()
        return self.frame

    def generate_frames(self):
        """Generator for the MJPEG video stream."""
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
            # Control frame rate for clients
            time.sleep(0.04)

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
            if not vertices:
                continue
                
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

    def draw_persons(self, frame: np.ndarray, persons: List[dict], violations: set = None):
        """Wrapper for drawing persons for compatibility."""
        self.draw_detections(frame, persons, violations or set(), [])

    def draw_env(self, frame: np.ndarray, hazards: List[dict]):
        """Wrapper for drawing environmental hazards for compatibility."""
        self.draw_detections(frame, [], set(), hazards)

    def draw_road(self, frame: np.ndarray, hazards: List[dict]):
        """Alias for draw_env for road/general hazards."""
        self.draw_env(frame, hazards)

    def draw_detections(self, frame: np.ndarray, detections: List[dict], violations: set, hazards: List[dict]):
        """Draw bounding boxes with full 3-stage detection info."""
        # 1. Draw Hazards (Stage 3: Environment)
        for haz in hazards:
            x1, y1, x2, y2 = [int(v) for v in haz["bbox"]]
            label = f"DANGER: {haz['label'].upper()} {haz['confidence']:.0%}"
            color = (0, 0, 255)  # Red for hazards
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # 2. Draw People (Stage 1: Person + Stage 2: PPE)
        for i, det in enumerate(detections):
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            conf = det["confidence"]
            ppe_result = det.get("ppe_result", {})
            
            # Build PPE status string from Stage 2 results
            ppe_parts = []
            if ppe_result:
                if ppe_result.get("has_helmet"): ppe_parts.append("Helm ✓")
                if ppe_result.get("has_vest"): ppe_parts.append("Vest ✓")
                if ppe_result.get("has_harness"): ppe_parts.append("Harness ✓")
                # Show raw detected items for extra detail
                raw = ppe_result.get("raw_labels", [])
                for lbl in raw:
                    if "gloves" in lbl: ppe_parts.append("Gloves ✓")
                    if "boots" in lbl: ppe_parts.append("Boots ✓")
                    if "goggles" in lbl: ppe_parts.append("Goggles ✓")
            
            ppe_str = ", ".join(ppe_parts) if ppe_parts else "No PPE"
            
            # Add identification info
            id_str = ""
            if det.get("face_name") and det["face_name"] != "Unknown":
                id_str = f" [{det['face_name']}]"
            elif det.get("ocr_code"):
                id_str = f" [ID:{det['ocr_code']}]"

            if i in violations:
                color = (0, 0, 255)  # Red for Danger
                label = f"BAHAYA {conf:.0%}{id_str}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
                
                # Identification label
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(frame, (x1, y1 - th - 12), (x1 + tw + 10, y1), color, -1)
                cv2.putText(frame, label, (x1 + 5, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
                
                # PPE status below
                (tw2, th2), _ = cv2.getTextSize(ppe_str, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                cv2.rectangle(frame, (x1, y2), (x1 + tw2 + 8, y2 + th2 + 10), (0, 0, 0), -1)
                cv2.putText(frame, ppe_str, (x1 + 4, y2 + th2 + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)
            else:
                color = (0, 255, 0)  # Green
                label = f"Person {conf:.0%}{id_str}"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                # Main label
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
                cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), (0, 0, 0), -1)
                cv2.putText(frame, label, (x1 + 2, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
                # PPE label below
                (tw2, th2), _ = cv2.getTextSize(ppe_str, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
                cv2.rectangle(frame, (x1, y2), (x1 + tw2 + 6, y2 + th2 + 8), (0, 0, 0), -1)
                cv2.putText(frame, ppe_str, (x1 + 3, y2 + th2 + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 200, 0), 1, cv2.LINE_AA)

    async def handle_violation(self, frame: np.ndarray, zone: dict, confidence: float, person_name: str = None, uniform_code: str = None):
        """Handle a zone violation: save snapshot, log alert, notify, trigger shutdown."""
        try:
            from datetime import datetime, timezone, timedelta
            zone_id = zone["id"]
            zone_name = zone["name"]
            risk_level = zone["risk_level"]
            now = time.time()

            # 1. Check cooldown
            last_alert = self.zone_cooldowns.get(zone_id, 0)
            if now - last_alert < self._notify_cooldown:
                return

            self.zone_cooldowns[zone_id] = now
            print(f"[ALERT-FLOW] 1. Starting alert process for {zone_name}...")

            # 2. Save snapshot
            now_utc = datetime.now(timezone.utc)
            timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"{timestamp_str}_{zone_id}.jpg"
            snapshot_path = f"static/snapshots/{snapshot_filename}"
            full_path = os.path.join(SNAPSHOT_DIR, snapshot_filename)
            cv2.imwrite(full_path, frame)
            print(f"[ALERT-FLOW] 2. Snapshot saved: {snapshot_path}")

            # 3. DB Logging
            shutdown_triggered = (risk_level == "high")
            db = SessionLocal()
            alert_id = 0
            try:
                alert = Alert(
                    zone_id=zone_id,
                    confidence=confidence,
                    snapshot_path=snapshot_path,
                    timestamp=now_utc,
                    shutdown_triggered=shutdown_triggered,
                    resolved=False,
                    violation_type="restricted_area",
                    person_name=person_name,
                    uniform_code=uniform_code,
                )
                db.add(alert)
                db.commit()
                db.refresh(alert)
                alert_id = alert.id
                print(f"[ALERT-FLOW] 3. DB Logged (ID: {alert_id})")

                if shutdown_triggered:
                    from shutdown import log_shutdown, trigger_relay
                    log_shutdown(db, zone_id, trigger_source="auto")
                    trigger_relay(zone_name)
                    print(f"[ALERT-FLOW] 4. Shutdown triggered")

                settings = {s.key: s.value for s in db.query(Setting).all()}
            except Exception as dbe:
                print(f"[ALERT-FLOW] !!! DB Error: {dbe}")
                db.rollback()
                settings = {}
            finally:
                db.close()

            # 4. WhatsApp Notification (Async Task)
            fonnte_token = settings.get("fonnte_token", "")
            recipients = settings.get("recipients", "")
            facility_name = settings.get("facility_name", "Offshore Platform A")

            recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]
            if person_name and person_name != "Unknown":
                from face_manager import face_manager
                for p in face_manager._registered:
                    if p["name"].lower() == person_name.lower() and p.get("phone"):
                        if p["phone"] not in recipient_list:
                            recipient_list.append(p["phone"])
                            print(f"[ALERT-FLOW] 5. Added direct phone for {person_name}")
            
            final_recipients = ",".join(recipient_list)
            asyncio.create_task(
                send_to_all_recipients(
                    final_recipients, zone_name, risk_level, confidence,
                    shutdown_triggered, facility_name, fonnte_token,
                    snapshot_url=f"/static/snapshots/{snapshot_filename}",
                    person_name=person_name, uniform_code=uniform_code
                )
            )

            # 5. WebSocket Broadcast
            ws_event = {
                "type": "alert",
                "alert_id": alert_id,
                "zone_name": zone_name,
                "zone_id": zone_id,
                "risk_level": risk_level,
                "timestamp": now_utc.isoformat(),
                "confidence": confidence,
                "snapshot_url": f"/{snapshot_path}",
                "shutdown_triggered": shutdown_triggered,
                "person_name": person_name,
                "uniform_code": uniform_code,
            }
            
            dead_clients = set()
            for ws in self.ws_clients:
                try:
                    await ws.send_json(ws_event)
                except Exception:
                    dead_clients.add(ws)
            self.ws_clients -= dead_clients
            print(f"[ALERT-FLOW] 6. Broadcast sent to {len(self.ws_clients)} clients")

        except Exception as e:
            print(f"[ALERT-FLOW] !!! CRITICAL FAIL: {e}")
            import traceback
            traceback.print_exc()

    async def start(self):
        """
        Main generator: capture frames, detect, check zones, yield MJPEG.
        """
        print("[STREAM] Starting stream generator...")
        self.load_settings()
        
        if not self.detector:
            print("[STREAM] Initializing detector...")
            self.init_detector()

        if not self.open_camera():
            print("[STREAM] Camera opening failed.")
            # Storage for "no camera" frame
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "KAMERA OFFLINE", (120, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3, cv2.LINE_AA)
            cv2.putText(frame, "Mencoba reconnect...", (150, 270),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA)
            _, jpeg = cv2.imencode(".jpg", frame)
            self.frame = jpeg.tobytes()
            # We don't yield here, we just wait for the main loop to handle it or retry

        print("[STREAM] Entering main loop...")
        self.running = True
        reconnect_attempts = 0
        while self.running:
            try:
                if self.simulation_frame is not None:
                    # STATIC SIMULATION: Use the static injected frame
                    frame = self.simulation_frame.copy()
                    ret = True
                    await asyncio.sleep(0.05)
                elif self.simulation_cap is not None:
                    # VIDEO SIMULATION: Read from video file
                    ret, frame = self.simulation_cap.read()
                    if not ret:
                        # Loop video
                        self.simulation_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = self.simulation_cap.read()
                    await asyncio.sleep(0.02) # Control playback speed
                else:
                    # LIVE MODE: read from camera
                    ret, frame = self.cap.read()
                    
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

                # Get active zones
                zones = self.get_active_zones()

                # Run detection on every Nth frame
                if self.frame_count % 5 == 0:
                    try:
                        from face_manager import face_manager
                        from ocr_engine import ocr_engine
                        
                        # Phase 1: YOLO Detect (People & Hazards)
                        self._last_persons, self._last_hazards = self.detector.detect_base(frame)
                        
                        # Phase 2: Multi-OCR Scan (Always run this now)
                        all_found_codes = ocr_engine.read_all_codes_multi(frame)
                        matched_codes = set()

                        if self._last_persons:
                            # Phase 3: PPE & Face for detected people
                            self._last_persons = self.detector.detect_ppe_full_frame(frame, self._last_persons)
                            person_bboxes = [p["bbox"] for p in self._last_persons]
                            face_results = face_manager.recognize_faces(frame, person_bboxes)
                            
                            for i, det in enumerate(self._last_persons):
                                det["face_name"] = "Unknown"
                                det["ocr_code"] = None
                                if i < len(face_results):
                                    det["face_name"] = face_results[i].get("name", "Unknown")
                                
                                # Find matching OCR from full-frame results for this person
                                px1, py1, px2, py2 = det["bbox"]
                                for code_entry in all_found_codes:
                                    cx1, cy1, cx2, cy2 = code_entry["bbox"]
                                    # If OCR center is inside person box
                                    if px1 <= (cx1+cx2)/2 <= px2 and py1 <= (cy1+cy2)/2 <= py2:
                                        det["ocr_code"] = code_entry["code"]
                                        matched_codes.add(code_entry["code"])
                                        break
                                
                                # SMART FALLBACK: lookup name from code
                                if det["face_name"] == "Unknown" and det["ocr_code"]:
                                    for p in face_manager._registered:
                                        if p.get("code") == det["ocr_code"]:
                                            det["face_name"] = p["name"]
                                            break

                        # Phase 4: Create Virtual Persons for unmatched OCR codes
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

                    except Exception as e:
                        print(f"[STREAM] Detection error: {e}")

                # Check violations
                violations = set()
                
                # Dynamic Hazards
                for haz in self._last_hazards:
                    hx1, hy1, hx2, hy2 = haz["bbox"]
                    for i, det in enumerate(self._last_persons):
                        x1, y1, x2, y2 = det["bbox"]
                        px, py = (x1 + x2) / 2, (y1 + y2) / 2
                        if hx1 <= px <= hx2 and hy1 <= py <= hy2:
                            violations.add(i)
                            hazard_zone = {"id": 999, "name": f"Area Berbahaya ({haz['label']})", "risk_level": "high"}
                            asyncio.create_task(self.handle_violation(frame.copy(), hazard_zone, det["confidence"], 
                                                       person_name=det.get("face_name"), 
                                                       uniform_code=det.get("ocr_code")))

                # Static Zones
                for i, det in enumerate(self._last_persons):
                    x1, y1, x2, y2 = det["bbox"]
                    head_p = [(x1 + x2) / 2 / w, (y1 + (y2-y1)*0.2) / h]
                    chest_p = [(x1 + x2) / 2 / w, (y1 + y2) / 2 / h]
                    feet_p = [(x1 + x2) / 2 / w, (y2 - 2) / h]
                    
                    for z in zones:
                        is_inside = False
                        from polygon import point_in_polygon
                        if point_in_polygon(head_p, z["vertices"]) or point_in_polygon(chest_p, z["vertices"]) or point_in_polygon(feet_p, z["vertices"]):
                            is_inside = True
                        
                        if is_inside:
                            violations.add(i)
                            zone_info = {"id": z["id"], "name": z["name"], "risk_level": z["risk_level"]}
                            asyncio.create_task(self.handle_violation(frame.copy(), zone_info, det["confidence"], 
                                                       person_name=det.get("face_name"), 
                                                       uniform_code=det.get("ocr_code")))

                # Draw Visuals
                self.draw_zones(frame, zones)
                self.draw_detections(frame, self._last_persons, violations, self._last_hazards)
                
                # Final Encoding
                _, jpeg = cv2.imencode('.jpg', frame)
                self.frame = jpeg.tobytes()
                await asyncio.sleep(0.01)

            except Exception as e:
                print(f"[STREAM] Main Loop Critical Error: {e}")
                await asyncio.sleep(1)
        
        self.cap.release()


# Singleton
stream_manager = StreamManager()
