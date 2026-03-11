import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-fermato-planovani-smen')
    DATABASE = os.environ.get('DATABASE_PATH', os.path.join(BASE_DIR, 'instance', 'planovani_smen.db'))
    EXPORT_DIR = os.path.join(os.path.dirname(DATABASE), 'exports')
    UPLOAD_DIR = os.path.join(os.path.dirname(DATABASE), 'uploads')

    # Email (SMTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', '')
