from flask import Blueprint, render_template
from flask_login import login_required, current_user

admin_bp = Blueprint("admin", __name__, template_folder="templates/admin")

@admin_bp.route("/dashboard")
@login_required
def dashboard():
    # simple admin dashboard stub
    return render_template("admin/dashboard.html")
