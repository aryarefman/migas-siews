"""
SIEWS+ 5.0 — Golang Polygon Client
HTTP client that communicates with the Go polygon microservice.
Falls back to Python implementation if Go service is unavailable.
"""
import httpx
from typing import List, Optional
from polygon import point_in_polygon


GO_POLYGON_URL = "http://localhost:8002"
_go_available: Optional[bool] = None


async def check_go_health() -> bool:
    """Check if the Go polygon service is running."""
    global _go_available
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{GO_POLYGON_URL}/health")
            _go_available = resp.status_code == 200
            if _go_available:
                print("[POLYGON-GO] ✓ Go microservice connected")
            return _go_available
    except Exception:
        _go_available = False
        return False


def check_go_health_sync() -> bool:
    """Synchronous health check."""
    global _go_available
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{GO_POLYGON_URL}/health")
            _go_available = resp.status_code == 200
            return _go_available
    except Exception:
        _go_available = False
        return False


def batch_check_violations_sync(
    persons: List[dict],
    zones: List[dict],
    frame_w: int,
    frame_h: int,
) -> List[dict]:
    """
    Check all persons against all zones using Go microservice.
    Falls back to Python if Go service is unavailable.

    Args:
        persons: List of dicts with "bottom_center" [x, y] and "confidence"
        zones:   List of zone dicts with "id", "name", "vertices", "risk_level"
        frame_w: Frame width in pixels
        frame_h: Frame height in pixels

    Returns:
        List of violation dicts: [{person_index, zone_id, zone_name, risk_level, confidence}]
    """
    global _go_available

    # Try Go service
    if _go_available is None:
        check_go_health_sync()

    if _go_available:
        try:
                payload = {
                    "persons": [
                        {
                            "index": i,
                            "center": [p["center"][0] / frame_w, p["center"][1] / frame_h],
                            "confidence": p.get("confidence", 0.0),
                        }
                        for i, p in enumerate(persons)
                    ],
                    "zones": [
                        {
                            "id": z["id"],
                            "name": z["name"],
                            "vertices": z["vertices"],
                            "risk_level": z.get("risk_level", "high"),
                        }
                        for z in zones
                    ]
                }
                with httpx.Client(timeout=1.0) as client:
                    resp = client.post(f"{GO_POLYGON_URL}/batch-check", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("violations", [])
        except Exception as e:
            print(f"[POLYGON-GO] Fallback to Python: {e}")
            _go_available = False

    # Python fallback
    return _python_batch_check(persons, zones, frame_w, frame_h)


def _python_batch_check(
    persons: List[dict],
    zones: List[dict],
    frame_w: int,
    frame_h: int,
) -> List[dict]:
    """Fallback: Python-based point-in-polygon check."""
    violations = []
    for i, person in enumerate(persons):
        c = person.get("center", [0, 0])
        px = c[0] / frame_w if c[0] > 1.0 else c[0]
        py = c[1] / frame_h if c[1] > 1.0 else c[1]

        for zone in zones:
            vertices = zone.get("vertices", [])
            if len(vertices) < 3:
                continue
            if point_in_polygon((px, py), vertices):
                violations.append({
                    "person_index": i,
                    "zone_id": zone["id"],
                    "zone_name": zone["name"],
                    "risk_level": zone.get("risk_level", "high"),
                    "confidence": person.get("confidence", 0.0),
                })

    return violations
