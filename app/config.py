"""Configuration loader for victron-bm-webui."""

import os

import yaml

DEFAULT_CONFIG = {
    "web": {
        "host": "0.0.0.0",
        "port": 80,
    },
}


def load_config(path: str = None) -> dict:
    """Load configuration from YAML file, merging with defaults.

    Args:
        path: Path to config file. If None, uses CONFIG_PATH env var
              or falls back to /app/config/config.yaml.

    Returns:
        Merged configuration dictionary.
    """
    if path is None:
        path = os.environ.get("CONFIG_PATH", "/app/config/config.yaml")

    config = dict(DEFAULT_CONFIG)

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
