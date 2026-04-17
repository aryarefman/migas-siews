from database import SessionLocal
from models import Zone

db = SessionLocal()
try:
    system_zone = db.query(Zone).filter(Zone.id == 999).first()
    if not system_zone:
        new_zone = Zone(
            id=999,
            name="Restricted Area (Auto Detection)",
            vertices_json="[]",
            color="#FF0000",
            active=True,
            risk_level="high"
        )
        db.add(new_zone)
        db.commit()
        print("Created System Zone (ID: 999)")
    else:
        print("System Zone already exists.")
finally:
    db.close()
