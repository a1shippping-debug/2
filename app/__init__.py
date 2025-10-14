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
    # Try to auto-apply pending migrations at startup to avoid schema/runtime mismatches
    try:
        from flask_migrate import upgrade as _alembic_upgrade
        with app.app_context():
            _alembic_upgrade()
    except Exception:
        # If migrations aren't set up or upgrade fails, continue; save handlers will surface errors
        pass
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
        supported = app.config.get("BABEL_SUPPORTED_LOCALES", ["en", "ar"]) or ["en", "ar"]
        # normalize & strip
        lang = (request.args.get("lang") or request.cookies.get("lang") or "").strip()
        if lang in supported:
            return lang
        return request.accept_languages.best_match(supported) or app.config.get("BABEL_DEFAULT_LOCALE", "en")

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

    @app.after_request
    def persist_lang_cookie(response):
        try:
            supported = app.config.get("BABEL_SUPPORTED_LOCALES", ["en", "ar"]) or ["en", "ar"]
            requested_language = (request.args.get("lang") or "").strip()
            if requested_language in supported:
                response.set_cookie(
                    "lang",
                    requested_language,
                    max_age=60 * 60 * 24 * 365,
                    samesite="Lax",
                )
        except Exception:
            pass
        # Always ensure UTF-8 for HTML responses to avoid mojibake
        try:
            content_type_header = response.headers.get("Content-Type", "")
            if content_type_header.startswith("text/html"):
                response.headers["Content-Type"] = "text/html; charset=utf-8"
        except Exception:
            pass
        return response

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.route("/")
    def index():
        return render_template("landing.html")

    @app.route("/tracking/<string:vin>")
    def tracking_page(vin: str):
        """Public vehicle shipment tracking by VIN.

        Renders a Bootstrap-based horizontal 12-stage timeline with icons and
        green/red status indicators. Data is derived from DB where available
        and otherwise simulated for demonstration.
        """
        from datetime import datetime, timedelta
        from .extensions import db
        from .models import Vehicle, Auction, Shipment, VehicleShipment

        vin_norm = (vin or "").strip()

        vehicle = (
            db.session.query(Vehicle)
            .join(Auction, Vehicle.auction_id == Auction.id, isouter=True)
            .filter(db.func.lower(Vehicle.vin) == db.func.lower(vin_norm))
            .first()
        )

        stages = []
        stage_details = {}
        lot_number = "-"

        if vehicle:
            lot_number = vehicle.auction.lot_number if vehicle.auction and vehicle.auction.lot_number else "-"

            shipments = (
                db.session.query(Shipment)
                .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
                .filter(VehicleShipment.vehicle_id == vehicle.id)
                .order_by(Shipment.created_at.asc())
                .all()
            )
            primary_shipment = shipments[0] if shipments else None

            departed = bool(primary_shipment and primary_shipment.departure_date)
            arrived = bool(primary_shipment and primary_shipment.arrival_date)
            shipment_status = (primary_shipment.status or "").strip().lower() if primary_shipment else ""
            shipment_delivered = shipment_status == "delivered"

            norm_status = (vehicle.status or "").strip().lower()

            def fmt_dt(dt):
                try:
                    return dt.strftime("%d-%m-%Y") if dt else ""
                except Exception:
                    return ""

            completed_map = {
                "New car": True,
                # Consider explicit status names as authoritative fallbacks
                "Cashier Payment": bool(vehicle.purchase_price_usd and float(vehicle.purchase_price_usd) > 0)
                or norm_status == "cashier payment",
                "Auction Payment": bool(vehicle.purchase_date) or norm_status == "auction payment",
                # Consider vehicle status for posting/shipping lifecycle too
                "Posted": bool(shipments)
                or norm_status in {"in shipping", "shipped", "delivered", "arrived", "in transit"}
                or norm_status == "posted",
                "Towing": any(k in norm_status for k in ["picked", "towing", "tow"]) or norm_status == "towing",
                # Treat customs-cleared/warehouse statuses as Warehouse stage
                "Warehouse": ("warehouse" in norm_status) or ("cleared" in norm_status) or norm_status == "warehouse",
                # If shipments exist and not yet departed -> Loading; otherwise, explicit status or shipped/in shipping implies
                "Loading": bool(shipments and not departed)
                or ("shipped" in norm_status)
                or ("in shipping" in norm_status)
                or norm_status == "loading",
                # Shipping-related stages can also be driven by explicit status
                "Shipping": bool(departed)
                or ("shipped" in norm_status)
                or ("in shipping" in norm_status)
                or norm_status == "shipping",
                "Port": bool(departed) or ("shipped" in norm_status) or ("in shipping" in norm_status) or norm_status == "port",
                # In transit can mark On way even if arrival not yet known
                "On way": bool(departed and not arrived) or ("in transit" in norm_status) or norm_status == "on way",
                # Mark Arrived if either shipment arrived or vehicle status says arrived
                "Arrived": bool(arrived) or ("arrived" in norm_status) or norm_status == "arrived",
                # Delivered from shipment state or vehicle status
                "Delivered": bool(shipment_delivered or "delivered" in norm_status or norm_status == "delivered"),
            }

            date_map = {
                "New car": fmt_dt(vehicle.created_at),
                "Cashier Payment": fmt_dt(vehicle.purchase_date) or fmt_dt(vehicle.created_at),
                "Auction Payment": fmt_dt(vehicle.purchase_date),
                "Posted": fmt_dt(vehicle.created_at),
                "Towing": "",
                "Warehouse": "",
                "Loading": fmt_dt(primary_shipment.departure_date - timedelta(days=1)) if departed and primary_shipment else "",
                "Shipping": fmt_dt(primary_shipment.departure_date) if primary_shipment else "",
                "Port": fmt_dt(primary_shipment.departure_date) if primary_shipment else "",
                "On way": fmt_dt(primary_shipment.departure_date) if primary_shipment else "",
                "Arrived": fmt_dt(primary_shipment.arrival_date) if primary_shipment else "",
                "Delivered": fmt_dt(primary_shipment.arrival_date) if primary_shipment else "",
            }

            # Build per-stage details using available data
            def clean_str(value):
                try:
                    s = str(value).strip()
                    return s if s else "-"
                except Exception:
                    return "-"

            def add_details(name: str, fields: list[tuple[str, str]]):
                stage_details[name] = [
                    {"label": lbl, "value": val if (val and str(val).strip()) else "-"}
                    for (lbl, val) in fields
                ]

            # Common references
            auction = vehicle.auction if vehicle else None

            # Details per stage
            add_details(
                "New car",
                [
                    ("Created", date_map.get("New car", "-")),
                    ("Status", clean_str(vehicle.status if vehicle else "")),
                    ("Lot #", clean_str(lot_number)),
                    ("Location", clean_str(vehicle.current_location if vehicle else "")),
                ],
            )

            add_details(
                "Cashier Payment",
                [
                    ("Amount (USD)", clean_str(vehicle.purchase_price_usd if vehicle else "")),
                    ("Date", date_map.get("Cashier Payment", "-")),
                ],
            )

            add_details(
                "Auction Payment",
                [
                    ("Paid On", date_map.get("Auction Payment", "-")),
                    ("Auction Provider", clean_str(auction.provider if auction else "")),
                    ("Lot #", clean_str(lot_number)),
                ],
            )

            add_details(
                "Posted",
                [
                    ("Auction", clean_str(auction.provider if auction else "")),
                    ("Auction Date", clean_str(fmt_dt(auction.auction_date) if auction else "")),
                    ("Location", clean_str(auction.location if auction else "")),
                    ("Lot #", clean_str(lot_number)),
                    ("Auction URL", clean_str(auction.auction_url if auction else "")),
                ],
            )

            add_details(
                "Towing",
                [
                    ("Current Status", clean_str(norm_status)),
                    ("Location", clean_str(vehicle.current_location if vehicle else "")),
                ],
            )

            add_details(
                "Warehouse",
                [
                    ("Location", clean_str(vehicle.current_location if vehicle else "")),
                    ("Status", clean_str(norm_status)),
                ],
            )

            add_details(
                "Loading",
                [
                    ("Planned Load Date", date_map.get("Loading", "-")),
                    ("Shipment #", clean_str(primary_shipment.shipment_number if primary_shipment else "")),
                    ("Shipping Company", clean_str(primary_shipment.shipping_company if primary_shipment else "")),
                    ("Container #", clean_str(primary_shipment.container_number if primary_shipment else "")),
                ],
            )

            add_details(
                "Shipping",
                [
                    ("Shipment #", clean_str(primary_shipment.shipment_number if primary_shipment else "")),
                    ("Origin Port", clean_str(primary_shipment.origin_port if primary_shipment else "")),
                    ("Destination Port", clean_str(primary_shipment.destination_port if primary_shipment else "")),
                    ("Departure", date_map.get("Shipping", "-")),
                    ("Arrival", date_map.get("Arrived", "-")),
                    ("Status", clean_str(primary_shipment.status if primary_shipment else "")),
                ],
            )

            add_details(
                "Port",
                [
                    ("Processed At", clean_str(primary_shipment.origin_port if primary_shipment else "")),
                    ("Departure", date_map.get("Shipping", "-")),
                    ("Shipment #", clean_str(primary_shipment.shipment_number if primary_shipment else "")),
                ],
            )

            add_details(
                "On way",
                [
                    ("From", clean_str(primary_shipment.origin_port if primary_shipment else "")),
                    ("To", clean_str(primary_shipment.destination_port if primary_shipment else "")),
                    ("Departure", date_map.get("Shipping", "-")),
                    ("ETA", date_map.get("Arrived", "-")),
                    ("Status", clean_str(primary_shipment.status if primary_shipment else "")),
                ],
            )

            add_details(
                "Arrived",
                [
                    ("Arrival", date_map.get("Arrived", "-")),
                    ("Destination Port", clean_str(primary_shipment.destination_port if primary_shipment else "")),
                    ("Shipment #", clean_str(primary_shipment.shipment_number if primary_shipment else "")),
                ],
            )

            add_details(
                "Delivered",
                [
                    ("Delivered On", date_map.get("Delivered", "-")),
                    ("Final Status", "Delivered" if completed_map.get("Delivered") else clean_str(norm_status)),
                ],
            )
        else:
            # Simulated example data when VIN is not found
            base = datetime.utcnow() - timedelta(days=15)
            lot_number = "-"
            completed_map, date_map = {}, {}
            sim_names = [
                "New car",
                "Cashier Payment",
                "Auction Payment",
                "Posted",
                "Towing",
                "Warehouse",
                "Loading",
                "Shipping",
                "Port",
                "On way",
                "Arrived",
                "Delivered",
            ]
            for idx, nm in enumerate(sim_names):
                completed_map[nm] = idx < 7  # first 7 steps completed in demo
                date_map[nm] = (base + timedelta(days=idx)).strftime("%d-%m-%Y") if completed_map[nm] else ""
            vehicle = None

            # Generic simulated details
            for nm in sim_names:
                stage_details[nm] = [
                    {"label": "Date", "value": date_map.get(nm, "-") or "-"},
                    {"label": "Info", "value": "Demo data"},
                ]

        icons = {
            "New car": "fa-car-side",
            "Cashier Payment": "fa-money-bill-wave",
            "Auction Payment": "fa-gavel",
            "Posted": "fa-bullhorn",
            "Towing": "fa-truck-pickup",
            "Warehouse": "fa-warehouse",
            "Loading": "fa-box-open",
            "Shipping": "fa-ship",
            "Port": "fa-anchor",
            "On way": "fa-route",
            "Arrived": "fa-flag-checkered",
            "Delivered": "fa-circle-check",
        }

        order = [
            "New car",
            "Cashier Payment",
            "Auction Payment",
            "Posted",
            "Towing",
            "Warehouse",
            "Loading",
            "Shipping",
            "Port",
            "On way",
            "Arrived",
            "Delivered",
        ]
        for name in order:
            stages.append(
                {
                    "name": name,
                    "icon": icons.get(name, "fa-circle"),
                    "completed": bool(completed_map.get(name)),
                    "date_str": date_map.get(name, ""),
                }
            )

        return render_template(
            "tracking.html",
            vin=vin_norm.upper(),
            lot_number=lot_number,
            vehicle=vehicle,
            stages=stages,
            stage_details=stage_details,
        )

    @app.shell_context_processor
    def make_shell_context():
        from .models import User, Role, Customer, Vehicle, Auction, Shipment
        return dict(db=db, User=User, Role=Role, Customer=Customer, Vehicle=Vehicle, Auction=Auction, Shipment=Shipment)

    return app
