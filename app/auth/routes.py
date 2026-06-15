from datetime import datetime, timezone

import logging

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, limiter, oauth
from app.forms import LoginForm, RegisterForm
from app.models import User
from app.services.analytics import record_login
from app.services.email import send_verification_email, verify_token
from app.utils.security import dev_verify_code_visible, safe_redirect_target
from app.utils.urls import build_external_url, is_google_oauth_configured

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _limit(rule):
    return limiter.limit(
        rule,
        exempt_when=lambda: not current_app.config.get("RATELIMIT_ENABLED", True),
    )


@auth_bp.route("/login", methods=["GET", "POST"])
@_limit(lambda: current_app.config.get("RATELIMIT_LOGIN", "10 per minute"))
def login():
    if current_user.is_authenticated:
        if not current_user.email_verified:
            return redirect(url_for("auth.verify_pending"))
        return redirect(url_for("main.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.check_password(form.password.data):
            if not user.is_active_user:
                flash("Аккаунт заблокирован. Обратитесь к администратору.", "error")
                return render_template("auth/login.html", form=form)

            login_user(user, remember=form.remember.data)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            record_login(user)

            if not user.email_verified:
                flash("Подтвердите email для доступа к сервису.", "warning")
                return redirect(url_for("auth.verify_pending"))

            next_page = safe_redirect_target(request.args.get("next"))
            return redirect(next_page or url_for("main.index"))

        flash("Неверный email или пароль.", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/register", methods=["GET", "POST"])
@_limit(lambda: current_app.config.get("RATELIMIT_REGISTER", "5 per hour"))
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        if User.query.filter_by(email=email).first():
            flash("Этот email уже зарегистрирован.", "error")
            return render_template("auth/register.html", form=form)

        user = User(email=email, name=form.name.data.strip() or None)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        record_login(user)

        result = send_verification_email(user)
        if result["sent"]:
            flash("Аккаунт создан! Проверьте почту — мы отправили код подтверждения.", "success")
        elif dev_verify_code_visible():
            session["dev_verify_code"] = result["code"]
            session["dev_verify_url"] = result["url"]
            err = result.get("error") or "SMTP недоступен"
            flash(f"Письмо не отправлено ({err}). Код показан на странице подтверждения.", "warning")
        else:
            flash("Аккаунт создан. Проверьте почту для кода подтверждения.", "success")

        return redirect(url_for("auth.verify_pending"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/verify-pending")
@login_required
def verify_pending():
    if current_user.email_verified:
        return redirect(url_for("main.index"))

    dev_code = None
    dev_url = None
    if dev_verify_code_visible():
        dev_code = session.get("dev_verify_code")
        dev_url = session.get("dev_verify_url")

    return render_template(
        "auth/verify_pending.html",
        dev_code=dev_code,
        dev_url=dev_url,
        email=current_user.email,
    )


@auth_bp.route("/verify-code", methods=["POST"])
@login_required
@_limit(lambda: current_app.config.get("RATELIMIT_VERIFY", "5 per minute"))
def verify_code():
    if current_user.email_verified:
        return redirect(url_for("main.index"))

    code = request.form.get("code", "").strip()
    if current_user.verify_code(code):
        db.session.commit()
        session.pop("dev_verify_code", None)
        session.pop("dev_verify_url", None)
        flash("Email подтверждён! Теперь можно создавать проекты.", "success")
        return redirect(url_for("projects.create"))

    flash("Неверный или просроченный код. Запросите новый.", "error")
    return redirect(url_for("auth.verify_pending"))


@auth_bp.route("/verify/<token>")
def verify_email(token):
    user_id = verify_token(token)
    if not user_id:
        flash("Ссылка недействительна или истекла.", "error")
        return redirect(url_for("auth.login"))

    user = db.session.get(User, user_id)
    if not user:
        flash("Пользователь не найден.", "error")
        return redirect(url_for("auth.login"))

    if user.email_verified:
        flash("Email уже подтверждён.", "info")
    else:
        user.email_verified = True
        user.verification_code = None
        user.verification_code_hash = None
        user.verification_code_expires = None
        db.session.commit()
        flash("Email успешно подтверждён! Добро пожаловать в Dpunk.", "success")

    if not current_user.is_authenticated:
        login_user(user)
        record_login(user)

    return redirect(url_for("projects.create"))


@auth_bp.route("/google")
def google_login():
    if not is_google_oauth_configured():
        flash("Google OAuth не настроен. Заполните GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в .env", "error")
        return redirect(url_for("auth.login"))

    redirect_uri = build_external_url("auth.google_callback")
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/google/callback")
def google_callback():
    if not is_google_oauth_configured():
        flash("Google OAuth не настроен.", "error")
        return redirect(url_for("auth.login"))

    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.google.userinfo()

        email = userinfo["email"].lower()
        google_id = userinfo["sub"]

        user = User.query.filter(
            (User.google_id == google_id) | (User.email == email)
        ).first()

        if user:
            if user.google_id and user.google_id != google_id:
                flash("Этот Google-аккаунт не совпадает с привязанным.", "error")
                return redirect(url_for("auth.login"))

            if user.password_hash and not user.google_id and not user.email_verified:
                flash(
                    "Для этого email уже есть регистрация. Подтвердите email или войдите с паролем.",
                    "error",
                )
                return redirect(url_for("auth.login"))

            user.google_id = google_id
            user.email_verified = True
            if userinfo.get("name"):
                user.name = userinfo["name"]
            if userinfo.get("picture"):
                user.avatar_url = userinfo["picture"]
        else:
            user = User(
                email=email,
                name=userinfo.get("name"),
                google_id=google_id,
                email_verified=True,
                avatar_url=userinfo.get("picture"),
            )
            db.session.add(user)

        db.session.commit()
        login_user(user)
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        record_login(user)

        flash(f"Добро пожаловать, {user.display_name}!", "success")
        return redirect(url_for("main.index"))

    except Exception as exc:
        logger.exception("Google OAuth callback failed: %s", exc)
        flash("Ошибка входа через Google. Попробуйте позже.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.pop("dev_verify_code", None)
    session.pop("dev_verify_url", None)
    flash("Вы вышли из аккаунта.", "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/resend-verification")
@login_required
def resend_verification():
    if current_user.email_verified:
        flash("Email уже подтверждён.", "info")
        return redirect(url_for("main.index"))

    result = send_verification_email(current_user)
    if result["sent"]:
        flash("Письмо с кодом отправлено повторно.", "success")
    elif dev_verify_code_visible():
        session["dev_verify_code"] = result["code"]
        session["dev_verify_url"] = result["url"]
        err = result.get("error") or "SMTP недоступен"
        flash(f"Письмо не отправлено ({err}). Код обновлён на странице.", "warning")
    else:
        flash("Не удалось отправить письмо. Попробуйте позже.", "error")

    return redirect(url_for("auth.verify_pending"))
