from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required
from ...security import role_required
from ...extensions import db
from ...models import Vehicle, Shipment, VehicleShipment, Customer, Notification, Auction, Document, CostItem
from datetime import datetime

ops_bp = Blueprint("ops", __name__, template_folder="templates/operations")


@ops_bp.route("/dashboard")
@role_required("employee", "admin")
def dashboard():
    # Summary cards
    total_cars = db.session.query(Vehicle).count()

    # Vehicles In Transit (via shipment association)
    in_transit_cars = (
        db.session.query(db.func.count(db.distinct(Vehicle.id)))
        .join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id)
        .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(db.func.lower(Shipment.status) == "in transit")
        .scalar()
        or 0
    )

    # Vehicles Arrived (arrival date set or delivered status)
    arrived_cars = (
        db.session.query(db.func.count(db.distinct(Vehicle.id)))
        .join(VehicleShipment, Vehicle.id == VehicleShipment.vehicle_id)
        .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
        .filter(
            db.or_(Shipment.arrival_date.isnot(None), db.func.lower(Shipment.status).in_(["arrived", "delivered"]))
        )
        .scalar()
        or 0
    )

    open_shipments = db.session.query(Shipment).filter(db.func.lower(Shipment.status) == "open").count()
    customers_count = db.session.query(Customer).count()

    # Monthly shipped cars (last 12 months)
    now = datetime.utcnow()
    month_labels = []
    shipped_counts = []
    dt = datetime(now.year, now.month, 1)
    months = []
    for _ in range(12):
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
    base = current_app.config.get('UPLOAD_FOLDER') or './app/static/uploads'
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
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    return render_template('operations/cars_list.html', cars=cars, customers=customers)


@ops_bp.route('/cars/new', methods=['GET', 'POST'])
@role_required('employee', 'admin')
def cars_new():
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
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
        purchase_price = request.form.get('purchase_price')
        auction_fees = request.form.get('auction_fees')
        local_transport = request.form.get('local_transport')
        client_id = request.form.get('client_id')
        status_val = request.form.get('status') or 'Purchased'

        # ensure auction record
        auc = None
        if auction_type or lot_number or auction_url:
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

        v = Vehicle(
            vin=vin or None,
            make=make or None,
            model=model or None,
            year=int(year) if year else None,
            auction_id=auc.id if auc else None,
            owner_customer_id=int(client_id) if client_id else None,
            status=status_val,
            current_location=current_location or None,
        )
        if purchase_price:
            try:
                v.purchase_price_usd = float(purchase_price)
            except Exception:
                v.purchase_price_usd = None
        if purchase_date:
            try:
                v.purchase_date = datetime.fromisoformat(purchase_date)
            except Exception:
                pass
        db.session.add(v)
        db.session.flush()

        # optional cost items
        try:
            if auction_fees:
                db.session.add(CostItem(vehicle_id=v.id, type='Auction Fees', amount_usd=float(auction_fees), description='Auction fees'))
            if local_transport:
                db.session.add(CostItem(vehicle_id=v.id, type='Local Transport', amount_usd=float(local_transport), description='Local transport'))
        except Exception:
            pass

        # save uploaded photos
        photos = request.files.getlist('photos') or []
        for f in photos:
            saved = save_uploaded_file(vin, f)
            if saved:
                db.session.add(Document(vehicle_id=v.id, doc_type='Vehicle Photo', file_path=saved))

        try:
            db.session.commit()
            notify(f"Vehicle {v.vin} added", 'Vehicle', v.id)
            return render_template('operations/cars_success.html', vehicle=v)
        except Exception:
            db.session.rollback()
    return render_template('operations/car_form.html', customers=customers)


@ops_bp.route('/cars/<int:vehicle_id>/edit', methods=['GET', 'POST'])
@role_required('employee', 'admin')
def cars_edit(vehicle_id: int):
    v = db.session.get(Vehicle, vehicle_id)
    if not v:
        return ("Not found", 404)
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
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
        client_id = request.form.get('client_id')
        v.owner_customer_id = int(client_id) if client_id else None
        # update auction fields if vehicle has auction
        auc_type = (request.form.get('auction_type') or '').strip()
        lot_number = (request.form.get('lot_number') or '').strip()
        auction_url = (request.form.get('auction_url') or '').strip()
        if auc_type or lot_number or auction_url:
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
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
    return render_template('operations/car_form.html', vehicle=v, customers=customers)


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
        w.writerow([v.vin, v.make, v.model, v.year or '', (v.owner.company_name if v.owner else ''), v.status])
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
        c = Customer(
            company_name=(request.form.get('company_name') or '').strip() or None,
            full_name=(request.form.get('full_name') or '').strip() or None,
            email=(request.form.get('email') or '').strip() or None,
            phone=(request.form.get('phone') or '').strip() or None,
            country=(request.form.get('country') or '').strip() or None,
            address=(request.form.get('address') or '').strip() or None,
            account_number=(request.form.get('account_number') or '').strip() or None,
        )
        db.session.add(c)
        try:
            db.session.commit(); notify(f"Customer {c.company_name or c.full_name} added", 'Customer', c.id)
            return render_template('operations/customer_form.html', customer=c, saved=True)
        except Exception:
            db.session.rollback()
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
        try:
            db.session.commit(); notify(f"Customer {c.company_name or c.full_name} updated", 'Customer', c.id)
        except Exception:
            db.session.rollback()
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
