import os
from flask import Flask
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
    babel.init_app(app)
    mail.init_app(app)

    # register blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(ops_bp, url_prefix="/ops")
    app.register_blueprint(acct_bp, url_prefix="/acct")
    app.register_blueprint(cust_bp, url_prefix="/customer")

    @app.shell_context_processor
    def make_shell_context():
        from .models import User, Role, Customer, Vehicle, Auction, Shipment
        return dict(db=db, User=User, Role=Role, Customer=Customer, Vehicle=Vehicle, Auction=Auction, Shipment=Shipment)

    return app
