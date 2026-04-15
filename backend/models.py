"""
SIEWS+ 5.0 SQLAlchemy ORM Models
Zones, Alerts, ShutdownLog, Settings, DetectionLog, VideoJob tables.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class Zone(Base):
    __tablename__ = "zones"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    vertices_json = Column(Text, nullable=False)  # JSON: list of [x, y] normalized floats
    color = Column(String(7), default="#FF0000")   # hex color
    active = Column(Boolean, default=True)
    risk_level = Column(String(10), default="high")  # "low" | "high"

    # Zone type — drives alert behaviour downstream
    # "restricted"  : no entry allowed, immediate alert
    # "monitoring"  : entry allowed, alert after dwell threshold
    # "caution"     : entry allowed, soft warning only
    zone_type = Column(String(20), default="restricted")

    # Seconds a person may stay before a dwell-time warning fires (0 = disabled)
    dwell_threshold_sec = Column(Integer, default=10)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    alerts = relationship("Alert", back_populates="zone")
    shutdown_logs = relationship("ShutdownLog", back_populates="zone")
    occupancy_logs = relationship("ZoneOccupancy", back_populates="zone")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    confidence = Column(Float, nullable=False)
    snapshot_path = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    shutdown_triggered = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)

    # Multi-stage pipeline additions
    violation_type = Column(String(30), default="restricted_area")
    # "restricted_area" | "missing_ppe" | "no_harness" | "fire_smoke" | "multiple"
    false_positive = Column(Boolean, default=False)
    ppe_detail = Column(Text, nullable=True)  # JSON: {helmet: bool, vest: bool, harness: bool, ...}

    zone = relationship("Zone", back_populates="alerts")
    detection_logs = relationship("DetectionLog", back_populates="alert")


class DetectionLog(Base):
    """Per-object crop logging for each alert — used for false positive review."""
    __tablename__ = "detection_log"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    class_name = Column(String(50), nullable=False)   # e.g. "no_helmet", "fire"
    confidence = Column(Float, nullable=False)
    crop_path = Column(String(255), nullable=True)    # path to cropped object image
    frame_number = Column(Integer, nullable=True)
    bbox_json = Column(Text, nullable=True)           # JSON: [x1, y1, x2, y2] pixel coords
    is_false_positive = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    alert = relationship("Alert", back_populates="detection_logs")


class ShutdownLog(Base):
    __tablename__ = "shutdown_log"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    trigger_source = Column(String(20), default="auto")  # "auto" or "manual"
    triggered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    zone = relationship("Zone", back_populates="shutdown_logs")


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, nullable=False)
    value = Column(Text, default="")


class VideoJob(Base):
    """Tracks async video upload processing jobs."""
    __tablename__ = "video_jobs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False)
    status = Column(String(20), default="pending")
    # "pending" | "processing" | "done" | "failed"
    progress = Column(Integer, default=0)          # 0–100 percent
    total_frames = Column(Integer, default=0)
    processed_frames = Column(Integer, default=0)
    result_json = Column(Text, nullable=True)      # JSON: list of frame detections
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)


class ZoneOccupancy(Base):
    """
    Persistent audit log for zone dwell-time events.
    Each row records one person entering and (optionally) exiting a zone.
    Written when a person exits or when the stream stops.

    track_id   — stable short UUID from PersonZoneTracker
    zone_id    — FK to Zone
    entry_time — UTC timestamp of zone entry
    exit_time  — UTC timestamp of zone exit (NULL if still inside)
    dwell_sec  — total seconds spent in zone (updated on exit)
    alert_level— "none" | "warning" | "critical" — highest level reached
    """
    __tablename__ = "zone_occupancy"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    track_id = Column(String(16), nullable=False, index=True)   # 8-char hex UUID
    entry_time = Column(DateTime, nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    exit_time = Column(DateTime, nullable=True)
    dwell_sec = Column(Float, default=0.0)
    alert_level = Column(String(10), default="none")  # "none"|"warning"|"critical"

    zone = relationship("Zone", back_populates="occupancy_logs")
