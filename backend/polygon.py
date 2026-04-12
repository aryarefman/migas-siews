"""
SIEWS+ 5.0 Polygon Utilities
Ray-casting point-in-polygon algorithm and polygon CRUD helpers.
"""
import json
from typing import List, Tuple


def point_in_polygon(point: Tuple[float, float], polygon: List[List[float]]) -> bool:
    """
    Ray-casting algorithm to determine if a point is inside a polygon.
    All coordinates are normalized (0.0 - 1.0).
    """
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i

    return inside


def parse_vertices(vertices_json: str) -> List[List[float]]:
    """Parse vertices JSON string into list of [x, y] pairs."""
    return json.loads(vertices_json)


def compute_centroid(vertices: List[List[float]]) -> Tuple[float, float]:
    """Compute centroid of a polygon."""
    n = len(vertices)
    if n == 0:
        return (0.0, 0.0)
    cx = sum(v[0] for v in vertices) / n
    cy = sum(v[1] for v in vertices) / n
    return (cx, cy)
