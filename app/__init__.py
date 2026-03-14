"""Flask application factory for victron-bm-webui."""

from flask import Flask

from app.config import load_config


def create_app() -> Flask:
    """Create and configure the Flask application."""
    config = load_config()

    app = Flask(__name__)
    app.config["VICTRON"] = config

    from app.views import views_bp
    app.register_blueprint(views_bp)

    return app
