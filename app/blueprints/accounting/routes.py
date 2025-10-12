from flask import Blueprint, render_template
from flask_login import login_required

acct_bp = Blueprint("acct", __name__, template_folder="templates/accounting")

@acct_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("accounting/dashboard.html")
