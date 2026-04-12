"""
SIEWS+ 5.0 SQLAlchemy ORM Models
Zones, Alerts, ShutdownLog, and Settings tables.
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
    risk_level = Column(String(10), default="high")  # "low" or "high"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    alerts = relationship("Alert", back_populates="zone")
    shutdown_logs = relationship("ShutdownLog", back_populates="zone")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    zone_id = Column(Integer, ForeignKey("zones.id"), nullable=False)
    confidence = Column(Float, nullable=False)
    snapshot_path = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    shutdown_triggered = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)

    zone = relationship("Zone", back_populates="alerts")


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
