from flask import Blueprint, render_template, request, send_file, abort, redirect, url_for
from flask_login import login_required, current_user
from ...extensions import db
from ...models import Vehicle, Auction, Shipment, VehicleShipment, Customer, Invoice, InvoiceItem
from ...utils_pdf import render_invoice_pdf

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
    return render_template("customer/invoices_list.html", invoices=invoices)


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
    path = inv.pdf_path or render_invoice_pdf(inv, items)
    return send_file(path, as_attachment=True, download_name=f"{inv.invoice_number}.pdf")
