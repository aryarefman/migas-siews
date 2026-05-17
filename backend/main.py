"""
SIEWS+ 5.0 — FastAPI Application Entry Point
CORS, router mounting, static files, WebSocket, and all API endpoints.
"""
import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

import cv2
import numpy as np

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, UploadFile, File, BackgroundTasks, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, init_db
from models import Zone, Alert, ShutdownLog, Setting, DetectionLog, VideoJob
from stream import stream_manager
from notifier import send_test_message
from shutdown import trigger_relay, log_shutdown
from config import STATIC_DIR
from video_processor import video_processor, UPLOADS_DIR
from face_manager import face_manager
from drawing import (
    draw_detections,
    draw_env_hazards,
    draw_persons,
    draw_road_damage,
    draw_safety_cones,
    draw_vehicles,
    draw_zones,
)
from detection_models import FIRE_SMOKE_LABELS

# ─── App Setup ────────────────────────────────────────────────
app = FastAPI(
    title="SIEWS+ 5.0 API",
    description="AI-Based Human Presence Detection for Intelligent Safety Shutdown",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (snapshots)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
async def startup():
    init_db()
    # 1. Start the background camera/detection loop
    from stream import stream_manager
    asyncio.create_task(stream_manager.start())
    # 2. Pre-warm OCR engine to avoid first-request timeout
    from ocr_engine import ocr_engine
    ocr_engine._init_reader()
    print("🚀 SIEWS+ 5.0 Backend started & AI Engine Running")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    from stream import stream_manager
    return {
        "status": "ok",
        "models_loaded": stream_manager.detector is not None,
        "pipeline_loaded": stream_manager.pipeline is not None,
        "camera_status": stream_manager.camera_status(),
        **stream_manager.camera_info(),
    }


@app.post("/camera/reconnect")
async def camera_reconnect():
    """Manually trigger camera reconnect."""
    from stream import stream_manager
    stream_manager.request_camera_reconnect("manual_api")
    return {"status": "reconnecting", "message": "Camera reconnect triggered"}


@app.get("/camera/status")
async def camera_status():
    """Get camera status for frontend polling."""
    from stream import stream_manager
    status = stream_manager.camera_status()
    is_on = status in ("online", "simulation")
    return {"status": "on" if is_on else "off", "detail": status}


@app.post("/camera/enable")
async def camera_enable():
    """Enable camera feed."""
    from stream import stream_manager
    if not stream_manager.running:
        asyncio.create_task(stream_manager.start())
    else:
        stream_manager.request_camera_reconnect("enable_api")
    return {"status": "on", "message": "Camera enabled"}


@app.post("/camera/disable")
async def camera_disable():
    """Disable camera feed."""
    from stream import stream_manager
    stream_manager.running = False
    stream_manager.camera_state = "offline"
    return {"status": "off", "message": "Camera disabled"}


@app.get("/camera/snapshot")
async def camera_snapshot():
    """Get current camera frame as base64 JPEG for face registration.
    This allows frontend to 'take photo' without needing direct camera access."""
    import base64
    from stream import stream_manager
    
    raw = stream_manager._raw_frame
    if raw is None:
        raise HTTPException(status_code=503, detail="Camera not available")
    
    _, buffer = cv2.imencode(".jpg", raw, [cv2.IMWRITE_JPEG_QUALITY, 90])
    img_b64 = base64.b64encode(buffer.tobytes()).decode("utf-8")
    
    return {
        "image": f"data:image/jpeg;base64,{img_b64}",
        "width": raw.shape[1],
        "height": raw.shape[0],
    }


# ─── Quick Image Analysis (Testing) ──────────────────────────
@app.post("/ai/analyze-image")
async def analyze_uploaded_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Analyze a static image for testing people, PPE, and OCR with robust error handling."""
    try:
        contents = await file.read()
        arr = np.frombuffer(contents, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            raise HTTPException(status_code=400, detail="Gagal membaca file gambar")

        if stream_manager.detector is None:
            stream_manager.init_detector()

        # 1. Pipeline Run
        result = stream_manager.detector.run_photo(frame)
        persons = result["persons"]
        hazards = result.get("env", [])
        road_damage = result.get("road", [])
        safety_cones = result.get("safety_cones", [])
        vehicles = result.get("vehicles", [])

        # 2. Add Identity (OCR + Face Match)
        from face_manager import face_manager
        from ocr_engine import ocr_engine
        
        person_bboxes = [p["bbox"] for p in persons]
        face_results = face_manager.recognize_faces(frame, person_bboxes)
        
        # Per-person OCR. Avoid full-frame fallback here so background text
        # is not assigned to the wrong person.
        ocr_results = ocr_engine.read_all_codes(frame, person_bboxes)

        # Multi-code scan is limited to detected person torso crops.
        all_codes = ocr_engine.read_all_codes_multi(frame, person_bboxes)
        matched_codes = set()

        # Assign identity to each detected person
        for i, det in enumerate(persons):
            if "face_name" not in det: det["face_name"] = "Unknown"
            if "ocr_code" not in det: det["ocr_code"] = None

            if i < len(face_results) and face_results[i]:
                det["face_name"] = face_results[i].get("name", "Unknown")
            if i < len(ocr_results) and ocr_results[i]:
                det["ocr_code"] = ocr_results[i].get("code")
                matched_codes.add(det["ocr_code"])
            
            # Smart Lookup: code → name
            if det.get("face_name") == "Unknown" and det.get("ocr_code"):
                for p_reg in face_manager._registered:
                    if p_reg.get("code") == det["ocr_code"]:
                        det["face_name"] = p_reg["name"]
                        break

        # Add extra OCR detections only when they came from person crops.
        for code_entry in all_codes:
            if code_entry["code"] not in matched_codes:
                name = "Unknown"
                for p_reg in face_manager._registered:
                    if p_reg.get("code") == code_entry["code"]:
                        name = p_reg["name"]
                        break
                persons.append({
                    "bbox": code_entry["bbox"],
                    "label": "OCR Code",
                    "confidence": code_entry["confidence"],
                    "face_name": name,
                    "ocr_code": code_entry["code"],
                })

        # 3. Draw Results for Feedback
        annotated = frame.copy()

        # ─── Dynamic Zone Violation Check ─────────────────────
        from polygon import point_in_polygon
        zone_violations = []
        active_zones = db.query(Zone).filter(Zone.active == True).all()
        zones_data = [
            {
                "id": z.id,
                "name": z.name,
                "vertices": json.loads(z.vertices_json),
                "color": z.color,
                "risk_level": z.risk_level,
            }
            for z in active_zones
        ]

        h, w = frame.shape[:2]
        zone_person_indices = set()
        for i, person in enumerate(persons):
            bbox = person.get("bbox", [0, 0, 0, 0])
            x1, y1, x2, y2 = bbox
            body_points = [
                ((x1 + x2) / 2 / w, (y1 + (y2 - y1) * 0.2) / h),
                ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h),
                ((x1 + x2) / 2 / w, (y2 - 2) / h),
            ]
            for zone in zones_data:
                vertices = zone["vertices"]
                if len(vertices) < 3:
                    continue
                for pt in body_points:
                    if point_in_polygon(pt, vertices):
                        zone_person_indices.add(i)
                        zone_violations.append({
                            "type": "person_in_zone",
                            "person_index": i,
                            "zone_id": zone["id"],
                            "zone_name": zone["name"],
                            "risk_level": zone["risk_level"],
                            "person_name": person.get("face_name", "Unknown"),
                        })
                        break

        # Check env hazards (open hole, fire, smoke) against zones
        for i, hazard in enumerate(hazards):
            bbox = hazard.get("bbox", [0, 0, 0, 0])
            x1, y1, x2, y2 = bbox
            center_pt = ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h)
            for zone in zones_data:
                vertices = zone["vertices"]
                if len(vertices) < 3:
                    continue
                if point_in_polygon(center_pt, vertices):
                    label = hazard.get("class_name", hazard.get("label", "unknown"))
                    zone_violations.append({
                        "type": "hazard_in_zone",
                        "detection_index": i,
                        "label": label,
                        "confidence": round(hazard.get("confidence", 0), 3),
                        "zone_id": zone["id"],
                        "zone_name": zone["name"],
                        "risk_level": zone["risk_level"],
                    })
                    break

        # Only auto-zones on analyze photo (manual zones only on live camera)
        draw_detections(annotated, persons, zone_person_indices, hazards, road_damage, safety_cones, vehicles)
        
        # 4. Encode result image to base64
        _, buffer = cv2.imencode(".jpg", annotated)
        import base64
        img_str = base64.b64encode(buffer).decode()

        # 5. Convert numpy types to native Python (fixes JSON serialization)
        def sanitize(obj):
            if isinstance(obj, np.integer): return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
            if isinstance(obj, dict): return {k: sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)): return [sanitize(x) for x in obj]
            return obj

        clean_persons = sanitize(persons)
        clean_hazards = sanitize(hazards)
        clean_road = sanitize(road_damage)
        clean_cones = sanitize(safety_cones)
        clean_vehicles = sanitize(vehicles)

        return {
            "summary": { "people_found": len(clean_persons), "hazards_found": len(clean_hazards), "road_found": len(clean_road), "vehicles_found": len(clean_vehicles), "zone_violations": len(zone_violations) },
            "detections": clean_persons,
            "hazards": clean_hazards,
            "road": clean_road,
            "safety_cones": clean_cones,
            "vehicles": clean_vehicles,
            "zone_violations": zone_violations,
            "zones_checked": len(zones_data),
            "image": f"data:image/jpeg;base64,{img_str}"
        }
    except Exception as e:
        print(f"[API] Analyze Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")


# ─── Simulation Mode ─────────────────────────────────────────
@app.post("/stream/simulate")
async def start_simulation(file: UploadFile = File(...)):
    """Inject a static image into the live MJPEG stream for testing."""
    contents = await file.read()
    arr = np.frombuffer(contents, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Gagal membaca gambar")
    
    stream_manager.simulation_frame = frame
    return {"status": "simulation_active", "message": "Gambar telah disuntikkan ke stream live"}

@app.post("/stream/reset")
async def reset_stream():
    """Stop simulation and return to live camera feed."""
    stream_manager.simulation_frame = None
    stream_manager.open_camera()
    return {"status": "live_active", "message": "Kembali ke kamera live"}


# ─── Pydantic Schemas ────────────────────────────────────────
class ZoneCreate(BaseModel):
    name: str
    vertices: list  # list of [x, y] normalized
    color: str = "#FF0000"
    active: bool = True
    risk_level: str = "high"

class ZoneUpdate(BaseModel):
    name: Optional[str] = None
    vertices: Optional[list] = None
    color: Optional[str] = None
    active: Optional[bool] = None
    risk_level: Optional[str] = None

class SettingUpdate(BaseModel):
    key: str
    value: str

class ShutdownRequest(BaseModel):
    zone_id: int

class FalsePositiveRequest(BaseModel):
    reason: Optional[str] = None


# ─── MJPEG Stream ────────────────────────────────────────────
@app.get("/stream")
async def video_stream():
    """MJPEG video stream with YOLO detection overlay."""
    return StreamingResponse(
        stream_manager.generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ─── Zone (Polygon) CRUD ─────────────────────────────────────
@app.get("/polygons")
def list_zones(db: Session = Depends(get_db)):
    """List all saved restricted zones."""
    zones = db.query(Zone).order_by(Zone.created_at.desc()).all()
    return [
        {
            "id": z.id,
            "name": z.name,
            "vertices": json.loads(z.vertices_json),
            "color": z.color,
            "active": z.active,
            "risk_level": z.risk_level,
            "created_at": z.created_at.isoformat() if z.created_at else None,
        }
        for z in zones
    ]


@app.post("/polygons")
def create_zone(zone: ZoneCreate, db: Session = Depends(get_db)):
    """Create a new restricted zone."""
    new_zone = Zone(
        name=zone.name,
        vertices_json=json.dumps(zone.vertices),
        color=zone.color,
        active=zone.active,
        risk_level=zone.risk_level,
    )
    db.add(new_zone)
    db.commit()
    db.refresh(new_zone)
    result = {
        "id": new_zone.id,
        "name": new_zone.name,
        "vertices": zone.vertices,
        "color": new_zone.color,
        "active": new_zone.active,
        "risk_level": new_zone.risk_level,
        "created_at": new_zone.created_at.isoformat() if new_zone.created_at else None,
    }
    from stream import stream_manager
    stream_manager.refresh_zones()
    return result


@app.put("/polygons/{zone_id}")
def update_zone(zone_id: int, update: ZoneUpdate, db: Session = Depends(get_db)):
    """Update an existing restricted zone."""
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    if update.name is not None:
        zone.name = update.name
    if update.vertices is not None:
        zone.vertices_json = json.dumps(update.vertices)
    if update.color is not None:
        zone.color = update.color
    if update.active is not None:
        zone.active = update.active
    if update.risk_level is not None:
        zone.risk_level = update.risk_level

    db.commit()
    db.refresh(zone)
    result = {
        "id": zone.id,
        "name": zone.name,
        "vertices": json.loads(zone.vertices_json),
        "color": zone.color,
        "active": zone.active,
        "risk_level": zone.risk_level,
    }
    from stream import stream_manager
    stream_manager.refresh_zones()
    return result


@app.delete("/polygons/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    """Delete a restricted zone and all its related records (Alerts, Shutdowns, Occupancy)."""
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    
    from models import ShutdownLog, ZoneOccupancy
    
    # 1. Delete all related records first (Cascade delete)
    db.query(Alert).filter(Alert.zone_id == zone_id).delete()
    db.query(ShutdownLog).filter(ShutdownLog.zone_id == zone_id).delete()
    db.query(ZoneOccupancy).filter(ZoneOccupancy.zone_id == zone_id).delete()
    
    # 2. Delete the zone
    db.delete(zone)
    db.commit()
    from stream import stream_manager
    stream_manager.refresh_zones()
    return {"status": "deleted", "id": zone_id}


# ─── Alerts ───────────────────────────────────────────────────
@app.get("/alerts")
def list_alerts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    zone_id: Optional[int] = None,
    risk_level: Optional[str] = None,
    resolved: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """Paginated incident log with optional filters."""
    # Simple query for maximum reliability
    query = db.query(Alert).order_by(Alert.timestamp.desc())
    total = query.count()
    alerts = query.offset((page - 1) * limit).limit(limit).all()

    result = []
    for a in alerts:
        # Get zone info safely
        zname = "Unknown Zone"
        risk = "high"  # Default to high for safety
        if a.zone_id:
            zone = db.query(Zone).filter(Zone.id == a.zone_id).first()
            if zone:
                zname = zone.name
                risk = zone.risk_level
            else:
                # PPE violations use hashed zone_id — show violation type instead
                vtype = a.violation_type or ""
                if "ppe" in vtype:
                    zname = "PPE Violation"
                    risk = "high"
                elif "fire" in vtype or "smoke" in vtype:
                    zname = "Fire/Smoke Detected"
                    risk = "high"
                elif "zone" in vtype:
                    zname = "Zone Violation"

        result.append({
            "alert_id": a.id,
            "zone_id": a.zone_id,
            "zone_name": zname,
            "risk_level": risk,
            "confidence": a.confidence,
            "snapshot_url": f"/{a.snapshot_path}" if a.snapshot_path and not a.snapshot_path.startswith("/") else a.snapshot_path,
            "timestamp": a.timestamp.isoformat() if hasattr(a.timestamp, "isoformat") else str(a.timestamp),
            "shutdown_triggered": a.shutdown_triggered,
            "resolved": a.resolved,
            "false_positive": a.false_positive or False,
            "person_name": a.person_name or "Unknown",
            "uniform_code": a.uniform_code,
            "violation_type": a.violation_type or "",
            "ppe_detail": json.loads(a.ppe_detail) if a.ppe_detail else None,
        })
    return {"total": total, "items": result}


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark an incident as resolved."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    db.commit()
    return {"status": "resolved", "id": alert_id}


@app.post("/alerts/resolve-all")
def resolve_all_alerts(db: Session = Depends(get_db)):
    """Bulk resolve all unresolved alerts."""
    count = db.query(Alert).filter(Alert.resolved == False).update({"resolved": True})
    db.commit()
    return {"status": "resolved", "count": count}


@app.post("/alerts/{alert_id}/false-positive")
def mark_false_positive(alert_id: int, req: FalsePositiveRequest, db: Session = Depends(get_db)):
    """Mark an alert as false positive and resolve it. Also raises adaptive threshold."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.false_positive = True
    alert.resolved = True
    db.query(DetectionLog).filter(DetectionLog.alert_id == alert_id).update(
        {"is_false_positive": True}
    )
    db.commit()

    # Adaptive threshold: raise threshold for the class that caused this FP
    from stream import stream_manager
    violation_type = alert.violation_type or ""
    zone_name = ""
    try:
        from models import Zone as ZoneModel
        z = db.query(ZoneModel).filter(ZoneModel.id == alert.zone_id).first()
        zone_name = z.name.lower() if z else ""
    except Exception:
        pass

    # Determine which class label to penalize
    if "smoke" in zone_name or "smoke" in violation_type:
        class_label = "smoke"
    elif "fire" in zone_name or "fire" in violation_type:
        class_label = "fire"
    elif "ppe" in violation_type or "helmet" in zone_name or "vest" in zone_name:
        class_label = "ppe_violation"
    else:
        class_label = violation_type or "unknown"

    from stream import report_false_positive
    report_false_positive(class_label)

    return {"status": "marked_false_positive", "id": alert_id, "adjusted_class": class_label}


@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Delete a single alert and its snapshot file."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    # Delete related detection logs
    db.query(DetectionLog).filter(DetectionLog.alert_id == alert_id).delete()
    # Delete snapshot file
    if alert.snapshot_path:
        snapshot_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), alert.snapshot_path)
        if os.path.exists(snapshot_file):
            os.remove(snapshot_file)
    db.delete(alert)
    db.commit()
    return {"status": "deleted", "id": alert_id}


@app.delete("/alerts")
def delete_all_alerts(db: Session = Depends(get_db)):
    """Delete all alerts and their snapshot files."""
    import shutil
    db.query(DetectionLog).delete()
    count = db.query(Alert).count()
    db.query(Alert).delete()
    db.commit()
    # Clear snapshot directory
    snapshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "snapshots")
    if os.path.exists(snapshot_dir):
        shutil.rmtree(snapshot_dir)
        os.makedirs(snapshot_dir)
    return {"status": "deleted", "count": count}


@app.get("/alerts/{alert_id}/detections")
def get_detection_logs(alert_id: int, db: Session = Depends(get_db)):
    """Get per-object detection crops for an alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    logs = db.query(DetectionLog).filter(DetectionLog.alert_id == alert_id).all()
    return [
        {
            "id": l.id,
            "class_name": l.class_name,
            "confidence": l.confidence,
            "crop_url": f"/{l.crop_path}" if l.crop_path else None,
            "frame_number": l.frame_number,
            "bbox": json.loads(l.bbox_json) if l.bbox_json else None,
            "is_false_positive": l.is_false_positive,
        }
        for l in logs
    ]


# ─── Shutdown ─────────────────────────────────────────────────
@app.post("/shutdown/trigger")
def manual_shutdown(req: ShutdownRequest, db: Session = Depends(get_db)):
    """Manually trigger shutdown signal for a zone."""
    zone = db.query(Zone).filter(Zone.id == req.zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    trigger_relay(zone.name)
    log = log_shutdown(db, zone.id, trigger_source="manual")

    return {
        "status": "triggered",
        "zone_name": zone.name,
        "log_id": log.id,
        "triggered_at": log.triggered_at.isoformat(),
    }


# ─── Settings ─────────────────────────────────────────────────
@app.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """Get all system settings."""
    settings = db.query(Setting).all()
    return {s.key: s.value for s in settings}


@app.post("/settings")
def update_setting(setting: SettingUpdate, db: Session = Depends(get_db)):
    """Update a setting key-value."""
    existing = db.query(Setting).filter(Setting.key == setting.key).first()
    if existing:
        existing.value = setting.value
    else:
        new_setting = Setting(key=setting.key, value=setting.value)
        db.add(new_setting)
    db.commit()

    # Reload stream settings if applicable
    stream_manager.load_settings()

    return {"status": "updated", "key": setting.key, "value": setting.value}


@app.post("/settings/notify-test")
async def test_notification(db: Session = Depends(get_db)):
    """Send test WhatsApp to all recipients."""
    settings = {s.key: s.value for s in db.query(Setting).all()}
    token = settings.get("fonnte_token", "")
    recipients = settings.get("recipients", "")
    facility = settings.get("facility_name", "Offshore Platform A")

    results = await send_test_message(token, recipients, facility)
    return {"status": "sent", "results": results}


# ─── WebSocket ────────────────────────────────────────────────
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    """Real-time alert push via WebSocket."""
    await websocket.accept()
    stream_manager.ws_clients.add(websocket)
    try:
        while True:
            # Keep connection alive; client can send ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        stream_manager.ws_clients.discard(websocket)
    except Exception:
        stream_manager.ws_clients.discard(websocket)


# ─── Browser Camera WebSocket ────────────────────────────────
def _run_pipeline_sync(frame: np.ndarray):
    """Run detection pipeline synchronously (called from thread executor)."""
    if stream_manager.pipeline is None:
        stream_manager.load_settings()
        stream_manager.init_pipeline()
    pipeline = stream_manager.pipeline
    if pipeline is None:
        return frame

    try:
        result = stream_manager.pipeline.run(frame)
        with stream_manager._result_lock:
            stream_manager._last_result["persons"] = result["persons"]
            stream_manager._last_result["env"] = result.get("env", [])
            stream_manager._last_result["vehicles"] = result.get("vehicles", [])
        draw_persons(frame, result["persons"], set())
        draw_vehicles(frame, result.get("vehicles", []))
    except Exception as e:
        print(f"[WS-CAMERA] Pipeline error: {e}")

    return frame


@app.websocket("/ws/camera")
async def websocket_camera(websocket: WebSocket):
    """Receive JPEG frames from browser camera, run AI detection, return annotated frame.
    Uses thread executor so YOLO inference doesn't block the async event loop.
    Auto-reconnect on pipeline failure after exponential backoff."""
    await websocket.accept()
    print("[WS-CAMERA] Browser camera connected")

    loop = asyncio.get_event_loop()
    frame_idx = 0
    processing = False  # backpressure: skip if previous inference still running

    # Reconnect state for browser camera pipeline failures
    _pipeline_failures = 0
    _next_retry_at = 0.0

    def _retry_delay() -> float:
        return min(30.0, 2.0 + (_pipeline_failures * 2.0))

    try:
        while True:
            data = await websocket.receive_bytes()
            if not data:
                continue

            frame_idx += 1

            # Decode frame (fast, sync ok)
            arr = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            # Run AI detection every 3rd frame & only if previous is done
            if frame_idx % 3 == 0 and not processing:
                processing = True
                try:
                    annotated = await loop.run_in_executor(
                        None, _run_pipeline_sync, frame.copy()
                    )
                    _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    await websocket.send_bytes(jpeg.tobytes())
                    _pipeline_failures = 0  # reset on success
                except Exception as e:
                    print(f"[WS-CAMERA] Inference error: {e}")
                    _pipeline_failures += 1
                    if time.time() >= _next_retry_at:
                        _next_retry_at = time.time() + _retry_delay()
                        print(f"[WS-CAMERA] Reinitializing pipeline, attempt {_pipeline_failures}")
                        try:
                            stream_manager.init_pipeline()
                        except Exception as pe:
                            print(f"[WS-CAMERA] Pipeline reinit failed: {pe}")
                finally:
                    processing = False

    except WebSocketDisconnect:
        print("[WS-CAMERA] Browser camera disconnected")
    except Exception as e:
        print(f"[WS-CAMERA] Error: {e}")


# ─── Analytics Endpoint ──────────────────────────────────────
@app.get("/analytics/compliance")
def get_compliance_analytics(db: Session = Depends(get_db)):
    """PPE compliance statistics."""
    from datetime import timedelta
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total = db.query(Alert).filter(Alert.timestamp >= today_start, Alert.false_positive == False).count()
    ppe_viols = db.query(Alert).filter(
        Alert.timestamp >= today_start,
        Alert.false_positive == False,
        Alert.violation_type.in_(["missing_ppe", "no_harness", "multiple"]),
    ).count()
    fire_smoke = db.query(Alert).filter(
        Alert.timestamp >= today_start,
        Alert.false_positive == False,
        Alert.violation_type == "fire_smoke",
    ).count()
    false_positives = db.query(Alert).filter(
        Alert.timestamp >= today_start,
        Alert.false_positive == True,
    ).count()

    return {
        "today_total_violations": total,
        "ppe_violations": ppe_viols,
        "fire_smoke_alerts": fire_smoke,
        "false_positives_today": false_positives,
        "false_positive_rate": round(false_positives / max(total + false_positives, 1) * 100, 1),
    }


# ─── Video Upload & Processing ────────────────────────────────
@app.post("/video/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload a video file for async multi-stage detection processing."""
    allowed = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = f"{ts}_{file.filename.replace(' ', '_')}"
    dest_path = os.path.join(UPLOADS_DIR, safe_name)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    job = VideoJob(
        filename=file.filename,
        file_path=dest_path,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(video_processor.process_video, job.id)

    return {
        "job_id": job.id,
        "filename": file.filename,
        "status": "pending",
        "message": "Video uploaded. Processing started in background.",
    }


@app.get("/video/jobs")
def list_video_jobs(db: Session = Depends(get_db)):
    """List all video processing jobs."""
    jobs = db.query(VideoJob).order_by(VideoJob.created_at.desc()).limit(50).all()
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "status": j.status,
            "progress": j.progress,
            "total_frames": j.total_frames,
            "processed_frames": j.processed_frames,
            "annotated_video_path": j.annotated_video_path,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@app.get("/video/annotated/{job_id}")
def get_annotated_video(job_id: int, request: Request, db: Session = Depends(get_db)):
    """Serve the annotated video file with HTTP Range support for browser playback."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Handle both forward and backslash paths (Windows/Linux compatibility)
    video_path = job.annotated_video_path.replace("\\", "/") if job.annotated_video_path else None
    if not video_path or (not os.path.exists(video_path) and not os.path.exists(job.annotated_video_path)):
        raise HTTPException(status_code=404, detail="Annotated video not found")

    # Resolve actual file path
    filename = os.path.basename(video_path)
    static_path = os.path.join(STATIC_DIR, "uploads", filename)
    if os.path.exists(static_path):
        file_path = static_path
    elif os.path.exists(video_path):
        file_path = video_path
    elif os.path.exists(job.annotated_video_path):
        file_path = job.annotated_video_path
    else:
        raise HTTPException(status_code=404, detail="Annotated video file not found on disk")

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    if range_header:
        # Parse Range header: "bytes=start-end"
        range_str = range_header.replace("bytes=", "")
        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        end = min(end, file_size - 1)
        content_length = end - start + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(65536, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    # No range header — return full file
    return FileResponse(file_path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})


@app.get("/video/jobs/{job_id}")
def get_video_job(job_id: int, db: Session = Depends(get_db)):
    """Get status and progress of a video job."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "filename": job.filename,
        "status": job.status,
        "progress": job.progress,
        "total_frames": job.total_frames,
        "processed_frames": job.processed_frames,
        "annotated_video_path": job.annotated_video_path,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@app.get("/video/jobs/{job_id}/result")
def get_video_result(job_id: int, db: Session = Depends(get_db)):
    """Get full detection results of a completed video job."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done":
        raise HTTPException(status_code=409, detail=f"Job not done yet. Status: {job.status}")
    result = json.loads(job.result_json) if job.result_json else []
    violations = [f for f in result if f.get("has_violation")]
    return {
        "job_id": job_id,
        "filename": job.filename,
        "total_frames_processed": job.processed_frames,
        "total_violation_frames": len(violations),
        "annotated_video_path": job.annotated_video_path,
        "frames": result,
    }


@app.delete("/video/jobs/{job_id}")
def delete_video_job(job_id: int, db: Session = Depends(get_db)):
    """Delete a video job and its uploaded file."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if os.path.exists(job.file_path):
        os.remove(job.file_path)
    # Also delete annotated video if exists
    if job.annotated_video_path and os.path.exists(job.annotated_video_path):
        os.remove(job.annotated_video_path)
    db.delete(job)
    db.commit()
    return {"status": "deleted", "id": job_id}


@app.post("/video/jobs/{job_id}/reprocess")
async def reprocess_video(job_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Re-process an existing video job with current zones. Generates new alerts."""
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Original video file not found")

    # Delete old annotated video
    if job.annotated_video_path and os.path.exists(job.annotated_video_path):
        os.remove(job.annotated_video_path)

    # Reset job status
    job.status = "pending"
    job.progress = 0
    job.processed_frames = 0
    job.result_json = None
    job.annotated_video_path = None
    job.error_message = None
    job.completed_at = None
    db.commit()

    # Start reprocessing in background
    background_tasks.add_task(video_processor.process_video, job.id)

    return {
        "job_id": job.id,
        "status": "pending",
        "message": "Video re-processing started with current zones.",
    }


@app.post("/video/jobs/{job_id}/check-frame")
async def check_video_frame(job_id: int, timestamp: float = Query(0), db: Session = Depends(get_db)):
    """
    Check violations for a specific frame timestamp in a processed video.
    Called by frontend during video playback to generate real-time alerts.
    Uses the stored result_json to check against current active zones.
    """
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job or job.status != "done" or not job.result_json:
        return {"violations": []}

    # Find the closest frame to the requested timestamp
    frames = json.loads(job.result_json)
    if not frames:
        return {"violations": []}

    # Find frame closest to timestamp
    closest = min(frames, key=lambda f: abs(f["timestamp_sec"] - timestamp))

    # Get active zones
    active_zones = db.query(Zone).filter(Zone.active == True).all()
    zones_data = [
        {"id": z.id, "name": z.name, "vertices": json.loads(z.vertices_json), "risk_level": z.risk_level}
        for z in active_zones
    ]

    if not zones_data and not closest.get("persons"):
        return {"violations": []}

    # Check violations using the stored detection data
    from violation_checker import ViolationChecker, Violation
    from polygon import point_in_polygon

    violations_found = []

    # Check persons against zones
    persons = closest.get("persons", [])
    for i, person in enumerate(persons):
        bbox = person.get("bbox", [0, 0, 0, 0])
        x1, y1, x2, y2 = bbox
        # Assume frame dimensions from video (use job metadata or default)
        frame_w = 1280
        frame_h = 720

        cx = ((x1 + x2) / 2) / frame_w
        cy = ((y1 + y2) / 2) / frame_h

        for zone in zones_data:
            verts = zone.get("vertices", [])
            if len(verts) < 3:
                continue
            if point_in_polygon([cx, cy], verts):
                violations_found.append({
                    "type": "zone_violation",
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "risk_level": zone["risk_level"],
                    "confidence": person.get("confidence", 0),
                    "person_index": i,
                })
                break

        # PPE violations
        ppe_violations = person.get("ppe_violations", [])
        if ppe_violations:
            violations_found.append({
                "type": "ppe_violation",
                "zone_id": hash(f"ppe_{i}") % 10000,
                "zone_name": f"PPE Violation ({', '.join(ppe_violations)})",
                "risk_level": "high",
                "confidence": person.get("confidence", 0),
                "person_index": i,
            })

    # Check env hazards (fire/smoke)
    for hazard in closest.get("env", []):
        category = hazard.get("category", "")
        class_name = hazard.get("class_name", "")
        if category == "fire_smoke" or class_name.lower() in ("fire", "smoke"):
            violations_found.append({
                "type": "fire_smoke",
                "zone_id": 998 if class_name.lower() == "fire" else 997,
                "zone_name": f"{class_name.title()} Detected",
                "risk_level": "high",
                "confidence": hazard.get("confidence", 0),
            })

    return {
        "frame": closest.get("frame", 0),
        "timestamp_sec": closest.get("timestamp_sec", 0),
        "violations": violations_found,
    }


class VideoAlertRequest(BaseModel):
    job_id: int
    zone_id: int
    zone_name: str
    risk_level: str = "high"
    confidence: float = 0.0
    violation_type: str = "zone_violation"
    timestamp_sec: float = 0.0
    person_name: str = "Unknown"
    uniform_code: Optional[str] = None


# Cooldown tracker for video playback alerts (prevent spam)
_video_alert_cooldowns: dict = {}


@app.post("/video/alert")
async def create_video_alert(req: VideoAlertRequest, db: Session = Depends(get_db)):
    """Create an alert from video playback detection. Same logic as live stream alerts."""
    import time as time_mod

    # Cooldown: 10 seconds per zone_id
    now = time_mod.time()
    last = _video_alert_cooldowns.get(req.zone_id, 0)
    if now - last < 10:
        return {"status": "cooldown", "message": "Alert already sent recently"}
    _video_alert_cooldowns[req.zone_id] = now

    now_utc = datetime.now(timezone.utc)

    # Create alert in database
    alert = Alert(
        zone_id=req.zone_id,
        confidence=req.confidence,
        snapshot_path=None,
        timestamp=now_utc,
        shutdown_triggered=False,
        resolved=False,
        violation_type=req.violation_type,
        person_name=req.person_name,
        uniform_code=req.uniform_code,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    # Broadcast via WebSocket
    ws_event = {
        "type": "alert",
        "alert_id": alert.id,
        "zone_name": req.zone_name,
        "zone_id": req.zone_id,
        "risk_level": req.risk_level,
        "timestamp": now_utc.isoformat(),
        "confidence": req.confidence,
        "snapshot_url": None,
        "shutdown_triggered": False,
        "person_name": req.person_name,
        "uniform_code": req.uniform_code,
        "violation_type": req.violation_type,
        "source": "video_playback",
    }
    await stream_manager._broadcast_to_ws(ws_event)

    # Send WhatsApp notification
    settings = {s.key: s.value for s in db.query(Setting).all()}
    fonnte_token = settings.get("fonnte_token", "")
    recipients = settings.get("recipients", "")
    facility_name = settings.get("facility_name", "Offshore Platform A")

    if fonnte_token and recipients:
        from notifier import send_to_all_recipients
        try:
            await send_to_all_recipients(
                recipients, req.zone_name, req.risk_level, req.confidence,
                False, facility_name, "",
                snapshot_url=None,
                person_name=req.person_name, uniform_code=req.uniform_code
            )
        except Exception as e:
            print(f"[VIDEO-ALERT] Notification error: {e}")

    return {"status": "alerted", "alert_id": alert.id}


# ─── Image Analysis ───────────────────────────────────────────
@app.post("/analyze/image")
async def analyze_image(file: UploadFile = File(...)):
    """
    Upload a single image and run the active detection pipeline.
    Returns annotated image (JPEG base64) + detection JSON.
    """
    allowed = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}. Use jpg/png/bmp/webp.")

    # Read and decode image
    contents = await file.read()
    arr = np.frombuffer(contents, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Gagal membaca gambar. Pastikan file tidak rusak.")

    # Ensure pipeline is ready
    if stream_manager.detector is None:
        stream_manager.init_detector()

    detector = stream_manager.detector
    if detector is None:
        raise HTTPException(status_code=503, detail="Pipeline belum siap. Restart backend.")

    # Run detection
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, detector.run_photo, frame.copy())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection error: {e}")

    persons = result.get("persons", [])
    env_detections = result.get("env", [])
    road_detections = result.get("road", [])
    safety_cones = result.get("safety_cones", [])
    vehicles = result.get("vehicles", [])

    # Add face/OCR identity to static image analysis as well.
    from ocr_engine import ocr_engine
    person_bboxes = [p.get("bbox", []) for p in persons]
    face_results = face_manager.recognize_faces(frame, person_bboxes)
    ocr_results = ocr_engine.read_all_codes(frame, person_bboxes)

    for i, person in enumerate(persons):
        person.setdefault("face_name", "Unknown")
        person.setdefault("ocr_code", None)

        if i < len(face_results) and face_results[i]:
            person["face_name"] = face_results[i].get("name", "Unknown")

        if i < len(ocr_results) and ocr_results[i]:
            person["ocr_code"] = ocr_results[i].get("code")

        if person.get("face_name") == "Unknown" and person.get("ocr_code"):
            for registered in face_manager._registered:
                if registered.get("code") == person["ocr_code"]:
                    person["face_name"] = registered["name"]
                    break

    # violation_indices: persons that have ppe_violations OR are inside restricted zones
    violation_indices = {
        i for i, p in enumerate(persons) if p.get("ppe_violations")
    }

    # ─── Dynamic Zone Violation Check ─────────────────────────
    from polygon import point_in_polygon
    from database import SessionLocal
    zone_violations = []
    db_zones = SessionLocal()
    try:
        active_zones = db_zones.query(Zone).filter(Zone.active == True).all()
        zones_data = [
            {
                "id": z.id,
                "name": z.name,
                "vertices": json.loads(z.vertices_json),
                "color": z.color,
                "risk_level": z.risk_level,
            }
            for z in active_zones
        ]
    finally:
        db_zones.close()

    h, w = frame.shape[:2]

    # Check persons against manual zones
    for i, person in enumerate(persons):
        bbox = person.get("bbox", [0, 0, 0, 0])
        x1, y1, x2, y2 = bbox

        # Check 3 body points (normalized)
        body_points = [
            ((x1 + x2) / 2 / w, (y1 + (y2 - y1) * 0.2) / h),  # head
            ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h),            # chest
            ((x1 + x2) / 2 / w, (y2 - 2) / h),                 # feet
        ]

        for zone in zones_data:
            vertices = zone["vertices"]
            if len(vertices) < 3:
                continue
            for pt in body_points:
                if point_in_polygon(pt, vertices):
                    violation_indices.add(i)
                    zone_violations.append({
                        "type": "person_in_zone",
                        "person_index": i,
                        "zone_id": zone["id"],
                        "zone_name": zone["name"],
                        "risk_level": zone["risk_level"],
                        "person_name": person.get("face_name", "Unknown"),
                    })
                    break

    # Check env hazards (open hole, fire, smoke) against manual zones
    for i, hazard in enumerate(env_detections):
        bbox = hazard.get("bbox", [0, 0, 0, 0])
        x1, y1, x2, y2 = bbox
        center_pt = ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h)

        for zone in zones_data:
            vertices = zone["vertices"]
            if len(vertices) < 3:
                continue
            if point_in_polygon(center_pt, vertices):
                label = hazard.get("class_name", hazard.get("label", "unknown"))
                zone_violations.append({
                    "type": "hazard_in_zone",
                    "detection_index": i,
                    "label": label,
                    "confidence": round(hazard.get("confidence", 0), 3),
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "risk_level": zone["risk_level"],
                })
                break

    # Check road damage (pothole/lubang jalan) against manual zones
    for i, road in enumerate(road_detections):
        bbox = road.get("bbox", [0, 0, 0, 0])
        x1, y1, x2, y2 = bbox
        center_pt = ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h)

        for zone in zones_data:
            vertices = zone["vertices"]
            if len(vertices) < 3:
                continue
            if point_in_polygon(center_pt, vertices):
                label = road.get("class_name", "pothole")
                zone_violations.append({
                    "type": "road_damage_in_zone",
                    "detection_index": i,
                    "label": label,
                    "confidence": round(road.get("confidence", 0), 3),
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "risk_level": zone["risk_level"],
                })
                break

    # ─── Auto-Generated Dynamic Zones ─────────────────────────
    # Automatically create polygon zones around detected hazards
    # (pothole, open hole, fire, smoke) — no manual zone needed.
    auto_zones = []

    # Auto-zone for env hazards (open hole, fire, smoke)
    for i, hazard in enumerate(env_detections):
        bbox = hazard.get("bbox", [0, 0, 0, 0])
        x1, y1, x2, y2 = bbox
        label = hazard.get("class_name", hazard.get("label", "unknown"))
        conf = hazard.get("confidence", 0)

        # Generate polygon from bbox with padding (normalized)
        pad = 0.02  # 2% padding
        nv = [
            [max(0, x1 / w - pad), max(0, y1 / h - pad)],
            [min(1, x2 / w + pad), max(0, y1 / h - pad)],
            [min(1, x2 / w + pad), min(1, y2 / h + pad)],
            [max(0, x1 / w - pad), min(1, y2 / h + pad)],
        ]
        display_name = label.replace("_", " ").upper()
        auto_zone = {
            "id": None,
            "name": f"DANGER: {display_name}",
            "vertices": nv,
            "color": "#FF0000",
            "risk_level": "high",
        }
        auto_zones.append(auto_zone)
        zone_violations.append({
            "type": "auto_zone_hazard",
            "detection_index": i,
            "label": label,
            "confidence": round(conf, 3),
            "zone_name": f"DANGER: {display_name}",
            "risk_level": "high",
        })

    # Auto-zone for road damage (pothole/lubang)
    for i, road in enumerate(road_detections):
        bbox = road.get("bbox", [0, 0, 0, 0])
        x1, y1, x2, y2 = bbox
        label = road.get("class_name", "pothole")
        conf = road.get("confidence", 0)

        pad = 0.02
        nv = [
            [max(0, x1 / w - pad), max(0, y1 / h - pad)],
            [min(1, x2 / w + pad), max(0, y1 / h - pad)],
            [min(1, x2 / w + pad), min(1, y2 / h + pad)],
            [max(0, x1 / w - pad), min(1, y2 / h + pad)],
        ]
        display_name = label.replace("_", " ").upper()
        auto_zone = {
            "id": None,
            "name": f"DANGER: {display_name}",
            "vertices": nv,
            "color": "#FF6600",
            "risk_level": "high",
        }
        auto_zones.append(auto_zone)
        zone_violations.append({
            "type": "auto_zone_road",
            "detection_index": i,
            "label": label,
            "confidence": round(conf, 3),
            "zone_name": f"DANGER: {display_name}",
            "risk_level": "high",
        })

    annotated = frame.copy()
    # Only draw auto-generated zones on analyze photo (manual zones only on live camera)
    if auto_zones:
        draw_zones(annotated, auto_zones)
    draw_persons(annotated, persons, violation_indices)
    draw_env_hazards(annotated, env_detections)
    draw_road_damage(annotated, road_detections)
    draw_safety_cones(annotated, safety_cones)
    draw_vehicles(annotated, vehicles)

    # Encode annotated image to base64
    import base64
    _, jpeg_buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
    img_b64 = base64.b64encode(jpeg_buf.tobytes()).decode("utf-8")

    # Build detection summary
    person_list = [
        {
            "bbox": p.get("bbox", []),
            "confidence": round(p.get("confidence", 0), 3),
            "violations": p.get("ppe_violations", []),
            "ppe_status": p.get("ppe_result", {}),
            "face_name": p.get("face_name", "Unknown"),
            "ocr_code": p.get("ocr_code"),
        }
        for p in persons
    ]

    env_list = [
        {
            "label": e.get("class_name", e.get("label", "")),
            "confidence": round(e.get("confidence", 0), 3),
            "bbox": e.get("bbox", []),
            "category": e.get("category"),
        }
        for e in env_detections
    ]

    road_list = [
        {
            "label": r.get("class_name", ""),
            "confidence": round(r.get("confidence", 0), 3),
            "bbox": r.get("bbox", []),
        }
        for r in road_detections
    ]

    safety_cone_list = [
        {
            "label": s.get("class_name", ""),
            "confidence": round(s.get("confidence", 0), 3),
            "bbox": s.get("bbox", []),
        }
        for s in safety_cones
    ]

    vehicle_list = [
        {
            "label": v.get("class_name", v.get("label", "")),
            "confidence": round(v.get("confidence", 0), 3),
            "bbox": v.get("bbox", []),
            "class_id": v.get("class_id"),
        }
        for v in vehicles
    ]

    hazard_violation_found = any(
        (e.get("category") == "fire_smoke")
        or (e.get("label") or e.get("class_name") or "").lower() in FIRE_SMOKE_LABELS
        or (e.get("label") or e.get("class_name") or "").lower() in {"open-hole", "open_hole"}
        for e in env_detections
    )

    return {
        "annotated_image": f"data:image/jpeg;base64,{img_b64}",
        "image_size": {"width": frame.shape[1], "height": frame.shape[0]},
        "detections": {
            "persons": person_list,
            "env": env_list,
            "road": road_list,
            "safety_cones": safety_cone_list,
            "vehicles": vehicle_list,
            "total_persons": len(persons),
            "total_env": len(env_detections),
            "total_road": len(road_detections),
            "total_safety_cones": len(safety_cones),
            "total_vehicles": len(vehicles),
            "violations_found": bool(violation_indices) or hazard_violation_found or bool(zone_violations),
            "zone_violations": zone_violations,
            "zones_checked": len(zones_data),
        },
    }


# ─── Face Management ──────────────────────────────────────────
@app.get("/faces")
def list_faces(include_samples: bool = Query(False, description="Include all sample URLs (internal use)")):
    """
    List all registered faces.

    - Default: returns primary image URL only (frontend compatible).
    - ?include_samples=true: returns all sample URLs per person (admin/internal use).
    """
    return face_manager.get_all_faces(include_all_samples=include_samples)


@app.post("/faces/register")
async def register_face(
    name: str = Query(...),
    code: str = Query(""),
    phone: str = Query(""),
    file: UploadFile = File(...),
):
    """Register a new face from an uploaded image.
    If person with same name/code exists, adds encoding to their profile (multi-angle)."""
    contents = await file.read()
    result = face_manager.register_face(contents, name, code, phone)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Gagal registrasi wajah"))
    return result


@app.post("/faces/register-multi")
async def register_face_multi(
    name: str = Query(...),
    code: str = Query(""),
    phone: str = Query(""),
    files: List[UploadFile] = File(...),
):
    """Register multiple photos for one person at once (multi-angle support).
    All photos are assigned to the same person ID."""
    if not files:
        raise HTTPException(status_code=400, detail="Tidak ada file yang diupload")

    results = []
    for f in files:
        contents = await f.read()
        result = face_manager.register_face(contents, name, code, phone)
        results.append(result)

    success_count = sum(1 for r in results if r.get("success"))
    failed_count = len(results) - success_count

    if success_count == 0:
        raise HTTPException(status_code=400, detail="Semua foto gagal diproses. Pastikan wajah terlihat jelas.")

    # Get final person info
    person_id = next((r["id"] for r in results if r.get("success")), None)
    total_encodings = max((r.get("total_encodings", 0) for r in results if r.get("success")), default=0)

    return {
        "success": True,
        "id": person_id,
        "name": name,
        "code": code,
        "phone": phone,
        "photos_registered": success_count,
        "photos_failed": failed_count,
        "total_encodings": total_encodings,
        "message": f"{success_count} foto berhasil didaftarkan untuk {name}",
    }


@app.delete("/faces/{face_id}")
def delete_face(face_id: str):
    """Delete a registered face."""
    success = face_manager.delete_face(face_id)
    if not success:
        raise HTTPException(status_code=404, detail="Face ID not found")
    return {"status": "deleted", "id": face_id}


@app.put("/faces/{face_id}")
def update_face(face_id: str, name: str = Query(None), code: str = Query(None), phone: str = Query(None)):
    """Update personnel info (name, code, phone)."""
    for entry in face_manager._registered:
        if entry["id"] == face_id:
            if name is not None:
                entry["name"] = name
            if code is not None:
                entry["code"] = code
            if phone is not None:
                entry["phone"] = phone
            face_manager._save_db()
            return {"status": "updated", "id": face_id, "name": entry["name"], "code": entry["code"], "phone": entry.get("phone", "")}
    raise HTTPException(status_code=404, detail="Face ID not found")


@app.post("/faces/{face_id}/sample")
async def add_face_sample(face_id: str, file: UploadFile = File(...)):
    """
    Add additional face sample to improve recognition accuracy.
    More samples from different angles = better matching.
    """
    contents = await file.read()
    result = face_manager.add_face_sample(face_id, contents)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Gagal tambah sample"))
    return result


@app.post("/faces/train")
def train_faces():
    """
    Sync & Train: Re-encode all registered faces with current engine (ArcFace).
    Use after changing face recognition engine or when recognition is inaccurate.
    """
    result = face_manager.retrain_all()
    return result


# ─── Stats Endpoint ───────────────────────────────────────────
@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """Dashboard stats."""
    from datetime import timedelta
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    total_zones = db.query(Zone).count()
    active_zones = db.query(Zone).filter(Zone.active == True).count()
    total_alerts = db.query(Alert).count()
    today_alerts = db.query(Alert).filter(Alert.timestamp >= today_start).count()
    unresolved = db.query(Alert).filter(Alert.resolved == False).count()
    total_shutdowns = db.query(ShutdownLog).count()

    fp_today = db.query(Alert).filter(
        Alert.timestamp >= today_start,
        Alert.false_positive == True,
    ).count()

    return {
        "total_zones": total_zones,
        "active_zones": active_zones,
        "total_alerts": total_alerts,
        "today_alerts": today_alerts,
        "unresolved_alerts": unresolved,
        "total_shutdowns": total_shutdowns,
        "false_positives_today": fp_today,
        "camera_status": stream_manager.camera_status(),
    }
# ─── Agentic AI & LLM Automation ─────────────────────────────
class ReportRequest(BaseModel):
    alert_id: int

@app.post("/ai/generate-report")
async def generate_incident_report(req: ReportRequest, db: Session = Depends(get_db)):
    """
    Fitur: Otomasi Dokumen (LLM).
    Menggunakan Gemini (simulasi) untuk membuat rincian laporan insiden yang profesional.
    """
    alert = db.query(Alert).filter(Alert.id == req.alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Simulasi prompt LLM
    prompt = f"Buat laporan keselamatan kerja untuk insiden di {alert.zone.name} pada {alert.timestamp}. Risiko: {alert.zone.risk_level}."
    
    # Mock LLM Response (Dapat diintegrasikan dengan LangChain/Gemini SDK)
    report = {
        "title": f"LAPORAN INSIDEN KESELAMATAN - #{alert.id}",
        "summary": f"Telah terjadi pelanggaran area di {alert.zone.name}. Sistem mendeteksi personel dengan tingkat kepercayaan {alert.confidence:.0%}.",
        "recommendation": "Lakukan briefing keselamatan ulang bagi personel di area tersebut dan pastikan gerbang zona terkunci saat tidak diawasi.",
        "status": "Generated by SIEWS+ LLM Engine"
    }
    return report

@app.post("/ai/schedule")
def automated_scheduling():
    """
    Fitur: Agentic AI (Manajemen Penjadwalan Otomatis).
    Mengatur jadwal patroli berdasarkan frekuensi pelanggaran zona.
    """
    # Logika Agentic AI: Menganalisis data historis untuk membuat jadwal
    # (Simulasi scheduling task)
    return {
        "status": "success",
        "message": "Jadwal patroli otomatis telah diperbarui berdasarkan kepadatan insiden.",
        "next_patrol": (datetime.now() + timedelta(hours=2)).isoformat(),
        "agent": "SIEWS+ Agentic Scheduler"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
