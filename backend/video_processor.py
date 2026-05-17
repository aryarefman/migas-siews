"""
SIEWS+ 5.0 — Async Video Upload Processor
Processes uploaded video files frame-by-frame using the multi-stage pipeline.
Results are stored in VideoJob table and retrievable via REST API.
Generates alerts for detected violations (PPE, zone, fire/smoke, etc.)
"""
import cv2
import json
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from detector import MultiStagePipeline
from database import SessionLocal
from models import VideoJob, Alert, Zone, Setting
from violation_checker import ViolationChecker

UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "uploads"
)
os.makedirs(UPLOADS_DIR, exist_ok=True)

SNAPSHOT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "snapshots"
)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# Process every Nth frame to speed up video analysis (1 = all frames, 5 = skip 4/5 frames)
VIDEO_PROCESS_INTERVAL = 1  # Changed to 1 for full video output


class VideoProcessor:
    """Singleton processor that handles one video job at a time asynchronously."""

    def __init__(self):
        self._pipeline: Optional[MultiStagePipeline] = None
        self._max_retries = 3
        self._retry_delay = 5.0  # seconds
        self._violation_checker = ViolationChecker(cooldown_seconds=5)

    def _get_pipeline(self) -> MultiStagePipeline:
        if self._pipeline is None:
            self._pipeline = MultiStagePipeline(confidence=0.25, ppe_confidence=0.30)
        return self._pipeline

    async def _generate_alerts(self, db, frame, result, zones_data, frame_width, frame_height, timestamp_sec, job_id):
        """Generate alerts for violations found in a video frame."""
        persons = result["persons"]
        hazards = result.get("env", [])
        road = result.get("road", [])

        violations = self._violation_checker.check_all_violations(
            persons=persons,
            hazards=hazards,
            zones=zones_data,
            frame_width=frame_width,
            frame_height=frame_height,
            road_detections=road,
        )

        if not violations:
            return

        # Broadcast alerts via WebSocket
        from stream import stream_manager

        for violation in violations:
            if not self._violation_checker.should_alert(violation.zone_id, violation.violation_type):
                continue

            now_utc = datetime.now(timezone.utc)
            timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"video_{job_id}_{timestamp_str}_{violation.zone_id}.jpg"
            snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_filename)
            cv2.imwrite(snapshot_path, frame)

            try:
                alert = Alert(
                    zone_id=violation.zone_id,
                    confidence=violation.confidence,
                    snapshot_path=f"static/snapshots/{snapshot_filename}",
                    timestamp=now_utc,
                    shutdown_triggered=False,
                    resolved=False,
                    violation_type=violation.violation_type,
                    person_name=violation.person_name,
                    uniform_code=violation.uniform_code,
                    ppe_detail=json.dumps(violation.ppe_detail) if violation.ppe_detail else None,
                )
                db.add(alert)
                db.commit()
                db.refresh(alert)

                # Push to WebSocket clients
                ws_event = {
                    "type": "alert",
                    "alert_id": alert.id,
                    "zone_name": violation.zone_name,
                    "zone_id": violation.zone_id,
                    "risk_level": violation.risk_level,
                    "timestamp": now_utc.isoformat(),
                    "confidence": violation.confidence,
                    "snapshot_url": f"/static/snapshots/{snapshot_filename}",
                    "shutdown_triggered": False,
                    "person_name": violation.person_name,
                    "uniform_code": violation.uniform_code,
                    "violation_type": violation.violation_type,
                    "ppe_detail": violation.ppe_detail,
                    "source": "video",
                }
                await stream_manager._broadcast_to_ws(ws_event)

            except Exception as e:
                print(f"[VIDEO-ALERT] Error creating alert: {e}")
                db.rollback()

    async def process_video(self, job_id: int):
        """
        Main async processing function. Runs in background after video upload.
        Updates VideoJob progress, writes results to result_json.
        """
        db = SessionLocal()
        try:
            job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
            if not job:
                return

            job.status = "processing"
            db.commit()

            cap = None
            last_error = None
            for attempt in range(self._max_retries):
                if cap is not None:
                    cap.release()
                cap = cv2.VideoCapture(job.file_path)
                if cap.isOpened():
                    last_error = None
                    break
                last_error = f"Attempt {attempt + 1}/{self._max_retries}: Cannot open video file"
                print(f"[VIDEO] {last_error}")
                if attempt < self._max_retries - 1:
                    import time as time_module
                    time_module.sleep(self._retry_delay)

            if cap is None or not cap.isOpened():
                job.status = "failed"
                job.error_message = last_error or "Cannot open video file"
                db.commit()
                return

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps is None or fps <= 0:
                fps = 25.0
                print(f"[VIDEO] Could not detect FPS, using default {fps}")
            job.total_frames = total_frames
            db.commit()

            pipeline = self._get_pipeline()
            frame_results = []
            frame_idx = 0
            processed = 0

            # Setup video writer for annotated output
            output_path = job.file_path.replace(".mp4", "_annotated.mp4").replace(".avi", "_annotated.avi")
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Try H264/avc1 first (best browser compat), fallback to others
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"[VIDEO] Output: {output_path}, Resolution: {width}x{height}, FPS: {fps}")

            out = None
            if output_path.endswith('.mp4'):
                # Try avc1/H264 first for best browser compatibility
                for codec in ['avc1', 'H264', 'XVID', 'mp4v']:
                    fourcc = cv2.VideoWriter_fourcc(*codec)
                    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                    if out.isOpened():
                        print(f"[VIDEO] Using codec: {codec}")
                        break
            else:
                for codec in ['XVID', 'MJPG', 'mp4v']:
                    fourcc = cv2.VideoWriter_fourcc(*codec)
                    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                    if out.isOpened():
                        print(f"[VIDEO] Using codec: {codec}")
                        break

            if out is None or not out.isOpened():
                raise Exception(f"Failed to open video writer for {output_path} with any codec")

            # Load active zones for violation checking
            active_zones = db.query(Zone).filter(Zone.active == True).all()
            zones_data = [
                {
                    "id": z.id,
                    "name": z.name,
                    "vertices": json.loads(z.vertices_json),
                    "color": z.color,
                    "risk_level": z.risk_level,
                }
                for z in active_zones
            ]

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_idx += 1

                # Only process every Nth frame
                if frame_idx % VIDEO_PROCESS_INTERVAL != 0:
                    continue

                # Yield control to event loop every 10 processed frames
                if processed % 10 == 0:
                    await asyncio.sleep(0)

                result = pipeline.run(frame)
                timestamp_sec = frame_idx / fps

                # ── Check zone violations for this frame ──────────────
                persons = result["persons"]
                hazards = result.get("env", [])
                road_damage = result.get("road", [])
                safety_cones = result.get("safety_cones", [])
                vehicles = result.get("vehicles", [])

                violations = self._violation_checker.check_all_violations(
                    persons=persons,
                    hazards=hazards,
                    zones=zones_data,
                    frame_width=width,
                    frame_height=height,
                    road_detections=road_damage,
                )
                violation_indices = self._violation_checker.get_violation_indices(persons, violations)

                # Also mark persons inside zones as violations
                from polygon import point_in_polygon
                for i, det in enumerate(persons):
                    if i in violation_indices:
                        continue
                    bbox = det["bbox"]
                    cx = ((bbox[0] + bbox[2]) / 2) / width
                    cy = ((bbox[1] + bbox[3]) / 2) / height
                    for z in zones_data:
                        verts = z.get("vertices", [])
                        if len(verts) >= 3 and point_in_polygon([cx, cy], verts):
                            violation_indices.add(i)
                            break

                # Get violated zone IDs for zone drawing
                violated_zone_ids = set()
                for v in violations:
                    if v.violation_type == "zone_violation":
                        violated_zone_ids.add(v.zone_id)

                # Annotate frame using the proper drawing module
                annotated = frame.copy()
                from drawing import (
                    draw_detections,
                    draw_zones,
                )
                draw_zones(annotated, zones_data, violated_zone_ids)
                draw_detections(annotated, persons, violation_indices, hazards, road_damage, safety_cones, vehicles)

                # Write annotated frame
                out.write(annotated)

                # Build compact frame result (match photo analysis format)
                frame_data = {
                    "frame": frame_idx,
                    "timestamp_sec": round(timestamp_sec, 2),
                    "persons": [
                        {
                            "bbox": p["bbox"],
                            "confidence": round(p["confidence"], 3),
                            "ppe_violations": p.get("ppe_violations", []),
                            "ppe": p.get("ppe_result", {}),
                        }
                        for p in persons
                    ],
                    "env": [
                        {
                            "class_name": d.get("class_name", d.get("label", "")),
                            "confidence": round(d["confidence"], 3),
                            "bbox": d["bbox"],
                            "category": d.get("category"),
                        }
                        for d in hazards
                    ],
                    "road": [
                        {
                            "class_name": r.get("class_name", ""),
                            "confidence": round(r["confidence"], 3),
                            "bbox": r["bbox"],
                        }
                        for r in road_damage
                    ],
                    "safety_cones": [
                        {
                            "class_name": s.get("class_name", ""),
                            "confidence": round(s["confidence"], 3),
                            "bbox": s["bbox"],
                        }
                        for s in safety_cones
                    ],
                    "vehicles": [
                        {
                            "class_name": v.get("class_name", v.get("label", "")),
                            "confidence": round(v["confidence"], 3),
                            "bbox": v["bbox"],
                            "class_id": v.get("class_id"),
                        }
                        for v in vehicles
                    ],
                    "has_violation": bool(violations),
                }
                frame_results.append(frame_data)
                processed += 1

                # ── Generate alerts for violations ──────────────────────
                if frame_data["has_violation"]:
                    await self._generate_alerts(
                        db, frame, result, zones_data, width, height,
                        timestamp_sec, job_id
                    )

                # Update progress in DB every 50 processed frames
                if processed % 50 == 0:
                    progress = min(99, int((frame_idx / max(total_frames, 1)) * 100))
                    db.query(VideoJob).filter(VideoJob.id == job_id).update({
                        "progress": progress,
                        "processed_frames": processed,
                    })
                    db.commit()

            cap.release()
            if out is not None:
                out.release()

            # Convert to browser-compatible H264 MP4 using FFmpeg
            final_output = output_path.replace("_annotated.", "_final.")
            if not final_output.endswith(".mp4"):
                final_output = final_output.rsplit(".", 1)[0] + ".mp4"

            import subprocess
            import shutil as _shutil
            
            # Find ffmpeg binary — prefer system ffmpeg, fallback to imageio-ffmpeg
            ffmpeg_path = _shutil.which("ffmpeg")
            if not ffmpeg_path:
                try:
                    import imageio_ffmpeg
                    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
                except ImportError:
                    ffmpeg_path = None

            if ffmpeg_path:
                try:
                    ffmpeg_cmd = [
                        ffmpeg_path, "-y", "-i", output_path,
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart",
                        final_output
                    ]
                    print(f"[VIDEO] Converting with: {ffmpeg_path}")
                    result_ffmpeg = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=600)
                    if result_ffmpeg.returncode == 0 and os.path.exists(final_output):
                        os.remove(output_path)
                        os.rename(final_output, output_path)
                        print(f"[VIDEO] Converted to H264: {output_path}")
                    else:
                        stderr_msg = result_ffmpeg.stderr.decode()[:300] if result_ffmpeg.stderr else "unknown"
                        print(f"[VIDEO] FFmpeg conversion failed: {stderr_msg}")
                except Exception as e:
                    print(f"[VIDEO] FFmpeg error: {e}")
            else:
                print("[VIDEO] WARNING: No ffmpeg found. Video may not play in browser.")

            # Verify output file exists and has content
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                print(f"[VIDEO] Annotated video created: {output_path} ({file_size} bytes)")
                if file_size < 1000:
                    print(f"[VIDEO] WARNING: Output file is very small ({file_size} bytes), may be corrupted")
            else:
                print(f"[VIDEO] ERROR: Output file not found: {output_path}")

            # Normalize path for cross-platform compatibility (store as forward slashes)
            normalized_output_path = output_path.replace("\\", "/")

            # Finalize job
            db.query(VideoJob).filter(VideoJob.id == job_id).update({
                "status": "done",
                "progress": 100,
                "processed_frames": processed,
                "result_json": json.dumps(frame_results),
                "annotated_video_path": normalized_output_path,
                "completed_at": datetime.now(timezone.utc),
            })
            db.commit()

        except Exception as e:
            db.query(VideoJob).filter(VideoJob.id == job_id).update({
                "status": "failed",
                "error_message": str(e),
            })
            db.commit()
        finally:
            db.close()


video_processor = VideoProcessor()
