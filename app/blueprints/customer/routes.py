from flask import (
    Blueprint,
    render_template,
    request,
    send_file,
    abort,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
)
from flask_login import login_required, current_user
from ...extensions import db
from ...models import (
    Vehicle,
    Auction,
    Shipment,
    VehicleShipment,
    Customer,
    Invoice,
    InvoiceItem,
    VehicleSaleListing,
    Document,
)
from ...utils_pdf import render_invoice_pdf
from decimal import Decimal
import os
import secrets

cust_bp = Blueprint("cust", __name__, template_folder="templates/customer")

@cust_bp.route("/dashboard")
@login_required
def dashboard():
    """Customer home page with personalized insights and quick actions."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()

    counts = {
        "total": 0,
        "in_transit": 0,
        "delivered": 0,
        "awaiting": 0,
        "open_invoices": 0,
    }
    vehicle_cards: list[dict] = []
    invoices_summary: list[dict] = []

    outstanding_total = Decimal("0")

    if cust:
        vehicles = (
            db.session.query(Vehicle)
            .filter(Vehicle.owner_customer_id == cust.id)
            .order_by(Vehicle.created_at.desc())
            .limit(6)
            .all()
        )
        counts["total"] = len(vehicles)

        shipments_by_vehicle: dict[int, Shipment] = {}
        if vehicles:
            vehicle_ids = [v.id for v in vehicles]
            shipment_rows = (
                db.session.query(Shipment, VehicleShipment.vehicle_id)
                .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
                .filter(VehicleShipment.vehicle_id.in_(vehicle_ids))
                .order_by(Shipment.created_at.desc())
                .all()
            )

            def shipment_sort_key(s: Shipment | None):
                if not s:
                    return None
                return (
                    s.arrival_date
                    or s.departure_date
                    or s.created_at
                )

            for shipment, vehicle_id in shipment_rows:
                existing = shipments_by_vehicle.get(vehicle_id)
                if existing is None:
                    shipments_by_vehicle[vehicle_id] = shipment
                else:
                    current_key = shipment_sort_key(existing)
                    new_key = shipment_sort_key(shipment)
                    if new_key and (current_key is None or new_key > current_key):
                        shipments_by_vehicle[vehicle_id] = shipment

        for vehicle in vehicles:
            shipment = shipments_by_vehicle.get(vehicle.id)
            status_text = (vehicle.status or "").strip()
            status_lower = status_text.lower()

            stage = "awaiting"
            if shipment and shipment.arrival_date:
                stage = "delivered"
            elif shipment and shipment.departure_date:
                stage = "in_transit"
            elif status_lower in {"delivered", "arrived"}:
                stage = "delivered"
            elif status_lower in {"in transit", "shipping", "shipped", "posted"}:
                stage = "in_transit"

            if stage == "in_transit":
                counts["in_transit"] += 1
            elif stage == "delivered":
                counts["delivered"] += 1
            else:
                counts["awaiting"] += 1

            vehicle_cards.append(
                {
                    "id": vehicle.id,
                    "vin": (vehicle.vin or "").strip(),
                    "title": " ".join(filter(None, [vehicle.make, vehicle.model, str(vehicle.year or "").strip()])),
                    "status": status_text or "-",
                    "stage": stage,
                    "container": (
                        (shipment.container_number if shipment and shipment.container_number else None)
                        or getattr(vehicle, "container_number", None)
                    ),
                    "origin": shipment.origin_port if shipment else None,
                    "destination": shipment.destination_port if shipment else None,
                    "departed": shipment.departure_date if shipment else None,
                    "eta": shipment.arrival_date if shipment else None,
                    "timeline_url": url_for("tracking_page", vin=vehicle.vin) if vehicle.vin else None,
                    "details_url": url_for("cust.my_cars") + f"?focus={vehicle.id}",
                }
            )

        invoice_rows = (
            db.session.query(Invoice)
            .filter(Invoice.customer_id == cust.id)
            .order_by(Invoice.created_at.desc())
            .limit(5)
            .all()
        )

        for invoice in invoice_rows:
            status_norm = (invoice.status or "").strip().lower()
            total_amount = Decimal(str(invoice.total_omr or 0))
            try:
                paid_amount = invoice.paid_total()
            except Exception:
                paid_amount = Decimal("0")

            outstanding_amount = total_amount - paid_amount
            if outstanding_amount < Decimal("0"):
                outstanding_amount = Decimal("0")

            is_open = status_norm not in {"paid", "cancelled"}
            if is_open:
                counts["open_invoices"] += 1
                outstanding_total += outstanding_amount

            invoices_summary.append(
                {
                    "id": invoice.id,
                    "number": invoice.invoice_number or f"INV-{invoice.id}",
                    "status": status_norm or "unknown",
                    "total": total_amount,
                    "outstanding": outstanding_amount,
                    "created_at": invoice.created_at,
                    "detail_url": url_for("cust.invoice_detail", invoice_id=invoice.id),
                    "is_open": is_open,
                }
            )

    return render_template(
        "customer/home.html",
        customer=cust,
        counts=counts,
        vehicles=vehicle_cards,
        invoices=invoices_summary,
        outstanding_total=outstanding_total,
    )


@cust_bp.route("/cars")
@login_required
def my_cars():
    """List vehicles that belong to the logged-in customer."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    cars = []
    if cust:
        cars = (
            db.session.query(Vehicle)
            .filter(Vehicle.owner_customer_id == cust.id)
            .order_by(Vehicle.created_at.desc())
            .all()
        )
    # fetch pending/last sale listing per vehicle for quick UI state
    listings_by_vehicle = {}
    if cars:
        vids = [v.id for v in cars]
        rows = (
            db.session.query(VehicleSaleListing)
            .filter(VehicleSaleListing.vehicle_id.in_(vids))
            .order_by(VehicleSaleListing.created_at.desc())
            .all()
        )
        for row in rows:
            # keep latest per vehicle
            if row.vehicle_id not in listings_by_vehicle:
                listings_by_vehicle[row.vehicle_id] = row
    return render_template("customer/my_cars.html", cars=cars, sale_listings=listings_by_vehicle)


@cust_bp.post("/cars/<int:vehicle_id>/sell")
@login_required
def request_sale_listing(vehicle_id: int):
    """Customer submits a request to list a car for sale with asking price.

    Creates a VehicleSaleListing in Pending status for Operations to approve.
    """
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    v = db.session.get(Vehicle, vehicle_id)
    if not v or not cust or v.owner_customer_id != cust.id:
        abort(404)

    price_str = (request.form.get("asking_price_omr") or "").strip()
    try:
        asking_price = float(price_str)
    except Exception:
        asking_price = None
    if not asking_price or asking_price <= 0:
        flash("الرجاء إدخال سعر صحيح بالريال العماني", "danger")
        return redirect(url_for("cust.my_cars"))

    # prevent multiple active pending for same vehicle
    existing = (
        db.session.query(VehicleSaleListing)
        .filter(VehicleSaleListing.vehicle_id == v.id, VehicleSaleListing.status == "Pending")
        .first()
    )
    if existing:
        flash("يوجد طلب بيع قيد الموافقة بالفعل لهذه السيارة", "warning")
        return redirect(url_for("cust.my_cars"))

    sl = VehicleSaleListing(
        vehicle_id=v.id,
        customer_id=cust.id,
        asking_price_omr=asking_price,
        status="Pending",
    )
    db.session.add(sl)
    try:
        db.session.commit()
        # Notify operations
        try:
            from ...blueprints.operations.routes import notify as ops_notify
            ops_notify(f"New sale request for {v.vin} (OMR {asking_price:.3f})", 'Vehicle', v.id)
        except Exception:
            pass
        flash("تم إرسال طلب عرض السيارة للبيع للموافقة", "success")
    except Exception:
        db.session.rollback()
        flash("تعذر حفظ الطلب. حاول مرة أخرى.", "danger")
    return redirect(url_for("cust.my_cars"))


@cust_bp.route("/cars/<int:vehicle_id>")
@login_required
def car_detail(vehicle_id: int):
    """Show car details for the current customer without tracking timeline."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    v = db.session.get(Vehicle, vehicle_id)
    if not v or not cust or v.owner_customer_id != cust.id:
        abort(404)

    # Related data
    auction = v.auction
    shipments = (
        db.session.query(Shipment)
        .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(VehicleShipment.vehicle_id == v.id)
        .order_by(Shipment.created_at.asc())
        .all()
    )

    # Collect image URLs from static/uploads/<VIN>/
    image_urls: list[str] = []
    try:
        vin = (v.vin or "").strip()
        base_dir = os.path.join(current_app.static_folder, "uploads", vin)
        if vin and os.path.isdir(base_dir):
            for fname in sorted(os.listdir(base_dir)):
                lower = fname.lower()
                if any(lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
                    image_urls.append(url_for("static", filename=f"uploads/{vin}/{fname}"))
    except Exception:
        image_urls = []

    # Fetch approved sale price (OMR) if any
    sale_price_omr = None
    try:
        row = (
            db.session.query(VehicleSaleListing)
            .filter(
                VehicleSaleListing.vehicle_id == v.id,
                VehicleSaleListing.status == "Approved",
            )
            .order_by(db.func.coalesce(VehicleSaleListing.decided_at, VehicleSaleListing.created_at).desc())
            .first()
        )
        if row and getattr(row, "asking_price_omr", None) is not None:
            sale_price_omr = row.asking_price_omr
    except Exception:
        sale_price_omr = None

    # Allow customers to access their own vehicle statement link
    return render_template(
        "public/vehicle_public.html",
        vehicle=v,
        auction=auction,
        shipments=shipments,
        image_urls=image_urls,
        sale_price_omr=sale_price_omr,
        soa_url=url_for('acct.vehicle_statement', vehicle_id=v.id),
    )

@cust_bp.post("/cars/<int:vehicle_id>/share")
@login_required
def share_vehicle(vehicle_id: int):
    """Enable public sharing for a vehicle and generate a share link.

    Redirects back to My Cars with a flash message containing the link.
    """
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    v = db.session.get(Vehicle, vehicle_id)
    if not v or not cust or v.owner_customer_id != cust.id:
        abort(404)

    # Ensure token exists and is unique; enable sharing
    if not getattr(v, "share_token", None):
        # Retry a few times in the extremely unlikely case of collision
        for attempt_index in range(5):
            candidate = secrets.token_urlsafe(24)[:64]
            exists = db.session.query(Vehicle).filter(Vehicle.share_token == candidate).first()
            if not exists:
                v.share_token = candidate
                break
        if not v.share_token:
            # AJAX/JSON response when requested
            wants_json = (
                "application/json" in request.accept_mimetypes
                or (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest"
            )
            if wants_json:
                return jsonify(success=False, message="تعذر إنشاء رابط المشاركة. حاول مرة أخرى."), 400
            flash("تعذر إنشاء رابط المشاركة. حاول مرة أخرى.", "danger")
            return redirect(url_for("cust.my_cars"))

    v.share_enabled = True
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        wants_json = (
            "application/json" in request.accept_mimetypes
            or (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest"
        )
        if wants_json:
            return jsonify(success=False, message="حدث خطأ أثناء حفظ رابط المشاركة."), 500
        flash("حدث خطأ أثناء حفظ رابط المشاركة.", "danger")
        return redirect(url_for("cust.my_cars"))

    share_url = url_for("vehicle_public_page", token=v.share_token, _external=True)

    # If this is an AJAX/JSON request, return the link as JSON so the client can copy it
    wants_json = (
        "application/json" in request.accept_mimetypes
        or (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest"
    )
    if wants_json:
        return jsonify(success=True, share_url=share_url, message="تم إنشاء رابط المشاركة")

    # Fallback to legacy behavior with flash + redirect
    flash(f"تم إنشاء رابط المشاركة: {share_url}", "success")
    return redirect(url_for("cust.my_cars"))


@cust_bp.post("/cars/<int:vehicle_id>/share/disable")
@login_required
def disable_share_vehicle(vehicle_id: int):
    """Disable public sharing for the vehicle."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    v = db.session.get(Vehicle, vehicle_id)
    if not v or not cust or v.owner_customer_id != cust.id:
        abort(404)

    v.share_enabled = False
    try:
        db.session.commit()
        flash("تم إيقاف مشاركة السيارة.", "success")
    except Exception:
        db.session.rollback()
        flash("تعذر إيقاف المشاركة.", "danger")
    return redirect(url_for("cust.my_cars"))


@cust_bp.route("/track")
def track():
    """Public entry point for shipment tracking.

    Accepts VIN or Lot inputs (via vin=, lot=, or q=) and redirects to /tracking/<identifier>.
    For authenticated customers, falls back to their most recent vehicle VIN.
    """
    identifier = (
        request.args.get("vin")
        or request.args.get("lot")
        or request.args.get("q")
        or ""
    ).strip()
    if identifier:
        return redirect(url_for("tracking_page", vin=identifier))

    # For signed-in customers, fall back to most recent vehicle VIN if available.
    if current_user.is_authenticated:
        cust = (
            db.session.query(Customer)
            .filter(Customer.user_id == current_user.id)
            .first()
        )
        if cust:
            v = (
                db.session.query(Vehicle)
                .filter(Vehicle.owner_customer_id == cust.id)
                .order_by(Vehicle.created_at.desc())
                .first()
            )
            if v and v.vin:
                return redirect(url_for("tracking_page", vin=v.vin))

    return render_template("customer/track.html")


@cust_bp.route("/invoices")
@login_required
def invoices_list():
    """List invoices for the logged-in customer."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    invoices: list[Invoice] = []
    auction_rows: list[dict] = []
    active_filter = (request.args.get("filter") or "").strip().lower()

    if cust:
        if active_filter == "auction":
            # Show uploaded Auction Invoice documents for customer's vehicles
            rows = (
                db.session.query(Document, Vehicle)
                .join(Vehicle, Vehicle.id == Document.vehicle_id)
                .filter(
                    Document.doc_type == "Auction Invoice",
                    Vehicle.owner_customer_id == cust.id,
                )
                .order_by(Document.created_at.desc())
                .all()
            )
            auction_rows = [{"doc": d, "vehicle": v} for d, v in rows]
        else:
            # Default and 'company': show system-created Invoices only
            invoices = (
                db.session.query(Invoice)
                .filter(Invoice.customer_id == cust.id)
                .order_by(Invoice.created_at.desc())
                .all()
            )

    # Compute summary counts (for company invoices view only)
    def normalize_status(text: str | None) -> str:
        return (text or "").strip()

    paid_count = sum(1 for inv in invoices if normalize_status(inv.status) == "Paid") if invoices else 0
    unpaid_count = (
        sum(1 for inv in invoices if normalize_status(inv.status) not in ("Paid", "Cancelled"))
        if invoices
        else 0
    )

    return render_template(
        "customer/invoices_list.html",
        invoices=invoices,
        auction_rows=auction_rows,
        paid_count=paid_count,
        unpaid_count=unpaid_count,
        active_filter=active_filter,
    )


@cust_bp.route("/auction-invoices/<int:doc_id>")
@login_required
def auction_invoice_download(doc_id: int):
    """Allow a customer to download their uploaded auction invoice securely."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    if not cust:
        abort(404)
    doc = db.session.get(Document, doc_id)
    if not doc or (doc.doc_type or "") != "Auction Invoice":
        abort(404)
    # Ensure document belongs to one of customer's vehicles
    v = db.session.get(Vehicle, doc.vehicle_id) if getattr(doc, "vehicle_id", None) else None
    if not v or v.owner_customer_id != cust.id:
        abort(404)
    path = getattr(doc, "file_path", None)
    if not path or not os.path.isfile(path):
        flash("الملف غير متوفر للتحميل", "danger")
        return redirect(url_for("cust.invoices_list", filter="auction"))
    fname = os.path.basename(path)
    return send_file(path, as_attachment=True, download_name=fname)


@cust_bp.route("/invoices/<int:invoice_id>")
@login_required
def invoice_detail(invoice_id: int):
    """Invoice detail page for the current customer."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    inv = db.session.get(Invoice, invoice_id)
    if not inv or not cust or inv.customer_id != cust.id:
        abort(404)
    return render_template("customer/invoice_detail.html", invoice=inv)


@cust_bp.route("/invoices/<int:invoice_id>/pdf")
@login_required
def invoice_pdf(invoice_id: int):
    """Generate or serve invoice PDF for the current customer."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    inv = db.session.get(Invoice, invoice_id)
    if not inv or not cust or inv.customer_id != cust.id:
        abort(404)
    items = db.session.query(InvoiceItem).filter_by(invoice_id=inv.id).all()
    path = inv.pdf_path
    if not path or not os.path.isfile(path):
        if path:
            try:
                current_app.logger.warning("Invoice PDF missing at %s; regenerating", path)
            except Exception:
                pass
        path = render_invoice_pdf(inv, items)
        inv.pdf_path = path
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    if not os.path.isfile(path):
        flash("Invoice PDF is not available.", "danger")
        return redirect(url_for("cust.invoice_detail", invoice_id=inv.id))
    return send_file(path, as_attachment=True, download_name=f"{inv.invoice_number}.pdf")
