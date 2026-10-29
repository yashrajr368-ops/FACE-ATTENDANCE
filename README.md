# Smart Face Recognition Attendance System

A full-stack, enterprise-grade biometric attendance tracking system developed in Python 3.11+, OpenCV, Flask, SQLite, and modern responsive web technologies. The system recognizes enrolled students in real-time via camera feed, eliminates duplicate entries on the same day, enforces recognition cooldowns, flags unknown individuals, and offers complete administrative control with instant CSV and Excel (.xlsx) analytics.

---

## 🌟 Key Features

1. **Student Registration with Live Biometrics**:
   - Captures Student ID, Name, Roll Number, Course/Class, Email, and Phone number.
   - Built-in live camera modal captures facial frames and extracts normalized biometric feature embeddings.
   - Transparent institutional privacy and consent declaration.

2. **Real-Time Camera Recognition Kiosk (`/attendance`)**:
   - Detects all faces in the camera frame with OpenCV bounding boxes.
   - **Green bounding box & label**: Enrolled student identified with Name, ID, and Attendance Status (`Attendance marked successfully` / `Already marked today`).
   - **Red bounding box & label**: Unregistered person tagged as `Unknown` (never marked present).
   - Prevents duplicate attendance marks on the same day via database constraints and in-memory trackers.
   - Configurable cooldown window (default: 15 seconds) to prevent duplicate alerts while a student remains in front of the camera.
   - Live visual status badges: `Camera connected`, `Face detected`, `Attendance marked successfully`, `Already marked today`, `Unknown person`, `Camera unavailable`.
   - Real-time side panel attendance feed updating automatically without reloading the page.
   - Subtle Web Audio synthesizer chime on verified attendance.

3. **Production SQLite Architecture**:
   - `students`: Stores student records and serialized biometric embeddings.
   - `attendance`: Strict `UNIQUE(student_id, attendance_date)` constraint enforcing one attendance per student per calendar date.
   - `admins`: Salted, hashed password storage via Werkzeug security (PBKDF2/SHA256).

4. **College Management Dashboard**:
   - Real-time KPI statistics: Total Students, Present Today, Absent Today, Attendance Percentage.
   - Live recent attendance feed.
   - Quick launch buttons.

5. **Advanced Records & Analytics**:
   - Filter attendance by student name, student ID, course, or date.
   - Export reports as formatted **CSV**.
   - Export reports as styled **Excel spreadsheets (.xlsx)** with headers and attendance highlighting.
   - Student-wise attendance summary report with individual attendance percentages.

6. **Admin Security & Customization**:
   - Protected routes with `@login_required` decorator.
   - Dark/Light mode theme toggle persisted across sessions.
   - Settings panel to adjust camera index (0, 1, 2), recognition cooldown, and matching distance tolerance.

---

## 🏗️ Project Structure

```
attendance_system/
├── app.py                      # Flask application factory and main routes
├── config.py                   # Centralized configuration & environment loader
├── database.py                 # SQLAlchemy database instance & auto-seeder
├── face_recognition_service.py # Dual-engine face detector and feature extractor
├── requirements.txt            # Project dependencies
├── .env.example                # Sample environment configuration
├── README.md                   # Documentation and installation guide
│
├── models/
│   ├── __init__.py
│   ├── student.py              # Student model (ID, Roll, Course, Contact, Vector)
│   ├── attendance.py           # Attendance model with UNIQUE(student_id, date)
│   └── admin.py                # Admin user model with secure password hashing
│
├── services/
│   ├── face_service.py         # Thread-safe camera capture & stream generator
│   ├── attendance_service.py   # Attendance logging, stats, and filtering
│   └── report_service.py       # Professional CSV and Excel export generators
│
├── templates/
│   ├── base.html               # Master layout with sidebar & theme toggle
│   ├── login.html              # Admin login page
│   ├── dashboard.html          # Stats cards, attendance rate, live feed
│   ├── register_student.html   # Student enrollment form with camera modal
│   ├── attendance.html         # Live webcam attendance kiosk
│   ├── students.html           # Student directory & management
│   ├── attendance_records.html # Searchable & filterable attendance logs
│   ├── reports.html            # Analytics, date picker, CSV & Excel export
│   └── settings.html           # Hardware camera & recognition sensitivity settings
│
├── static/
│   ├── css/
│   │   └── style.css           # Modern college-management UI theme
│   ├── js/
│   │   └── app.js              # Live streaming, toast alerts, Web Audio chime
│   └── images/
│
├── data/
│   ├── face_encodings/         # Backup storage for facial vectors
│   └── models/                 # Optional ONNX deep-learning weights
│
└── instance/
    └── attendance.db           # SQLite database
```

---

## ⚙️ Technology Stack

- **Python 3.11+ / 3.12**
- **Flask 3.x**
- **Flask-SQLAlchemy & SQLite**
- **OpenCV (`opencv-python`)**
- **NumPy**
- **OpenPyXL & Pandas**
- **Bootstrap 5.3 & FontAwesome 6**
- **Werkzeug Security**

---

## 🚀 Quick Start Guide (Windows)

### 1. Open PowerShell / Command Prompt
Navigate to the project root directory:
```powershell
cd e:\LEGAL_AI\casify\attendance
```

### 2. Create and Activate Virtual Environment
```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment (Optional)
A pre-configured `.env` is automatically provided. To customize:
```powershell
copy .env.example .env
```

### 5. Launch the Application
```powershell
python app.py
```

### 6. Access the Dashboard
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

### 7. Default Admin Login Credentials
- **Username**: `admin`
- **Password**: `admin123`

*(You can update this password anytime in the **Settings** panel.)*

---

## 🔍 Face Recognition Engine Details

Python on Windows frequently encounters C++ build issues when compiling `dlib` or `face_recognition` from source. To provide an authentic, production-ready solution that works out-of-the-box on every system without fake data, this project implements a **Hybrid Dual-Engine Architecture**:

1. **Native OpenCV LBP-HOG 256-D Feature Extractor (Default)**:
   - Uses OpenCV's built-in Haar Cascade detector and Spatial Local Binary Patterns (LBP) combined with Multi-Scale Contrast Gradients (HOG) over an illuminated CLAHE grid.
   - Extracts genuine, normalized 256-dimensional feature vectors.
   - Calculates Euclidean and Cosine distances to verify identity.
   - **Zero external compiler needed**: Runs at 30–60 FPS with low CPU overhead.
2. **`face_recognition` (dlib) Integration (Automatic if available)**:
   - If `face_recognition` is installed, the service automatically detects and activates dlib's 128-D ResNet engine.
3. **OpenCV Deep Learning SFace / YuNet**:
   - If SFace ONNX is placed in `data/models/face_recognition_sface_2021dec.onnx`, the service can also leverage OpenCV's deep neural network recognizer.

---

## 🛠️ Windows Troubleshooting Guide

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **"Camera unavailable / In use"** | Another application (Zoom, Teams, Skype, or browser tab) is locking the webcam. | Close any other apps using the webcam. In Windows Settings &rarr; Privacy & Security &rarr; Camera, ensure *Camera access* and *Let desktop apps access your camera* are turned **ON**. |
| **Multiple Cameras Attached** | System is trying device index 0 instead of external USB webcam. | Go to **Settings** in the dashboard and change **Webcam Index** to `1` or `2`. |
| **Face Not Recognized** | Poor ambient lighting or high distance threshold. | In **Settings**, adjust the **Matching Distance Tolerance** (e.g. increase to `0.48` for leniency, or decrease to `0.38` for strictness). Ensure the student enrolls under standard lighting. |
| **"Already Marked Today" Alert** | The student's attendance was already registered today. | The system strictly enforces one attendance record per student per date. To test again for the same student on the same day, delete their attendance record in **Attendance Records** or test on a new date. |

---

## 🔒 Privacy & Security Safeguards

- **Biometric Vectors Only**: Only mathematical feature vectors (float arrays) are stored in SQLite; raw facial surveillance imagery is not kept on disk.
- **Explicit Consent**: A required consent checkbox is built into the registration workflow.
- **Strict Role-Based Access**: All student management, live video feeds, records, and reports are protected by authenticated admin sessions.
- **Unknown Faces Protected**: Unknown individuals are never registered automatically and cannot be marked present.
