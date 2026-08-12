import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from datetime import datetime

from flask_wtf.csrf import CSRFProtect

from app.config import Config
from app.extensions import db, login_manager, mail, migrate, oauth, limiter

csrf = CSRFProtect()
BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config_class=Config):
    load_dotenv()

    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.config.from_object(config_class)
    _refresh_env_config(app)
    _validate_production_secrets(app)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    limiter.enabled = app.config.get("RATELIMIT_ENABLED", True)

    if app.config.get("PREFERRED_URL_SCHEME") == "http":
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

    _init_oauth(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.projects.routes import projects_bp
    from app.admin.routes import admin_bp
    from app.dashboard.routes import dashboard_bp
    from app.api_proxy.routes import api_proxy_bp
    from app.api_portal.routes import api_portal_bp
    from app.docs.routes import docs_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_portal_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(api_proxy_bp)

    csrf.exempt(api_proxy_bp)

    @app.after_request
    def _security_headers(response):
        from app.utils.security import apply_security_headers
        return apply_security_headers(response)

    @app.context_processor
    def inject_globals():
        from app.forms import AccessRequestForm
        from app.models import SiteSetting
        from app.utils.nav import nav_is_active
        from app.utils.security import dev_verify_code_visible
        from app.utils.status import is_active, status_label

        try:
            site_settings = SiteSetting.get_or_create()
        except Exception:
            app.logger.exception("Failed to load site_settings for maintenance banner")
            site_settings = None

        return {
            "now": datetime.now,
            "status_label": status_label,
            "is_active_status": is_active,
            "nav_is_active": nav_is_active,
            "app_url": app.config.get("APP_URL", "").rstrip("/") or "http://localhost:5000",
            "dev_verify_code_visible": dev_verify_code_visible,
            "max_upload_mb": app.config.get("SPEECHLAB_MAX_UPLOAD_MB", 150),
            "site_settings": site_settings,
            "access_request_form": AccessRequestForm(),
        }

    with app.app_context():
        _ensure_schema()
        _bootstrap_admin(app)

    return app


def _validate_production_secrets(app):
    """Refuse weak defaults when running as production."""
    env = (app.config.get("FLASK_ENV") or "").lower()
    if env != "production":
        return

    secret = (app.config.get("SECRET_KEY") or "").strip()
    weak_secrets = {
        "",
        "dev-secret-change-in-production",
        "change-me-to-a-long-random-string",
        "change-me",
    }
    if secret in weak_secrets or len(secret) < 24:
        raise RuntimeError(
            "Production requires a strong SECRET_KEY in .env (min 24 chars, not a placeholder)."
        )

    admin_pw = (app.config.get("ADMIN_PASSWORD") or "").strip()
    if admin_pw in ("", "admin123", "change-me"):
        raise RuntimeError(
            "Production requires a non-default ADMIN_PASSWORD in .env."
        )

    if not (app.config.get("SPEECHLAB_API_KEY") or "").strip():
        app.logger.warning("SPEECHLAB_API_KEY is empty — dubbing will fail")


def _refresh_env_config(app):
    """Apply .env values to app.config (Config class reads env at import time)."""
    env_keys = (
        "SECRET_KEY",
        "SPEECHLAB_BASE_URL",
        "SPEECHLAB_API_KEY",
        "SPEECHLAB_MAX_UPLOAD_MB",
        "MAIL_SERVER",
        "MAIL_PORT",
        "MAIL_USE_TLS",
        "MAIL_USE_SSL",
        "MAIL_USERNAME",
        "MAIL_PASSWORD",
        "MAIL_DEFAULT_SENDER",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "APP_URL",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "FLASK_ENV",
        "DEV_SHOW_VERIFY_CODE",
        "ADMIN_RESET_PASSWORD",
        "MAX_DUB_JOBS_PER_DAY",
        "RATELIMIT_ENABLED",
        "YTDLP_ENABLED",
        "YTDLP_TIMEOUT_SEC",
        "YTDLP_MAX_DURATION_SEC",
        "GPU_POWER_ENABLED",
        "GPU_SERVER_ID",
        "GPU_WAKE_TIMEOUT_SEC",
        "GPU_SHELVE_TIMEOUT_SEC",
        "GPU_IDLE_SEC",
        "GPU_HEALTH_POLL_SEC",
        "GPU_STATUS_POLL_SEC",
        "OS_AUTH_URL",
        "OS_USERNAME",
        "OS_PASSWORD",
        "OS_USER_DOMAIN_NAME",
        "OS_PROJECT_ID",
        "OS_PROJECT_DOMAIN_NAME",
        "OS_REGION_NAME",
        "OS_IDENTITY_API_VERSION",
    )
    for key in env_keys:
        val = os.environ.get(key)
        if val is not None and val != "":
            if key in (
                "MAIL_PORT",
                "SPEECHLAB_MAX_UPLOAD_MB",
                "MAX_DUB_JOBS_PER_DAY",
                "YTDLP_TIMEOUT_SEC",
                "YTDLP_MAX_DURATION_SEC",
                "GPU_WAKE_TIMEOUT_SEC",
                "GPU_SHELVE_TIMEOUT_SEC",
                "GPU_IDLE_SEC",
                "GPU_HEALTH_POLL_SEC",
                "GPU_STATUS_POLL_SEC",
            ):
                app.config[key] = int(val)
            elif key in (
                "MAIL_USE_TLS",
                "MAIL_USE_SSL",
                "RATELIMIT_ENABLED",
                "DEV_SHOW_VERIFY_CODE",
                "ADMIN_RESET_PASSWORD",
                "YTDLP_ENABLED",
                "GPU_POWER_ENABLED",
            ):
                app.config[key] = val.lower() in ("1", "true", "yes")
            else:
                app.config[key] = val

    if app.config.get("SPEECHLAB_API_KEY"):
        app.logger.info("SpeechLab API key loaded (%d chars)", len(app.config["SPEECHLAB_API_KEY"]))
    else:
        app.logger.warning("SPEECHLAB_API_KEY is missing — dubbing will fail with 401")


def _ensure_schema():
    from sqlalchemy import inspect, text

    db.create_all()
    inspector = inspect(db.engine)
    if not inspector.has_table("users"):
        return

    columns = {col["name"] for col in inspector.get_columns("users")}
    with db.engine.begin() as conn:
        if "verification_code" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_code VARCHAR(6)"))
        if "verification_code_expires" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_code_expires DATETIME"))
        if "verification_code_hash" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN verification_code_hash VARCHAR(255)"))

    if inspector.has_table("projects"):
        proj_cols = {col["name"] for col in inspector.get_columns("projects")}
        with db.engine.begin() as conn:
            if "voice_options" not in proj_cols:
                conn.execute(text("ALTER TABLE projects ADD COLUMN voice_options TEXT"))

    if inspector.has_table("user_api_keys"):
        key_cols = {col["name"]: col for col in inspector.get_columns("user_api_keys")}
        col = key_cols.get("key_hash")
        # Widen hash column if still VARCHAR(64) (pbkdf2 hashes are longer)
        if col is not None:
            typ = str(col.get("type") or "").upper()
            if "64" in typ and "255" not in typ:
                dialect = db.engine.dialect.name
                with db.engine.begin() as conn:
                    if dialect == "postgresql":
                        conn.execute(text(
                            "ALTER TABLE user_api_keys ALTER COLUMN key_hash TYPE VARCHAR(255)"
                        ))
                    elif dialect == "sqlite":
                        # SQLite ignores length; recreate not required
                        pass
                    else:
                        try:
                            conn.execute(text(
                                "ALTER TABLE user_api_keys MODIFY key_hash VARCHAR(255)"
                            ))
                        except Exception:
                            pass


def _init_oauth(app):
    oauth.init_app(app)
    cid = (app.config.get("GOOGLE_CLIENT_ID") or "").strip()
    secret = (app.config.get("GOOGLE_CLIENT_SECRET") or "").strip()
    if not cid or not secret or "your-google" in cid:
        return
    oauth.register(
        name="google",
        client_id=cid,
        client_secret=secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _bootstrap_admin(app):
    from app.models import User

    admin_email = app.config.get("ADMIN_EMAIL")
    admin_password = app.config.get("ADMIN_PASSWORD")
    if not admin_email or not admin_password:
        return

    existing = User.query.filter_by(email=admin_email.lower()).first()
    if existing:
        changed = False
        if not existing.is_admin:
            existing.is_admin = True
            changed = True
        if not existing.email_verified:
            existing.email_verified = True
            changed = True
        if app.config.get("ADMIN_RESET_PASSWORD"):
            existing.set_password(admin_password)
            changed = True
        if changed:
            db.session.commit()
        return

    admin = User(
        email=admin_email.lower(),
        name="Administrator",
        is_admin=True,
        email_verified=True,
    )
    admin.set_password(admin_password)
    db.session.add(admin)
    db.session.commit()
