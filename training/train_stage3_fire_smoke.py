#!/usr/bin/env python3
"""
SIEWS+ 5.0 — Stage 3: Fire & Smoke Detection
Transfer Learning with YOLOv8n

Usage:
    python train_stage3_fire_smoke.py

Requirements:
    pip install ultralytics torch matplotlib opencv-python pyyaml

Dataset:
    - Place 'Fire and Smoke.v14i.yolo26.zip' in dataset/ folder
    - Or place extracted 'stage3/' folder in dataset/ folder
    - Supplemental dataset from Roboflow: fire-smoke-qa4or
"""

import os
import sys
import zipfile
import shutil
import yaml
import random
from pathlib import Path

# ============================================================
# 1. DETECT ENVIRONMENT
# ============================================================
IS_KAGGLE = os.path.exists('/kaggle')
IS_COLAB  = False

try:
    import google.colab
    IS_COLAB = True
except ImportError:
    pass

print(f"Environment: Kaggle={IS_KAGGLE}, Colab={IS_COLAB}")

# ============================================================
# 2. INSTALL DEPENDENCIES
# ============================================================
print("\n[1/14] Installing dependencies...")
import subprocess
subprocess.run(['pip', 'install', '-U', 'ultralytics', '-q'], check=True)

import torch
print(f"CUDA available : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU            : {torch.cuda.get_device_name(0)}")
    DEVICE = '0'
else:
    print("No GPU — using CPU")
    DEVICE = 'cpu'

from ultralytics import YOLO

# ============================================================
# 3. PATH CONFIGURATION
# ============================================================
print("\n[2/14] Configuring paths...")

# Root project = parent of 'training' folder
SCRIPT_DIR = Path(__file__).parent.resolve() if '__file__' in dir() else Path.cwd()
PROJECT_ROOT = SCRIPT_DIR.parent
INPUT_DIR = PROJECT_ROOT / 'dataset'
OUTPUT_DIR = PROJECT_ROOT / 'training' / 'runs'

# For Kaggle/Colab override
if IS_KAGGLE:
    PROJECT_ROOT = Path('/kaggle/working')
    INPUT_DIR    = Path('/kaggle/input')
    OUTPUT_DIR   = PROJECT_ROOT
elif IS_COLAB:
    from google.colab import drive
    drive.mount('/content/drive')
    PROJECT_ROOT = Path('/content/drive/MyDrive/migas-siews')
    INPUT_DIR    = PROJECT_ROOT / 'dataset'
    OUTPUT_DIR   = PROJECT_ROOT / 'training' / 'runs'

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"  PROJECT_ROOT : {PROJECT_ROOT}")
print(f"  INPUT_DIR    : {INPUT_DIR}")
print(f"  OUTPUT_DIR   : {OUTPUT_DIR}")

# ============================================================
# 4. DATASET SETUP
# ============================================================
print("\n[3/14] Setting up dataset...")

def find_dataset_root():
    """Find folder with train/images structure."""
    for search_root in [INPUT_DIR, PROJECT_ROOT]:
        if not search_root.exists():
            continue
        for pattern in ['stage3', 'Fire and Smoke', 'fire-smoke', 'Fire_and_Smoke']:
            candidate = search_root / pattern
            if (candidate / 'train' / 'images').exists():
                return candidate
        # Fallback: search recursively
        train_dirs = list(search_root.rglob('train/images'))
        if train_dirs:
            train_dirs.sort(key=lambda p: len(p.parts))
            return train_dirs[0].parent.parent
    return None

def find_zip():
    """Find fire/smoke dataset ZIP."""
    zips = list(INPUT_DIR.rglob('*.zip'))
    fire_zips = [z for z in zips if 'fire' in z.name.lower() or 'smoke' in z.name.lower()]
    return fire_zips[0] if fire_zips else None

dataset_root = find_dataset_root()
stage3_zip   = find_zip()
EXTRACT_DIR  = OUTPUT_DIR / 'stage3_dataset'

print(f"  ZIP found : {stage3_zip}")
print(f"  Folder    : {dataset_root}")

if dataset_root is None and stage3_zip and stage3_zip.exists():
    print(f"  Extracting {stage3_zip.name} ...")
    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR)
    with zipfile.ZipFile(stage3_zip, 'r') as zf:
        zf.extractall(OUTPUT_DIR)
    extracted_roots = list(OUTPUT_DIR.rglob('train/images'))
    if extracted_roots:
        extracted_roots.sort(key=lambda p: len(p.parts))
        dataset_root = extracted_roots[0].parent.parent

if dataset_root and not EXTRACT_DIR.exists():
    try:
        EXTRACT_DIR.symlink_to(dataset_root.resolve())
        print(f"  Symlinked to: {dataset_root}")
    except:
        shutil.copytree(dataset_root, EXTRACT_DIR)

# Resolve symlink
if EXTRACT_DIR.is_symlink():
    EXTRACT_DIR = EXTRACT_DIR.resolve()

print(f"  EXTRACT_DIR: {EXTRACT_DIR}")

# ============================================================
# 5. VALIDATE STRUCTURE
# ============================================================
print("\n[4/14] Validating dataset structure...")

train_img = EXTRACT_DIR / 'train' / 'images'
val_img   = EXTRACT_DIR / 'val' / 'images'
if not val_img.exists():
    val_img = EXTRACT_DIR / 'valid' / 'images'

for split, img_dir in [('train', train_img), ('val', val_img)]:
    if img_dir.exists():
        n_img = len(list(img_dir.glob('*.*')))
        lbl_dir = img_dir.parent.parent / 'labels'
        n_lbl = len(list(lbl_dir.glob('*.txt'))) if lbl_dir.exists() else 0
        print(f"  [{split}] images={n_img:5d}  labels={n_lbl:5d}")
    else:
        print(f"  [{split}] NOT FOUND: {img_dir}")

# ============================================================
# 6. LABEL AUDIT
# ============================================================
print("\n[5/14] Auditing labels...")

CANONICAL_CLASS_NAMES  = {0: 'fire', 1: 'smoke'}
CANONICAL_CLASS_LIST   = ['fire', 'smoke']
CANONICAL_CLASS_COLORS = {0: (255, 80, 0), 1: (180, 180, 180)}

from collections import Counter
cls_counter = Counter()
n_audited = 0

train_lbl_dir = EXTRACT_DIR / 'train' / 'labels'
if train_lbl_dir.exists():
    for lbl_file in train_lbl_dir.glob('*.txt'):
        for line in lbl_file.read_text().strip().splitlines():
            parts = line.split()
            if parts:
                cls_counter[int(parts[0])] += 1
        n_audited += 1

print(f"  Files audited: {n_audited}")
for cls_id, count in sorted(cls_counter.items()):
    name = CANONICAL_CLASS_NAMES.get(cls_id, f'UNKNOWN-{cls_id}')
    print(f"    cls {cls_id} ({name:6s}): {count:6d} boxes")

unexpected = [k for k in cls_counter if k not in CANONICAL_CLASS_NAMES]
if unexpected:
    print(f"\n  WARNING: Unexpected class IDs: {unexpected}")
    print("  Please verify your dataset labels!")
else:
    print("\n  ✅ Class IDs valid (0=fire, 1=smoke)")

# ============================================================
# 7. CREATE CUSTOM YAML
# ============================================================
print("\n[6/14] Creating custom YAML...")

val_split = 'valid' if (EXTRACT_DIR / 'valid' / 'images').exists() else 'val'

custom_yaml = OUTPUT_DIR / 'stage3_fire_smoke.yaml'
yaml_content = {
    'path' : str(EXTRACT_DIR),
    'train': 'train/images',
    'val'  : f'{val_split}/images',
    'test' : 'test/images' if (EXTRACT_DIR / 'test' / 'images').exists() else f'{val_split}/images',
    'nc'   : 2,
    'names': CANONICAL_CLASS_LIST,  # LIST, not dict!
}

with open(custom_yaml, 'w') as f:
    yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)

print(f"  Custom YAML: {custom_yaml}")
print(f"\n{yaml_content}")

# Verify
_verify = yaml.safe_load(custom_yaml.read_text())
assert _verify['names'] == CANONICAL_CLASS_LIST
assert _verify['nc'] == 2
print("  ✅ YAML verified")

# ============================================================
# 8. VISUALIZE SAMPLES
# ============================================================
print("\n[7/14] Visualizing samples...")

try:
    import cv2
    import matplotlib.pyplot as plt

    train_img_dir = EXTRACT_DIR / 'train' / 'images'
    train_lbl_dir = EXTRACT_DIR / 'train' / 'labels'

    all_imgs = list(train_img_dir.glob('*.jpg')) + list(train_img_dir.glob('*.png'))
    samples = random.sample(all_imgs, min(6, len(all_imgs)))

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, img_path in zip(axes.flat, samples):
        img = cv2.imread(str(img_path))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w = img.shape[:2]
        lbl_path = train_lbl_dir / (img_path.stem + '.txt')
        if lbl_path.exists():
            for line in lbl_path.read_text().strip().splitlines():
                cls, xc, yc, bw, bh = map(float, line.split())
                cls = int(cls)
                x1 = int((xc - bw/2) * w); y1 = int((yc - bh/2) * h)
                x2 = int((xc + bw/2) * w); y2 = int((yc + bh/2) * h)
                color = CANONICAL_CLASS_COLORS.get(cls, (0, 255, 0))
                cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
                cv2.putText(img, f'ID:{cls} {CANONICAL_CLASS_NAMES.get(cls, "?")}',
                           (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        ax.imshow(img); ax.axis('off'); ax.set_title(img_path.name[:20])

    plt.suptitle('Sample Dataset — Fire & Smoke', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / 'dataset_samples.png'), dpi=100)
    plt.close()
    print("  ✅ Samples visualized and saved to dataset_samples.png")
except ImportError:
    print("  ⚠️ matplotlib/cv2 not available, skipping visualization")

# ============================================================
# 9. TRAINING CONFIG
# ============================================================
print("\n[8/14] Configuring training...")

# Auto-adjust batch size based on GPU memory
if torch.cuda.is_available():
    gpu_mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    if gpu_mem_gb > 14:
        BATCH = 16
    elif gpu_mem_gb > 7:
        BATCH = 8
    else:
        BATCH = 4
else:
    BATCH = 4

EPOCHS   = 80
IMGSZ    = 640
PATIENCE = 15
FREEZE   = 10

print(f"  EPOCHS   : {EPOCHS}")
print(f"  BATCH    : {BATCH} (auto-adjusted for GPU)")
print(f"  IMGSZ    : {IMGSZ}")
print(f"  PATIENCE : {PATIENCE}")
print(f"  FREEZE   : {FREEZE} layers (transfer learning)")
print(f"  DEVICE   : {DEVICE}")

# ============================================================
# 10. TRAIN
# ============================================================
print("\n[9/14] Loading base model...")
base_model = YOLO('yolov8n.pt')
print(f"  Model: {base_model.model_name}")
print(f"  Base classes: {len(base_model.names)} (COCO)")
print(f"  Fine-tuning to: fire, smoke")

print("\n[10/14] Starting training...")
results = base_model.train(
    data    = str(custom_yaml),
    epochs  = EPOCHS,
    batch   = BATCH,
    imgsz   = IMGSZ,
    device  = DEVICE,
    patience= PATIENCE,
    freeze  = FREEZE,
    pretrained = True,

    project = str(OUTPUT_DIR / 'runs'),
    name    = 'stage3_fire_smoke',
    exist_ok = True,

    augment    = True,
    mosaic     = 1.0,
    mixup      = 0.1,
    copy_paste = 0.1,
    hsv_h      = 0.03,
    hsv_s      = 0.9,
    hsv_v      = 0.5,
    fliplr     = 0.5,
    flipud     = 0.1,
    degrees    = 5.0,
    scale      = 0.6,
    translate  = 0.1,
    erasing    = 0.3,

    optimizer     = 'AdamW',
    lr0           = 0.001,
    lrf           = 0.01,
    weight_decay  = 0.0005,
    warmup_epochs = 3,

    save_period = 10,
    verbose     = True,
    plots       = True,
)

# ============================================================
# 11. EVALUATE
# ============================================================
print("\n[11/14] Evaluating results...")
print("=" * 50)
print("TRAINING RESULTS")
print("=" * 50)

metrics = results.results_dict
map50   = metrics.get('metrics/mAP50(B)', 0)
map5095 = metrics.get('metrics/mAP50-95(B)', 0)
prec    = metrics.get('metrics/precision(B)', 0)
rec     = metrics.get('metrics/recall(B)', 0)

print(f"mAP50     : {map50:.4f}  (target: > 0.85)")
print(f"mAP50-95  : {map5095:.4f}")
print(f"Precision : {prec:.4f}  (target: > 0.80)")
print(f"Recall    : {rec:.4f}  (target: > 0.80)")

if map50 >= 0.85:
    print("\n✅ Model GOOD! mAP50 >= 0.85")
elif map50 >= 0.70:
    print("\n⚠️  Model OK. Consider more epochs or data.")
else:
    print("\n❌ Model needs improvement.")

# ============================================================
# 12. VALIDATE BEST MODEL
# ============================================================
print("\n[12/14] Validating best model...")

run_dir = OUTPUT_DIR / 'runs' / 'stage3_fire_smoke'
best_pt = run_dir / 'weights' / 'best.pt'

if not best_pt.exists():
    print(f"  ⚠️ best.pt not found at {best_pt}")
    best_pt = run_dir / 'weights' / 'last.pt'
    print(f"  Using last.pt instead")

best_model = YOLO(str(best_pt))

loaded_names = {int(k): v for k, v in dict(best_model.names).items()}
if loaded_names != CANONICAL_CLASS_NAMES:
    print(f"  WARNING: Class mismatch {loaded_names} -> patching...")
    best_model.model.names = CANONICAL_CLASS_NAMES
    patched_pt = run_dir / 'weights' / 'best_patched.pt'
    best_model.save(str(patched_pt))
    best_model = YOLO(str(patched_pt))

final_names = {int(k): v for k, v in dict(best_model.names).items()}
print(f"  Final model names: {final_names}")
assert final_names == CANONICAL_CLASS_NAMES

val_results = best_model.val(data=str(custom_yaml), device=DEVICE, verbose=True)
print(f"\n  Val mAP50   : {val_results.box.map50:.4f}")
print(f"  Val mAP50-95: {val_results.box.map:.4f}")

# ============================================================
# 13. INFERENCE TEST
# ============================================================
print("\n[13/14] Running inference test...")

TEST_CONF = 0.15

test_img_dir = EXTRACT_DIR / 'test' / 'images'
if not test_img_dir.exists():
    test_img_dir = EXTRACT_DIR / val_split / 'images'

all_test = list(test_img_dir.glob('*.jpg')) + list(test_img_dir.glob('*.png'))
if all_test:
    test_imgs = random.sample(all_test, min(6, len(all_test)))

    PRED_COLORS_BGR = {0: (0, 140, 255), 1: (180, 180, 180)}
    GT_COLOR_BGR    = (0, 255, 80)

    import cv2
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, img_path in zip(axes.flat, test_imgs):
        pred    = best_model.predict(str(img_path), conf=TEST_CONF, verbose=False)[0]
        img_bgr = cv2.imread(str(img_path))
        h, w    = img_bgr.shape[:2]
        boxes   = pred.boxes
        label_parts = []

        lbl_path = test_img_dir.parent.parent / 'labels' / (img_path.stem + '.txt')
        if lbl_path.exists():
            for line in lbl_path.read_text().strip().splitlines():
                parts = line.split()
                if not parts: continue
                cls_gt = int(parts[0])
                xc, yc, bw, bh = map(float, parts[1:5])
                gx1 = int((xc - bw/2) * w); gy1 = int((yc - bh/2) * h)
                gx2 = int((xc + bw/2) * w); gy2 = int((yc + bh/2) * h)
                gt_name = CANONICAL_CLASS_NAMES.get(cls_gt, f'cls_{cls_gt}')
                cv2.rectangle(img_bgr, (gx1, gy1), (gx2, gy2), GT_COLOR_BGR, 1)
                cv2.putText(img_bgr, f'GT:{gt_name}', (gx1, max(gy1 - 18, 14)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, GT_COLOR_BGR, 1)

        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                name  = CANONICAL_CLASS_NAMES.get(cls_id, f'UNKNOWN-{cls_id}')
                color = PRED_COLORS_BGR.get(cls_id, (0, 255, 0))
                cv2.rectangle(img_bgr, (x1, y1), (x2, y2), color, 2)
                cv2.putText(img_bgr, f'{name} {conf:.0%}', (x1, max(y1 - 6, 18)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
                label_parts.append(f'ID:{cls_id}={name}({conf:.0%})')

        annotated = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        ax.imshow(annotated)
        ax.axis('off')
        preds_str = ', '.join(label_parts) if label_parts else '— no detection —'
        ax.set_title(preds_str[:40], fontsize=8)

    plt.suptitle('Inference Test — Best Model\n(orange=fire, gray=smoke, green=GT)')
    plt.tight_layout()
    plt.savefig(str(OUTPUT_DIR / 'inference_test.png'), dpi=100)
    plt.close()
    print("  ✅ Inference test saved to inference_test.png")
else:
    print("  ⚠️ No test images found, skipping inference test")

# ============================================================
# 14. SAVE MODEL
# ============================================================
print("\n[14/14] Saving model...")

last_pt = run_dir / 'weights' / 'last.pt'

export_model = best_model
export_model.names = CANONICAL_CLASS_NAMES

models_dir = PROJECT_ROOT / 'backend' / 'models'
models_dir.mkdir(parents=True, exist_ok=True)

out_best = models_dir / 'best_stage3_fire_smoke.pt'
out_last = models_dir / 'last_stage3_fire_smoke.pt'

export_model.save(str(out_best))
shutil.copy2(last_pt, out_last)

print(f"  ✅ Saved to backend/models/:")
print(f"     {out_best}  ({out_best.stat().st_size/1e6:.1f} MB)")
print(f"     {out_last}  ({out_last.stat().st_size/1e6:.1f} MB)")

if IS_KAGGLE:
    kaggle_best = Path('/kaggle/working/best_stage3_fire_smoke.pt')
    export_model.save(str(kaggle_best))
    print(f"\n  ✅ Also saved for Kaggle download: {kaggle_best}")

print("\n" + "=" * 50)
print("TRAINING COMPLETE!")
print("=" * 50)
print("\nNext steps:")
print("  1. If on Kaggle: download from Output tab")
print("  2. Copy best_*.pt to backend/models/")
print("  3. Restart backend to use new model")