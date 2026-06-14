from flask import Blueprint, current_app, render_template

docs_bp = Blueprint("docs", __name__, url_prefix="/docs")


@docs_bp.route("/")
def index():
    base_url = current_app.config.get("APP_URL", "").rstrip("/") or "http://localhost:5000"
    return render_template("docs/index.html", api_base_url=base_url)
