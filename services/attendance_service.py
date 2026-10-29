"""
Attendance Service Module
Manages attendance logging, duplicate prevention, statistics aggregation,
and filtered querying.
"""

from datetime import date, datetime
from typing import Dict, List, Tuple, Optional
from sqlalchemy import func
from database import db
from models.student import Student
from models.attendance import Attendance


class AttendanceService:
    def mark_attendance(self, student_id: str) -> Tuple[str, str]:
        """
        Marks attendance for a student for the current date.
        Returns (status_code, message):
        - ('marked', 'Attendance marked successfully')
        - ('already_marked', 'Already marked today')
        - ('error', 'Student not found')
        """
        today = date.today()
        current_time = datetime.now().time()

        # Check if student exists
        student = Student.query.filter_by(student_id=student_id).first()
        if not student:
            return 'error', 'Student not found'

        # Check for existing record today (enforced by DB unique constraint too)
        existing = Attendance.query.filter_by(
            student_id=student_id,
            attendance_date=today
        ).first()

        if existing:
            return 'already_marked', 'Already marked today'

        try:
            record = Attendance(
                student_id=student_id,
                attendance_date=today,
                attendance_time=current_time,
                status='Present'
            )
            db.session.add(record)
            db.session.commit()
            return 'marked', 'Attendance marked successfully'
        except Exception as e:
            db.session.rollback()
            # In case of race condition caught by unique constraint
            existing = Attendance.query.filter_by(student_id=student_id, attendance_date=today).first()
            if existing:
                return 'already_marked', 'Already marked today'
            return 'error', f'Database error: {str(e)}'

    def get_dashboard_stats(self) -> Dict:
        """
        Calculates high-level metrics for the dashboard:
        - Total Students
        - Present Today
        - Absent Today
        - Attendance Percentage
        """
        today = date.today()
        total_students = Student.query.count()

        present_today = Attendance.query.filter_by(
            attendance_date=today,
            status='Present'
        ).count()

        absent_today = max(0, total_students - present_today)
        rate = round((present_today / total_students * 100), 1) if total_students > 0 else 0.0

        return {
            'total_students': total_students,
            'present_today': present_today,
            'absent_today': absent_today,
            'attendance_rate': rate,
            'today_date': today.strftime('%B %d, %Y')
        }

    def get_recent_attendance(self, limit: int = 10) -> List[Dict]:
        """Returns the most recent attendance records."""
        records = (
            Attendance.query
            .order_by(Attendance.attendance_date.desc(), Attendance.attendance_time.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in records]

    def get_filtered_records(
        self,
        search_query: Optional[str] = None,
        date_filter: Optional[str] = None,
        course_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        page: int = 1,
        per_page: int = 25
    ):
        """
        Queries attendance records with flexible filtering:
        - search_query matches student name, student_id, or roll_number
        - date_filter matches YYYY-MM-DD
        - course_filter matches student course
        - status_filter matches 'Present' / 'Absent'
        """
        query = Attendance.query.join(Student, Attendance.student_id == Student.student_id)

        if search_query:
            q = f"%{search_query.strip()}%"
            query = query.filter(
                (Student.name.ilike(q)) |
                (Student.student_id.ilike(q)) |
                (Student.roll_number.ilike(q))
            )

        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter.strip(), "%Y-%m-%d").date()
                query = query.filter(Attendance.attendance_date == parsed_date)
            except ValueError:
                pass

        if course_filter:
            query = query.filter(Student.course.ilike(f"%{course_filter.strip()}%"))

        if status_filter:
            query = query.filter(Attendance.status.ilike(status_filter.strip()))

        query = query.order_by(Attendance.attendance_date.desc(), Attendance.attendance_time.desc())
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)

        return paginated

    def get_all_courses(self) -> List[str]:
        """Returns list of distinct courses from registered students."""
        results = db.session.query(Student.course).distinct().all()
        return [r[0] for r in results if r[0]]
