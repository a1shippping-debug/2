import os
from flask import Flask, request, g, render_template, current_app, url_for, abort
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
        # Always prioritize explicit user choice via query/cookie; otherwise default to Arabic
        supported = app.config.get("BABEL_SUPPORTED_LOCALES", ["ar", "en"]) or ["ar", "en"]
        lang = (request.args.get("lang") or request.cookies.get("lang") or "").strip()
        if lang in supported:
            return lang
        # Ignore Accept-Language to keep Arabic as the canonical default language
        return app.config.get("BABEL_DEFAULT_LOCALE", "ar")

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
            g.lang_code = select_locale() or "ar"
        except Exception:
            g.lang_code = "ar"

    @app.after_request
    def persist_lang_cookie(response):
        try:
            supported = app.config.get("BABEL_SUPPORTED_LOCALES", ["ar", "en"]) or ["ar", "en"]
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
        # Show a small selection of approved sale listings on the homepage
        try:
            from .extensions import db
            from .models import Vehicle, VehicleSaleListing

            # Prefer explicitly approved sale listings (latest first)
            rows = (
                db.session.query(VehicleSaleListing)
                .join(Vehicle, Vehicle.id == VehicleSaleListing.vehicle_id)
                .filter(VehicleSaleListing.status == "Approved")
                .order_by(db.func.coalesce(VehicleSaleListing.decided_at, VehicleSaleListing.created_at).desc())
                .limit(6)
                .all()
            )
            cars_for_sale = [r.vehicle for r in rows if getattr(r, "vehicle", None)]

            # Annotate vehicles with sale (asking) price for display
            for r in rows:
                try:
                    if getattr(r, "vehicle", None) is not None:
                        setattr(r.vehicle, "sale_price_omr", getattr(r, "asking_price_omr", None))
                except Exception:
                    pass

            # Fallback to previously visible vehicles if there are no approved listings yet
            if not cars_for_sale:
                q = db.session.query(Vehicle).filter(Vehicle.owner_customer_id.is_(None))
                excluded = ["delivered", "arrived", "shipping", "on way", "in transit"]
                q = q.filter(db.func.lower(Vehicle.status).notin_(excluded))
                cars_for_sale = q.order_by(Vehicle.created_at.desc()).limit(6).all()
        except Exception:
            cars_for_sale = []

        # Attach primary image URL for each vehicle card on the homepage
        try:
            for v in cars_for_sale or []:
                try:
                    vin = (v.vin or "").strip()
                    base_dir = os.path.join(current_app.static_folder, "uploads", vin)
                    primary_url = None
                    if vin and os.path.isdir(base_dir):
                        for fname in sorted(os.listdir(base_dir)):
                            lower = fname.lower()
                            if lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                                primary_url = url_for("static", filename=f"uploads/{vin}/{fname}")
                                break
                    setattr(v, "primary_image_url", primary_url)
                except Exception:
                    setattr(v, "primary_image_url", None)
        except Exception:
            # Fail-safe: don't block homepage if image probing fails
            pass

        # Load latest approved testimonials
        try:
            from .models import Testimonial
            testimonials = (
                db.session.query(Testimonial)
                .filter(Testimonial.approved.is_(True))
                .order_by(Testimonial.created_at.desc())
                .limit(6)
                .all()
            )
        except Exception:
            testimonials = []

        return render_template("landing.html", cars_for_sale=cars_for_sale, testimonials=testimonials)

    @app.route("/testimonials", methods=["POST"])
    def submit_testimonial():
        name = (request.form.get("name") or "").strip()
        role = (request.form.get("role") or "").strip()
        content = (request.form.get("content") or "").strip()
        rating_raw = (request.form.get("rating") or "").strip()

        if not name or not content:
            # basic validation; show message and redirect back to homepage
            try:
                from flask import flash
                flash("الرجاء إدخال الاسم والمحتوى", "danger")
            except Exception:
                pass
            return render_template("landing.html", cars_for_sale=[], testimonials=[]), 400

        try:
            rating = int(rating_raw) if rating_raw else 5
        except Exception:
            rating = 5
        rating = max(1, min(5, rating))

        try:
            from .models import Testimonial
            t = Testimonial(name=name, role=role or None, content=content, rating=rating, approved=True)
            db.session.add(t)
            db.session.commit()
            try:
                from flask import flash
                flash("تم إرسال رأيك بنجاح. شكرًا لك!", "success")
            except Exception:
                pass
        except Exception:
            try:
                db.session.rollback()
            except Exception:
                pass
            try:
                from flask import flash
                flash("تعذر حفظ رأيك. حاول مرة أخرى.", "danger")
            except Exception:
                pass

        # redirect back to homepage after submission
        from flask import redirect
        return redirect(url_for("index"))

    # Public informational pages
    @app.route("/about")
    def about_page():
        return render_template("info/about.html")

    @app.route("/services")
    def services_page():
        return render_template("info/services.html")

    @app.route("/contact")
    def contact_page():
        return render_template("info/contact.html")

    @app.route("/tracking/<string:vin>")
    def tracking_page(vin: str):
        """Public vehicle shipment tracking by VIN.

        Renders a Bootstrap-based horizontal 12-stage timeline with icons and
        green/red status indicators. Data is derived from DB where available
        and otherwise simulated for demonstration.
        """
        from datetime import datetime, timedelta
        from .extensions import db
        from .models import Vehicle, Auction, Shipment, VehicleShipment, InternationalCost
        from decimal import Decimal

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
            latest_shipment = shipments[-1] if shipments else None

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

        # Summary fields for quick view
        container_number = "-"
        arrival_date = "-"
        total_cost_omr = None

        try:
            if vehicle:
                # Prefer the latest shipment for container/arrival summary
                if 'latest_shipment' in locals() and latest_shipment:
                    container_number = (latest_shipment.container_number or "-").strip() if getattr(latest_shipment, 'container_number', None) else "-"
                    arrival_date = fmt_dt(getattr(latest_shipment, 'arrival_date', None)) or "-"

                # Compute total cost in OMR if InternationalCost exists
                cost_row = db.session.query(InternationalCost).filter_by(vehicle_id=vehicle.id).first()
                if cost_row:
                    def dec(x):
                        try:
                            return Decimal(str(x or 0))
                        except Exception:
                            return Decimal('0')

                    usd_sum = dec(vehicle.purchase_price_usd) + dec(cost_row.freight_usd) + dec(cost_row.insurance_usd) + dec(cost_row.auction_fees_usd)
                    omr_rate = Decimal(str(current_app.config.get("OMR_EXCHANGE_RATE", 0.385)))
                    omr_from_usd = usd_sum * omr_rate
                    omr_local = dec(cost_row.customs_omr) + dec(cost_row.vat_omr) + dec(cost_row.local_transport_omr) + dec(cost_row.misc_omr)
                    total_cost_omr = omr_from_usd + omr_local
        except Exception:
            # Fail-safe: keep defaults
            container_number = container_number or "-"
            arrival_date = arrival_date or "-"
            total_cost_omr = total_cost_omr

        return render_template(
            "tracking.html",
            vin=vin_norm.upper(),
            lot_number=lot_number,
            vehicle=vehicle,
            stages=stages,
            stage_details=stage_details,
            container_number=container_number,
            arrival_date=arrival_date,
            total_cost_omr=total_cost_omr,
        )

    @app.route("/vehicle/<string:vin>")
    def vehicle_detail_page(vin: str):
        """Public vehicle detail page by VIN without tracking timeline.

        Shows images and comprehensive details similar to the shared public page,
        and includes the sale price (OMR) when an approved sale listing exists.
        """
        from .extensions import db
        from .models import Vehicle, Auction, Shipment, VehicleShipment, VehicleSaleListing

        vin_norm = (vin or "").strip()
        if not vin_norm:
            abort(404)

        vehicle = (
            db.session.query(Vehicle)
            .join(Auction, Vehicle.auction_id == Auction.id, isouter=True)
            .filter(db.func.lower(Vehicle.vin) == db.func.lower(vin_norm))
            .first()
        )
        if not vehicle:
            abort(404)

        auction = vehicle.auction
        shipments = (
            db.session.query(Shipment)
            .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
            .filter(VehicleShipment.vehicle_id == vehicle.id)
            .order_by(Shipment.created_at.asc())
            .all()
        )

        # Collect image URLs from static/uploads/<VIN>/
        image_urls = []
        try:
            vin2 = (vehicle.vin or "").strip()
            base_dir = os.path.join(current_app.static_folder, "uploads", vin2)
            if vin2 and os.path.isdir(base_dir):
                for fname in sorted(os.listdir(base_dir)):
                    lower = fname.lower()
                    if any(lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                        image_urls.append(url_for("static", filename=f"uploads/{vin2}/{fname}"))
        except Exception:
            image_urls = []

        # Fetch approved sale price (OMR) if any
        sale_price_omr = None
        try:
            row = (
                db.session.query(VehicleSaleListing)
                .filter(
                    VehicleSaleListing.vehicle_id == vehicle.id,
                    VehicleSaleListing.status == "Approved",
                )
                .order_by(db.func.coalesce(VehicleSaleListing.decided_at, VehicleSaleListing.created_at).desc())
                .first()
            )
            if row and getattr(row, "asking_price_omr", None) is not None:
                sale_price_omr = row.asking_price_omr
        except Exception:
            sale_price_omr = None

        return render_template(
            "public/vehicle_public.html",
            vehicle=vehicle,
            auction=auction,
            shipments=shipments,
            image_urls=image_urls,
            sale_price_omr=sale_price_omr,
        )

    @app.route("/v/<string:token>")
    def vehicle_public_page(token: str):
        """Public vehicle detail page by share token.

        Shows images and comprehensive details for the vehicle associated with
        the provided share token, if sharing is enabled.
        """
        from .extensions import db
        from .models import Vehicle, Auction, Shipment, VehicleShipment, VehicleSaleListing

        token_norm = (token or "").strip()
        if not token_norm:
            abort(404)

        vehicle = (
            db.session.query(Vehicle)
            .join(Auction, Vehicle.auction_id == Auction.id, isouter=True)
            .filter(Vehicle.share_token == token_norm)
            .first()
        )
        if not vehicle or not getattr(vehicle, "share_enabled", False):
            abort(404)

        # Gather related info
        auction = vehicle.auction
        shipments = (
            db.session.query(Shipment)
            .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
            .filter(VehicleShipment.vehicle_id == vehicle.id)
            .order_by(Shipment.created_at.asc())
            .all()
        )

        # Collect image URLs from static/uploads/<VIN>/
        image_urls = []
        try:
            vin = (vehicle.vin or "").strip()
            base_dir = os.path.join(current_app.static_folder, "uploads", vin)
            if vin and os.path.isdir(base_dir):
                for fname in sorted(os.listdir(base_dir)):
                    lower = fname.lower()
                    if any(lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                        image_urls.append(url_for("static", filename=f"uploads/{vin}/{fname}"))
        except Exception:
            # Fail silently; images are optional
            image_urls = []

        # Fetch approved sale price (OMR) if any
        sale_price_omr = None
        try:
            row = (
                db.session.query(VehicleSaleListing)
                .filter(
                    VehicleSaleListing.vehicle_id == vehicle.id,
                    VehicleSaleListing.status == "Approved",
                )
                .order_by(db.func.coalesce(VehicleSaleListing.decided_at, VehicleSaleListing.created_at).desc())
                .first()
            )
            if row and getattr(row, "asking_price_omr", None) is not None:
                sale_price_omr = row.asking_price_omr
        except Exception:
            sale_price_omr = None

        return render_template(
            "public/vehicle_public.html",
            vehicle=vehicle,
            auction=auction,
            shipments=shipments,
            image_urls=image_urls,
            sale_price_omr=sale_price_omr,
        )

    @app.shell_context_processor
    def make_shell_context():
        from .models import User, Role, Customer, Vehicle, Auction, Shipment
        return dict(db=db, User=User, Role=Role, Customer=Customer, Vehicle=Vehicle, Auction=Auction, Shipment=Shipment)

    return app
