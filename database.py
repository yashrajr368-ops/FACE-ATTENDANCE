from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def init_db(app):
    """Initialize database and seed default admin account if not already created."""
    db.init_app(app)
    with app.app_context():
        # Import models so SQLAlchemy discovers them before create_all
        from models.admin import Admin
        from models.student import Student
        from models.attendance import Attendance

        db.create_all()

        # Check if default admin exists
        admin_username = app.config.get('ADMIN_USERNAME', 'admin')
        admin_password = app.config.get('ADMIN_PASSWORD', 'admin123')
        
        existing_admin = Admin.query.filter_by(username=admin_username).first()
        if not existing_admin:
            default_admin = Admin(username=admin_username)
            default_admin.set_password(admin_password)
            db.session.add(default_admin)
            db.session.commit()
            print(f"[*] Default admin account initialized: '{admin_username}'")
