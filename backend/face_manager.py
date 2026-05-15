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
                    # Handle multi-encoding format
                    if "encodings" in entry and entry["encodings"]:
                        entry["encodings"] = [
                            np.array(e) if e is not None else None
                            for e in entry["encodings"]
                        ]
                    else:
                        # Migrate old single-encoding to list
                        old_enc = entry.get("encoding")
                        if old_enc is not None and len(old_enc) > 0:
                            entry["encodings"] = [np.array(old_enc)]
                        else:
                            entry["encodings"] = []

                    # Keep old field for backward compat
                    entry["encoding"] = None
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
            # Save encodings list
            if "encodings" in d and d["encodings"]:
                d["encodings"] = [
                    e.tolist() if isinstance(e, np.ndarray) else e
                    for e in d["encodings"] if e is not None
                ]
            # Clear deprecated single encoding field
            d["encoding"] = []
            data.append(d)
        with open(FACE_DB_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def register_face(self, image_bytes: bytes, name: str, code: str = "", phone: str = "") -> dict:
        """
        Register a new face or add encoding to existing person.

        If a person with the same name+code already exists, the new encoding
        is appended to their encodings list (multi-angle support).
        Otherwise, a new person entry is created.

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

        # Extract encoding
        encoding = self._encode_face(img)
        if encoding is None:
            return {"success": False, "error": "Tidak ada wajah terdeteksi dalam gambar"}

        # Check if person already exists (same name OR same code)
        existing = self._find_existing_person(name, code)

        if existing is not None:
            # Add encoding to existing person
            idx = existing
            entry = self._registered[idx]

            # Migrate old single-encoding format to multi-encoding
            if "encodings" not in entry:
                old_enc = entry.get("encoding")
                entry["encodings"] = [old_enc] if old_enc is not None and len(old_enc) > 0 else []
                entry["encoding"] = None  # Keep for backward compat but not used

            entry["encodings"].append(encoding)

            # Save additional photo
            photo_idx = len(entry.get("photos", []))
            img_filename = f"{entry['id']}_angle{photo_idx}.jpg"
            img_path = os.path.join(FACE_DATA_DIR, img_filename)
            cv2.imwrite(img_path, img)

            if "photos" not in entry:
                entry["photos"] = [entry.get("image_path", "")]
            entry["photos"].append(f"static/faces/{img_filename}")

            # Update phone if provided
            if phone and not entry.get("phone"):
                entry["phone"] = phone

            self._save_db()

            return {
                "success": True,
                "id": entry["id"],
                "name": entry["name"],
                "code": entry.get("code", ""),
                "phone": entry.get("phone", ""),
                "image_url": f"/static/faces/{img_filename}",
                "total_encodings": len(entry["encodings"]),
                "message": f"Foto tambahan berhasil ditambahkan ({len(entry['encodings'])} total)",
            }

        # New person — create fresh entry
        face_id = f"face_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._registered)}"

        # Save image
        img_filename = f"{face_id}.jpg"
        img_path = os.path.join(FACE_DATA_DIR, img_filename)
        cv2.imwrite(img_path, img)

        entry = {
            "id": face_id,
            "name": name,
            "code": code,
            "phone": phone,
            "encoding": None,  # Deprecated — use encodings list
            "encodings": [encoding],
            "photos": [f"static/faces/{img_filename}"],
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
            "total_encodings": 1,
        }

    def _find_existing_person(self, name: str, code: str) -> Optional[int]:
        """Find index of existing person by name or code."""
        name_lower = name.strip().lower()
        code_clean = code.strip().upper() if code else ""

        for i, entry in enumerate(self._registered):
            # Match by code first (more reliable)
            if code_clean and entry.get("code", "").strip().upper() == code_clean:
                return i
            # Match by name
            if entry.get("name", "").strip().lower() == name_lower:
                return i
        return None

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
                           If provided, returns exactly one result per bbox (matched or empty dict)

        Returns:
            List of dicts (same length as person_bboxes):
            [{name, code, confidence, bbox, face_id}] or {} if no face found
        """
        if not self._registered:
            return [{} for _ in (person_bboxes or [])]

        if FACE_ENGINE == "dlib":
            return self._recognize_dlib_per_person(frame, person_bboxes)
        else:
            return self._recognize_opencv_per_person(frame, person_bboxes)

    def _recognize_dlib_per_person(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """Recognize using dlib — returns one result per person bbox."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb, dtype=np.uint8)

        if not person_bboxes:
            # Full frame mode — return all detected faces
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

        # Per-person mode: one result per bbox
        results = []
        for bbox in person_bboxes:
            x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            crop = rgb[y1:y2, x1:x2]
            if crop.size == 0 or crop.shape[0] < 20 or crop.shape[1] < 20:
                results.append({})
                continue

            # Focus on upper body (head area) for better face detection
            head_h = min(int((y2 - y1) * 0.45), crop.shape[0])
            head_crop = crop[:head_h, :]

            locations = fr.face_locations(head_crop, model="hog")
            if not locations:
                # Try full person crop as fallback
                locations = fr.face_locations(crop, model="hog")
                if not locations:
                    results.append({})
                    continue
                # Use full crop for encoding
                used_crop = crop
            else:
                used_crop = head_crop

            # Ensure crop is contiguous uint8 for dlib
            used_crop = np.ascontiguousarray(used_crop, dtype=np.uint8)
            encodings = fr.face_encodings(used_crop, locations)
            if not encodings:
                results.append({})
                continue

            # Use the first (largest/most confident) face in this person's bbox
            match = self._match_encoding_dlib(encodings[0])
            top, right, bottom, left = locations[0]
            results.append({
                "name": match["name"] if match else "Unknown",
                "code": match["code"] if match else "",
                "confidence": match["confidence"] if match else 0.0,
                "face_id": match["id"] if match else None,
                "bbox": [x1 + left, y1 + top, x1 + right, y1 + bottom],
            })

        return results

    def _recognize_opencv_per_person(self, frame: np.ndarray, person_bboxes: List[list] = None) -> List[dict]:
        """Fallback recognition using OpenCV — returns one result per person bbox."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._haar_cascade is None:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._haar_cascade = cv2.CascadeClassifier(cascade_path)

        if not person_bboxes:
            faces = self._haar_cascade.detectMultiScale(gray, 1.3, 5)
            results = []
            for (x, y, w, h) in faces:
                face_crop = gray[y:y+h, x:x+w]
                face_resized = cv2.resize(face_crop, (128, 128))
                hist = cv2.calcHist([face_resized], [0], None, [128], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()
                match = self._match_encoding_opencv(hist)
                results.append({
                    "name": match["name"] if match else "Unknown",
                    "code": match["code"] if match else "",
                    "confidence": match["confidence"] if match else 0.0,
                    "face_id": match["id"] if match else None,
                    "bbox": [x, y, x + w, y + h],
                })
            return results

        # Per-person mode
        results = []
        for bbox in person_bboxes:
            x1, y1, x2, y2 = [max(0, int(v)) for v in bbox]
            region = gray[y1:y2, x1:x2]
            if region.size == 0:
                results.append({})
                continue

            faces = self._haar_cascade.detectMultiScale(region, 1.3, 5)
            if len(faces) == 0:
                results.append({})
                continue

            # Use largest face
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
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
                "bbox": [x1 + x, y1 + y, x1 + x + w, y1 + y + h],
            })

        return results

    def _match_encoding_dlib(self, encoding: np.ndarray) -> Optional[dict]:
        """
        Find best match from registered faces using dlib encodings.
        Supports multi-encoding per person — checks all angles and picks
        the closest match across all encodings for each person.
        """
        if not self._registered:
            return None

        best_match = None
        best_dist = float('inf')

        for entry in self._registered:
            # Support both old format (single encoding) and new (encodings list)
            encodings_list = entry.get("encodings", [])
            if not encodings_list:
                # Fallback to old single encoding
                old_enc = entry.get("encoding")
                if old_enc is not None and len(old_enc) == 128:
                    encodings_list = [old_enc]
                else:
                    continue

            # Check all encodings for this person, keep minimum distance
            for enc in encodings_list:
                if enc is None or len(enc) != 128:
                    continue
                enc_arr = np.array(enc) if not isinstance(enc, np.ndarray) else enc
                dist = float(fr.face_distance([enc_arr], encoding)[0])
                if dist < best_dist:
                    best_dist = dist
                    best_match = entry

        if best_match is None or best_dist > self.tolerance:
            return None

        confidence = max(0.0, 1.0 - best_dist)
        return {
            "id": best_match["id"],
            "name": best_match["name"],
            "code": best_match.get("code", ""),
            "confidence": round(confidence, 3),
        }

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

    def get_all_faces(self, include_all_samples: bool = False) -> List[dict]:
        """Return all registered faces (without raw encodings)."""
        return [
            {
                "id": e["id"],
                "name": e["name"],
                "code": e.get("code", ""),
                "phone": e.get("phone", ""),
                "image_url": f"/{e['image_path']}",
                "photos": [f"/{p}" for p in e.get("photos", [e.get("image_path", "")])] if include_all_samples else [f"/{e['image_path']}"],
                "total_encodings": len(e.get("encodings", [])),
                "registered_at": e.get("registered_at", ""),
            }
            for e in self._registered
        ]

    def add_face_sample(self, face_id: str, image_bytes: bytes) -> dict:
        """Add additional face sample (photo from different angle) to existing person."""
        # Find person
        target = None
        for entry in self._registered:
            if entry["id"] == face_id:
                target = entry
                break

        if target is None:
            return {"success": False, "error": "Face ID not found"}

        # Decode and encode face
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "error": "Gagal membaca gambar"}

        encoding = self._encode_face(img)
        if encoding is None:
            return {"success": False, "error": "Tidak ada wajah terdeteksi dalam gambar"}

        # Add encoding
        if "encodings" not in target:
            old_enc = target.get("encoding")
            target["encodings"] = [old_enc] if old_enc is not None and len(old_enc) > 0 else []
        target["encodings"].append(encoding)

        # Save photo
        photo_idx = len(target.get("photos", []))
        img_filename = f"{face_id}_angle{photo_idx}.jpg"
        img_path = os.path.join(FACE_DATA_DIR, img_filename)
        cv2.imwrite(img_path, img)

        if "photos" not in target:
            target["photos"] = [target.get("image_path", "")]
        target["photos"].append(f"static/faces/{img_filename}")

        self._save_db()

        return {
            "success": True,
            "id": face_id,
            "total_encodings": len(target["encodings"]),
            "message": f"Sample added ({len(target['encodings'])} total)",
        }

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
