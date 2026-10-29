import json
import numpy as np
from datetime import datetime
from database import db

class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(50), nullable=False, index=True)
    course = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    face_encoding = db.Column(db.Text, nullable=True)  # JSON-encoded float array
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to attendance records
    attendances = db.relationship(
        'Attendance', 
        backref='student', 
        cascade='all, delete-orphan', 
        lazy=True,
        foreign_keys='Attendance.student_id'
    )

    def set_encoding(self, encoding_array):
        """Serialize numpy array or list of floats to JSON."""
        if encoding_array is None:
            self.face_encoding = None
            return
        if isinstance(encoding_array, np.ndarray):
            encoding_array = encoding_array.tolist()
        self.face_encoding = json.dumps(encoding_array)

    def get_encoding(self):
        """Deserialize JSON string into numpy float array."""
        if not self.face_encoding:
            return None
        try:
            arr = json.loads(self.face_encoding)
            return np.array(arr, dtype=np.float32)
        except Exception:
            return None

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'name': self.name,
            'roll_number': self.roll_number,
            'course': self.course,
            'email': self.email or '',
            'phone': self.phone or '',
            'has_face': bool(self.face_encoding),
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else ''
        }

    def __repr__(self):
        return f"<Student {self.student_id} - {self.name}>"
