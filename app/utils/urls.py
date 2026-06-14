from flask import current_app, url_for


def build_external_url(endpoint, **values):
    """Build absolute URL using APP_URL (stable for OAuth redirect URIs)."""
    base = current_app.config.get("APP_URL", "http://localhost:5000").rstrip("/")
    path = url_for(endpoint, **values)
    return f"{base}{path}"


def is_google_oauth_configured():
    cid = (current_app.config.get("GOOGLE_CLIENT_ID") or "").strip()
    secret = (current_app.config.get("GOOGLE_CLIENT_SECRET") or "").strip()
    if not cid or not secret:
        return False
    if "your-google" in cid or "your-google" in secret:
        return False
    return True
