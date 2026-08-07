from datetime import timedelta

from flask import current_app

from app.extensions import db
from app.models import DubUsage, utcnow


def dub_jobs_last_24h(user_id):
    since = utcnow() - timedelta(days=1)
    return DubUsage.query.filter(
        DubUsage.user_id == user_id,
        DubUsage.created_at >= since,
    ).count()


def dub_quota_remaining(user_id):
    limit = current_app.config.get("MAX_DUB_JOBS_PER_DAY", 20)
    used = dub_jobs_last_24h(user_id)
    return max(0, limit - used), limit


def check_dub_quota(user_id):
    remaining, _ = dub_quota_remaining(user_id)
    return remaining > 0


def record_dub_usage(user_id, source="web"):
    """Record one dub start against the daily quota (web create/restart or API)."""
    db.session.add(DubUsage(user_id=user_id, source=source))
