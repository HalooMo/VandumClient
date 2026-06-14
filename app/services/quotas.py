from datetime import timedelta

from flask import current_app

from app.models import ApiJob, Project, utcnow


def dub_jobs_last_24h(user_id):
    since = utcnow() - timedelta(days=1)
    api_count = ApiJob.query.filter(
        ApiJob.user_id == user_id,
        ApiJob.created_at >= since,
    ).count()
    web_count = Project.query.filter(
        Project.user_id == user_id,
        Project.created_at >= since,
    ).count()
    return api_count + web_count


def dub_quota_remaining(user_id):
    limit = current_app.config.get("MAX_DUB_JOBS_PER_DAY", 20)
    used = dub_jobs_last_24h(user_id)
    return max(0, limit - used), limit


def check_dub_quota(user_id):
    remaining, _ = dub_quota_remaining(user_id)
    return remaining > 0
