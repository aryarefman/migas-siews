"""
SIEWS+ 5.0 — Stage 4: Infrastructure + Vehicles + Equipment Detection Training
Model: YOLOv8s (small — better accuracy for varied object sizes)

Stage 4 detects infrastructure and equipment on the full frame:
  0: oil_storage_tank
  1: oil_tank_truck
  2: construction_equip
  3: open_hole
  4: pressure_gauge
  5: adr_plate
  6: truck
  7: cctv_anomaly

Dataset: Merged from multiple Roboflow datasets (see dataset/analyze_and_merge_all.py)
         train=12920, val=1152, test=1056

Usage:
    python train_stage4.py [--epochs 100] [--batch 16] [--imgsz 640]
    python train_stage4.py --epochs 80 --batch 8 --device cpu  # CPU fallback

Kaggle Usage:
    # Upload this script + dataset/stage4/ to Kaggle
    # Enable GPU accelerator (P100 or T4)
    # Run: python train_stage4.py --epochs 100 --batch 16 --device 0
"""

import argparse
import shutil
from pathlib import Path
from ultralytics import YOLO

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
DATASET_YAML = ROOT_DIR / "dataset" / "stage4_infrastructure.yaml"
STAGE4_DATA = ROOT_DIR / "dataset" / "stage4"
MODELS_DIR = ROOT_DIR / "backend" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Train Stage 4: Infrastructure Detection")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    return parser.parse_args()


def check_dataset():
    """Verify dataset exists and report sample counts."""
    if not STAGE4_DATA.exists():
        print(f"[ERROR] Stage 4 dataset not found: {STAGE4_DATA}")
        print("        Run: python dataset/analyze_and_merge_all.py first")
        return False

    for split in ["train", "val", "test"]:
        split_path = STAGE4_DATA / split / "images"
        if split_path.exists():
            imgs = list(split_path.glob("*.*"))
            lbls_path = STAGE4_DATA / split / "labels"
            lbls = list(lbls_path.glob("*.txt")) if lbls_path.exists() else []
            print(f"  [{split}] images={len(imgs)}, labels={len(lbls)}")
        else:
            print(f"  [{split}] NOT FOUND")

    return True


def main():
    args = parse_args()

    print("=" * 60)
    print("SIEWS+ 5.0 — Stage 4: Infrastructure + Vehicles + Equipment")
    print("=" * 60)

    if not check_dataset():
        return

    model_weights = "yolov8s.pt"
    if args.resume:
        last = BASE_DIR / "runs" / "stage4_infrastructure" / "weights" / "last.pt"
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
        name="stage4_infrastructure",
        exist_ok=True,
        pretrained=True,
        # Augmentations
        augment=True,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,
        degrees=10.0,
        scale=0.5,
        shear=3.0,
        perspective=0.0,
        fliplr=0.5,
        flipud=0.0,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        # Optimizer
        optimizer="SGD",
        lr0=0.01,
        lrf=0.01,
        momentum=0.937,
        weight_decay=0.0005,
        warmup_epochs=3,
        # Multi-scale training for varied object sizes
        multi_scale=True,
        verbose=True,
        save_period=10,
    )

    best_weights = BASE_DIR / "runs" / "stage4_infrastructure" / "weights" / "best.pt"
    if best_weights.exists():
        dst = MODELS_DIR / "stage4_infrastructure.pt"
        shutil.copy2(best_weights, dst)
        print(f"\n[OK] Best weights saved to {dst}")
    else:
        print("[WARN] best.pt not found. Check training logs.")

    metrics = results.results_dict
    print(f"\n[DONE] Stage 4 training complete.")
    print(f"       mAP50:    {metrics.get('metrics/mAP50(B)', 'N/A')}")
    print(f"       mAP50-95: {metrics.get('metrics/mAP50-95(B)', 'N/A')}")
    print(f"       Precision: {metrics.get('metrics/precision(B)', 'N/A')}")
    print(f"       Recall:    {metrics.get('metrics/recall(B)', 'N/A')}")


if __name__ == "__main__":
    main()
