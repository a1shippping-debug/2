from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_babel import Babel
from flask_mail import Mail

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
babel = Babel()
mail = Mail()


def init_extensions(app):
    """Initialize core Flask extensions."""
    db.init_app(app)
    migrate.init_app(app, db)
