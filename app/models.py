import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255))
    name = db.Column(db.String(120))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_user = db.Column(db.Boolean, default=True, nullable=False)
    email_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_code = db.Column(db.String(6))
    verification_code_hash = db.Column(db.String(255))
    verification_code_expires = db.Column(db.DateTime(timezone=True))
    google_id = db.Column(db.String(255), unique=True, index=True)
    avatar_url = db.Column(db.String(512))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_login = db.Column(db.DateTime(timezone=True))

    projects = db.relationship("Project", backref="owner", lazy="dynamic", cascade="all, delete-orphan")
    api_keys = db.relationship("UserApiKey", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    api_jobs = db.relationship("ApiJob", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def issue_verification_code(self):
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        self.verification_code_hash = generate_password_hash(code, method="pbkdf2:sha256")
        self.verification_code = None
        self.verification_code_expires = utcnow() + timedelta(hours=24)
        return code

    def verify_code(self, code):
        if not code:
            return False
        code = code.strip()

        if self.verification_code_hash:
            if not check_password_hash(self.verification_code_hash, code):
                return False
        elif self.verification_code:
            if self.verification_code != code:
                return False
        else:
            return False

        if self.verification_code_expires:
            expires = self.verification_code_expires
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < utcnow():
                return False
        self.email_verified = True
        self.verification_code = None
        self.verification_code_hash = None
        self.verification_code_expires = None
        return True

    @property
    def display_name(self):
        return self.name or self.email.split("@")[0]

    def can_use_service(self):
        return self.is_active_user and self.email_verified


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    project_name = db.Column(db.String(64), nullable=False)
    job_id = db.Column(db.String(64), index=True)
    source_language = db.Column(db.String(16), nullable=False)
    target_language = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)
    error_message = db.Column(db.Text)
    voice_gender = db.Column(db.String(16))
    voice_age = db.Column(db.Integer)
    voice_prompt = db.Column(db.Text)
    voice_options = db.Column(db.Text)
    original_filename = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        db.UniqueConstraint("user_id", "project_name", name="uq_user_project"),
    )


class UserActivity(db.Model):
    """Track daily active users for dashboard analytics."""
    __tablename__ = "user_activity"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    login_count = db.Column(db.Integer, default=1, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", name="uq_user_activity_date"),
    )


class UserApiKey(db.Model):
    __tablename__ = "user_api_keys"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False, default="Default")
    key_prefix = db.Column(db.String(20), nullable=False)
    key_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_used_at = db.Column(db.DateTime(timezone=True))

    jobs = db.relationship("ApiJob", backref="api_key", lazy="dynamic")


class ApiJob(db.Model):
    """Tracks upstream SpeechLab jobs created via user API keys."""
    __tablename__ = "api_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey("user_api_keys.id"), index=True)
    job_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    project_name = db.Column(db.String(64), nullable=False)
    source_language = db.Column(db.String(16))
    target_language = db.Column(db.String(16))
    status = db.Column(db.String(32), default="queued", nullable=False)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = db.Column(db.DateTime(timezone=True))
