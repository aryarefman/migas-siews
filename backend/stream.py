"""
SIEWS+ 5.0 — MJPEG Stream + YOLO Inference + Zone Violation Check

Architecture (lag-free):
  CaptureThread  →  frame_queue  →  InferenceThread  →  result_queue
  AsyncLoop reads result_queue, draws overlays, encodes JPEG, serves MJPEG

Adaptive FPS: Render loop measures actual frame time and adjusts sleep
  dynamically so it never exceeds device capability. GPU devices get higher
  throughput automatically; CPU devices gracefully degrade without stutter.

Adaptive threshold: FALSE POS feedback auto-raises per-class threshold.
Temporal consistency: fire/smoke requires N consecutive frames before alert.
"""
import os
import cv2
import time
import json
import asyncio
import threading
import queue
import numpy as np
from collections import defaultdict, deque
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

# ─── Adaptive FPS Configuration ──────────────────────────────
# Push FPS as high as device can handle — no artificial cap
MAX_FPS = 120         # No cap — let GPU push maximum
MIN_FPS = 20          # Minimum acceptable
FPS_WINDOW = 10       # Fast adaptation
TARGET_UTILIZATION = 0.90  # Use 90% of frame budget — maximize throughput

# ─── Temporal Consistency ─────────────────────────────────────
# Fire/smoke must appear in N consecutive inference frames before alerting.
TEMPORAL_REQUIRED_FRAMES = 5

# ─── Adaptive Threshold ───────────────────────────────────────
# Per-class threshold adjustments stored in memory (persisted to DB on change).
# Key: class label (e.g. "smoke", "fire", "ppe_violation")
# Value: float delta added to base threshold
_adaptive_delta: dict = defaultdict(float)
_ADAPTIVE_STEP_UP = 0.05    # raise threshold on FALSE POS click
_ADAPTIVE_MAX_DELTA = 0.30  # cap so threshold never goes above base + 0.30
_ADAPTIVE_DECAY = 0.005     # slowly lower delta over time (per inference cycle)


# ─── Auto-Zone Helpers ──────────────────────────────────────────
def bbox_to_polygon_vertices(bbox, padding_pct=0.15, frame_w=None, frame_h=None):
    """Convert [x1,y1,x2,y2] to 4-corner polygon with optional padding.

    If frame_w/frame_h provided, returns normalized (0-1) vertices.
    Otherwise returns pixel-space vertices.
    """
    x1, y1, x2, y2 = bbox
    pad_x = (x2 - x1) * padding_pct
    pad_y = (y2 - y1) * padding_pct

    if frame_w and frame_h:
        return [
            [(x1 - pad_x) / frame_w, (y1 - pad_y) / frame_h],
            [(x2 + pad_x) / frame_w, (y1 - pad_y) / frame_h],
            [(x2 + pad_x) / frame_w, (y2 + pad_y) / frame_h],
            [(x1 - pad_x) / frame_w, (y2 + pad_y) / frame_h],
        ]
    else:
        return [
            [x1 - pad_x, y1 - pad_y],
            [x2 + pad_x, y1 - pad_y],
            [x2 + pad_x, y2 + pad_y],
            [x1 - pad_x, y2 + pad_y],
        ]


def build_auto_zones(env_hazards, road_detections, vehicles, frame_w, frame_h):
    """Build dynamic polygon auto-zones from current detections."""
    auto_zones = []

    # Environmental hazards (fire, smoke, open-hole, barricade, etc.)
    for i, haz in enumerate(env_hazards):
        bbox = haz.get("bbox", [])
        if len(bbox) != 4:
            continue
        label = haz.get("label", haz.get("class_name", "hazard")).lower()
        vertices = bbox_to_polygon_vertices(bbox, padding_pct=0.15, frame_w=frame_w, frame_h=frame_h)
        auto_zones.append({
            "id": f"auto_env_{i}_{label}",
            "name": f"AUTO: {label.upper()}",
            "vertices": vertices,
            "color": "#FF0000",
            "risk_level": "high",
            "auto": True,
        })

    # Road damage (pothole/lubang)
    for i, rd in enumerate(road_detections):
        bbox = rd.get("bbox", [])
        if len(bbox) != 4:
            continue
        label = rd.get("label", rd.get("class_name", "lubang")).upper()
        vertices = bbox_to_polygon_vertices(bbox, padding_pct=0.20, frame_w=frame_w, frame_h=frame_h)
        auto_zones.append({
            "id": f"auto_road_{i}_{label}",
            "name": f"DANGER: {label}",
            "vertices": vertices,
            "color": "#FF8C00",
            "risk_level": "high",
            "auto": True,
        })

    # Vehicles
    for i, veh in enumerate(vehicles):
        bbox = veh.get("bbox", [])
        if len(bbox) != 4:
            continue
        label = veh.get("label", veh.get("class_name", "vehicle")).upper()
        vertices = bbox_to_polygon_vertices(bbox, padding_pct=0.10, frame_w=frame_w, frame_h=frame_h)
        auto_zones.append({
            "id": f"auto_veh_{i}_{label}",
            "name": f"VEHICLE: {label}",
            "vertices": vertices,
            "color": "#FF00FF",
            "risk_level": "medium",
            "auto": True,
        })

    return auto_zones


class AdaptiveFPSController:
    """
    Measures actual frame processing time and dynamically adjusts the render
    sleep interval so the system never tries to push more FPS than the device
    can handle.

    On GPU: frame processing is fast → sleep is longer → steady 25-30 FPS
    On CPU: frame processing is slow → sleep is shorter → settles at 10-20 FPS
    """

    def __init__(self, max_fps: int = MAX_FPS, min_fps: int = MIN_FPS, window: int = FPS_WINDOW):
        self._max_fps = max_fps
        self._min_fps = min_fps
        self._frame_times: deque = deque(maxlen=window)
        self._target_interval = 1.0 / max_fps  # Start optimistic
        self._current_fps = float(max_fps)
        self._warmup_frames = 10  # First N frames use conservative timing
        self._frame_count = 0

    def frame_start(self) -> float:
        """Call at the start of each render cycle. Returns current time."""
        return time.perf_counter()

    def frame_end(self, start_time: float):
        """
        Call at the end of each render cycle.
        Measures how long the frame took and recalculates target interval.
        """
        elapsed = time.perf_counter() - start_time
        self._frame_times.append(elapsed)
        self._frame_count += 1

        if self._frame_count <= self._warmup_frames:
            # During warmup, be conservative
            self._target_interval = 1.0 / self._min_fps
            return

        # Calculate average frame processing time
        avg_frame_time = sum(self._frame_times) / len(self._frame_times)

        # Target: leave headroom so we don't saturate the CPU
        # If avg_frame_time is 20ms, we want total cycle to be ~27ms (75% util)
        # → sleep = (avg_frame_time / TARGET_UTILIZATION) - avg_frame_time
        ideal_cycle = avg_frame_time / TARGET_UTILIZATION
        max_cycle = 1.0 / self._min_fps
        min_cycle = 1.0 / self._max_fps

        self._target_interval = max(min_cycle, min(max_cycle, ideal_cycle)) - avg_frame_time
        self._target_interval = max(0.001, self._target_interval)  # Never negative/zero

        # Update current FPS estimate
        total_cycle = avg_frame_time + self._target_interval
        self._current_fps = min(self._max_fps, 1.0 / max(total_cycle, 0.001))

    @property
    def sleep_interval(self) -> float:
        """How long to sleep between frames (seconds)."""
        return self._target_interval

    @property
    def current_fps(self) -> float:
        """Current effective FPS."""
        return round(self._current_fps, 1)

    @property
    def avg_frame_time_ms(self) -> float:
        """Average frame processing time in milliseconds."""
        if not self._frame_times:
            return 0.0
        return round(sum(self._frame_times) / len(self._frame_times) * 1000, 1)

    def get_stats(self) -> dict:
        """Return FPS stats for health/debug endpoints."""
        return {
            "current_fps": self.current_fps,
            "target_fps": round(1.0 / (self.sleep_interval + self.avg_frame_time_ms / 1000), 1) if self.avg_frame_time_ms > 0 else self._max_fps,
            "avg_frame_time_ms": self.avg_frame_time_ms,
            "sleep_interval_ms": round(self.sleep_interval * 1000, 1),
            "max_fps": self._max_fps,
            "min_fps": self._min_fps,
        }


def report_false_positive(class_label: str):
    """Called when user clicks FALSE POS — raises threshold for that class."""
    _adaptive_delta[class_label] = min(
        _adaptive_delta[class_label] + _ADAPTIVE_STEP_UP,
        _ADAPTIVE_MAX_DELTA
    )
    print(f"[ADAPTIVE] FALSE POS for '{class_label}' → delta={_adaptive_delta[class_label]:.2f}")


def get_effective_threshold(base: float, class_label: str) -> float:
    """Return base threshold + adaptive delta for a class."""
    return min(0.95, base + _adaptive_delta[class_label])


def _decay_adaptive_thresholds():
    """Slowly decay adaptive deltas back toward zero (called each inference cycle)."""
    for k in list(_adaptive_delta.keys()):
        _adaptive_delta[k] = max(0.0, _adaptive_delta[k] - _ADAPTIVE_DECAY)


def _overlaps_any_person(bbox, person_bboxes, iou_threshold=0.3):
    """Check if a detection bbox overlaps significantly with any person bbox."""
    x1, y1, x2, y2 = bbox
    for pb in person_bboxes:
        px1, py1, px2, py2 = pb
        # Calculate IoU
        ix1 = max(x1, px1)
        iy1 = max(y1, py1)
        ix2 = min(x2, px2)
        iy2 = min(y2, py2)
        if ix2 <= ix1 or iy2 <= iy1:
            continue
        intersection = (ix2 - ix1) * (iy2 - iy1)
        area_det = max(0, (x2 - x1) * (y2 - y1))
        area_person = max(0, (px2 - px1) * (py2 - py1))
        # Check if detection is mostly inside person OR person is mostly inside detection
        if area_det > 0 and intersection / area_det > iou_threshold:
            return True
        if area_person > 0 and intersection / area_person > iou_threshold:
            return True
    return False


class StreamManager:
    def __init__(self):
        self.detector: Optional[MultiStagePipeline] = None
        self.violation_checker = ViolationChecker(cooldown_seconds=7)
        self.ws_clients: Set = set()
        self.running = False
        self.camera_state = "offline"
        self.camera_last_error: Optional[str] = None
        self._reconnect_attempts = 0
        self._next_reconnect_at = 0.0
        self._last_successful_frame_at = 0.0
        self._last_zone_refresh = 0.0
        self._zones_cache = []

        # Adaptive FPS controller — adjusts render rate to device capability
        self.fps_controller = AdaptiveFPSController()

        # Last known frame dimensions (for auto-zone rendering)
        self._last_w = 640
        self._last_h = 480

        # Settings
        self._camera_source = "0"
        self._confidence = 0.5
        self._detection_interval = 1
        self._notify_cooldown = 5

        # WhatsApp notification cooldown (separate from alert creation)
        self._wa_last_sent: float = 0.0  # timestamp of last WhatsApp sent
        self._debug_zone_counter: int = 0

        # Simulation mode
        self.simulation_frame: Optional[np.ndarray] = None
        self.simulation_cap: Optional[cv2.VideoCapture] = None

        # Current JPEG frame (for MJPEG)
        self.frame: Optional[bytes] = None
        self._raw_frame: Optional[np.ndarray] = None

        # ── Thread-safe queues ──────────────────────────────────
        # frame_queue: latest frame for inference (size=1, always drop old)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=1)
        # result_queue: inference results for async loop to consume
        self._result_queue: queue.Queue = queue.Queue(maxsize=4)

        # Latest detection results (written by inference thread, read by async loop)
        self._last_result: dict = {
            "persons": [], "env": [], "road": [], "safety_cones": [], "vehicles": []
        }
        self._result_lock = threading.Lock()

        # Temporal consistency counters: label → consecutive frame count
        self._temporal_counts: dict = defaultdict(int)

        # Capture and inference threads
        self._capture_thread: Optional[threading.Thread] = None
        self._inference_thread: Optional[threading.Thread] = None

    # =========================================================================
    # Camera Status
    # =========================================================================

    def camera_status(self) -> str:
        if self.simulation_frame is not None or self.simulation_cap is not None:
            return "simulation"
        if self.camera_state == "online":
            return "online"
        if self.camera_state == "reconnecting" or time.time() < self._next_reconnect_at:
            return "reconnecting"
        return "offline"

    def camera_info(self) -> dict:
        return {
            "status": self.camera_status(),
            "source": self._camera_source,
            "reconnect_attempts": self._reconnect_attempts,
            "last_error": self.camera_last_error,
            "last_successful_frame_at": self._last_successful_frame_at,
            "fps": self.fps_controller.get_stats(),
        }

    def request_camera_reconnect(self, reason: str = "manual"):
        print(f"[STREAM] Camera reconnect requested: {reason}")
        self.camera_state = "reconnecting"
        self.camera_last_error = reason
        self._next_reconnect_at = 0.0

    def _reconnect_delay(self) -> float:
        return min(30.0, 2.0 + self._reconnect_attempts * 2.0)

    def load_settings(self):
        db = SessionLocal()
        try:
            settings = {s.key: s.value for s in db.query(Setting).all()}
            self._camera_source = settings.get("camera_source", "0")
            self._confidence = float(settings.get("confidence_threshold", "0.5"))
            self._detection_interval = int(settings.get("detection_interval", "3"))
            self._notify_cooldown = int(settings.get("notify_cooldown", "7"))
            self.violation_checker._cooldown_seconds = self._notify_cooldown
        finally:
            db.close()

    def init_detector(self):
        self.detector = MultiStagePipeline(confidence=self._confidence)
        self.pipeline = self.detector

    def init_pipeline(self):
        self.init_detector()

    # =========================================================================
    # MJPEG
    # =========================================================================

    def get_frame(self) -> bytes:
        if self.frame is None:
            black = np.zeros((720, 1280, 3), dtype=np.uint8)
            _, jp = cv2.imencode(".jpg", black)
            return jp.tobytes()
        return self.frame

    def generate_frames(self):
        """MJPEG stream generator — 30 FPS output to browser."""
        print("[STREAM] MJPEG Stream client connected")
        while True:
            frame = self.get_frame()
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.033)  # 30 FPS — smooth for browser MJPEG

    # =========================================================================
    # Zone Management
    # =========================================================================

    def get_active_zones(self, force: bool = False) -> List[dict]:
        """Get zones from DB, with caching to avoid slamming the DB every frame."""
        now = time.time()
        # If forced or cache is empty or cache expired (reduced to 1s for better sync)
        if not force and self._zones_cache and (now - self._last_zone_refresh < 1.0):
            return self._zones_cache

        db = SessionLocal()
        try:
            # Only get zones that are explicitly active
            zones = db.query(Zone).filter(Zone.active == True).all()
            new_zones = [
                {
                    "id": z.id,
                    "name": z.name,
                    "vertices": parse_vertices(z.vertices_json),
                    "color": z.color,
                    "risk_level": z.risk_level,
                }
                for z in zones
            ]
            
            # Atomic update of cache
            self._zones_cache = new_zones
            self._last_zone_refresh = now
            return self._zones_cache
        except Exception as e:
            print(f"[STREAM] Zone fetch error: {e}")
            return self._zones_cache # return last known on error
        finally:
            db.close()

    def refresh_zones(self):
        """Force immediate refresh of zones from DB."""
        self._zones_cache = [] # Clear cache first
        self.get_active_zones(force=True)

    # =========================================================================
    # Capture Thread — reads camera as fast as possible, drops old frames
    # =========================================================================

    def _capture_loop(self):
        """Dedicated thread: captures frames and puts latest into frame_queue."""
        cap = None
        frame_count = 0

        while self.running:
            # Simulation mode
            if self.simulation_frame is not None:
                self._put_frame(self.simulation_frame.copy())
                time.sleep(self.fps_controller.sleep_interval)
                continue
            if self.simulation_cap is not None:
                ret, frame = self.simulation_cap.read()
                if not ret:
                    self.simulation_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = self.simulation_cap.read()
                if ret:
                    self._put_frame(frame)
                time.sleep(self.fps_controller.sleep_interval)
                continue

            # Open camera if needed
            if cap is None or not cap.isOpened():
                if time.time() < self._next_reconnect_at:
                    time.sleep(0.5)
                    continue
                source = self._camera_source
                if isinstance(source, str) and source.isdigit():
                    source = int(source)
                cap = cv2.VideoCapture(source)
                if not cap.isOpened():
                    self.camera_state = "reconnecting"
                    self.camera_last_error = f"failed to open {self._camera_source}"
                    self._reconnect_attempts += 1
                    self._next_reconnect_at = time.time() + self._reconnect_delay()
                    print(f"[STREAM] Failed to open camera source: {self._camera_source}. "
                          f"Retry in {self._reconnect_delay():.0f}s")
                    cap = None
                    self._store_offline_frame()
                    continue
                # Optimize capture buffer — reduce internal buffering lag
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.camera_state = "online"
                self.camera_last_error = None
                self._reconnect_attempts = 0
                self._next_reconnect_at = 0.0
                print(f"[STREAM] Camera opened: {self._camera_source}")

            ret, frame = cap.read()
            if not ret or frame is None:
                self.camera_state = "reconnecting"
                self.camera_last_error = "camera read failed"
                self._next_reconnect_at = time.time() + self._reconnect_delay()
                cap.release()
                cap = None
                self._store_offline_frame()
                continue

            self.camera_state = "online"
            self._last_successful_frame_at = time.time()
            frame_count += 1

            # Only send every N frames to inference (skip frames = less lag)
            if frame_count % self._detection_interval == 0:
                self._put_frame(frame)

            # Store raw frame and dimensions — async loop will draw overlay and write self.frame
            self._raw_frame = frame
            self._last_h, self._last_w = frame.shape[:2]

        if cap:
            cap.release()

    def _put_frame(self, frame: np.ndarray):
        """Non-blocking put — drop old frame if queue full (always latest)."""
        try:
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            try:
                self._frame_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frame_queue.put_nowait(frame)
            except queue.Full:
                pass

    # =========================================================================
    # Inference Thread — runs YOLO, never blocks capture
    # =========================================================================

    def _inference_loop(self):
        """Dedicated thread: pulls frames from queue, runs YOLO, pushes results."""
        _face_ocr_counter = 0
        _last_ocr_codes = {}   # cache: person index -> ocr_code

        while self.running:
            try:
                frame = self._frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if self.detector is None:
                continue

            try:
                h, w = frame.shape[:2]
                persons, env_hazards, road, safety_cones = self.detector.detect_base(frame)
                vehicles = self.detector.detect_vehicles(frame)

                # Cross-stage NMS: suppress env/road false positives that overlap with persons
                if persons and (env_hazards or road):
                    person_bboxes_raw = [p["bbox"] for p in persons]
                    env_hazards = [e for e in env_hazards if not _overlaps_any_person(e["bbox"], person_bboxes_raw, 0.3)]
                    road = [r for r in road if not _overlaps_any_person(r["bbox"], person_bboxes_raw, 0.3)]

                if persons:
                    persons = self.detector.detect_ppe_full_frame(frame, persons)
                    person_bboxes = [p["bbox"] for p in persons]

                    # Face recognition: ALWAYS run (no throttle)
                    # Face name is critical for alerts — must be available immediately
                    face_results = face_manager.recognize_faces(frame, person_bboxes)

                    # OCR: throttle every 3 cycles (less critical, slower)
                    _face_ocr_counter += 1
                    if _face_ocr_counter >= 3:
                        _face_ocr_counter = 0
                        ocr_results = ocr_engine.read_all_codes(frame, person_bboxes)
                        _last_ocr_codes = {}
                        for i, det in enumerate(persons):
                            if i < len(ocr_results) and ocr_results[i]:
                                _last_ocr_codes[i] = ocr_results[i].get("code")

                    # Apply face + cached OCR results
                    for i, det in enumerate(persons):
                        det["face_name"] = "Unknown"
                        det["ocr_code"] = None
                        try:
                            if i < len(face_results) and face_results[i]:
                                det["face_name"] = face_results[i].get("name", "Unknown")
                                if det["face_name"] != "Unknown":
                                    print(f"[FACE-MATCH] Recognized: {det['face_name']} (conf={face_results[i].get('confidence', 0):.3f})")
                            if i in _last_ocr_codes:
                                det["ocr_code"] = _last_ocr_codes[i]
                            if det["face_name"] == "Unknown" and det["ocr_code"]:
                                for p in face_manager._registered:
                                    if p.get("code") == det["ocr_code"]:
                                        det["face_name"] = p["name"]
                                        print(f"[OCR-MATCH] Code '{det['ocr_code']}' -> {det['face_name']}")
                                        break
                        except (AttributeError, TypeError):
                            pass

                # Apply adaptive threshold decay
                _decay_adaptive_thresholds()

                # Temporal consistency filter for fire/smoke
                env_hazards = self._apply_temporal_filter(env_hazards)

                result = {
                    "persons": persons,
                    "env": env_hazards,
                    "road": road,
                    "safety_cones": safety_cones,
                    "vehicles": vehicles,
                    "frame": frame,
                    "w": w,
                    "h": h,
                }

                with self._result_lock:
                    self._last_result = result

                # Push to async loop for violation handling
                try:
                    self._result_queue.put_nowait(result)
                except queue.Full:
                    try:
                        self._result_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._result_queue.put_nowait(result)
                    except queue.Full:
                        pass

                if persons or env_hazards or road or safety_cones or vehicles:
                    # Log PPE status for debugging
                    for p in persons:
                        ppe = p.get("ppe_result", {})
                        viols = p.get("ppe_violations", [])
                        if viols:
                            print(f"[DETECTOR] Person '{p.get('face_name','?')}' PPE violations: {viols}")
                    print(f"[DETECTOR] Detected: {len(persons)} people, "
                          f"{len(env_hazards)} env, {len(road)} road, "
                          f"{len(safety_cones)} safety-cones, {len(vehicles)} vehicles")

            except Exception as e:
                print(f"[INFERENCE] Error: {e}")

    def _apply_temporal_filter(self, hazards: List[dict]) -> List[dict]:
        """
        Fire/smoke must appear in TEMPORAL_REQUIRED_FRAMES consecutive inference
        cycles before being passed through. Resets counter if label disappears.
        """
        from detection_models import FIRE_SMOKE_LABELS
        current_labels = {h.get("label", "").lower() for h in hazards
                          if h.get("label", "").lower() in FIRE_SMOKE_LABELS}

        # Increment counters for present labels, reset absent ones
        for label in list(self._temporal_counts.keys()):
            if label not in current_labels:
                self._temporal_counts[label] = 0

        for label in current_labels:
            self._temporal_counts[label] += 1

        # Only pass through hazards that have met the consecutive frame requirement
        filtered = []
        for h in hazards:
            label = h.get("label", "").lower()
            if label in FIRE_SMOKE_LABELS:
                if self._temporal_counts[label] >= TEMPORAL_REQUIRED_FRAMES:
                    filtered.append(h)
            else:
                filtered.append(h)
        return filtered

    # =========================================================================
    # Violation Handling
    # =========================================================================

    async def _handle_violation(self, frame: np.ndarray, violation):
        zone_id = violation.zone_id
        zone_name = violation.zone_name
        risk_level = violation.risk_level

        if not self.violation_checker.should_alert(zone_id, violation.violation_type):
            return

        try:
            now_utc = datetime.now(timezone.utc)
            timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"{timestamp_str}_{zone_id}.jpg"
            snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_filename)
            cv2.imwrite(snapshot_path, frame)

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
                    ppe_detail=json.dumps(violation.ppe_detail) if violation.ppe_detail else None,
                )
                db.add(alert)
                db.commit()
                db.refresh(alert)
                alert_id = alert.id

                if shutdown_triggered:
                    from shutdown import log_shutdown, trigger_relay
                    log_shutdown(db, zone_id, trigger_source="auto")
                    trigger_relay(zone_name)

                settings = {s.key: s.value for s in db.query(Setting).all()}
            except Exception as dbe:
                print(f"[ALERT-FLOW] DB Error: {dbe}")
                db.rollback()
                settings = {}
            finally:
                db.close()

            fonnte_token = settings.get("fonnte_token", "")
            recipients = settings.get("recipients", "")
            facility_name = settings.get("facility_name", "Offshore Platform A")

            # Build recipient list:
            # - If person is identified (face/OCR match) → send to that person's phone only
            # - If person is Unknown → send to admin recipients from settings
            recipient_list = []
            person_phone_found = False

            if violation.person_name and violation.person_name != "Unknown":
                for p in face_manager._registered:
                    if p["name"].lower() == violation.person_name.lower() and p.get("phone"):
                        recipient_list.append(p["phone"])
                        person_phone_found = True
                        break

            # Fallback to admin recipients if person not identified or has no phone
            if not person_phone_found:
                recipient_list = [r.strip() for r in recipients.split(",") if r.strip()]

            # WhatsApp notification — separate cooldown from alert creation
            # Alerts always go to DB + WebSocket, but WhatsApp respects notify_cooldown
            now_ts = time.time()
            wa_cooldown = int(settings.get("notify_cooldown", "300"))
            if now_ts - self._wa_last_sent >= wa_cooldown:
                self._wa_last_sent = now_ts
                asyncio.create_task(self._send_notifications(
                    recipient_list, zone_name, risk_level, violation.confidence,
                    shutdown_triggered, facility_name, snapshot_filename,
                    violation.person_name, violation.uniform_code, fonnte_token
                ))
            else:
                remaining = wa_cooldown - (now_ts - self._wa_last_sent)
                print(f"[ALERT-FLOW] WhatsApp skipped (cooldown {remaining:.0f}s remaining)")

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
                "violation_type": violation.violation_type,
                "ppe_detail": violation.ppe_detail,
            }
            await self._broadcast_to_ws(ws_event)

        except Exception as e:
            print(f"[ALERT-FLOW] CRITICAL FAIL: {e}")
            import traceback
            traceback.print_exc()

    async def _send_notifications(self, recipients, zone_name, risk_level,
                                   confidence, shutdown_triggered, facility_name,
                                   snapshot_filename, person_name, uniform_code, fonnte_token=""):
        from notifier import send_to_all_recipients
        try:
            print(f"[ALERT-FLOW] Sending notification: token_len={len(fonnte_token)}, recipients={len(recipients)}")
            if not fonnte_token:
                print(f"[ALERT-FLOW] WARNING: fonnte_token is empty! Attempting to reload from DB...")
                from database import SessionLocal
                from models import Setting
                db = SessionLocal()
                try:
                    settings = {s.key: s.value for s in db.query(Setting).all()}
                    fonnte_token = settings.get("fonnte_token", "")
                    print(f"[ALERT-FLOW] Reloaded token from DB: len={len(fonnte_token)}")
                finally:
                    db.close()
            await send_to_all_recipients(
                ",".join(recipients), zone_name, risk_level, confidence,
                shutdown_triggered, facility_name, fonnte_token,
                snapshot_url=f"/static/snapshots/{snapshot_filename}",
                person_name=person_name, uniform_code=uniform_code
            )
        except Exception as e:
            print(f"[ALERT-FLOW] Notification error: {e}")

    async def _broadcast_to_ws(self, event):
        dead = set()
        for ws in self.ws_clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.add(ws)
        self.ws_clients -= dead

    async def _broadcast_camera_state(self):
        await self._broadcast_to_ws({
            "type": "camera_status",
            "status": self.camera_status(),
            "reconnect_attempts": self._reconnect_attempts,
            "last_error": self.camera_last_error,
        })

    # =========================================================================
    # Offline Frame
    # =========================================================================

    def _offline_frame(self):
        """Generate a clean, minimal offline frame — just black."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        return frame

    def _store_offline_frame(self):
        _, jpeg = cv2.imencode(".jpg", self._offline_frame())
        self.frame = jpeg.tobytes()

    # =========================================================================
    # Main Async Loop — draws overlays, handles violations
    # =========================================================================

    async def start(self):
        print("[STREAM] Starting stream manager...")
        self.load_settings()

        if not self.detector:
            print("[STREAM] Initializing detector...")
            self.init_detector()

        self.running = True

        # Start capture thread
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="CaptureThread"
        )
        self._capture_thread.start()

        # Start inference thread
        self._inference_thread = threading.Thread(
            target=self._inference_loop, daemon=True, name="InferenceThread"
        )
        self._inference_thread.start()

        print("[STREAM] Capture + Inference threads started. Entering async loop...")

        # Last known detection state — persisted between inference cycles
        _last_persons = []
        _last_env = []
        _last_road = []
        _last_safety_cones = []
        _last_vehicles = []
        _last_zones = []
        _last_violations = []
        _last_auto_zones = []
        _last_violated_zone_ids = set()

        # FPS logging interval
        _fps_log_interval = 10.0  # Log FPS every 10 seconds
        _last_fps_log = time.time()

        while self.running:
            try:
                frame_start = self.fps_controller.frame_start()

                # Check for new inference result (non-blocking)
                result = None
                while True:
                    try:
                        result = self._result_queue.get_nowait()
                    except queue.Empty:
                        break

                if result:
                    persons = result["persons"]
                    env_hazards = result["env"]
                    road = result["road"]
                    safety_cones = result["safety_cones"]
                    vehicles = result.get("vehicles", [])
                    w, h = result["w"], result["h"]

                    # Update last known state
                    _last_persons = persons
                    _last_env = env_hazards
                    _last_road = road
                    _last_safety_cones = safety_cones
                    _last_vehicles = vehicles
                    _last_zones = self.get_active_zones()

                    # Build auto-zones from current detections (cached for render loop)
                    auto_zones = build_auto_zones(env_hazards, road, vehicles, w, h)
                    _last_auto_zones = auto_zones
                    all_zones = _last_zones + auto_zones

                    # Check violations on new result (polygon-based for all zones)
                    violations = self.violation_checker.check_all_violations(
                        persons, env_hazards, all_zones, w, h,
                        road_detections=road,
                    )
                    _last_violations = violations
                    _last_violated_zone_ids = self.violation_checker.get_violated_zone_ids(
                        persons, all_zones, violations
                    )
                    for v in violations:
                        asyncio.create_task(self._handle_violation(result["frame"].copy(), v))

                # Always render: draw last known detections onto latest raw frame
                raw = self._raw_frame
                if raw is not None:
                    display = raw.copy()

                    # Draw zone polygons (borders only — fast)
                    all_zones = _last_zones + _last_auto_zones
                    if all_zones:
                        # Use cached violated IDs from last inference (not recalculated every frame)
                        draw_zones(display, all_zones, _last_violated_zone_ids)

                    if _last_persons or _last_env or _last_road or _last_safety_cones or _last_vehicles:
                        violation_indices = self.violation_checker.get_violation_indices(_last_persons, _last_violations)
                        draw_detections(display, _last_persons, violation_indices,
                                        _last_env, _last_road, _last_safety_cones, _last_vehicles)
                    _, jpeg = cv2.imencode('.jpg', display, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    self.frame = jpeg.tobytes()

                # Measure frame time and adapt sleep
                self.fps_controller.frame_end(frame_start)

                # Periodic FPS logging
                now = time.time()
                if now - _last_fps_log >= _fps_log_interval:
                    stats = self.fps_controller.get_stats()
                    print(f"[STREAM] Adaptive FPS: {stats['current_fps']} fps | "
                          f"frame_time={stats['avg_frame_time_ms']}ms | "
                          f"sleep={stats['sleep_interval_ms']}ms")
                    _last_fps_log = now

                # Adaptive sleep — device-aware pacing
                await asyncio.sleep(self.fps_controller.sleep_interval)

            except Exception as e:
                print(f"[STREAM] Async loop error: {e}")
                await asyncio.sleep(1)


# Singleton instance
stream_manager = StreamManager()
