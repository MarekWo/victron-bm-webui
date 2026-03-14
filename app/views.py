"""Web UI routes for victron-bm-webui."""

from flask import Blueprint, render_template

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def dashboard():
    """Render the main dashboard page."""
    return render_template("dashboard.html")


@views_bp.route("/trends")
def trends():
    """Render the trends page (placeholder)."""
    return render_template("trends.html")


@views_bp.route("/alarm-log")
def alarm_log():
    """Render the alarm log page (placeholder)."""
    return render_template("alarm_log.html")


@views_bp.route("/info")
def info():
    """Render the info/about page (placeholder)."""
    return render_template("info.html")
