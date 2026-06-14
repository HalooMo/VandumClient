from flask import request

NAV_ACTIVE_MAP = {
    "about": frozenset({"main.about"}),
    "docs": frozenset({"docs.index"}),
    "api": frozenset({"api_portal.index"}),
    "create": frozenset({"projects.create", "projects.edit"}),
    "projects": frozenset({
        "projects.list_projects",
        "projects.detail",
        "projects.download",
        "projects.status_api",
        "projects.status_batch",
    }),
    "dashboard": frozenset({"dashboard.index"}),
    "admin": frozenset({"admin.index", "admin.edit_user"}),
}


def nav_is_active(key):
    endpoint = request.endpoint
    if not endpoint:
        return False
    return endpoint in NAV_ACTIVE_MAP.get(key, frozenset())
