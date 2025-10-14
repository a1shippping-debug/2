from flask import Blueprint, render_template, request, send_file, abort
from flask_login import login_required, current_user
from ...extensions import db
from ...models import Vehicle, Auction, Shipment, VehicleShipment, Customer, Invoice, InvoiceItem
from ...utils_pdf import render_invoice_pdf

cust_bp = Blueprint("cust", __name__, template_folder="templates/customer")

@cust_bp.route("/dashboard")
@login_required
def dashboard():
    """Customer dashboard now renders the unified tracking timeline page.

    If a VIN is provided via query string (vin= or q=), we render its timeline.
    Otherwise we pick the latest vehicle owned by the logged-in customer.
    If none found, we render a simulated timeline so the page isn't empty.
    """
    from datetime import datetime, timedelta
    from flask_login import current_user

    # Resolve current customer's profile (if any)
    customer = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()

    # Determine VIN to display: explicit 'vin' or 'q' param, else latest vehicle VIN
    vin_param = (request.args.get("vin") or request.args.get("q") or "").strip()
    vin_norm = vin_param

    vehicle = None
    if not vin_norm and customer:
        vehicle = (
            db.session.query(Vehicle)
            .filter(Vehicle.owner_customer_id == customer.id)
            .order_by(Vehicle.created_at.desc())
            .first()
        )
        vin_norm = (vehicle.vin or "").strip() if vehicle else ""

    stages = []
    lot_number = "-"

    if vin_norm:
        if vehicle is None:
            vehicle = (
                db.session.query(Vehicle)
                .join(Auction, Vehicle.auction_id == Auction.id, isouter=True)
                .filter(db.func.lower(Vehicle.vin) == db.func.lower(vin_norm))
                .first()
            )

        # Ensure customers can only view their own vehicle details
        if vehicle and customer and vehicle.owner_customer_id and vehicle.owner_customer_id != customer.id:
            vehicle = None

    completed_map = {}
    date_map = {}

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
            "Cashier Payment": bool(vehicle.purchase_price_usd and float(vehicle.purchase_price_usd) > 0),
            "Auction Payment": bool(vehicle.purchase_date),
            "Posted": bool(shipments) or norm_status in {"in shipping", "shipped", "delivered", "arrived", "in transit"},
            "Towing": any(k in norm_status for k in ["picked", "towing", "tow"]),
            "Warehouse": "warehouse" in norm_status,
            "Loading": bool(shipments and not departed),
            "Shipping": bool(departed),
            "Port": bool(departed),
            "On way": bool(departed and not arrived),
            "Arrived": bool(arrived),
            "Delivered": bool(shipment_delivered or "delivered" in norm_status),
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
    else:
        # Simulated example data when VIN not found or customer has no vehicles
        base = datetime.utcnow() - timedelta(days=15)
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
            completed_map[nm] = idx < 7
            date_map[nm] = (base + timedelta(days=idx)).strftime("%d-%m-%Y") if completed_map[nm] else ""

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
        vin=(vin_norm.upper() if vin_norm else ""),
        lot_number=lot_number,
        vehicle=vehicle,
        stages=stages,
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
