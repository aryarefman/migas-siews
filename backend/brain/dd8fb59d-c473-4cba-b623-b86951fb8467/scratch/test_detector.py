import sys
import os
sys.path.append(os.getcwd())
from detector import UnifiedDetector
import numpy as np
import cv2

try:
    print("Initialising UnifiedDetector...")
    det = UnifiedDetector()
    print("Detector initialised.")
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    print("Running detection...")
    people, hazards = det.detect(frame)
    print(f"Detected {len(people)} people and {len(hazards)} hazards.")
    print("Test successful!")
except Exception as e:
    print(f"Test failed: {e}")
    import traceback
    traceback.print_exc()
