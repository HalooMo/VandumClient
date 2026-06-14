from urllib.parse import urlparse

from flask import current_app, request


def is_production():
    env = (current_app.config.get("FLASK_ENV") or "").lower()
    if env == "production":
        return True
    scheme = (current_app.config.get("PREFERRED_URL_SCHEME") or "http").lower()
    host = (urlparse(current_app.config.get("APP_URL", "")).hostname or "").lower()
    return scheme == "https" and host not in ("localhost", "127.0.0.1", "")


def dev_verify_code_visible():
    if current_app.config.get("DEV_SHOW_VERIFY_CODE"):
        return True
    return not is_production()


def safe_redirect_target(next_url):
    """Allow only same-site relative paths (blocks open redirect)."""
    if not next_url:
        return None
    next_url = next_url.strip()
    if not next_url.startswith("/") or next_url.startswith("//"):
        return None
    if "\n" in next_url or "\r" in next_url:
        return None
    return next_url


def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if is_production():
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
