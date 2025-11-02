from flask import Blueprint, render_template, request, jsonify, current_app, redirect, url_for, flash
from flask_babel import gettext as _
from flask_login import login_required
from ...security import role_required
from ...extensions import db
from ...models import (
    Vehicle,
    Shipment,
    VehicleShipment,
    Customer,
    Notification,
    Auction,
    Document,
    CostItem,
    User,
    Role,
    Invoice,
    InvoiceItem,
    VehicleSaleListing,
    ShippingRegionPrice,
    InternationalCost,
    Buyer,
    ClientAccountStructure,
)
from datetime import datetime

ops_bp = Blueprint("ops", __name__, template_folder="templates/operations")
# Regions suggest endpoint for searchable dropdown (Operations UI)
@ops_bp.get('/shipping/regions.json')
@role_required('employee', 'admin')
def shipping_regions_suggest():
    """Return list of regions filtered by query for autocomplete.

    Query params:
      - q: free text (matches code or name, case-insensitive)
      - limit: max results (default 10, max 20)

    Response: [{region_code, region_name, price_omr}]
    """
    q = (request.args.get('q') or '').strip().lower()
    try:
        limit = int(request.args.get('limit') or 10)
    except Exception:
        limit = 10
    limit = max(1, min(20, limit))

    query = db.session.query(ShippingRegionPrice)
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                db.func.lower(ShippingRegionPrice.region_code).like(like),
                db.func.lower(ShippingRegionPrice.region_name).like(like),
            )
        )
    # Optional category filter
    category = (request.args.get('category') or '').strip().lower()
    if category in {"normal", "container", "vip", "vvip"}:
        query = query.filter(ShippingRegionPrice.category == category)
    rows = query.order_by(ShippingRegionPrice.region_code.asc()).limit(limit).all()

    out = []
    for r in rows:
        try:
            price_val = float(r.price_omr or 0)
        except Exception:
            price_val = 0.0
        out.append({
            'region_code': r.region_code,
            'region_name': r.region_name,
            'price_omr': price_val,
        })
    return jsonify(out)
# Region shipping price lookup for Operations UI
@ops_bp.get('/shipping/region-price')
@role_required('employee', 'admin')
def shipping_region_price():
    """Return OMR price for a given region code or name.

    Query param: q (region code or name, case-insensitive)
    Response: {found: bool, region_code, region_name, price_omr}
    """
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'error': 'missing parameter q'}), 400

    # Optional category filter
    category = (request.args.get('category') or '').strip().lower()
    cat_filter = None
    if category in {"normal", "container", "vip", "vvip"}:
        cat_filter = (ShippingRegionPrice.category == category)

    # Try exact match on code or name (case-insensitive)
    base = db.session.query(ShippingRegionPrice)
    if cat_filter is not None:
        base = base.filter(cat_filter)
    row = (
        base.filter(
            db.or_(
                db.func.lower(ShippingRegionPrice.region_code) == q.lower(),
                db.func.lower(ShippingRegionPrice.region_name) == q.lower(),
            )
        ).first()
    )
    if not row:
        # Fallback to partial match
        like = f"%{q.lower()}%"
        base = db.session.query(ShippingRegionPrice)
        if cat_filter is not None:
            base = base.filter(cat_filter)
        row = (
            base.filter(
                db.or_(
                    db.func.lower(ShippingRegionPrice.region_code).like(like),
                    db.func.lower(ShippingRegionPrice.region_name).like(like),
                )
            )
            .order_by(ShippingRegionPrice.region_code.asc())
            .first()
        )

    if not row:
        return jsonify({'found': False}), 404

    try:
        price_val = float(row.price_omr or 0)
    except Exception:
        price_val = 0.0
    return jsonify({
        'found': True,
        'region_code': row.region_code,
        'region_name': row.region_name,
        'price_omr': price_val,
    })



@ops_bp.route("/dashboard")
@role_required("employee", "admin")
def dashboard():
    # Summary cards
    total_cars = db.session.query(Vehicle).count()

    # Vehicles In Transit: include either shipment status or vehicle status keywords
    in_transit_via_shipments = (
        db.session.query(db.func.count(db.distinct(Vehicle.id)))
        .join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id)
        .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(db.func.lower(Shipment.status) == "in transit")
        .scalar()
        or 0
    )
    in_transit_via_vehicle = (
        db.session.query(db.func.count(Vehicle.id))
        .filter(db.func.lower(Vehicle.status).in_(["in transit", "on way", "shipping"]))
        .scalar()
        or 0
    )
    in_transit_cars = int(in_transit_via_shipments) + int(in_transit_via_vehicle)

    # Vehicles Arrived: include shipment arrival or vehicle status keywords
    arrived_via_shipments = (
        db.session.query(db.func.count(db.distinct(Vehicle.id)))
        .join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id)
        .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(
            db.or_(Shipment.arrival_date.isnot(None), db.func.lower(Shipment.status).in_(["arrived", "delivered"]))
        )
        .scalar()
        or 0
    )
    arrived_via_vehicle = (
        db.session.query(db.func.count(Vehicle.id))
        .filter(db.func.lower(Vehicle.status).in_(["arrived", "delivered"]))
        .scalar()
        or 0
    )
    arrived_cars = int(arrived_via_shipments) + int(arrived_via_vehicle)

    open_shipments = db.session.query(Shipment).filter(db.func.lower(Shipment.status) == "open").count()
    customers_count = db.session.query(Customer).count()

    # Monthly shipped cars (last 12 months)
    now = datetime.utcnow()
    month_labels = []
    shipped_counts = []
    dt = datetime(now.year, now.month, 1)
    months = []
    for month_index in range(12):
        start = dt
        end = datetime(dt.year + 1, 1, 1) if dt.month == 12 else datetime(dt.year, dt.month + 1, 1)
        months.append((start, end, start.strftime("%b")))
        # previous month
        if dt.month == 1:
            dt = datetime(dt.year - 1, 12, 1)
        else:
            dt = datetime(dt.year, dt.month - 1, 1)
    months = list(reversed(months))
    for start, end, label in months:
        count = (
            db.session.query(db.func.count(db.distinct(Vehicle.id)))
            .join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id)
            .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
            .filter(Shipment.departure_date >= start, Shipment.departure_date < end)
            .scalar()
            or 0
        )
        month_labels.append(label)
        shipped_counts.append(int(count))

    # Recent vehicles
    recent_vehicles = db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(5).all()

    # Notifications (latest 10)
    notifications = db.session.query(Notification).order_by(Notification.created_at.desc()).limit(10).all()

    counts = {
        "total_cars": total_cars,
        "in_transit_cars": in_transit_cars,
        "arrived_cars": arrived_cars,
        "open_shipments": open_shipments,
        "customers": customers_count,
    }
    chart = {"months": month_labels, "shipped": shipped_counts}
    return render_template("operations/dashboard.html", counts=counts, chart=chart, recent=recent_vehicles, notifications=notifications)


@ops_bp.route("/notifications.json")
@role_required("employee", "admin")
def notifications_feed():
    rows = (
        db.session.query(Notification)
        .order_by(Notification.read.asc(), Notification.created_at.desc())
        .limit(20)
        .all()
    )
    def row_to_dict(n: Notification):
        return {
            "id": n.id,
            "message": n.message,
            "level": n.level,
            "target_type": n.target_type,
            "target_id": n.target_id,
            "created_at": n.created_at.strftime("%Y-%m-%d %H:%M") if n.created_at else "",
            "read": bool(n.read),
        }
    return jsonify([row_to_dict(n) for n in rows])





@ops_bp.route("/notifications/<int:nid>/read", methods=["POST"]) 
@role_required("employee", "admin")
def notifications_mark_read(nid: int):
    n = db.session.get(Notification, nid)
    if n:
        n.read = True
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return ("", 204)


# Helpers
def notify(message: str, target_type: str, target_id: int, level: str = "info") -> None:
    try:
        note = Notification(message=message, level=level, target_type=target_type, target_id=target_id)
        db.session.add(note)
        db.session.commit()
    except Exception:
        db.session.rollback()


def save_uploaded_file(subdir: str, file_obj, filename_hint: str | None = None) -> str | None:
    import os, secrets
    if not file_obj:
        return None
    base = current_app.config.get('UPLOAD_FOLDER') or os.path.join(current_app.root_path, 'static', 'uploads')
    outdir = os.path.join(base, subdir)
    os.makedirs(outdir, exist_ok=True)
    ext = ''
    if hasattr(file_obj, 'filename') and '.' in file_obj.filename:
        ext = '.' + file_obj.filename.rsplit('.', 1)[-1].lower()
    name = filename_hint or secrets.token_hex(8)
    path = os.path.join(outdir, f"{name}{ext}")
    try:
        file_obj.save(path)
        return path
    except Exception:
        return None


# Cars Management
@ops_bp.route('/cars')
@role_required('employee', 'admin')
def cars_list():
    q = db.session.query(Vehicle)
    vin = (request.args.get('vin') or '').strip()
    status = (request.args.get('status') or '').strip()
    client_id = request.args.get('client_id')
    if vin:
        q = q.filter(db.func.lower(Vehicle.vin).like(db.func.lower(f"%{vin}%")))
    if status:
        q = q.filter(Vehicle.status == status)
    if client_id:
        try:
            q = q.filter(Vehicle.owner_customer_id == int(client_id))
        except Exception:
            pass
    cars = q.order_by(Vehicle.created_at.desc()).limit(200).all()

    # Precompute a current tracking stage for each vehicle
    tracking_stage = {}
    if cars:
        vehicle_ids = [v.id for v in cars]
        rows = (
            db.session.query(VehicleShipment.vehicle_id, Shipment)
            .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
            .filter(VehicleShipment.vehicle_id.in_(vehicle_ids))
            .order_by(Shipment.created_at.asc())
            .all()
        )
        shipments_by_vehicle: dict[int, list[Shipment]] = {}
        for vid, shp in rows:
            shipments_by_vehicle.setdefault(vid, []).append(shp)

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

        # Helper to get stage index safely
        def stage_index_from_status(text: str | None) -> int:
            norm = (text or "").strip().lower()
            for idx, name in enumerate(order):
                if name.lower() == norm:
                    return idx
            return 0

        for v in cars:
            shps = shipments_by_vehicle.get(v.id, [])
            primary = shps[0] if shps else None
            departed = bool(primary and primary.departure_date)
            arrived = bool(primary and primary.arrival_date)
            shipment_status = (primary.status or "").strip().lower() if primary else ""

            idx = stage_index_from_status(v.status)
            # Promote index based on shipment signals
            if departed and not arrived:
                idx = max(idx, order.index("On way"))
            if arrived:
                idx = max(idx, order.index("Arrived"))
            if shipment_status == "delivered":
                idx = max(idx, order.index("Delivered"))

            tracking_stage[v.id] = order[idx] if 0 <= idx < len(order) else "-"

    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    return render_template('operations/cars_list.html', cars=cars, customers=customers, tracking_stage=tracking_stage)


# Sale Listings: list and approve/reject
@ops_bp.route('/sale-listings')
@role_required('employee', 'admin')
def sale_listings_list():
    status = (request.args.get('status') or '').strip()
    q = db.session.query(VehicleSaleListing).order_by(VehicleSaleListing.created_at.desc())
    if status:
        q = q.filter(VehicleSaleListing.status == status)
    rows = q.limit(300).all()
    return render_template('operations/sale_listings.html', rows=rows)


@ops_bp.post('/sale-listings/<int:listing_id>/approve')
@role_required('employee', 'admin')
def sale_listings_approve(listing_id: int):
    from datetime import datetime
    sl = db.session.get(VehicleSaleListing, listing_id)
    if not sl or sl.status != 'Pending':
        return ("Not found", 404)
    sl.status = 'Approved'
    sl.decided_at = datetime.utcnow()
    try:
        # who approved
        from flask_login import current_user
        if current_user and getattr(current_user, 'id', None):
            sl.decided_by_user_id = int(current_user.id)
    except Exception:
        pass
    try:
        db.session.commit(); notify(f"Sale listing approved for vehicle {sl.vehicle.vin}", 'Vehicle', sl.vehicle_id)
        # Optional: could change vehicle status to 'Posted' to indicate sale
    except Exception:
        db.session.rollback()
        return ("", 400)
    return redirect(url_for('ops.sale_listings_list'))


@ops_bp.post('/sale-listings/<int:listing_id>/reject')
@role_required('employee', 'admin')
def sale_listings_reject(listing_id: int):
    from datetime import datetime
    sl = db.session.get(VehicleSaleListing, listing_id)
    if not sl or sl.status != 'Pending':
        return ("Not found", 404)
    reason = (request.form.get('reason') or '').strip() or None
    sl.status = 'Rejected'
    sl.note_admin = reason
    sl.decided_at = datetime.utcnow()
    try:
        from flask_login import current_user
        if current_user and getattr(current_user, 'id', None):
            sl.decided_by_user_id = int(current_user.id)
    except Exception:
        pass
    try:
        db.session.commit(); notify(f"Sale listing rejected for vehicle {sl.vehicle.vin}", 'Vehicle', sl.vehicle_id)
    except Exception:
        db.session.rollback()
        return ("", 400)
    return redirect(url_for('ops.sale_listings_list'))


@ops_bp.route('/cars/new', methods=['GET', 'POST'])
@role_required('employee', 'admin')
def cars_new():
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    buyers = (
        db.session.query(Buyer)
        .order_by(db.func.coalesce(Buyer.buyer_number, ''), Buyer.name.asc())
        .all()
    )
    regions = db.session.query(ShippingRegionPrice).order_by(ShippingRegionPrice.region_code.asc()).all()
    if request.method == 'POST':
        vin = (request.form.get('vin') or '').strip().upper()
        make = (request.form.get('make') or '').strip()
        model = (request.form.get('model') or '').strip()
        year = request.form.get('year')
        auction_type = (request.form.get('auction_type') or '').strip()
        lot_number = (request.form.get('lot_number') or '').strip()
        auction_url = (request.form.get('auction_url') or '').strip()
        current_location = (request.form.get('current_location') or '').strip()
        purchase_date = request.form.get('purchase_date')
        # Combined auction price including fees (new single field)
        auction_total_usd = request.form.get('auction_total_usd')
        # Fallback support for older clients posting separate fields
        purchase_price = request.form.get('purchase_price')
        auction_fees = request.form.get('auction_fees')
        local_transport = request.form.get('local_transport')
        # Optional region + precomputed OMR shipping/transport from UI
        region_val = (request.form.get('region') or '').strip()
        shipping_price_omr = request.form.get('shipping_price_omr')
        client_id = request.form.get('client_id')
        buyer_id = request.form.get('buyer_id')
        status_val = request.form.get('status') or 'New car'
        container_number = (request.form.get('container_number') or '').strip()
        booking_number = (request.form.get('booking_number') or '').strip()

        # ensure auction record
        auc = None
        # Ensure auction row exists if any auction field OR a buyer is provided
        if auction_type or lot_number or auction_url or buyer_id:
            auc = db.session.query(Auction).filter(
                db.func.lower(Auction.provider) == auction_type.lower(),
                Auction.lot_number == lot_number
            ).first()
            if not auc:
                auc = Auction(provider=auction_type or None, lot_number=lot_number or None, auction_url=auction_url or None)
                db.session.add(auc)
                db.session.flush()
            else:
                if auction_url:
                    auc.auction_url = auction_url
            # Link selected buyer (and its customer) to the auction
            try:
                b = db.session.get(Buyer, int(buyer_id)) if buyer_id else None
            except Exception:
                b = None
            if b:
                auc.buyer_id = b.id
                if not getattr(auc, 'customer_id', None) and getattr(b, 'customer_id', None):
                    auc.customer_id = b.customer_id

        v = Vehicle(
            vin=vin or None,
            make=make or None,
            model=model or None,
            year=int(year) if year else None,
            auction_id=auc.id if auc else None,
            owner_customer_id=int(client_id) if client_id else None,
            status=status_val,
            current_location=current_location or None,
            container_number=container_number or None,
            booking_number=booking_number or None,
        )
        # Set purchase price (USD) from combined total if provided; otherwise sum legacy fields
        total_usd_val = None
        try:
            if auction_total_usd and str(auction_total_usd).strip():
                total_usd_val = float(auction_total_usd)
            else:
                # Backward-compat: combine price + fees if both provided
                pp = float(purchase_price) if purchase_price else 0.0
                af = float(auction_fees) if auction_fees else 0.0
                total = pp + af
                if total > 0:
                    total_usd_val = total
        except Exception:
            total_usd_val = None
        v.purchase_price_usd = total_usd_val
        if purchase_date:
            try:
                v.purchase_date = datetime.fromisoformat(purchase_date)
            except Exception:
                pass
        db.session.add(v)
        db.session.flush()

        # If no client selected but auction (via buyer) linked to a customer, inherit it
        if not client_id and auc and getattr(auc, 'customer_id', None):
            v.owner_customer_id = auc.customer_id

        # Ensure per-vehicle sub-ledger exists
        try:
            from ..accounting.routes import _ensure_vehicle_accounts, create_vehicle_chart
            _ensure_vehicle_accounts(v)
            if v.owner_customer_id:
                create_vehicle_chart(v.id, v.owner_customer_id)
        except Exception:
            # Non-blocking
            pass

        # If purchase price/date provided and customer is known, create draft invoice
        try:
            should_invoice = bool(v.owner_customer_id and v.purchase_price_usd)
        except Exception:
            should_invoice = False
        if should_invoice:
            usd_to_omr = float(current_app.config.get('OMR_EXCHANGE_RATE', 0.385))
            amount_omr = float(v.purchase_price_usd or 0) * usd_to_omr
            # Create an initial car invoice linked to this vehicle so the accountant dashboard
            # correctly classifies it as a car cost once paid.
            inv = Invoice(
                invoice_number=f"INV-{int(datetime.utcnow().timestamp())}",
                customer_id=v.owner_customer_id,
                vehicle_id=v.id,
                invoice_type='CAR',
                status='Draft',
                total_omr=amount_omr,
            )
            db.session.add(inv)
            db.session.flush()
            db.session.add(InvoiceItem(invoice_id=inv.id, vehicle_id=v.id, description=f"Vehicle {v.vin} purchase", amount_omr=amount_omr))

        # Optional costs: local transport/shipping (OMR in InternationalCost)
        try:
            # Gather values; store OMR amounts in InternationalCost
            cost_row = None
            def ensure_cost_row() -> InternationalCost:
                nonlocal cost_row
                if cost_row is None:
                    cost_row = db.session.query(InternationalCost).filter_by(vehicle_id=v.id).first()
                    if not cost_row:
                        cost_row = InternationalCost(vehicle_id=v.id)
                        db.session.add(cost_row)
                        db.session.flush()
                return cost_row

            # Local transport (OMR)
            if local_transport:
                try:
                    lt_omr = float(local_transport)
                except Exception:
                    lt_omr = None
                if lt_omr is not None:
                    ensure_cost_row().local_transport_omr = lt_omr

            # Shipping price from region (OMR) — store into misc_omr to include in totals
            if shipping_price_omr:
                try:
                    shp_omr = float(shipping_price_omr)
                except Exception:
                    shp_omr = None
                if shp_omr is not None:
                    cr = ensure_cost_row()
                    try:
                        existing = float(cr.misc_omr or 0)
                    except Exception:
                        existing = 0.0
                    cr.misc_omr = (existing or 0) + shp_omr
        except Exception:
            pass

        # save uploaded photos
        photos = request.files.getlist('photos') or []
        for f in photos:
            saved = save_uploaded_file(vin, f)
            if saved:
                db.session.add(Document(vehicle_id=v.id, doc_type='Vehicle Photo', file_path=saved))

        # optional auction invoice upload
        auction_invoice = request.files.get('auction_invoice')
        if auction_invoice and getattr(auction_invoice, 'filename', ''):
            saved = save_uploaded_file(v.vin or str(v.id), auction_invoice, filename_hint='auction_invoice')
            if saved:
                db.session.add(Document(vehicle_id=v.id, doc_type='Auction Invoice', file_path=saved))

        try:
            db.session.commit()
            notify(f"Vehicle {v.vin} added", 'Vehicle', v.id)
            return render_template('operations/cars_success.html', vehicle=v)
        except Exception:
            db.session.rollback()
    return render_template('operations/car_form.html', customers=customers, regions=regions, buyers=buyers)


@ops_bp.route('/cars/<int:vehicle_id>/edit', methods=['GET', 'POST'])
@role_required('employee', 'admin')
def cars_edit(vehicle_id: int):
    v = db.session.get(Vehicle, vehicle_id)
    if not v:
        return ("Not found", 404)
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    buyers = (
        db.session.query(Buyer)
        .order_by(db.func.coalesce(Buyer.buyer_number, ''), Buyer.name.asc())
        .all()
    )
    regions = db.session.query(ShippingRegionPrice).order_by(ShippingRegionPrice.region_code.asc()).all()
    if request.method == 'POST':
        v.make = (request.form.get('make') or '').strip() or v.make
        v.model = (request.form.get('model') or '').strip() or v.model
        try:
            v.year = int(request.form.get('year') or v.year or 0) or v.year
        except Exception:
            pass
        loc_val = (request.form.get('current_location') or '').strip()
        if loc_val:
            v.current_location = loc_val
        status_val = (request.form.get('status') or '').strip()
        if status_val and status_val != v.status:
            v.status = status_val
            notify(f"Vehicle {v.vin} status updated to {v.status}", 'Vehicle', v.id)
        container_val = (request.form.get('container_number') or '').strip()
        booking_val = (request.form.get('booking_number') or '').strip()
        v.container_number = container_val or None
        v.booking_number = booking_val or None
        client_id = request.form.get('client_id')
        buyer_id = request.form.get('buyer_id')
        v.owner_customer_id = int(client_id) if client_id else None
        # update auction fields if vehicle has auction
        auc_type = (request.form.get('auction_type') or '').strip()
        lot_number = (request.form.get('lot_number') or '').strip()
        auction_url = (request.form.get('auction_url') or '').strip()
        if auc_type or lot_number or auction_url or buyer_id:
            auc = v.auction
            if not auc:
                auc = Auction(provider=auc_type or None, lot_number=lot_number or None, auction_url=auction_url or None)
                db.session.add(auc)
                db.session.flush()
                v.auction_id = auc.id
            else:
                if auc_type:
                    auc.provider = auc_type
                if lot_number:
                    auc.lot_number = lot_number
                if auction_url:
                    auc.auction_url = auction_url
            # Link selected buyer (and its customer) to the auction
            try:
                b = db.session.get(Buyer, int(buyer_id)) if buyer_id else None
            except Exception:
                b = None
            if b:
                auc.buyer_id = b.id
                if not getattr(auc, 'customer_id', None) and getattr(b, 'customer_id', None):
                    auc.customer_id = b.customer_id
                # If client not explicitly selected, align vehicle owner with buyer's customer
                if not client_id and getattr(b, 'customer_id', None):
                    v.owner_customer_id = b.customer_id
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return render_template('operations/car_form.html', vehicle=v, customers=customers, regions=regions, buyers=buyers)


@ops_bp.route('/cars/<int:vehicle_id>/delete', methods=['POST'])
@role_required('employee', 'admin')
def cars_delete(vehicle_id: int):
    v = db.session.get(Vehicle, vehicle_id)
    if v:
        db.session.delete(v)
        try:
            db.session.commit(); notify(f"Vehicle {v.vin} deleted", 'Vehicle', vehicle_id, level='warning')
        except Exception:
            db.session.rollback()
    return ("", 204)


@ops_bp.route('/cars/<int:vehicle_id>/upload', methods=['POST'])
@role_required('employee', 'admin')
def cars_upload(vehicle_id: int):
    v = db.session.get(Vehicle, vehicle_id)
    if not v:
        return ("Not found", 404)
    files = request.files.getlist('files') or []
    for f in files:
        saved = save_uploaded_file(v.vin or str(v.id), f)
        if saved:
            db.session.add(Document(vehicle_id=v.id, doc_type='Vehicle Doc', file_path=saved))
            notify(f"New document added for {v.vin}", 'Vehicle', v.id)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return ("", 204)


@ops_bp.route('/cars/export.csv')
@role_required('employee', 'admin')
def cars_export():
    import csv
    from io import StringIO
    rows = db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).all()
    buf = StringIO(); w = csv.writer(buf)
    w.writerow(['VIN','Make','Model','Year','Client','Status'])
    for v in rows:
        w.writerow([v.vin, v.make, v.model, v.year or '', (v.owner.display_name if v.owner else ''), v.status])
    buf.seek(0)
    from flask import send_file
    from io import BytesIO
    b = BytesIO(buf.read().encode('utf-8-sig'))
    b.seek(0)
    return send_file(b, mimetype='text/csv', as_attachment=True, download_name='cars.csv')


# Shipments Management
@ops_bp.route('/shipments')
@role_required('employee', 'admin')
def shipments_list():
    shipments = db.session.query(Shipment).order_by(Shipment.created_at.desc()).limit(200).all()
    # precompute cars count per shipment
    ids = [s.id for s in shipments]
    counts = {i: 0 for i in ids}
    if ids:
        for sid, cnt in db.session.query(VehicleShipment.shipment_id, db.func.count(VehicleShipment.id)).filter(VehicleShipment.shipment_id.in_(ids)).group_by(VehicleShipment.shipment_id):
            counts[sid] = cnt
    return render_template('operations/shipments_list.html', shipments=shipments, cars_count=counts)


@ops_bp.route('/shipments/new', methods=['GET','POST'])
@role_required('employee', 'admin')
def shipments_new():
    vehicles = db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(200).all()
    if request.method == 'POST':
        s = Shipment(
            shipment_number=(request.form.get('shipment_number') or f"SHP-{int(datetime.utcnow().timestamp())}"),
            type=request.form.get('type') or None,
            origin_port=request.form.get('origin_port') or None,
            destination_port=request.form.get('destination_port') or None,
            shipping_company=request.form.get('shipping_company') or None,
            container_number=request.form.get('container_number') or None,
            status=request.form.get('status') or 'Open',
        )
        # dates
        for fld in ('departure_date','arrival_date'):
            val = request.form.get(fld)
            if val:
                try:
                    setattr(s, fld, datetime.fromisoformat(val))
                except Exception:
                    pass
        # costs
        try:
            s.cost_freight_usd = float(request.form.get('cost_freight_usd') or 0)
        except Exception:
            pass
        try:
            s.cost_insurance_usd = float(request.form.get('cost_insurance_usd') or 0)
        except Exception:
            pass
        db.session.add(s)
        db.session.flush()

        # attach vehicles
        vehicle_ids = request.form.getlist('vehicle_ids')
        for vid in vehicle_ids:
            try:
                db.session.add(VehicleShipment(vehicle_id=int(vid), shipment_id=s.id))
            except Exception:
                pass

        # optional BOL upload
        bol = request.files.get('bol')
        if bol:
            saved = save_uploaded_file(f'shipment_{s.id}', bol, filename_hint='bol')
            if saved:
                db.session.add(Document(shipment_id=s.id, doc_type='Bill of Lading', file_path=saved))

        try:
            db.session.commit(); notify(f"Shipment {s.shipment_number} created", 'Shipment', s.id)
            return render_template('operations/shipment_form.html', shipment=s, vehicles=vehicles, saved=True)
        except Exception:
            db.session.rollback()

    return render_template('operations/shipment_form.html', vehicles=vehicles)


@ops_bp.route('/shipments/<int:shipment_id>/edit', methods=['GET','POST'])
@role_required('employee', 'admin')
def shipments_edit(shipment_id: int):
    s = db.session.get(Shipment, shipment_id)
    if not s:
        return ("Not found", 404)
    vehicles = db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(200).all()
    if request.method == 'POST':
        for fld in ('type','origin_port','destination_port','shipping_company','container_number','status'):
            val = request.form.get(fld)
            if val is not None:
                setattr(s, fld, val)
        for fld in ('departure_date','arrival_date'):
            val = request.form.get(fld)
            if val:
                try:
                    setattr(s, fld, datetime.fromisoformat(val))
                except Exception:
                    pass
        for fld in ('cost_freight_usd','cost_insurance_usd'):
            val = request.form.get(fld)
            if val:
                try:
                    setattr(s, fld, float(val))
                except Exception:
                    pass

        # reattach vehicles if provided
        if request.form.get('update_vehicles') == '1':
            db.session.query(VehicleShipment).filter_by(shipment_id=s.id).delete()
            for vid in request.form.getlist('vehicle_ids'):
                try:
                    db.session.add(VehicleShipment(vehicle_id=int(vid), shipment_id=s.id))
                except Exception:
                    pass
        try:
            db.session.commit(); notify(f"Shipment {s.shipment_number} updated", 'Shipment', s.id)
        except Exception:
            db.session.rollback()
    return render_template('operations/shipment_form.html', shipment=s, vehicles=vehicles)


@ops_bp.route('/shipments/<int:shipment_id>/status', methods=['POST'])
@role_required('employee', 'admin')
def shipments_update_status(shipment_id: int):
    s = db.session.get(Shipment, shipment_id)
    if not s:
        return ("Not found", 404)
    old = s.status or ''
    s.status = request.form.get('status') or s.status
    try:
        db.session.commit(); notify(f"Shipment {s.shipment_number} status: {old} ➜ {s.status}", 'Shipment', s.id)
    except Exception:
        db.session.rollback()
    return ("", 204)


@ops_bp.route('/shipments/<int:shipment_id>/docs/upload', methods=['POST'])
@role_required('employee', 'admin')
def shipments_upload_doc(shipment_id: int):
    s = db.session.get(Shipment, shipment_id)
    if not s:
        return ("Not found", 404)
    f = request.files.get('file')
    saved = save_uploaded_file(f'shipment_{s.id}', f)
    if saved:
        db.session.add(Document(shipment_id=s.id, doc_type='Attachment', file_path=saved))
        notify(f"Document added to shipment {s.shipment_number}", 'Shipment', s.id)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return ("", 204)


@ops_bp.route('/shipments/<int:shipment_id>/docs/<int:doc_id>/delete', methods=['POST'])
@role_required('employee', 'admin')
def shipments_delete_doc(shipment_id: int, doc_id: int):
    doc = db.session.get(Document, doc_id)
    if doc and doc.shipment_id == shipment_id:
        db.session.delete(doc)
        try:
            db.session.commit(); notify("Shipment document deleted", 'Shipment', shipment_id, level='warning')
        except Exception:
            db.session.rollback()
    return ("", 204)


@ops_bp.route('/shipments/export.csv')
@role_required('employee', 'admin')
def shipments_export():
    import csv
    from io import StringIO, BytesIO
    rows = db.session.query(Shipment).order_by(Shipment.created_at.desc()).all()
    buf = StringIO(); w = csv.writer(buf)
    w.writerow(['Shipment No','Type','Port From','Port To','Departure','Arrival','Status','Cars'])
    for s in rows:
        cars_cnt = db.session.query(VehicleShipment).filter_by(shipment_id=s.id).count()
        w.writerow([
            s.shipment_number, s.type, s.origin_port, s.destination_port,
            (s.departure_date.strftime('%Y-%m-%d') if s.departure_date else ''),
            (s.arrival_date.strftime('%Y-%m-%d') if s.arrival_date else ''), s.status, cars_cnt
        ])
    buf.seek(0)
    from flask import send_file
    b = BytesIO(buf.read().encode('utf-8-sig')); b.seek(0)
    return send_file(b, mimetype='text/csv', as_attachment=True, download_name='shipments.csv')


# Customers Management
@ops_bp.route('/customers')
@role_required('employee', 'admin')
def customers_list():
    q = db.session.query(Customer)
    name = (request.args.get('name') or '').strip()
    email = (request.args.get('email') or '').strip()
    if name:
        q = q.filter(db.func.lower(Customer.company_name).like(db.func.lower(f"%{name}%")))
    if email:
        q = q.filter(db.func.lower(Customer.email).like(db.func.lower(f"%{email}%")))
    customers = q.order_by(Customer.company_name.asc()).limit(200).all()
    return render_template('operations/customers_list.html', customers=customers)


@ops_bp.route('/customers/new', methods=['GET','POST'])
@role_required('employee', 'admin')
def customers_new():
    if request.method == 'POST':
        company_name = (request.form.get('company_name') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        email = (request.form.get('email') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        country = (request.form.get('country') or '').strip()
        address = (request.form.get('address') or '').strip()
        account_number = (request.form.get('account_number') or '').strip()
        password = (request.form.get('password') or '').strip()
        password_confirm = (request.form.get('password_confirm') or '').strip()
        price_category = (request.form.get('price_category') or 'normal').strip().lower()
        if price_category not in {"normal","container","vip","vvip"}:
            price_category = 'normal'

        # Build a transient customer to repopulate the form on validation errors
        c = Customer(
            company_name=company_name or None,
            full_name=full_name or None,
            email=email or None,
            phone=phone or None,
            country=country or None,
            address=address or None,
            account_number=account_number or None,
            price_category=price_category,
        )

        # Required fields on create: name (company or full), phone, country, card number, email, password
        has_name = bool(company_name or full_name)
        has_phone = bool(phone)
        has_country = bool(country)
        has_card = bool(account_number)
        has_email = bool(email)
        has_password = bool(password)

        if not has_name:
            flash(_('الاسم مطلوب (اسم الشركة أو الاسم الكامل)'), 'danger')
        if not has_phone:
            flash(_('رقم الجوال مطلوب'), 'danger')
        if not has_country:
            flash(_('الدولة مطلوبة'), 'danger')
        if not has_card:
            flash(_('رقم البطاقة مطلوب'), 'danger')
        if not has_email:
            flash(_('البريد الإلكتروني مطلوب'), 'danger')
        if not has_password:
            flash(_('كلمة المرور مطلوبة'), 'danger')
        if password and password_confirm and password != password_confirm:
            flash(_('تأكيد كلمة المرور غير مطابق'), 'danger')
        if not (has_name and has_phone and has_country and has_card and has_email and has_password and (password == password_confirm)):
            return render_template('operations/customer_form.html', customer=c)

        # Ensure user email is unique for login
        try:
            existing = (
                db.session.query(User)
                .filter(db.func.lower(User.email) == email.lower())
                .first()
            )
        except Exception:
            existing = None
        if existing:
            flash(_('هذا البريد الإلكتروني مستخدم بالفعل'), 'danger')
            return render_template('operations/customer_form.html', customer=c)

        # Create a login user for this customer and set provided password

        # Ensure 'customer' role exists
        role_customer = db.session.query(Role).filter(db.func.lower(Role.name) == 'customer').first()
        if not role_customer:
            role_customer = Role(name='customer')
            db.session.add(role_customer)
            db.session.flush()

        user = User(
            name=(company_name or full_name) or None,
            email=email,
            phone=phone or None,
            role=role_customer,
            active=True,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.flush()

        # Link customer to the created user
        c.user_id = user.id
        db.session.add(c)
        # Ensure per-client sub-ledger exists
        try:
            # Lazy import to avoid circulars
            from ..accounting.routes import _ensure_client_accounts
            _ensure_client_accounts(c)
        except Exception:
            # Non-blocking
            pass

        try:
            db.session.commit()
            notify(f"Customer {c.company_name or c.full_name} added", 'Customer', c.id)
            flash(_('Customer saved successfully'), 'success')
            # Provide login credentials (email only). Avoid flashing passwords.
            try:
                flash(_('Email: %(email)s', email=email), 'info')
            except Exception:
                flash(f"Email: {email}", 'info')
            return redirect(url_for('ops.customers_edit', customer_id=c.id))
        except Exception as e:
            current_app.logger.exception('Failed to save customer')
            db.session.rollback()
            # Provide a helpful message for common problems (e.g., missing migrations or unique constraints)
            message = _('Failed to save customer')
            text = str(e).lower()
            if 'no such column' in text or 'does not exist' in text:
                message = _('Database schema is outdated. Please run the database migrations.')
            elif 'unique constraint' in text or 'unique failed' in text:
                if 'users' in text or 'email' in text:
                    message = _('User email already exists')
                else:
                    message = _('Account number already exists')
            flash(message, 'danger')
            return render_template('operations/customer_form.html', customer=c)
    return render_template('operations/customer_form.html')


@ops_bp.route('/customers/<int:customer_id>/edit', methods=['GET','POST'])
@role_required('employee', 'admin')
def customers_edit(customer_id: int):
    c = db.session.get(Customer, customer_id)
    if not c:
        return ("Not found", 404)
    if request.method == 'POST':
        for fld in ('company_name','full_name','email','phone','country','address','account_number'):
            val = request.form.get(fld)
            if val is not None:
                setattr(c, fld, val)

        # Update price category if provided
        pc = request.form.get('price_category')
        if pc is not None:
            pc_norm = (pc or '').strip().lower()
            if pc_norm in {"normal","container","vip","vvip"}:
                c.price_category = pc_norm or c.price_category

        # Optional password change for linked user
        new_password = (request.form.get('password') or '').strip()
        new_password_confirm = (request.form.get('password_confirm') or '').strip()
        if new_password or new_password_confirm:
            if not (new_password and new_password_confirm and new_password == new_password_confirm):
                flash(_('تأكيد كلمة المرور غير مطابق'), 'danger')
                return render_template('operations/customer_form.html', customer=c)
            # Ensure customer has a linked user; if not, create one minimally
            user = None
            try:
                if c.user_id:
                    user = db.session.get(User, c.user_id)
            except Exception:
                user = None
            if not user:
                # Ensure 'customer' role exists
                role_customer = db.session.query(Role).filter(db.func.lower(Role.name) == 'customer').first()
                if not role_customer:
                    role_customer = Role(name='customer')
                    db.session.add(role_customer)
                    db.session.flush()
                user = User(
                    name=(c.company_name or c.full_name) or None,
                    email=c.email,
                    phone=c.phone or None,
                    role=role_customer,
                    active=True,
                )
                db.session.add(user)
                db.session.flush()
                c.user_id = user.id
            user.set_password(new_password)
        # Ensure per-client sub-ledger exists after edits if missing
        try:
            from ..accounting.routes import _ensure_client_accounts
            _ensure_client_accounts(c)
        except Exception:
            pass
        try:
            db.session.commit(); notify(f"Customer {c.company_name or c.full_name} updated", 'Customer', c.id)
            flash(_('Customer updated'), 'success')
        except Exception as e:
            current_app.logger.exception('Failed to update customer')
            db.session.rollback()
            flash(_('Failed to update customer'), 'danger')
    return render_template('operations/customer_form.html', customer=c)


@ops_bp.route('/customers/<int:customer_id>/delete', methods=['POST'])
@role_required('employee', 'admin')
def customers_delete(customer_id: int):
    c = db.session.get(Customer, customer_id)
    if c:
        db.session.delete(c)
        try:
            db.session.commit(); notify("Customer deleted", 'Customer', customer_id, level='warning')
        except Exception:
            db.session.rollback()
    return ("", 204)


# Calendar
@ops_bp.route('/calendar')
@role_required('employee', 'admin')
def calendar_page():
    return render_template('operations/calendar.html')


@ops_bp.route('/calendar/events.json')
@role_required('employee', 'admin')
def calendar_events():
    events = []
    for s in db.session.query(Shipment).all():
        if s.departure_date:
            events.append({
                'title': f"Depart: {s.shipment_number}",
                'start': s.departure_date.strftime('%Y-%m-%d'),
            })
        if s.arrival_date:
            events.append({
                'title': f"Arrive: {s.shipment_number}",
                'start': s.arrival_date.strftime('%Y-%m-%d'),
            })
    return jsonify(events)


# Bulk vehicle status update page (Operations)
@ops_bp.route('/cars/status', methods=['GET', 'POST'])
@role_required('employee', 'admin')
def cars_status():
    if request.method == 'POST':
        # Expect multiple repeated fields: status[vehicle_id] = new_status
        # Or pairs of vehicle_ids[] and statuses[] in the same order
        updated = 0

        # Canonical order and helpers to advance status progressively
        order = [
            'New car',
            'Cashier Payment',
            'Auction Payment',
            'Posted',
            'Towing',
            'Warehouse',
            'Loading',
            'Shipping',
            'Port',
            'On way',
            'Arrived',
            'Delivered',
        ]

        def stage_index_from_status(text: str | None) -> int:
            norm = (text or '').strip().lower()
            for idx, name in enumerate(order):
                if name.lower() == norm:
                    return idx
            return 0

        shipping_idx = stage_index_from_status('Shipping')

        def advance_vehicle_status(v: Vehicle, target_status: str) -> bool:
            # Advance vehicle status, auto-filling intermediate stages forward.
            if not target_status or target_status == v.status:
                return False
            old_idx = stage_index_from_status(v.status)
            new_idx = stage_index_from_status(target_status)
            if new_idx > old_idx:
                # Walk forward through intermediate stages and notify for each step
                for idx in range(old_idx + 1, new_idx + 1):
                    step = order[idx]
                    v.status = step
                    try:
                        notify(f"Vehicle {v.vin} status updated to {step}", 'Vehicle', v.id)
                    except Exception:
                        pass
                return True
            else:
                # Moving backward or to same/unknown: set directly and notify once
                v.status = target_status
                try:
                    notify(f"Vehicle {v.vin} status updated to {v.status}", 'Vehicle', v.id)
                except Exception:
                    pass
                return True

        updates = {}
        for key, val in (request.form or {}).items():
            if key.startswith('status_'):
                try:
                    vid = int(key.split('_', 1)[1])
                except Exception:
                    continue
                if val:
                    updates[vid] = val
            elif key.startswith('status[') and key.endswith(']'):
                try:
                    vid = int(key[7:-1])
                except Exception:
                    continue
                val = request.form.get(key)
                if val:
                    updates[vid] = val

        errors = []
        pending = []

        for vid, target_status in updates.items():
            v = db.session.get(Vehicle, vid)
            if not v:
                continue
            container_val = (request.form.get(f'container_{vid}') or '').strip()
            booking_val = (request.form.get(f'booking_{vid}') or '').strip()
            target_idx = stage_index_from_status(target_status)
            requires_shipping_fields = target_idx >= shipping_idx
            existing_container = (v.container_number or '').strip()
            existing_booking = (v.booking_number or '').strip()
            if requires_shipping_fields:
                if not (container_val or existing_container):
                    errors.append(_('Container number is required for %(vin)s', vin=v.vin or vid))
                if not (booking_val or existing_booking):
                    errors.append(_('Booking number is required for %(vin)s', vin=v.vin or vid))
            pending.append((v, target_status, container_val, booking_val))

        if errors:
            db.session.rollback()
            return jsonify({'errors': errors}), 400

        for v, target_status, container_val, booking_val in pending:
            existing_container = (v.container_number or '').strip()
            existing_booking = (v.booking_number or '').strip()
            fields_changed = False
            if container_val and container_val != existing_container:
                v.container_number = container_val
                fields_changed = True
            if booking_val and booking_val != existing_booking:
                v.booking_number = booking_val
                fields_changed = True
            if advance_vehicle_status(v, target_status):
                updated += 1
            elif fields_changed:
                updated += 1
        try:
            if updated:
                db.session.commit()
            return jsonify({'updated': updated})
        except Exception:
            db.session.rollback()
            return ('', 400)

    q = db.session.query(Vehicle)
    vin = (request.args.get('vin') or '').strip()
    client_id = request.args.get('client_id')
    if vin:
        q = q.filter(db.func.lower(Vehicle.vin).like(db.func.lower(f"%{vin}%")))
    if client_id:
        try:
            q = q.filter(Vehicle.owner_customer_id == int(client_id))
        except Exception:
            pass
    cars = q.order_by(Vehicle.created_at.desc()).limit(200).all()
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    return render_template('operations/cars_status.html', cars=cars, customers=customers)

# Vehicle tracking timeline view for Operations (staff access)
@ops_bp.route('/cars/<int:vehicle_id>/tracking')
@role_required('employee', 'admin')
def vehicle_tracking(vehicle_id: int):
    from datetime import timedelta
    v = db.session.get(Vehicle, vehicle_id)
    if not v:
        return ("Not found", 404)

    # Gather shipments for this vehicle
    shipments = (
        db.session.query(Shipment)
        .join(VehicleShipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(VehicleShipment.vehicle_id == v.id)
        .order_by(Shipment.created_at.asc())
        .all()
    )
    primary = shipments[0] if shipments else None

    departed = bool(primary and primary.departure_date)
    arrived = bool(primary and primary.arrival_date)
    shipment_status = (primary.status or "").strip().lower() if primary else ""
    delivered = shipment_status == "delivered"

    norm_status = (v.status or "").strip().lower()

    def fmt_dt(dt):
        try:
            return dt.strftime("%d-%m-%Y") if dt else ""
        except Exception:
            return ""

    date_map = {
        "New car": fmt_dt(v.created_at),
        "Cashier Payment": fmt_dt(v.purchase_date) or fmt_dt(v.created_at),
        "Auction Payment": fmt_dt(v.purchase_date),
        "Posted": fmt_dt(v.created_at),
        "Towing": "",
        "Warehouse": "",
        "Loading": fmt_dt(primary.departure_date - timedelta(days=1)) if departed and primary else "",
        "Shipping": fmt_dt(primary.departure_date) if primary else "",
        "Port": fmt_dt(primary.departure_date) if primary else "",
        "On way": fmt_dt(primary.departure_date) if primary else "",
        "Arrived": fmt_dt(primary.arrival_date) if primary else "",
        "Delivered": fmt_dt(primary.arrival_date) if primary else "",
    }

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

    # Determine current stage index from explicit status and shipment signals
    def stage_index_from_status(text: str | None) -> int:
        norm = (text or "").strip().lower()
        for idx, name in enumerate(order):
            if name.lower() == norm:
                return idx
        return 0

    current_idx = stage_index_from_status(v.status)
    if departed and not arrived:
        current_idx = max(current_idx, order.index("On way"))
    if arrived:
        current_idx = max(current_idx, order.index("Arrived"))
    if delivered:
        current_idx = max(current_idx, order.index("Delivered"))

    stages = []
    for idx, name in enumerate(order):
        stages.append(
            {
                "name": name,
                "icon": icons.get(name, "fa-circle"),
                "completed": idx <= current_idx,  # Auto-complete all prior stages
                "date_str": date_map.get(name, ""),
            }
        )

    lot_number = v.auction.lot_number if v.auction and v.auction.lot_number else "-"

    # Summary fields (align with public tracking page behavior)
    container_number = "-"
    arrival_date = "-"
    total_cost_omr = None
    try:
        # Prefer primary shipment for quick summary
        if primary:
            try:
                container_number = (primary.container_number or "-").strip() if getattr(primary, "container_number", None) else "-"
            except Exception:
                container_number = "-"
            arrival_date = fmt_dt(getattr(primary, "arrival_date", None)) or "-"
        if (not container_number or container_number == "-") and getattr(v, "container_number", None):
            try:
                container_number = (v.container_number or "-").strip() or "-"
            except Exception:
                container_number = "-"

        # Compute total cost (OMR) from InternationalCost when available
        try:
            from decimal import Decimal
            from ...models import InternationalCost

            cost_row = db.session.query(InternationalCost).filter_by(vehicle_id=v.id).first()
            if cost_row:
                def dec(x):
                    try:
                        return Decimal(str(x or 0))
                    except Exception:
                        return Decimal('0')

                usd_sum = dec(v.purchase_price_usd) + dec(cost_row.freight_usd) + dec(cost_row.insurance_usd) + dec(cost_row.auction_fees_usd)
                omr_rate = Decimal(str(current_app.config.get("OMR_EXCHANGE_RATE", 0.385)))
                omr_from_usd = usd_sum * omr_rate
                omr_local = dec(cost_row.customs_omr) + dec(cost_row.vat_omr) + dec(cost_row.local_transport_omr) + dec(cost_row.misc_omr)
                total_cost_omr = omr_from_usd + omr_local
        except Exception:
            # keep defaults if any issue in cost calculation
            total_cost_omr = total_cost_omr
    except Exception:
        # Fail-safe: keep defaults
        container_number = container_number or "-"
        arrival_date = arrival_date or "-"
        total_cost_omr = total_cost_omr

    return render_template(
        "tracking.html",
        vin=(v.vin or "").upper(),
        lot_number=lot_number,
        vehicle=v,
        stages=stages,
        # Provide values to avoid template UndefinedError in staff view
        container_number=container_number,
        arrival_date=arrival_date,
        total_cost_omr=total_cost_omr,
        stage_details={},
    )
