from flask import Blueprint, render_template, abort, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...extensions import db
from ...models import (
    User,
    Role,
    Customer,
    Vehicle,
    Auction,
    Shipment,
    Invoice,
    CostItem,
    AuditLog,
    Backup,
)

admin_bp = Blueprint("admin", __name__, template_folder="templates/admin")

@admin_bp.route("/dashboard")
@login_required
def dashboard():
    # restrict to admin users only
    user_role = getattr(getattr(current_user, "role", None), "name", None)
    if user_role != "admin":
        abort(403)

    # aggregate counts for top-level entities
    counts = {
        "users": db.session.query(User).count(),
        "customers": db.session.query(Customer).count(),
        "vehicles": db.session.query(Vehicle).count(),
        "auctions": db.session.query(Auction).count(),
        "shipments": db.session.query(Shipment).count(),
        "invoices": db.session.query(Invoice).count(),
        "cost_items": db.session.query(CostItem).count(),
        "audit_logs": db.session.query(AuditLog).count(),
        "backups": db.session.query(Backup).count(),
    }

    # totals
    totals = {
        "revenue_omr": db.session.query(db.func.coalesce(db.func.sum(Invoice.total_omr), 0)).scalar(),
    }

    # recent activity lists
    recent = {
        "vehicles": db.session.query(Vehicle).order_by(Vehicle.created_at.desc()).limit(5).all(),
        "shipments": db.session.query(Shipment).order_by(Shipment.created_at.desc()).limit(5).all(),
        "invoices": db.session.query(Invoice).order_by(Invoice.created_at.desc()).limit(5).all(),
        "users": db.session.query(User).order_by(User.created_at.desc()).limit(5).all(),
        "audit_logs": db.session.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(5).all(),
    }

    return render_template("admin/dashboard.html", counts=counts, totals=totals, recent=recent)


@admin_bp.route("/users")
@login_required
def users_list():
    # restrict to admin users only
    user_role = getattr(getattr(current_user, "role", None), "name", None)
    if user_role != "admin":
        abort(403)

    users = db.session.query(User).order_by(User.created_at.desc()).all()
    return render_template("admin/users_list.html", users=users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@login_required
def users_new():
    # restrict to admin users only
    user_role = getattr(getattr(current_user, "role", None), "name", None)
    if user_role != "admin":
        abort(403)

    roles = db.session.query(Role).order_by(Role.name.asc()).all()
    if not roles:
        flash(
            "No roles found. Initialize roles first from Admin Dashboard Quick Links.",
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
            flash("Please fill in all required fields.", "danger")
            return render_template("admin/user_new.html", roles=roles, form=request.form)

        # ensure email is unique
        if db.session.query(User).filter_by(email=email).first():
            flash("Email already exists.", "danger")
            return render_template("admin/user_new.html", roles=roles, form=request.form)

        try:
            role_id = int(role_id_raw)
        except (TypeError, ValueError):
            flash("Invalid role selection.", "danger")
            return render_template("admin/user_new.html", roles=roles, form=request.form)

        role = db.session.get(Role, role_id)
        if not role:
            flash("Selected role not found.", "danger")
            return render_template("admin/user_new.html", roles=roles, form=request.form)

        # create user
        user = User(name=name, email=email, phone=phone, role_id=role.id, active=active)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:  # pragma: no cover
            db.session.rollback()
            flash("Failed to create user. Please try again.", "danger")
            return render_template("admin/user_new.html", roles=roles, form=request.form)

        flash("User created successfully.", "success")
        return redirect(url_for("admin.users_list"))

    # Ensure template always receives a form object (empty on initial GET)
    return render_template("admin/user_new.html", roles=roles, form=request.form)
