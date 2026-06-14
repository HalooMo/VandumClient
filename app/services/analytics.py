from datetime import date

from app.extensions import db
from app.models import UserActivity


def record_login(user):
    today = date.today()
    activity = UserActivity.query.filter_by(user_id=user.id, date=today).first()
    if activity:
        activity.login_count += 1
    else:
        activity = UserActivity(user_id=user.id, date=today, login_count=1)
        db.session.add(activity)
    db.session.commit()
