import hashlib
import secrets

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

KEY_PREFIX = "vdm_"
MAX_KEYS_PER_USER = 5
_HASH_PREFIXES = ("pbkdf2:", "scrypt:", "argon2:")


def _pepper():
    return current_app.config.get("SECRET_KEY", "dev")


def _legacy_hash(raw_key: str) -> str:
    return hashlib.sha256(f"{raw_key}:{_pepper()}".encode()).hexdigest()


def hash_api_key(raw_key: str) -> str:
    return generate_password_hash(raw_key.strip(), method="pbkdf2:sha256:600000")


def _is_modern_hash(stored: str) -> bool:
    return stored.startswith(_HASH_PREFIXES)


def verify_api_key_hash(raw_key: str, stored_hash: str) -> bool:
    if _is_modern_hash(stored_hash):
        return check_password_hash(stored_hash, raw_key.strip())
    return stored_hash == _legacy_hash(raw_key)


def generate_api_key():
    """Return (plaintext, prefix_display, key_hash)."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    prefix = raw[:12] + "…"
    return raw, prefix, hash_api_key(raw)


def verify_api_key(raw_key: str):
    from app.models import UserApiKey

    if not raw_key or not raw_key.startswith(KEY_PREFIX):
        return None

    stripped = raw_key.strip()
    prefix_display = stripped[:12] + "…"
    record = UserApiKey.query.filter_by(
        key_prefix=prefix_display,
        is_active=True,
    ).first()
    if not record or not verify_api_key_hash(stripped, record.key_hash):
        return None

    user = record.user
    if not user.is_active_user or not user.email_verified:
        return None
    return record
