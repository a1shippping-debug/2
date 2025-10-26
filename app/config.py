import os
from dotenv import load_dotenv

load_dotenv()


def _default_sqlite_uri() -> str:
    """Build an absolute SQLite URI pointing to instance/cartrade.db.

    Using an absolute path avoids accidental creation of a new DB in the
    current working directory when running CLIs or tests from different CWDs.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))  # /path/to/app
    db_path = os.path.abspath(os.path.join(base_dir, "..", "instance", "cartrade.db"))
    return f"sqlite:///{db_path}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "devkey")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", _default_sqlite_uri())
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Use an absolute path for uploads to avoid CWD-related issues across OSes
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "static", "uploads"
    )
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    # Default site language is Arabic; English is the secondary translation
    BABEL_DEFAULT_LOCALE = os.getenv("BABEL_DEFAULT_LOCALE", "ar")
    # Keep Arabic first to reflect primary UI language
    BABEL_SUPPORTED_LOCALES = os.getenv("BABEL_SUPPORTED_LOCALES", "ar,en").split(",")
    MAIL_SERVER = os.getenv("MAIL_SERVER")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 25) or 25)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    OMR_EXCHANGE_RATE = float(os.getenv("OMR_EXCHANGE_RATE", 0.385))
