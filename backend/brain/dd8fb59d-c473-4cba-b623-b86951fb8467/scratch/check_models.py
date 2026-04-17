from ultralytics import YOLO
import os

models = [
    "backend/Model/stage1_person.pt",
    "backend/Model/stage2_ppe_harness.pt",
    "backend/Model/stage3_environment.pt"
]

for m in models:
    if os.path.exists(m):
        try:
            model = YOLO(m)
            print(f"Model {m} loaded successfully!")
            print(f"Classes: {model.names}")
        except Exception as e:
            print(f"Failed to load {m}: {e}")
    else:
        print(f"File {m} not found")
