"""
SIEWS+ 5.0 — FastAPI Application Entry Point
CORS, router mounting, static files, WebSocket, and all API endpoints.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, init_db
from models import Zone, Alert, ShutdownLog, Setting
from stream import stream_manager
from notifier import send_test_message
from shutdown import trigger_relay, log_shutdown
from config import STATIC_DIR

# ─── App Setup ────────────────────────────────────────────────
app = FastAPI(
    title="SIEWS+ 5.0 API",
    description="AI-Based Human Presence Detection for Intelligent Safety Shutdown",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (snapshots)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup():
    init_db()
    print("🚀 SIEWS+ 5.0 Backend started")


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
    return {
        "id": new_zone.id,
        "name": new_zone.name,
        "vertices": zone.vertices,
        "color": new_zone.color,
        "active": new_zone.active,
        "risk_level": new_zone.risk_level,
        "created_at": new_zone.created_at.isoformat() if new_zone.created_at else None,
    }


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
    return {
        "id": zone.id,
        "name": zone.name,
        "vertices": json.loads(zone.vertices_json),
        "color": zone.color,
        "active": zone.active,
        "risk_level": zone.risk_level,
    }


@app.delete("/polygons/{zone_id}")
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    """Delete a restricted zone."""
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    db.delete(zone)
    db.commit()
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
    query = db.query(Alert).join(Zone)

    if zone_id is not None:
        query = query.filter(Alert.zone_id == zone_id)
    if risk_level is not None:
        query = query.filter(Zone.risk_level == risk_level)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)

    total = query.count()
    alerts = query.order_by(Alert.timestamp.desc()).offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "alerts": [
            {
                "id": a.id,
                "zone_id": a.zone_id,
                "zone_name": a.zone.name if a.zone else "Unknown",
                "risk_level": a.zone.risk_level if a.zone else "unknown",
                "confidence": a.confidence,
                "snapshot_path": a.snapshot_path,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None,
                "shutdown_triggered": a.shutdown_triggered,
                "resolved": a.resolved,
            }
            for a in alerts
        ],
    }


@app.post("/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    """Mark an incident as resolved."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.resolved = True
    db.commit()
    return {"status": "resolved", "id": alert_id}


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

    return {
        "total_zones": total_zones,
        "active_zones": active_zones,
        "total_alerts": total_alerts,
        "today_alerts": today_alerts,
        "unresolved_alerts": unresolved,
        "total_shutdowns": total_shutdowns,
        "camera_status": "online" if stream_manager.cap and stream_manager.cap.isOpened() else "offline",
    }
