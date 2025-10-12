from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required

ops_bp = Blueprint("ops", __name__, template_folder="templates/operations")

@ops_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template("operations/dashboard.html")
