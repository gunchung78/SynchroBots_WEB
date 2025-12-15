from flask import render_template
from . import web_bp

@web_bp.route("/")
def index():
    return render_template("dashboard.html", active_page="dashboard")

@web_bp.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", active_page="dashboard")

@web_bp.route("/control")
def control():
    return render_template("control.html", active_page="control")

@web_bp.route("/logs/vision")
def vision_logs():
    return render_template("vision_logs.html", active_page="vision_logs")
