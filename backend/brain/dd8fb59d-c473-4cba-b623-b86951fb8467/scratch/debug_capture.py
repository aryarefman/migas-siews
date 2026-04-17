import cv2
import sys
import os
import numpy as np
sys.path.append(os.getcwd())
from detector import UnifiedDetector

def debug_capture():
    print("Initializing detector...")
    det = UnifiedDetector(confidence=0.1) # Very low confidence for debug
    
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open camera.")
        return

    print("Capturing frame...")
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        print("Error: Could not read frame.")
        return

    print("Running detection...")
    people, hazards = det.detect_base(frame)
    print(f"Results: {len(people)} people, {len(hazards)} hazards")
    
    for p in people:
        x1, y1, x2, y2 = [int(v) for v in p["bbox"]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        print(f"Person at {p['bbox']} with conf {p['confidence']}")
        
    for h in hazards:
        x1, y1, x2, y2 = [int(v) for v in h["bbox"]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        print(f"Hazard {h['label']} at {h['bbox']}")

    output_path = "brain/dd8fb59d-c473-4cba-b623-b86951fb8467/scratch/debug_detect.jpg"
    cv2.imwrite(output_path, frame)
    print(f"Debug image saved to {output_path}")

if __name__ == "__main__":
    debug_capture()
