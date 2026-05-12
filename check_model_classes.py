"""
Check actual class names from the trained model.
"""
from ultralytics import YOLO
import os

# Path to model
model_path = os.path.join(os.path.dirname(__file__), "model", "New", "best_stage2_labeled_safety.pt")

print(f"[CHECK] Loading model from: {model_path}")
print(f"[CHECK] Model exists: {os.path.exists(model_path)}")

try:
    model = YOLO(model_path)
    print(f"\n[CHECK] Model names from YOLO:")
    print(model.names)
    
    # Also check if names is dict or list
    print(f"\n[CHECK] Type of names: {type(model.names)}")
    if isinstance(model.names, dict):
        for k, v in model.names.items():
            print(f"  Class {k}: {v}")
    elif isinstance(model.names, list):
        for i, v in enumerate(model.names):
            print(f"  Index {i}: {v}")
            
except Exception as e:
    print(f"[ERROR] Failed to load model: {e}")
    import traceback
    traceback.print_exc()
