from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_babel import gettext as _
from ...extensions import db
from ...models import User, Role, AuditLog
from ...extensions import db
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash

auth_bp = Blueprint("auth", __name__, template_folder="templates")

@auth_bp.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        pwd = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pwd):
            login_user(user)
            try:
                db.session.add(AuditLog(user_id=user.id, action="login", target_type="Auth", target_id=user.id, meta={"email": user.email}))
                user.last_login_at = db.func.now()
                db.session.commit()
            except Exception:
                db.session.rollback()
            role = user.role.name if user.role else "customer"
            if role == "admin":
                return redirect(url_for("admin.dashboard"))
            if role == "staff":
                return redirect(url_for("ops.dashboard"))
            if role == "accountant":
                return redirect(url_for("acct.dashboard"))
            return redirect(url_for("cust.dashboard"))
        flash(_("Invalid credentials"), "danger")
    return render_template("auth/login.html")

@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))

@auth_bp.route("/init")
def init_sample():
    # create roles and an admin user for quick start (idempotent)
    if not Role.query.filter_by(name="admin").first():
        r1 = Role(name="admin")
        r2 = Role(name="staff")
        r3 = Role(name="accountant")
        r4 = Role(name="customer")
        db.session.add_all([r1,r2,r3,r4])
        db.session.commit()
    if not User.query.filter_by(email="admin@example.com").first():
        admin = User(name="Admin", email="admin@example.com", role=Role.query.filter_by(name="admin").first())
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
    return "Initialized sample roles and admin user (admin@example.com / admin123)"
