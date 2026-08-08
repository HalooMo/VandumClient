from pathlib import Path
from datetime import timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user

from app.extensions import db, limiter
from app.forms import AccessRequestForm
from app.models import AccessRequest, Project, SiteSetting, User, utcnow
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


@main_bp.route("/access-request", methods=["POST"])
@limiter.limit("5 per hour")
def access_request():
    settings = SiteSetting.get_or_create()
    if not settings.maintenance_banner:
        flash("Сейчас предупреждение о доработке скрыто — сайт доступен.", "info")
        return redirect(request.referrer or url_for("main.index"))

    form = AccessRequestForm()
    if not form.validate_on_submit():
        flash("Не удалось отправить запрос. Проверьте email.", "error")
        return redirect(request.referrer or url_for("main.index"))

    if current_user.is_authenticated:
        email = (current_user.email or "").strip().lower()
        name = current_user.display_name
        user_id = current_user.id
    else:
        email = (form.email.data or "").strip().lower()
        name = None
        user_id = None
        if not email:
            flash("Укажите email для запроса на использование.", "error")
            return redirect(request.referrer or url_for("main.index"))

    since = utcnow() - timedelta(hours=1)
    recent = AccessRequest.query.filter(
        AccessRequest.email == email,
        AccessRequest.created_at >= since,
        AccessRequest.status == "pending",
    ).first()
    if recent:
        flash("Запрос уже отправлен. Обычно мы отвечаем в течение 20 минут.", "info")
        return redirect(request.referrer or url_for("main.index"))

    row = AccessRequest(
        user_id=user_id,
        email=email,
        name=name,
        note=(form.note.data or "").strip() or None,
        status="pending",
    )
    db.session.add(row)
    db.session.commit()
    flash(
        "Запрос отправлен. В течение 20 минут мы постараемся возобновить работу сервера.",
        "success",
    )
    return redirect(request.referrer or url_for("main.index"))
