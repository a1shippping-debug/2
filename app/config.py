import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///cartrade.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Use an absolute path for uploads to avoid CWD-related issues across OSes
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static", "uploads"
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    BABEL_DEFAULT_LOCALE = os.getenv("BABEL_DEFAULT_LOCALE", "en")
    BABEL_SUPPORTED_LOCALES = os.getenv("BABEL_SUPPORTED_LOCALES", "en,ar").split(",")
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 25) or 25)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    OMR_EXCHANGE_RATE = float(os.getenv("OMR_EXCHANGE_RATE", 0.385))
