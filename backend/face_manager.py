"""
SIEWS+ 5.0 — Face Recognition Manager
Handles face registration, encoding storage, and real-time face matching.

Uses face_recognition library (dlib-based) for robust face encoding.
Falls back to OpenCV's Haar cascade for environments without dlib.
"""
import os
import json
import cv2
import numpy as np
from datetime import datetime, timezone
from typing import List, Optional, Tuple

# Face data storage paths
FACE_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "faces")
FACE_DB_FILE = os.path.join(FACE_DATA_DIR, "face_db.json")
os.makedirs(FACE_DATA_DIR, exist_ok=True)

# Try to import face_recognition; fall back to OpenCV
try:
    import face_recognition as fr
    FACE_ENGINE = "dlib"
    print("[FACE] Using dlib face_recognition engine")
except ImportError:
    FACE_ENGINE = "opencv"
    print("[FACE] face_recognition not available, using OpenCV Haar cascade fallback")


class FaceManager:
    """
    Manages registered faces: encode, store, match.

    Workflow:
        1. Register: Upload photo + name → extract encoding → store
        2. Detect:   Given a frame, find all faces and match against registered
        3. Result:   Return list of recognized names or "Unknown"
    """

    def __init__(self, tolerance: float = 0.65):
        self.tolerance = tolerance
        self._registered: List[dict] = []  # [{id, name, code, encoding, image_path}]
        self._haar_cascade = None
        self._load_db()

    def _load_db(self):
        """Load registered faces from disk."""
        if os.path.exists(FACE_DB_FILE):
            try:
                with open(FACE_DB_FILE, "r") as f:
                    data = json.load(f)
                self._registered = []
                for entry in data:
                    entry["encoding"] = np.array(entry["encoding"]) if entry.get("encoding") else None
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
            if isinstance(d.get("encoding"), np.ndarray):
                d["encoding"] = d["encoding"].tolist()
            elif d.get("encoding") is None:
                d["encoding"] = []
            data.append(d)
        with open(FACE_DB_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def register_face(self, image_bytes: bytes, name: str, code: str = "", phone: str = "") -> dict:
        """
        Register a new face.

        Args:
            image_bytes: Raw image bytes (JPEG/PNG)
            name:        Person's name
            code:        Optional safety uniform code
            phone:       Optional WhatsApp phone number

        Returns:
            dict with registration result
        """
        # Decode image
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Gagal membaca gambar"}

        # Generate ID
        face_id = f"face_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._registered)}"

        # Save image
        img_filename = f"{face_id}.jpg"
        img_path = os.path.join(FACE_DATA_DIR, img_filename)
        cv2.imwrite(img_path, img)

        # Extract encoding
        encoding = self._encode_face(img)
        if encoding is None:
            return {"success": False, "error": "Tidak ada wajah terdeteksi dalam gambar"}

        entry = {
            "id": face_id,
            "name": name,
            "code": code,
            "phone": phone,
            "encoding": encoding,
            "image_path": f"static/faces/{img_filename}",
            "registered_at": datetime.now(timezone.utc).isoformat(),
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
        """Extract face encoding from an image."""
        if FACE_ENGINE == "dlib":
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            locations = fr.face_locations(rgb, model="hog")
            if not locations:
                return None
            encodings = fr.face_encodings(rgb, locations)
            if not encodings:
                return None
            return encodings[0]
        else:
            # OpenCV fallback: use histogram-based simple encoding
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if self._haar_cascade is None:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self._haar_cascade = cv2.CascadeClassifier(cascade_path)

            faces = self._haar_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) == 0:
                return None

            # Use the largest face
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            face_crop = gray[y:y+h, x:x+w]
            face_resized = cv2.resize(face_crop, (128, 128))
            # Simple histogram-based encoding
            hist = cv2.calcHist([face_resized], [0], None, [128], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            return hist

    def recognize_faces(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """
        Recognize faces in a frame.

        Args:
            frame:         Full frame (BGR)
            person_bboxes: Optional list of [x1, y1, x2, y2] person bounding boxes
                           If provided, only search within these boxes

        Returns:
            List of dicts: [{name, code, confidence, bbox, face_id}]
        """
        if not self._registered:
            return []

        results = []

        if FACE_ENGINE == "dlib":
            results = self._recognize_dlib(frame, person_bboxes)
        else:
            results = self._recognize_opencv(frame, person_bboxes)

        return results

    def _recognize_dlib(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """Recognize using dlib face_recognition."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Detect faces
        if person_bboxes:
            # Search only within person bounding boxes for efficiency
            all_results = []
            for bbox in person_bboxes:
                x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
                crop = rgb[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                locations = fr.face_locations(crop, model="hog")
                if not locations:
                    continue

                encodings = fr.face_encodings(crop, locations)
                for i, enc in enumerate(encodings):
                    match = self._match_encoding_dlib(enc)
                    top, right, bottom, left = locations[i]
                    all_results.append({
                        "name": match["name"] if match else "Unknown",
                        "code": match["code"] if match else "",
                        "confidence": match["confidence"] if match else 0.0,
                        "face_id": match["id"] if match else None,
                        "bbox": [x1 + left, y1 + top, x1 + right, y1 + bottom],
                    })
            return all_results
        else:
            # Full frame detection
            locations = fr.face_locations(rgb, model="hog")
            if not locations:
                return []

            encodings = fr.face_encodings(rgb, locations)
            results = []
            for i, enc in enumerate(encodings):
                match = self._match_encoding_dlib(enc)
                top, right, bottom, left = locations[i]
                results.append({
                    "name": match["name"] if match else "Unknown",
                    "code": match["code"] if match else "",
                    "confidence": match["confidence"] if match else 0.0,
                    "face_id": match["id"] if match else None,
                    "bbox": [left, top, right, bottom],
                })
            return results

    def _match_encoding_dlib(self, encoding: np.ndarray) -> Optional[dict]:
        """Find best match from registered faces using dlib encodings."""
        if not self._registered:
            return None

        registered_encodings = []
        valid_entries = []
        for entry in self._registered:
            if entry.get("encoding") is not None and len(entry["encoding"]) == 128:
                registered_encodings.append(entry["encoding"])
                valid_entries.append(entry)

        if not registered_encodings:
            return None

        distances = fr.face_distance(registered_encodings, encoding)
        best_idx = np.argmin(distances)
        best_dist = distances[best_idx]

        if best_dist <= self.tolerance:
            confidence = max(0.0, 1.0 - best_dist)
            return {
                "id": valid_entries[best_idx]["id"],
                "name": valid_entries[best_idx]["name"],
                "code": valid_entries[best_idx].get("code", ""),
                "confidence": round(confidence, 3),
            }
        return None

    def _recognize_opencv(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """Fallback recognition using OpenCV histogram matching."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._haar_cascade is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._haar_cascade = cv2.CascadeClassifier(cascade_path)

        search_regions = []
        if person_bboxes:
            for bbox in person_bboxes:
                x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
                search_regions.append((gray[y1:y2, x1:x2], x1, y1))
        else:
            search_regions.append((gray, 0, 0))

        results = []
        for region, offset_x, offset_y in search_regions:
            if region.size == 0:
                continue
            faces = self._haar_cascade.detectMultiScale(region, 1.3, 5)
            for (x, y, w, h) in faces:
                face_crop = region[y:y+h, x:x+w]
                face_resized = cv2.resize(face_crop, (128, 128))
                hist = cv2.calcHist([face_resized], [0], None, [128], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()

                match = self._match_encoding_opencv(hist)
                results.append({
                    "name": match["name"] if match else "Unknown",
                    "code": match["code"] if match else "",
                    "confidence": match["confidence"] if match else 0.0,
                    "face_id": match["id"] if match else None,
                    "bbox": [offset_x + x, offset_y + y, offset_x + x + w, offset_y + y + h],
                })
        return results

    def _match_encoding_opencv(self, hist: np.ndarray) -> Optional[dict]:
        """Match using histogram correlation."""
        best_match = None
        best_score = -1

        for entry in self._registered:
            if entry.get("encoding") is None or len(entry["encoding"]) == 0:
                continue
            ref_hist = np.array(entry["encoding"]).astype(np.float32)
            if ref_hist.shape != hist.shape:
                continue
            score = cv2.compareHist(
                ref_hist.reshape(-1, 1),
                hist.reshape(-1, 1),
                cv2.HISTCMP_CORREL
            )
            if score > best_score and score > 0.5:
                best_score = score
                best_match = {
                    "id": entry["id"],
                    "name": entry["name"],
                    "code": entry.get("code", ""),
                    "confidence": round(score, 3),
                }

        return best_match

    def get_all_faces(self) -> List[dict]:
        """Return all registered faces (without raw encodings)."""
        return [
            {
                "id": e["id"],
                "name": e["name"],
                "code": e.get("code", ""),
                "phone": e.get("phone", ""),
                "image_url": f"/{e['image_path']}",
                "registered_at": e.get("registered_at", ""),
            }
            for e in self._registered
        ]

    def delete_face(self, face_id: str) -> bool:
        """Remove a registered face."""
        for i, entry in enumerate(self._registered):
            if entry["id"] == face_id:
                # Remove image file
                img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), entry["image_path"])
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)
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
