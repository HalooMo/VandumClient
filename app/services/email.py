import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app
from flask_mail import Message

from app.extensions import db, mail

logger = logging.getLogger(__name__)

PLACEHOLDER_MARKERS = ("your@", "your-app-password", "change-me", "example.com")


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def is_mail_configured():
    username = (current_app.config.get("MAIL_USERNAME") or "").strip()
    password = (current_app.config.get("MAIL_PASSWORD") or "").strip()
    if not username or not password:
        return False
    combined = f"{username}:{password}".lower()
    return not any(marker in combined for marker in PLACEHOLDER_MARKERS)


def build_verify_url(user_id):
    token = _serializer().dumps({"user_id": user_id}, salt="email-verify")
    base = current_app.config.get("APP_URL", "http://localhost:5000").rstrip("/")
    return f"{base}/auth/verify/{token}"


def generate_verification_token(user_id):
    return _serializer().dumps({"user_id": user_id}, salt="email-verify")


def verify_token(token, max_age=86400):
    try:
        data = _serializer().loads(token, salt="email-verify", max_age=max_age)
        return data.get("user_id")
    except (BadSignature, SignatureExpired):
        return None


def _send_via_smtplib(recipient, subject, body, html):
    cfg = current_app.config
    host = cfg["MAIL_SERVER"]
    port = cfg["MAIL_PORT"]
    username = cfg["MAIL_USERNAME"]
    password = cfg["MAIL_PASSWORD"]
    sender = cfg["MAIL_DEFAULT_SENDER"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    if cfg.get("MAIL_USE_SSL"):
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(username, password)
            server.sendmail(sender, [recipient], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            if cfg.get("MAIL_USE_TLS"):
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.sendmail(sender, [recipient], msg.as_string())


def _try_send_email(recipient, subject, body, html):
    errors = []

    if is_mail_configured():
        try:
            msg = Message(subject=subject, recipients=[recipient])
            msg.body = body
            msg.html = html
            mail.send(msg)
            return True, None
        except Exception as exc:
            errors.append(f"Flask-Mail: {exc}")
            logger.warning("Flask-Mail failed for %s: %s", recipient, exc)

        try:
            _send_via_smtplib(recipient, subject, body, html)
            return True, None
        except Exception as exc:
            errors.append(f"SMTP: {exc}")
            logger.warning("SMTP fallback failed for %s: %s", recipient, exc)

    return False, "; ".join(errors) if errors else "SMTP не настроен"


def send_verification_email(user):
    """Send verification email. Returns dict with sent/code/url/error."""
    code = user.issue_verification_code()
    db.session.commit()

    verify_url = build_verify_url(user.id)
    result = {"sent": False, "code": code, "url": verify_url, "error": None}

    body = f"""Здравствуйте, {user.display_name}!

Добро пожаловать в Vandum — платформу AI-дубляжа.

Код подтверждения: {code}

Или перейдите по ссылке:
{verify_url}

Код и ссылка действительны 24 часа.

— Команда Vandum
"""
    html = f"""
    <div style="font-family: 'Segoe UI', sans-serif; max-width: 520px; margin: 0 auto; padding: 40px 20px;">
        <h2 style="color: #00f0ff; margin-bottom: 8px;">Vandum</h2>
        <p style="color: #ccc;">Здравствуйте, <strong>{user.display_name}</strong>!</p>
        <p style="color: #aaa;">Код подтверждения:</p>
        <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #00f0ff;">{code}</p>
        <a href="{verify_url}" style="display: inline-block; margin: 24px 0; padding: 14px 32px;
           background: linear-gradient(135deg, #00f0ff, #7b2ff7); color: #000; text-decoration: none;
           border-radius: 8px; font-weight: 600;">Подтвердить аккаунт</a>
        <p style="color: #666; font-size: 13px;">Код и ссылка действительны 24 часа.</p>
    </div>
    """

    sent, error = _try_send_email(user.email, "Подтвердите аккаунт Vandum", body, html)
    result["sent"] = sent
    result["error"] = error

    if sent:
        logger.info("Verification email sent to %s", user.email)
    else:
        logger.info("Verification for %s — code: %s (mail error: %s)", user.email, code, error)

    return result
