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
        "max_scanner_restarts": 3,
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
        "ac_power_voltage": None,
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
        "ac_power_lost": True,
        "ac_power_restored": True,
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

    # Apply environment variable overrides
    _apply_device_env_overrides(config)
    _apply_smtp_env_overrides(config)

    return config


def _apply_device_env_overrides(config: dict[str, Any]) -> None:
    """Override device config values from environment variables.

    Environment variables (all optional, only non-empty values are applied):
        DEVICE_MOCK, BLE_MAC_ADDRESS, BLE_ADV_KEY.
    """
    device = config.setdefault("device", {})

    mac = os.environ.get("BLE_MAC_ADDRESS", "").strip()
    if mac:
        device["mac_address"] = mac

    adv_key = os.environ.get("BLE_ADV_KEY", "").strip()
    if adv_key:
        device["advertisement_key"] = adv_key

    mock_val = os.environ.get("DEVICE_MOCK", "").strip()
    if mock_val:
        device["mock"] = mock_val.lower() in ("true", "1", "yes")


def _apply_smtp_env_overrides(config: dict[str, Any]) -> None:
    """Override SMTP config values from environment variables.

    Environment variables (all optional, only non-empty values are applied):
        SMTP_ENABLED, SMTP_SERVER, SMTP_PORT, SMTP_USE_TLS,
        SMTP_USERNAME, SMTP_PASSWORD, SMTP_SENDER_NAME,
        SMTP_SENDER_EMAIL, SMTP_RECIPIENTS (comma-separated).
    """
    smtp = config.setdefault("smtp", {})

    env_map = {
        "SMTP_ENABLED": ("enabled", lambda v: v.lower() in ("true", "1", "yes")),
        "SMTP_SERVER": ("server", str),
        "SMTP_PORT": ("port", int),
        "SMTP_USE_TLS": ("use_tls", lambda v: v.lower() in ("true", "1", "yes", "auto")),
        "SMTP_USERNAME": ("username", str),
        "SMTP_PASSWORD": ("password", str),
        "SMTP_SENDER_NAME": ("sender_name", str),
        "SMTP_SENDER_EMAIL": ("sender_email", str),
    }

    for env_var, (key, converter) in env_map.items():
        val = os.environ.get(env_var, "").strip()
        if val:
            try:
                smtp[key] = converter(val)
            except (ValueError, TypeError):
                pass

    recipients_env = os.environ.get("SMTP_RECIPIENTS", "").strip()
    if recipients_env:
        smtp["recipients"] = [r.strip() for r in recipients_env.split(",") if r.strip()]


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
