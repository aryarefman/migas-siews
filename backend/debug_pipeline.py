"""Debug script: test YOLO pipeline with webcam frame directly."""
import cv2
import numpy as np
from detector import MultiStagePipeline

print("=" * 60)
print("SIEWS+ 5.0 — Pipeline Debug Test")
print("=" * 60)

# Initialize pipeline
print("[1] Initializing pipeline...")
pipeline = MultiStagePipeline(confidence=0.3, ppe_confidence=0.2)
print(f"    S1 loaded: {pipeline.model_s1 is not None}")
print(f"    S2 loaded: {pipeline.model_s2 is not None}")
print(f"    S3 loaded: {pipeline.model_s3 is not None}")
print(f"    S4 loaded: {pipeline.model_s4 is not None}")

# Open webcam
print("\n[2] Opening webcam...")
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("    FAIL: Cannot open webcam")
    exit(1)
print("    Webcam opened")

# Capture frame
print("\n[3] Capturing frame...")
ret, frame = cap.read()
cap.release()

if not ret:
    print("    FAIL: Cannot capture frame")
    exit(1)

print(f"    Frame shape: {frame.shape}")

# Run pipeline
print("\n[4] Running pipeline...")
result = pipeline.run(frame)

persons = result.get("persons", [])
env = result.get("env", [])
infra = result.get("infra", [])

print(f"    Persons detected: {len(persons)}")
print(f"    Environmental hazards: {len(env)}")
print(f"    Infrastructure objects: {len(infra)}")

if persons:
    print("\n[5] Person details:")
    for i, p in enumerate(persons):
        print(f"    Person {i}:")
        print(f"      Confidence: {p['confidence']:.3f}")
        print(f"      Bbox: {p['bbox']}")
        print(f"      PPE: {p['ppe']}")
        print(f"      Violations: {p['ppe_violations']}")

# Save annotated frame for visual verification
output_path = "debug_frame_output.jpg"
print(f"\n[6] Saving debug frame to {output_path}...")
for p in persons:
    x1, y1, x2, y2 = p["bbox"]
    conf = p["confidence"]
    color = (0, 255, 0)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    label = f"Person {conf:.0%}"
    cv2.putText(frame, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

cv2.imwrite(output_path, frame)
print(f"    Saved: {output_path}")

print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)
