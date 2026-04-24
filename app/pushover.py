"""Pushover notification sending for victron-bm-webui."""

import logging
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger(__name__)


def send_pushover(
    pushover_config: dict[str, Any],
    message: str,
    title: str | None = None,
    priority: int = 0,
) -> bool:
    """Send a push notification using Pushover.

    Args:
        pushover_config: Pushover configuration dictionary with keys:
            token, user.
        message: Notification message.
        title: Optional notification title.
        priority: Notification priority (-2 to 2).

    Returns:
        True if the notification was sent successfully, False otherwise.
    """
    if not pushover_config.get("enabled", False):
        log.debug("Pushover disabled, skipping notification: %s", message)
        return False

    token = pushover_config.get("token")
    user = pushover_config.get("user")

    if not token or not user:
        log.warning("Pushover token or user key not configured")
        return False

    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": token,
        "user": user,
        "message": message,
        "priority": priority,
    }
    if title:
        data["title"] = title

    # Emergency priority requires retry and expire
    if priority == 2:
        data["retry"] = 60  # Retry every 60 seconds
        data["expire"] = 3600  # Expire after 1 hour

    try:
        encoded_data = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=encoded_data, method="POST")
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                log.info("Pushover notification sent: %s", message)
                return True
            else:
                log.error("Pushover API returned status %s", response.status)
                return False

    except Exception:
        log.exception("Failed to send Pushover notification")
        return False
