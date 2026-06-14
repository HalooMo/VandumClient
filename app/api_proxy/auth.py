from functools import wraps

from flask import jsonify, request

from app.services.api_keys import verify_api_key


def _extract_api_key():
    header = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        raw = _extract_api_key()
        if not raw:
            return jsonify({"error": "Неверный или отсутствующий API key (X-API-Key)"}), 401

        record = verify_api_key(raw)
        if not record:
            return jsonify({"error": "Неверный или отсутствующий API key (X-API-Key)"}), 401

        from app.extensions import db
        from app.models import utcnow

        record.last_used_at = utcnow()
        db.session.commit()
        return f(record, *args, **kwargs)

    return decorated
