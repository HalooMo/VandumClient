from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.decorators import admin_required
from app.extensions import db
from app.forms import AdminUserForm
from app.models import Project, User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@login_required
@admin_required
def index():
    users = User.query.order_by(User.created_at.desc()).all()
    stats = {
        "total_users": User.query.count(),
        "verified_users": User.query.filter_by(email_verified=True).count(),
        "active_users": User.query.filter_by(is_active_user=True).count(),
        "total_projects": Project.query.count(),
        "done_projects": Project.query.filter_by(status="done").count(),
        "running_projects": Project.query.filter(
            Project.status.in_(["queued", "running", "pending"])
        ).count(),
    }
    return render_template("admin/index.html", users=users, stats=stats)


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
