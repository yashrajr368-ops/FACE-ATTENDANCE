from datetime import datetime, date, time
from database import db

class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.String(50), 
        db.ForeignKey('students.student_id', ondelete='CASCADE'), 
        nullable=False, 
        index=True
    )
    attendance_date = db.Column(db.Date, nullable=False, default=date.today, index=True)
    attendance_time = db.Column(db.Time, nullable=False, default=lambda: datetime.now().time())
    status = db.Column(db.String(20), nullable=False, default='Present')

    __table_args__ = (
        db.UniqueConstraint('student_id', 'attendance_date', name='uq_student_attendance_date'),
    )

    def to_dict(self):
        student_name = self.student.name if self.student else "Unknown"
        roll_number = self.student.roll_number if self.student else ""
        course = self.student.course if self.student else ""

        return {
            'id': self.id,
            'student_id': self.student_id,
            'student_name': student_name,
            'roll_number': roll_number,
            'course': course,
            'attendance_date': self.attendance_date.strftime('%Y-%m-%d') if self.attendance_date else '',
            'attendance_time': self.attendance_time.strftime('%H:%M:%S') if self.attendance_time else '',
            'status': self.status
        }

    def __repr__(self):
        return f"<Attendance {self.student_id} on {self.attendance_date}: {self.status}>"
