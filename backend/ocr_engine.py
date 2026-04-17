"""
SIEWS+ 5.0 — OCR Engine for Safety Uniform Code Detection
Reads alphanumeric codes from safety uniforms/vests on detected personnel.

Uses EasyOCR for text detection, with fallback to Tesseract.
Applies preprocessing filters to handle CCTV image quality.
"""
import cv2
import re
import numpy as np
from typing import List, Optional, Tuple

# Try to import OCR engines
try:
    import easyocr
    OCR_ENGINE = "easyocr"
    print("[OCR] Using EasyOCR engine")
except ImportError:
    OCR_ENGINE = "none"
    print("[OCR] No OCR engine available. Install easyocr: pip install easyocr")


class OCREngine:
    """
    Reads safety uniform codes from person crops.

    Uniform codes typically follow patterns like:
        - P78, P79, P80 (employee codes)
        - TW2-001, TW2-002 (site codes)
        - Alphanumeric 2-8 characters

    Workflow:
        1. Receive person crop (from YOLO person bbox)
        2. Preprocess: enhance contrast, sharpen, denoise
        3. Run OCR on the vest/chest area
        4. Filter results by safety code pattern
    """

    # Regex patterns — Priority order matters!
    # Tier 1: Letter+Digit combos (most likely to be actual safety codes)
    PRIORITY_PATTERNS = [
        r"[A-Z]{1,3}\d{1,5}",         # P80, TW2, ABC12345
        r"[A-Z]{2,3}-\d{2,5}",        # TW-001, AB-12345
        r"\d{2,5}[A-Z]{1,3}",         # 80P, 001TW
        r"[A-Z]{1,4}\d{1,4}[A-Z]?",   # PPE2A, SAF1
    ]
    # Tier 2: Fallback patterns (less specific)
    FALLBACK_PATTERNS = [
        r"[A-Z]\d{1,2}",              # P7, A1
        r"\d{3,8}",                   # 123456 (pure digits)
    ]

    def __init__(self, languages: list = None):
        self._reader = None
        self._languages = languages or ["en"]
        self._initialized = False

    def _init_reader(self):
        """Lazy initialization of OCR reader (heavy resource)."""
        if self._initialized:
            return

        if OCR_ENGINE == "easyocr":
            try:
                self._reader = easyocr.Reader(
                    self._languages,
                    gpu=False,
                    verbose=False,
                )
                self._allowlist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
                self._initialized = True
                print("[OCR] EasyOCR reader initialized")
            except Exception as e:
                print(f"[OCR] Failed to initialize EasyOCR: {e}")
                self._initialized = False

    def read_uniform_code(self, frame: np.ndarray, person_bbox: list) -> Optional[dict]:
        """
        Extract safety uniform code from a person's detection area.

        Args:
            frame:       Full frame (BGR)
            person_bbox: [x1, y1, x2, y2] pixel coordinates

        Returns:
            dict with {code, confidence, bbox} or None if no code found
        """
        if OCR_ENGINE == "none":
            return None

        self._init_reader()
        if not self._initialized:
            return None

        x1, y1, x2, y2 = [max(0, int(v)) for v in person_bbox]
        h_person = y2 - y1
        w_person = x2 - x1

        if h_person < 30 or w_person < 20:
            return None

        # Optimization: only crop to 'chest' if this is a person detection
        # If full frame (fallback), use the whole area
        is_full_frame = (x1 == 0 and y1 == 0 and w_person >= frame.shape[1] - 5 and h_person >= frame.shape[0] - 5)
        
        if is_full_frame:
            crop = frame.copy()
            chest_x1, chest_y1 = 0, 0
        else:
            # Focus on the chest/torso area (upper 10-75% of person height)
            chest_y1 = y1 + int(h_person * 0.10) 
            chest_y2 = y1 + int(h_person * 0.75)
            chest_x1 = max(0, x1 - 10)
            chest_x2 = min(frame.shape[1], x2 + 10)
            crop = frame[chest_y1:chest_y2, chest_x1:chest_x2]

        if crop.size == 0:
            return None

        # Preprocess for better OCR accuracy
        processed = self._preprocess(crop)

        # Run OCR
        try:
            results = self._reader.readtext(
                processed,
                detail=1,
                paragraph=False,
                min_size=10,
                text_threshold=0.5,
                low_text=0.3,
                width_ths=0.7,
                allowlist=self._allowlist,
            )
        except Exception as e:
            print(f"[OCR] Read error: {e}")
            return None

        # fuzzy matching to known registered codes
        import difflib
        final_matches = []

        try:
            from face_manager import face_manager
            registered_codes = {p.get("code") for p in face_manager._registered if p.get("code")}
        except Exception:
            registered_codes = set()

        for (bbox_ocr, text, conf) in results:
            cleaned = text.strip().upper().replace(" ", "").replace(".", "").replace(":", "")
            if len(cleaned) < 2 or len(cleaned) > 12:
                continue
            
            # Common replacements
            corrected = cleaned.replace("O", "0").replace("I", "1").replace("S", "5").replace("B", "8").replace("Z", "2")
            
            # Re-assemble keeping prefix letters (like P80 -> "P" + "80")
            num_idx = next((i for i, c in enumerate(cleaned) if c.isdigit()), len(cleaned))
            if num_idx > 0 and num_idx < len(cleaned):
                corrected = cleaned[:num_idx] + cleaned[num_idx:].replace("O", "0").replace("I", "1").replace("S", "5").replace("B", "8")
            
            if conf > 0.25:
                print(f"[OCR-DEBUG] Detected: '{cleaned}' → corrected: '{corrected}' (conf: {conf:.2f})")

            # 1. Fuzzy match against registered codes first!
            best_match = None
            best_ratio = 0
            for r_code in registered_codes:
                ratio1 = difflib.SequenceMatcher(None, cleaned, r_code).ratio()
                ratio2 = difflib.SequenceMatcher(None, corrected, r_code).ratio()
                ratio = max(ratio1, ratio2)
                # If 70% match or 1 character mistake, we consider it a hit!
                if ratio > 0.70 and ratio > best_ratio:
                    best_match = r_code
                    best_ratio = ratio

            matched_code = best_match or corrected

            # 2. Add to all matches if it looks somewhat valid or we fuzzy matched it
            ocr_pts = np.array(bbox_ocr).astype(int)
            ocr_x1 = chest_x1 + min(ocr_pts[:, 0])
            ocr_y1 = chest_y1 + min(ocr_pts[:, 1])
            ocr_x2 = chest_x1 + max(ocr_pts[:, 0])
            ocr_y2 = chest_y1 + max(ocr_pts[:, 1])

            entry = {
                "code": matched_code,
                "full_text": matched_code,
                "confidence": round(float(conf), 3),
                "bbox": [ocr_x1, ocr_y1, ocr_x2, ocr_y2],
            }

            if best_match:
                print(f"[OCR] Fuzzy Matched: {cleaned} -> {matched_code} (Ratio: {best_ratio:.2f})")
                final_matches.append(entry)
            else:
                # Try regex only if not fuzzy matched
                for pattern in self.PRIORITY_PATTERNS:
                    if re.search(pattern, matched_code):
                        final_matches.append(entry)
                        break

        if not final_matches:
            return None
            
        # Return first fuzzy matched or regex matched
        return final_matches[0]

    def read_all_codes_multi(self, frame: np.ndarray) -> List[dict]:
        """Scan full frame and return ALL detected codes (for image analysis)."""
        if OCR_ENGINE == "none" or not self._initialized:
            self._init_reader()
            if not self._initialized:
                return []

        processed = self._preprocess(frame)
        try:
            results = self._reader.readtext(processed, detail=1, paragraph=False,
                                            min_size=10, text_threshold=0.5, low_text=0.3, width_ths=0.7, allowlist=self._allowlist)
        except Exception:
            return []

        import difflib
        try:
            from face_manager import face_manager
            registered_codes = {p.get("code") for p in face_manager._registered if p.get("code")}
        except:
            registered_codes = set()

        all_matches = []
        seen_codes = set()
        for (bbox_ocr, text, conf) in results:
            cleaned = text.strip().upper().replace(" ", "").replace(".", "").replace(":", "")
            if len(cleaned) < 2 or len(cleaned) > 12:
                continue

            corrected = cleaned.replace("O", "0").replace("I", "1").replace("S", "5").replace("B", "8").replace("Z", "2")
            num_idx = next((i for i, c in enumerate(cleaned) if c.isdigit()), len(cleaned))
            if num_idx > 0 and num_idx < len(cleaned):
                corrected = cleaned[:num_idx] + cleaned[num_idx:].replace("O", "0").replace("I", "1").replace("S", "5").replace("B", "8")

            best_match = None
            best_ratio = 0
            for r_code in registered_codes:
                ratio = max(difflib.SequenceMatcher(None, cleaned, r_code).ratio(), difflib.SequenceMatcher(None, corrected, r_code).ratio())
                if ratio > 0.70 and ratio > best_ratio:
                    best_match = r_code
                    best_ratio = ratio

            matched_code = best_match or corrected

            if best_match or any(re.search(p, matched_code) for p in self.PRIORITY_PATTERNS):
                if matched_code not in seen_codes:
                    ocr_pts = np.array(bbox_ocr).astype(int)
                    all_matches.append({
                        "code": matched_code,
                        "full_text": matched_code,
                        "confidence": round(float(conf), 3),
                        "bbox": [int(min(ocr_pts[:, 0])), int(min(ocr_pts[:, 1])),
                                 int(max(ocr_pts[:, 0])), int(max(ocr_pts[:, 1]))],
                    })
                    seen_codes.add(matched_code)
        return all_matches

    def read_all_codes(self, frame: np.ndarray, person_bboxes: List[list]) -> List[Optional[dict]]:
        """Read uniform codes from detected persons, with full-frame fallback."""
        h, w = frame.shape[:2]
        full_frame_result = self.read_uniform_code(frame, [0, 0, w, h])

        if not person_bboxes:
            return [full_frame_result] if full_frame_result else []

        results = []
        for bbox in person_bboxes:
            result = self.read_uniform_code(frame, bbox)
            if result is None:
                result = full_frame_result
            results.append(result)
        return results

    def _preprocess(self, crop: np.ndarray) -> np.ndarray:
        """
        Preprocess image crop for better OCR accuracy.
        Applies multiple enhancement stages for CCTV quality images.
        """
        # 1. Resize if too small (OCR needs decent resolution)
        h, w = crop.shape[:2]
        if w < 100:
            scale = 100 / w
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        # 2. Convert to grayscale
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # 3. CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 4. Denoise
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10, templateWindowSize=7, searchWindowSize=21)

        # 5. Sharpen
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(denoised, -1, kernel)

        # 6. Sharpened grayscale is usually best for EasyOCR
        return sharpened

    def draw_ocr_result(self, frame: np.ndarray, ocr_result: dict):
        """Draw OCR detection on frame."""
        if not ocr_result:
            return

        x1, y1, x2, y2 = [int(v) for v in ocr_result["bbox"]]
        code = ocr_result["code"]
        conf = ocr_result["confidence"]

        # Cyan color for OCR
        color = (255, 255, 0)  # Cyan BGR
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"ID: {code} ({conf:.0%})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 6, y1), (0, 0, 0), -1)
        cv2.putText(frame, label, (x1 + 3, y1 - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


# Singleton
ocr_engine = OCREngine()
