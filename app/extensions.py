from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
oauth = OAuth()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

login_manager.login_view = "auth.login"
login_manager.login_message = "Войдите для доступа к этой странице."
login_manager.login_message_category = "info"
