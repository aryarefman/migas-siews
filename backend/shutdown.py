"""
SIEWS+ 5.0 Shutdown Signal Handler
Log shutdown events and simulate relay trigger.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import ShutdownLog


def trigger_relay(zone_name: str):
    """
    Placeholder for real GPIO/PLC integration.
    In production, this would trigger a physical relay output.
    """
    print(f"🔴 SHUTDOWN SIGNAL SENT TO ZONE: {zone_name}")
    print(f"   Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"   [In production: GPIO/relay output would be triggered here]")


def log_shutdown(db: Session, zone_id: int, trigger_source: str = "auto") -> ShutdownLog:
    """
    Log a shutdown event to the database.
    trigger_source: "auto" (from detection) or "manual" (from dashboard)
    """
    log = ShutdownLog(
        zone_id=zone_id,
        trigger_source=trigger_source,
        triggered_at=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log
