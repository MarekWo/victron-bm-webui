"""Configuration loader for victron-bm-webui."""

import os
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "device": {
        "mac_address": "",
        "advertisement_key": "",
        "name": "BMV-712 Smart",
        "mock": False,
    },
    "ble": {
        "poll_interval_seconds": 10,
    },
    "web": {
        "host": "0.0.0.0",
        "port": 80,
    },
    "database": {
        "path": "/data/victron-bm.db",
        "retention_days": 30,
    },
    "alarms": {
        "low_voltage": 11.5,
        "high_voltage": 15.0,
        "low_soc": 20.0,
        "high_temperature": 45.0,
        "low_temperature": 0.0,
    },
    "smtp": {
        "enabled": False,
        "server": "",
        "port": 587,
        "use_tls": True,
        "username": "",
        "password": "",
        "sender_name": "Victron BM Monitor",
        "sender_email": "",
        "recipients": [],
    },
    "notifications": {
        "alarm_triggered": True,
        "alarm_cleared": True,
        "threshold_exceeded": True,
        "device_offline": True,
        "device_online": True,
    },
}


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load configuration from YAML file, merging with defaults.

    Args:
        path: Path to config file. If None, uses CONFIG_PATH env var
              or falls back to /app/config/config.yaml.

    Returns:
        Merged configuration dictionary.
    """
    if path is None:
        path = os.environ.get("CONFIG_PATH", "/app/config/config.yaml")

    config = _deep_merge(DEFAULT_CONFIG, {})

    if os.path.exists(path):
        with open(path, "r") as f:
            user_config = yaml.safe_load(f) or {}
        config = _deep_merge(config, user_config)

    return config


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
