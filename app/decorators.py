from functools import wraps

from flask import abort, flash, redirect, request, url_for
from flask_login import current_user


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def verified_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.url))
        if not current_user.can_use_service():
            flash("Подтвердите email, чтобы создавать проекты дубляжа.", "warning")
            return redirect(url_for("auth.verify_pending"))
        return f(*args, **kwargs)
    return decorated
