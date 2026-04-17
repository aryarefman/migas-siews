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

# Process every Nth frame to speed up video analysis (skip similar frames)
VIDEO_PROCESS_INTERVAL = 5


class VideoProcessor:
    """Singleton processor that handles one video job at a time asynchronously."""

    def __init__(self):
        self._pipeline: Optional[MultiStagePipeline] = None

    def _get_pipeline(self) -> MultiStagePipeline:
        if self._pipeline is None:
            self._pipeline = MultiStagePipeline(confidence=0.45, ppe_confidence=0.35)
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
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            job.total_frames = total_frames
            db.commit()

            pipeline = self._get_pipeline()
            frame_results = []
            frame_idx = 0
            processed = 0

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

                # Build compact frame result
                frame_data = {
                    "frame": frame_idx,
                    "timestamp_sec": round(timestamp_sec, 2),
                    "persons": [
                        {
                            "bbox": p["bbox"],
                            "confidence": round(p["confidence"], 3),
                            "ppe": p.get("ppe_result", {}),
                        }
                        for p in result["persons"]
                    ],
                    "env": [
                        {
                            "label": d.get("label", "Hazard"),
                            "confidence": round(d["confidence"], 3),
                            "bbox": d["bbox"],
                        }
                        for d in result["env"]
                    ],
                    "has_violation": (
                        any(not p.get("ppe_result", {}).get("has_helmet") or not p.get("ppe_result", {}).get("has_vest") for p in result["persons"])
                        or bool(result["env"])
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

            # Finalize job
            db.query(VideoJob).filter(VideoJob.id == job_id).update({
                "status": "done",
                "progress": 100,
                "processed_frames": processed,
                "result_json": json.dumps(frame_results),
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
