"""
Face Recognition Attendance System - Main Application
Flask Server providing Web Dashboard, Live Webcam Attendance Kiosk,
Biometric Enrollment, Student Management, and CSV/Excel Reporting.
"""

import os
import json
from datetime import date, datetime
from functools import wraps
import numpy as np

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, Response, jsonify, send_file
)

from config import Config
from database import db, init_db
from models.admin import Admin
from models.student import Student
from models.attendance import Attendance
from services.face_service import FaceService
from services.attendance_service import AttendanceService
from services.report_service import ReportService

# Initialize Flask App
app = Flask(__name__)
app.config.from_object(Config)

# Initialize Database
init_db(app)

# Initialize Core Services
face_service = FaceService(app.config)
attendance_service = AttendanceService()
report_service = ReportService()


# Populate in-memory face recognition cache with registered students on startup
def load_registered_faces():
    with app.app_context():
        students = Student.query.all()
        face_service.load_known_students(students)

load_registered_faces()


# --- Authentication Decorator ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_id'):
            flash('Please log in with administrator credentials to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


# --- Auth Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_id'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            flash(f'Welcome back, {admin.username}!', 'success')
            next_url = request.args.get('next')
            return redirect(next_url or url_for('dashboard'))
        else:
            flash('Invalid username or password. Please try again.', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# --- Dashboard ---
@app.route('/')
@login_required
def dashboard():
    stats = attendance_service.get_dashboard_stats()
    recent = attendance_service.get_recent_attendance(limit=8)
    return render_template('dashboard.html', stats=stats, recent_records=recent)


# --- Live Attendance Kiosk ---
@app.route('/attendance')
@login_required
def attendance_kiosk():
    today = date.today()
    today_records = (
        Attendance.query
        .filter_by(attendance_date=today)
        .order_by(Attendance.attendance_time.desc())
        .all()
    )
    return render_template(
        'attendance.html',
        today_records=[r.to_dict() for r in today_records],
        today_str=today.strftime('%B %d, %Y')
    )


# --- Video Streaming Routes ---
@app.route('/video_feed')
@login_required
def video_feed():
    """Live MJPEG video stream with face recognition bounding boxes & labels."""
    return Response(
        face_service.generate_attendance_stream(attendance_service=attendance_service),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/capture_feed')
@login_required
def capture_feed():
    """Live MJPEG stream for student face registration modal."""
    return Response(
        face_service.generate_registration_preview_stream(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# --- Face Capture & Polling APIs ---
@app.route('/api/capture_face', methods=['POST'])
@login_required
def api_capture_face():
    """Captures facial frames from webcam, extracts normalized feature vector."""
    success, encoding, msg = face_service.capture_samples_for_registration()
    if not success or encoding is None:
        return jsonify({'success': False, 'message': msg}), 400

    enc_list = encoding.tolist() if isinstance(encoding, np.ndarray) else list(encoding)
    return jsonify({
        'success': True,
        'message': msg,
        'dimensions': len(enc_list),
        'encoding': enc_list
    })


@app.route('/api/attendance_status')
@login_required
def api_attendance_status():
    """Real-time polling endpoint returning camera state and latest events."""
    return jsonify({
        'camera_connected': face_service.camera_connected,
        'latest_status': face_service.latest_status,
        'recent_events': face_service.recent_events
    })


# --- Student Management ---
@app.route('/register', methods=['GET', 'POST'])
@login_required
def register_student():
    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        roll_number = request.form.get('roll_number', '').strip()
        course = request.form.get('course', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        face_encoding_raw = request.form.get('face_encoding', '')

        # Validations
        if not student_id or not name or not roll_number or not course:
            flash('Please fill in all required fields marked with an asterisk (*).', 'error')
            return redirect(url_for('register_student'))

        existing = Student.query.filter_by(student_id=student_id).first()
        if existing:
            flash(f"Student ID '{student_id}' is already registered in the system.", 'error')
            return redirect(url_for('register_student'))

        encoding_array = None
        if face_encoding_raw:
            try:
                parsed = json.loads(face_encoding_raw)
                encoding_array = np.array(parsed, dtype=np.float32)
            except Exception as e:
                print(f"[!] Encoding parse error: {e}")

        # Create student record
        new_student = Student(
            student_id=student_id,
            name=name,
            roll_number=roll_number,
            course=course,
            email=email if email else None,
            phone=phone if phone else None
        )
        if encoding_array is not None:
            new_student.set_encoding(encoding_array)

        try:
            db.session.add(new_student)
            db.session.commit()

            # Update in-memory face service cache
            if encoding_array is not None:
                face_service.add_or_update_student(
                    student_id=student_id,
                    encoding=encoding_array,
                    name=name,
                    roll_number=roll_number,
                    course=course
                )

            flash(f"Student '{name}' ({student_id}) successfully enrolled with biometrics!", 'success')
            return redirect(url_for('students_list'))
        except Exception as e:
            db.session.rollback()
            flash(f"Database error while saving student: {str(e)}", 'error')
            return redirect(url_for('register_student'))

    return render_template('register_student.html')


@app.route('/students')
@login_required
def students_list():
    search = request.args.get('search', '').strip()
    course = request.args.get('course', '').strip()

    query = Student.query
    if search:
        q = f"%{search}%"
        query = query.filter(
            (Student.name.ilike(q)) |
            (Student.student_id.ilike(q)) |
            (Student.roll_number.ilike(q))
        )
    if course:
        query = query.filter(Student.course.ilike(f"%{course}%"))

    students = query.order_by(Student.name.asc()).all()
    courses = attendance_service.get_all_courses()

    return render_template(
        'students.html',
        students=students,
        courses=courses,
        search_query=search,
        course_filter=course
    )


@app.route('/students/delete/<student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.filter_by(student_id=student_id).first_or_404()
    student_name = student.name
    try:
        db.session.delete(student)
        db.session.commit()
        face_service.remove_student(student_id)
        flash(f"Student '{student_name}' ({student_id}) removed from database.", 'info')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting student: {str(e)}", 'error')

    return redirect(url_for('students_list'))


# --- Attendance Records ---
@app.route('/attendance-records')
@login_required
def attendance_records():
    search = request.args.get('search', '').strip()
    date_val = request.args.get('date', '').strip()
    course = request.args.get('course', '').strip()
    status = request.args.get('status', '').strip()
    page = request.args.get('page', 1, type=int)

    paginated = attendance_service.get_filtered_records(
        search_query=search if search else None,
        date_filter=date_val if date_val else None,
        course_filter=course if course else None,
        status_filter=status if status else None,
        page=page,
        per_page=20
    )

    courses = attendance_service.get_all_courses()

    return render_template(
        'attendance_records.html',
        pagination=paginated,
        courses=courses,
        search_query=search,
        date_filter=date_val,
        course_filter=course,
        status_filter=status
    )


# --- Reports & Exports ---
@app.route('/reports')
@login_required
def reports_view():
    courses = attendance_service.get_all_courses()
    students = Student.query.order_by(Student.name.asc()).all()
    summary = report_service.get_student_summary_report()

    return render_template(
        'reports.html',
        courses=courses,
        students=students,
        summary=summary
    )


@app.route('/reports/export/csv')
@login_required
def export_csv():
    start_date = request.args.get('start_date') or request.args.get('date')
    end_date = request.args.get('end_date')
    student_id = request.args.get('student_id')
    course = request.args.get('course')

    buffer = report_service.generate_csv_report(
        start_date=start_date,
        end_date=end_date,
        student_id=student_id,
        course=course
    )

    filename = f"attendance_report_{date.today().strftime('%Y%m%d')}.csv"
    return send_file(
        buffer,
        mimetype='text/csv; charset=utf-8',
        as_attachment=True,
        download_name=filename
    )


@app.route('/reports/export/excel')
@login_required
def export_excel():
    start_date = request.args.get('start_date') or request.args.get('date')
    end_date = request.args.get('end_date')
    student_id = request.args.get('student_id')
    course = request.args.get('course')

    buffer = report_service.generate_excel_report(
        start_date=start_date,
        end_date=end_date,
        student_id=student_id,
        course=course
    )

    filename = f"attendance_report_{date.today().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buffer,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )


# --- System Settings ---
@app.route('/settings')
@login_required
def settings_view():
    return render_template('settings.html', config=app.config)


@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    try:
        camera_idx = int(request.form.get('camera_index', 0))
        cooldown = int(request.form.get('cooldown_seconds', 15))
        tolerance = float(request.form.get('match_tolerance', 0.45))

        app.config['CAMERA_INDEX'] = camera_idx
        app.config['RECOGNITION_COOLDOWN_SECONDS'] = cooldown
        app.config['FACE_MATCH_TOLERANCE'] = tolerance

        face_service.camera_index = camera_idx
        face_service.cooldown_seconds = cooldown
        face_service.tolerance = tolerance
        face_service.face_rec.tolerance = tolerance

        flash('Hardware and recognition parameters updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating settings: {str(e)}', 'error')

    return redirect(url_for('settings_view'))


@app.route('/settings/change-password', methods=['POST'])
@login_required
def change_password():
    current_pass = request.form.get('current_password', '')
    new_pass = request.form.get('new_password', '')
    confirm_pass = request.form.get('confirm_password', '')

    admin = Admin.query.get(session['admin_id'])
    if not admin or not admin.check_password(current_pass):
        flash('Current password verification failed. Please try again.', 'error')
        return redirect(url_for('settings_view'))

    if new_pass != confirm_pass:
        flash('New password and confirmation do not match.', 'error')
        return redirect(url_for('settings_view'))

    if len(new_pass) < 6:
        flash('New password must be at least 6 characters long.', 'error')
        return redirect(url_for('settings_view'))

    admin.set_password(new_pass)
    db.session.commit()
    flash('Administrator password updated successfully!', 'success')
    return redirect(url_for('settings_view'))


# Application entry point
if __name__ == '__main__':
    print("=" * 65)
    print("  Face Recognition Attendance System")
    print("  Server launching on: http://127.0.0.1:5000")
    print("  Default Admin Login: admin / admin123")
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1')
    app.run(host='0.0.0.0', port=5000, debug=debug_mode, use_reloader=False)
