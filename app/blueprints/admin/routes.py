from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, send_file
from flask_babel import gettext as _
from flask_login import login_required, current_user
from ...security import role_required
from ...extensions import db
from ...utils.audit import log_action
from ...models import (
    User,
    Role,
    Customer,
    Vehicle,
    Auction,
    Shipment,
    Invoice,
    CostItem,
    Setting,
    AuditLog,
    Backup,
)

admin_bp = Blueprint("admin", __name__, template_folder="templates/admin")

@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    # aggregate counts for top-level entities
    counts = {
        "users": db.session.query(User).count(),
        "customers": db.session.query(Customer).count(),
        "active_customers": db.session.query(User)
            .join(Role, isouter=True)
            .filter(Role.name == "customer", User.active.is_(True)).count(),
        "vehicles": db.session.query(Vehicle).count(),
        "vehicles_shipping": db.session.query(Vehicle).filter(Vehicle.status == "In Shipping").count(),
        # vehicle status breakdown for admin cards
        "vehicles_in_auction": db.session.query(Vehicle).filter(Vehicle.status == "In Auction").count(),
        "vehicles_in_warehouse": db.session.query(Vehicle).filter(Vehicle.status.in_(["In Warehouse", "Arrived Warehouse"]))
            .count(),
        "vehicles_no_title": db.session.query(Vehicle).filter(Vehicle.status == "No Title").count(),
        "vehicles_shipped": db.session.query(Vehicle).filter(Vehicle.status.in_(["In Shipping", "Shipped"]))
            .count(),
        "auctions": db.session.query(Auction).count(),
        "shipments": db.session.query(Shipment).count(),
        "open_shipments": db.session.query(Shipment).filter(Shipment.status == "Open").count(),
        "invoices": db.session.query(Invoice).count(),
        "cost_items": db.session.query(CostItem).count(),
        "audit_logs": db.session.query(AuditLog).count(),
        "backups": db.session.query(Backup).count(),
    }

    # totals
    # monthly revenue (current month)
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    totals = {
        "revenue_omr": db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0))
            .filter(Invoice.created_at >= month_start).scalar(),
    }

    # recent activity lists
    recent = {
        "vehicles": db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(5).all(),
        "shipments": db.session.query(Shipment).order_by(Shipment.created_at.desc()).limit(5).all(),
        "invoices": db.session.query(Invoice).order_by(Invoice.created_at.desc()).limit(5).all(),
        "users": db.session.query(User).order_by(User.created_at.desc()).limit(5).all(),
        "audit_logs": db.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(5).all(),
    }

    # charts data
    def month_labels(n=12):
        labels = []
        dt = datetime(now.year, now.month, 1)
        for i in range(n):
            labels.append(dt.strftime("%b"))
            # go back one month
            if dt.month == 1:
                dt = datetime(dt.year - 1, 12, 1)
            else:
                dt = datetime(dt.year, dt.month - 1, 1)
        return list(reversed(labels))

    def monthly_revenue(n=12):
        vals = []
        dt = datetime(now.year, now.month, 1)
        for i in range(n):
            start = dt
            if dt.month == 12:
                end = datetime(dt.year + 1, 1, 1)
            else:
                end = datetime(dt.year, dt.month + 1, 1)
            total = db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0))\
                .filter(Invoice.created_at >= start, Invoice.created_at < end).scalar()
            vals.append(float(total or 0))
            # go back one month
            if dt.month == 1:
                dt = datetime(dt.year - 1, 12, 1)
            else:
                dt = datetime(dt.year, dt.month - 1, 1)
        return list(reversed(vals))

    # shipments status breakdown
    status_counts = {s: 0 for s in ("Open", "In Transit", "Delivered")}
    for status, cnt in db.session.query(Shipment.status, db.func.count(Shipment.id)).group_by(Shipment.status):
        if status in status_counts:
            status_counts[status] = cnt

    chart = {
        "months": month_labels(),
        "revenue": monthly_revenue(),
        "shipment_status_labels": list(status_counts.keys()),
        "shipment_status_values": list(status_counts.values()),
    }

    return render_template("admin/dashboard.html", counts=counts, totals=totals, recent=recent, chart=chart)


# Placeholder routes for sections in sidebar
@admin_bp.route("/reports")
@role_required("admin")
def reports():
    from datetime import datetime
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from openpyxl import Workbook

    # compute monthly financials
    now = datetime.utcnow()
    labels = []
    revenue = []
    expenses = []
    dt = datetime(now.year, now.month, 1)
    for _ in range(12):
        start = dt
        end = datetime(dt.year + 1, 1, 1) if dt.month == 12 else datetime(dt.year, dt.month + 1, 1)
        labels.append(dt.strftime("%b %Y"))
        rev = db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0)).filter(Invoice.created_at >= start, Invoice.created_at < end).scalar() or 0
        # approximate expenses in OMR from USD-based costs (freight + cost items)
        usd_to_omr = 0.385
        freight = db.session.query(db.func.coalesce(db.func.sum(Shipment.cost_freight_usd), 0)).filter(Shipment.created_at >= start, Shipment.created_at < end).scalar() or 0
        costs = db.session.query(db.func.coalesce(db.func.sum(CostItem.amount_usd), 0)).filter(CostItem.id.isnot(None)).scalar() or 0
        exp = (float(freight) + float(costs)) * usd_to_omr
        revenue.append(float(rev))
        expenses.append(float(exp))
        # previous month
        if dt.month == 1:
            dt = datetime(dt.year - 1, 12, 1)
        else:
            dt = datetime(dt.year, dt.month - 1, 1)
    labels = list(reversed(labels))
    revenue = list(reversed(revenue))
    expenses = list(reversed(expenses))

    export = request.args.get("export")
    if export == "pdf":
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        y = height - 50
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, y, "Monthly Financial Report")
        y -= 30
        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"Generated: {now:%Y-%m-%d %H:%M}")
        y -= 20
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Month")
        c.drawString(200, y, "Revenue (OMR)")
        c.drawString(350, y, "Expenses (OMR)")
        c.drawString(480, y, "Profit (OMR)")
        y -= 15
        c.setFont("Helvetica", 10)
        for m, r, e in zip(labels, revenue, expenses):
            if y < 50:
                c.showPage(); y = height - 50
                c.setFont("Helvetica-Bold", 11)
                c.drawString(40, y, "Month"); c.drawString(200, y, "Revenue (OMR)"); c.drawString(350, y, "Expenses (OMR)"); c.drawString(480, y, "Profit (OMR)")
                y -= 15; c.setFont("Helvetica", 10)
            c.drawString(40, y, m)
            c.drawRightString(300, y, f"{r:,.3f}")
            c.drawRightString(450, y, f"{e:,.3f}")
            c.drawRightString(560, y, f"{(r-e):,.3f}")
            y -= 14
        c.showPage(); c.save()
        buf.seek(0)
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name="financial_report.pdf")
    elif export == "xlsx":
        wb = Workbook(); ws = wb.active; ws.title = "Financials"
        ws.append(["Month", "Revenue (OMR)", "Expenses (OMR)", "Profit (OMR)"])
        for m, r, e in zip(labels, revenue, expenses):
            ws.append([m, r, e, r - e])
        buf = BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="financial_report.xlsx")

    return render_template("admin/reports.html", chart={"months": labels, "revenue": revenue, "expenses": expenses})


@admin_bp.route("/settings", methods=["GET", "POST"])
@role_required("admin")
def settings():
    settings_row = db.session.query(Setting).first()
    if not settings_row:
        settings_row = Setting(customs_rate=0, vat_rate=0, shipping_fee=0)
        db.session.add(settings_row)
        db.session.commit()

    if request.method == "POST":
        def to_decimal(val):
            try:
                return db.session.bind.dialect.type_descriptor(db.Numeric()).python_type(val)  # not used; fallback below
            except Exception:
                try:
                    return float(val)
                except Exception:
                    return 0

        customs_rate = request.form.get("customs_rate") or 0
        vat_rate = request.form.get("vat_rate") or 0
        shipping_fee = request.form.get("shipping_fee") or 0

        try:
            settings_row.customs_rate = float(customs_rate)
            settings_row.vat_rate = float(vat_rate)
            settings_row.shipping_fee = float(shipping_fee)
            db.session.commit()
            flash(_("Settings updated"), "success")
        except Exception:
            db.session.rollback()
            flash(_("Failed to update settings"), "danger")

    return render_template("admin/settings.html", settings=settings_row)


@admin_bp.route("/activity")
@role_required("admin")
def activity_log():
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    export = request.args.get("export")
    logs = db.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(200).all()
    if export == "pdf":
        buf = BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        y = height - 40
        c.setFont("Helvetica-Bold", 16); c.drawString(40, y, "Activity Log")
        y -= 25; c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Time"); c.drawString(180, y, "User"); c.drawString(240, y, "Action"); c.drawString(340, y, "Target")
        y -= 15; c.setFont("Helvetica", 10)
        for a in logs:
            if y < 40:
                c.showPage(); y = height - 40
                c.setFont("Helvetica-Bold", 11); c.drawString(40, y, "Time"); c.drawString(180, y, "User"); c.drawString(240, y, "Action"); c.drawString(340, y, "Target")
                y -= 15; c.setFont("Helvetica", 10)
            c.drawString(40, y, str(a.timestamp)[:19])
            c.drawString(180, y, str(a.user_id or '-'))
            c.drawString(240, y, a.action)
            c.drawString(340, y, f"{a.target_type}#{a.target_id}")
            y -= 13
        c.showPage(); c.save(); buf.seek(0)
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name="activity_log.pdf")
    return render_template("admin/activity_log.html", logs=logs)

@admin_bp.route("/users")
@role_required("admin")
def users_list():
    # allow filtering by role/status
    q = db.session.query(User)
    role = request.args.get("role")
    active = request.args.get("active")
    if role:
        q = q.join(Role, isouter=True).filter(Role.name == role)
    if active in ("true", "false"):
        q = q.filter(User.active.is_(active == "true"))
    users = q.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@role_required("admin")
def users_new():

    roles = db.session.query(Role).order_by(Role.name.asc()).all()
    if not roles:
        flash(
            _("No roles found. Initialize roles first from Admin Dashboard Quick Links."),
            "danger",
        )

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        role_id_raw = request.form.get("role_id")
        active = request.form.get("active") == "on"

        # basic validation
        if not name or not email or not password or not role_id_raw:
            flash(_("Please fill in all required fields."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form)

        # ensure email is unique
        if db.session.query(User).filter_by(email=email).first():
            flash(_("Email already exists."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form)

        try:
            role_id = int(role_id_raw)
        except (TypeError, ValueError):
            flash(_("Invalid role selection."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form)

        role = db.session.get(Role, role_id)
        if not role:
            flash(_("Selected role not found."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form)

        # create user
        user = User(name=name, email=email, phone=phone, role_id=role.id, active=active)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:  # pragma: no cover
            db.session.rollback()
            flash(_("Failed to create user. Please try again."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form)

        flash(_("User created successfully."), "success")
        log_action("create", "User", user.id, {"email": user.email})
        return redirect(url_for("admin.users_list"))

    # Ensure template always receives a form object (empty on initial GET)
    return render_template("admin/user_form.html", roles=roles, form=request.form)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def users_edit(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    roles = db.session.query(Role).order_by(Role.name.asc()).all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        password = request.form.get("password") or ""
        role_id_raw = request.form.get("role_id")
        active = request.form.get("active") == "on"

        if not name or not email or not role_id_raw:
            flash(_("Please fill in all required fields."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form, user=user)

        dup = db.session.query(User).filter(User.email == email, User.id != user.id).first()
        if dup:
            flash(_("Email already exists."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form, user=user)

        try:
            role_id = int(role_id_raw)
        except (TypeError, ValueError):
            flash(_("Invalid role selection."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form, user=user)

        role = db.session.get(Role, role_id)
        if not role:
            flash(_("Selected role not found."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form, user=user)

        user.name = name
        user.email = email
        user.phone = phone
        user.role_id = role.id
        user.active = active
        if password:
            user.set_password(password)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash(_("Failed to update user."), "danger")
            return render_template("admin/user_form.html", roles=roles, form=request.form, user=user)

        flash(_("User updated successfully."), "success")
        log_action("update", "User", user.id, {"email": user.email})
        return redirect(url_for("admin.users_list"))

    form_defaults = {
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "role_id": str(user.role_id) if user.role_id else "",
        "active": user.active,
    }
    return render_template("admin/user_form.html", roles=roles, form=form_defaults, user=user)


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"]) 
@role_required("admin")
def users_delete(user_id: int):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    db.session.delete(user)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash(_("Failed to delete user."), "danger")
        return redirect(url_for("admin.users_list"))
    flash(_("User deleted."), "success")
    log_action("delete", "User", user.id, {"email": user.email})
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/bayarat")
@role_required("admin")
def bayarat_list():
    # Filters: provider, lot_number, date range
    q = db.session.query(Auction)
    provider = (request.args.get("provider") or "").strip()
    lot_number = (request.args.get("lot_number") or "").strip()
    date_from = (request.args.get("date_from") or "").strip()
    date_to = (request.args.get("date_to") or "").strip()

    if provider:
        q = q.filter(db.func.lower(Auction.provider).like(db.func.lower(f"%{provider}%")))
    if lot_number:
        q = q.filter(db.func.lower(Auction.lot_number).like(db.func.lower(f"%{lot_number}%")))

    if date_from:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_from)
            q = q.filter(Auction.auction_date >= dt)
        except Exception:
            pass
    if date_to:
        try:
            from datetime import datetime, timedelta
            dt = datetime.fromisoformat(date_to)
            # include the whole day by adding one day and using < next day
            q = q.filter(Auction.auction_date < (dt + timedelta(days=1)))
        except Exception:
            pass

    auctions = q.order_by(Auction.auction_date.desc(), Auction.id.desc()).limit(300).all()

    # Pre-compute vehicles count per auction
    counts = {}
    if auctions:
        ids = [a.id for a in auctions]
        for aid, cnt in (
            db.session.query(Vehicle.auction_id, db.func.count(Vehicle.id))
            .filter(Vehicle.auction_id.in_(ids))
            .group_by(Vehicle.auction_id)
        ):
            counts[aid] = cnt

    return render_template("admin/bayarat_list.html", auctions=auctions, counts=counts)


@admin_bp.route("/bayarat/new", methods=["GET", "POST"])
@role_required("admin")
def bayarat_new():
    if request.method == "POST":
        provider = (request.form.get("provider") or "").strip()
        lot_number = (request.form.get("lot_number") or "").strip()
        location = (request.form.get("location") or "").strip()
        auction_url = (request.form.get("auction_url") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        auction_date_raw = (request.form.get("auction_date") or "").strip()

        if not (provider or lot_number):
            flash(_("Please enter at least Provider or Lot Number"), "danger")
            return render_template("admin/bayarat_form.html", form=request.form)

        a = Auction(
            provider=provider or None,
            lot_number=lot_number or None,
            location=location or None,
            auction_url=auction_url or None,
            notes=notes or None,
        )

        if auction_date_raw:
            try:
                from datetime import datetime
                a.auction_date = datetime.fromisoformat(auction_date_raw)
            except Exception:
                pass

        db.session.add(a)
        try:
            db.session.commit()
            flash(_("Auction created"), "success")
            log_action("create", "Auction", a.id, {"provider": a.provider, "lot": a.lot_number})
            return redirect(url_for("admin.bayarat_list"))
        except Exception:
            db.session.rollback()
            flash(_("Failed to create auction"), "danger")
            return render_template("admin/bayarat_form.html", form=request.form)

    return render_template("admin/bayarat_form.html", form=request.form)


@admin_bp.route("/bayarat/<int:auction_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def bayarat_edit(auction_id: int):
    a = db.session.get(Auction, auction_id)
    if not a:
        abort(404)

    if request.method == "POST":
        provider = (request.form.get("provider") or "").strip()
        lot_number = (request.form.get("lot_number") or "").strip()
        location = (request.form.get("location") or "").strip()
        auction_url = (request.form.get("auction_url") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        auction_date_raw = (request.form.get("auction_date") or "").strip()

        if not (provider or lot_number):
            flash(_("Please enter at least Provider or Lot Number"), "danger")
            return render_template("admin/bayarat_form.html", form=request.form, auction=a)

        a.provider = provider or None
        a.lot_number = lot_number or None
        a.location = location or None
        a.auction_url = auction_url or None
        a.notes = notes or None

        if auction_date_raw:
            try:
                from datetime import datetime
                a.auction_date = datetime.fromisoformat(auction_date_raw)
            except Exception:
                pass
        else:
            a.auction_date = None

        try:
            db.session.commit()
            flash(_("Auction updated"), "success")
            log_action("update", "Auction", a.id, {"provider": a.provider, "lot": a.lot_number})
            return redirect(url_for("admin.bayarat_list"))
        except Exception:
            db.session.rollback()
            flash(_("Failed to update auction"), "danger")

    form_defaults = {
        "provider": a.provider or "",
        "lot_number": a.lot_number or "",
        "location": a.location or "",
        "auction_url": a.auction_url or "",
        "notes": a.notes or "",
        "auction_date": a.auction_date.strftime("%Y-%m-%d") if a.auction_date else "",
    }
    return render_template("admin/bayarat_form.html", form=form_defaults, auction=a)


@admin_bp.route("/bayarat/<int:auction_id>/delete", methods=["POST"])
@role_required("admin")
def bayarat_delete(auction_id: int):
    a = db.session.get(Auction, auction_id)
    if not a:
        abort(404)
    db.session.delete(a)
    try:
        db.session.commit()
        flash(_("Auction deleted"), "success")
        log_action("delete", "Auction", auction_id, None)
    except Exception:
        db.session.rollback()
        flash(_("Failed to delete auction"), "danger")
    return redirect(url_for("admin.bayarat_list"))
