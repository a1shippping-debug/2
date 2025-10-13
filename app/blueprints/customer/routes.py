from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from ...extensions import db
from ...models import Vehicle, Auction, Shipment, VehicleShipment, Customer

cust_bp = Blueprint("cust", __name__, template_folder="templates/customer")

@cust_bp.route("/dashboard")
@login_required
def dashboard():
    """Customer dashboard with VIN/lot search and stage indicators."""
    query_text = (request.args.get("q") or "").strip()

    vehicles = []
    if query_text:
        # base query, outer-join auction to allow filtering by lot number
        q = db.session.query(Vehicle).join(Auction, Vehicle.auction_id == Auction.id, isouter=True)

        like_val = f"%{query_text}%"
        # case-insensitive contains match for VIN or lot number
        q = q.filter(
            db.or_(
                db.func.lower(Vehicle.vin).like(db.func.lower(like_val)),
                db.func.lower(Auction.lot_number).like(db.func.lower(like_val)),
            )
        )

        # restrict to vehicles owned by the current customer, if applicable
        cust = db.session.query(Customer).filter(Customer.user_id == current_user.id).first()
        if cust:
            q = q.filter(Vehicle.owner_customer_id == cust.id)

        vehicles = q.order_by(Vehicle.created_at.desc()).all()

    def compute_stages(v: Vehicle):
        """Derive stage completion booleans from available data."""
        normalized_status = (v.status or "").strip().lower()

        # Stage 1: Auction payment considered done if purchase price is set (>0)
        paid = False
        try:
            paid = v.purchase_price_usd is not None and float(v.purchase_price_usd) > 0
        except Exception:
            paid = False

        # Stage 2: Picked up from auction (heuristic from status)
        picked_statuses = {"picked up", "at warehouse", "in shipping", "delivered", "arrived", "received"}
        picked_up = normalized_status in picked_statuses

        # Stage 3: Arrived to warehouse (heuristic from status)
        warehouse_statuses = {"at warehouse", "in shipping", "delivered", "arrived", "received"}
        at_warehouse = normalized_status in warehouse_statuses

        # Stages 4 & 5 from shipments association
        shipped = False
        delivered = False
        if v.id:
            shipments = (
                db.session.query(Shipment)
                .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
                .filter(VehicleShipment.vehicle_id == v.id)
                .all()
            )
            for s in shipments:
                s_norm = (s.status or "").strip().lower()
                if (s.departure_date is not None) or (s_norm in {"in transit", "delivered"}):
                    shipped = True
                if (s.arrival_date is not None) or (s_norm == "delivered"):
                    delivered = True

        return {
            "paid": paid,
            "picked_up": picked_up,
            "warehouse": at_warehouse,
            "shipped": shipped,
            "delivered": delivered,
        }

    results = []
    for v in vehicles:
        results.append({
            "vehicle": v,
            "auction": v.auction,
            "stages": compute_stages(v),
        })

    return render_template("customer/dashboard.html", q=query_text, results=results)
