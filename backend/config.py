"""
SIEWS+ 5.0 Configuration
Load all environment variables with sensible defaults.
"""
import os
from dotenv import load_dotenv

load_dotenv()

CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "0")
FACILITY_NAME = os.getenv("FACILITY_NAME", "Offshore Platform A")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.3"))
DETECTION_INTERVAL = int(os.getenv("DETECTION_INTERVAL", "3"))
NOTIFY_COOLDOWN = int(os.getenv("NOTIFY_COOLDOWN", "10"))
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "")
DEFAULT_RECIPIENTS = os.getenv("DEFAULT_RECIPIENTS", "")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./siews.db")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SNAPSHOT_DIR = os.path.join(STATIC_DIR, "snapshots")

# Ensure directories exist
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
