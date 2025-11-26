# app/web/dashboard/routes.py

from flask import render_template
from . import dashboard_bp


@dashboard_bp.get("/")
def index():
    return render_template("dashboard.html")


@dashboard_bp.get("/control")
def control_page():
    return render_template("control.html")