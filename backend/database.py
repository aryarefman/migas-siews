"""
SIEWS+ 5.0 Database Setup
SQLAlchemy engine, session, and base configuration.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency: yield a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_alert_columns():
    """Add new columns to alerts table if they don't exist (SQLite safe migration)."""
    migrations = [
        "ALTER TABLE alerts ADD COLUMN violation_type VARCHAR(30) DEFAULT 'restricted_area'",
        "ALTER TABLE alerts ADD COLUMN false_positive BOOLEAN DEFAULT 0",
        "ALTER TABLE alerts ADD COLUMN ppe_detail TEXT",
        "ALTER TABLE alerts ADD COLUMN persons_count INTEGER DEFAULT 0",
    ]
    with engine.connect() as conn:
        for stmt in migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(stmt))
                conn.commit()
            except Exception:
                pass  # Column already exists


def init_db():
    """Create all tables and seed default settings."""
    from models import Zone, Alert, ShutdownLog, Setting, DetectionLog, VideoJob  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate_alert_columns()

    db = SessionLocal()
    try:
        # Seed default settings if not present
        defaults = {
            "camera_source": "0",
            "facility_name": "Offshore Platform A",
            "confidence_threshold": "0.5",
            "detection_interval": "3",
            "notify_cooldown": "300",
            "fonnte_token": "",
            "recipients": "",
        }
        for key, value in defaults.items():
            existing = db.query(Setting).filter(Setting.key == key).first()
            if not existing:
                db.add(Setting(key=key, value=value))
        db.commit()
    finally:
        db.close()
