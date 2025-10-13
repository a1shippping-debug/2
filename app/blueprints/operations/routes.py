from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app, send_from_directory
from flask_login import login_required
from ...security import role_required
from ...extensions import db
from ...models import Vehicle, Shipment, Customer, VehicleShipment, Document, Notification, User
from ...utils.notify import create_notification
from datetime import datetime
import os

ops_bp = Blueprint("ops", __name__, template_folder="templates/operations")

@ops_bp.route("/dashboard")
@role_required("employee", "admin")
def dashboard():
    # KPI cards
    total_vehicles = db.session.query(Vehicle).count()
    in_transit = db.session.query(Shipment).filter(Shipment.status == "In Transit").count()
    arrived = db.session.query(Shipment).filter(Shipment.status == "Arrived").count()
    open_shipments = db.session.query(Shipment).filter(Shipment.status.in_(["Open", "In Transit")).count()
    customers_count = db.session.query(Customer).count()

    # monthly shipped vehicles chart (count of VehicleShipment by month of departure)
    def last_n_months(n=12):
        months = []
        now = datetime.utcnow()
        dt = datetime(now.year, now.month, 1)
        for _ in range(n):
            months.append(dt)
            if dt.month == 1:
                dt = datetime(dt.year - 1, 12, 1)
            else:
                dt = datetime(dt.year, dt.month - 1, 1)
        return list(reversed(months))

    month_labels = []
    shipped_counts = []
    months = last_n_months()
    for start in months:
        if start.month == 12:
            end = datetime(start.year + 1, 1, 1)
        else:
            end = datetime(start.year, start.month + 1, 1)
        count = (
            db.session.query(VehicleShipment)
            .join(Shipment, Shipment.id == VehicleShipment.shipment_id)
            .filter(Shipment.departure_date >= start, Shipment.departure_date < end)
            .count()
        )
        month_labels.append(start.strftime("%b"))
        shipped_counts.append(count)

    # latest 5 vehicles
    latest_vehicles = db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(5).all()

    return render_template(
        "operations/dashboard.html",
        kpi={
            "total_vehicles": total_vehicles,
            "in_transit": in_transit,
            "arrived": arrived,
            "open_shipments": open_shipments,
            "customers": customers_count,
        },
        chart={"months": month_labels, "shipped_counts": shipped_counts},
        latest_vehicles=latest_vehicles,
    )


# Cars Management
@ops_bp.route("/cars")
@role_required("employee", "admin")
def cars_list():
    q = db.session.query(Vehicle)
    status = request.args.get("status")
    vin = request.args.get("vin")
    customer_id = request.args.get("customer_id")
    if status:
        q = q.filter(Vehicle.status == status)
    if vin:
        q = q.filter(Vehicle.vin.ilike(f"%{vin}%"))
    if customer_id:
        try:
            cid = int(customer_id)
            q = q.filter(Vehicle.owner_customer_id == cid)
        except Exception:
            pass
    vehicles = q.order_by(Vehicle.created_at.desc()).all()
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    return render_template("operations/cars_list.html", vehicles=vehicles, customers=customers)


@ops_bp.route("/cars/new", methods=["GET", "POST"])
@role_required("employee", "admin")
def cars_new():
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    if request.method == "POST":
        form = request.form
        vehicle = Vehicle(
            vin=(form.get("vin") or "").strip().upper(),
            make=form.get("make"),
            model=form.get("model"),
            year=int(form.get("year") or 0) or None,
            lot_number=form.get("lot_number"),
            auction_type=form.get("auction_type"),
            purchase_date=datetime.strptime(form.get("purchase_date"), "%Y-%m-%d") if form.get("purchase_date") else None,
            purchase_price_usd=float(form.get("purchase_price_usd") or 0) or None,
            auction_fees_usd=float(form.get("auction_fees_usd") or 0) or None,
            local_transport_cost_usd=float(form.get("local_transport_cost_usd") or 0) or None,
            owner_customer_id=int(form.get("customer_id")) if form.get("customer_id") else None,
            status=form.get("status") or "Purchased",
        )
        if not vehicle.vin:
            flash("VIN is required", "danger")
            return render_template("operations/car_form.html", customers=customers, form=form)
        if db.session.query(Vehicle).filter_by(vin=vehicle.vin).first():
            flash("VIN already exists", "danger")
            return render_template("operations/car_form.html", customers=customers, form=form)
        db.session.add(vehicle)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to add vehicle", "danger")
            return render_template("operations/car_form.html", customers=customers, form=form)

        # handle photos upload
        for field in ("photo_before", "photo_after"):
            file = request.files.get(field)
            if file and file.filename:
                save_entity_document(file, entity_type="vehicle", entity_id=vehicle.id, doc_type="Vehicle Photo")

        create_notification(f"Vehicle {vehicle.vin} created", url_for("ops.cars_edit", vehicle_id=vehicle.id))
        flash("Vehicle added", "success")
        return redirect(url_for("ops.cars_list"))
    return render_template("operations/car_form.html", customers=customers)


@ops_bp.route("/cars/<int:vehicle_id>/edit", methods=["GET", "POST"])
@role_required("employee", "admin")
def cars_edit(vehicle_id: int):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        abort(404)
    customers = db.session.query(Customer).order_by(Customer.company_name.asc()).all()
    if request.method == "POST":
        form = request.form
        vehicle.make = form.get("make")
        vehicle.model = form.get("model")
        vehicle.year = int(form.get("year") or 0) or None
        vehicle.lot_number = form.get("lot_number")
        vehicle.auction_type = form.get("auction_type")
        vehicle.purchase_date = datetime.strptime(form.get("purchase_date"), "%Y-%m-%d") if form.get("purchase_date") else None
        vehicle.purchase_price_usd = float(form.get("purchase_price_usd") or 0) or None
        vehicle.auction_fees_usd = float(form.get("auction_fees_usd") or 0) or None
        vehicle.local_transport_cost_usd = float(form.get("local_transport_cost_usd") or 0) or None
        vehicle.owner_customer_id = int(form.get("customer_id")) if form.get("customer_id") else None
        vehicle.status = form.get("status") or vehicle.status
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to update vehicle", "danger")
            return render_template("operations/car_form.html", customers=customers, form=form, vehicle=vehicle)

        # optional new photos
        for field in ("photo_before", "photo_after"):
            file = request.files.get(field)
            if file and file.filename:
                save_entity_document(file, entity_type="vehicle", entity_id=vehicle.id, doc_type="Vehicle Photo")

        create_notification(f"Vehicle {vehicle.vin} updated", url_for("ops.cars_edit", vehicle_id=vehicle.id))
        flash("Vehicle updated", "success")
        return redirect(url_for("ops.cars_list"))
    return render_template("operations/car_form.html", customers=customers, vehicle=vehicle)


@ops_bp.route("/cars/<int:vehicle_id>/delete", methods=["POST"])
@role_required("employee", "admin")
def cars_delete(vehicle_id: int):
    vehicle = db.session.get(Vehicle, vehicle_id)
    if not vehicle:
        abort(404)
    db.session.delete(vehicle)
    try:
        db.session.commit()
        flash("Vehicle deleted", "success")
    except Exception:
        db.session.rollback()
        flash("Failed to delete vehicle", "danger")
    return redirect(url_for("ops.cars_list"))


# Shipments Management
@ops_bp.route("/shipments")
@role_required("employee", "admin")
def shipments_list():
    shipments = db.session.query(Shipment).order_by(Shipment.created_at.desc()).all()
    return render_template("operations/shipments_list.html", shipments=shipments)


@ops_bp.route("/shipments/new", methods=["GET", "POST"])
@role_required("employee", "admin")
def shipments_new():
    if request.method == "POST":
        form = request.form
        shipment = Shipment(
            shipment_number=(form.get("shipment_number") or "").strip(),
            type=form.get("type"),
            origin_port=form.get("origin_port"),
            destination_port=form.get("destination_port"),
            departure_date=datetime.strptime(form.get("departure_date"), "%Y-%m-%d") if form.get("departure_date") else None,
            arrival_date=datetime.strptime(form.get("arrival_date"), "%Y-%m-%d") if form.get("arrival_date") else None,
            shipping_company=form.get("shipping_company"),
            container_no=form.get("container_no"),
            status=form.get("status") or "Open",
            cost_freight_usd=float(form.get("cost_freight_usd") or 0) or None,
            cost_insurance_usd=float(form.get("cost_insurance_usd") or 0) or None,
        )
        if not shipment.shipment_number:
            flash("Shipment number is required", "danger")
            return render_template("operations/shipment_form.html")
        if db.session.query(Shipment).filter_by(shipment_number=shipment.shipment_number).first():
            flash("Shipment number already exists", "danger")
            return render_template("operations/shipment_form.html")
        db.session.add(shipment)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to create shipment", "danger")
            return render_template("operations/shipment_form.html")

        # attach vehicles
        vehicle_ids = request.form.getlist("vehicle_ids")
        for vid in vehicle_ids:
            try:
                vs = VehicleShipment(vehicle_id=int(vid), shipment_id=shipment.id)
                db.session.add(vs)
            except Exception:
                continue
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        # BOL upload
        bol = request.files.get("bill_of_lading")
        if bol and bol.filename:
            save_entity_document(bol, entity_type="shipment", entity_id=shipment.id, doc_type="Bill of Lading")

        create_notification(f"Shipment {shipment.shipment_number} created", url_for("ops.shipments_edit", shipment_id=shipment.id))
        flash("Shipment created", "success")
        return redirect(url_for("ops.shipments_list"))
    # GET
    vehicles = db.session.query(Vehicle).filter(Vehicle.status.in_(["Purchased", "Shipped"])) .all()
    return render_template("operations/shipment_form.html", vehicles=vehicles)


@ops_bp.route("/shipments/<int:shipment_id>/edit", methods=["GET", "POST"])
@role_required("employee", "admin")
def shipments_edit(shipment_id: int):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        abort(404)
    if request.method == "POST":
        form = request.form
        shipment.type = form.get("type")
        shipment.origin_port = form.get("origin_port")
        shipment.destination_port = form.get("destination_port")
        shipment.departure_date = datetime.strptime(form.get("departure_date"), "%Y-%m-%d") if form.get("departure_date") else None
        shipment.arrival_date = datetime.strptime(form.get("arrival_date"), "%Y-%m-%d") if form.get("arrival_date") else None
        shipment.shipping_company = form.get("shipping_company")
        shipment.container_no = form.get("container_no")
        shipment.status = form.get("status") or shipment.status
        shipment.cost_freight_usd = float(form.get("cost_freight_usd") or 0) or None
        shipment.cost_insurance_usd = float(form.get("cost_insurance_usd") or 0) or None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to update shipment", "danger")
            return render_template("operations/shipment_form.html", shipment=shipment)

        # optional documents
        bol = request.files.get("bill_of_lading")
        if bol and bol.filename:
            save_entity_document(bol, entity_type="shipment", entity_id=shipment.id, doc_type="Bill of Lading")
        create_notification(f"Shipment {shipment.shipment_number} updated", url_for("ops.shipments_edit", shipment_id=shipment.id))
        flash("Shipment updated", "success")
        return redirect(url_for("ops.shipments_list"))
    # GET
    vehicles = db.session.query(Vehicle).all()
    attached_ids = {vs.vehicle_id for vs in db.session.query(VehicleShipment).filter_by(shipment_id=shipment.id)}
    return render_template("operations/shipment_form.html", shipment=shipment, vehicles=vehicles, attached_ids=attached_ids)


@ops_bp.route("/shipments/<int:shipment_id>/attach", methods=["POST"])
@role_required("employee", "admin")
def shipments_attach(shipment_id: int):
    shipment = db.session.get(Shipment, shipment_id)
    if not shipment:
        abort(404)
    vehicle_ids = request.form.getlist("vehicle_ids")
    for vid in vehicle_ids:
        try:
            db.session.add(VehicleShipment(vehicle_id=int(vid), shipment_id=shipment.id))
        except Exception:
            continue
    try:
        db.session.commit()
        flash("Vehicles attached", "success")
    except Exception:
        db.session.rollback()
        flash("Failed to attach vehicles", "danger")
    return redirect(url_for("ops.shipments_edit", shipment_id=shipment.id))


# Customers Management
@ops_bp.route("/customers")
@role_required("employee", "admin")
def customers_list():
    q = db.session.query(Customer)
    name = request.args.get("name")
    email = request.args.get("email")
    if name:
        q = q.filter(Customer.company_name.ilike(f"%{name}%"))
    if email:
        q = q.join(User, isouter=True).filter(User.email.ilike(f"%{email}%"))
    customers = q.order_by(Customer.company_name.asc()).all()
    return render_template("operations/customers_list.html", customers=customers)


@ops_bp.route("/customers/new", methods=["GET", "POST"])
@role_required("employee", "admin")
def customers_new():
    if request.method == "POST":
        form = request.form
        customer = Customer(
            account_number=form.get("account_number"),
            company_name=form.get("company_name"),
            address=form.get("address"),
        )
        db.session.add(customer)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to add customer", "danger")
            return render_template("operations/customer_form.html")
        flash("Customer added", "success")
        return redirect(url_for("ops.customers_list"))
    return render_template("operations/customer_form.html")


@ops_bp.route("/customers/<int:customer_id>/edit", methods=["GET", "POST"])
@role_required("employee", "admin")
def customers_edit(customer_id: int):
    customer = db.session.get(Customer, customer_id)
    if not customer:
        abort(404)
    if request.method == "POST":
        form = request.form
        customer.account_number = form.get("account_number")
        customer.company_name = form.get("company_name")
        customer.address = form.get("address")
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Failed to update customer", "danger")
            return render_template("operations/customer_form.html", customer=customer)
        flash("Customer updated", "success")
        return redirect(url_for("ops.customers_list"))
    return render_template("operations/customer_form.html", customer=customer)


@ops_bp.route("/customers/<int:customer_id>/vehicles")
@role_required("employee", "admin")
def customers_vehicles(customer_id: int):
    customer = db.session.get(Customer, customer_id)
    if not customer:
        abort(404)
    vehicles = db.session.query(Vehicle).filter(Vehicle.owner_customer_id == customer.id).all()
    return render_template("operations/customer_vehicles.html", customer=customer, vehicles=vehicles)


# Documents
def ensure_upload_dir(subpath: str) -> str:
    base = current_app.config.get("UPLOAD_FOLDER", "./app/static/uploads")
    path = os.path.join(base, subpath)
    os.makedirs(path, exist_ok=True)
    return path


def save_entity_document(file_storage, entity_type: str, entity_id: int, doc_type: str):
    filename = file_storage.filename
    # store under uploads/<vin>/ or uploads/shipment_<id>/
    subdir = f"{entity_type}_{entity_id}"
    folder = ensure_upload_dir(subdir)
    dest = os.path.join(folder, filename)
    file_storage.save(dest)
    doc = Document(entity_type=entity_type, entity_id=entity_id, doc_type=doc_type, file_path=os.path.relpath(dest))
    db.session.add(doc)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    try:
        # emit notification with contextual URL
        if entity_type == "shipment":
            url = url_for("ops.shipments_edit", shipment_id=entity_id)
        elif entity_type == "vehicle":
            url = url_for("ops.cars_edit", vehicle_id=entity_id)
        else:
            url = None
        create_notification(f"{doc_type} uploaded", url)
    except Exception:
        pass
    return dest


@ops_bp.route("/documents/<path:subdir>/<path:filename>")
@role_required("employee", "admin")
def documents_serve(subdir: str, filename: str):
    base = current_app.config.get("UPLOAD_FOLDER", "./app/static/uploads")
    directory = os.path.join(base, subdir)
    return send_from_directory(directory, filename, as_attachment=False)


# Calendar feed for shipments
@ops_bp.route("/calendar.json")
@role_required("employee", "admin")
def calendar_feed():
    events = []
    for s in db.session.query(Shipment).all():
        if s.departure_date:
            events.append({
                "id": f"ship-{s.id}-dep",
                "title": f"Depart: {s.shipment_number}",
                "start": s.departure_date.strftime("%Y-%m-%d"),
                "color": "#3b82f6"
            })
        if s.arrival_date:
            events.append({
                "id": f"ship-{s.id}-arr",
                "title": f"Arrive: {s.shipment_number}",
                "start": s.arrival_date.strftime("%Y-%m-%d"),
                "color": "#10b981"
            })
    return {"events": events}


@ops_bp.route("/calendar")
@role_required("employee", "admin")
def calendar_page():
    return render_template("operations/calendar.html")


# Notifications endpoints
@ops_bp.route("/notifications/mark_all", methods=["POST"])
@role_required("employee", "admin")
def notifications_mark_all():
    from sqlalchemy import or_
    from datetime import datetime as dt
    if getattr(getattr(getattr(current_app, 'login_manager', None), 'user_callback', None), '__call__', None) is None:
        # safeguard, but typically not needed
        return redirect(request.referrer or url_for("ops.dashboard"))
    # mark all for employee audience or direct user as read
    from flask_login import current_user
    role_name = getattr(getattr(current_user, 'role', None), 'name', None)
    if not role_name:
        return redirect(request.referrer or url_for("ops.dashboard"))
    q = db.session.query(Notification).filter(
        or_(Notification.audience_role == role_name.lower(), Notification.recipient_user_id == current_user.id),
        Notification.read_at.is_(None)
    )
    q.update({Notification.read_at: dt.utcnow()}, synchronize_session=False)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(request.referrer or url_for("ops.dashboard"))


@ops_bp.route("/notifications/<int:notif_id>/read", methods=["POST"])
@role_required("employee", "admin")
def notifications_mark_one(notif_id: int):
    from flask_login import current_user
    n = db.session.get(Notification, notif_id)
    if not n:
        abort(404)
    # simple authorization: allow if audience matches or direct recipient
    role_name = getattr(getattr(current_user, 'role', None), 'name', '').lower()
    if not (n.recipient_user_id == getattr(current_user, 'id', None) or n.audience_role == role_name):
        abort(403)
    from datetime import datetime as dt
    n.read_at = dt.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(request.referrer or url_for("ops.dashboard"))


# Documents delete
@ops_bp.route("/documents/<int:doc_id>/delete", methods=["POST"])
@role_required("employee", "admin")
def documents_delete(doc_id: int):
    doc = db.session.get(Document, doc_id)
    if not doc:
        abort(404)
    # remove file if present
    try:
        abs_path = os.path.abspath(doc.file_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception:
        pass
    db.session.delete(doc)
    try:
        db.session.commit()
        flash("Document deleted", "success")
    except Exception:
        db.session.rollback()
        flash("Failed to delete document", "danger")
    return redirect(request.referrer or url_for("ops.dashboard"))
