from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required
from sqlalchemy import func

from app.decorators import admin_required
from app.extensions import db
from app.models import Project, User, UserActivity

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
@login_required
@admin_required
def index():
    return render_template("dashboard/index.html")


@dashboard_bp.route("/api/stats")
@login_required
@admin_required
def stats_api():
    period = request.args.get("period", "month")
    return jsonify(_build_stats(period))


def _build_stats(period):
    today = date.today()

    if period == "day":
        start = today - timedelta(days=30)
        group_fmt = "%Y-%m-%d"
        label_fmt = lambda d: d.strftime("%d.%m")
    elif period == "year":
        start = today.replace(month=1, day=1) - timedelta(days=365 * 3)
        group_fmt = "%Y"
        label_fmt = lambda d: d.strftime("%Y")
    else:
        start = today.replace(day=1) - timedelta(days=365)
        group_fmt = "%Y-%m"
        label_fmt = lambda d: d.strftime("%b %Y")

    # User registrations over time
    users = User.query.filter(User.created_at >= datetime.combine(start, datetime.min.time())).all()
    reg_counts = defaultdict(int)
    for u in users:
        key = u.created_at.strftime(group_fmt)
        reg_counts[key] += 1

    # Active users from activity log
    activities = UserActivity.query.filter(UserActivity.date >= start).all()
    active_counts = defaultdict(set)
    for a in activities:
        if period == "day":
            key = a.date.strftime(group_fmt)
        elif period == "year":
            key = a.date.strftime(group_fmt)
        else:
            key = a.date.strftime(group_fmt)
        active_counts[key].add(a.user_id)

    active_user_counts = {k: len(v) for k, v in active_counts.items()}

    # Projects over time
    projects = Project.query.filter(Project.created_at >= datetime.combine(start, datetime.min.time())).all()
    proj_counts = defaultdict(int)
    proj_done = defaultdict(int)
    for p in projects:
        key = p.created_at.strftime(group_fmt)
        proj_counts[key] += 1
        if p.status == "done":
            proj_done[key] += 1

    # Build sorted timeline
    all_keys = sorted(set(reg_counts) | set(active_user_counts) | set(proj_counts))
    if not all_keys:
        all_keys = [today.strftime(group_fmt)]

    labels = []
    for k in all_keys:
        try:
            if period == "day":
                d = datetime.strptime(k, "%Y-%m-%d").date()
            elif period == "year":
                d = datetime.strptime(k, "%Y").date()
            else:
                d = datetime.strptime(k, "%Y-%m").date()
            labels.append(label_fmt(d))
        except ValueError:
            labels.append(k)

    return {
        "labels": labels,
        "keys": all_keys,
        "registrations": [reg_counts.get(k, 0) for k in all_keys],
        "active_users": [active_user_counts.get(k, 0) for k in all_keys],
        "projects": [proj_counts.get(k, 0) for k in all_keys],
        "projects_done": [proj_done.get(k, 0) for k in all_keys],
        "totals": {
            "users": User.query.count(),
            "verified": User.query.filter_by(email_verified=True).count(),
            "projects": Project.query.count(),
            "projects_done": Project.query.filter_by(status="done").count(),
            "projects_running": Project.query.filter(
                Project.status.in_(["queued", "running", "pending"])
            ).count(),
        },
    }
