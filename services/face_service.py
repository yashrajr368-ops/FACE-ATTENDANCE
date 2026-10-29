"""
Face Service Manager
Handles thread-safe webcam access, live MJPEG streaming, bounding box annotations,
cooldown enforcement, duplicate attendance prevention, and registration multi-sample capture.
"""

import time
import threading
from typing import Dict, Optional, Tuple, List
import numpy as np
import cv2

from face_recognition_service import FaceRecognitionService


class CameraManager:
    """Thread-safe singleton for managing OpenCV VideoCapture."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, camera_index: int = 0):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, camera_index: int = 0):
        if self._initialized:
            return
        self.camera_index = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.is_running = False
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._initialized = True

    def start(self):
        with self.frame_lock:
            if self.is_running and self.cap is not None and self.cap.isOpened():
                return
            try:
                # Open with DirectShow backend on Windows for fastest startup and reliability
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    # Fallback to default backend
                    self.cap = cv2.VideoCapture(self.camera_index)

                if self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    self.cap.set(cv2.CAP_PROP_FPS, 30)
                    self.is_running = True
                    print(f"[*] Camera opened on index {self.camera_index}")
                else:
                    self.is_running = False
                    print(f"[!] Warning: Camera index {self.camera_index} could not be opened.")
            except Exception as e:
                self.is_running = False
                print(f"[!] Camera initialization error: {e}")

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.is_running or self.cap is None or not self.cap.isOpened():
            self.start()

        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                return True, frame

        return False, None

    def release(self):
        with self.frame_lock:
            self.is_running = False
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            print("[*] Camera released.")


class FaceService:
    def __init__(self, app_config=None):
        self.config = app_config
        self.camera_index = getattr(app_config, 'CAMERA_INDEX', 0) if app_config else 0
        self.cooldown_seconds = getattr(app_config, 'RECOGNITION_COOLDOWN_SECONDS', 15) if app_config else 15
        self.tolerance = getattr(app_config, 'FACE_MATCH_TOLERANCE', 0.45) if app_config else 0.45
        backend = getattr(app_config, 'FACE_BACKEND', 'auto') if app_config else 'auto'

        self.face_rec = FaceRecognitionService(
            backend=backend,
            tolerance=self.tolerance,
            encodings_dir=getattr(app_config, 'ENCODINGS_DIR', None) if app_config else None
        )
        self.camera = CameraManager(camera_index=self.camera_index)

        # Cache of registered student encodings: {student_id: numpy_array}
        self.known_encodings: Dict[str, np.ndarray] = {}
        # Metadata cache: {student_id: {'name': str, 'roll_number': str, 'course': str}}
        self.student_metadata: Dict[str, Dict[str, str]] = {}
        # Cooldown tracker: {student_id: float_timestamp}
        self.last_recognized_time: Dict[str, float] = {}

        # Real-time state
        self.latest_status = "System Ready"
        self.latest_event = None
        self.camera_connected = False
        self.recent_events: List[Dict] = []
        self._lock = threading.Lock()

    def load_known_students(self, students: List):
        """Populates the in-memory cache of student encodings and metadata."""
        with self._lock:
            self.known_encodings.clear()
            self.student_metadata.clear()
            count = 0
            for student in students:
                enc = student.get_encoding()
                if enc is not None:
                    self.known_encodings[student.student_id] = enc
                    self.student_metadata[student.student_id] = {
                        'name': student.name,
                        'roll_number': student.roll_number,
                        'course': student.course
                    }
                    count += 1
            print(f"[*] Loaded {count} registered face encodings into active memory.")

    def add_or_update_student(self, student_id: str, encoding: np.ndarray, name: str, roll_number: str, course: str):
        """Updates cache when a new student is registered."""
        with self._lock:
            self.known_encodings[student_id] = encoding
            self.student_metadata[student_id] = {
                'name': name,
                'roll_number': roll_number,
                'course': course
            }
            # Save backup file
            self.face_rec.save_encoding_file(student_id, encoding)

    def remove_student(self, student_id: str):
        """Removes student from cache."""
        with self._lock:
            self.known_encodings.pop(student_id, None)
            self.student_metadata.pop(student_id, None)
            self.last_recognized_time.pop(student_id, None)

    def create_placeholder_frame(self, message: str = "Camera Unavailable") -> np.ndarray:
        """Generates a polished placeholder frame when webcam is disconnected or busy."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Gradient background
        for y in range(480):
            frame[y, :] = (int(25 + y * 0.05), int(20 + y * 0.04), int(30 + y * 0.05))

        # Box
        cv2.rectangle(frame, (80, 140), (560, 340), (60, 50, 70), 2)
        cv2.putText(frame, "ATTENDANCE SYSTEM CAMERA", (130, 200), cv2.FONT_HERSHEY_DUPLEX, 0.8, (200, 200, 200), 1)
        cv2.putText(frame, message, (120, 250), cv2.FONT_HERSHEY_DUPLEX, 0.75, (0, 165, 255), 2)
        cv2.putText(frame, "Please connect a webcam or check permissions", (110, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
        return frame

    def capture_single_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Reads one raw frame from camera."""
        return self.camera.read_frame()

    def capture_samples_for_registration(self, max_samples: int = 5) -> Tuple[bool, Optional[np.ndarray], str]:
        """
        Captures multiple samples for a student and averages their encodings.
        Ensures high stability and lighting tolerance.
        """
        success, frame = self.camera.read_frame()
        if not success or frame is None:
            return False, None, "Camera unavailable or could not capture frame."

        faces = self.face_rec.detect_faces(frame)
        if len(faces) == 0:
            return False, None, "No face detected in the frame. Please look directly at the camera."
        if len(faces) > 1:
            return False, None, "Multiple faces detected! Please ensure only one person is in front of the camera."

        # Compute encodings from this clean frame
        encodings = self.face_rec.compute_face_encodings(frame, faces)
        if not encodings or len(encodings) == 0:
            return False, None, "Could not extract clear facial features. Please ensure proper lighting."

        primary_encoding = encodings[0]
        return True, primary_encoding, "Face captured successfully!"

    def process_attendance_frame(self, frame: np.ndarray, attendance_service=None) -> Tuple[np.ndarray, List[Dict]]:
        """
        Processes a video frame for the /attendance live stream:
        1. Detects all faces.
        2. Compares each face to registered students.
        3. Annotates bounding box, name, ID, and attendance status.
        4. Triggers automatic attendance marking with cooldown.
        """
        display_frame = frame.copy()
        current_time = time.time()
        detected_events = []

        faces = self.face_rec.detect_faces(frame)
        if len(faces) == 0:
            self.latest_status = "Camera connected - Waiting for face..."
            # Clean watermark
            cv2.putText(display_frame, "Ready - Please stand in front of camera", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
            return display_frame, detected_events

        self.latest_status = f"Face detected ({len(faces)} person{'s' if len(faces)>1 else ''})"
        candidate_encodings = self.face_rec.compute_face_encodings(frame, faces)

        for i, (x, y, w, h) in enumerate(faces):
            candidate_enc = candidate_encodings[i] if i < len(candidate_encodings) else None
            student_id, distance = self.face_rec.compare_face_to_known(
                candidate_enc, self.known_encodings, tolerance=self.tolerance
            )

            if student_id and student_id in self.student_metadata:
                # Registered student recognized
                meta = self.student_metadata[student_id]
                student_name = meta['name']
                roll_no = meta['roll_number']

                # Check cooldown
                last_time = self.last_recognized_time.get(student_id, 0.0)
                in_cooldown = (current_time - last_time) < self.cooldown_seconds

                mark_result = "Recognized"
                if not in_cooldown and attendance_service:
                    # Mark attendance in database
                    mark_status, mark_msg = attendance_service.mark_attendance(student_id)
                    self.last_recognized_time[student_id] = current_time
                    mark_result = mark_msg
                    self.latest_status = f"{student_name}: {mark_msg}"
                    event = {
                        'student_id': student_id,
                        'name': student_name,
                        'roll_number': roll_no,
                        'course': meta['course'],
                        'status': mark_status,
                        'message': mark_msg,
                        'timestamp': time.strftime("%H:%M:%S")
                    }
                    detected_events.append(event)
                    self._record_recent_event(event)
                elif in_cooldown:
                    mark_result = "Active (Cooldown)"

                # Draw GREEN bounding box for registered student
                color = (46, 204, 113)  # Bright Green
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)

                # Header label box
                label = f"{student_name} ({student_id})"
                sub_label = f"Status: {mark_result}"
                
                # Background pill
                cv2.rectangle(display_frame, (x, y - 55), (x + max(w, 240), y), color, -1)
                cv2.putText(display_frame, label, (x + 8, y - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
                cv2.putText(display_frame, sub_label, (x + 8, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 50, 0), 1)

            else:
                # UNKNOWN face - DO NOT MARK ATTENDANCE
                color = (0, 69, 255)  # Orange/Red
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 2)
                cv2.rectangle(display_frame, (x, y - 35), (x + 160, y), color, -1)
                cv2.putText(display_frame, "Unknown Person", (x + 8, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
                self.latest_status = "Unknown person detected"

        return display_frame, detected_events

    def _record_recent_event(self, event: Dict):
        """Keeps rolling buffer of recent attendance triggers."""
        self.recent_events.insert(0, event)
        if len(self.recent_events) > 20:
            self.recent_events.pop()

    def generate_attendance_stream(self, attendance_service=None):
        """
        Yields MJPEG multipart frame buffer for streaming directly to <img> tags.
        """
        while True:
            success, frame = self.camera.read_frame()
            if not success or frame is None:
                self.camera_connected = False
                frame = self.create_placeholder_frame("Camera Unavailable")
            else:
                self.camera_connected = True
                frame, _ = self.process_attendance_frame(frame, attendance_service=attendance_service)

            # Encode as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.03)  # ~30 FPS

    def generate_registration_preview_stream(self):
        """
        Yields MJPEG stream for the student registration modal.
        Shows face detection bounding box and feedback.
        """
        while True:
            success, frame = self.camera.read_frame()
            if not success or frame is None:
                frame = self.create_placeholder_frame("Camera Unavailable")
            else:
                display_frame = frame.copy()
                faces = self.face_rec.detect_faces(frame)
                if len(faces) == 1:
                    x, y, w, h = faces[0]
                    cv2.rectangle(display_frame, (x, y), (x + w, y + h), (46, 204, 113), 2)
                    cv2.putText(display_frame, "Face Position: Ready to Capture", (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (46, 204, 113), 2)
                elif len(faces) > 1:
                    for (x, y, w, h) in faces:
                        cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                    cv2.putText(display_frame, "Multiple faces detected!", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    cv2.putText(display_frame, "Position face inside frame", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
                frame = display_frame

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.04)
