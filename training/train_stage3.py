"""
SIEWS+ 5.0 — Stage 3: Environmental Hazard Detection Training
Model: YOLOv8n (fast — runs on full frame in parallel with other stages)

Stage 3 detects environmental hazards on the full frame:
- fire (class 0)
- smoke (class 1)

Dataset: D-Fire + data_fire_smoke (merged via merge_datasets.py)

Usage:
    python train_stage3.py [--epochs 100] [--batch 16] [--imgsz 640]
    python train_stage3.py --epochs 80 --batch 8 --device cpu  # CPU fallback
"""

import argparse
import shutil
from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
DATASET_YAML = ROOT_DIR / "dataset" / "stage3_environment.yaml"
STAGE3_DATA = ROOT_DIR / "dataset" / "stage3"
MODELS_DIR = ROOT_DIR / "backend" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Train Stage 3: Fire/Smoke Detection")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    return parser.parse_args()


def check_dataset():
    if not STAGE3_DATA.exists():
        print(f"[ERROR] Stage 3 dataset not found: {STAGE3_DATA}")
        print("        Run: python dataset/merge_datasets.py first")
        return False

    for split in ["train", "val", "test"]:
        split_path = STAGE3_DATA / split / "images"
        if split_path.exists():
            imgs = list(split_path.glob("*.*"))
            print(f"  [{split}] images={len(imgs)}")

    return True


def main():
    args = parse_args()

    print("=" * 60)
    print("SIEWS+ 5.0 — Stage 3: Fire/Smoke Detection")
    print("=" * 60)

    if not check_dataset():
        return

    model_weights = "yolov8n.pt"
    if args.resume:
        last = BASE_DIR / "runs" / "stage3_environment" / "weights" / "last.pt"
        if last.exists():
            model_weights = str(last)
            print(f"[INFO] Resuming from: {model_weights}")

    model = YOLO(model_weights)
    print(f"[INFO] Loaded model: {model_weights}")
    print(f"[INFO] Training config: epochs={args.epochs}, batch={args.batch}, imgsz={args.imgsz}")

    results = model.train(
        data=str(DATASET_YAML),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=20,
        device=args.device if args.device else None,
        project=str(BASE_DIR / "runs"),
        name="stage3_environment",
        exist_ok=True,
        pretrained=True,
        augment=True,
        mosaic=1.0,
        mixup=0.15,
        degrees=10.0,
        scale=0.5,
        fliplr=0.5,
        hsv_h=0.02,
        hsv_s=0.8,
        hsv_v=0.5,
        # Fire/smoke benefit from color augmentation (day/night conditions)
        erasing=0.4,
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3,
        verbose=True,
        save_period=10,
    )

    best_weights = BASE_DIR / "runs" / "stage3_environment" / "weights" / "best.pt"
    if best_weights.exists():
        dst = MODELS_DIR / "stage3_environment.pt"
        shutil.copy2(best_weights, dst)
        print(f"\n[OK] Best weights saved to {dst}")
    else:
        print("[WARN] best.pt not found. Check training logs.")

    metrics = results.results_dict
    print(f"\n[DONE] Stage 3 training complete.")
    print(f"       mAP50:    {metrics.get('metrics/mAP50(B)', 'N/A')}")
    print(f"       mAP50-95: {metrics.get('metrics/mAP50-95(B)', 'N/A')}")
    print(f"       Precision: {metrics.get('metrics/precision(B)', 'N/A')}")
    print(f"       Recall:    {metrics.get('metrics/recall(B)', 'N/A')}")


if __name__ == "__main__":
    main()
