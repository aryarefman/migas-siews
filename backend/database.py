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


def init_db():
    """Create all tables and seed default settings."""
    from models import Zone, Alert, ShutdownLog, Setting
    Base.metadata.create_all(bind=engine)

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
