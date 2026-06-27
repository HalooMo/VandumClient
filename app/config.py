import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
_APP_URL = os.environ.get("APP_URL", "http://localhost:5000")
_PARSED_APP_URL = urlparse(_APP_URL)


def _resolve_database_uri():
    uri = os.environ.get("DATABASE_URL", "").strip()
    if not uri:
        return f"sqlite:///{BASE_DIR / 'dpunk.db'}"
    # Docker hostname "db" is only reachable inside docker-compose network
    if "@db:" in uri and not os.environ.get("DOCKER_CONTAINER"):
        return f"sqlite:///{BASE_DIR / 'dpunk.db'}"
    return uri


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = _resolve_database_uri()

    # Stable external URLs (OAuth, email links)
    APP_URL = _APP_URL.rstrip("/")
    _host = (_PARSED_APP_URL.hostname or "").lower()
    _scheme = (_PARSED_APP_URL.scheme or "http").lower()
    SERVER_NAME = _PARSED_APP_URL.netloc if _host not in ("localhost", "127.0.0.1") else None
    PREFERRED_URL_SCHEME = _scheme or "http"

    _is_secure = _scheme == "https" and _host not in ("localhost", "127.0.0.1")

    # CSRF / sessions
    WTF_CSRF_SSL_STRICT = _is_secure
    SESSION_COOKIE_SECURE = _is_secure
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _is_secure
    REMEMBER_COOKIE_HTTPONLY = True

    # Dev-only: show verification code on screen when SMTP fails
    DEV_SHOW_VERIFY_CODE = os.environ.get("DEV_SHOW_VERIFY_CODE", "").lower() in ("1", "true", "yes")

    # Rate limits (Flask-Limiter)
    RATELIMIT_ENABLED = os.environ.get("RATELIMIT_ENABLED", "true").lower() == "true"
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per hour")
    RATELIMIT_LOGIN = os.environ.get("RATELIMIT_LOGIN", "10 per minute")
    RATELIMIT_REGISTER = os.environ.get("RATELIMIT_REGISTER", "5 per hour")
    RATELIMIT_VERIFY = os.environ.get("RATELIMIT_VERIFY", "5 per minute")
    RATELIMIT_API_DUB = os.environ.get("RATELIMIT_API_DUB", "10 per hour")
    RATELIMIT_API_KEY_CREATE = os.environ.get("RATELIMIT_API_KEY_CREATE", "5 per hour")

    # Daily dub quota per user (web + API proxy)
    MAX_DUB_JOBS_PER_DAY = int(os.environ.get("MAX_DUB_JOBS_PER_DAY", "20"))

    # Admin bootstrap: reset password only when explicitly requested
    ADMIN_RESET_PASSWORD = os.environ.get("ADMIN_RESET_PASSWORD", "").lower() in ("1", "true", "yes")

    # SpeechLab API
    SPEECHLAB_BASE_URL = os.environ.get("SPEECHLAB_BASE_URL", "https://app.vandum.ru").rstrip("/")
    SPEECHLAB_API_KEY = os.environ.get("SPEECHLAB_API_KEY", "")
    SPEECHLAB_MAX_UPLOAD_MB = int(os.environ.get("SPEECHLAB_MAX_UPLOAD_MB", "500"))
    VOICE_SAMPLE_MAX_MB = int(os.environ.get("VOICE_SAMPLE_MAX_MB", "10"))
    MAX_CONTENT_LENGTH = (SPEECHLAB_MAX_UPLOAD_MB + VOICE_SAMPLE_MAX_MB * 2 + 5) * 1024 * 1024

    # Mail
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "Dpunk <noreply@dpunk.online>")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # Bootstrap admin
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@dpunk.online")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    UPLOAD_FOLDER = BASE_DIR / "uploads"
    LANGUAGES = [
        ("auto", "Авто"),
        ("en", "English"),
        ("ru", "Русский"),
        ("de", "Deutsch"),
        ("es", "Español"),
        ("fr", "Français"),
        ("it", "Italiano"),
        ("pt", "Português"),
        ("zh", "中文"),
        ("ja", "日本語"),
        ("ko", "한국어"),
        ("ar", "العربية"),
    ]
