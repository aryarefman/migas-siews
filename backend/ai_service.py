"""
SIEWS+ AI Worker Service (Python)
Internal API called by the Golang core backend for image-based AI detections.
"""
from fastapi import FastAPI, UploadFile, File, Form
import uvicorn
import cv2
import numpy as np
import os
import json

from detector import MultiStagePipeline
from face_manager import face_manager
from ocr_engine import ocr_engine

app = FastAPI(title="SIEWS+ AI Worker")

# Initialize models
pipeline = MultiStagePipeline(confidence=0.4)

@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    """Receives an image, runs Yolo + Face + OCR, returns JSON."""
    contents = await file.read()
    arr = np.frombuffer(contents, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    
    if frame is None:
        return {"error": "Invalid image"}

    # 1. Base Detection (People & Hazards)
    results = pipeline.run(frame) # Returns {persons, env}
    
    persons = results["persons"]
    hazards = results["env"]
    
    if persons:
        # 2. Face Recognition
        person_bboxes = [p["bbox"] for p in persons]
        face_results = face_manager.recognize_faces(frame, person_bboxes)
        
        # 3. OCR for Uniform
        ocr_results = ocr_engine.read_all_codes(frame, person_bboxes)
        
        # Merge results
        for i, p in enumerate(persons):
            p["face_name"] = "Unknown"
            p["ocr_code"] = None
            
            if i < len(face_results):
                p["face_name"] = face_results[i].get("name", "Unknown")
            
            if i < len(ocr_results) and ocr_results[i]:
                p["ocr_code"] = ocr_results[i].get("code")

    return {
        "persons": persons,
        "hazards": hazards
    }

@app.post("/train")
async def train():
    """Triggers the face manager to reload/train encodings."""
    from face_manager import face_manager
    face_manager._load_db()
    return {"status": "success", "count": face_manager.count}

if __name__ == "__main__":
    print("🤖 SIEWS+ AI Worker starting on port 8003...")
    uvicorn.run(app, host="0.0.0.0", port=8003)
