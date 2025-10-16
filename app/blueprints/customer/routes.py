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
from ...models import Vehicle, Auction, Shipment, VehicleShipment, Customer, Invoice, InvoiceItem
from ...utils_pdf import render_invoice_pdf
import os
import secrets

cust_bp = Blueprint("cust", __name__, template_folder="templates/customer")

@cust_bp.route("/dashboard")
@login_required
def dashboard():
    """Customer home page with quick actions."""
    return render_template("customer/home.html")


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
    return render_template("customer/my_cars.html", cars=cars)


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

    # Reuse the public details template (no timeline)
    return render_template(
        "public/vehicle_public.html",
        vehicle=v,
        auction=auction,
        shipments=shipments,
        image_urls=image_urls,
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
        for _ in range(5):
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
@login_required
def track():
    """VIN entry and redirect to the public tracking timeline.

    If a VIN is provided (via vin= or q=), redirect to /tracking/<vin>.
    Otherwise, try to use the latest vehicle of the current customer.
    If none, show a simple VIN input form.
    """
    vin_param = (request.args.get("vin") or request.args.get("q") or "").strip()
    if vin_param:
        return redirect(url_for("tracking_page", vin=vin_param))

    # Pick latest vehicle for convenience
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
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
    invoices = []
    if cust:
        invoices = (
            db.session.query(Invoice)
            .filter(Invoice.customer_id == cust.id)
            .order_by(Invoice.created_at.desc())
            .all()
        )
    # Compute summary counts for paid vs unpaid (excluding cancelled)
    def normalize_status(text: str | None) -> str:
        return (text or "").strip()

    paid_count = sum(1 for inv in invoices if normalize_status(inv.status) == "Paid")
    unpaid_count = sum(
        1
        for inv in invoices
        if normalize_status(inv.status) != "Paid" and normalize_status(inv.status) != "Cancelled"
    )

    return render_template(
        "customer/invoices_list.html",
        invoices=invoices,
        paid_count=paid_count,
        unpaid_count=unpaid_count,
    )


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
