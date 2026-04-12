"""
SIEWS+ 5.0 YOLOv8 Detector
Wrapper for YOLOv8n model: load, inference, return bounding boxes.
"""
from ultralytics import YOLO
from typing import List, Tuple
import numpy as np


class PersonDetector:
    """YOLOv8 person detector wrapper."""

    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.5):
        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame: np.ndarray) -> List[dict]:
        """
        Run YOLO inference on a frame.
        Returns list of detections:
        [{ "bbox": [x1, y1, x2, y2], "confidence": float, "bottom_center": [cx, cy] }]
        All coordinates are in pixel values.
        """
        results = self.model(frame, verbose=False, conf=self.confidence)
        detections = []

        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                cls_id = int(box.cls[0])
                if cls_id != 0:  # 0 = person in COCO
                    continue

                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                # Bottom-center point (for zone checking)
                cx = (x1 + x2) / 2
                cy = y2

                detections.append({
                    "bbox": [x1, y1, x2, y2],
                    "confidence": conf,
                    "bottom_center": [cx, cy],
                })

        return detections
