from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user
from ...extensions import db
from ...models import (
    User,
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
