"""Flask application factory for victron-bm-webui."""

import logging

from flask import Flask

from app.config import load_config
from app.models import Database
from app.ble_reader import BLEReaderThread, SharedState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    config = load_config()

    app = Flask(__name__)
    app.config["VICTRON"] = config

    # Initialize database
    db = Database(config["database"]["path"])
    db.init()
    app.config["DB"] = db

    # Initialize shared state and BLE reader
    shared_state = SharedState()
    app.config["SHARED_STATE"] = shared_state

    ble_reader = BLEReaderThread(config, shared_state, db)
    ble_reader.start()
    app.config["BLE_READER"] = ble_reader

    from app.views import views_bp
    app.register_blueprint(views_bp)

    return app
