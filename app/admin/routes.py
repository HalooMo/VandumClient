from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import AdminMaintenanceForm, AdminUserForm
from app.models import AccessRequest, Project, SiteSetting, User, utcnow

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@login_required
@admin_required
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    settings = SiteSetting.get_or_create()
    maintenance_form = AdminMaintenanceForm(obj=settings)
    access_requests = (
        AccessRequest.query.order_by(AccessRequest.created_at.desc()).limit(50).all()
    )
    pending_count = AccessRequest.query.filter_by(status="pending").count()
    stats = {
        "total_users": User.query.count(),
        "verified_users": User.query.filter_by(email_verified=True).count(),
        "active_users": User.query.filter_by(is_active_user=True).count(),
        "total_projects": Project.query.count(),
        "done_projects": Project.query.filter_by(status="done").count(),
        "running_projects": Project.query.filter(
            Project.status.in_(["queued", "running", "pending"])
        ).count(),
        "pending_access_requests": pending_count,
    }
    return render_template(
        "admin/index.html",
        users=users,
        stats=stats,
        settings=settings,
        maintenance_form=maintenance_form,
        access_requests=access_requests,
    )


@admin_bp.route("/maintenance", methods=["POST"])
@login_required
@admin_required
def update_maintenance():
    settings = SiteSetting.get_or_create()
    form = AdminMaintenanceForm()
    if form.validate_on_submit():
        settings.maintenance_banner = bool(form.maintenance_banner.data)
        settings.maintenance_message = (form.maintenance_message.data or "").strip()
        db.session.commit()
        if settings.maintenance_banner:
            flash("Предупреждение о доработке включено на сайте.", "success")
        else:
            flash("Предупреждение скрыто — сайт без баннера.", "success")
    else:
        flash("Не удалось сохранить настройки. Проверьте текст сообщения.", "error")
    return redirect(url_for("admin.index"))


@admin_bp.route("/maintenance/hide", methods=["POST"])
@login_required
@admin_required
def hide_maintenance():
    """Resume site for users: hide the maintenance banner and mark pending requests resolved."""
    settings = SiteSetting.get_or_create()
    settings.maintenance_banner = False
    now = utcnow()
    pending = AccessRequest.query.filter_by(status="pending").all()
    for req in pending:
        req.status = "resolved"
        req.resolved_at = now
    db.session.commit()
    flash(
        "Предупреждение скрыто. Ожидающие запросы отмечены как обработанные.",
        "success",
    )
    return redirect(url_for("admin.index"))


@admin_bp.route("/access-requests/<int:req_id>/resolve", methods=["POST"])
@login_required
@admin_required
def resolve_access_request(req_id):
    req = db.session.get(AccessRequest, req_id)
    if not req:
        abort(404)
    req.status = "resolved"
    req.resolved_at = utcnow()
    db.session.commit()
    flash("Запрос отмечен как обработанный.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    form = AdminUserForm(obj=user)

    if form.validate_on_submit():
        user.name = form.name.data
        user.email = form.email.data.lower().strip()
        user.is_admin = form.is_admin.data
        user.is_active_user = form.is_active_user.data
        user.email_verified = form.email_verified.data
        if form.new_password.data:
            user.set_password(form.new_password.data)
        db.session.commit()
        flash("Пользователь обновлён.", "success")
        return redirect(url_for("admin.index"))

    return render_template("admin/edit_user.html", form=form, user=user)


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        flash("Пользователь не найден.", "error")
        return redirect(url_for("admin.index"))

    if user.id == current_user.id:
        flash("Нельзя удалить свой аккаунт.", "error")
        return redirect(url_for("admin.index"))

    db.session.delete(user)
    db.session.commit()
    flash("Пользователь удалён.", "success")
    return redirect(url_for("admin.index"))
