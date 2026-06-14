from flask import Blueprint, flash, redirect, render_template, request, session, url_for, current_app
from flask_login import current_user, login_required

from app.decorators import verified_required
from app.extensions import db, limiter
from app.models import UserApiKey
from app.services.api_keys import MAX_KEYS_PER_USER, generate_api_key

api_portal_bp = Blueprint("api_portal", __name__, url_prefix="/api")


@api_portal_bp.route("/")
@login_required
def index():
    keys = (
        UserApiKey.query.filter_by(user_id=current_user.id)
        .order_by(UserApiKey.created_at.desc())
        .all()
    )
    new_key = session.pop("new_api_key", None)
    return render_template(
        "api/keys.html",
        keys=keys,
        new_key=new_key,
        max_keys=MAX_KEYS_PER_USER,
    )


@api_portal_bp.route("/keys", methods=["POST"])
@login_required
@verified_required
@limiter.limit(
    lambda: current_app.config.get("RATELIMIT_API_KEY_CREATE", "5 per hour"),
    exempt_when=lambda: not current_app.config.get("RATELIMIT_ENABLED", True),
)
def create_key():
    count = UserApiKey.query.filter_by(user_id=current_user.id, is_active=True).count()
    if count >= MAX_KEYS_PER_USER:
        flash(f"Максимум {MAX_KEYS_PER_USER} активных ключей.", "error")
        return redirect(url_for("api_portal.index"))

    name = (request.form.get("name") or "Default").strip()[:64]
    raw, prefix, key_hash = generate_api_key()

    db.session.add(
        UserApiKey(
            user_id=current_user.id,
            name=name,
            key_prefix=prefix,
            key_hash=key_hash,
        )
    )
    db.session.commit()

    session["new_api_key"] = raw
    flash("Ключ создан. Скопируйте его сейчас — больше он не будет показан.", "success")
    return redirect(url_for("api_portal.index"))


@api_portal_bp.route("/keys/<int:key_id>/revoke", methods=["POST"])
@login_required
@verified_required
def revoke_key(key_id):
    record = UserApiKey.query.filter_by(id=key_id, user_id=current_user.id).first_or_404()
    record.is_active = False
    db.session.commit()
    flash("Ключ отозван.", "success")
    return redirect(url_for("api_portal.index"))
