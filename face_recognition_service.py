"""
Face Recognition Service Module
Provides high-performance face detection, feature extraction, and identity matching.
Supports:
1. OpenCV-native Spatial LBP + Multi-Scale HOG Feature Embeddings (built-in, zero-dependency, works everywhere on Windows)
2. OpenCV Deep Learning SFace / YuNet (if onnx models are present)
3. dlib / face_recognition library (if installed)
"""

import os
import json
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import numpy as np
import cv2

# Check optional libraries
HAVE_FACE_RECOGNITION = False
try:
    import face_recognition  # type: ignore
    HAVE_FACE_RECOGNITION = True
except ImportError:
    HAVE_FACE_RECOGNITION = False


class FaceRecognitionService:
    def __init__(self, backend: str = "auto", tolerance: float = 0.38, encodings_dir: Optional[Path] = None):
        self.tolerance = tolerance
        self.encodings_dir = Path(encodings_dir) if encodings_dir else Path("data/face_encodings")
        self.encodings_dir.mkdir(parents=True, exist_ok=True)
        
        # Decide backend
        if backend == "auto":
            if HAVE_FACE_RECOGNITION:
                self.backend = "face_recognition"
            else:
                self.backend = "opencv"
        else:
            self.backend = backend
            
        print(f"[*] FaceRecognitionService initialized using backend: '{self.backend}'")

        # Initialize OpenCV Haar Cascades for reliable, offline face detection
        cascade_dir = cv2.data.haarcascades
        self.face_cascade = cv2.CascadeClassifier(os.path.join(cascade_dir, 'haarcascade_frontalface_default.xml'))
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        # Check for optional SFace model
        self.sface = None
        sface_model = Path("data/models/face_recognition_sface_2021dec.onnx")
        if sface_model.exists() and sface_model.stat().st_size > 1000000:
            try:
                self.sface = cv2.FaceRecognizerSF.create(str(sface_model), "")
                print("[*] OpenCV SFace deep-learning recognizer loaded successfully!")
            except Exception as e:
                print(f"[!] Warning: Could not initialize SFace: {e}")

    @staticmethod
    def _compute_lbp(gray_image: np.ndarray) -> np.ndarray:
        """Vectorized 3x3 Local Binary Pattern (LBP) computation."""
        h, w = gray_image.shape
        lbp = np.zeros((h - 2, w - 2), dtype=np.uint8)
        center = gray_image[1:-1, 1:-1]

        neighbors = [
            gray_image[0:-2, 0:-2],  # top-left
            gray_image[0:-2, 1:-1],  # top
            gray_image[0:-2, 2:  ],  # top-right
            gray_image[1:-1, 2:  ],  # right
            gray_image[2:  , 2:  ],  # bottom-right
            gray_image[2:  , 1:-1],  # bottom
            gray_image[2:  , 0:-2],  # bottom-left
            gray_image[1:-1, 0:-2]   # left
        ]
        for bit, n in enumerate(neighbors):
            lbp += ((n >= center).astype(np.uint8) << bit)
        return lbp

    def extract_opencv_embedding(self, face_roi: np.ndarray) -> np.ndarray:
        """
        Extracts a normalized 256-dimensional feature vector using
        Contrast-Normalized Spatial LBP Histograms and Multi-Scale Gradients.
        """
        if len(face_roi.shape) == 3:
            gray = cv2.cvtColor(face_roi, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_roi

        resized = cv2.resize(gray, (128, 128), interpolation=cv2.INTER_AREA)
        norm_gray = self.clahe.apply(resized)

        # 1. 4x4 spatial grid LBP histogram (16 cells x 10 bins = 160 features)
        lbp_map = self._compute_lbp(norm_gray)
        gh, gw = lbp_map.shape[0] // 4, lbp_map.shape[1] // 4

        features = []
        for r in range(4):
            for c in range(4):
                cell = lbp_map[r * gh:(r + 1) * gh, c * gw:(c + 1) * gw]
                hist, _ = np.histogram(cell, bins=10, range=(0, 256))
                features.extend(hist.astype(np.float32))

        # 2. 4x4 spatial grid HOG gradient orientations (16 cells x 6 bins = 96 features)
        gx = cv2.Sobel(norm_gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(norm_gray, cv2.CV_32F, 0, 1, ksize=3)
        mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        ch, cw = 128 // 4, 128 // 4
        for r in range(4):
            for c in range(4):
                c_mag = mag[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
                c_ang = ang[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
                hist, _ = np.histogram(c_ang, bins=6, range=(0, 360), weights=c_mag)
                features.extend(hist.astype(np.float32))

        vec = np.array(features, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 1e-6:
            vec = vec / norm
        return vec

    def detect_faces(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        Detects faces in a BGR frame.
        Returns list of (x, y, w, h) bounding boxes.
        """
        if frame is None or frame.size == 0:
            return []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Haar cascade detection with minNeighbors=5 to suppress false positives
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.15,
            minNeighbors=5,
            minSize=(60, 60),
            flags=cv2.CASCADE_SCALE_IMAGE
        )
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in faces]

    def compute_face_encodings(self, frame: np.ndarray, face_locations: Optional[List[Tuple[int, int, int, int]]] = None) -> List[np.ndarray]:
        """
        Computes facial encodings for all faces in the given frame.
        Returns a list of 1D numpy arrays.
        """
        if frame is None or frame.size == 0:
            return []

        if face_locations is None:
            face_locations = self.detect_faces(frame)

        encodings = []
        if self.backend == "face_recognition" and HAVE_FACE_RECOGNITION:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # convert (x, y, w, h) to (top, right, bottom, left)
            css_locations = [(y, x + w, y + h, x) for (x, y, w, h) in face_locations]
            try:
                encs = face_recognition.face_encodings(rgb_frame, css_locations)
                return [np.array(e, dtype=np.float32) for e in encs]
            except Exception as e:
                print(f"[!] face_recognition error: {e}, falling back to OpenCV")

        # OpenCV Native / SFace
        for (x, y, w, h) in face_locations:
            # Add safe margin around face
            pad_y = int(h * 0.05)
            pad_x = int(w * 0.05)
            y1 = max(0, y - pad_y)
            y2 = min(frame.shape[0], y + h + pad_y)
            x1 = max(0, x - pad_x)
            x2 = min(frame.shape[1], x + w + pad_x)

            face_roi = frame[y1:y2, x1:x2]
            if face_roi.size == 0:
                continue

            enc = self.extract_opencv_embedding(face_roi)
            encodings.append(enc)

        return encodings

    def compare_face_to_known(
        self, 
        candidate_encoding: np.ndarray, 
        known_encodings: Dict[str, np.ndarray], 
        tolerance: Optional[float] = None
    ) -> Tuple[Optional[str], float]:
        """
        Compares candidate encoding against a dictionary of {student_id: encoding_array}.
        Returns (matched_student_id, distance). If no match under tolerance, returns (None, min_distance).
        """
        tol = tolerance if tolerance is not None else self.tolerance
        if not known_encodings or candidate_encoding is None:
            return None, 1.0

        min_dist = float("inf")
        best_match_id = None

        candidate_norm = candidate_encoding / (np.linalg.norm(candidate_encoding) + 1e-8)

        for student_id, known_enc in known_encodings.items():
            if known_enc is None or len(known_enc) != len(candidate_encoding):
                continue

            known_norm = known_enc / (np.linalg.norm(known_enc) + 1e-8)
            # Euclidean distance between normalized vectors
            dist = float(np.linalg.norm(candidate_norm - known_norm))

            if dist < min_dist:
                min_dist = dist
                if dist < tol:
                    best_match_id = student_id

        return best_match_id, min_dist

    def save_encoding_file(self, student_id: str, encoding: np.ndarray):
        """Saves encoding array to JSON file as a backup."""
        file_path = self.encodings_dir / f"{student_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(encoding.tolist(), f)
        except Exception as e:
            print(f"[!] Error saving encoding file: {e}")

    def load_encoding_file(self, student_id: str) -> Optional[np.ndarray]:
        """Loads encoding array from JSON file."""
        file_path = self.encodings_dir / f"{student_id}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return np.array(data, dtype=np.float32)
        except Exception as e:
            print(f"[!] Error loading encoding file: {e}")
            return None
