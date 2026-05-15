from database import SessionLocal
from models import Zone
import json

db = SessionLocal()
try:
    zones = db.query(Zone).all()
    print(f"Total zones in DB: {len(zones)}")
    for z in zones:
        print(f"ID: {z.id}, Name: {z.name}, Active: {z.active}, Risk: {z.risk_level}")
finally:
    db.close()
