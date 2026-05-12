"""
Train and validate the Rust/Corrosion YOLO model with defensive label checks.

Why this exists:
- Roboflow exports can contain paths that are fragile outside the original
  notebook/runtime.
- A swapped class id silently ruins training. This script audits class ids,
  writes a clean YOLO data yaml, and supports explicit remapping before train.
- The inference preview draws ground truth and prediction side by side using
  the expected class map, so a wrong model.names mapping is visible.

Examples:
    python training/train_rust_corrosion.py --audit-only
    python training/train_rust_corrosion.py --epochs 100 --batch 16 --device 0
    python training/train_rust_corrosion.py --remap 0:3,3:0 --epochs 100 --device 0
    python training/train_rust_corrosion.py --predict-only backend/models/rust_corrosion.pt
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT_DIR / "dataset" / "Rust Corrosion Detection.v16i.yolo26"
DEFAULT_RUN_ROOT = ROOT_DIR / "training" / "runs_rust_corrosion"
DEFAULT_EXPORT_DIR = ROOT_DIR / "backend" / "models"
DEFAULT_LEGACY_EXPORT_DIR = ROOT_DIR / "model" / "New"

# Canonical class order used by the local corrosion dataset.
CLASS_NAMES = {
    0: "corrosion",
    1: "moderate corrosion",
    2: "rust",
    3: "severe corrosion",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine tune Rust/Corrosion YOLO safely")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--weights", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="")
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--freeze", type=int, default=0)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-size", type=int, default=12)
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--skip-preview", action="store_true")
    parser.add_argument(
        "--no-clean-invalid",
        action="store_true",
        help="Keep invalid zero-area/out-of-range boxes. By default they are removed in a prepared copy.",
    )
    parser.add_argument("--predict-only", type=Path, default=None, help="Run test inference preview with an existing .pt")
    parser.add_argument(
        "--remap",
        type=str,
        default="",
        help="Optional label id remap, e.g. '0:3,3:0'. Use only after visual audit proves labels are swapped.",
    )
    parser.add_argument(
        "--export-name",
        type=str,
        default="rust_corrosion.pt",
        help="Filename for exported best checkpoint.",
    )
    return parser.parse_args()


def parse_remap(raw: str) -> Dict[int, int]:
    if not raw.strip():
        return {}

    remap: Dict[int, int] = {}
    for item in raw.split(","):
        if ":" not in item:
            raise ValueError(f"Invalid remap item '{item}'. Expected OLD:NEW.")
        old_s, new_s = item.split(":", 1)
        old_id, new_id = int(old_s), int(new_s)
        if old_id not in CLASS_NAMES or new_id not in CLASS_NAMES:
            raise ValueError(f"Class id out of range in remap '{item}'.")
        remap[old_id] = new_id
    return remap


def split_names(dataset_dir: Path) -> Tuple[str, str]:
    val_split = "valid" if (dataset_dir / "valid" / "images").exists() else "val"
    test_split = "test" if (dataset_dir / "test" / "images").exists() else val_split
    return val_split, test_split


def iter_images(images_dir: Path) -> List[Path]:
    if not images_dir.exists():
        return []
    return sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)


def read_label_file(path: Path) -> List[Tuple[int, float, float, float, float]]:
    rows: List[Tuple[int, float, float, float, float]] = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 5:
            raise ValueError(f"{path}:{line_no} has {len(parts)} columns, expected at least 5.")
        cls_id = int(float(parts[0]))
        coords = tuple(float(v) for v in parts[1:5])
        rows.append((cls_id, *coords))
    return rows


def is_valid_yolo_row(row: Tuple[int, float, float, float, float]) -> bool:
    cls_id, xc, yc, width, height = row
    return (
        cls_id in CLASS_NAMES
        and 0 <= xc <= 1
        and 0 <= yc <= 1
        and 0 < width <= 1
        and 0 < height <= 1
    )


def report_has_invalid_labels(report: Dict[str, Dict]) -> bool:
    for split, info in report.items():
        if split.startswith("_"):
            continue
        if info["invalid_ids"] or info["invalid_rows"]:
            return True
    return False


def audit_dataset(dataset_dir: Path) -> Dict[str, Dict]:
    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_dir}")

    val_split, test_split = split_names(dataset_dir)
    report: Dict[str, Dict] = {}
    label_to_images: Dict[int, List[Path]] = defaultdict(list)

    for split in ["train", val_split, test_split]:
        images_dir = dataset_dir / split / "images"
        labels_dir = dataset_dir / split / "labels"
        images = iter_images(images_dir)
        labels = sorted(labels_dir.glob("*.txt")) if labels_dir.exists() else []
        image_stems = {p.stem for p in images}
        label_stems = {p.stem for p in labels}

        counts = Counter()
        empty = 0
        invalid_rows: List[str] = []
        invalid_ids = Counter()

        for label_path in labels:
            try:
                rows = read_label_file(label_path)
            except Exception as exc:
                invalid_rows.append(str(exc))
                continue

            if not rows:
                empty += 1
            for cls_id, xc, yc, width, height in rows:
                counts[cls_id] += 1
                if cls_id not in CLASS_NAMES:
                    invalid_ids[cls_id] += 1
                if not (0 <= xc <= 1 and 0 <= yc <= 1 and 0 < width <= 1 and 0 < height <= 1):
                    invalid_rows.append(
                        f"{label_path}: invalid bbox cls={cls_id} xywh={xc:.4f},{yc:.4f},{width:.4f},{height:.4f}"
                    )
                if cls_id in CLASS_NAMES and len(label_to_images[cls_id]) < 12:
                    image_path = dataset_dir / split / "images" / f"{label_path.stem}.jpg"
                    if image_path.exists():
                        label_to_images[cls_id].append(image_path)

        report[split] = {
            "images": len(images),
            "labels": len(labels),
            "empty_labels": empty,
            "missing_labels": sorted(image_stems - label_stems)[:20],
            "orphan_labels": sorted(label_stems - image_stems)[:20],
            "counts": dict(sorted(counts.items())),
            "invalid_ids": dict(sorted(invalid_ids.items())),
            "invalid_rows": invalid_rows[:20],
        }

    report["_meta"] = {
        "dataset": str(dataset_dir),
        "val_split": val_split,
        "test_split": test_split,
        "class_names": CLASS_NAMES,
        "label_examples": {str(k): [str(p) for p in v] for k, v in label_to_images.items()},
    }
    return report


def print_audit(report: Dict[str, Dict]) -> None:
    print("\n=== Rust/Corrosion Dataset Audit ===")
    print(f"dataset: {report['_meta']['dataset']}")
    print("class map:")
    for cls_id, name in CLASS_NAMES.items():
        print(f"  {cls_id}: {name}")

    for split, info in report.items():
        if split.startswith("_"):
            continue
        total = sum(info["counts"].values())
        print(f"\n[{split}] images={info['images']} labels={info['labels']} empty={info['empty_labels']} instances={total}")
        for cls_id in sorted(CLASS_NAMES):
            count = info["counts"].get(cls_id, 0)
            pct = (count / total * 100) if total else 0.0
            marker = "  <-- no instances in this split" if count == 0 else ""
            print(f"  {cls_id} {CLASS_NAMES[cls_id]:20s}: {count:6d} ({pct:5.1f}%){marker}")
        if info["missing_labels"]:
            print(f"  warning: sample images without labels: {info['missing_labels'][:3]}")
        if info["orphan_labels"]:
            print(f"  warning: sample labels without images: {info['orphan_labels'][:3]}")
        if info["invalid_ids"]:
            print(f"  error: invalid class ids: {info['invalid_ids']}")
        if info["invalid_rows"]:
            print(f"  error: invalid rows: {info['invalid_rows'][:3]}")


def write_data_yaml(dataset_dir: Path, run_root: Path) -> Path:
    val_split, test_split = split_names(dataset_dir)
    run_root.mkdir(parents=True, exist_ok=True)
    yaml_path = run_root / "rust_corrosion.clean.yaml"
    payload = {
        "path": str(dataset_dir.resolve()),
        "train": "train/images",
        "val": f"{val_split}/images",
        "test": f"{test_split}/images",
        "nc": len(CLASS_NAMES),
        "names": [CLASS_NAMES[i] for i in sorted(CLASS_NAMES)],
    }
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    print(f"\n[OK] Clean YOLO yaml written: {yaml_path}")
    return yaml_path


def link_or_copy_images(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    try:
        os.symlink(src.resolve(), dst, target_is_directory=True)
    except OSError:
        shutil.copytree(src, dst)


def create_prepared_dataset(dataset_dir: Path, run_root: Path, remap: Dict[int, int], clean_invalid: bool) -> Path:
    if not remap and not clean_invalid:
        return dataset_dir

    parts = []
    if clean_invalid:
        parts.append("clean")
    if remap:
        parts.append("remap_" + "_".join(f"{old}to{new}" for old, new in sorted(remap.items())))
    out_dir = run_root / ("dataset_" + "_".join(parts))
    val_split, test_split = split_names(dataset_dir)

    print(f"\n[INFO] Creating prepared dataset: {out_dir}")
    if remap:
        print(f"       remap: {remap}")
    if clean_invalid:
        print("       cleaning: invalid class ids and zero-area/out-of-range boxes are removed")

    removed_rows = Counter()
    for split in ["train", val_split, test_split]:
        src_images = dataset_dir / split / "images"
        src_labels = dataset_dir / split / "labels"
        dst_split = out_dir / split
        dst_labels = dst_split / "labels"
        dst_split.mkdir(parents=True, exist_ok=True)
        dst_labels.mkdir(parents=True, exist_ok=True)
        link_or_copy_images(src_images, dst_split / "images")

        for src_label in src_labels.glob("*.txt"):
            new_lines: List[str] = []
            for line_no, line in enumerate(src_label.read_text().splitlines(), start=1):
                if not line.strip():
                    continue
                parts = line.split()
                try:
                    old_id = int(float(parts[0]))
                    row = (remap.get(old_id, old_id), *(float(v) for v in parts[1:5]))
                except Exception:
                    if clean_invalid:
                        removed_rows[split] += 1
                        continue
                    raise ValueError(f"{src_label}:{line_no} cannot be parsed: {line}")

                parts[0] = str(row[0])
                if clean_invalid and not is_valid_yolo_row(row):
                    removed_rows[split] += 1
                    continue
                new_lines.append(" ".join(parts))
            (dst_labels / src_label.name).write_text(("\n".join(new_lines) + "\n") if new_lines else "")

    if removed_rows:
        print(f"       removed rows: {dict(sorted(removed_rows.items()))}")
    return out_dir


def save_audit_report(report: Dict[str, Dict], run_root: Path) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    report_path = run_root / "dataset_audit.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"[OK] Audit report written: {report_path}")


def choose_weights(args: argparse.Namespace) -> str:
    if args.weights:
        return str(args.weights)
    for candidate in [ROOT_DIR / "yolo26n.pt", ROOT_DIR / "yolov8n.pt"]:
        if candidate.exists():
            return str(candidate)
    return "yolov8n.pt"


def train_model(args: argparse.Namespace, data_yaml: Path) -> Path:
    from ultralytics import YOLO

    weights = choose_weights(args)
    print(f"\n[INFO] Training from weights: {weights}")
    model = YOLO(weights)
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device if args.device else None,
        patience=args.patience,
        freeze=args.freeze,
        project=str(args.run_root / "runs"),
        name="rust_corrosion",
        exist_ok=True,
        pretrained=True,
        augment=True,
        mosaic=1.0,
        mixup=0.05,
        copy_paste=0.05,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        fliplr=0.5,
        degrees=5.0,
        scale=0.5,
        erasing=0.3,
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        weight_decay=0.0005,
        warmup_epochs=3,
        save_period=10,
        plots=True,
        seed=args.seed,
        verbose=True,
    )

    metrics = getattr(results, "results_dict", {}) or {}
    print("\n=== Validation Metrics ===")
    for key in ["metrics/mAP50(B)", "metrics/mAP50-95(B)", "metrics/precision(B)", "metrics/recall(B)"]:
        print(f"{key}: {metrics.get(key, 'N/A')}")

    best_pt = args.run_root / "runs" / "rust_corrosion" / "weights" / "best.pt"
    if not best_pt.exists():
        best_pt = args.run_root / "runs" / "rust_corrosion" / "weights" / "last.pt"
    if not best_pt.exists():
        raise FileNotFoundError("No best.pt or last.pt checkpoint found after training.")

    export_checkpoint(best_pt, args.export_name)
    return best_pt


def export_checkpoint(checkpoint: Path, export_name: str) -> None:
    for export_dir in [DEFAULT_EXPORT_DIR, DEFAULT_LEGACY_EXPORT_DIR]:
        export_dir.mkdir(parents=True, exist_ok=True)
        dst = export_dir / export_name
        shutil.copy2(checkpoint, dst)
        print(f"[OK] Exported checkpoint: {dst}")


def draw_yolo_boxes(image, rows: Sequence[Tuple[int, float, float, float, float]], class_names: Dict[int, str], title: str):
    import cv2

    canvas = image.copy()
    height, width = canvas.shape[:2]
    colors = {
        0: (255, 120, 20),
        1: (0, 210, 255),
        2: (255, 60, 60),
        3: (255, 230, 0),
    }
    for cls_id, xc, yc, bw, bh in rows:
        x1 = int((xc - bw / 2) * width)
        y1 = int((yc - bh / 2) * height)
        x2 = int((xc + bw / 2) * width)
        y2 = int((yc + bh / 2) * height)
        color = colors.get(cls_id, (255, 255, 255))
        label = class_names.get(cls_id, f"cls_{cls_id}")
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        cv2.putText(canvas, label, (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
    cv2.putText(canvas, title, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return canvas


def predictions_as_yolo_rows(result) -> List[Tuple[int, float, float, float, float]]:
    rows: List[Tuple[int, float, float, float, float]] = []
    if result.boxes is None:
        return rows
    height, width = result.orig_shape[:2]
    for box in result.boxes:
        cls_id = int(box.cls[0])
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
        xc = ((x1 + x2) / 2) / width
        yc = ((y1 + y2) / 2) / height
        bw = (x2 - x1) / width
        bh = (y2 - y1) / height
        rows.append((cls_id, xc, yc, bw, bh))
    return rows


def save_label_preview(dataset_dir: Path, run_root: Path, sample_size: int, seed: int) -> None:
    try:
        import cv2
        import matplotlib.pyplot as plt
    except ImportError as exc:
        print(f"[WARN] Skipping label preview because an optional package is missing: {exc}")
        return

    image_dir = dataset_dir / "train" / "images"
    label_dir = dataset_dir / "train" / "labels"
    rng = random.Random(seed)
    examples: Dict[int, List[Path]] = defaultdict(list)

    for label_path in sorted(label_dir.glob("*.txt")):
        rows = read_label_file(label_path)
        ids = {row[0] for row in rows if is_valid_yolo_row(row)}
        if not ids:
            continue
        image_path = None
        for ext in IMAGE_EXTENSIONS:
            candidate = image_dir / f"{label_path.stem}{ext}"
            if candidate.exists():
                image_path = candidate
                break
        if image_path is None:
            continue
        for cls_id in ids:
            if len(examples[cls_id]) < sample_size:
                examples[cls_id].append(image_path)

    selected: List[Tuple[int, Path]] = []
    per_class = max(1, min(3, sample_size // max(1, len(CLASS_NAMES))))
    for cls_id in sorted(CLASS_NAMES):
        candidates = examples.get(cls_id, [])
        if candidates:
            selected.extend((cls_id, p) for p in rng.sample(candidates, min(per_class, len(candidates))))

    if not selected:
        print("[WARN] No labels available for label preview.")
        return

    cols = min(4, len(selected))
    rows_count = (len(selected) + cols - 1) // cols
    fig, axes = plt.subplots(rows_count, cols, figsize=(cols * 4.2, rows_count * 4.0))
    if rows_count == 1 and cols == 1:
        axes_flat = [axes]
    else:
        axes_flat = list(getattr(axes, "flat", axes))

    for ax, (target_cls_id, image_path) in zip(axes_flat, selected):
        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None:
            ax.axis("off")
            continue
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        rows = read_label_file(label_dir / f"{image_path.stem}.txt")
        canvas = draw_yolo_boxes(image_rgb, rows, CLASS_NAMES, f"ID {target_cls_id}: {CLASS_NAMES[target_cls_id]}")
        ax.imshow(canvas)
        ax.axis("off")
        ax.set_title(image_path.name[:50], fontsize=8)

    for ax in axes_flat[len(selected):]:
        ax.axis("off")

    out_png = run_root / "label_audit_by_class.png"
    plt.tight_layout()
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] Label audit preview written: {out_png}")


def save_inference_preview(model_path: Path, dataset_dir: Path, run_root: Path, conf: float, sample_size: int, seed: int) -> None:
    try:
        import cv2
        import matplotlib.pyplot as plt
        from ultralytics import YOLO
    except ImportError as exc:
        print(f"[WARN] Skipping inference preview because an optional package is missing: {exc}")
        return

    _, test_split = split_names(dataset_dir)
    image_dir = dataset_dir / test_split / "images"
    label_dir = dataset_dir / test_split / "labels"
    images = [p for p in iter_images(image_dir) if (label_dir / f"{p.stem}.txt").exists()]
    if not images:
        print("[WARN] No test images with labels available for inference preview.")
        return

    rng = random.Random(seed)
    samples = rng.sample(images, min(sample_size, len(images)))
    model = YOLO(str(model_path))

    cols = 2
    rows = len(samples)
    fig, axes = plt.subplots(rows, cols, figsize=(14, max(4, rows * 3.2)))
    if rows == 1:
        axes = [axes]

    detections = {}
    for row_axes, image_path in zip(axes, samples):
        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None:
            continue
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        gt_rows = read_label_file(label_dir / f"{image_path.stem}.txt")
        result = model.predict(str(image_path), conf=conf, verbose=False)[0]
        pred_rows = predictions_as_yolo_rows(result)

        detections[image_path.name] = [
            {
                "class_id": cls_id,
                "class_name": CLASS_NAMES.get(cls_id, f"cls_{cls_id}"),
                "xywh": [xc, yc, bw, bh],
            }
            for cls_id, xc, yc, bw, bh in pred_rows
        ]

        gt_canvas = draw_yolo_boxes(image_rgb, gt_rows, CLASS_NAMES, "GROUND TRUTH")
        pred_canvas = draw_yolo_boxes(image_rgb, pred_rows, CLASS_NAMES, "PREDICTION")
        row_axes[0].imshow(gt_canvas)
        row_axes[0].axis("off")
        row_axes[0].set_title(image_path.name, fontsize=8)
        row_axes[1].imshow(pred_canvas)
        row_axes[1].axis("off")
        pred_names = [CLASS_NAMES.get(cls_id, f"cls_{cls_id}") for cls_id, *_ in pred_rows]
        row_axes[1].set_title(", ".join(pred_names) or "no detection", fontsize=8)

    out_png = run_root / "inference_gt_vs_pred.png"
    out_json = run_root / "inference_predictions.json"
    plt.tight_layout()
    fig.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close(fig)
    out_json.write_text(json.dumps(detections, indent=2))
    print(f"[OK] Inference preview written: {out_png}")
    print(f"[OK] Inference json written: {out_json}")


def main() -> None:
    args = parse_args()
    random.seed(args.seed)
    remap = parse_remap(args.remap)

    source_dataset_dir = args.dataset.resolve()
    dataset_dir = source_dataset_dir
    args.run_root.mkdir(parents=True, exist_ok=True)

    source_report = audit_dataset(source_dataset_dir)
    source_has_invalid = report_has_invalid_labels(source_report)
    prepare_dataset = bool(remap) or (source_has_invalid and not args.no_clean_invalid)
    if prepare_dataset:
        print_audit(source_report)
        save_audit_report(source_report, args.run_root / "source")
        dataset_dir = create_prepared_dataset(
            source_dataset_dir,
            args.run_root,
            remap,
            clean_invalid=source_has_invalid and not args.no_clean_invalid,
        ).resolve()

    report = audit_dataset(dataset_dir)
    print_audit(report)
    save_audit_report(report, args.run_root)
    data_yaml = write_data_yaml(dataset_dir, args.run_root)
    if not args.skip_preview:
        save_label_preview(dataset_dir, args.run_root, args.sample_size, args.seed)

    bad_splits = [
        split
        for split, info in report.items()
        if not split.startswith("_") and (info["invalid_ids"] or info["invalid_rows"])
    ]
    if args.audit_only:
        print("\n[DONE] Audit-only mode. No training was started.")
        return

    if bad_splits:
        raise RuntimeError(f"Dataset has invalid labels in splits: {bad_splits}")

    model_path: Optional[Path]
    if args.predict_only:
        model_path = args.predict_only.resolve()
        if not model_path.exists():
            raise FileNotFoundError(f"Predict-only checkpoint not found: {model_path}")
    else:
        model_path = train_model(args, data_yaml)

    if not args.skip_preview:
        save_inference_preview(model_path, dataset_dir, args.run_root, args.conf, args.sample_size, args.seed)

    print("\n[DONE] Rust/Corrosion fine tuning flow complete.")


if __name__ == "__main__":
    main()
