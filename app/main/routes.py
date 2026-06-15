from pathlib import Path

from flask import Blueprint, jsonify, render_template, send_from_directory
from flask_login import current_user

from app.models import Project, User
from app.services.speechlab import SpeechLabClient

main_bp = Blueprint("main", __name__)
_SITE_ROOT = Path(__file__).resolve().parent.parent.parent


def _platform_stats():
    return {
        "users": User.query.count(),
        "projects": Project.query.count(),
        "projects_done": Project.query.filter_by(status="done").count(),
        "languages": 12,
    }


def _user_stats():
    if not current_user.is_authenticated:
        return None
    return {
        "my_projects": Project.query.filter_by(user_id=current_user.id).count(),
        "my_done": Project.query.filter_by(user_id=current_user.id, status="done").count(),
    }


def _sanitize_server_status(raw):
    if not raw or raw.get("status") != "ok":
        return {"status": "offline"}
    return {
        "status": "ok",
        "env": raw.get("env"),
        "active_job": raw.get("active_job"),
    }


def _fetch_server_status():
    """Quick upstream ping for homepage — must not block page render."""
    try:
        return _sanitize_server_status(SpeechLabClient().health(timeout=2))
    except Exception:
        return {"status": "offline"}


@main_bp.route("/")
def index():
    return render_template(
        "main/index.html",
        server_status=_fetch_server_status(),
        stats=_platform_stats(),
        user_stats=_user_stats(),
    )


@main_bp.route("/about")
def about():
    return render_template("main/about.html", stats=_platform_stats())


@main_bp.route("/yandex_6c655ab99bbf8d25.html")
def yandex_verification():
    return send_from_directory(_SITE_ROOT, "yandex_6c655ab99bbf8d25.html")


@main_bp.route("/api/public/stats")
def public_stats():
    data = _platform_stats()
    data["server"] = _fetch_server_status()
    return jsonify(data)
