"""
SIEWS+ 5.0 — MJPEG Stream + Multi-Stage Pipeline + Zone Violation Check

Key upgrades over v1:
- MultiStagePipeline: person → PPE/harness → fire/smoke
- Consistency check: N consecutive frames before alert fires (false positive prevention)
- Object-level crop logging: each detected object saved as crop image
- Multi violation types: restricted_area | missing_ppe | no_harness | fire_smoke | multiple
"""
import cv2
import json
import os
import time
import asyncio
import numpy as np
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Set

from detector import MultiStagePipeline
from polygon import point_in_polygon, parse_vertices, compute_centroid
from notifier import send_to_all_recipients
from shutdown import trigger_relay, log_shutdown
from database import SessionLocal
from models import Zone, Alert, DetectionLog, Setting
from config import SNAPSHOT_DIR
from video_processor import UPLOADS_DIR

# Consistency check: violation must appear in this many consecutive detection
# cycles before triggering an alert (prevents single-frame false positives)
CONSISTENCY_FRAMES_REQUIRED = 4

# Crop directory for object-level snapshots
CROPS_DIR = os.path.join(SNAPSHOT_DIR, "crops")
os.makedirs(CROPS_DIR, exist_ok=True)


class StreamManager:
    """Manages camera stream, multi-stage YOLO detection, and zone violation pipeline."""

    def __init__(self):
        self.pipeline: Optional[MultiStagePipeline] = None
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_count = 0
        self.zone_cooldowns: dict = {}       # zone_id -> last_alert_timestamp
        self.ws_clients: Set = set()
        self.running = False

        # Last pipeline results (reused between detection intervals)
        self._last_persons: List[dict] = []
        self._last_env: List[dict] = []
        self._last_infra: List[dict] = []

        # Consistency tracking: counts consecutive detections per (zone_id, violation_type)
        self._consistency_counters: dict = defaultdict(int)

        # Settings
        self._camera_source = "0"
        self._confidence = 0.3
        self._detection_interval = 3
        self._notify_cooldown = 300

    def load_settings(self):
        db = SessionLocal()
        try:
            settings = {s.key: s.value for s in db.query(Setting).all()}
            self._camera_source = settings.get("camera_source", "0")
            self._confidence = float(settings.get("confidence_threshold", "0.3"))
            self._detection_interval = int(settings.get("detection_interval", "3"))
            self._notify_cooldown = int(settings.get("notify_cooldown", "300"))
        finally:
            db.close()

    def init_pipeline(self, force: bool = False):
        if self.pipeline is not None and not force:
            return
        self.pipeline = MultiStagePipeline(
            confidence=self._confidence,
            ppe_confidence=0.01,
        )

    def open_camera(self) -> bool:
        if self.cap is not None:
            self.cap.release()
        source = self._camera_source
        if source.isdigit():
            source = int(source)
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            print(f"[STREAM] Failed to open camera: {self._camera_source}")
            self.cap = None
            return False
        print(f"[STREAM] Camera opened: {self._camera_source}")
        return True

    def get_active_zones(self) -> List[dict]:
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

    # ─── Crop Helpers ──────────────────────────────────────────────────────────

    def _save_crop(self, frame: np.ndarray, bbox: List[int], prefix: str) -> Optional[str]:
        """Crop a bounding box from frame and save as JPEG. Returns relative path."""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{prefix}_{ts}.jpg"
        full_path = os.path.join(CROPS_DIR, filename)
        cv2.imwrite(full_path, crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return f"static/snapshots/crops/{filename}"

    def _log_detection_crops(
        self,
        db,
        frame: np.ndarray,
        alert_id: int,
        persons: List[dict],
        env: List[dict],
        frame_number: int,
    ):
        """Save per-object crops and write DetectionLog entries."""
        for person in persons:
            # Log person crop
            crop_path = self._save_crop(frame, person["bbox"], "person")
            db.add(DetectionLog(
                alert_id=alert_id,
                class_name="person",
                confidence=person["confidence"],
                crop_path=crop_path,
                frame_number=frame_number,
                bbox_json=json.dumps(person["bbox"]),
            ))
            # Log each PPE violation as separate crop
            for viol in person.get("ppe_violations", []):
                db.add(DetectionLog(
                    alert_id=alert_id,
                    class_name=viol,
                    confidence=person["ppe"].get(viol, {}).get("confidence", 0.0),
                    crop_path=crop_path,  # same person crop
                    frame_number=frame_number,
                    bbox_json=json.dumps(person["bbox"]),
                ))
        for det in env:
            crop_path = self._save_crop(frame, det["bbox"], det["class_name"])
            db.add(DetectionLog(
                alert_id=alert_id,
                class_name=det["class_name"],
                confidence=det["confidence"],
                crop_path=crop_path,
                frame_number=frame_number,
                bbox_json=json.dumps(det["bbox"]),
            ))
        db.commit()

    # ─── Violation Detection ───────────────────────────────────────────────────

    def _determine_violation_type(self, person: dict, in_zone: bool) -> Optional[str]:
        """Determine the primary violation type for a person detection."""
        violations = []
        if in_zone:
            violations.append("restricted_area")
        viols = person.get("ppe_violations", [])
        if "no_helmet" in viols or "no_vest" in viols:
            violations.append("missing_ppe")
        if "no_harness" in viols:
            violations.append("no_harness")
        if not violations:
            return None
        if len(violations) > 1:
            return "multiple"
        return violations[0]

    def _check_consistency(self, key: str, is_active: bool) -> bool:
        """
        Track consecutive detection count for a key.
        Returns True only when threshold is first reached (edge trigger).
        Resets counter when violation disappears.
        """
        if is_active:
            self._consistency_counters[key] += 1
            return self._consistency_counters[key] == CONSISTENCY_FRAMES_REQUIRED
        else:
            self._consistency_counters[key] = 0
            return False

    # ─── Alert Handler ─────────────────────────────────────────────────────────

    async def handle_violation(
        self,
        frame: np.ndarray,
        zone: dict,
        confidence: float,
        violation_type: str,
        persons_in_violation: List[dict],
        env_detections: List[dict],
    ):
        """Save snapshot, log alert + crops, notify, trigger shutdown."""
        zone_id = zone["id"]
        zone_name = zone["name"]
        risk_level = zone["risk_level"]
        now = time.time()

        cooldown_key = f"{zone_id}_{violation_type}"
        last_alert = self.zone_cooldowns.get(cooldown_key, 0)
        if now - last_alert < self._notify_cooldown:
            return

        self.zone_cooldowns[cooldown_key] = now

        # Full-frame snapshot
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        snap_filename = f"{ts_str}_{zone_id}_{violation_type}.jpg"
        snap_full = os.path.join(SNAPSHOT_DIR, snap_filename)
        cv2.imwrite(snap_full, frame)
        snapshot_path = f"static/snapshots/{snap_filename}"

        shutdown_triggered = (risk_level == "high") and (
            violation_type in {"restricted_area", "no_harness", "multiple"}
        )

        # Build PPE detail JSON
        ppe_detail = {}
        for p in persons_in_violation:
            for cls_name, info in p.get("ppe", {}).items():
                ppe_detail[cls_name] = round(info["confidence"], 3)

        db = SessionLocal()
        try:
            alert = Alert(
                zone_id=zone_id,
                confidence=confidence,
                snapshot_path=snapshot_path,
                timestamp=datetime.now(timezone.utc),
                shutdown_triggered=shutdown_triggered,
                resolved=False,
                violation_type=violation_type,
                ppe_detail=json.dumps(ppe_detail) if ppe_detail else None,
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            alert_id = alert.id

            # Log per-object crops
            self._log_detection_crops(
                db, frame, alert_id,
                persons_in_violation, env_detections,
                self.frame_count,
            )

            if shutdown_triggered:
                log_shutdown(db, zone_id, trigger_source="auto")
                trigger_relay(zone_name)

            settings = {s.key: s.value for s in db.query(Setting).all()}
        finally:
            db.close()

        # WhatsApp notification
        asyncio.create_task(
            send_to_all_recipients(
                settings.get("recipients", ""),
                zone_name, risk_level, confidence,
                shutdown_triggered,
                settings.get("facility_name", "Offshore Platform A"),
                settings.get("fonnte_token", ""),
            )
        )

        # WebSocket broadcast
        ws_event = {
            "type": "alert",
            "alert_id": alert_id,
            "zone_name": zone_name,
            "zone_id": zone_id,
            "risk_level": risk_level,
            "violation_type": violation_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "confidence": round(confidence, 3),
            "snapshot_url": f"/{snapshot_path}",
            "shutdown_triggered": shutdown_triggered,
            "ppe_detail": ppe_detail,
            "persons_count": len(persons_in_violation),
        }
        dead = set()
        for ws in self.ws_clients:
            try:
                await ws.send_json(ws_event)
            except Exception:
                dead.add(ws)
        self.ws_clients -= dead

    # ─── Drawing ───────────────────────────────────────────────────────────────

    def draw_zones(self, frame: np.ndarray, zones: List[dict]):
        h, w = frame.shape[:2]
        overlay = frame.copy()
        for zone in zones:
            vertices = zone["vertices"]
            risk = zone["risk_level"]
            pts = np.array([[int(v[0] * w), int(v[1] * h)] for v in vertices], dtype=np.int32)
            fill_color = (0, 0, 180) if risk == "high" else (0, 180, 180)
            border_color = (0, 0, 255) if risk == "high" else (0, 255, 255)
            cv2.fillPoly(overlay, [pts], fill_color)
            cv2.polylines(frame, [pts], True, border_color, 2, cv2.LINE_AA)
            centroid = compute_centroid(vertices)
            cx, cy = int(centroid[0] * w), int(centroid[1] * h)
            label = f"{zone['name']} ({risk.upper()})"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (cx - tw // 2 - 4, cy - th - 6), (cx + tw // 2 + 4, cy + 4), (0, 0, 0), -1)
            cv2.putText(frame, label, (cx - tw // 2, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.5, border_color, 1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)

    def draw_persons(self, frame: np.ndarray, persons: List[dict], violation_indices: set):
        for i, p in enumerate(persons):
            x1, y1, x2, y2 = p["bbox"]
            conf = p["confidence"]
            viols = p.get("ppe_violations", [])
            ppe_status = p.get("ppe", {})
            is_violation = i in violation_indices or bool(viols)

            # Build PPE status string from all detections
            ppe_labels = [f"{k}:{v['confidence']:.0%}" for k, v in ppe_status.items()]
            ppe_str = " | ".join(ppe_labels) if ppe_labels else "no PPE data"

            if is_violation:
                color = (0, 0, 255)
                viol_label = ", ".join(viols) if viols else "RESTRICTED"
                label = f"BAHAYA {conf:.0%} [{viol_label}]"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
                cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), (0, 0, 200), -1)
                cv2.putText(frame, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
            else:
                color = (0, 255, 0)
                label = f"Person {conf:.0%} OK"
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), (0, 0, 0), -1)
                cv2.putText(frame, label, (x1 + 2, y1 - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

            # Draw PPE status line below bounding box
            ppe_color = (0, 0, 255) if viols else (0, 220, 255)
            (pw, ph), _ = cv2.getTextSize(ppe_str, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            cv2.rectangle(frame, (x1, y2), (x1 + pw + 6, y2 + ph + 6), (0, 0, 0), -1)
            cv2.putText(frame, ppe_str, (x1 + 3, y2 + ph + 2), cv2.FONT_HERSHEY_SIMPLEX, 0.42, ppe_color, 1, cv2.LINE_AA)

    # ── Warna per class S3 (openhole model) ──────────────────────────────
    _ENV_COLORS = {
        "open-hole":    (0,   0,   220),   # merah  — bahaya utama
        "barricade":    (0,   140, 255),   # oranye — pembatas
        "safety-cone":  (0,   200, 255),   # kuning — kerucut
        "hard-hat":     (0,   200,  80),   # hijau  — helm
        "vest":         (200, 200,   0),   # cyan   — rompi
        "fire":         (0,   40,  255),   # merah terang
        "smoke":        (120, 120, 120),   # abu
    }

    def draw_env(self, frame: np.ndarray, env: List[dict]):
        for det in env:
            x1, y1, x2, y2 = det["bbox"]
            cls = det["class_name"]
            conf = det["confidence"]
            color = self._ENV_COLORS.get(cls, (100, 100, 100))
            label = f"{cls.upper()} {conf:.0%}"
            thickness = 3 if cls == "open-hole" else 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    def draw_infra(self, frame: np.ndarray, infra: List[dict]):
        for det in infra:
            x1, y1, x2, y2 = det["bbox"]
            cls = det["class_name"]
            conf = det["confidence"]
            color = (255, 165, 0)  # orange for infrastructure
            label = f"{cls.upper()} {conf:.0%}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 6, y1), (180, 100, 0), -1)
            cv2.putText(frame, label, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    # ── Warna per class S5 (road damage model) ─────────────────────────────────
    _ROAD_COLORS = {
        "lubang":    (0,   0,   255),   # biru    — pothole utama
        "retak":     (0,   150, 255),   # orange  — crack
        "tambalan":  (0,   255,   0),   # hijau   — patch/repair
    }

    def draw_road(self, frame: np.ndarray, road: List[dict]):
        for det in road:
            x1, y1, x2, y2 = det["bbox"]
            cls = det["class_name"]
            conf = det["confidence"]
            color = self._ROAD_COLORS.get(cls, (128, 128, 128))
            label = f"{cls.upper()} {conf:.0%}"
            thickness = 3 if cls == "lubang" else 2
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
            cv2.putText(frame, label, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

    # ─── Main Frame Generator ──────────────────────────────────────────────────

    def _offline_frame(self) -> bytes:
        """Return a static JPEG frame indicating camera is offline. No fake detections."""
        h, w = 480, 640
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # Subtle border
        cv2.rectangle(frame, (2, 2), (w - 3, h - 3), (40, 40, 40), 1)
        # Camera icon (circle + lens)
        cx, cy = w // 2, h // 2 - 20
        cv2.circle(frame, (cx, cy), 36, (55, 55, 55), 2)
        cv2.circle(frame, (cx, cy), 18, (55, 55, 55), 2)
        cv2.line(frame, (cx - 50, cy - 36), (cx + 50, cy - 36), (55, 55, 55), 2)
        # Status text
        cv2.putText(frame, "KAMERA OFFLINE", (w // 2 - 110, cy + 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 80, 80), 1, cv2.LINE_AA)
        cv2.putText(frame, "Menghubungkan kembali...", (w // 2 - 105, cy + 98),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (55, 55, 55), 1, cv2.LINE_AA)
        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return jpeg.tobytes()

    async def generate_frames(self):
        self.load_settings()
        self.init_pipeline(force=True)

        camera_ok = self.open_camera()

        if not camera_ok:
            # Try to use a real uploaded video file as fallback
            fallback_video = None
            if os.path.isdir(UPLOADS_DIR):
                for f in sorted(Path(UPLOADS_DIR).glob("*.mp4"), reverse=True):
                    fallback_video = str(f)
                    break
            if fallback_video:
                self.cap = cv2.VideoCapture(fallback_video)
                if self.cap.isOpened():
                    print(f"[STREAM] Using uploaded video as fallback: {fallback_video}")
                    camera_ok = True
                else:
                    self.cap = None

        if not camera_ok:
            print("[STREAM] No camera/video — serving offline frame, retrying every 5s")
            offline_jpeg = self._offline_frame()
            self.running = True
            while self.running:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + offline_jpeg + b"\r\n"
                await asyncio.sleep(5)
                # Retry real camera
                if self.open_camera():
                    print("[STREAM] Camera reconnected — switching to live feed")
                    camera_ok = True
                    break

        self.running = True
        reconnect_attempts = 0

        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                reconnect_attempts += 1
                if reconnect_attempts > 10:
                    self.open_camera()
                    reconnect_attempts = 0
                await asyncio.sleep(0.5)
                continue

            reconnect_attempts = 0
            self.frame_count += 1
            h, w = frame.shape[:2]

            # Run pipeline every N frames
            if self.frame_count % self._detection_interval == 0:
                print(f"[DEBUG] Frame {self.frame_count}: Running pipeline...")
                try:
                    result = self.pipeline.run(frame)
                    self._last_persons = result["persons"]
                    self._last_env = result["env"]
                    self._last_infra = result.get("infra", [])
                    print(f"[DEBUG] Pipeline returned: persons={len(self._last_persons)}, env={len(self._last_env)}, infra={len(self._last_infra)}")
                    if self._last_persons or self._last_env:
                        print(f"[DETECT] Frame {self.frame_count}: "
                              f"persons={len(self._last_persons)}, "
                              f"env={len(self._last_env)}, "
                              f"infra={len(result.get('infra', []))}")
                except Exception as e:
                    print(f"[ERROR] Pipeline run failed: {e}")
                    import traceback
                    traceback.print_exc()

            zones = self.get_active_zones()
            violation_person_indices = set()

            # ── Check each person against zones + PPE ──────────────────────────
            for i, person in enumerate(self._last_persons):
                bcx = person["bottom_center"][0] / w
                bcy = person["bottom_center"][1] / h
                norm_pt = (bcx, bcy)

                in_zone = False
                triggering_zone = None
                for zone in zones:
                    if point_in_polygon(norm_pt, zone["vertices"]):
                        in_zone = True
                        triggering_zone = zone
                        break

                has_ppe_viol = bool(person.get("ppe_violations"))
                viol_type = self._determine_violation_type(person, in_zone)

                if viol_type:
                    violation_person_indices.add(i)
                    # Use zone or a dummy zone for PPE-only violations
                    target_zone = triggering_zone or (zones[0] if zones else None)
                    if target_zone:
                        ckey = f"{target_zone['id']}_{viol_type}_{i}"
                        if self._check_consistency(ckey, True):
                            await self.handle_violation(
                                frame,
                                target_zone,
                                person["confidence"],
                                viol_type,
                                [person],
                                [],
                            )
                    elif has_ppe_viol:
                        # No zones defined — still alert on PPE violation
                        ckey = f"global_{viol_type}_{i}"
                        if self._check_consistency(ckey, True):
                            fake_zone = {
                                "id": 0, "name": "General Area",
                                "risk_level": "low", "vertices": [],
                            }
                            await self.handle_violation(
                                frame, fake_zone,
                                person["confidence"], viol_type, [person], [],
                            )
                else:
                    # Clear consistency counters for this person
                    for z in zones:
                        for vt in ["restricted_area", "missing_ppe", "no_harness", "multiple"]:
                            ckey = f"{z['id']}_{vt}_{i}"
                            self._consistency_counters.pop(ckey, None)

            # ── Check environment detections (fire/smoke) ──────────────────────
            if self._last_env and zones:
                ckey_env = "env_fire_smoke"
                if self._check_consistency(ckey_env, True):
                    await self.handle_violation(
                        frame,
                        zones[0],
                        max(d["confidence"] for d in self._last_env),
                        "fire_smoke",
                        [],
                        self._last_env,
                    )
            else:
                self._consistency_counters.pop("env_fire_smoke", None)

            # ── Draw ──────────────────────────────────────────────────────────
            self.draw_zones(frame, zones)
            self.draw_infra(frame, self._last_infra)
            self.draw_env(frame, self._last_env)
            self.draw_persons(frame, self._last_persons, violation_person_indices)

            # Watermark
            cv2.putText(frame, "SIEWS+ 5.0", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            cv2.putText(frame, ts, (10, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)

            _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"

            await asyncio.sleep(0.033)


# Singleton
stream_manager = StreamManager()
