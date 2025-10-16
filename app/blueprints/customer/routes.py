from flask import Blueprint, render_template, request, send_file, abort, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from ...extensions import db
from ...models import Vehicle, Auction, Shipment, VehicleShipment, Customer, Invoice, InvoiceItem, InternationalCost
from ...utils_pdf import render_invoice_pdf
import os

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


@cust_bp.route("/cars/<int:vehicle_id>")
@login_required
def car_detail(vehicle_id: int):
    """Full vehicle details for the logged-in customer, including shipment/container and totals."""
    cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
    v = db.session.get(Vehicle, vehicle_id)
    if not v or not cust or v.owner_customer_id != cust.id:
        abort(404)

    # Fetch shipments ordered by creation (primary first)
    shipments = (
        db.session.query(Shipment)
        .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(VehicleShipment.vehicle_id == v.id)
        .order_by(Shipment.created_at.asc())
        .all()
    )
    primary = shipments[0] if shipments else None

    # Container number and arrival date (from primary shipment when present)
    container_number = primary.container_number if primary else None
    arrival_date = primary.arrival_date if primary else None

    # Compute total cost for this vehicle for the customer
    # Prefer invoice items linked to this vehicle; otherwise estimate from InternationalCost/other known fields
    inv_items = (
        db.session.query(InvoiceItem)
        .join(Invoice, InvoiceItem.invoice_id == Invoice.id)
        .filter(Invoice.customer_id == cust.id, InvoiceItem.vehicle_id == v.id)
        .all()
    )
    total_omr_actual = sum([float(it.amount_omr or 0) for it in inv_items]) if inv_items else 0.0

    # Estimated total if no invoice items
    try:
        usd_to_omr = float(current_app.config.get("OMR_EXCHANGE_RATE", 0.385))
    except Exception:
        usd_to_omr = 0.385
    est_total_omr = 0.0
    ic = db.session.query(InternationalCost).filter_by(vehicle_id=v.id).first()
    try:
        base_usd = float(ic.cif_usd or 0) if ic else float(v.purchase_price_usd or 0)
        est_total_omr += base_usd * usd_to_omr
    except Exception:
        pass
    if ic:
        try:
            est_total_omr += float(ic.customs_omr or 0)
            est_total_omr += float(ic.vat_omr or 0)
            est_total_omr += float(ic.local_transport_omr or 0)
            est_total_omr += float(ic.misc_omr or 0)
        except Exception:
            pass

    total_omr = total_omr_actual or est_total_omr

    return render_template(
        "customer/car_detail.html",
        vehicle=v,
        primary_shipment=primary,
        container_number=container_number,
        arrival_date=arrival_date,
        total_omr=total_omr,
        invoice_items=inv_items,
    )

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
