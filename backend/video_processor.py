"""
SIEWS+ 5.0 — Async Video Upload Processor
Processes uploaded video files frame-by-frame using the multi-stage pipeline.
Results are stored in VideoJob table and retrievable via REST API.
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
from models import VideoJob

UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "static", "uploads"
)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Process every Nth frame to speed up video analysis (1 = all frames, 5 = skip 4/5 frames)
VIDEO_PROCESS_INTERVAL = 1  # Changed to 1 for full video output


class VideoProcessor:
    """Singleton processor that handles one video job at a time asynchronously."""

    def __init__(self):
        self._pipeline: Optional[MultiStagePipeline] = None

    def _get_pipeline(self) -> MultiStagePipeline:
        if self._pipeline is None:
            self._pipeline = MultiStagePipeline(confidence=0.25, ppe_confidence=0.30)
        return self._pipeline

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

            cap = cv2.VideoCapture(job.file_path)
            if not cap.isOpened():
                job.status = "failed"
                job.error_message = "Cannot open video file"
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

                # Annotate frame with bounding boxes
                annotated = frame.copy()
                violation_indices = {i for i, p in enumerate(result["persons"]) if p.get("ppe_violations")}

                # Draw persons
                for i, p in enumerate(result["persons"]):
                    bbox = p["bbox"]
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    color = (0, 0, 255) if i in violation_indices else (0, 255, 0)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    label = f"Person {p['confidence']:.0%}"
                    if i in violation_indices:
                        label = f"BAHAYA {p['confidence']:.0%}"
                    cv2.putText(annotated, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                # Draw env hazards
                for d in result["env"]:
                    bbox = d["bbox"]
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                    label = f"DANGER: {d.get('class_name', 'Hazard')} {d['confidence']:.0%}"
                    cv2.putText(annotated, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                # Draw road damage
                for r in result.get("road", []):
                    bbox = r["bbox"]
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    label = f"ROAD: {r.get('class_name', 'Damage')} {r['confidence']:.0%}"
                    cv2.putText(annotated, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

                # Draw safety cones
                for s in result.get("safety_cones", []):
                    bbox = s["bbox"]
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"Safety-cone {s['confidence']:.0%}"
                    cv2.putText(annotated, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

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
                        for p in result["persons"]
                    ],
                    "env": [
                        {
                            "class_name": d.get("class_name", d.get("label", "")),
                            "confidence": round(d["confidence"], 3),
                            "bbox": d["bbox"],
                        }
                        for d in result["env"]
                    ],
                    "road": [
                        {
                            "class_name": r.get("class_name", ""),
                            "confidence": round(r["confidence"], 3),
                            "bbox": r["bbox"],
                        }
                        for r in result.get("road", [])
                    ],
                    "safety_cones": [
                        {
                            "class_name": s.get("class_name", ""),
                            "confidence": round(s["confidence"], 3),
                            "bbox": s["bbox"],
                        }
                        for s in result.get("safety_cones", [])
                    ],
                    "has_violation": (
                        any(p.get("ppe_violations") for p in result["persons"])
                        or bool(result["env"])
                        or bool(result.get("road"))
                    ),
                }
                frame_results.append(frame_data)
                processed += 1

                # Update progress in DB every 50 processed frames
                if processed % 50 == 0:
                    progress = min(99, int((frame_idx / max(total_frames, 1)) * 100))
                    db.query(VideoJob).filter(VideoJob.id == job_id).update({
                        "progress": progress,
                        "processed_frames": processed,
                    })
                    db.commit()

            cap.release()
            out.release()

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
