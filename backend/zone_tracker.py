"""
SIEWS+ 5.0 — Zone Tracker
Centroid-based person identity tracking across frames + time-in-zone (dwell time) engine.

Design goals:
  - Stable person IDs across frames (centroid proximity matching)
  - Per-person per-zone entry/exit timestamps
  - Threshold-triggered dwell events (warning / critical)
  - Extensible: new event types can be added without touching stream.py

Usage:
    tracker = PersonZoneTracker()

    # Each detection cycle:
    events = tracker.update(persons, active_zones, frame_w, frame_h)
    for ev in events:
        # ev["type"]       : "zone_entry" | "dwell_warning" | "dwell_critical" | "zone_exit"
        # ev["track_id"]   : stable person ID (short UUID)
        # ev["zone_id"]    : int
        # ev["zone_name"]  : str
        # ev["dwell_sec"]  : float — how long in zone so far
        # ev["bbox"]       : [x1, y1, x2, y2] pixel coords
        ...

    # Query current occupancy (for API):
    occupancy = tracker.get_occupancy()
    # [ {"track_id", "zone_id", "zone_name", "entry_time_iso", "dwell_sec"}, ... ]
"""
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple


# ─── Tunable Constants ──────────────────────────────────────────────────────
# Max normalized centroid distance to consider two detections the same person.
# 0.12 ≈ 12% of frame width/height — reasonable for walking speed at 3-5fps.
MATCH_DIST_THRESHOLD = 0.12

# Seconds without any detection before a track is considered "left frame"
TRACK_TIMEOUT_SEC = 3.0

# Dwell thresholds (seconds inside a zone before an event fires)
DWELL_WARNING_SEC  = 10   # first warning
DWELL_CRITICAL_SEC = 30   # escalation

# Minimum seconds between repeated dwell alerts for the same (track, zone, level)
DWELL_ALERT_COOLDOWN_SEC = 60


# ─── Data Structures ────────────────────────────────────────────────────────

@dataclass
class PersonTrack:
    """Represents a tracked person with stable identity across frames."""
    track_id: str                            # short UUID
    centroid: Tuple[float, float]            # normalized (cx, cy)
    bbox: List[int]                          # pixel [x1, y1, x2, y2]
    last_seen: float = field(default_factory=time.monotonic)

    # {zone_id: entry_monotonic_time}
    zone_entry: Dict[int, float] = field(default_factory=dict)

    # {zone_id: set of already-fired thresholds ("warning", "critical")}
    dwell_alerted: Dict[int, Set[str]] = field(default_factory=dict)

    # {zone_id: last dwell-alert monotonic time}
    dwell_last_alert: Dict[int, float] = field(default_factory=dict)

    @property
    def is_stale(self) -> bool:
        return (time.monotonic() - self.last_seen) > TRACK_TIMEOUT_SEC


# ─── Tracker ────────────────────────────────────────────────────────────────

class PersonZoneTracker:
    """
    Maintains person tracks across frames and reports zone dwell events.

    Extensibility note:
        - Override `_custom_events()` to add new event types without forking.
        - Add new threshold tuples to `DWELL_THRESHOLDS` to add levels.
    """

    DWELL_THRESHOLDS = [
        (DWELL_WARNING_SEC,  "dwell_warning"),
        (DWELL_CRITICAL_SEC, "dwell_critical"),
    ]

    def __init__(self):
        self._tracks: Dict[str, PersonTrack] = {}  # track_id → PersonTrack

    # ── Public API ─────────────────────────────────────────────────────────

    def update(
        self,
        persons: List[dict],
        active_zones: List[dict],
        frame_w: int,
        frame_h: int,
    ) -> List[dict]:
        """
        Call once per detection cycle.

        Args:
            persons     : list of dicts from Stage 1 detection
                          must have keys: "bbox" [x1,y1,x2,y2], "bottom_center" [cx,cy]
            active_zones: list of zone dicts — must have "id", "name", "vertices"
            frame_w/h   : pixel dimensions of current frame

        Returns:
            List of event dicts (may be empty).
        """
        now = time.monotonic()
        events: List[dict] = []

        # Step 1: match incoming detections to existing tracks
        matched_ids: Set[str] = set()
        new_centroids = [
            self._to_norm_centroid(p["bbox"], frame_w, frame_h)
            for p in persons
        ]

        unmatched_detections = list(range(len(persons)))

        for track in list(self._tracks.values()):
            best_idx, best_dist = self._find_closest(track.centroid, new_centroids, unmatched_detections)
            if best_idx is not None and best_dist < MATCH_DIST_THRESHOLD:
                # Update existing track
                track.centroid = new_centroids[best_idx]
                track.bbox = persons[best_idx]["bbox"]
                track.last_seen = now
                matched_ids.add(track.track_id)
                unmatched_detections.remove(best_idx)

        # Step 2: create new tracks for unmatched detections
        for idx in unmatched_detections:
            new_id = uuid.uuid4().hex[:8]
            self._tracks[new_id] = PersonTrack(
                track_id=new_id,
                centroid=new_centroids[idx],
                bbox=persons[idx]["bbox"],
                last_seen=now,
            )

        # Step 3: remove stale tracks + emit zone_exit events
        for tid in list(self._tracks.keys()):
            track = self._tracks[tid]
            if track.is_stale:
                for zid in list(track.zone_entry.keys()):
                    events.append(self._make_exit_event(track, zid, active_zones))
                del self._tracks[tid]

        # Step 4: check zone membership for each alive track
        zone_lookup = {z["id"]: z for z in active_zones}

        for track in self._tracks.values():
            if track.track_id not in matched_ids and track.track_id not in [
                self._tracks[k].track_id for k in self._tracks
                if not self._tracks[k].is_stale
            ]:
                continue  # stale

            cx, cy = track.centroid
            active_zone_ids: Set[int] = set()

            for zone in active_zones:
                zid = zone["id"]
                inside = _point_in_polygon_norm((cx, cy), zone["vertices"])

                if inside:
                    active_zone_ids.add(zid)
                    if zid not in track.zone_entry:
                        # First frame inside — record entry
                        track.zone_entry[zid] = now
                        events.append({
                            "type": "zone_entry",
                            "track_id": track.track_id,
                            "zone_id": zid,
                            "zone_name": zone["name"],
                            "dwell_sec": 0.0,
                            "bbox": track.bbox,
                        })
                    else:
                        # Already inside — check dwell thresholds
                        dwell = now - track.zone_entry[zid]
                        alerted = track.dwell_alerted.setdefault(zid, set())
                        last_alerted = track.dwell_last_alert.get(zid, 0.0)

                        for threshold_sec, level in self.DWELL_THRESHOLDS:
                            if (
                                dwell >= threshold_sec
                                and level not in alerted
                                or (
                                    level in alerted
                                    and now - last_alerted >= DWELL_ALERT_COOLDOWN_SEC
                                )
                            ):
                                alerted.add(level)
                                track.dwell_last_alert[zid] = now
                                events.append({
                                    "type": level,
                                    "track_id": track.track_id,
                                    "zone_id": zid,
                                    "zone_name": zone["name"],
                                    "dwell_sec": round(dwell, 1),
                                    "bbox": track.bbox,
                                })
                                break  # only emit highest level per cycle

                else:
                    # Was inside but no longer — exit
                    if zid in track.zone_entry:
                        events.append(self._make_exit_event(track, zid, active_zones))
                        track.zone_entry.pop(zid, None)
                        track.dwell_alerted.pop(zid, None)
                        track.dwell_last_alert.pop(zid, None)

            # Clean up zones the person is no longer near
            for zid in list(track.zone_entry.keys()):
                if zid not in active_zone_ids:
                    events.append(self._make_exit_event(track, zid, active_zones))
                    track.zone_entry.pop(zid, None)
                    track.dwell_alerted.pop(zid, None)
                    track.dwell_last_alert.pop(zid, None)

        # Step 5: allow subclasses to inject extra events
        events.extend(self._custom_events(self._tracks, active_zones))

        return events

    def get_occupancy(self) -> List[dict]:
        """Return current zone occupancy state (for API endpoint)."""
        now = time.monotonic()
        result = []
        for track in self._tracks.values():
            if track.is_stale:
                continue
            for zid, entry_mono in track.zone_entry.items():
                dwell = now - entry_mono
                result.append({
                    "track_id": track.track_id,
                    "zone_id": zid,
                    "dwell_sec": round(dwell, 1),
                    "bbox": track.bbox,
                    "entry_time_iso": datetime.now(timezone.utc).isoformat(),
                })
        return result

    def get_track_dwell(self, track_id: str, zone_id: int) -> float:
        """Returns seconds a specific track has been in a specific zone (0 if not)."""
        track = self._tracks.get(track_id)
        if track is None or zone_id not in track.zone_entry:
            return 0.0
        return time.monotonic() - track.zone_entry[zone_id]

    def reset(self):
        """Clear all tracks (e.g. when camera source changes)."""
        self._tracks.clear()

    # ── Extensibility hook ──────────────────────────────────────────────────

    def _custom_events(
        self,
        tracks: Dict[str, PersonTrack],
        zones: List[dict],
    ) -> List[dict]:
        """
        Override this method in a subclass to add new event types.

        Example:
            def _custom_events(self, tracks, zones):
                # Emit "crowd_warning" if >3 people in the same zone
                ...
        """
        return []

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _to_norm_centroid(bbox: List[int], fw: int, fh: int) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        cx = ((x1 + x2) / 2) / fw
        cy = ((y1 + y2) / 2) / fh
        return (cx, cy)

    @staticmethod
    def _find_closest(
        centroid: Tuple[float, float],
        candidates: List[Tuple[float, float]],
        indices: List[int],
    ):
        """Find closest candidate by Euclidean distance. Returns (idx, dist) or (None, inf)."""
        best_idx = None
        best_dist = float("inf")
        cx, cy = centroid
        for i in indices:
            dx = candidates[i][0] - cx
            dy = candidates[i][1] - cy
            d = (dx * dx + dy * dy) ** 0.5
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx, best_dist

    def _make_exit_event(self, track: PersonTrack, zone_id: int, zones: List[dict]) -> dict:
        zone_name = next((z["name"] for z in zones if z["id"] == zone_id), f"Zone {zone_id}")
        dwell = time.monotonic() - track.zone_entry.get(zone_id, time.monotonic())
        return {
            "type": "zone_exit",
            "track_id": track.track_id,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "dwell_sec": round(dwell, 1),
            "bbox": track.bbox,
        }


# ─── Polygon helper (local copy to avoid circular imports) ──────────────────

def _point_in_polygon_norm(
    point: Tuple[float, float],
    polygon: List[List[float]],
) -> bool:
    """Ray-casting point-in-polygon for normalized coordinates."""
    if len(polygon) < 3:
        return False
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
