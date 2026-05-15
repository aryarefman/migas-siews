"""
SIEWS+ 5.0 — Face Recognition Manager
Handles face registration, encoding storage, and real-time face matching.

Engine priority:
  1. face_recognition (dlib) — if installed, uses HOG + 128-dim encoding
  2. SCRFD + ArcFace ONNX — fallback, uses landmark alignment + 512-dim embedding
"""
import os
import json
import cv2
import numpy as np
import onnxruntime as ort
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

# Try to import face_recognition (dlib); fall back to SCRFD+ArcFace
try:
    import face_recognition as fr
    FACE_ENGINE = "dlib"
    print("[FACE] Using dlib face_recognition engine (HOG + 128-dim)")
except ImportError:
    FACE_ENGINE = "arcface"
    print("[FACE] face_recognition not available, using SCRFD + ArcFace ONNX")

# Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FACE_DATA_DIR = os.path.join(BACKEND_DIR, "static", "faces")
FACE_DB_FILE = os.path.join(FACE_DATA_DIR, "face_db.json")
SCRFD_MODEL_PATH = os.path.join(BACKEND_DIR, "models_onnx", "det_500m.onnx")
ARCFACE_MODEL_PATH = os.path.join(BACKEND_DIR, "models_onnx", "w600k_mbf.onnx")
os.makedirs(FACE_DATA_DIR, exist_ok=True)

# ArcFace alignment template (112x112 target positions)
ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# SCRFD Face Detector (used when dlib not available)
# ═══════════════════════════════════════════════════════════════════════════════

def _align_face(img: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """Align face to ArcFace template using 5-point landmarks."""
    M, _ = cv2.estimateAffinePartial2D(landmarks, ARCFACE_DST)
    if M is None:
        M = cv2.getAffineTransform(
            landmarks[:3].astype(np.float32),
            ARCFACE_DST[:3].astype(np.float32)
        )
    return cv2.warpAffine(img, M, (112, 112), borderValue=0)


class SCRFDDetector:
    """SCRFD face detection with 5-point landmarks."""

    def __init__(self, model_path: str, conf_threshold: float = 0.5):
        self.conf_threshold = conf_threshold
        self.nms_threshold = 0.4
        self.session = None
        self._input_size = (640, 640)
        self._feat_stride_fpn = [8, 16, 32]
        self._num_anchors = 2

        if os.path.exists(model_path):
            self.session = ort.InferenceSession(
                model_path,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
            )
            input_shape = self.session.get_inputs()[0].shape
            if len(input_shape) == 4:
                h_val, w_val = input_shape[2], input_shape[3]
                if isinstance(h_val, int) and isinstance(w_val, int):
                    self._input_size = (h_val, w_val)
            print(f"[FACE] SCRFD loaded (input={self._input_size})")

    def detect(self, img: np.ndarray) -> List[Tuple[List[int], Optional[np.ndarray], float]]:
        """Returns: list of (bbox[x1,y1,x2,y2], landmarks[5,2], confidence)"""
        if self.session is None:
            return []

        h, w = img.shape[:2]
        scale = min(self._input_size[0] / h, self._input_size[1] / w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img, (new_w, new_h))

        padded = np.zeros((self._input_size[0], self._input_size[1], 3), dtype=np.uint8)
        padded[:new_h, :new_w] = resized

        blob = ((padded.astype(np.float32) - 127.5) / 128.0).transpose(2, 0, 1)[np.newaxis]

        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: blob})
        return self._postprocess(outputs, scale, h, w)

    def _postprocess(self, outputs, scale, orig_h, orig_w):
        fmc = len(self._feat_stride_fpn)
        scores_list, bboxes_list, kpss_list = [], [], []

        for idx, stride in enumerate(self._feat_stride_fpn):
            scores = outputs[idx].flatten()
            bbox_preds = outputs[idx + fmc]
            kps_preds = outputs[idx + fmc * 2] if len(outputs) > fmc * 2 else None

            height = self._input_size[0] // stride
            width = self._input_size[1] // stride

            anchor_centers = np.stack(
                np.mgrid[:height, :width][::-1], axis=-1
            ).astype(np.float32).reshape(-1, 2) * stride

            if self._num_anchors > 1:
                anchor_centers = np.stack(
                    [anchor_centers] * self._num_anchors, axis=1
                ).reshape(-1, 2)

            pos_inds = np.where(scores >= self.conf_threshold)[0]
            if len(pos_inds) == 0:
                continue

            pos_scores = scores[pos_inds]
            pos_bboxes = bbox_preds[pos_inds]
            pos_centers = anchor_centers[pos_inds]

            x1 = (pos_centers[:, 0] - pos_bboxes[:, 0] * stride) / scale
            y1 = (pos_centers[:, 1] - pos_bboxes[:, 1] * stride) / scale
            x2 = (pos_centers[:, 0] + pos_bboxes[:, 2] * stride) / scale
            y2 = (pos_centers[:, 1] + pos_bboxes[:, 3] * stride) / scale

            scores_list.append(pos_scores)
            bboxes_list.append(np.stack([x1, y1, x2, y2], axis=-1))

            if kps_preds is not None:
                pos_kps = kps_preds[pos_inds]
                kps = np.zeros((len(pos_inds), 5, 2), dtype=np.float32)
                for k in range(5):
                    kps[:, k, 0] = (pos_centers[:, 0] + pos_kps[:, k * 2] * stride) / scale
                    kps[:, k, 1] = (pos_centers[:, 1] + pos_kps[:, k * 2 + 1] * stride) / scale
                kpss_list.append(kps)

        if not scores_list:
            return []

        scores_all = np.concatenate(scores_list)
        bboxes_all = np.concatenate(bboxes_list)
        kpss_all = np.concatenate(kpss_list) if kpss_list else None

        # NMS
        x1, y1, x2, y2 = bboxes_all[:, 0], bboxes_all[:, 1], bboxes_all[:, 2], bboxes_all[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores_all.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[np.where(iou <= self.nms_threshold)[0] + 1]

        results = []
        for i in keep:
            bbox = bboxes_all[i]
            bx1 = max(0, int(bbox[0]))
            by1 = max(0, int(bbox[1]))
            bx2 = min(orig_w, int(bbox[2]))
            by2 = min(orig_h, int(bbox[3]))
            kps = kpss_all[i] if kpss_all is not None else None
            results.append(([bx1, by1, bx2, by2], kps, float(scores_all[i])))
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# FaceManager — Main Class
# ═══════════════════════════════════════════════════════════════════════════════

class FaceManager:
    """
    Manages registered faces: encode, store, match.

    Engine selection:
      - dlib available: uses face_recognition (HOG detection + 128-dim encoding)
      - dlib not available: uses SCRFD (landmark detection) + ArcFace (512-dim)
    """

    def __init__(self, tolerance: float = 0.65):
        """
        tolerance: matching threshold.
          - dlib mode: face_distance <= tolerance means match (0.6 default, lower = stricter)
          - arcface mode: cosine similarity >= tolerance means match (0.60 = strict, reduces false positives)
        """
        self.tolerance = tolerance
        self._registered: List[dict] = []
        self._scrfd = None
        self._arcface_session = None

        if FACE_ENGINE == "arcface":
            self._load_arcface_models()

        self._load_db()

    def _load_arcface_models(self):
        """Load SCRFD detector and ArcFace embedding model."""
        if os.path.exists(SCRFD_MODEL_PATH):
            self._scrfd = SCRFDDetector(SCRFD_MODEL_PATH, conf_threshold=0.35)
            print("[FACE] SCRFD detector ready")

        if os.path.exists(ARCFACE_MODEL_PATH):
            self._arcface_session = ort.InferenceSession(
                ARCFACE_MODEL_PATH,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
            )
            print("[FACE] ArcFace ONNX loaded (512-dim)")

    def _load_db(self):
        """Load registered faces from disk with auto-migration from legacy format."""
        if os.path.exists(FACE_DB_FILE):
            try:
                with open(FACE_DB_FILE, "r") as f:
                    data = json.load(f)
                self._registered = []
                for entry in data:
                    # Migration: if no 'samples' key, convert legacy format
                    if "samples" not in entry:
                        enc = entry.get("encoding")
                        image_path = entry.get("image_path", "")

                        # Create samples array from legacy encoding
                        samples = []
                        if enc and isinstance(enc, list) and len(enc) > 0:
                            samples.append({
                                "sample_id": "sample_0",
                                "image_path": image_path,
                                "image_url": f"/{image_path}",
                                "encoding": enc,
                                "sample_type": "front",
                                "quality_score": 0.85,  # assume good for legacy
                                "captured_at": entry.get("registered_at", datetime.now(timezone.utc).isoformat()),
                            })

                        entry["samples"] = samples
                        entry["primary_image_url"] = f"/{image_path}"
                        entry["encoding"] = np.array(enc, dtype=np.float32) if enc else None
                    else:
                        # Normal: convert encoding arrays to numpy for each sample
                        for sample in entry.get("samples", []):
                            if "encoding" in sample and isinstance(sample["encoding"], list):
                                sample["encoding"] = np.array(sample["encoding"], dtype=np.float32)

                        # Ensure primary_image_url exists
                        if "primary_image_url" not in entry:
                            entry["primary_image_url"] = entry["samples"][0].get("image_url", f"/{entry.get('image_path', '')}") if entry.get("samples") else f"/{entry.get('image_path', '')}"

                    self._registered.append(entry)
                print(f"[FACE] Loaded {len(self._registered)} registered faces")
            except Exception as e:
                print(f"[FACE] Error loading face DB: {e}")
                self._registered = []
        else:
            self._registered = []

    def _save_db(self):
        """Persist registered faces to disk."""
        data = []
        for entry in self._registered:
            d = entry.copy()

            # Convert main encoding to list (legacy support)
            if isinstance(d.get("encoding"), np.ndarray):
                d["encoding"] = d["encoding"].tolist()
            elif d.get("encoding") is None:
                d["encoding"] = []

            # Convert sample encodings to lists
            for sample in d.get("samples", []):
                if isinstance(sample.get("encoding"), np.ndarray):
                    sample["encoding"] = sample["encoding"].tolist()

            data.append(d)
        with open(FACE_DB_FILE, "w") as f:
            json.dump(data, f)

    # ═══════════════════════════════════════════════════════════════════════════
    # Registration
    # ═══════════════════════════════════════════════════════════════════════════

    def register_face(self, image_bytes: bytes, name: str, code: str = "", phone: str = "") -> dict:
        """Register a new face from uploaded image (front photo as first sample)."""
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Gagal membaca gambar"}

        # Detect face for quality scoring
        bbox, _ = self._detect_face_for_quality(img)
        if bbox is None:
            return {"success": False, "error": "Tidak ada wajah terdeteksi dalam gambar"}

        # Extract encoding based on engine
        encoding = self._encode_face(img)
        if encoding is None:
            return {"success": False, "error": "Tidak ada wajah terdeteksi dalam gambar"}

        # Quality check
        quality_score, reason = self._score_image_quality(img, bbox)
        # Log warning but don't reject registration (user might have good reason)
        if quality_score < 0.45:
            print(f"[FACE] Warning: registration quality low ({reason}, score={quality_score:.2f})")

        # Save image
        face_id = f"face_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._registered)}"
        img_filename = f"{face_id}.jpg"
        img_path = os.path.join(FACE_DATA_DIR, img_filename)
        cv2.imwrite(img_path, img)

        # Build entry with new samples[] structure
        entry = {
            "id": face_id,
            "name": name,
            "code": code,
            "phone": phone,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "primary_image_url": f"/static/faces/{img_filename}",
            "encoding": encoding,  # kept for legacy migration
            "image_path": f"static/faces/{img_filename}",  # kept for legacy migration
            "samples": [
                {
                    "sample_id": "sample_0",
                    "image_path": f"static/faces/{img_filename}",
                    "image_url": f"/static/faces/{img_filename}",
                    "encoding": encoding.tolist(),
                    "sample_type": "front",
                    "quality_score": round(quality_score, 3),
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        }
        self._registered.append(entry)
        self._save_db()

        return {
            "success": True,
            "id": face_id,
            "name": name,
            "code": code,
            "phone": phone,
            "image_url": f"/static/faces/{img_filename}",
        }

    def _encode_face(self, img: np.ndarray) -> Optional[np.ndarray]:
        """Extract face encoding using available engine."""
        if FACE_ENGINE == "dlib":
            return self._encode_dlib(img)
        else:
            return self._encode_arcface(img)

    def _detect_face_for_quality(self, img: np.ndarray) -> Optional[Tuple[List[int], np.ndarray]]:
        """Detect face bounding box and landmarks for quality scoring."""
        if FACE_ENGINE == "dlib":
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            locations = fr.face_locations(rgb, model="hog")
            if locations:
                top, right, bottom, left = locations[0]
                return [left, top, right, bottom], None
            return None, None
        else:
            if self._scrfd is None:
                return None, None
            detections = self._scrfd.detect(img)
            if not detections:
                return None, None
            largest = max(detections, key=lambda d: (d[0][2]-d[0][0])*(d[0][3]-d[0][1]))
            return largest[0], largest[1]  # bbox, landmarks

    def _score_image_quality(self, img: np.ndarray, bbox: List[int] = None) -> Tuple[float, str]:
        """
        Score image quality 0.0-1.0 based on blur, face size, and lighting.

        Returns: (score, reason)
          - reason: "ok" | "blur_too_high" | "face_too_small" | "lighting_poor"
        Reject if score < 0.45.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Blur detection (Laplacian variance)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        blur_score = min(1.0, laplacian_var / 150.0)

        # 2. Face size relative to image area
        if bbox:
            x1, y1, x2, y2 = bbox
            face_w, face_h = x2 - x1, y2 - y1
            face_area_score = min(1.0, (face_w * face_h) / (80 * 80))
        else:
            face_area_score = 0.5

        # 3. Lighting (mean brightness)
        mean_brightness = np.mean(gray)
        if mean_brightness < 40:
            lighting_score = mean_brightness / 40 * 0.5
        elif mean_brightness > 220:
            lighting_score = (255 - mean_brightness) / 35 * 0.5
        else:
            lighting_score = 1.0

        total_score = blur_score * 0.4 + face_area_score * 0.35 + lighting_score * 0.25

        # Determine rejection reason
        if laplacian_var < 80:
            reason = "blur_too_high"
        elif bbox and (face_w < 25 or face_h < 25):
            reason = "face_too_small"
        elif mean_brightness < 30 or mean_brightness > 240:
            reason = "lighting_poor"
        else:
            reason = "ok"

        return total_score, reason

    def _encode_dlib(self, img: np.ndarray) -> Optional[np.ndarray]:
        """Extract 128-dim encoding using dlib/face_recognition."""
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        locations = fr.face_locations(rgb, model="hog")
        if not locations:
            return None
        encodings = fr.face_encodings(rgb, locations)
        if not encodings:
            return None
        return encodings[0]

    def _encode_arcface(self, img: np.ndarray) -> Optional[np.ndarray]:
        """Extract 512-dim encoding using SCRFD + ArcFace with alignment."""
        if self._scrfd is None or self._arcface_session is None:
            return None

        detections = self._scrfd.detect(img)
        if not detections:
            return None

        # Pick largest face
        largest = max(detections, key=lambda d: (d[0][2] - d[0][0]) * (d[0][3] - d[0][1]))
        bbox, landmarks, conf = largest

        # Align and get embedding
        if landmarks is not None and landmarks.shape == (5, 2):
            aligned = _align_face(img, landmarks)
        else:
            x1, y1, x2, y2 = bbox
            face_crop = img[y1:y2, x1:x2]
            if face_crop.size == 0:
                return None
            aligned = cv2.resize(face_crop, (112, 112))

        return self._run_arcface(aligned)

    def _run_arcface(self, face_112: np.ndarray) -> Optional[np.ndarray]:
        """Run ArcFace inference on 112x112 aligned face."""
        if self._arcface_session is None:
            return None
        face = cv2.cvtColor(face_112, cv2.COLOR_BGR2RGB).astype(np.float32)
        face = ((face / 255.0) - 0.5) / 0.5  # normalize to [-1, 1]
        face = face.transpose(2, 0, 1)[np.newaxis]  # NCHW

        input_name = self._arcface_session.get_inputs()[0].name
        output = self._arcface_session.run(None, {input_name: face})
        embedding = output[0][0]

        # L2 normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32)


    # ═══════════════════════════════════════════════════════════════════════════
    # Recognition
    # ═══════════════════════════════════════════════════════════════════════════

    def recognize_faces(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """
        Recognize faces in frame within person bounding boxes.

        Returns: list of match dicts (one per person_bbox), or None if no match.
        """
        if not self._registered:
            return [None] * len(person_bboxes) if person_bboxes else []

        if FACE_ENGINE == "dlib":
            return self._recognize_dlib(frame, person_bboxes)
        else:
            return self._recognize_arcface(frame, person_bboxes)

    def _recognize_dlib(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """Recognize using dlib face_recognition (HOG)."""
        results = []
        if not person_bboxes:
            return results

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        for bbox in person_bboxes:
            x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
            # Crop upper 70% (head region)
            head_y2 = y1 + int((y2 - y1) * 0.70)
            crop = rgb[y1:head_y2, x1:x2]

            if crop.size == 0 or crop.shape[0] < 40 or crop.shape[1] < 40:
                results.append(None)
                continue

            locations = fr.face_locations(crop, model="hog")
            if not locations:
                results.append(None)
                continue

            encodings = fr.face_encodings(crop, locations)
            if not encodings:
                results.append(None)
                continue

            # Match best face found
            match = self._match_dlib(encodings[0])
            results.append(match)

        return results

    def _match_dlib(self, encoding: np.ndarray) -> Optional[dict]:
        """
        Match query face against ALL samples from ALL registered persons.
        Returns best match with MAX confidence (minimum distance).
        """
        all_encodings = []
        all_entries = []  # (person_entry, sample_id or None)

        for person in self._registered:
            samples = person.get("samples", [])
            if not samples:
                # Legacy fallback: single encoding at person level
                enc = person.get("encoding")
                if enc is not None and isinstance(enc, np.ndarray) and len(enc) == 128:
                    all_encodings.append(enc)
                    all_entries.append((person, "legacy"))
                continue

            # All-sample matching
            for sample in samples:
                enc = sample.get("encoding")
                if enc is not None and isinstance(enc, np.ndarray) and len(enc) == 128:
                    all_encodings.append(enc)
                    all_entries.append((person, sample.get("sample_id")))

        if not all_encodings:
            return None

        distances = fr.face_distance(all_encodings, encoding)
        best_idx = int(np.argmin(distances))
        best_dist = distances[best_idx]

        if best_dist <= 0.45:
            best_person, best_sample_id = all_entries[best_idx]
            confidence = max(0.0, 1.0 - best_dist)
            return {
                "name": best_person["name"],
                "code": best_person.get("code", ""),
                "confidence": round(confidence, 3),
                "face_id": best_person["id"],
                "best_sample_id": best_sample_id,
            }
        return None

    def _recognize_arcface(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """Recognize using SCRFD + ArcFace (fallback when dlib not available)."""
        results = []
        if not person_bboxes:
            return results

        if self._scrfd is None or self._arcface_session is None:
            return [None] * len(person_bboxes)

        for bbox in person_bboxes:
            x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
            h_frame, w_frame = frame.shape[:2]
            x2, y2 = min(x2, w_frame), min(y2, h_frame)

            # Crop upper 70% (head region)
            head_y2 = y1 + int((y2 - y1) * 0.70)
            head_crop = frame[y1:head_y2, x1:x2]

            if head_crop.size == 0 or head_crop.shape[0] < 40 or head_crop.shape[1] < 40:
                results.append(None)
                continue

            # Detect face with landmarks
            detections = self._scrfd.detect(head_crop)
            if not detections:
                # Try full person bbox as fallback
                full_crop = frame[y1:y2, x1:x2]
                detections = self._scrfd.detect(full_crop)
                if not detections:
                    results.append(None)
                    continue
                # Use full crop context
                head_crop = full_crop

            # Largest face
            largest = max(detections, key=lambda d: (d[0][2] - d[0][0]) * (d[0][3] - d[0][1]))
            face_bbox, landmarks, det_conf = largest
            fx1, fy1, fx2, fy2 = face_bbox
            face_w, face_h = fx2 - fx1, fy2 - fy1

            # Reject tiny faces (lowered to 25px for distant persons)
            if face_w < 25 or face_h < 25:
                results.append(None)
                continue

            # Get aligned embedding
            if landmarks is not None and landmarks.shape == (5, 2):
                aligned = _align_face(head_crop, landmarks)
            else:
                face_crop = head_crop[fy1:fy2, fx1:fx2]
                if face_crop.size == 0:
                    results.append(None)
                    continue
                aligned = cv2.resize(face_crop, (112, 112))

            embedding = self._run_arcface(aligned)
            if embedding is None:
                results.append(None)
                continue

            match = self._match_arcface(embedding)
            results.append(match)

        return results

    def _match_arcface(self, query: np.ndarray) -> Optional[dict]:
        """
        Match query face against ALL samples from ALL registered persons.
        Returns best match with MAX cosine similarity across all samples.
        """
        best_person = None
        best_sim = -1.0
        best_sample_id = None

        for person in self._registered:
            samples = person.get("samples", [])

            if not samples:
                # Legacy fallback: single encoding at person level
                ref = person.get("encoding")
                if ref is None:
                    continue
                if isinstance(ref, list):
                    ref = np.array(ref, dtype=np.float32)
                if not isinstance(ref, np.ndarray) or ref.shape != query.shape:
                    continue
                sim = float(np.dot(query, ref))
                if sim > best_sim:
                    best_sim = sim
                    best_person = person
                    best_sample_id = "legacy"
                continue

            # Check ALL samples for this person
            for sample in samples:
                ref = sample.get("encoding")
                if ref is None:
                    continue
                ref = np.array(ref, dtype=np.float32)
                if ref.shape != query.shape:
                    continue
                sim = float(np.dot(query, ref))
                if sim > best_sim:
                    best_sim = sim
                    best_person = person
                    best_sample_id = sample.get("sample_id")

        if best_sim >= self.tolerance and best_person is not None:
            return {
                "name": best_person["name"],
                "code": best_person.get("code", ""),
                "confidence": round(best_sim, 3),
                "face_id": best_person["id"],
                "best_sample_id": best_sample_id,
            }

        if self._registered and best_sim > 0:
            print(f"[FACE] Best similarity: {best_sim:.3f} (threshold={self.tolerance}) → {'MATCH' if best_sim >= self.tolerance else 'NO MATCH'}")

        return None


    # ═══════════════════════════════════════════════════════════════════════════
    # Add Extra Sample
    # ═══════════════════════════════════════════════════════════════════════════

    def add_face_sample(self, face_id: str, image_bytes: bytes, sample_type: str = "extra") -> dict:
        """
        Add additional face sample to improve recognition accuracy.
        Saves SEPARATE image + SEPARATE encoding (NOT averaged).
        Rejects low quality samples.
        """
        entry = None
        for e in self._registered:
            if e["id"] == face_id:
                entry = e
                break
        if entry is None:
            return {"success": False, "error": "Face ID not found"}

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Gagal membaca gambar"}

        # Detect face for quality scoring
        bbox, _ = self._detect_face_for_quality(img)
        if bbox is None:
            return {"success": False, "error": "Wajah tidak terdeteksi"}

        encoding = self._encode_face(img)
        if encoding is None:
            return {"success": False, "error": "Gagal ekstrak encoding"}

        # Quality check — reject low quality samples
        quality_score, reason = self._score_image_quality(img, bbox)
        if quality_score < 0.45:
            return {
                "success": False,
                "error": f"Kualitas foto rendah ({reason}). Pastikan foto tajam, wajah jelas, dan pencahayaan baik.",
                "quality_score": round(quality_score, 3),
            }

        # Save as NEW separate image file (NOT averaged)
        samples = entry.get("samples", [])
        sample_idx = len(samples)
        safe_id = entry["id"].replace("-", "_")
        sample_filename = f"{safe_id}_sample{sample_idx}_{sample_type}.jpg"
        img_path = os.path.join(FACE_DATA_DIR, sample_filename)
        cv2.imwrite(img_path, img)

        # Store as SEPARATE sample (NOT averaged)
        sample_entry = {
            "sample_id": f"sample_{sample_idx}",
            "image_path": f"static/faces/{sample_filename}",
            "image_url": f"/static/faces/{sample_filename}",
            "encoding": encoding.tolist(),
            "sample_type": sample_type,
            "quality_score": round(quality_score, 3),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }

        if "samples" not in entry:
            entry["samples"] = []
        entry["samples"].append(sample_entry)

        # Update primary_image_url to first sample
        if sample_idx == 0:
            entry["primary_image_url"] = sample_entry["image_url"]

        self._save_db()
        return {
            "success": True,
            "message": f"Sample {sample_type} added (quality={quality_score:.2f})",
            "sample_id": sample_entry["sample_id"],
            "quality_score": round(quality_score, 3),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # Retrain / Sync
    # ═══════════════════════════════════════════════════════════════════════════

    def retrain_all(self) -> dict:
        """Re-encode all registered faces with current engine."""
        updated = 0
        failed = 0

        for entry in self._registered:
            img_path = os.path.join(BACKEND_DIR, entry.get("image_path", ""))
            if not os.path.exists(img_path):
                failed += 1
                continue

            img = cv2.imread(img_path)
            if img is None:
                failed += 1
                continue

            encoding = self._encode_face(img)
            if encoding is not None:
                entry["encoding"] = encoding
                updated += 1
            else:
                failed += 1

        self._save_db()
        print(f"[FACE] Retrain: {updated} OK, {failed} failed (engine={FACE_ENGINE})")
        return {"success": True, "updated": updated, "failed": failed, "total": len(self._registered)}

    # ═══════════════════════════════════════════════════════════════════════════
    # CRUD
    # ═══════════════════════════════════════════════════════════════════════════

    def get_all_faces(self, include_all_samples: bool = False) -> List[dict]:
        """
        Return all registered faces.

        Args:
            include_all_samples: If True, returns all sample URLs per person (internal use).
                                If False (default), returns primary_image_url only (frontend compatible).
        """
        result = []
        for e in self._registered:
            samples = e.get("samples", [])

            # Primary image: first sample or legacy image_path
            if samples:
                primary_url = samples[0].get("image_url", f"/{e.get('image_path', '')}")
            else:
                primary_url = f"/{e.get('image_path', '')}"

            entry = {
                "id": e["id"],
                "name": e["name"],
                "code": e.get("code", ""),
                "phone": e.get("phone", ""),
                "registered_at": e.get("registered_at", ""),
                "image_url": primary_url,
                "sample_count": len(samples) if samples else 1,
            }

            if include_all_samples:
                entry["all_sample_urls"] = [
                    s["image_url"] for s in samples
                ] if samples else [primary_url]

            result.append(entry)
        return result

    def delete_face(self, face_id: str) -> bool:
        """Remove a registered face and all its sample images."""
        for i, entry in enumerate(self._registered):
            if entry["id"] == face_id:
                # Delete all sample images
                for sample in entry.get("samples", []):
                    img_path = os.path.join(BACKEND_DIR, sample.get("image_path", ""))
                    if os.path.exists(img_path):
                        try:
                            os.remove(img_path)
                        except Exception:
                            pass
                # Also delete legacy image path if exists
                legacy_path = os.path.join(BACKEND_DIR, entry.get("image_path", ""))
                if os.path.exists(legacy_path):
                    try:
                        os.remove(legacy_path)
                    except Exception:
                        pass
                self._registered.pop(i)
                self._save_db()
                return True
        return False

    @property
    def count(self) -> int:
        return len(self._registered)


# Singleton
face_manager = FaceManager()
