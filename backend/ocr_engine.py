"""
SIEWS+ 5.0 - OCR Engine for safety uniform code detection.

The engine is tuned for small CCTV crops: it reads torso regions first,
generates several contrast variants, normalizes common OCR mistakes, and
scores candidates before returning a code.
"""
import os
import re
import difflib
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

try:
    import easyocr
    OCR_ENGINE = "easyocr"
    print("[OCR] Using EasyOCR engine")
except ImportError:
    easyocr = None
    OCR_ENGINE = "none"
    print("[OCR] No OCR engine available. Install easyocr: pip install easyocr")


@dataclass
class OCRCandidate:
    code: str
    raw_text: str
    confidence: float
    bbox: List[int]
    score: float
    source: str
    matched_registered: bool = False


class OCREngine:
    """Reads alphanumeric safety codes from detected personnel."""

    PRIORITY_PATTERNS = [
        r"^[A-Z]{1,3}\d{1,5}$",          # P80, ID123, TW2
        r"^[A-Z]{2,4}-\d{2,5}$",         # TW-001, SAFE-01
        r"^[A-Z]{1,4}\d{1,4}[A-Z]?$",    # PPE2A, SAF1
        r"^\d{2,5}[A-Z]{1,3}$",          # 80P, 001TW
    ]
    FALLBACK_PATTERNS = [
        r"^[A-Z]\d{1,3}$",
        r"^\d{3,8}$",
    ]

    ALLOWLIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
    MIN_RAW_CONFIDENCE = 0.20
    MIN_ACCEPT_SCORE = 0.58
    MIN_ACCEPT_CONFIDENCE = 0.28
    REGISTERED_MATCH_RATIO = 0.80

    def __init__(self, languages: Optional[list] = None):
        self._reader = None
        self._languages = languages or ["en"]
        self._initialized = False
        self._debug = os.getenv("OCR_DEBUG", "").lower() in {"1", "true", "yes"}

    def _init_reader(self):
        """Lazy initialization of OCR reader."""
        if self._initialized:
            return
        if OCR_ENGINE != "easyocr":
            return

        try:
            self._reader = easyocr.Reader(self._languages, gpu=False, verbose=False)
            self._initialized = True
            print("[OCR] EasyOCR reader initialized")
        except Exception as e:
            print(f"[OCR] Failed to initialize EasyOCR: {e}")
            self._initialized = False

    def read_uniform_code(self, frame: np.ndarray, person_bbox: list) -> Optional[dict]:
        """Extract the best safety code from one detected person bbox."""
        if not self._ensure_ready():
            return None

        crop_info = self._extract_torso_crop(frame, person_bbox)
        if crop_info is None:
            return None

        crop, offset_x, offset_y, _ = crop_info
        registered_codes = self._registered_codes()
        candidates = self._read_candidates(crop, offset_x, offset_y, registered_codes, source="person")
        best = self._select_best(candidates)
        return self._candidate_to_dict(best) if best else None

    def read_all_codes(self, frame: np.ndarray, person_bboxes: List[list]) -> List[Optional[dict]]:
        """
        Read uniform codes for detected persons.

        Full-frame OCR is intentionally not used as a fallback per person because
        it can assign background text to the wrong worker. If no person is found,
        scan the full frame once.
        """
        if not person_bboxes:
            return self.read_all_codes_multi(frame, full_frame_fallback=True)

        return [self.read_uniform_code(frame, bbox) for bbox in person_bboxes]

    def read_all_codes_multi(
        self,
        frame: np.ndarray,
        person_bboxes: Optional[List[list]] = None,
        full_frame_fallback: bool = False,
    ) -> List[dict]:
        """
        Return all detected codes.

        When person bboxes are supplied, OCR runs only on torso crops. Full-frame
        scanning is opt-in and mainly useful for static test images.
        """
        if not self._ensure_ready():
            return []

        registered_codes = self._registered_codes()
        candidates: List[OCRCandidate] = []

        if person_bboxes:
            for idx, bbox in enumerate(person_bboxes):
                crop_info = self._extract_torso_crop(frame, bbox)
                if crop_info is None:
                    continue
                crop, ox, oy, _ = crop_info
                candidates.extend(
                    self._read_candidates(crop, ox, oy, registered_codes, source=f"person:{idx}")
                )
        elif full_frame_fallback:
            candidates.extend(self._read_candidates(frame, 0, 0, registered_codes, source="full_frame"))

        return [self._candidate_to_dict(c) for c in self._dedupe_candidates(candidates)]

    def _ensure_ready(self) -> bool:
        if OCR_ENGINE == "none":
            return False
        self._init_reader()
        return self._initialized

    def _extract_torso_crop(self, frame: np.ndarray, bbox: Sequence[float]):
        h_frame, w_frame = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_frame, x2), min(h_frame, y2)

        h_person = y2 - y1
        w_person = x2 - x1
        if h_person < 35 or w_person < 20:
            return None

        is_full_frame = x1 <= 2 and y1 <= 2 and x2 >= w_frame - 3 and y2 >= h_frame - 3
        if is_full_frame:
            return frame.copy(), 0, 0, [0, 0, w_frame, h_frame]

        pad_x = max(6, int(w_person * 0.08))
        torso_x1 = max(0, x1 - pad_x)
        torso_x2 = min(w_frame, x2 + pad_x)
        torso_y1 = max(0, y1 + int(h_person * 0.12))
        torso_y2 = min(h_frame, y1 + int(h_person * 0.82))

        crop = frame[torso_y1:torso_y2, torso_x1:torso_x2]
        if crop.size == 0:
            return None
        return crop, torso_x1, torso_y1, [torso_x1, torso_y1, torso_x2, torso_y2]

    def _preprocess_variants(self, crop: np.ndarray) -> List[Tuple[str, np.ndarray]]:
        h, w = crop.shape[:2]
        target_min_w = 240
        target_min_h = 120
        scale = min(3.2, max(1.0, target_min_w / max(w, 1), target_min_h / max(h, 1)))
        if scale > 1.05:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
        denoised = cv2.fastNlMeansDenoising(clahe, h=7, templateWindowSize=7, searchWindowSize=21)

        blur = cv2.GaussianBlur(denoised, (0, 0), 1.0)
        sharp = cv2.addWeighted(denoised, 1.7, blur, -0.7, 0)

        binary = cv2.adaptiveThreshold(
            sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 7
        )
        inv_binary = cv2.bitwise_not(binary)

        return [
            ("sharp", sharp),
            ("binary", binary),
            ("inverse", inv_binary),
        ]

    def _read_candidates(
        self,
        crop: np.ndarray,
        offset_x: int,
        offset_y: int,
        registered_codes: Sequence[str],
        source: str,
    ) -> List[OCRCandidate]:
        candidates: List[OCRCandidate] = []
        scale_x = scale_y = 1.0

        for variant_name, image in self._preprocess_variants(crop):
            scale_y = image.shape[0] / max(crop.shape[0], 1)
            scale_x = image.shape[1] / max(crop.shape[1], 1)
            try:
                results = self._reader.readtext(
                    image,
                    detail=1,
                    paragraph=False,
                    min_size=8,
                    text_threshold=0.42,
                    low_text=0.25,
                    link_threshold=0.25,
                    width_ths=0.85,
                    slope_ths=0.25,
                    ycenter_ths=0.6,
                    decoder="beamsearch",
                    beamWidth=5,
                    contrast_ths=0.1,
                    adjust_contrast=0.7,
                    allowlist=self.ALLOWLIST,
                )
            except Exception as e:
                print(f"[OCR] Read error: {e}")
                continue

            for bbox_ocr, text, conf in results:
                if float(conf) < self.MIN_RAW_CONFIDENCE:
                    continue
                bbox = self._scale_bbox(bbox_ocr, offset_x, offset_y, scale_x, scale_y)
                candidates.extend(
                    self._build_candidates(
                        text=text,
                        conf=float(conf),
                        bbox=bbox,
                        registered_codes=registered_codes,
                        source=f"{source}:{variant_name}",
                    )
                )

        return candidates

    def _build_candidates(
        self,
        text: str,
        conf: float,
        bbox: List[int],
        registered_codes: Sequence[str],
        source: str,
    ) -> List[OCRCandidate]:
        raw = self._clean_text(text)
        if len(raw) < 2:
            return []

        variants = self._normalized_variants(raw)
        built: List[OCRCandidate] = []
        for code in variants:
            if not (2 <= len(code) <= 12):
                continue

            matched_code, ratio = self._best_registered_match(code, registered_codes)
            final_code = matched_code or code
            pattern_score = self._pattern_score(final_code)
            if not matched_code and pattern_score <= 0:
                continue

            score = (conf * 0.62) + (pattern_score * 0.25)
            if matched_code:
                score += 0.25 + (ratio * 0.15)
            if "-" in final_code:
                score += 0.03
            if 3 <= len(final_code) <= 8:
                score += 0.04

            if score < self.MIN_ACCEPT_SCORE and not matched_code:
                continue
            if conf < self.MIN_ACCEPT_CONFIDENCE and not matched_code:
                continue

            if self._debug:
                print(
                    f"[OCR] {raw} -> {final_code} conf={conf:.2f} "
                    f"score={score:.2f} src={source}"
                )

            built.append(
                OCRCandidate(
                    code=final_code,
                    raw_text=raw,
                    confidence=round(conf, 3),
                    bbox=bbox,
                    score=round(score, 3),
                    source=source,
                    matched_registered=bool(matched_code),
                )
            )

        return built

    def _clean_text(self, text: str) -> str:
        cleaned = text.upper().strip()
        cleaned = cleaned.replace(" ", "").replace("_", "-")
        cleaned = re.sub(r"[^A-Z0-9-]", "", cleaned)
        cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
        return cleaned

    def _normalized_variants(self, text: str) -> List[str]:
        variants = [text]

        digit_fix = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8"})
        letter_fix = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})

        variants.append(text.translate(digit_fix))

        first_digit = next((i for i, c in enumerate(text) if c.isdigit()), -1)
        if first_digit > 0:
            prefix = text[:first_digit].translate(letter_fix)
            suffix = text[first_digit:].translate(digit_fix)
            variants.append(prefix + suffix)

        # Common EasyOCR split/merge artifact: P-80 should still match P80.
        if "-" in text:
            variants.append(text.replace("-", ""))

        out = []
        for v in variants:
            if v and v not in out:
                out.append(v)
        return out

    def _pattern_score(self, code: str) -> float:
        if any(re.match(pattern, code) for pattern in self.PRIORITY_PATTERNS):
            return 1.0
        if any(re.match(pattern, code) for pattern in self.FALLBACK_PATTERNS):
            return 0.62
        if any(ch.isalpha() for ch in code) and any(ch.isdigit() for ch in code):
            return 0.45
        return 0.0

    def _best_registered_match(self, code: str, registered_codes: Sequence[str]) -> Tuple[Optional[str], float]:
        best_match = None
        best_ratio = 0.0
        for registered in registered_codes:
            ratio = difflib.SequenceMatcher(None, code, registered).ratio()
            max_len = max(len(code), len(registered))
            close_one_char = max_len >= 3 and self._edit_distance_at_most_one(code, registered)
            if (ratio >= self.REGISTERED_MATCH_RATIO or close_one_char) and ratio > best_ratio:
                best_match = registered
                best_ratio = ratio
        return best_match, best_ratio

    def _registered_codes(self) -> List[str]:
        try:
            from face_manager import face_manager
            codes = []
            for person in face_manager._registered:
                code = self._clean_text(str(person.get("code") or ""))
                if code:
                    codes.append(code)
            return sorted(set(codes))
        except Exception:
            return []

    def _dedupe_candidates(self, candidates: List[OCRCandidate]) -> List[OCRCandidate]:
        best_by_code = {}
        for candidate in candidates:
            current = best_by_code.get(candidate.code)
            if current is None or candidate.score > current.score:
                best_by_code[candidate.code] = candidate
        return sorted(best_by_code.values(), key=lambda c: c.score, reverse=True)

    def _select_best(self, candidates: List[OCRCandidate]) -> Optional[OCRCandidate]:
        deduped = self._dedupe_candidates(candidates)
        return deduped[0] if deduped else None

    def _scale_bbox(self, bbox_ocr, offset_x: int, offset_y: int, scale_x: float, scale_y: float) -> List[int]:
        pts = np.array(bbox_ocr).astype(float)
        xs = pts[:, 0] / max(scale_x, 1e-6)
        ys = pts[:, 1] / max(scale_y, 1e-6)
        return [
            int(offset_x + xs.min()),
            int(offset_y + ys.min()),
            int(offset_x + xs.max()),
            int(offset_y + ys.max()),
        ]

    def _candidate_to_dict(self, candidate: OCRCandidate) -> dict:
        return {
            "code": candidate.code,
            "full_text": candidate.raw_text,
            "confidence": candidate.confidence,
            "score": candidate.score,
            "bbox": candidate.bbox,
            "source": candidate.source,
            "matched_registered": candidate.matched_registered,
        }

    def _edit_distance_at_most_one(self, left: str, right: str) -> bool:
        if abs(len(left) - len(right)) > 1:
            return False
        if left == right:
            return True

        i = j = edits = 0
        while i < len(left) and j < len(right):
            if left[i] == right[j]:
                i += 1
                j += 1
                continue
            edits += 1
            if edits > 1:
                return False
            if len(left) == len(right):
                i += 1
                j += 1
            elif len(left) > len(right):
                i += 1
            else:
                j += 1
        return True

    def draw_ocr_result(self, frame: np.ndarray, ocr_result: dict):
        """Draw OCR detection on frame."""
        if not ocr_result:
            return

        x1, y1, x2, y2 = [int(v) for v in ocr_result["bbox"]]
        code = ocr_result["code"]
        conf = ocr_result["confidence"]

        color = (255, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        label = f"ID: {code} ({conf:.0%})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 6, y1), (0, 0, 0), -1)
        cv2.putText(
            frame, label, (x1 + 3, y1 - 3),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA
        )


ocr_engine = OCREngine()
