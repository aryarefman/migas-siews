import sys, os
sys.path.append(os.getcwd())
from ultralytics import YOLO
import urllib.request

# Download a standard PPE test image (construction workers with helmets & vests)
test_urls = [
    "https://images.unsplash.com/photo-1504307651254-35680f356dfd?w=640",  # construction workers
    "https://images.unsplash.com/photo-1581092795360-fd1ca04f0952?w=640",  # worker with vest
]

scratch = "brain/dd8fb59d-c473-4cba-b623-b86951fb8467/scratch"

model = YOLO("Model/stage2_ppe_harness.pt")
print(f"PPE Model classes: {model.names}")
print(f"PPE Model task: {model.task}")
print()

# Test 1: On saved camera image
print("=" * 60)
print("TEST 1: PPE model on YOUR camera image (debug_detect.jpg)")
print("=" * 60)
results = model(f"{scratch}/debug_detect.jpg", conf=0.05)
if results[0].boxes and len(results[0].boxes) > 0:
    for c, cf in zip(results[0].boxes.cls, results[0].boxes.conf):
        print(f"  {model.names[int(c)]}: {float(cf):.1%}")
else:
    print("  ❌ NOTHING DETECTED")

# Save annotated
annotated = results[0].plot()
import cv2
cv2.imwrite(f"{scratch}/ppe_on_camera.jpg", annotated)
print(f"  Saved: {scratch}/ppe_on_camera.jpg")

# Test 2: On internet PPE images
for i, url in enumerate(test_urls):
    fname = f"{scratch}/ppe_test_{i}.jpg"
    try:
        print(f"\n{'=' * 60}")
        print(f"TEST {i+2}: PPE model on internet image #{i+1}")
        print(f"{'=' * 60}")
        urllib.request.urlretrieve(url, fname)
        results = model(fname, conf=0.05)
        if results[0].boxes and len(results[0].boxes) > 0:
            for c, cf in zip(results[0].boxes.cls, results[0].boxes.conf):
                print(f"  {model.names[int(c)]}: {float(cf):.1%}")
        else:
            print("  ❌ NOTHING DETECTED")
        
        annotated = results[0].plot()
        cv2.imwrite(f"{scratch}/ppe_result_{i}.jpg", annotated)
        print(f"  Saved: {scratch}/ppe_result_{i}.jpg")
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)
print("If NOTHING was detected on ANY image, the model is broken/incompatible.")
print("If detections appear on internet images but not camera, it's a camera issue.")
