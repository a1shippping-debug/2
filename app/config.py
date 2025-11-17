import os
from dotenv import load_dotenv

load_dotenv()


def _database_url() -> str:
    raw_url = os.getenv("DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError("DATABASE_URL must be set to connect to PostgreSQL.")
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)
    return raw_url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 50 * 1024 * 1024))
    # Default site language is Arabic; English is the secondary translation
    BABEL_DEFAULT_LOCALE = os.getenv("BABEL_DEFAULT_LOCALE", "ar")
    # Keep Arabic first to reflect primary UI language
    BABEL_SUPPORTED_LOCALES = os.getenv("BABEL_SUPPORTED_LOCALES", "ar,en").split(",")
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 25) or 25)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    OMR_EXCHANGE_RATE = float(os.getenv("OMR_EXCHANGE_RATE", 0.385))
    B2_BUCKET_NAME = os.getenv("B2_BUCKET_NAME")
    B2_ENDPOINT = os.getenv("B2_ENDPOINT")
    B2_KEY_ID = os.getenv("B2_KEY_ID")
    B2_APPLICATION_KEY = os.getenv("B2_APPLICATION_KEY")
    B2_PUBLIC_URL = os.getenv("B2_PUBLIC_URL")
