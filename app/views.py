"""Web UI routes for victron-bm-webui."""

from flask import Blueprint, current_app, jsonify, render_template

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
def dashboard():
    """Render the main dashboard page."""
    config = current_app.config["VICTRON"]
    device_name = config["device"].get("name", "BMV-712 Smart")
    return render_template("dashboard.html", device_name=device_name)


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


@views_bp.route("/api/internal/current")
def api_internal_current():
    """Return current device state as JSON for AJAX polling."""
    shared_state = current_app.config.get("SHARED_STATE")
    if shared_state is None:
        return jsonify({"error": "No data available"}), 503

    data = shared_state.get()
    return jsonify(data)
