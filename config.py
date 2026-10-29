import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load .env file
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-dev-secret-key-3984718923')
    
    # Instance directory for database
    INSTANCE_DIR = BASE_DIR / 'instance'
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    
    # Database path normalized to POSIX format for SQLite URL cross-platform compatibility
    DB_FILE = (INSTANCE_DIR / 'attendance.db').resolve().as_posix()
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL') or f'sqlite:///{DB_FILE}'
    if SQLALCHEMY_DATABASE_URI.startswith('sqlite:///instance/'):
        # Fix relative path to absolute
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{DB_FILE}'
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Face encodings backup directory
    ENCODINGS_DIR = BASE_DIR / 'data' / 'face_encodings'
    ENCODINGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Camera and Recognition parameters
    CAMERA_INDEX = int(os.getenv('CAMERA_INDEX', '0'))
    FACE_BACKEND = os.getenv('FACE_BACKEND', 'auto')
    FACE_MATCH_TOLERANCE = float(os.getenv('FACE_MATCH_TOLERANCE', '0.48'))
    RECOGNITION_COOLDOWN_SECONDS = int(os.getenv('RECOGNITION_COOLDOWN_SECONDS', '15'))
    
    # Default Admin Credentials
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
