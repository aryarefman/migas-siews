"""
SIEWS+ 5.0 — Stage 1: Person Detection Training
Model: YOLOv8n (fine-tune from COCO pretrained)

Stage 1 detects people in the full frame.
COCO yolov8n already knows 'person' (class 0), so we fine-tune
only if you have custom migas-environment footage.
If no custom data, you can skip training and use the pretrained model directly.

Usage:
    python train_stage1.py [--custom] [--epochs 50] [--batch 16] [--imgsz 640]

Args:
    --custom   If set, fine-tune on your custom person dataset in dataset/stage1/
               Otherwise, downloads YOLOv8n pretrained weights and uses them as-is.
    --epochs   Number of training epochs (default: 50)
    --batch    Batch size (default: 16, reduce to 8 for low-VRAM GPUs)
    --imgsz    Image size (default: 640)
    --device   Training device: 0 (GPU), cpu (default: auto)
"""

import argparse
import shutil
from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
DATASET_YAML = ROOT_DIR / "dataset" / "stage1_person.yaml"
MODELS_DIR = ROOT_DIR / "backend" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Train Stage 1: Person Detection")
    parser.add_argument("--custom", action="store_true", help="Fine-tune on custom dataset")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="")
    return parser.parse_args()


def main():
    args = parse_args()

    print("=" * 60)
    print("SIEWS+ 5.0 — Stage 1: Person Detection")
    print("=" * 60)

    model = YOLO("yolov8n.pt")
    print("[INFO] Loaded YOLOv8n pretrained weights")

    if not args.custom:
        print("[INFO] No --custom flag. Using pretrained YOLOv8n directly (COCO person class).")
        print("[INFO] Saving pretrained weights to backend/models/stage1_person.pt")
        model.save(str(MODELS_DIR / "stage1_person.pt"))
        print("[OK] Stage 1 model saved.")
        return

    if not DATASET_YAML.exists():
        print(f"[ERROR] Dataset YAML not found: {DATASET_YAML}")
        print("        Place your custom person images in dataset/stage1/train|val|test/images+labels")
        return

    print(f"[INFO] Fine-tuning on custom dataset: {DATASET_YAML}")
    print(f"       epochs={args.epochs}, batch={args.batch}, imgsz={args.imgsz}")

    results = model.train(
        data=str(DATASET_YAML),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=15,
        device=args.device if args.device else None,
        project=str(BASE_DIR / "runs"),
        name="stage1_person",
        exist_ok=True,
        pretrained=True,
        augment=True,
        mosaic=1.0,
        mixup=0.1,
        degrees=10.0,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        verbose=True,
    )

    best_weights = BASE_DIR / "runs" / "stage1_person" / "weights" / "best.pt"
    if best_weights.exists():
        dst = MODELS_DIR / "stage1_person.pt"
        shutil.copy2(best_weights, dst)
        print(f"\n[OK] Best weights saved to {dst}")
    else:
        print("[WARN] best.pt not found. Check training logs.")

    print(f"\n[DONE] Stage 1 training complete.")
    print(f"       mAP50: {results.results_dict.get('metrics/mAP50(B)', 'N/A'):.4f}")


if __name__ == "__main__":
    main()
