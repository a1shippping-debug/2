import os
from flask import Flask, request, g, render_template
from .config import Config
from .extensions import db, migrate, login_manager, babel, mail
from .blueprints.auth.routes import auth_bp
from .blueprints.admin.routes import admin_bp
from .blueprints.operations.routes import ops_bp
from .blueprints.accounting.routes import acct_bp
from .blueprints.customer.routes import cust_bp

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)

    # init extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        if not user_id:
            return None
        try:
            return User.query.get(int(user_id))
        except (ValueError, TypeError):
            return None
    # i18n
    def select_locale():
        lang = request.args.get("lang") or request.cookies.get("lang")
        if lang in ("ar", "en"):
            return lang
        return request.accept_languages.best_match(["ar", "en"]) or "en"

    babel.init_app(app, locale_selector=select_locale)
    mail.init_app(app)

    # register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(ops_bp, url_prefix="/ops")
    app.register_blueprint(acct_bp, url_prefix="/acct")
    app.register_blueprint(cust_bp, url_prefix="/customer")

    @app.before_request
    def inject_lang_to_g():
        try:
            g.lang_code = select_locale()
        except Exception:
            g.lang_code = "en"

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.shell_context_processor
    def make_shell_context():
        from .models import User, Role, Customer, Vehicle, Auction, Shipment
        return dict(db=db, User=User, Role=Role, Customer=Customer, Vehicle=Vehicle, Auction=Auction, Shipment=Shipment)

    return app
